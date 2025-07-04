import joblib as jl
import logging
from os.path import isfile, join, split
import sys
import urllib3
import xml.etree.ElementTree as ET
from SemEHR.ann_post_rules import AnnRuleExecutor
import SemEHR.utils as utils

logger = logging.getLogger(__name__)


class StudyConcept(object):

    def __init__(self, name, terms, umls_instance=None):
        self.terms = terms
        self._name = name
        self._term_to_concept = None
        self._concept_closure = None
        self._umls_instance = umls_instance

    def gen_concept_closure(self, term_concepts=None, concept_to_closure=None):
        raise Exception('not implemented in this version')

    @staticmethod
    def compute_all_concept_closure(all_concepts, umls_instance, skip_relations={}):
        concept_to_closure = {}
        print('all concepts number %s' % len(all_concepts))
        computed = []
        results =[]
        utils.multi_thread_tasking(all_concepts, 40, StudyConcept.do_compute_concept_closure,
                                   args=[umls_instance, computed, results, skip_relations])
        for r in results:
            concept_to_closure[r['concept']] = r['closure']
        return concept_to_closure

    @staticmethod
    def do_compute_concept_closure(concept, umls_instance, computed, results, skip_relations={}):
        if concept not in computed:
            closure = umls_instance.transitive_narrower(concept, skip_relations=skip_relations)
            computed.append(concept)
            results.append({'concept': concept, 'closure': closure})
            print('concept: %s transitive children %s' % (concept, closure))

    @property
    def name(self):
        return self._name

    @property
    def concept_closure(self):
        if self._concept_closure is None:
            self.gen_concept_closure()
        return self._concept_closure

    @concept_closure.setter
    def concept_closure(self, value):
        self._concept_closure = value

    @property
    def term_to_concept(self):
        if self._concept_closure is None:
            self.gen_concept_closure()
        return self._term_to_concept

    @term_to_concept.setter
    def term_to_concept(self, value):
        self._term_to_concept = value


class StudyAnalyzer(object):

    def __init__(self, name):
        self._study_name = name
        self._study_concepts = []
        self._skip_terms = []
        self._options = None

    @property
    def study_name(self):
        return self._study_name

    @study_name.setter
    def study_name(self, value):
        self._study_name = value

    @property
    def study_concepts(self):
        return self._study_concepts

    @study_concepts.setter
    def study_concepts(self, value):
        self._study_concepts = value

    @property
    def skip_terms(self):
        return self._skip_terms

    @skip_terms.setter
    def skip_terms(self, value):
        self._skip_terms = value

    def add_concept(self, concept):
        self.study_concepts.append(concept)

    def generate_exclusive_concepts(self):
        """
        it is important to have a set of disjoint concepts otherwise concept-document frequencies would
        contain double-counted results
        :return:
        """
        # call the concept closure property to make sure
        # that the closure has been generated before
        # compute the disjoint
        for sc in self.study_concepts:
            cc = sc.concept_closure
        intersections = {}
        explain_inter = {}
        for i in range(1, len(self.study_concepts)):
            for j in range(i):
                common = self.study_concepts[i].concept_closure & self.study_concepts[j].concept_closure
                if len(common) > 0:
                    intersections[self.study_concepts[i].name + ' - ' + self.study_concepts[j].name] = common
                    self.study_concepts[j].concept_closure -= common
                    explain_inter[self.study_concepts[j].name] = \
                        ['removed %s common (%s) concepts' % (len(common), self.study_concepts[i].name)] \
                            if self.study_concepts[j].name not in explain_inter \
                            else explain_inter[self.study_concepts[j].name] + \
                                 ['removed %s common (%s) concepts' % (len(common), self.study_concepts[i].name)]
        # if len(intersections) > 0:
        #     print 'intersections [[\n%s\n]]' % json.dumps(explain_inter)
        # for sc in self.study_concepts:
        #     print '%s %s' % (sc.name, len(sc.concept_closure))

    def remove_study_concept_by_name(self, concept_name):
        for sc in self.study_concepts:
            if sc.name == concept_name:
                self.study_concepts.remove(sc)

    def retain_study_concepts(self, concept_names):
        retained = []
        for sc in self.study_concepts:
            if sc.name in concept_names:
                retained.append(sc)
        self.study_concepts = retained

    def export_mapping_in_json(self):
        mapping = {}
        for c in self._study_concepts:
            mapping[c.name] = c.term_to_concept

    def serialise(self, out_file):
        print('iterating concepts to populate the mappings')
        for c in self._study_concepts:
            tc = c.term_to_concept
        print('saving...')
        jl.dump(self, out_file)
        print('serialised to %s' % out_file)

    @property
    def study_options(self):
        return self._options

    @study_options.setter
    def study_options(self, value):
        self._options = value

    @staticmethod
    def deserialise(ser_file):
        return jl.load(ser_file)

    def gen_study_table_with_rules(self, cohort_name, out_file, sample_out_file, ruler, ruled_out_file,
                                   sql_config, db_conn_file, text_preprocessing=False):
        raise Exception('gen_study_table_with_rules not supported')

    def gen_study_table_in_one_iteration(self, cohort_name, out_file, sample_out_file,
                                         sql_config, db_conn_file):
        raise Exception('gen_study_table_in_one_iteration not supported')

    def gen_study_table_with_rules_es(self, cohort_name, out_file, sample_out_file, ruler, ruled_out_file,
                                      sem_idx_setting_file, retained_patients_filter, filter_obj=None):
        raise Exception('gen_study_table_with_rules_es not supported')


