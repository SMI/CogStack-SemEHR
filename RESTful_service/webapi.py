from os import listdir
from os.path import isfile, join
import codecs
import json
import re
import logging
import random
import utils
from multiprocessing import Manager
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError
import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json
from psycopg2.extensions import AsIs
import umls
import glob
import os
import uuid
from datetime import date


def save_json_array(lst, file_path, encoding='utf-8'):
    with codecs.open(file_path, 'w', encoding=encoding) as wf:
        json.dump(lst, wf)


def load_json_data(file_path):
    data = None
    with codecs.open(file_path, encoding='utf-8') as rf:
        data = json.load(rf)
    return data

def pg_row_to_dict(row, colnames):
    """ Convert a tuple returned from a psycopg2 query into a dict
    using the list of colnames. """
    retdict = {}
    for ii in range(len(colnames)):
        retdict[colnames[ii]] = row[ii]
    return retdict


# ---------------------------------------------------------------------
class DocAnn(object):
    def __init__(self):
        self._map_name = ''
        self._mappings = {}
        self._transaction_dir = None
        self._training_dir = None

    def set_transaction_dir(self, tdir):
        """ Called by webserver.py with the value from the config file.
        The internal value is used by the postgres query()
        """
        self._transaction_dir = tdir

    def set_training_dir(self, tdir):
        """ Called by webserver.py with the value from the config file.
        The internal value is used by the postgres put_trained_docs()
        """
        self._training_dir = tdir

    def get_doc_list(self):
        pass

    def get_doc_content(self, doc_id):
        pass

    def get_doc_ann(self, doc_id):
        return DocAnn.default_filtering(self.raw_doc_ann(doc_id))

    def raw_doc_ann(self, doc_id):
        pass

    def load_mappings_dir(self, mappings_dir):
        """ Load all the JSON files in a directory.
        The filename is the mapping name, the content is as below.
        """
        mapping_list = []
        for file in glob.glob(os.path.join(mappings_dir, '*.json')):
            mapping_name = os.path.basename(file).replace('.json','')
            mapping_list.append( { 'name': mapping_name,
                'file': file } )
        self.load_mappings(mapping_list)

    def load_mappings(self, mappings):
        """ mappings is a list of dictionaries:
        {'name':'mapname, 'file':'/path/file.json'}
        where the json file contains a dictionary with
        eg. "HP:0001489": ["C0423361"],
        so each key in the mapping can be a list of CUIs.
        The CUIs can be a string "CUI\tPREF\tSTY" for
        compatibility with nlp2phenome (PREF,STY ignored here).
        This function unpacks the list of CUIs and creates
        a reverse mapping from CUI to the term name.
        self._mappings['mapname'] = { 'CUI':'term' }
        """
        for m in mappings:
            mm = {}
            logging.debug('Loading mapping %s from %s' % (m['name'], m['file']))
            term2umls = load_json_data(m['file'])
            for term in term2umls:
                for cui in term2umls[term]:
                    cui = cui.split('\t')[0] # eg. C123 from "C123\tPref\tSty"
                    mm[cui] = term
            self._mappings[m['name']] = mm

    def mapping_cui_list(self, map_name):
        """ Return a list of the CUIs in the map
        regardless of what terms they map to.
        Returns empty list if map not known.
        """
        return [cui for cui in self._mappings.get(map_name, [])]

    def get_doc_ann_by_mapping(self, doc_id, map_name):
        """ same as get_doc_ann() but also
        adds a 'mapped' field to each annotation that
        has a CUI in the given mapping table giving
        the phenotype name for that CUI.
        Annotations not in the mapping are removed.
        The whole doc has 'mapping_name' added.
        """
        doc_anns = self.get_doc_ann(doc_id)
        umls2term = None if map_name not in self._mappings else self._mappings[map_name]
        if umls2term is None:
            logging.error('mapping %s not found' % map_name)
            return doc_anns
        anns = doc_anns['annotations']
        mapped = []
        for ann in anns:
            if ann['cui'] in umls2term:
                ann['mapped'] = umls2term[ann['cui']]
                mapped.append(ann)
        doc_anns['annotations'] = mapped
        doc_anns['mapping_name'] = map_name
        return doc_anns

    def is_mapping(self, map_name):
        return map_name in self._mappings

    def get_available_mappings(self):
        return list(self._mappings.keys())

    # def search_docs(self, query):
    #     query = '\\b%s\\b' % query
    #     matched_docs = Manager().list()
    #     utils.multi_process_tasking(self.get_doc_list(), DocAnn.do_search_doc, args=[self, query, matched_docs])
    #     return list(matched_docs)
    #
    # def search_anns(self, query, map_name=None):
    #     matched_docs = Manager().list()
    #     utils.multi_process_tasking(self.get_doc_list(), DocAnn.do_search_anns,
    #                                args=[self, query, map_name, matched_docs])
    #     return list(matched_docs)

    @staticmethod
    def default_filtering(doc_anns):
        anns = doc_anns['annotations']
        mapped = []
        for ann in anns:
            if len(ann['ruled_by']) > 0 and \
                    ('not_mention_filters.json' in ann['ruled_by']
                     or 'skip terms' in ann['ruled_by']):
                pass
            else:
                mapped.append(ann)
        doc_anns['annotations'] = mapped
        return doc_anns

    @staticmethod
    def do_search_doc(d, inst, query, container):
        content = inst.get_doc_content(d)
        if re.search(query, content, re.IGNORECASE):
            container.append(d)

    @staticmethod
    def do_search_anns(d, inst, query, map_name, container):
        ann_obj = inst.get_doc_ann(d) if map_name is None else inst.get_doc_ann_by_mapping(d, map_name)
        matched = False
        for ann in ann_obj['annotations']:
            if re.search(query, ' | '.join([str(ann['str']), str(ann['pref']), ann['cui'], ann['sty']]), re.IGNORECASE):
                container.append(d)
                matched = True
                break
        if not matched:
            for ann in ann_obj['phenotypes']:
                if re.search(query, ' | '.join([str(ann['str']), ann['minor_type']])):
                    container.append(d)
                break


