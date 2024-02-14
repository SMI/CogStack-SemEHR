import sys, os
from SemEHR.anonymiser import do_anonymisation_by_conf

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('the syntax is [python anonymiser.py CONF_SETTINGS_FILE_PATH]')
    else:
        do_anonymisation_by_conf(sys.argv[1])
