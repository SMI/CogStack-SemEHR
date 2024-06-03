# SemEHR Anonymiser

This code will anonymise text files and produce two outputs:
* the redacted text file
* a metadata file describing which PII elements were found, with their position in the document.

The metadata output can be in JSON format or XML format.
SMI uses the XML format for two reasons, it is more comprehensive
and it can be used as input to the eHOST program for manual
annotation and correction. This is essential for training and
verification.

# Installation

This version no longer requires Python2, it works in Python3.

The python regular expression parser `re` cannot handle some of the
regular expressions in the anonymisation rules, especially on some of
the larger documents, so it tries to use Google's replacement, called `re2`.
You need to `apt install libre2-dev` first, then `pip install pyre2`.
If re2 is not installed it will silently fallback to normal re but this may hang
on the complex patterns. Note: do not `pip install re2`, it doesn't work.
There is also `google-re2` but this is untested.

# Configuration

The template configuration file in conf/anonymisation_task.json
can be copied and modified.

```
{
  "mode": "mt",
  "number_threads": 0,
  "rules_folder": "./conf/rules/",
  "rule_file_pattern": ".*_rules.json",
  "rule_group_name": "PHI_rules",
  "working_fields": ["Finding", "Text", "ContentSequence"],
  "sensitive_fields": ["Patient ID", "Patient Name", "Person Observer Name", "Referring Physician Name"],
  "annotation_mode": false,
  "text_data_path": "./test_data",
  "anonymisation_output": "./test_output/",
  "extracted_phi": "./test_output/extracted_phi.json",
  "grouped_phi_output": "./test_output/grouped_phi.txt",
  "logging_level": "DEBUG",
  "logging_file": "./test_output/anonymisation.log"
}
```

The `mode` can be `mt` or `dir` but we use `mt` only.
There is no requirement for using multiple threads.
The `annotation_mode` determines whether it writes json output or
knowtator.xml output. We use the latter so set it to `true`.

The `working_fields` and `sensitive_fields` relate to the input
file format, described below.

The `phi` options relate to the metadata output.

There is an additional `use_spacy` which defaults to False but if
set to True and spacy is installed then it uses spaCy to anonymise
as well. The language model is currently hard-coded `en_core_web_sm`.
It only anonymises `PERSON` entities but has the disadvantage that
it may also remove the names of drugs.

The rules used to anonymise text are stored in the `rules_folder` directory.
All files matching the `rule_file_pattern` will be loaded.

The rule file format is like this:
```
{
  "PHI_rules": {
    "clinic": [
      {
        "comment": "A full description of this rule in plain English.",
        "test_true": [ "list of strings which the pattern must match", "more" ],
        "test_false": [ "list of strings which the pattern must not match", "more" ],
        "pattern": "\\bplease\\s+contact(\\s+\\w+(\\s+\\w+){0,2})",
        "flags": [ "ignorecase" ],
        "data_labels": [ "name" ],
        "data_type": "institute"
      },
```

The pattern is a python regex but note that as it's in JSON it needs a
double backslash so things like `\b` for boundary should be written `\\b`.
The flags can be `ignorecase` and/or `multiline` and
have the same meaning as described in the Python documentation.
The `data_labels` and `data_type` are simply used for labelling.
There should be a data_label for each regex pattern group because each matching part
can be made available via the named label.
The comment is optional but should be used to describe the rule.
The tests are optional but should be used to allow automated testing of rules,
using the `test_rules.py` script. All strings in the `test_true` list should
contain something which matches the pattern and all strings in the `test_false` list
should contain something that is not matched by the pattern.

Regex tip: `(?:[^\d]|\b)` can be used either side of a number regex
because it matches either non-digit or boundary (which handles start/end of
line/file).

Regex tip: `(?<![\\.0-9A-Za-z])XX` will ensure that the XX is not preceded
by a dot, a digit or a letter.

The `test_rules.py` program can be used to test a string against the rules.
It also tests some basic properties of the rules: that the regex is valid,
that the tests all pass, and that all labels have a matching regex group.

For more details see the `structuredreports` repo.

# Usage

Pass the path to a configuration file. You can use any path;
in this example we are using the provided template config file.

```
cd CogStack-SemEHR/anonymisation
./anonymiser.py conf/anonymisation_task.json
```

The program will anonymise all the text files in the input folder
and place annotations and/or anonymised text in the output folder.
The folders are specified in the config file as:
`text_data_path` for input files,
`anonymisation_output` for output files,
`extracted_phi` for the filename of the found names,
`grouped_phi_output` similarly,
`logging_file` for the log file, and set
`annotation_mode=true`.

Input files must be in the SMI format for best results. This is the
output from `CTP_DicomToText.py` (see the SmiServices repo) but is
easily created manually. It has headers like this:
```
[[Patient Name]] Anne Boleyn
[[Referring Physician Name]] Charles Dickens
[[ContentSequence]]
```

The headers are defined in the config file as `sensitive_fields`.
It uses the given names (from any tag listed in the `sensitive_fields` config)
so they can be replaced if found in the text. Forenames and surnames
are handled separately (as long as they are 4 or more letters).

It then anonymises all text after the `[[ContentSequence]]` header, or any
tag listed in the `working_fields` config. If there is no field in the input
from the `working_fields` config then nothing is anonymised.

The output files are given the same name as the input files.
If XML has been requested then additional files will be written having
the same name but with `.knowtator.xml` appended. The `phi` file will
be in JSON format.

The XML format contains a set of annotations like this:
```
<?xml version="1.0" ?>
<annotations>
 <annotation>
  <mention id="filename-1"/>
  <annotator id="filename-1">semehr</annotator>
  <span start="125" end="135"/>
  <spannedText>Tom Sawyer</spannedText>
  <creationDate>Wed November 11 13:04:51 2020</creationDate>
 </annotation>
 <classMention id="filename-1">
  <mentionClass id="semehr_sensitive_info">Tom Sawyer</mentionClass>
 </classMention>
</annotations>
```

The phi output looks like this:
```
  {
    "doc": "inputfile1.txt",
    "pos": 520,
    "start": 520,
    "type": "date",
    "sent": "23/04/15"
  },
  {
    "doc": "inputfile2.txt",
    "pos": 1435,
    "start": 1447,
    "type": "assistant",
    "sent": "Dr Jobs"
  },
```

The grouped phi output is plain text and is not useful.

A simple `test_anon.py` script can be used to test the anonymiser without having
to create directories and config files. Simply pass a document string as the first
argument. It can contain `\n` strings which will be converted to newlines. The
output will show the redacted words as DEBUG statements and then the content of
the output phi json file. For example `./test_anon.py "Seen by Dr. Jones on 15 Feb here"`
```
Usage: test_anon.py [-v] "document text to be anonymised"
Usage: test_anon.py [-v] filename.txt
Usage: test_anon.py  (uses built-in sample text)
```

# Troubleshooting

If it crashes with an exception like this
`TypeError: must be str, not NoneType`
on this line
`start = d['pos'][0] + d['attrs']['full_match'].find(d['attrs']['name'])`
and the output contains a line like this
`DEBUG removing None [clinic]`
then the cause is probably the regular expression in the rule.
It is trying to put the match groups into the named `data_labels`,
i.e. the first group of matching text inside `()` brackets is placed
into the first named data_label, and so on. If there is no text then
`None` is returned which causes the crash. The solution is to make
the preceding match groups into non-returning ones by prefixing them
with `?:`