# ---------------------------------------------------------------------
class FileBasedDocAnn(DocAnn):
    def __init__(self, doc_folder, ann_folder):
        super().__init__()
        self._doc_folder = doc_folder
        self._ann_folder = ann_folder
        self._file_list = None

    def get_doc_list(self):
        if self._file_list is not None:
            return self._file_list
        self._file_list = [f for f in listdir(self._doc_folder) if isfile(join(self._doc_folder, f))]
        return self._file_list

    def get_doc_content(self, doc_id):
        return FileBasedDocAnn.read_text_file(join(self._doc_folder, doc_id))

    def raw_doc_ann(self, doc_id, ptn='se_ann_%s.json'):
        return FileBasedDocAnn.load_json(join(self._ann_folder, ptn % doc_id[:doc_id.rfind('.')]))

    @staticmethod
    def read_text_file(path):
        s = None
        with codecs.open(path) as rf:
            s = rf.read()
        return s

    @staticmethod
    def load_json(file_path):
        data = None
        with codecs.open(file_path, encoding='utf-8') as rf:
            data = json.load(rf)
        return data


# ---------------------------------------------------------------------
class PostgresDocAnn(DocAnn):
    def __init__(self, conf):
        super().__init__()
        self._host = conf['host']
        self._user = conf['user']
        self._pwd = conf['password']
        self._db = conf['db']
        self._schema = conf['schema']
        self._ann_collection = conf['ann_collection']
        self._text_collection = conf['text_collection'] # XXX not used
        self._pgConnection = None
        self._pgCursor = None
        self.umls_map = umls.UMLSmap(settings = conf)
        self._default_query_depth = 0
        self._uuid = ''
        self._has_cuisop = False


    def open_database(self):
        """ Open a connection to the database using the credentials
        held in the class variables _host, _user, etc.
        Sets self._pgConnection to be used by other methods.
        Sets self._has_cuisop to True if the "cui_sop" table exists.
        """
        logging.info('Connecting to postgresql')
        self._pgConnection = psycopg2.connect(host=self._host, user=self._user, password=self._pwd, dbname=self._db)
        # Set the schema name so it doesn't need to be specified before each table name
        self._pgConnection.cursor().execute(sql.SQL("SET search_path TO {},public").format(sql.Identifier(self._schema)))
        self._pgConnection.commit()
        # Find out if the "cui_sop" table exists (only in new database)
        cursor = self._pgConnection.cursor()
        cursor.execute("SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name='cui_sop')")
        if bool(cursor.fetchone()[0]):
            self._has_cuisop = True


    def save_transaction(self, docs):
        """ Save the current docs (actually just SOPInstanceUID,
        or Series if not SOP, or Study if not Series)
        in a file in the transaction dir (defined in settings file)
        with a filename being the current uuid value.
        docs should be an array of dicts containing SOPInstanceUID.
        """
        if not self._transaction_dir:
            return
        if not self._uuid:
            return
        if not docs or not isinstance(docs, list):
            return
        os.makedirs(self._transaction_dir, exist_ok = True)
        with open(os.path.join(self._transaction_dir, self._uuid + '.json'), 'w') as fd:
            logging.debug('Saving transaction %s' % self._uuid)
            # Save a list of the most defining element of all docs
            if 'SOPInstanceUID' in docs[0]:
                fd.write(json.dumps([doc['SOPInstanceUID'] for doc in docs]))
            elif 'SeriesInstanceUID' in docs[0]:
                fd.write(json.dumps([doc['SeriesInstanceUID'] for doc in docs]))
            elif 'StudyInstanceUID' in docs[0]:
                fd.write(json.dumps([doc['StudyInstanceUID'] for doc in docs]))
            else:
                # probably a pure list of SOPInstanceUIDs rather than dicts
                fd.write(json.dumps(docs))

    # No longer a static method, was @staticmethod, so we can set uuid
    def format_doc_list_rets(self, docs):
        """ Convert the 'docs' object into a structure to be
        returned from the web interface by adding a header.
        """
        logging.debug('format_doc_list_rets')
        retdict = {
            "success": True,
            "num_results": len(docs),
            "results": docs,
            "transactionId": self._uuid
        }
        # Only query() sets uuid
        if self._uuid:
            self.save_transaction(docs)
        return retdict

    def get_doc_list(self):
        logging.debug('get_doc_list')
        # TODO: to do pagination
        #   docs = self.query({}, pagination={'skip': 0, 'limit': 10}, filter={'SOPInstanceUID': 1})
        # docs = self.query({}, filter={'SOPInstanceUID': 1})
        docs = [] # do not try to query all docs, it's pointless
        return self.format_doc_list_rets(docs)

    def get_doc_content(self, doc_id):
        logging.debug('XXX get_doc_content not yet implemented')
        # TODO: get the document text content
        return ""

    def raw_doc_ann(self, doc_id):
        logging.debug('raw_doc_ann')
        q = {"SOPInstanceUID": doc_id}
        rets = self.query(q)
        return None if len(rets) == 0 else rets[0]

    def cui_list_filtered_to_used(self, cui_list):
        """ Given a list of CUIs filter it to contain only
        those CUIs which have actually been used in the database.
        Requires a populated table cui_count.
        XXX not yet implemented
        """
        logging.debug('XXX not yet implemented: cui_list_filtered_to_used')
        if not cui_list:
            logging.error('XXX cui_list_filtered_to_used has an empty list - should return this info to user')
        return cui_list

    def re_snomed_match(self, snomed):
        """ If the string looks like a SNOMED (string of digits)
        then return the matched characters, or None if not like a SNOMED.
        """
        snomed_match = re.match(r'^\s*([0-9]{7,15})\s*$', snomed)
        if snomed_match:
            return snomed_match[1]
        return None

    def re_cui_match(self, cui):
        """ If the string looks like a CUI (letter C followed by digits)
        then return the matched characters, or None if not like a CUI.
        """
        cui_match = re.match(r'^\s*([Cc][0-9]{5,15})\s*$', cui)
        if cui_match:
            return cui_match[1]
        return None

    def query_or_cui_to_cui_list(self, q, qdepth = 0, qstop = [], qonlysty = True):
        """ Given a query string which may be:
        * free text e.g. "lung"
        * a SNOMED e.g. "456"
        * a CUI in the form Cnnnnnnn e.g. "C123"
        * a comma-separated list of the above e.g. "C123,456"
        * an actual list of the above e.g. ["C123","456"]
        return an expanded list of CUIs filtered to
        only those which occur in the database.
        Expansion is done using cui_narrower, or
        if q is the name of a mapping then all CUIs in the map are returned.
        Returns an empty list if q is a text string (not CUI or mapping name).
        """
        cui_list = []

        # Turn it into a list (if not already)
        if isinstance(q, list):
            qlist = q
        else:
            qlist = q.split(',')

        for q in qlist:
            # If it's a SNOMED code then convert it 
            snomed_match = self.re_snomed_match(q)
            if snomed_match:
                sc = self.umls_map.snomed_to_cui(snomed_match)
                logging.debug('SNOMED %s -> CUI %s' % (snomed_match, sc))
                if sc:
                    q = sc
                # XXX else need to return an error message that SNOMED doesn't exist.

            cui_match = self.re_cui_match(q)
            if cui_match:
                # Looks like a CUI so use the index on the array of CUIs
                # Query expansion:
                cui_list.extend(self.umls_map.cui_narrower(cui_match, maxdepth=qdepth, filter_to_same_tui=qonlysty, prunelist=qstop))
            elif self.is_mapping(q):
                # Not a CUI, so check if it's the name of a mapping
                cui_list.extend(self.mapping_cui_list(q))
                logging.debug('Mapped %s to %s' % (q, cui_list))
            else:
                pass # return an empty list if q is plain text

        # Filter this list down to just the CUIs which are present in the database.
        # XXX if that results in zero then return an error message that no CUIs present.
        cui_list = self.cui_list_filtered_to_used(cui_list)

        return cui_list


    def query_or_cui_list_to_sql(self, q):
        """ Given a query which may be a list of CUIs, or a free text string,
        return a SQL object being the query expression,
        i.e. annotation_array_as_text_array(semehr_results, 'cui') && ARRAY[CUI,CUI,...]
        or   to_tsvector(annotation_array_as_text(semehr_results, 'pref')) @@ websearch_to_tsquery(q)
        If you have the cui_sop table it will become
        SOPInstanceUID IN ( SELECT SOPInstanceUID FROM cui_sop WHERE cui IN ('C111','C222') ), or
        SOPInstanceUID = ANY( ARRAY( SELECT SOPInstanceUID FROM cui_sop WHERE cui IN ('C111','C222') ) )
        """
        cui_list = q if isinstance(q, list) else []
        cui_list_as_pg_array = ','.join(["'"+x+"'" for x in cui_list]) # e.g. 'c1','c2'
        logging.debug('Filtered list of CUI to find: %s' % cui_list)
        # Create SQL using new cui_sop table if available
        if self._has_cuisop and len(cui_list) > 0:
            sql_query = " SOPInstanceUID = ANY(ARRAY( SELECT SOPInstanceUID FROM {cuitab} WHERE cui IN ("
            sql_exe = sql.SQL(sql_query).format(cuitab = sql.Identifier('cui_sop'))
            sql_exe += sql.SQL(',').join([sql.Literal(n) for n in cui_list])
            sql_exe += sql.SQL(')))')
            return sql_exe
       # Create SQL
        if len(cui_list) > 1:
            # XXX why using public schema for function???
            sql_query = "(annotation_array_as_text_array(semehr_results, 'cui') && ARRAY[%s])" % cui_list_as_pg_array
            sql_exe = sql.SQL(sql_query)
        elif len(cui_list) > 0:
            # Only one to search for.
            # XXX why using public schema for function???
            sql_query = "(annotation_array_as_text_array(semehr_results, 'cui') @> ARRAY[{qu}])"
            sql_exe = sql.SQL(sql_query).format(qu = sql.Literal(cui_list[0]))
        else:
            # Looks like words so use the English index on 'pref'
            sql_query = "(to_tsvector('english', semehr.annotation_array_as_text(semehr_results, 'pref')) @@ websearch_to_tsquery('english', {qu}))"
            sql_exe = sql.SQL(sql_query).format(qu = sql.Literal(q))
        return sql_exe


    def query(self, q, collection=None, filter=None, pagination=None, queryDict=None, map_name=None):
        """ Query the database of documents:
        q is the query term, can be a free text string,
          or a CUI in the form Cnnnnnnn, (or a sequence of, incl - to negate?),
          (or a SNOMED code which is all digits? not yet implemented)
          or is a dict {"SOPInstanceUID": doc_id} to get a whole single document,
          or the empty dict {} for a list of all documents, but why??? XXX this returns [].
          if a queryDict is supplied with a term then q is ignored.
        collection can be None or semehr_results (there's no separate collection to return whole documents)
        filter can be None or { 'SOPInstanceUID':1 } to return only that field from the document
          (this returns any document field as text, not the column called SOPInstanceUID)
        pagination can be None to start a query, subsequently followed by a dict
          { "skip": num_to_skip, "limit": num_to_return }
        queryDict is additional search criteria
          terms: [ { q: query_text, qdepth, qstop, negation, experiencer, temporality }, ... ]
          filter: { modalities[], start_date, end_date }
          returnFields: [ "SOPInstanceUID", "SeriesInstanceUID", "StudyInstanceUID" ]
        map_name can be the name of a mapping which will be used as the list of CUIs
        for replacing CUIs with phenotypes in results.
        """

        """ Query processing:
          SELECT filter_col FROM X WHERE Y AND Z
            filter_col is semehr_results (the doc),
              or SOPInstanceUID if only ids are wanted,
              or semehr_results->>K for specific json element(s)
               (as defined in returnFields or if q is a dict).
            X is semehr_results (the table name) or collection if given.
            If no queryDict and q is a plain text string, Y is annotation_array_as_text(pref) @@ q
            If no queryDict and q is a CUI, Y is annotation_array_as_text_array(cui) @> q
            If queryDict:
             q (as above using pref or cui as appropriate)
             AND semehr_results->'annotations' @> '[{"cui":q,"negation":"Affirmed"}]' (use)above one too as indexed)
             AND modalities_as_array(semehr_results-->modalities_in_study) @> modalities
             AND semehr_results-->study_date BETWEEN start_date AND end_date ** should index this as a date?
        """

        """
        New query SQL to use the cui_sop table
        SELECT semehr_results FROM semehr_results WHERE
          SOPInstanceUID IN ( SELECT SOPInstanceUID FROM cui_sop WHERE cui = 'C0205076' )
        or with a date range:
        SELECT semehr_results FROM semehr_results WHERE
          (cast_to_date(semehr_results->>'ContentDate') BETWEEN '2010-01-02' AND '2010-01-10') AND
          SOPInstanceUID IN ( SELECT SOPInstanceUID FROM cui_sop WHERE cui = 'C0205076' )
        sql_args = ()
        sql_str = "SELECT semehr_results FROM {tab} WHERE "
        sql_str += " SOPInstanceUID IN ("
        sql_str += "   SELECT SOPInstanceUID FROM {cuitab} WHERE cui = %s "
        sql_args += (cui,)
        sql_str += " );"
        """

        logging.debug('query %s called with collection %s filter %s pagination %s dict %s' % (q,collection,filter,pagination,queryDict))

        # The collection can name a *table* in the database, to override the one in conf/settings.
        if not collection:
            collection = self._ann_collection

        # The filter can specify if only SOPInstanceUID should be returned (or PatientID).
        # The default is to return the whole of the semehr_results column (the JSONB doc).
        # Specify filter like {'SOPInstanceUID':1} to return that field from the doc.
        # New API has returnFields in queryDict which is an array of fields to return,
        # all taken from the top level of the json doc.
        # This was previously implemented as a set (to ensure uniqueness?) but that
        # loses the order of the elements so we use list/append instead of set/add.
        # XXX Should restrict the fields to prevent extraction of sensitive data.
        # XXX   especially delete PatientID before returning doc.
        filter_set = list()
        filter_names = list()
        if queryDict:
            if 'returnFields' in queryDict:
                for key in queryDict['returnFields']:
                    filter_set.append(f"semehr_results ->> '{key}'")
                    filter_names.append(f"{key}")
            # Default to SOPInstanceUID
            if not filter_set:
                filter_set.append("semehr_results ->> 'SOPInstanceUID'")
                filter_names.append("SOPInstanceUID")
        elif filter:
            filter_col=""
            for key in filter:
                if filter[key] == 1:
                    # use ->> to extract as text
                    filter_set.append(f"semehr_results ->> '{key}'")
                    filter_names.append(f"{key}")
        if not filter_set:
            filter_set.append("semehr_results")
            filter_names.append("semehr_results")
        filter_col = ','.join([x for x in filter_set])

        # Connect to database
        self.open_database()

        # SQL select
        sql_select_exe = sql.SQL('SELECT DISTINCT %s FROM {tab} WHERE ' % filter_col).format(tab = sql.Identifier(collection))

        # Convert the query parameter into PostgreSQL statement.
        if isinstance(q, dict):
            # If 'q' is a dict then it normally means a request for ALL documents,
            # or just one whole document given a SOPInstanceUID.
            # Don't allow all documents to be returned, pointless.
            if q == {}:
                return []
            # XXX this only handles one element in the dict
            for key in q:
                if key == 'SOPInstanceUID':
                    # Handle key which is actual column in table
                    sql_query = "{key} = {val} "
                    # Sadly sql.Identifier puts quotes round column names but postgresl turns column names lowercase (if not quoted during creation) so need to lower() here
                    sql_exe = sql_select_exe + sql.SQL(sql_query).format(key=sql.Identifier(key.lower()), val=sql.Literal(q[key]))
                else:
                    # Handle keys which are elements in the json document
                    sql_query = "semehr_results->>{key} = {val} "
                    # Sadly sql.Identifier puts quotes round column names but postgresl turns column names lowercase (if not quoted during creation) so need to lower() here
                    sql_exe = sql_select_exe + sql.SQL(sql_query).format(key=sql.Identifier(key.lower()), val=sql.Literal(q[key]))
        else:
            if not queryDict:
                # If not supplied then construct from 'q'
                queryDict = { 'terms': [ { 'q': q } ] }
            # The full query is in queryDict so we can ignore 'q'
            sql_query_term_exe = sql.SQL('')
            for term in queryDict['terms']:
                # If sql query already started then AND the next term
                if sql_query_term_exe != sql.SQL(''):
                    sql_query_term_exe += sql.SQL(' AND ')
                # If query looks like a CUI (or SNOMED) then expand it
                # If query looks like the name of a mapping then expand it
                # Otherwise it's a plain text string so leave it alone.
                cui_list = self.query_or_cui_to_cui_list(term['q'],
                    qdepth=term.get('qdepth', self._default_query_depth), # XXX default to one level down
                    qstop=term.get('qstop', []),  # XXX default to no removing child nodes
                    qonlysty=term.get('qonlysty', True)) # XXX default to keeping only semantic types in same group
                # Start with a SQL query which uses the index to narrow down to possible docs of interest
                if cui_list:
                    sql_query_term_exe += self.query_or_cui_list_to_sql(cui_list)
                else:
                    sql_query_term_exe += self.query_or_cui_list_to_sql(term['q'])
                # Add on the qualifiers such as negation or experiencer.
                # Aim to build SQL like semehr_results->'annotations' @> '[{"cui":q,"negation":"Affirmed"}]'
                # XXX can't search for q LIKE pref if also adding negation etc
                negation_term = term.get('negation', 'Any')
                experiencer_term = term.get('experiencer', 'Any')
                temporality_term = term.get('temporality', 'Any')
                if temporality_term == ['Any']:
                    temporality_term = 'Any'
                if (negation_term != 'Any' or
                    temporality_term != 'Any' or
                    experiencer_term != 'Any'):
                    if cui_list:
                        first_term = '"cui":"%s"' % cui_list[0] # XXX need an expression for EVERY cui in cui_list
                    else:
                        first_term = '"pref":"%s"' % term['q']
                    if negation_term != 'Any':
                        first_term += ',"negation":"%s"' % term['negation']
                    if temporality_term not in ('Any', ['Any']):
                        # XXX could be a list but we can't handle multiple values right now
                        # XXX so just use the first
                        if isinstance(temporality_term, list):
                            first_term += ',"temporality":"%s"' % temporality_term[0]
                        else:
                            first_term += ',"temporality":"%s"' % temporality_term
                    if experiencer_term != 'Any':
                        first_term += ',"experiencer":"%s"' % term['experiencer']
                    if first_term:
                        sql_query_term_exe += sql.SQL(" AND (semehr_results->'annotations' @> '[{%s}]') " % first_term)

            # Apply the date range and modality filters
            sql_query_filter = ''
            # Convert given dates from YYY-MM-DD to DICOM style YYYYMMDD
            # if no start date use 1990, if no end date use today
            start_date = queryDict.get('filter', {}).get('start_date', '').replace('-', '')
            end_date = queryDict.get('filter', {}).get('end_date', '').replace('-', '')
            if start_date and not end_date:
                end_date = str(date.today()).replace('-', '')
            if end_date and not start_date:
                start_date = '19900101'
            modalities = queryDict.get('filter', {}).get('modalities', 'Any') # i.e. 'Any' if not set
            sopinstanceuids = queryDict.get('filter', {}).get('sopinstanceuid', [])
            seriesinstanceuids = queryDict.get('filter', {}).get('seriesinstanceuid', [])
            studyinstanceuids = queryDict.get('filter', {}).get('studyinstanceuid', [])
            if modalities not in ('Any', ['Any']):
                if isinstance(modalities, str):
                    # Convert string CT,MR into 'CT','MR'
                    marr = ','.join(["'"+x+"'" for x in modalities.split(',')])
                else:
                    # Convert arrray ['CT','MR'] into string
                    marr = ','.join(["'"+x+"'" for x in modalities])
                sql_query_filter += " AND (regexp_split_to_array(semehr_results->>'ModalitiesInStudy', '\\\\') && ARRAY[%s]) " % marr
            if start_date and end_date:
                # XXX need to sanity-check the string matches YYYYMMDD or use {sd} AND {ed} Literals
                sql_query_filter += " AND (cast_to_date(semehr_results->>'ContentDate') BETWEEN {sd} AND {ed}) "
            if sopinstanceuids:
                # SOPInstanceUID is a column so see if it matches
                sarr = ",".join(["('"+ inst +"')" for inst in sopinstanceuids])
                sql_query_filter += " AND (semehr_results.SOPInstanceUID IN (VALUES %s)) " % sarr
            if seriesinstanceuids:
                # SeriesInstanceUID is a JSON element
                sarr = ",".join(["('"+ inst +"')" for inst in seriesinstanceuids])
                sql_query_filter += " AND ((semehr_results->>'SeriesInstanceUID') IN (VALUES %s)) " % sarr
            if studyinstanceuids:
                # StudyInstanceUID is a JSON element
                sarr = ",".join(["('"+ inst +"')" for inst in studyinstanceuids])
                sql_query_filter += " AND ((semehr_results->>'StudyInstanceUID') IN (VALUES %s)) " % sarr
            sql_query_filter_exe = sql.SQL(sql_query_filter).format(sd = sql.Literal(start_date), ed=sql.Literal(end_date))
            sql_exe = sql_select_exe + sql_query_term_exe + sql_query_filter_exe

        logging.info('querying [%s] using "%s" ...' % (q, sql_exe.as_string(self._pgConnection)))

        if pagination is None:
            self._pgCursor = self._pgConnection.cursor()
            logging.debug('execute SQL %s' % self._pgCursor.mogrify(sql_exe).decode())
            self._pgCursor.execute(sql_exe)
            fetched = self._pgCursor.fetchall()
        else:
            # XXX first time around the query hasn't been execute()d yet so cannot scroll yet
            # so always ensure you set pagination=None when making first call.
            self._pgCursor.scroll(pagination['skip'], mode='absolute')
            fetched = self._pgCursor.fetchmany(size = pagination['limit'])

        # If only wanting a single value returned (eg. SOPInstanceUID)
        # then extract the first element from each tuple returned
        # otherwise return the whole tuple and leave the caller to decode it.
        if len(filter_set) == 1:
            rets = [row[0] for row in fetched]
        else:
            rets = [pg_row_to_dict(row, filter_names) for row in fetched]
        logging.debug('num results = %d' % len(fetched))
        logging.info('query result set size %s for %s' % (len(fetched), q))

        # Finish the query
        logging.debug('postgres commit')
        self._pgConnection.commit()
        self._uuid = str(uuid.uuid4())
        return rets


    def search_anns(self, q, map_name=None, queryDict=None):
        """ search annotations
        queryDict has the form:
          terms: [  {q=QUERY, negation=, experiencer=, temporality=}, ...]
          filter: {start_date=, end_date=, modalities=}
        map_name can replace CUIs in results with phenotypes from mapping.
        """
        logging.debug('search_anns for %s in %s (%s)' % (q, map_name, queryDict))
        # Replace the original q with the one from the queryDict if available
        if queryDict:
            q = queryDict.get('terms',[{}]) [0] .get('q',q)
        rets = self.query(q, filter={'SOPInstanceUID': 1}, queryDict=queryDict, map_name=map_name)
        return self.format_doc_list_rets(rets)

    def search_docs(self, query, queryDict=None):
        logging.debug('search_docs (ERROR NOT YET IMPLEMENTED?')
        return query(query)

    def get_training_docs(self, transaction_id):
        """ Get a random set of document annotations from the query
        identified by the transaction_id, a uuid returned by a query.
        """
        logging.error('get_training_docs %s NOT YET IMPLEMENTED' % transaction_id)
        # Get random select of docs given a transaction_id (uuid).
        # read list of document identifiers,
        # get a random subset,
        # make a query to retrieve the actual document annotations with those ids,
        # convert to XML,
        # return in a zip with uuid as filename.
        doc_list = []
        # read transaction_dir/<uuid>.json which has list of docs
        # XXX it may contain Study or Series identifiers not SOPInstance??
        with open(os.path.join(self._transaction_dir, transaction_id + '.json')) as fd:
            doc_list = json.load(fd)
        # select a random sample, max 200, but never more than 10% of collection
        # to prevent someone getting ALL the docs this way
        random_docs = random.sample(doc_list, max(200, len(doc_list)/10))
        return False

    def put_trained_docs(self, post_data):
        """ Upload a zip file whose filename is a transaction_id (uuid)
        and pass the contents to nlp2phenome for training
        """
        filename = os.path.basename(post_data['filename'])
        logging.error('put_trained_docs %s NOT YET IMPLEMENTED' % filename)
        with open(os.path.join(self._training_dir, filename), 'wb') as fd:
            fd.write(post_data['content'])
        # XXX extract zip, run nlp2phenome
        return True

