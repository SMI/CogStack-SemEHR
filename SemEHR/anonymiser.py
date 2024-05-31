import logging
import os
from os.path import isfile, join
from os import listdir
import re
import sys
from SemEHR.rule_extractor import ExtractRule
from SemEHR.anony_ann_converter import AnnConverter
import SemEHR.utils as utils


logger = logging.getLogger(__name__)


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
                    if prev_field in sents:
                        # If a [[tag]] appears multiple times then append after a space
                        sents[prev_field] = sents[prev_field] + ' ' + txt
                    else:
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
            if prev_field in sents:
                # If a [[tag]] appears multiple times then append after a space
                sents[prev_field] = sents[prev_field] + ' ' + txt
            else:
                sents[prev_field] = txt
    return sec_texts, sents


def anonymise_doc(doc_id, text, failed_docs, anonymis_inst, sent_container, rule_group):
    """
    anonymise a document
    :param doc_id: name of document, used as 'doc' key in sent_container output
    :param text:   the input text
    :param failed_docs:  returns a list of doc_id which failed to anonymise
    :param anonymis_inst: anonymise_rule instance
    :param sent_container: returns list [{doc, pos, start, type, sent}, ...]
    :param rule_group: passed to the anonymis_inst method do_full_text_parsing
    :return: sent_container updated, returns tuple (anonymised text, sen_data)
    WARNINGS:
    the anonymised text returned is not fully anonymised as there are
    additional entries in sent_container that were not redacted.
    """
    # rets = do_letter_parsing(text)
    rets = anonymis_inst.do_full_text_parsing(text, rule_group=rule_group)
    if rets[1] < 0 or rets[2] < 0:
        # in practice this can never occur, see rule_extractor.py
        failed_docs.append(doc_id)
        logger.error('failed to anonymise %s' % doc_id)
        return None, None

    sen_data = rets[0]
    # print 'sentdata : [%s]' % sen_data
    anonymised_text = text
    for d in sen_data:
        if 'SKIPDOC' in d['attrs']:
            anonymised_text = 'TOTALLY_IGNORED_CONTENT'
            sen_data = []
            break
        if 'name' in d['attrs']:
            logger.debug('removing %s [%s] [%s]' % (d['attrs']['name'], d['type'], d['rule']))
            start = d['attrs']['name_start']
            if is_valid_place_holder(d['attrs']['name']):
                anonymised_text = ExtractRule.do_replace(anonymised_text, start, d['attrs']['name'])
                # 'x' * len(d['attrs']['name']))
            sent_container.append({'doc': doc_id, 'pos':d['pos'][0], 'start':start, 'type': d['type'], 'sent': d['attrs']['name'], 'rule': d['rule']})
        if 'number' in d['attrs']:
            logger.debug('removing %s ' % d['attrs']['number'])
            # XXX should we change 'start' in the same way as for 'name' above?
            if is_valid_place_holder(d['attrs']['number']):
                anonymised_text = ExtractRule.do_replace(anonymised_text, d['pos'][0], d['attrs']['number'])
            sent_container.append({'doc': doc_id, 'pos':d['pos'][0], 'start': d['pos'][0], 'type': d['type'], 'sent': d['attrs']['number'], 'rule':d['rule']})
    if use_spacy:
        spacy_doc = spacy_nlp(anonymised_text)
        for ent in spacy_doc.ents:
            if ent.label_ == "PERSON":
                sent_container.append({'doc': doc_id, 'pos':ent.start_char, 'start': ent.start_char, 'type': 'PERSON', 'sent': ent.text, 'rule': 'spacy'})
                # XXX what about updating anonymised_text, sen_data here?
    return anonymised_text, sen_data


