#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import xml.dom.minidom
import datetime
from os.path import join, isfile
from os import listdir
import logging
import re
import sys
import SemEHR.ann_post_rules as ann_post_rules
from SemEHR.docanalysis import SemEHRAnnDoc
import SemEHR.utils as utils


class AnnConverter(object):

    @staticmethod
    def load_ann(ann_json, file_key):
        d = SemEHRAnnDoc(file_key=file_key)
        d.load(ann_json)
        return d

    @staticmethod
    def get_semehr_ann_label(ann):
        str_context = ''
        if ann.negation != 'Affirmed':
            str_context += ann.negation + '_'
        if ann.temporality != 'Recent':
            str_context += ann.temporality + '_'
        if ann.experiencer != 'Patient':
            str_context += ann.experiencer + '_'
        if hasattr(ann, 'ruled_by'):
            if ann.ruled_by is not None and len(ann.ruled_by) >0:
                str_context += 'ruled_'
        pref = ''
        if hasattr(ann, 'pref'):
            pref = ann.pref
        elif hasattr(ann, 'minor_type'):
            pref = ann.minor_type
        cui = ''
        if hasattr(ann, 'cui'):
            cui = ann.cui
        elif hasattr(ann, 'major_type'):
            cui = ann.major_type
        return '%s%s(%s)' % (str_context, pref, cui)

    @staticmethod
    def get_semehr_ann_label_simple(ann, label_mapping=None, label='Phenotype'):
        # only return one label and ignore (a) negated (b)experiencer != patient (c) has been ruled out by rules
        if ann.negation != 'Affirmed' or ann.experiencer != 'Patient':
            return None
        if hasattr(ann, 'ruled_by'):
            if ann.ruled_by is not None and len(ann.ruled_by) >0:
                return None
        if label is None and label_mapping is not None:
            pref = ''
            if hasattr(ann, 'cui'):
                if ann.cui in label_mapping:
                    pref = label_mapping[ann.cui]
                else:
                    pref = None
            elif hasattr(ann, 'minor_type'):
                # pref = ann.minor_type
                pref = None
            label = pref
        return label

    @staticmethod
    def to_eHOST(ann_doc, full_text=None, file_pattern='%s.txt', id_pattern='smehr-%s-%s',
                 ann_to_convert=None, sty_filters=None,
                 ann_simplification=False, simplified_label=None, label_mapping=None):
        """
        convert SemEHR annotations to eHOST for annotation
        :param ann_doc:
        :param full_text:
        :param file_pattern:
        :param id_pattern:
        :param ann_to_convert:
        :param sty_filters:
        :param ann_simplification: whether to use simplification on selecting contextualised annotations from SemEHR
        :param simplified_label: single label to be used for annotation, like phenotype
        :param label_mapping: dictionary to map CUI to labels
        :return:
        """
        elem_annotations = ET.Element("annotations")
        elem_annotations.set('textSource', file_pattern % ann_doc.file_key)
        idx = 0
        anns = []
        if ann_to_convert is None:
            ann_to_convert = ['annotations', 'phenotypes']
        if 'annotations' in ann_to_convert:
            anns += ann_doc.annotations
        if 'phenotypes' in ann_to_convert:
            anns += ann_doc.phenotypes
        for ann in sorted(anns, key=lambda x: x.start): # was just anns
            if sty_filters is not None:
                if not hasattr(ann, 'sty') or ann.sty not in sty_filters:
                    continue
            if ann_simplification:
                # only show positive annotations and use single label
                label_class = AnnConverter.get_semehr_ann_label_simple(ann, label=simplified_label,
                                                                       label_mapping=label_mapping)
            else:
                label_class = AnnConverter.get_semehr_ann_label(ann)
            if label_class is None:
                continue
            idx += 1
            mention_id = id_pattern % (ann_doc.file_key, idx)
            elem_ann = ET.SubElement(elem_annotations, "annotation")
            elem_mention = ET.SubElement(elem_ann, "mention")
            elem_mention.set('id', mention_id)
            elem_annotator = ET.SubElement(elem_ann, "annotator")
            elem_annotator.set('id', 'semehr')
            elem_annotator.text = 'semehr'
            elem_span = ET.SubElement(elem_ann, "span")
            s = ann.start
            e = ann.end
            if full_text is not None:
                if full_text[s:e].lower() != ann.str.lower():
                    os = s
                    oe = e
                    [s, e] = ann_post_rules.AnnRuleExecutor.relocate_annotation_pos(full_text,
                                                                                    s, e, ann.str)
                    logging.info('%s,%s => %s,%s' % (os, oe, s, e))
                # else:
                #    logging.info('string matches, no reloaction needed [%s] [%s]' % (full_text[s:e].lower(), ann.str.lower()))
            elem_span.set('start', '%s' % s)
            elem_span.set('end', '%s' % e)
            elem_spanText = ET.SubElement(elem_ann, "spannedText")
            elem_spanText.text = ann.str
            elem_date = ET.SubElement(elem_ann, "creationDate")
            elem_date.text = datetime.datetime.now().strftime("%a %B %d %X %Z %Y")
            #
            elem_class = ET.SubElement(elem_annotations, "classMention")
            elem_class.set('id', mention_id)
            elem_mention_class = ET.SubElement(elem_class, "mentionClass")
            elem_mention_class.set('id', label_class)
            elem_mention_class.text = ann.str
        tree = ET.ElementTree(elem_annotations)
        #return ET.tostring(elem_annotations, encoding='utf8', method='xml')
        return xml.dom.minidom.parseString(ET.tostring(elem_annotations)).toprettyxml(indent=" ")

    @staticmethod
    def convert_text_ann_from_db(sql_temp, pks, db_conn, full_text_folder, ann_folder,
                                 full_text_file_pattern='%s.txt',
                                 ann_file_pattern='%s.txt.knowtator.xml'):
        raise Exception('convert_text_ann_from_db not supported')

    @staticmethod
    def get_db_docs_for_converting(settings):
        raise Exception('get_db_docs_for_converting not supported')

    @staticmethod
    def convert_text_ann_from_files(full_text_folder, ann_folder, output_folder,
                                    full_text_file_pattern='(%s).txt',
                                    ann_file_pattern='se_ann_%s.json',
                                    output_file_pattern='%s.txt.knowtator.xml',
                                    ann_to_convert=None, ann_simplification=False,
                                    simplified_label=None, label_mapping=None):
        text_files = [f for f in listdir(full_text_folder) if isfile(join(full_text_folder, f))]
        p = re.compile(full_text_file_pattern)
        for f in text_files:
            logging.info('working on [%s]' % f)
            m = p.match(f)
            if m is not None:
                fk = m.group(1)
                text = utils.read_text_file_as_string(join(full_text_folder, f))
                anns = utils.load_json_data(join(ann_folder, ann_file_pattern % fk))
                xml = AnnConverter.to_eHOST(AnnConverter.load_ann(anns, fk), full_text=text,
                                            ann_to_convert=ann_to_convert,
                                            ann_simplification=ann_simplification,
                                            simplified_label=simplified_label,
                                            label_mapping=label_mapping)
                utils.save_string(xml, join(output_folder, output_file_pattern % fk))
                utils.save_string(text.replace('\r', ' '), join(full_text_folder, f))
                logging.info('doc [%s] done' % fk)

    @staticmethod
    def get_files_for_converting(settings):
        label_mapping = None
        if 'label_mapping_json' in settings:
            label_mapping = utils.load_json_data(settings['label_mapping_json'])
        AnnConverter.convert_text_ann_from_files(
            settings['full_text_folder'],
            settings['ann_folder'],
            settings['output_folder'],
            settings['full_text_file_pattern'],
            settings['ann_file_pattern'],
            settings['output_file_pattern'],
            settings['ann_to_convert'],
            ann_simplification=settings['anns_simplification'] if 'anns_simplification' in settings else False,
            simplified_label=settings['simplified_label'] if 'simplified_label' in settings else None,
            label_mapping=label_mapping
        )

    @staticmethod
    def convvert_anns(setting_file):
        settings = utils.load_json_data(setting_file)
        if settings['source'] == 'db':
            AnnConverter.get_db_docs_for_converting(settings)
        else:
            AnnConverter.get_files_for_converting(settings)


