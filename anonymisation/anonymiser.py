import sys, os

cdir = os.path.dirname(os.path.realpath(__file__))
pdir = os.path.dirname(cdir)
sys.path.append(pdir)

import logging
from rule_extractor import ExtractRule
import anony_ann_converter as ac
import re
import utils
from os.path import isfile, join
from os import listdir
# import urllib3


def is_valid_place_holder(s):
    return len(s) >= 2


def retain_text_sections(text, sects, sent_fields):
    """
    Split the text into sections, where
      sects is an array like ["Finding", "Text", "ContentSequence"]
      sent_fields is an array like ["Patient ID", "Patient Name"]
      text is a document like this:
      [[Patient ID]]12345
      [[Patient Name]]Thomas MacThomas
      [[Text]]
      The patient Thomas was examined.
    Returns a tuple of two items (a, b) where
      a = [ ('Text', 'The patient ...') ]
      b = { 'Patient Name': 'Thomas MacThomas', ... }
    """
    ptn = re.compile(r'\[\[([^\]]+)\]\]')
    matches = re.finditer(ptn, text)
    sec_texts = []
    prev_field = None
    prev_pos = 0
    sents = {}
    for m in matches:
        if prev_field is not None:
            if prev_field in sent_fields:
                txt = text[prev_pos:m.span()[0]].strip()
                if txt:
                    sents[prev_field] = txt
            if prev_field in sects:
                sec_texts.append((prev_field, text[prev_pos:m.span()[0]]))
        prev_pos = m.span()[0] + len(m.group(0))
        prev_field = m.group(1)
    if prev_field in sects:
        sec_texts.append((prev_field, text[prev_pos:]))
    if prev_field in sent_fields:
        txt = text[prev_pos:].strip()
        if txt:
            sents[prev_field] = txt
    return sec_texts, sents


def anonymise_doc(doc_id, text, failed_docs, anonymis_inst, sent_container, rule_group):
    """
    anonymise a document
    :param doc_id:
    :param text:
    :param failed_docs:
    :param anonymis_inst: anonymise_rule instance
    :return:
    """
    # rets = do_letter_parsing(text)
    rets = anonymis_inst.do_full_text_parsing(text, rule_group=rule_group)
    if rets[1] < 0 or rets[2] < 0:
        failed_docs.append(doc_id)
        logging.info('````````````` %s failed' % doc_id)
        return None, None
    else:
        sen_data = rets[0]
        # print 'sentdata : [%s]' % sen_data
        anonymised_text = text
        for d in sen_data:
            if 'SKIPDOC' in d['attrs']:
                anonymised_text = 'TOTALLY_IGNORED_CONTENT'
                sen_data = []
                break
            if 'name' in d['attrs']:
                logging.debug('removing %s [%s] ' % (d['attrs']['name'], d['type']))
                start = d['pos'][0] + d['attrs']['full_match'].find(d['attrs']['name'])
                if is_valid_place_holder(d['attrs']['name']):
                    anonymised_text = ExtractRule.do_replace(anonymised_text, start, d['attrs']['name'])
                    # 'x' * len(d['attrs']['name']))
                sent_container.append({'doc': doc_id, 'pos':d['pos'][0], 'start':start, 'type': d['type'], 'sent': d['attrs']['name']})
            if 'number' in d['attrs']:
                logging.debug('removing %s ' % d['attrs']['number'])
                if is_valid_place_holder(d['attrs']['number']):
                    anonymised_text = ExtractRule.do_replace(anonymised_text, d['pos'][0], d['attrs']['number'])
                sent_container.append({'doc': doc_id, 'pos':d['pos'][0], 'start': d['pos'][0], 'type': d['type'], 'sent': d['attrs']['number']})
        if use_spacy:
            spacy_doc = spacy_nlp(anonymised_text)
            for ent in spacy_doc.ents:
                if ent.label_ == "PERSON":
                    sent_container.append({'doc': doc_id, 'pos':ent.start_char, 'start': ent.start_char, 'type': 'PERSON', 'sent': ent.text})
        return anonymised_text, sen_data


def wrap_anonymise_doc_by_file(fn, folder, rule_group, anonymised_folder, failed_docs, anonymis_inst, sent_container,
                               fields, sensitive_fields, do_ann=False):
    text = utils.read_text_file_as_string(join(folder, fn))

    f_t_tuples, sents = retain_text_sections(text, fields, sensitive_fields)
    s = ''
    for t in f_t_tuples:
        s += '[[%s]]\n%s' % (t[0], t[1])
    if len(s) == 0:
        s = text
        # let's do nothing if no text fields were found
        return
    s = s.replace('\r', ' ')
    s2repls = []
    for f in sents:
        s2repls.append(sents[f].strip())
        arr = [v for v in sents[f].strip().split(' ') if len(v) > 3]
        s2repls += arr

    cur_sent_container = []
    anonymised_text, sen_data = anonymise_doc(fn, s, failed_docs, anonymis_inst, cur_sent_container, rule_group)
    sent_container += cur_sent_container

    for sd in cur_sent_container:
        if len(sd['sent']) > 3:
            s2repls.append(sd['sent'])
    for v in s2repls:
            ptn = re.compile(re.escape(v), re.IGNORECASE)
            matches = re.finditer(ptn, anonymised_text)
            for m in matches:
                sent_container.append({'doc': fn, 'pos': m.span()[0], 'start': m.span()[0], 'sent': m.group(0), 'type': "PHI-replace"})

    # save eHost ann
    if do_ann:
        # XXX I have introduced a bug here, the XML just accumulates records after each file... (was: cur_sent_container,fn)
        ehost_data = ac.AnnConverter.anonymisation_to_eHost(sent_container, fn)
        utils.save_string(s, join(anonymised_folder, fn))
        utils.save_string(ehost_data, join(anonymised_folder, '%s.knowtator.xml' % fn))
    else:
        for v in s2repls:
            ptn = re.compile(re.escape(v), re.IGNORECASE)
            anonymised_text = ptn.sub('Q' * len(v), anonymised_text)
        utils.save_string(anonymised_text, join(anonymised_folder, fn))
    logging.info('%s anonymised' % fn)