# ---------------------------------------------------------------------
class MongoDocAnn(DocAnn):
    def __init__(self, conf):
        super().__init__()
        self._host = conf['host']
        self._user = conf['user']
        self._pwd = conf['password']
        self._db = conf['db']
        self._auth_source = conf['auth_source']
        self._ann_collection = conf['ann_collection']
        self._text_collection = conf['text_collection']

    @staticmethod
    def format_doc_list_rets(docs):
        if docs is not None and len(docs) > 0:
            return [d['SOPInstanceUID'] for d in docs]
        else:
            return []

    def get_doc_list(self):
        # TODO: to do pagination
        # docs = self.query({}, pagination={'skip': 0, 'limit': 10}, filter={'SOPInstanceUID': 1})
        docs = self.query({}, filter={'SOPInstanceUID': 1})
        return MongoDocAnn.format_doc_list_rets(docs)

    def get_doc_content(self, doc_id):
        # TODO: get the document text content
        return ""

    def raw_doc_ann(self, doc_id):
        q = {"SOPInstanceUID": doc_id}
        rets = self.query(q)
        return None if len(rets) == 0 else rets[0]

    def query(self, q, collection=None, filter=None, pagination=None):
        # Connect to database
        mongo_connection = MongoClient(host=self._host, username=self._user, password=self._pwd,
                                       authSource=self._auth_source)
        mongo_db = mongo_connection[self._db]
        if collection is None:
            collection = mongo_db[self._ann_collection]
        logging.info('querying [%s] ...' % q)
        if pagination is None:
            mongo_cursor = collection.find(q, filter)
        else:
            mongo_cursor = collection.find(q, filter).skip(pagination['skip']).limit(pagination['limit'])
        rets = [d for d in mongo_cursor]
        for d in rets:
            d['_id'] = ''
        logging.info('result set size %s' % len(rets))
        return rets

    def search_anns(self, q, map_name=None):
        import re
        ptn = re.compile('.*%s.*' % q, re.IGNORECASE)
        rets = self.query({"$or": [
            {"annotations.pref": ptn},
            {"annotations.str": ptn}
        ]
        }, filter={'SOPInstanceUID': 1})
        return MongoDocAnn.format_doc_list_rets(rets)

    def search_docs(self, query):
        return query(query)