if __name__ == "__main__":
    logging.basicConfig(level='INFO', format='%(name)s %(asctime)s %(levelname)s %(message)s')
    if len(sys.argv) < 2:
        print('Usage:')
        print('  python ann_converter.py SETTING_FILE_PATH')
        print('or:')
        print('  python ann_converter.py input.txt input.semehr_results input.mapping output.xml')
        exit(0)
    if len(sys.argv) < 3:
        AnnConverter.convvert_anns(sys.argv[1])
        exit(0)
    if len(sys.argv) < 6:
        # Parameters: doc.txt semehr_results.json mapping.json out.xml
        text = utils.read_text_file_as_string(sys.argv[1])
        anns = utils.load_json_data(sys.argv[2])
        # a json file to map a CUI to a label, e.g., { "C0948008": "Ischemic stroke" }
        mapping = utils.load_json_data(sys.argv[3])
        # If using a concept mapping file it needs to be flattened and inverted.
        # i.e. { 'thing' : [ 'C123\tstuff', ... ] }  =>  { 'C123':'thing' }
        # A concept mapping file will have a list for the value of each element:
        if isinstance(mapping[next(iter(mapping))], list):
            # Each element is a list of "CUI\tDesc\tDesc"
            # so get CUI from first elem of tab-separated string
            flattened_mapping = {}
            for label in mapping:
                flattened_mapping.update( { x : label for x in [cui_str.split('\t')[0] for cui_str in mapping[label]] } )
            mapping = flattened_mapping
        file_key = None
        anns_loaded = AnnConverter.load_ann(anns, file_key)
        xml = AnnConverter.to_eHOST(anns_loaded, full_text=text, ann_to_convert=None,
                                ann_simplification=True,
                                simplified_label=None,
                                label_mapping=mapping)
        utils.save_string(xml, sys.argv[4])
        exit(0)
    exit(1)
