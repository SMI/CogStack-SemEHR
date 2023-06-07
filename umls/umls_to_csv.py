#!/usr/bin/env python3
# Extract the UMLS tables into the fields we need for SemEHR
# This version is for the UMLS-2019 specifically
# because the 2021 version removed the relationships and put
# them into the hierarchy file but in a useless format.

# Download and unpack (example is 2021, same for 2019):
# unzip umls-2021AA-full.zip
# cd 2021AA-full
# unzip 2021aa-1-meta.nlm
# unzip 2021aa-2-meta.nlm
# cd 2021AA/META
# gunzip *.gz
# cat MRCONSO.RRF.a?   > MRCONSO.RRF
# cat MRHIER.RRF.a?    > MRHIER.RRF
# cat MRREL.RRF.a?     > MRREL.RRF
# cat MRSAT.RRF.a?     > MRSAT.RRF
# cat MRXNS_ENG.RRF.a? > MRXNS_ENG.RRF
# cat MRXNW_ENG.RRF.a? > MRXNW_ENG.RRF
# cat MRXW_ENG.RRF.a?  > MRXW_ENG.RRF
# wget https://lhncbc.nlm.nih.gov/ii/tools/MetaMap/Docs/SemanticTypes_2018AB.txt
# wget https://lhncbc.nlm.nih.gov/ii/tools/MetaMap/Docs/SemGroups_2018.txt

# There are two types of parent/child relationship:
#  Broader/Narrower and Parent/Child
#  Honghan thinks only Narrower is needed but the UMLS people say:
#  RB/RN are generally used when the relations are not part of a broader hierarchy.
#  PAR/CHD relations are generally part of a hierarchy. There may be some exceptions to this. 
# However the relations can come from different vocabularies (sources)
# so we might restrict our narrower results to those defined in the Metathesaurus (MTH)
# or those coming from SNOMED (SNOMEDCT_US).

include_CHD = True                           # include Child relations?
filter_to_sources = [ 'MTH', 'SNOMEDCT_US' ] # empty list [] is not filtered, else MTH and/or SNOMEDCT_US
test_code = 'C0205076'

import argparse
import csv
import os
import sys

tui_for_cui = {}
label_for_tui = {}
group_for_tui = {}
grouplabel_for_tui = {}
cui_for_snomed = {}
label_for_cui = {}
narrower = {}
broader = {}

# ---------------------------------------------------------------------
parser = argparse.ArgumentParser(description='UMLS to CSV')
parser.add_argument('--sources', dest='sources', action="store", help='comma-separated list of sources default %(default)s', default='MTH,SNOMEDCT_US')
parser.add_argument('--chd', dest='chd', action="store_true", help="whether to include CHD (child) relationships default %(default)s", default=True)
parser.add_argument('--test', dest='test', action="store", help="CUI to display narrower concepts default %(default)s", default=test_code)
args = parser.parse_args()
include_CHD = args.chd
filter_to_sources = args.sources.split(',')


# ---------------------------------------------------------------------
# Sample code to traverse the narrower relationships

_narrower_rc = set()

def list_intersection(list1, list2):
    assert(isinstance(list1, list))
    assert(isinstance(list2, list))
    return [x for x in list1 if x in list2]

def cui_narrower(cui, depth=0, maxdepth=999):
    """
    Return a list of CUIs which are narrower concepts.
    depth - for internal use, counting how deep we are in recursion
    maxdepth - 0 returns the cui, 1 returns its children, and so on
    filter_to_same-tui - only returns CUIs from the same Samantic Type Group
    prunelist - a list of CUI which should not be descended or returned
    """
    global _narrower_rc
    if maxdepth == 0:
        return [cui]
    if depth == 0:
        _narrower_rc = set()
        _narrower_rc.update([cui]) # added myself first
    if depth >= maxdepth:
        return
    children = narrower.get(cui, [])
    useful_children = [child for child in children if
        child not in _narrower_rc]
    #print('%s%s children: %s' % (' '*depth, cui, useful_children))
    for ch in useful_children:
        print('%s%s = %s' % (' '*depth, ch, label_for_cui[ch]))
    _narrower_rc.update(useful_children)
    for child in useful_children:
        cui_narrower(child, depth+1, maxdepth=maxdepth)
    if depth == 0:
        return list(_narrower_rc)


