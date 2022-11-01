#!/usr/bin/env python3
# Simple program to call the anonymiser in the current directory with a
# document consisting of the string passed on the command line.
#
# Usage: test_anon.py [-v] "document text to be anonymised"
# Usage: test_anon.py [-v] filename.txt
# Usage: test_anon.py  (uses built-in sample text)

import json
import os
import sys
import tempfile

verbose = False

def anon_file(filename):
    with open(filename) as fd:
        doc = fd.read()
        return anon_doc(doc)

def anon_doc(doc):
    with tempfile.TemporaryDirectory() as tmpdirname:
        os.mkdir(tmpdirname + "/out")
        cfg = {
          "mode": "mt",
          "number_threads": 0,
          "rules_folder": "./conf/rules/",
          "rule_file_pattern": ".*_rules.json$",
          "rule_group_name": "PHI_rules",
          "working_fields": ["Finding", "Text", "ContentSequence"],
          "sensitive_fields": ["Patient ID", "Patient Name", "Person Observer Name", "Referring Physician Name"],
          "annotation_mode": False,
          "text_data_path": tmpdirname,
          "anonymisation_output": tmpdirname + "/out",
          "extracted_phi": tmpdirname + "/out/extracted_phi.json",
          "grouped_phi_output": tmpdirname + "/out/grouped_phi.txt",
          "logging_level": "DEBUG",
          "logging_file": tmpdirname + "/anonymisation.log"
        }
        # Prefix text with a field from "working_fields" otherwise it's ignored
        if not '[[' in doc:
            doc = "[[ContentSequence]]\n" + doc
        # Save the document text to a file
        with open(tmpdirname + "/doc.txt", 'w') as txt_fd:
            print(doc, file=txt_fd)
        # Create a config file
        with open(tmpdirname + "/cfg", 'w') as cfg_fd:
            print(json.dumps(cfg), file=cfg_fd)
        # This will output DEBUG statements saying what has been redacted:
        print('RUNNING ANONYMISER')
        os.system("python3 ./anonymiser.py %s" % tmpdirname + "/cfg")
        # Now show the phi json too
        with open("%s/out/extracted_phi.json" % tmpdirname) as phi_fd:
            phi = json.load(phi_fd)
            for item in phi:
                if verbose:
                    print('REDACT "%s"' % item['sent'])
        #os.system("find %s -ls" % tmpdirname)
        #os.system("cat %s/out/doc.txt" % tmpdirname)
        #os.system("cat %s/out/grouped_phi.txt" % tmpdirname)
        #os.system("cat %s/out/extracted_phi.json" % tmpdirname)
        with open('%s/out/doc.txt' % tmpdirname) as fd:
            ret = fd.read()
        return ret, phi

def unescape_str(doc):
    # Convert any escape sequences so if you type "hi\nthere" as an argument
    # it is converted to two lines with a newline character between so
    # you can simulate a multiple line report.
    return doc.encode('ascii', 'ignore').decode('unicode_escape')


if __name__ == '__main__':
    if len(sys.argv)>1:
        doc = sys.argv[1]
        if doc == '-v':
            doc = sys.argv[1]
            verbose = True
        if os.path.isfile(doc):
            anon_doc, anon_phi = anon_file(doc)
        else:
            anon_doc, anon_phi = anon_doc(unescape_str(doc))
        print('ANONYMISED DOCUMENT:')
        print(anon_doc)
    else:
        # This tests postcode(!) as 6th is mistaken for the end of a postcode and it thinks the whole thing is an address
        doc = "....Semi-urgent (<1 month) outpatient MRI head \\T\\ orbits please. Complete left 6th cranial nerve palsy/lateral rectus restriction since 20th February - no improvement. Initially pain around left eye but now comfortable. No disc swelling. Diabetic with history of polyneuropathy, and previous left 3rd nerve palsy 2006 (recovered). ?Structural cause for 6th nerve palsy.\n"
        doc += "<BR>Radiology Report (Booking No. 31065412), Raigmore Hospital, Inverness\n\n\n<BR>2004429060               Exam Date 21/10/2016\n\n\n<BR>Angry Nelly (10/04/1952 Male)\n\n\n<BR>58 BLANTYREE RD  LOCHDUBH  INVERNESS    IV2 1BS\n\n\n<BR>Referred by  Dell, Michael (Cons A&E)\n\n\n<BR>Raigmore A&E  Raigmore Hospital  Old Perth Road  Inverness  IV2 3UJ\n"
        doc += "<BR>CHI NUMBER: 12345  Examination Number: 23456  Examination Date: 12 June 2002\n"
        doc += "<BR>GMC 34567\n"
        doc += "<BR>0131 937 2450\n"
        doc += "<BR>Another 10-digit number: 1357924680\n"
        doc += "<BR>Address: Geriatric Ward, Aisla, Ayr\n"
        doc += "Radiographers: Looky Person\n"
        expected_phi = [
            '2006', '31065412', ' Raigmore Hospital, Inverness',
            '21/10/2016', 'Angry Nelly', '10/04/1952',
            '<BR>58 BLANTYREE RD  LOCHDUBH  INVERNESS    IV2 1BS',
            'Dell, Michael',
            '<BR>Raigmore A&E  Raigmore Hospital  Old Perth Road  Inverness  IV2 3UJ',
            '12345', '12 June 2002',
            '34567',
            '0131 937 2450',
            '1357924680',
            'Geriatric Ward, Aisla, Ayr',
            'Looky Person'
        ]
        anon_doc, anon_phi = anon_doc(unescape_str(doc))
        print('ANONYMISED DOCUMENT:')
        print(anon_doc)
        redacted_words = [phi['sent'] for phi in anon_phi]
        for phi in expected_phi:
            if phi not in redacted_words:
                print('ERROR: did not redact %s' % phi)
