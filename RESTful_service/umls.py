#!/usr/bin/env python3

import argparse
import csv
import json
import logging
import os
import psycopg2
from psycopg2 import sql
import sys

# ==> cui.csv <==
# cui|tui|tuigroup|cuilabel
# ==> rel.csv <==
# cui1|has|cui2
# ==> snomed.csv <==
# snomed|cui
# ==> sty.csv <==
# tui|tuigroup|tuigrouplabel

class UMLSmap:
    """ contains mappings from the UMLS Metathesaurus for
    relationships and concept ids
    """
    # Class static members (so we only load the databases once)
    _cui_tui = {}       # cui.csv
    _cui_tuigroup = {}  # cui.csv
    _cui_label = {}     # cui.csv
    _cui_narrower = {}  # rel.csv
    _snomed_to_cui = {} # snomed.csv
    _tui_to_group = {}  # sty.csv
    _tui_to_label = {}  # sty.csv


    def __init__(self, settings = None, csv_dir = None):
        """ Construct a UMLS mapping object.
        The settings parameter is required to configure postgres and
        the location of the CSV files. It should be a dict, being the
        whole settings file or just the postgreSQL part.
        A connection to postgres is opened, and the CSV files are loaded
        (except some may not be loaded if load_into_memory is False).
        If csv_dir and not settings then only CSV files are loaded.
        """
        self._load_into_memory = True
        self._csv_dir = csv_dir
        self._narrower_rc = set()
        if isinstance(settings, dict):
            # You can pass in the whole settings dict or just the postgreSQL part
            if 'postgreSQL' in settings:
                settings = settings['postgreSQL']
            self._csv_dir = settings.get('umls_csv_dir', self._csv_dir)
            self._host = settings['host']
            self._user = settings['user']
            self._pwd = settings['password']
            self._db = settings['db']
            self._schema = 'umls'
            self._pgConnection = None
            self._pgCursor = None
            self._load_into_memory = False
            self.open_postgres()
        if self._csv_dir:
            self.load_csvs()

    def open_postgres(self):
        """ Open a connection to postgres and keep the connection open.
        Connection parameters must already have been set in the constructor.
        """
        try:
            self._pgConnection = psycopg2.connect(host=self._host, user=self._user, password=self._pwd, dbname=self._db)
        except:
            logging.warning("cannot connect to postgresql, will try using local CSV files instead")
            logging.warning(sys.exc_info()[1]) # error message
            self._load_into_memory = True
            return
        self._pgCursor = self._pgConnection.cursor()
        # Set the schema name so it doesn't need to be specified before each table name
        self._pgCursor.execute(sql.SQL("SET search_path TO {},public").format(sql.Identifier(self._schema)))
        self._pgConnection.commit()

    def load_csvs(self):
        """ Load all the CSV files into memory,
        except only load the cui table if 'load_into_memory' is set
        because it is very large / slow / crashes
        """
        if self._load_into_memory:
            self.load_cui()
        self.load_rel()
        self.load_snomed()
        self.load_sty()

    def load_cui(self):
        """ Load the cui.csv file into memory.
        cui|tui|tuigroup|cuilabel
        """
        logging.debug('Loading cui.csv')
        with open(os.path.join(self._csv_dir, 'cui.csv')) as fd:
            rdr = csv.reader(fd, delimiter='|')
            n = 0
            for row in rdr:
                n += 1
                print('%d \r' % n, end='')
                # cui|tui|tuigroup|cuilabel
                UMLSmap._cui_tui[row[0]] = row[1].split(',')
                UMLSmap._cui_tuigroup[row[0]] = row[2].split(',')
                UMLSmap._cui_label[row[0]] = row[3]

    def load_rel(self):
        """ Load the rel.csv file into memory.
        This contains the relationships (narrower concepts).
        cui1|has|cui2
        """
        logging.debug('Loading rel.csv')
        with open(os.path.join(self._csv_dir, 'rel.csv')) as fd:
            rdr = csv.reader(fd, delimiter='|')
            for row in rdr:
                # cui1|has|cui2
                if row[1] != 'RN':
                    continue
                UMLSmap._cui_narrower[row[0]] = row[2].split(',')
            logging.debug('Loaded %d relationships' % len(UMLSmap._cui_narrower))
            logging.debug('C0205076 narrower -> %s' % UMLSmap._cui_narrower['C0205076'])

    def load_snomed(self):
        """ Load the snomed.csv file into memory.
        This maps from SNOMED into CUI.
        snomed|cui
        """
        logging.debug('Loading snomed.csv')
        UMLSmap._snomed_to_cui = {}
        with open(os.path.join(self._csv_dir, 'snomed.csv')) as fd:
            rdr = csv.reader(fd, delimiter='|')
            for row in rdr:
                # snomed|cui
                UMLSmap._snomed_to_cui[row[0]] = row[1]

    def load_sty(self):
        """ Load the sty.csv file into memory.
        This maps from a concept type into a type group.
        Probably not needed since type groups are in cui.csv
        tui|tuigroup|tuigrouplabel
        """
        logging.debug('Loading sty.csv')
        with open(os.path.join(self._csv_dir, 'sty.csv')) as fd:
            rdr = csv.reader(fd, delimiter='|')
            for row in rdr:
                # tui|tuigroup|tuigrouplabel
                UMLSmap._tui_to_group[row[0]] = row[1]
                UMLSmap._tui_to_label[row[0]] = row[2]