def anonymise_files_in_folder_mt(input_folder, anonymised_folder, rule_file, sent_data_file, sent_data_output,
                                 rule_group, working_fields, sensitive_fields, annotation_mode=False,
                                 num_threads=0):
    fns = [f for f in listdir(input_folder) if isfile(join(input_folder, f))]
    anonymis_inst = ExtractRule(rule_file)
    failed_docs = []
    sent_data = []
    if num_threads > 0:
        utils.multi_thread_tasking(fns, num_threads, wrap_anonymise_doc_by_file,
                                   args=[input_folder, rule_group, anonymised_folder, failed_docs,
                                         anonymis_inst, sent_data,
                                         working_fields, sensitive_fields, annotation_mode
                                         ])
    else:
        for fn in fns:
            wrap_anonymise_doc_by_file(fn, # num_threads, wrap_anonymise_doc_by_file,
                                       input_folder, rule_group, anonymised_folder, failed_docs,
                                       anonymis_inst, sent_data,
                                       fields=working_fields, sensitive_fields=sensitive_fields, do_ann=annotation_mode)
    utils.save_json_array(sent_data, sent_data_file)
    t2sent = {}
    for s in sent_data:
        if s['type'] not in t2sent:
            t2sent[s['type']] = []
        t2sent[s['type']].append('\t'.join([s['doc'], str(s['pos']), s['sent']]))
    s = ''
    for t in t2sent:
        t2sent[t] = list(set(t2sent[t]))
        s += '%s\n======\n%s\n\n' % (t, '\n'.join(t2sent[t]))
    utils.save_string(s, sent_data_output)


def parse_imaging_reports(text):
    """
    parse SMI imaging report structure
    """
    ptn = re.compile(r'\[\[([^\]]+)\]\]')
    matches = re.finditer(ptn, text)
    f2v = {}
    prev_field = None
    prev_pos = 0
    for m in matches:
        if prev_field is not None:
            f2v[prev_field] = text[prev_pos:m.span()[0]]
        prev_pos = m.span()[0] + len(m.group(0))
        prev_field = m.group(1)
    f2v[prev_field]=text[prev_pos]
    # print('XXX parse_imaging_reports returning %s' % f2v)
    return f2v


def dir_anonymisation(folder, rule_files, rule_group):
    anonymis_inst = ExtractRule(rule_files)
    onlyfiles = [f for f in listdir(folder) if isfile(join(folder, f))]
    container = []
    sent_data = []
    for f in onlyfiles:
        text = utils.read_text_file_as_string(join(folder, f))
        logging.info(anonymise_doc(f, text, container, anonymis_inst, sent_data, rule_group=rule_group))


def do_anonymisation_by_conf(conf_file):
    global use_spacy, spacy_nlp
    setttings = utils.load_json_data(conf_file)
    text_foler = setttings['text_data_path']
    rules_folder = setttings['rules_folder']
    rule_group = setttings['rule_group_name']
    working_fileds = setttings['working_fields']
    sensitive_fields = setttings['sensitive_fields']
    annotation_mode = setttings['annotation_mode'] if 'annotation_mode' in setttings else False
    number_threads = setttings['number_threads'] if 'number_threads' in setttings else 0
    rule_files = [join(rules_folder, f) for f in listdir(rules_folder) if isfile(join(rules_folder, f))
                  and re.match(setttings['rule_file_pattern'], f)]
    use_spacy = setttings.get('use_spacy', False)
    if use_spacy:
        import spacy
        spacy_nlp = spacy.load(setttings.get('spacy_model', 'en_core_web_sm'))


    # logging setup
    log_level = setttings['logging_level'] if 'logging_level' in setttings else 'INFO'
    log_format = setttings['logging_format'] if 'logging_format' in setttings \
        else '%(name)s %(asctime)s %(levelname)s %(message)s'
    logging.basicConfig(level=log_level, format=log_format)
    log_file = None if 'logging_file' not in setttings else setttings['logging_file']
    if log_file is not None:
        formatter = logging.Formatter(log_format)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler)
        logging.info('logging to %s' % log_file)

    if setttings['mode'] == 'dir':
        dir_anonymisation(text_foler, rule_files, rule_group=rule_group)
    else:
        anonymised_folder = setttings['anonymisation_output']
        removed_output = setttings['extracted_phi']
        sensitive_output = setttings['grouped_phi_output']
        anonymise_files_in_folder_mt(text_foler, anonymised_folder, rule_files, removed_output,
                                     sensitive_output, rule_group=rule_group,
                                     working_fields=working_fileds, sensitive_fields=sensitive_fields,
                                     annotation_mode=annotation_mode,
                                     num_threads=number_threads)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('the syntax is [python anonymiser.py CONF_SETTINGS_FILE_PATH]')
    else:
        do_anonymisation_by_conf(sys.argv[1])
