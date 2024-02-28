# SemEHR library

Sorry, this was not documented by the original author so this information is sparse.

## Anonymisation

The main entrypoint is `do_anonymisation_by_conf()`

```
from SemEHR.anonymiser import do_anonymisation_by_conf
do_anonymisation_by_conf(config)
```

The config can be either a filename to a config file, or it can be a dictionary with the same content.

A template config filename can be found in [anonymisation/conf/anonymisation_task.json](../anonymisation/conf/anonymisation_task.json)

The rules folder is defined as `rules_folder: ./conf/rules/` which is a relative path so you will want to change that to an absolute path.

## Annotation

The main entrypoint is `process_semehr()`

```
from SemEHR.semehr_processor import process_semehr
process_semehr(config)
```

The config can be either a filename to a config file, or it can be a dictionary with the same content.

A template config filename can be found in [data/semehr_settings.json](../data/semehr_settings.json)

The subprocesses change the current working directory so you may want to call it like this:
```
current_dir = os.getcwd()
process_semehr(config)
os.chdir(current_dir)
```

You might want to consider turning off urllib3 warnings with:
```
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
```
