# setup.py for SemEHR
#   Uses setuptools instead of distutils
# Requires:
#   Requirements.txt with list of dependencies
#   Uses the find_packages function but skips tests

from setuptools import setup, find_packages
from os.path import join, abspath, dirname, isdir
import sys

# Read requirements.txt in current directory
# and convert it into the form required by setuptools
requirements_txt = join(abspath(dirname(__file__)), 'requirements.txt')
requirements = [l.strip() for l in open(requirements_txt) if l and not l.startswith('#')]
 
def translate_req(req):
    # this>=0.3.2 -> this(>=0.3.2)
    ops = ('<=', '>=', '==', '<', '>', '!=')
    version = None
    for op in ops:
        if op in req:
            req, version = req.split(op)
            version = op + version
    if version:
        req += '(%s)' % version
    return req
 
def version_from_txt():
    with open('version.txt') as fd:
        ver = next(fd).strip()
    version = ver.split('.')
    version[2] = str(int(version[2]) + 1)
    vernext = '.'.join(version)
    with open('version.txt', 'w') as fd:
        print(vernext, file=fd)
    return ver

setup(
    name='SemEHR',
    version=version_from_txt(),
    packages=find_packages(where=dirname(__file__), exclude=('tests',)),
    package_dir={'':dirname(__file__)},
    url='https://github.com/SMI/CogStack-SemEHR',
    license='GPLv3',
    description='Python modules for Semantic Analysis of Electronic Health Records',
    long_description='SemEHR common modules provide useful functions for anonymisation and annotation of text from DICOM Structured Report files.',
    requires=[translate_req(r) for r in requirements],
    install_requires=requirements
)