#    def test(self, cui, depth=0, prefix=''):
#        """ Recursively descend from a given cui,
#        displaying the full path to all children,
#        eg. Chest Wall / Rib cage / Thoracic cavity structure / Mediastinum / Heart / Heart disease / Angina pectoris / Coronary artery spasm
#        eg. Chest Wall / Rib cage / Thoracic cavity structure / Mediastinum / Heart / Heart disease / Other heart disease / Cardiovascular disease / Cerebrovascular disease / Head injury /  / Open wound of eyeball / Ocular laceration with prolapse AND/OR exposure of intraocular tissue / [X]Ocular laceration and rupture with prolapse or loss of intraocular tissue /
#        C2114768 =  / C0222762 Rib cage / C0230139 Thoracic cavity structure / C0025066 Mediastinum/ C0018787 Heart/ C0018799 Heart disease/ C0178273 Other heart disease/ C0007222 Cardiovascular disease/ C0007820 Cerebrovascular disease/ C0018674 Headinjury/ C0160536  / C0160474 Open wound ofeyeball/ C0015409 Penetrating injury of eye/ C0160468 Ocular laceration with prolapse AND/OR exposure of intraocular tissue / C3536765 [X]Ocular laceration and rupture with prolapse or loss of intraocular tissue / C0271101 Prolapse of iris/ C2114768
#        """
#        if depth == 0:
#            self._mrrel_rc = set()
#        self._mrrel_rc.update([cui])
#        children = self._mrrel_dict.get(cui,[])
#        for child in children:
#            if child in self._mrrel_rc:
#                continue
#            cui_str = prefix +' / ' +child +' ' +'#'.join(self.MRCONSO_CUI_to_str(child))
#            print('%s%s = %s' % (' '*depth, child, cui_str))
#            self.test(child, depth+1, cui_str)

    def list_intersection(self, list1, list2):
        """ Return a new list which is the intersection of list1 and list2
        """
        assert(isinstance(list1, list))
        assert(isinstance(list2, list))
        return [x for x in list1 if x in list2]

    def cui_narrower(self, cui, depth=0, maxdepth=999, filter_to_same_tui=False, prunelist=[]):
        """
        Return a list of CUIs which are narrower concepts.
        depth - for internal use, counting how deep we are in recursion
        maxdepth - 0 returns the cui, 1 returns its children, and so on
        filter_to_same-tui - only returns CUIs from the same Samantic Type Group
        prunelist - a list of CUI which should not be descended or returned
        XXX prunelist can remove unwanted CUIs but we need to do the opposite,
        only keep CUIs which are known to be used in the annotation DB.
        """
        if maxdepth == 0:
            return [cui]
        if depth == 0:
            self._narrower_rc = set()
            self._narrower_rc.update([cui]) # added myself first
            self._narrower_tui_list = self.cui_to_tui_list(cui)
            #logging.debug('List of concept types for %s = %s' % (cui, self._narrower_tui_list))
        if depth >= maxdepth:
            return
        children = UMLSmap._cui_narrower.get(cui, [])
        #print('%s%s children: %s' % (' '*depth, cui, children))
        useful_children = [child for child in children if 
            child not in self._narrower_rc and
            child not in prunelist and
            (not filter_to_same_tui or
            (filter_to_same_tui and self.list_intersection(self._narrower_tui_list, self.cui_to_tui_list(child))))]
        self._narrower_rc.update(useful_children)
        for child in useful_children:
            self.cui_narrower(child, depth+1, maxdepth=maxdepth, filter_to_same_tui=filter_to_same_tui, prunelist=prunelist)
        if depth == 0:
            return list(self._narrower_rc)

    def snomed_to_cui(self, snomed):
        """ Map from a SNOMED code into a CUI.
        Assumes the table has been loaded into memory (does not use the database).
        """
        return UMLSmap._snomed_to_cui.get(snomed, None)

    def cui_to_tui_list(self, cui):
        if self._load_into_memory:
            return UMLSmap._cui_tuigroup.get(cui, [])
        sql_exe = sql.SQL('SELECT tui FROM cui WHERE cui = {cui}').format(cui = sql.Literal(cui))
        self._pgCursor.execute(sql_exe)
        ff = self._pgCursor.fetchall()
        self._pgConnection.commit()
        return ff[0][0].split(',') # [first row][first element of tuple (first column)] string split into list

    def cui_to_label(self, cui):
        if self._load_into_memory:
            return UMLSmap._cui_label.get(cui, '')
        sql_exe = sql.SQL('SELECT cuilabel FROM cui WHERE cui = {cui}').format(cui = sql.Literal(cui))
        #logging.debug('execute SQL %s' % self._pgCursor.mogrify(sql_exe).decode())
        self._pgCursor.execute(sql_exe)
        ff = self._pgCursor.fetchall()
        self._pgConnection.commit()
        return ff[0][0] # [first row][first element of tuple (first column)]