# ---------------------------------------------------------------------
# SemGroups
#  maps a semantic type (tui) to a semantic type group
#  i.e. groups together related tui into a set
#     Group|GroupName|Type|TypeLabel
# eg. ACTI|Activities & Behaviors|T052|Activity

print('Reading semantic groups...')
with open('SemGroups_2018.txt') as fd:
    rdr = csv.reader(fd, delimiter='|')
    for row in rdr:
        group_for_tui[row[2]] = row[0]
        grouplabel_for_tui[row[2]] = row[1]
        label_for_tui[row[2]] = row[3]

# ---------------------------------------------------------------------
# MRSTY
#  maps a concept to a semantic type
#     cui|tui|...
# eg. C0000005|T116|A1.4.1.2.1.7|Amino Acid, Peptide, or Protein|AT17648347|256|

print('Reading semantic types...')
with open('MRSTY.RRF') as fd:
    rdr = csv.reader(fd, delimiter='|')
    for row in rdr:
        cui=row[0]
        tui=row[1]
        if cui in tui_for_cui:
            tui_for_cui[cui].append(tui)
        else:
            tui_for_cui[cui] = [tui]


# ---------------------------------------------------------------------
# MRCONSO
#  maps from concept (cui) to other vocabularies
#     cui|lang|ts|lui|   stt|sui|IsPref|aui      |saui    |scui|sdui|sab|tty|code|str|srl|suppress|cvf
# eg.
# C0205076|ENG|S|L0248726|PF|S2717960|N|A12802125|        |C62484||NCI|PT|C62484|Chest Wall|0|N|256|
# C0205076|ENG|S|L0248726|PF|S2717960|N|A23964177|        |C62484||NCI_CDISC|SY|C62484|Chest Wall|0|N|256|
# C0205076|ENG|S|L0248726|PF|S2717960|N|A24093967|        |LA4178-5||LNC|LA|LA4178-5|Chest Wall|0|N|256|
# C0205076|ENG|S|L0248726|PF|S2717960|N|A31603448|        |C62484||NCI_GDC|PT|C62484|Chest Wall|0|N|256|
# C0205076|ENG|S|L0248726|PF|S2717960|N|A32395146|        |C62484||NCI_caDSR|SY|C62484|Chest Wall|0|N||
# C0205076|ENG|S|L0248726|PF|S2717960|Y|A26648386|        |M0407552|D035441|MSH|ET|D035441|Chest Wall|0|N|256|
# C0205076|ENG|P|L0780053|PF|S0836022|N|A3108835|503946010|78904004||SNOMEDCT_US|PT|78904004|Chest wall structure|9|N|256|
# C0205076|ENG|S|L0248726|VO|S0282525|Y|A2895894|130920016|78904004||SNOMEDCT_US|SY|78904004|Chest wall|9|N|256|
# C0205076|ENG|S|L0248726|VO|S0324474|N|A4737697|130921017|78904004||SNOMEDCT_US|IS|78904004|Chest wall, NOS|9|O|256|
# C0205076|ENG|S|L0248727|VO|S0324475|Y|A2920897|130922012|78904004||SNOMEDCT_US|SY|78904004|Thoracic wall|9|N|256|
# C0205076|ENG|S|L2896366|PF|S3215819|Y|A3348310|819896010|78904004||SNOMEDCT_US|FN|78904004|Chest wall structure (body structure)|9|N||

print('Reading concepts...')
with open('MRCONSO.RRF') as fd:
    rdr = csv.reader(fd, delimiter='|')
    for row in rdr:
        cui = row[0]
        lang = row[1]    # e.g. ENG
        ts = row[2]      # e.g. P or S
        stt = row[4]     # e.g. PF VC VO
        ispref = row[6]  # e.g. Y or N
        snomed = row[9]
        dic = row[11]
        label = row[14]
        # Ignore non-English names
        if lang != 'ENG':
            continue
        # Preferred label, see https://list.nih.gov/cgi-bin/wa.exe?A2=ind1910&L=UMLSUSERS-L&P=R655
        # LAT='ENG' and TS='P' and STT='PF' and ISPREF='Y' 
        if lang == 'ENG' and ts == 'P' and stt == 'PF' and ispref == 'Y':
            label_for_cui[cui] = label
        if dic == 'SNOMEDCT_US':
            cui_for_snomed[snomed] = cui # may be multiple, last row wins
            if cui == test_code:
                print('Mapping SNOMED %s to %s' % (snomed, cui))

