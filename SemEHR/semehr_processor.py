from datetime import datetime
import datetime
import logging
from os.path import isfile, join
from os import listdir
import os
import sys
import urllib3
import xml.etree.ElementTree as ET
from subprocess import Popen, STDOUT
import SemEHR.utils as utils
import SemEHR.docanalysis as docanalysis


logger = logging.getLogger(__name__)


class ProcessSetting(object):
    def __init__(self, setting_file):
        if isinstance(setting_file, str):
            self.__conf = None
            self.__file = setting_file
            self.load_data()
        elif isinstance(setting_file, dict):
            self.__conf = setting_file
        else:
            raise TypeError('ProcessSetting must be given a str (filename) or dict (settings)')

    def load_data(self):
        self.__conf = utils.load_json_data(self.__file)

    def get_attr(self, attr_path):
        dict_obj = self.__conf
        for e in attr_path:
            if e in dict_obj:
                dict_obj = dict_obj[e]
            else:
                return None
        return dict_obj


class JobStatus(object):
    """
    A JobStatus class for continuous processing on an incremental fashion
    e.g., doing updates every morning
    """
    STATUS_SUCCESS = 0
    STATUS_FAILURE = -1
    STATUS_WORKING = 1
    STATUS_UNKNOWN = -2

    def __init__(self, job_file, dfmt='%Y-%m-%d %H:%M:%S'):
        self._dfmt = dfmt
        self._end_time_point = None
        self._start_time_point = None
        self._last_status = JobStatus.STATUS_FAILURE
        self._job_file = job_file
        self.load_data()

    def load_data(self):
        if isfile(self._job_file):
            d = utils.load_json_data(self._job_file)
            self._end_time_point = d['end_time_point']
            self._start_time_point = d['start_time_point']
            self._last_status = d['last_status']
        else:
            self._end_time_point = datetime.datetime.now().strftime(self._dfmt)
            self._start_time_point = datetime.date(2000, 1, 1).strftime(self._dfmt)
            self._last_status = JobStatus.STATUS_UNKNOWN

    def save(self):
        utils.save_json_array(self.get_ser_data(), self._job_file)

    def get_ser_data(self):
        return {'last_status': self._last_status,
                'start_time_point': self._start_time_point,
                'end_time_point': self._end_time_point}

    def set_status(self, is_success):
        self._last_status = JobStatus.STATUS_SUCCESS if is_success else JobStatus.STATUS_FAILURE

    def job_start(self, dt=None):
        if self._last_status == JobStatus.STATUS_SUCCESS:
            self._start_time_point = self._end_time_point
            if dt is None:
                dt = datetime.datetime.now().strftime(self._dfmt)
            self._end_time_point = dt
        self._last_status = JobStatus.STATUS_WORKING
        return self.get_ser_data()


def set_sys_env(settings):
    """
    set bash command environment
    :param settings:
    :return:
    """
    envs = settings.get_attr(['env'])
    for env in envs:
        os.environ[env.upper()] = envs[env]
    ukb_home = settings.get_attr(['env', 'ukb_home'])
    if ukb_home is not None and len(ukb_home) > 0 and ukb_home not in os.environ['PATH']:
        os.environ['PATH'] += ':' + ukb_home + '/bin'
    gate_home = settings.get_attr(['env', 'gate_home'])
    if gate_home is not None and len(gate_home) > 0 and gate_home not in os.environ['PATH']:
        os.environ['PATH'] += ':' + gate_home + '/bin'
    gcp_home = settings.get_attr(['env', 'gcp_home'])
    if gcp_home is not None and len(gcp_home) > 0 and gcp_home not in os.environ['PATH']:
        os.environ['PATH'] += ':' + gcp_home


