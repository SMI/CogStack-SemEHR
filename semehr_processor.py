import sys
import urllib3
from SemEHR.semehr_processor import process_semehr

if __name__ == "__main__":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    if len(sys.argv) != 2:
        print('the syntax is [python semehr_processor.py PROCESS_SETTINGS_FILE_PATH]')
    else:
        process_semehr(sys.argv[1])
