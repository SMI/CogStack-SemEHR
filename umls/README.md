# UMLS Metathesaurus

## Introduction

The query expansion code requires a local copy of the UMLS database,
and the code which maps SNOMED codes to UMLS concepts also requires it.

NOTE! The UMLS CANNOT be redistributed or used without an agreement.

NOTE! The 2019 version of the UMLS database must be used for two reasons:
* the annotation creation part of SemEHR uses the 2019 version so it makes
sense to keep the concepts identical
* the 2021 version of the UMLS removed the relationships from the MRREL file
and the replacement MRHIER file is not so useful

## Creation

Download the UMLS metathesaurus (warning, needs 40GB space!). Unpack:
```
unzip umls-2019.zip
cd 2019*
unzip 2019*-1-meta.nlm
unzip 2019*-2-meta.nlm
cd 2019*/META
gunzip *.gz
cat MRCONSO.RRF.a?   > MRCONSO.RRF
cat MRHIER.RRF.a?    > MRHIER.RRF
cat MRREL.RRF.a?     > MRREL.RRF
cat MRSAT.RRF.a?     > MRSAT.RRF
cat MRXNS_ENG.RRF.a? > MRXNS_ENG.RRF
cat MRXNW_ENG.RRF.a? > MRXNW_ENG.RRF
cat MRXW_ENG.RRF.a?  > MRXW_ENG.RRF
wget https://lhncbc.nlm.nih.gov/ii/tools/MetaMap/Docs/SemanticTypes_2018AB.txt
wget https://lhncbc.nlm.nih.gov/ii/tools/MetaMap/Docs/SemGroups_2018.txt
```

Convert the useful parts of the database to our own format CSV files.
These have a useful selection of columns and also reformat the rows so,
for example, the Narrower Concepts are all listed in a single row for
each concept rather than as multiple rows.


```
./umls_to_csv.py
```

There is an option to specify whether the relationships should be filtered
to include only those defined in the Metathesaurus or in SMOMED.
By default both of those are included. This means that relationships
defined by other vocabularies are ignored. You can choose to filter only
to MTH or only to SNOMEDCT_US or both using
```
umls_to_csv.py --sources MTH
umls_to_csv.py --sources SNOMEDCT_US
umls_to_csv.py --sources MTH,SNOMEDCT_US
```

The difference, as an example using concept C0205076 (Chest Wall) is:
* MTH - only has 1 child concept, fully expands to 2 children
* SNOMED - has 16 child concepts, fully expands to 2283 children
* both - same 16 child concepts, fully expands to 8075 children

```
umls.py --cfg . --csvs SNOMED/
umls.py --cfg . --csvs MTH/
umls.py --cfg . --csvs MTH+SNOMED/
```

# CSV files

Note that the files are pipe-separated so that the columns can contain
commas more easily.

## cui.csv

Maps CUI (concept id) to TUI (semantic type id), and also gives
the TUI group names and a label (description) of the CUI.  The CUI
can have several semantic types so they are comma-separated.

```
(cui|tui|tuigroup|cuilabel
C0000005|T116,T121,T130|CHEM,CHEM,CHEM|(131)I-MAA
```

(In practice the 3 group names are identical so only CHEM is output)

## rel.csv

Relationship between CUI1 and CUI2 with the implied meaning "has",
i.e. cui1 has a narrow (RN) concept cui2. The list of narrower
concepts is comma-separated.

```
cui1|has|cui2
C0000039|RN|C0043950,C0615231,C3253442,C3885037,C0621533,C0216971,C1611431,C0381030,C4489915,C1310941
```

## snomed.csv

Map a SNOMED code to a CUI. If there were multiple CUIs only one was chosen.
```
snomed|cui
100000000|C0308478
```

## sty.csv

Describes a Semantic Type. The identifier TUI is a member of a group of similar
types tuigroup, and the group has a label tuigrouplabel. This is used to find out
if a concept is related to other concepts that also share a simlar Semantic Type,
i.e. their types are both members of the same Semantic Group.

```
tui|tuigroup|tuigrouplabel
T001|LIVB|Living Beings
```

# Load into PostgreSQL

Use this script to load theresulting CSV files into a database:

```
./umls_create_postgres.py
```

## PostgreSQL tables

Schema: umls
Permission: granted to semehr_user, and semehr_admin.

```
CREATE TABLE umls.cui(cui varchar(16), tui varchar(99), tuigroup varchar(99), cuilabel text);
CREATE INDEX icui ON umls.cui (cui);
CREATE TABLE umls.rel(cui1 varchar(16), has varchar(4), cui2 text);
CREATE INDEX icui1 ON umls.rel (cui1);
CREATE TABLE umls.snomed(snomed text, cui text NOT NULL);
CREATE INDEX isnomed ON umls.snomed (snomed);
CREATE TABLE umls.sty(tui varchar(8), tuigroup varchar(8), tuigrouplabel varchar(99));
CREATE INDEX isty ON umls.sty (tui);
```