def produce_yodie_config(settings, data_rows, docid_path):
    """
    generate bio-yodie configuration xml file
    :param settings: the config instance
    :param data_rows: data arrays
    :param docid_path: the file path to save docids
    :return: number of docs to be processed
    """
    batch = ET.Element("batch")
    task_id = settings.get_attr(['job', 'job_id'])
    batch.set('id', 'semehr-%s' % task_id)
    batch.set('xmlns', "http://gate.ac.uk/ns/cloud/batch/1.0")

    application = ET.SubElement(batch, "application")
    application.set('file', '%s/bio-yodie-1-2-1/main-bio/main-bio.xgapp' % settings.get_attr(['env', 'yodie_path']))

    report = ET.SubElement(batch, "report")
    report_file = '%s/%s.xml' % (settings.get_attr(['env', 'yodie_path']), task_id)
    report.set('file', report_file)
    if settings.get_attr(['yodie', 'retain_report']) != 'yes':
        if os.path.isfile(report_file):
            os.unlink(report_file)

    input = ET.SubElement(batch, "input")
    input.set('encoding', 'UTF-8')
    num_docs = len(data_rows)
    if settings.get_attr(['yodie', 'input_source']) == "sql":
        input.set('class', 'kcl.iop.brc.core.kconnect.crisfeeder.CRISDocInputHandler')
        input.set('dbSettingImportant', 'true')
        input_db = utils.load_json_data(settings.get_attr(['yodie', 'input_dbconn_setting_file']))
        input.set('db_url', input_db['db_url'])
        input.set('db_driver', input_db['db_driver'])
        input.set('user', input_db['user'])
        input.set('password', input_db['password'])
        input.set('get_doc_sql_prefix', input_db['get_doc_sql_prefix'])
        logger.info('using docs from sql server [%s]' % settings.get_attr(['yodie', 'input_dbconn_setting_file']))
    elif settings.get_attr(['yodie', 'input_source']) == "files":
        dir_path = settings.get_attr(['yodie', 'input_doc_file_path'])
        num_docs = len([f for f in listdir(dir_path) if isfile(join(dir_path, f))])
        input.set('class', 'gate.cloud.io.file.FileInputHandler')
        input.set('dir', dir_path)
        documents = ET.SubElement(batch, "documents")
        documentEnumerator = ET.SubElement(documents, "documentEnumerator")
        documentEnumerator.set('class', 'gate.cloud.io.file.FileDocumentEnumerator')
        documentEnumerator.set('dir', settings.get_attr(['yodie', 'input_doc_file_path']))
        logger.info('using docs from folder [%s]' % dir_path)
    else:
        input.set('class', 'kcl.iop.brc.core.kconnect.crisfeeder.ESDocInputHandler')
        input.set('es_doc_url', '%s/%s/%s' % (
            settings.get_attr(['semehr', 'es_doc_url']), settings.get_attr(['semehr', 'full_text_index']),
            settings.get_attr(['semehr', 'full_text_doc_type'])))
        input.set('main_text_field', '%s' % settings.get_attr(['semehr', 'full_text_text_field']))
        input.set('doc_guid_field', '%s' % settings.get_attr(['semehr', 'full_text_doc_id']))
        input.set('doc_created_date_field', '%s' % settings.get_attr(['semehr', 'full_text_doc_date']))
        logger.info('using docs from elasticsearch [%s]' % settings.get_attr(['semehr', 'full_text_index']))

    output = ET.SubElement(batch, "output")
    if settings.get_attr(['yodie', 'output_destination']) == "sql":
        output.set('dbSettingImportant', 'true')
        output.set('class', 'kcl.iop.brc.core.kconnect.outputhandler.SQLOutputHandler')
        output_db = utils.load_json_data(settings.get_attr(['yodie', 'output_dbconn_setting_file']))
        output.set('db_url', output_db['db_url'])
        output.set('db_driver', output_db['db_driver'])
        output.set('user', output_db['user'])
        output.set('password', output_db['password'])
        output.set('output_table', '%s' % settings.get_attr(['yodie', 'output_table']))
        if settings.get_attr(['yodie', 'annotationOutputSettings']) is not None:
            output.set('annotationOutputSettings', settings.get_attr(['yodie', 'annotationOutputSettings']))
        if settings.get_attr(['yodie', 'docBasedOutput']) is not None:
            output.set('docBasedOutput', settings.get_attr(['yodie', 'docBasedOutput']))
        if settings.get_attr(['yodie', 'docAnnSQLTemplate']) is not None:
            output.set('docAnnSQLTemplate', settings.get_attr(['yodie', 'docAnnSQLTemplate']))
        if settings.get_attr(['yodie', 'singleAnnSQLTemplate']) is not None:
            output.set('singleAnnSQLTemplate', settings.get_attr(['yodie', 'singleAnnSQLTemplate']))
        if settings.get_attr(['yodie', 'output_concept_filter_file']) is not None:
            output.set('concept_filter', '%s' % settings.get_attr(['yodie', 'output_concept_filter_file']))
        logger.info('saving annotations to sql [%s]' % settings.get_attr(['yodie', 'output_dbconn_setting_file']))
    else:
        output.set('class', 'kcl.iop.brc.core.kconnect.outputhandler.YodieOutputHandler')
        output.set('output_folder', '%s' % settings.get_attr(['yodie', 'output_file_path']))
        output.set('file_based', '%s' % settings.get_attr(['yodie', 'use_file_based']))
        logger.info('saving annotations to folder [%s]' % settings.get_attr(['yodie', 'output_file_path']))

    if settings.get_attr(['yodie', 'input_source']) != "files":
        logger.info('doing yodie with %s documents, saved to %s...' %
                     (str(len(data_rows)), docid_path))
        if len(data_rows) > 0:
            # save doc ids to text file for input to bioyodie
            logger.info('saving doc ids to [%s]' % docid_path)
            utils.save_string('\n'.join([str(r['docid']) for r in data_rows]), docid_path)
        elif os.path.exists(docid_path):
            num_docs = len(utils.read_text_file(docid_path))
        documents = ET.SubElement(batch, "documents")
        documentEnumerator = ET.SubElement(documents, "documentEnumerator")
        documentEnumerator.set('class', 'kcl.iop.brc.core.kconnect.crisfeeder.PlainTextEnumerator')
        documentEnumerator.set('doc_id_file', '%s/%s_docids.txt' % (
            settings.get_attr(['yodie', 'input_doc_file_path']), settings.get_attr(['job', 'job_id'])))

    tree = ET.ElementTree(batch)
    tree.write("%s" % settings.get_attr(['yodie', 'config_xml_path']), xml_declaration=True)
    return num_docs


