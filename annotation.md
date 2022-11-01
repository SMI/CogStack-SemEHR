# Annotation setup 
This document describes how to collect feedback for SemEHR annotations for training machine learning models for improving baseline results.

## use eHOST as the annotation tool
1. Convert SemEHR annotation results to eHOST format. This step uses `ann_converter.py` at the root folder of this repository.
    ```bash
   python ann_converter.py text_file semehr_ann_file cui2label_mapping_file output_xml_file
    ```
   - `text_file` is the full text file 
   - `semehr_ann_file` is the SemEHR result json file
   - `cui2lable_mapping_file` is a json file to map UMLS CUI to a label, see below as an example for mapping two CUIs to `Ischemic stroke`.
   ```json
   {
    "C0948008": "Ischemic stroke",
    "C3178801": "Ischemic stroke",
    "C0859253": "Haemorrhage stroke"
   }   	
   ```
2. Annotation process: use eHOST to load the outputs and ask the annotators to do three things:
   - `delete` not relevant annotations
   - `add` missed annotations using relevant labels from the above mapping file
   - `correct` mislabelled annotations by changing the class to a correct label
