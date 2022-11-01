# SemEHR

Surfacing Semantic Data from Clinical Notes in Electronic Health Records for Tailored Care, Trial Recruitment and Clinical Research.

This repo has been migrated without history from the `smi-branch` branch in https://git.ecdf.ed.ac.uk/hwu33/CogStack-SemEHR/-/tree/smi-branch

Contents:
* Anonymisation of Structured Reports
* Annotation service for medical terms extracted from Structured Reports

## Documentation

* [REST API](RESTful_service/README.md)
* [REST API Dockerfile](Dockerfile.md)
* [REST API images](RESTful_service/vis/images/README.md)
* [REST API css](RESTful_service/vis/css/images/README.md)
* [anonymisation rules](anonymisation/README.md)
* [anonymisation rules](anonymisation/conf/README.md)
* [anonymisation rules](anonymisation/conf/rules/README.md)
* [UMLS ontology](umls/README.md)
* [eHOST annotation](annotation.md)
* [installation](installation/readme.md)

## Updates

- see git history for updates
- (19/11/2021) Annotation Conversion updated
- (30/11/2020) This is minimised version of SemEHR to be run within a constrained environment (e.g. NHS safehaven) where only NLP is needed 

## Annotation conversion from SemEHR results into eHOST

Check [annotation.md](annotation.md) for details

## Publications

SemEHR: surfacing semantic data from clinical notes in electronic health records for tailored care, trial recruitment, and clinical research. Honghan Wu, Giulia Toti, Katherine I Morley, Zina Ibrahim, Amos Folarin, Ismail Kartoglu, Richard Jackson, Asha Agrawal, Clive Stringer, Darren Gale, Genevieve M Gorrell, Angus Roberts, Matthew Broadbent, Robert Stewart, Richard J B Dobson. The Lancet , Volume 390 , S97. [10.1016/S0140-6736(17)33032-5](http://dx.doi.org/10.1016/S0140-6736%2817%2933032-5)

SemEHR: A General-purpose Semantic Search System to Surface Semantic Data from Clinical Notes for Tailored Care, Trial Recruitment and Clinical Research. Honghan Wu, Giulia Toti, Katherine I Morley, Zina Ibrahim, Amos Folarin, Ismail Kartoglu, Richard Jackson, Asha Agrawal, Clive Stringer, Darren Gale, Genevieve M Gorrell, Angus Roberts, Matthew Broadbent, Robert Stewart, Richard J B Dobson.Journal of the American Medical Informatics Association, 2017. [10.1093/jamia/ocx160](http://dx.doi.org/10.1093/jamia/ocx160)

## Questions?

Please contact SMI rather than the original author.