def get_sql_template(config_file):
    root = ET.parse(config_file).getroot()
    return {'term_doc_anns_sql': root.find('term_doc_anns_sql').text,
            'patients_sql': root.find('patients_sql').text,
            'skip_term_sql': root.find('skip_term_sql').text}


def get_one_iteration_sql_template(config_file):
    root = ET.parse(config_file).getroot()
    return {'doc_to_brc_sql': root.find('doc_to_brc_sql').text,
            'brc_sql': root.find('brc_sql').text,
            'anns_iter_sql': root.find('anns_iter_sql').text,
            'doc_content_sql': root.find('doc_content_sql').text,
            'skip_term_sql': root.find('skip_term_sql').text}


def load_ruler(rule_setting_file):
    ruler = AnnRuleExecutor()
    if rule_setting_file is None:
        ruler.load_rule_config('./studies/rules/_default_rule_config.json')
    else:
        ruler.load_rule_config(rule_setting_file)
    return ruler


def load_study_settings(folder, umls_instance,
                        rule_setting_file=None,
                        concept_filter_file=None,
                        do_disjoint_computing=True,
                        export_study_concept_only=False):
    p, fn = split(folder)
    if isfile(join(folder, 'study_analyzer.pickle')):
        sa = StudyAnalyzer.deserialise(join(folder, 'study_analyzer.pickle'))
    else:
        sa = StudyAnalyzer(fn)
        if isfile(join(folder, 'label2concept.tsv')):
            # using tsv file if exists
            logger.info('loading study concepts from tsv file...')
            lines = utils.read_text_file(join(folder, 'label2concept.tsv'))
            scs = []
            for l in lines:
                arr = l.split('\t')
                if len(arr) != 2:
                    logger.error('line [%s] not parsable' % l)
                    continue
                t = arr[0]
                c = arr[1]
                sc = StudyConcept(t, [t])
                sc.concept_closure = set([c])
                tc = {}
                tc[t] = {'closure': 1, 'mapped': c}
                sc.term_to_concept = tc
                scs.append(sc)
                logger.debug('study concept [%s]: %s, %s' % (sc.name, sc.term_to_concept, sc.concept_closure))
            sa.study_concepts = scs
            logger.info('study concepts loaded')
        elif isfile(join(folder, 'exact_concepts_mappings.json')):
            concept_mappings = utils.load_json_data(join(folder, 'exact_concepts_mappings.json'))
            concept_to_closure = None
            # concept_to_closure = \
            #     StudyConcept.compute_all_concept_closure([concept_mappings[t] for t in concept_mappings],
            #                                              umls_instance, skip_relations=skip_closure_relations)

            scs = []
            for t in concept_mappings:
                sc = StudyConcept(t, [t])
                t_c = {}
                t_c[t] = [concept_mappings[t]]
                sc.gen_concept_closure(term_concepts=t_c, concept_to_closure=concept_to_closure)
                scs.append(sc)
                logger.debug(sc.concept_closure)
            sa.study_concepts = scs
            sa.serialise(join(folder, 'study_analyzer.pickle'))
        elif isfile(join(folder, 'manual_mapped_concepts.json')):
            mapped_scs = utils.load_json_data(join(folder, 'manual_mapped_concepts.json'))
            scs = []
            for t in mapped_scs:
                sc = StudyConcept(t, [t])
                sc.concept_closure = set(mapped_scs[t]['concepts'])
                tc = {}
                tc[t] = mapped_scs[t]['tc']
                sc.term_to_concept = tc
                scs.append(sc)
                logger.debug('study concept [%s]: %s, %s' % (sc.name, sc.term_to_concept, sc.concept_closure))
            sa.study_concepts = scs
        else:
            concepts = utils.load_json_data(join(folder, 'study_concepts.json'))
            if len(concepts) > 0:
                scs = []
                for name in concepts:
                    scs.append(StudyConcept(name, concepts[name], umls_instance=umls_instance))
                    logger.debug('%s, %s' % (name, concepts[name]))
            sa.study_concepts = scs
            sa.serialise(join(folder, 'study_analyzer.pickle'))

    # get filtered concepts only, if filter exists
    if concept_filter_file is not None:
        logger.debug('before removal, the concept length is: %s' % len(sa.study_concepts))
        concept_names = utils.load_json_data(concept_filter_file)
        sa.retain_study_concepts(concept_names)
        logger.debug('after removal: %s' % len(sa.study_concepts))

    # compute disjoint concepts
    if do_disjoint_computing:
        sa.generate_exclusive_concepts()

    if export_study_concept_only:
        sc2closure = {}
        for sc in sa.study_concepts:
            sc2closure[sc.name] = list(sc.concept_closure)
        utils.save_json_array(sc2closure, join(folder, 'sc2closure.json'))
        logger.debug('sc2closure.json generated in %s' % folder)

    if isfile(join(folder, 'study_options.json')):
        sa.study_options = utils.load_json_data(join(folder, 'study_options.json'))
    merged_mappings = {}
    study_concept_list = []
    for c in sa.study_concepts:
        for t in c.term_to_concept:
            all_concepts = list(c.concept_closure)
            study_concept_list += all_concepts
            if len(all_concepts) > 1:
                idx = 0
                for cid in all_concepts:
                    merged_mappings['(%s) %s (%s)' % (c.name, t, idx)] = {'closure': len(all_concepts), 'mapped': cid}
                    idx += 1
            else:
                merged_mappings['(%s) %s' % (c.name, t)] = c.term_to_concept[t]
        # print c.name, c.term_to_concept, c.concept_closure
        # print json.dumps(list(c.concept_closure))
    # logger.debug('print merged mappings...')
    # print json.dumps(merged_mappings)
    # logger.debug(len(study_concept_list))
    utils.save_string('\n'.join(study_concept_list), join(folder, 'all_concepts.txt'))

    if export_study_concept_only:
        return

    # sa.gen_study_table(cohort_name, join(folder, 'result.csv'))
    # sa.gen_sample_docs(cohort_name, join(folder, 'sample_docs.json'))
    ruler = load_ruler(rule_setting_file)
    if len(ruler.skip_terms) > 0:
        sa.skip_terms = ruler.skip_terms
    return {'study_analyzer': sa, 'ruler': ruler}