# ---------------------------------------------------------------------
# Tests

test_pgconf = {
        "host": "localhost", "user":"semehr", "password":"semehr",
        "db":"semehr", "schema":"semehr",
        "ann_collection":"semehr_results",
        "text_collection":"semehr_results"
    }

def test_query_or_cui_to_cui_list():
    p = PostgresDocAnn(test_pgconf)
    assert(p.query_or_cui_to_cui_list(q = "lung") == [])
    assert(p.query_or_cui_to_cui_list(q = "1234567") == [])
    # XXX should check a known snomed maps to a CUI (requires snomed.csv)
    assert(p.query_or_cui_to_cui_list(q = "C123456") == ["C123456"])
    assert(p.query_or_cui_to_cui_list(q = "C123456,C234567") == ["C123456","C234567"])
    assert(p.query_or_cui_to_cui_list(q = ["C123456","C234567"]) == ["C123456","C234567"])
    # XXX also need to test a named mapping

def test_query_to_sql():
    # Test converting query to SQL
    # Sadly this requires an open connection to a database
    # and assumes the "cui_sop" table exists otherwise you get
    # a different query syntax.
    p = PostgresDocAnn(test_pgconf)
    p.open_database()
    sql_exe = p.query_or_cui_list_to_sql(["C123456","C234567"])
    cursor = p._pgConnection.cursor()
    rc = cursor.mogrify(sql_exe).decode()
    expected = " SOPInstanceUID = ANY(ARRAY( SELECT SOPInstanceUID FROM \"cui_sop\" WHERE cui IN ('C123456','C234567')))"
    assert(rc == expected)


# ---------------------------------------------------------------------
if __name__ == '__main__':
    # Test
    logging.basicConfig(level=logging.DEBUG)
    with open('conf/settings.json') as fd: conf = json.load(fd)
    p = PostgresDocAnn(conf['postgreSQL'])
    #  query(q, collection=None, filter=None, pagination=None, queryDict=None)
    query = 'C0205076'
    query = '78904004'
    q = { "terms": [ {"q":query} ],
    #q = { "terms": [ {"q":query}, {"q":query, "negation":"Affirmed"} ],
      #"filter": { "modalities": ["CT","MR"], "start_date":"1999-01-01", "end_date":"2000-10-10" },
      "returnFields": [ "SOPInstanceUID" ]
      }
    r = p.query('', queryDict=q)
    print('query returned %s' % r)
