#!/usr/bin/env python3
# Usage: rule_test.py TEXT
# will look through all the rules in the rules/conf/*.json directory
# and report which rules match the given TEXT.
# eg. if TEXT is 01312223333 it reports: MATCH phone using ^\s{0,}(\d[\d\s]+)\Z
# ./test_rules.py 'found to be ok. Dr. Shine Light, Consultant Radiologist, HCPC CS12345 GMC 12345. Reported By: MargeRise Mactoff, physicist. Reported by Miss Marge Rise Mactoff, NMC'
# You can also pass TEXT like a document you'd get from CTP_DicomToText,
# eg. "[[Patient Name]]Me\n[[ContentSequence]]Hello and how are you.\n<BR>0131 5372450\nGoodbye\n"
# If you don't give any text then some sample text is used,
# and it reports if all the expected PII was found using the rules.

import json
import glob
import re2 as re
import sys

sample_text = "Patient found to be ok. Dr. Shine Light, Consultant Radiologist, HCPC CS12345 GMC: 12345. Reported By: MargeRise Mactoff, physicist. Reported by Miss Marge Rise Mactoff, NMC. Dr Ra'Ed Al-Gebra\nDr O'Connor\nEntered by John O'Rio\nDictating Radiologist / Clinical Specialist   Kava-Muto, Lucy (Loc Rad)\n"
sample_PII = {
    "Dr. Shine Light" : 0,
    "HCPC CS12345" : 0,
    "GMC: 12345" : 0,
    "Reported By: MargeRise Mactoff, physicist." : 0,
    "Reported by Miss Marge Rise Mactoff" : 0,
    "Dr Ra'Ed Al-Gebra" : 0,
    "Dr O'Connor" : 0,
    "Entered by John O'Rio" : 0,
    "Specialist   Kava-Muto, Lucy" : 0
}

if len(sys.argv)>1:
    text = sys.argv[1]
else:
    text = sample_text
verbose = 0

# Copied from conf/anonymisation_task.json
# Only used if the input text contains a [[]] field.
working_fields = ["Finding", "Text", "ContentSequence"]
sensitive_fields = ["Patient ID", "Patient Name", "Person Observer Name", "Referring Physician Name"]

# Copied directory from anonymiser.py
# Only used if the input text contains a [[]] field.
def retain_text_sections(text, sects, sent_fields):
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

# Convert any escape sequences so if you type "hi\nthere" as an argument
# it is converted to two lines with a newline character between so
# you can simulate a multiple line report.
text = text.encode('ascii', 'ignore').decode('unicode_escape')

if '[[' in text:
    text_tuples, sensitive_dict = retain_text_sections(text, working_fields, sensitive_fields)
    # XXX only using the first element of the returned array
    # (the [1] takes the tuple 'value' of that element given (key,value))
    text = text_tuples[0][1]

for file in glob.glob('conf/rules/*.json'):
    if verbose: print('%s' % file)
    with open(file) as fd:
        rule_dict = json.load(fd)
        for rule_set in rule_dict:
            if verbose: print(' %s' % rule_set)
            for rule_cat in rule_dict[rule_set]:
                if verbose: print('  %s' % rule_cat)
                for rule in rule_dict[rule_set][rule_cat]:
                    if verbose: print('   %s [%s]' % (rule['data_type'], rule['pattern']))
                    flags = 0
                    if 'multiline' in rule['flags']: flags |= re.MULTILINE
                    if 'ignorecase' in rule['flags']: flags |= re.IGNORECASE
                    if rule.get('disabled', False):
                        continue
                    p = re.compile(rule['pattern'], flags)
                    # Check that the number of groups matches the labels array
                    # Note on nested groups, eg. ((x)y) matches xy with group1=xy group2=x
                    # so you might have less labels than match groups as first label captures more.
                    if p.groups != len(rule['data_labels']):
                        err = 'WARN' if p.groups > len(rule['data_labels']) else 'ERROR'
                        print('%s %d labels (%s) but %d groups in %s' % (err, len(rule['data_labels']), ','.join(rule['data_labels']), p.groups, rule['pattern']))
                    # Test all matches
                    for match in p.finditer(text):
                        if text == sample_text:
                            if match.group(0) in sample_PII:
                                sample_PII[match.group(0)] += 1
                            if verbose: print('MATCH "%s" AS "%s" USING "%s"' % (match.group(0), rule['data_type'], rule['pattern']))
                        else:
                            print('MATCH "%s" AS "%s" USING "%s"' % (match.group(0), rule['data_type'], rule['pattern']))
if text == sample_text:
    all_found = True
    for pii in sample_PII:
        if sample_PII[pii] < 1:
            print("Expected to find PII but didn't : %s" % pii)
            all_found = False
    if all_found:
        print('All expected PII was found OK')