def study(folder, cohort_name, sql_config_file, db_conn_file, umls_instance,
          do_one_iter=False, do_preprocessing=False,
          rule_setting_file=None, sem_idx_setting_file=None,
          concept_filter_file=None,
          retained_patients_filter=None,
          filter_obj_setting=None,
          do_disjoint_computing=True,
          export_study_concept_only=False,
          skip_closure_relations={}):
    ret = load_study_settings(folder, umls_instance,
                              rule_setting_file=rule_setting_file,
                              concept_filter_file=concept_filter_file,
                              do_disjoint_computing=do_disjoint_computing,
                              export_study_concept_only=export_study_concept_only)
    sa = ret['study_analyzer']
    ruler = ret['ruler']
    if do_one_iter:
        sa.gen_study_table_in_one_iteration(cohort_name, join(folder, 'result.csv'), join(folder, 'sample_docs.json'),
                                            sql_config_file, db_conn_file)
    else:
        if sem_idx_setting_file is None:
            sa.gen_study_table_with_rules(cohort_name, join(folder, 'result.csv'), join(folder, 'sample_docs.js'), ruler,
                                          join(folder, 'ruled_anns.json'), sql_config_file, db_conn_file,
                                          text_preprocessing=do_preprocessing)
        else:
            filter_obj = None
            if filter_obj_setting is not None:
                filter_obj = utils.load_json_data(filter_obj_setting)
            sa.gen_study_table_with_rules_es(cohort_name, join(folder, 'result.csv'), join(folder, 'sample_docs.js'),
                                             ruler,
                                             join(folder, 'ruled_anns.json'),
                                             sem_idx_setting_file,
                                             retained_patients_filter,
                                             filter_obj=filter_obj)
    logger.info('done')


def run_study(folder_path, no_sql_filter=None):
    study_config = 'study.json' if no_sql_filter is None else 'study_no_filter.json'
    if isfile(join(folder_path, study_config)):
        r = utils.load_json_data(join(folder_path, study_config))
        retained_patients = None
        if 'query_patients_file' in r:
            retained_patients = []
            lines = utils.read_text_file(r['query_patients_file'])
            for l in lines:
                arr = l.split('\t')
                retained_patients.append(arr[0])
        skip_closure_relations = {}
        if 'skip_closure_relations' in r:
            skip_closure_relations = utils.load_json_data(r['skip_closure_relations'])
        study(folder_path, r['cohort'], r['sql_config'], r['db_conn'],
              None,
              do_preprocessing=r['do_preprocessing'],
              rule_setting_file=r['rule_setting_file'],
              do_one_iter=r['do_one_iter'],
              sem_idx_setting_file=None if 'sem_idx_setting_file' not in r else r['sem_idx_setting_file'],
              concept_filter_file=None if 'concept_filter_file' not in r else r['concept_filter_file'],
              retained_patients_filter=retained_patients,
              filter_obj_setting=None if 'filter_obj_setting' not in r else r['filter_obj_setting'],
              do_disjoint_computing=True if 'do_disjoint' not in r else r['do_disjoint'],
              export_study_concept_only=False if 'export_study_concept' not in r else r['export_study_concept'],
              skip_closure_relations=skip_closure_relations
              )
    else:
        logger.error('study.json not found in the folder')


if __name__ == "__main__":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    if 2 < len(sys.argv) > 3:
        print('the syntax is [python study_analyzer.py STUDY_DIR [-no-sql-filter]]')
    else:
        run_study(sys.argv[1], no_sql_filter=None if len(sys.argv) == 2 else 'yes')