def wrap_anonymise_doc_by_file(fn, folder, rule_group, anonymised_folder, failed_docs, anonymis_inst, sent_container,
                               fields, sensitive_fields, do_ann=False):
    text = utils.read_text_file_as_string(join(folder, fn))

    f_t_tuples, sents = retain_text_sections(text, fields, sensitive_fields)
    s = ''
    for t in f_t_tuples:
        s += '[[%s]]\n%s' % (t[0], t[1])
    if len(s) == 0:
        # No text fields found, continue but write empty output and xml
        pass
        #s = text
        # let's do nothing if no text fields were found
        # XXX make this an option
        #return
    s = s.replace('\r', ' ')
    # Collect all sensitive phrases, and
    # split into sensitive words for words >= 4 chars long
    # s2repls will contain an array of regex looking for names, and
    # each will be surrounded by \b to ensure not found in middle of words.
    s2repls = []
    for f in sents:
        s2repls.append(sents[f].strip())
        # Split into words and keep each word that is 4 or more characters.
        # Surround with '\b' to ensure each is a unique word (don't find 'a' within a word!)
        arr = ['\\b' +v +'\\b' for v in sents[f].strip().split(' ') if len(v) > 3]
        s2repls += arr

    # Update sent_container with entities found in the document using rules
    cur_sent_container = []
    anonymised_text, sen_data = anonymise_doc(fn, s, failed_docs, anonymis_inst, cur_sent_container, rule_group)
    sent_container += cur_sent_container

    # Add the new entities to the list of regex in s2repls
    # presumably so that anything found via a rule will also be
    # found again anywhere else??
    # XXX Not sure this is wise...
    for sd in cur_sent_container:
        if len(sd['sent']) > 3:
            s2repls.append(sd['sent'])

    # Look for all sensitive phrases/words in anonymised_text
    # and append to sent_container
    for v in s2repls:
            ptn = re.compile(re.escape(v), re.IGNORECASE)
            matches = re.finditer(ptn, anonymised_text)
            for m in matches:
                sent_container.append({'doc': fn, 'pos': m.span()[0], 'start': m.span()[0], 'sent': m.group(0), 'type': "PHI-replace"})

    # save eHost ann
    if do_ann:
        # SMI not used
        # XXX I have introduced a bug here, the XML just accumulates records after each file... (was: cur_sent_container,fn)
        ehost_data = AnnConverter.anonymisation_to_eHost(sent_container, fn)
        utils.save_string(s, join(anonymised_folder, fn))
        utils.save_string(ehost_data, join(anonymised_folder, '%s.knowtator.xml' % fn))
    else:
        # SMI used
        for v in s2repls:
            ptn = re.compile(re.escape(v), re.IGNORECASE)
            anonymised_text = ptn.sub('Q' * len(v), anonymised_text)
        utils.save_string(anonymised_text, join(anonymised_folder, fn))
    logger.info('%s anonymised' % fn)


def anonymise_files_in_folder_mt(input_folder, anonymised_folder, rule_file, sent_data_file, sent_data_output,
                                 rule_group, working_fields, sensitive_fields, annotation_mode=False,
                                 num_threads=0):
    fns = [f for f in listdir(input_folder) if isfile(join(input_folder, f))]
    anonymis_inst = ExtractRule(rule_file)
    failed_docs = []
    sent_data = []
    if num_threads > 0:
        # SMI configuration does not use threads
        utils.multi_thread_tasking(fns, num_threads, wrap_anonymise_doc_by_file,
                                   args=[input_folder, rule_group, anonymised_folder, failed_docs,
                                         anonymis_inst, sent_data,
                                         working_fields, sensitive_fields, annotation_mode
                                         ])
    else:
        # SMI configuration:
        for fn in fns:
            wrap_anonymise_doc_by_file(fn, # num_threads, wrap_anonymise_doc_by_file,
                                       input_folder, rule_group, anonymised_folder, failed_docs,
                                       anonymis_inst, sent_data,
                                       fields=working_fields, sensitive_fields=sensitive_fields, do_ann=annotation_mode)
    utils.save_json_array(sent_data, sent_data_file)
    # Make a list of all the 'type' attributes and their doc,pos,sent values
    # e.g. t2sent['name'] = [ 'doc \t posN \t sent', ... ]
    t2sent = {}
    for s in sent_data:
        if s['type'] not in t2sent:
            t2sent[s['type']] = []
        t2sent[s['type']].append('\t'.join([s['doc'], str(s['pos']), s['sent']]))
    # Make sure there's no duplicates within each list
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
        logger.info(anonymise_doc(f, text, container, anonymis_inst, sent_data, rule_group=rule_group))


def do_anonymisation_by_conf(conf_file):
    global use_spacy, spacy_nlp
    if isinstance(conf_file, str):
        setttings = utils.load_json_data(conf_file)
    elif isinstance(conf_file, dict):
        setttings = conf_file
    else:
        raise TypeError('expected a dict or a str')
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
    log_file = None if 'logging_file' not in setttings else setttings['logging_file']
    if log_file is not None:
        logging.basicConfig(level=log_level, format=log_format)
        formatter = logging.Formatter(log_format)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler)
        logging.info('logging to %s' % log_file)

    if setttings['mode'] == 'dir':
        # SMI configuration does not use 'dir'
        dir_anonymisation(text_foler, rule_files, rule_group=rule_group)
    else:
        # SMI configuration uses 'mt'
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
        print('Usage: %s python anonymiser.py CONF_SETTINGS_FILE_PATH' % sys.argv[0], file=sys.stderr)
    else:
        do_anonymisation_by_conf(sys.argv[1])