def clear_folder(folder):
    """
    remove all files within a folder
    :param folder:
    :return:
    """
    if not os.path.exists(folder):
        return
    for the_file in os.listdir(folder):
        file_path = os.path.join(folder, the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(e)


def do_semehr_doc_anns_analysis(settings):
    anns_folder = settings.get_attr(['doc_ann_analysis', 'ann_docs_path'])
    text_folder = settings.get_attr(['doc_ann_analysis', 'full_text_folder'])
    full_text_file_pattern = settings.get_attr(['doc_ann_analysis', 'full_text_fn_ptn'])
    rule_config = settings.get_attr(['doc_ann_analysis', 'rule_config_path'])
    output_folder = settings.get_attr(['doc_ann_analysis', 'output_folder'])
    study_folder = settings.get_attr(['doc_ann_analysis', 'study_folder'])
    combined_anns = settings.get_attr(['doc_ann_analysis', 'combined_anns'])
    es_output_index = settings.get_attr(['doc_ann_analysis', 'es_output_index'])
    es_output_doc = settings.get_attr(['doc_ann_analysis', 'es_output_doc'])
    output_file_pattern = settings.get_attr(['doc_ann_analysis', 'output_fn_pattern'])
    thread_num = settings.get_attr(['doc_ann_analysis', 'thread_num'])
    if thread_num is None:
        thread_num = 10
    process_mode = settings.get_attr(['doc_ann_analysis', 'process_mode'])
    if process_mode is not None and process_mode != 'sql':
        if settings.get_attr(['doc_ann_analysis', 'es_host']) is not None:
            raise Exception('using elasticsearch in this version is not supported')
        else:
            docanalysis.process_doc_anns(anns_folder=anns_folder,
                                         full_text_folder=text_folder,
                                         rule_config_file=rule_config,
                                         output_folder=output_folder,
                                         study_folder=study_folder,
                                         full_text_fn_ptn=full_text_file_pattern,
                                         fn_pattern=output_file_pattern,
                                         thread_num=thread_num
                                         )
    else:
        ann_list_sql = settings.get_attr(['doc_ann_analysis', 'ann_list_sql'])
        primary_keys = settings.get_attr(['doc_ann_analysis', 'primary_keys'])
        ann_inst_sql = settings.get_attr(['doc_ann_analysis', 'ann_inst_sql'])
        full_text_sql = settings.get_attr(['doc_ann_analysis', 'full_text_sql'])
        update_query_template = settings.get_attr(['doc_ann_analysis', 'update_query_template'])
        update_status_template = settings.get_attr(['doc_ann_analysis', 'update_status_template'])
        dbconn_file = settings.get_attr(['doc_ann_analysis', 'dbconn_file'])
        docanalysis.analyse_db_doc_anns(ann_list_sql, ann_inst_sql, primary_keys, update_query_template,
                                        full_text_sql, dbconn_file,
                                        thread_num=thread_num,
                                        study_folder=study_folder,
                                        rule_config_file=rule_config,
                                        update_status_template=update_status_template
                                        )


def populate_cohort_results(settings):
    cohort_sql = settings.get_attr(['populate_cohort_result', 'cohort_sql'])
    doc_ann_sql_temp = settings.get_attr(['populate_cohort_result', 'doc_ann_sql_temp'])
    doc_ann_pks = settings.get_attr(['populate_cohort_result', 'doc_ann_pks'])
    dbcnn_file = settings.get_attr(['populate_cohort_result', 'dbconn_file'])
    study_folder = settings.get_attr(['populate_cohort_result', 'study_folder'])
    output_folder = settings.get_attr(['populate_cohort_result', 'output_folder'])
    sample_sql_temp = settings.get_attr(['populate_cohort_result', 'sample_sql_temp'])
    thread_num = settings.get_attr(['populate_cohort_result', 'thread_num'])
    sampling = settings.get_attr(['populate_cohort_result', 'sampling'])
    sample_size = None
    if sampling is None:
        sampling = True
    if sampling:
        sample_size = settings.get_attr(['populate_cohort_result', 'sample_size'])
    if sample_size is None:
        sample_size = 20
    docanalysis.db_populate_study_results(cohort_sql, doc_ann_sql_temp, doc_ann_pks, dbcnn_file,
                                          study_folder, output_folder, sample_sql_temp,
                                          thread_num=thread_num, sampling=sampling,
                                          sample_size=sample_size)


def collect_cohort_doc_results(settings, doc2pid):
    processed_ann_path = settings.get_attr(['cohort_doc_collection', 'se_result_path'])
    ann_doc_pattern = settings.get_attr(['cohort_doc_collection', 'ann_doc_pattern'])
    semantic_types = settings.get_attr(['cohort_doc_collection', 'semantic_types'])
    result_file_path = settings.get_attr(['cohort_doc_collection', 'result_file_path'])
    graph_file_path = settings.get_attr(['cohort_doc_collection', 'graph_file_path'])
    dc = docanalysis.DocCohort(doc2pid, processed_ann_path, doc_id_pattern=ann_doc_pattern)
    dc.collect_semantic_types = semantic_types
    dc.collect_result(result_file_path, graph_file_path)


def do_patient_indexing(pid, es, doc_level_index, doc_ann_type,
                        doc_index, doc_type, doc_pid_field_name, doc_text_field_name,
                        patient_index, patient_doct_type,
                        ann_field_name, ignore_exist=False):
    if ignore_exist:
        if es.get_doc_detail(pid) is not None:
            return
    es.index_patient(doc_level_index, pid, doc_ann_type,
                     doc_index, doc_type, doc_pid_field_name, doc_text_field_name,
                     patient_index, patient_doct_type,
                     ann_field_name=ann_field_name)


def process_semehr(config_file):
    """
    a pipeline to process all SemEHR related processes:
    0. ES doc copy from one index to another;
    1. bio-yodie NLP pipeline annotation on docs;
    2. entity centric SemEHR ES indexing
    :param config_file:
    :return:
    """
    # read the configuration
    ps = ProcessSetting(config_file)

    # setting log configuration
    log_level = 'INFO' if ps.get_attr(['logging', 'level']) is None else ps.get_attr(['logging', 'level'])
    log_format = '%(name)s %(asctime)s %(levelname)s %(message)s' if ps.get_attr(['logging', 'format']) is None \
        else ps.get_attr(['logging', 'format'])
    log_file = None if ps.get_attr(['logging', 'file']) is None else ps.get_attr(['logging', 'file'])
    if log_file is not None:
        logging.basicConfig(level=log_level, format=log_format)
        formatter = logging.Formatter(log_format)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler)
        logging.info('logging to %s' % log_file)

    # initialise the jobstatus class instance
    job_file = join(ps.get_attr(['job', 'job_status_file_path']),
                    'semehr_job_status_%s.json' % ps.get_attr(['job', 'job_id']))
    logger.info('[SemEHR-step] using job status file %s' % job_file)
    job_status = JobStatus(job_file)
    job_status.job_start()

    # preload: load documents to es
    if ps.get_attr(['job', 'epr_index']) == 'yes':
        raise Exception('epr_index not supported by this version')

    data_rows = []
    doc2pid = {}
    pids = []
    if ps.get_attr(['job', 'load_docs']) == 'yes':
        raise Exception('load_docs not supported')
    elif ps.get_attr(['job', 'cohort_docs']) == 'yes':
        raise Exception('cohort_docs not supported in this version')

    try:
    # if True:
        # 0. copy docs
        if ps.get_attr(['job', 'copy_docs']) == 'yes':
            raise Exception('copy_docs not supported in this version')

        if ps.get_attr(['job', 'yodie']) == 'yes':
            docid_path = '%s/%s_docids.txt' % (
                ps.get_attr(['yodie', 'input_doc_file_path']), ps.get_attr(['job', 'job_id']))
            logger.info('[SemEHR-step] doing yodie')
            # 1. do bio-yodie pipeline
            # 1.1 prepare the configuration file
            num_docs = produce_yodie_config(ps, data_rows, docid_path)
            if num_docs == 0:
                logger.info('[SemEHR-step-end] nothing to process, NLP step done')
            else:
                logger.info('total number of docs %s' % num_docs)
                # 1.2 set the env variables
                set_sys_env(ps)
                # 1.3 clear ann output folder
                logger.info('clearing %s ...' % ps.get_attr(['yodie', 'output_file_path']))
                clear_folder(ps.get_attr(['yodie', 'output_file_path']))
                # 1.3 run bio-yodie
                os.chdir(ps.get_attr(['yodie', 'gcp_run_path']))
                if ps.get_attr(['yodie', 'os']) == 'win':
                    cmd = ' '.join(['java',
                                    "-Dgate.home=%s" % ps.get_attr(['env', 'gate_home']),
                                    "-Dgcp.home=%s" % ps.get_attr(['env', 'gcp_home']),
                                    "-Djava.protocol.handler.pkgs=gate.cloud.util.protocols",
                                    "-cp .;{SCRIPTDIR}/conf;{SCRIPTDIR}/gcp.jar;{SCRIPTDIR}/lib/*;"
                                    "{GATE_HOME}/bin/gate.jar;{GATE_HOME}/lib/*".format(
                                        **{"SCRIPTDIR":ps.get_attr(['env', 'gcp_home']),
                                           "GATE_HOME":ps.get_attr(['env', 'gate_home'])}),
                                    '-Dat.ofai.gate.modularpipelines.configFile="%s/bio-yodie-1-2-1/main-bio/main-bio.config.yaml" '
                                    % ps.get_attr(['env', 'yodie_path']),
                                    "-Xmx%s" % ps.get_attr(['yodie', 'memory']),
                                    "gate.cloud.batch.BatchRunner",
                                    "-t %s" % ps.get_attr(['yodie', 'thread_num']),
                                    "-b %s" % ps.get_attr(['yodie', 'config_xml_path'])
                                    ])
                else:
                    cmd = ' '.join(['gcp-direct.sh',
                                    "-t %s" % ps.get_attr(['yodie', 'thread_num']),
                                    "-Xmx%s" % ps.get_attr(['yodie', 'memory']),
                                    "-b %s" % ps.get_attr(['yodie', 'config_xml_path']),
                                    '-Dat.ofai.gate.modularpipelines.configFile="%s/bio-yodie-1-2-1/main-bio/main-bio.config.yaml" '
                                    % ps.get_attr(['env', 'yodie_path']),
                                    ])
                logger.debug('executing the following command to start NLP...')
                logger.info(cmd)
                p = Popen(cmd, shell=True, stderr=STDOUT)
                p.wait()

                if 0 != p.returncode:
                    job_status.set_status(False)
                    job_status.save()
                    logger.error('ERROR doing the NLP, stopped with a coide [%s]' % p.returncode)
                    exit(p.returncode)
                else:
                    logger.info('[SemEHR-step-end] NLP step done')
                semehr_path = None
                if 'semehr_path' in os.environ:
                    logger.info('changing back to semehr_path: %s' % os.environ['semehr_path'])
                    semehr_path = os.environ['semehr_path']
                else:
                    semehr_path = ps.get_attr(['env', 'semehr_path'])
                if semehr_path is not None:
                    os.chdir(semehr_path)

        # 2. do SemEHR concept/entity indexing
        if ps.get_attr(['job', 'semehr-concept']) == 'yes' or ps.get_attr(['job', 'semehr-patients']) == 'yes':
            raise Exception('semehr-concept indexing not supported by this version')

        # 3. do SemEHR actionable transparency
        if ps.get_attr(['job', 'action_trans']) == 'yes':
            raise Exception('action_trans not supported by this version')

        # 4. do SemEHR document annotation analysis (post processing)
        if ps.get_attr(['job', 'doc_analysis']) == 'yes':
            logger.info('[SemEHR-step] doing SemEHR annotation analysis...')
            do_semehr_doc_anns_analysis(settings=ps)
            logger.info('[SemEHR-step-end] doc_analysis step done')

        # 4.5 do SemEHR patient level index
        if ps.get_attr(['job', 'patient_index']) == 'yes':
            raise Exception('action_trans not supported by this version')

        # 5. do populate results for a research study
        if ps.get_attr(['job', 'populate_cohort_result']) == 'yes':
            logger.info('[SemEHR-step] doing SemEHR cohort result extraction...')
            populate_cohort_results(settings=ps)
            logger.info('[SemEHR-step-end] populate_cohort_result step done')

        # 6. do collect cohort doc based results for a research study
        if ps.get_attr(['job', 'cohort_doc_collection']) == 'yes':
            logger.info('[SemEHR-step] doing SemEHR cohort doc based collection...')
            collect_cohort_doc_results(settings=ps, doc2pid=doc2pid)
            logger.info('[SemEHR-step-end] collect_cohort_doc_results step done')

        job_status.set_status(True)
        job_status.save()
        logger.info('[SemEHR-process-end] all done')
    except Exception as e:
        logger.error('[SemEHR-process-ERROR] Failed to do SemEHR process %s' % str(e))
        job_status.set_status(False)
        job_status.save()


if __name__ == "__main__":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    if len(sys.argv) != 2:
        print('the syntax is [python semehr_processor.py PROCESS_SETTINGS_FILE_PATH]')
    else:
        process_semehr(sys.argv[1])