if __name__ == '__main__':
    """ This test program can display the number of narrower concepts
    Use --cfg to specify path to settings.json where postgresql params are,
    or to a dummy file if you don't want to use postgresql.
    Use --csvs to specify path to directory containing CSV files.
    Options are:
    --snomed or --cui is the query concept identifier.
    --depth is how far down tree to go, try 0, 1, 2, 999.
    --same_tui will restrict the search to concepts which are of the same 'type' or group
    eg. if your concept is ANATOMY it will ignore FINDING.
    """
    logging.basicConfig(level = logging.DEBUG)
    parser = argparse.ArgumentParser(description='UMLS Test')
    parser.add_argument('--cfg', dest='cfg', action="store", help='Config file %(default)s', default='conf/settings.json')
    parser.add_argument('--cui', dest='cui', action="store", help="Test CUI code %(default)s", default="C0205076")
    parser.add_argument('--snomed', dest='snomed', action="store", help="Test SNOMED code %(default)s", default="78904004")
    parser.add_argument('--csvs', dest='csv_dir', action="store", help="Directory of UMLS CSV files %(default)s", default="../umls")
    parser.add_argument('--depth', dest='depth', action="store", help="Max depth %(default)s", default=999)
    parser.add_argument('--same_tui', dest='same_tui', action="store_true", help="Filter to same concept type group default %(default)s", default=False)
    args = parser.parse_args()

    sett = None
    if os.path.isfile(args.cfg):
        with open('conf/settings.json') as fd:
            sett = json.load(fd)

    mapper = UMLSmap(settings = sett, csv_dir = args.csv_dir)

    if args.cui:
        cui = args.cui
    if args.snomed:
        cui = mapper.snomed_to_cui(args.snomed)

    c = mapper.cui_narrower(cui, maxdepth=args.depth, filter_to_same_tui=args.same_tui)
    print('%s = %d entries' % (cui, len(c)))

    c = mapper.cui_narrower(cui, maxdepth=args.depth, filter_to_same_tui=False)
    print('%s       any TUI = %d entries' % (cui, len(c)))
    c = mapper.cui_narrower(cui, maxdepth=args.depth, filter_to_same_tui=True)
    print('%s only same TUI = %d entries' % (cui, len(c)))
    for maxdepth in [2,1,0]:
        c1 = mapper.cui_narrower(cui, maxdepth=maxdepth, filter_to_same_tui=False)
        c2 = mapper.cui_narrower(cui, maxdepth=maxdepth, filter_to_same_tui=True)
        print('%s depth %d = %d, filter to same tui = %d' % (cui, maxdepth, len(c1), len(c2)))
    #print('First few: %s' % c[0:9])
    #for i in list(c):
    #    print('%s = %s' % (i, m.cui_to_label(i)))