# ---------------------------------------------------------------------
# MRREL
#  relationships between CUIs
#     cui1    |aui1     |typ1|rel|cui2    |aui2    |typ2|rela|rui|srui|sab|sl|rg|dir|suppress|cvf
# eg. C0000005|A13433185|SCUI|RB|C0036775|A7466261|SCUI||R86000559||MSHFRE|MSHFRE|||N||

print('Reading relationships...')
with open('MRREL.RRF') as fd:
    rdr = csv.reader(fd, delimiter='|')
    for row in rdr:
        cui1 = row[0]
        rel  = row[3]
        cui2 = row[4]
        source = row[10]
        # Ignore self-referential or missing
        if (cui1 == cui2) or (not cui1) or (not cui2):
            continue
        # Ignore if not from a requested vocabulary
        if filter_to_sources and (source not in filter_to_sources):
            continue
        # Narrower relationship, create set or update
        if rel == 'RN' or (include_CHD and rel == 'CHD'):
            if cui1 in narrower:
                narrower[cui1].update([cui2])
            else:
                narrower[cui1] = set([ cui2 ])
        # Broader relationship, create set or update
        elif rel == 'RB' or rel == 'PAR':
            if cui1 in broader:
                broader[cui1].update([cui2])
            else:
                broader[cui1] = set([ cui2 ])
        # Debug
        if cui1 == test_code and (rel == 'RN' or rel=='RB' or rel=='PAR' or (include_CHD and rel=='CHD')):
            print('%s -> %s -> %s [from %s]' % (cui1,rel,cui2,source))

# ---------------------------------------------------------------------
# Now remove all the terms in narrower which also appear in broader
print('%s narrower -> %s' % (test_code, sorted(narrower.get(test_code, []))))
print('%s broader  <- %s' % (test_code, sorted(broader.get(test_code, []))))
print('Filtering %d narrower relationships...' % len(narrower))
for cui1 in narrower:
    newlist = [x for x in narrower[cui1] if x not in broader.get(cui1, [])]
    narrower[cui1] = newlist
print('%s narrower (immediate children) -> %s' % (test_code, sorted(narrower[test_code])))
# Test a complete traverse
print('All narrower concepts:')
nar = cui_narrower(test_code)
print('%s ...' % nar[0:99])
print('(%d entries total))' % len(nar))

# ---------------------------------------------------------------------
# OUTPUT

print('Output semantic types (sty.csv)...')
with open('sty.csv', 'w') as fd:
    print('tui|tuigroup|tuigrouplabel', file=fd)
    for tui in sorted(group_for_tui):
        print('%s|%s|%s' % (tui, group_for_tui[tui], grouplabel_for_tui[tui]), file=fd)

print('Output SNOMED (snomed.csv)...')
with open('snomed.csv', 'w') as fd:
    print('snomed|cui', file=fd)
    for snomed in sorted(cui_for_snomed):
        print('%s|%s' % (snomed, cui_for_snomed[snomed]), file=fd)

print('Output concepts (cui.csv)...')
with open('cui.csv', 'w') as fd:
    print('cui|tui|tuigroup|cuilabel', file=fd)
    for cui in sorted(tui_for_cui):
        print('%s|%s|%s|%s' % (cui,
            ','.join(tui_for_cui[cui]),
            ','.join(set([ group_for_tui[x] for x in tui_for_cui[cui] ])),
            label_for_cui.get(cui,'')), # some concepts only have non-English labels
            file=fd)

print('Output relationships (rel.csv)...')
with open('rel.csv', 'w') as fd:
    print('cui1|has|cui2', file=fd)
    for cui1 in sorted(narrower):
        print('%s|%s|%s' % (cui1, 'RN', ','.join(narrower[cui1])), file=fd)
