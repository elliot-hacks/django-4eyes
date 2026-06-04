"""
Setup configuration for django-4eyes package.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding='utf-8')

# Package metadata
NAME = 'django-4eyes'
VERSION = '1.0.0'
DESCRIPTION = 'Enterprise-grade approval workflow engine for Django'
LONG_DESCRIPTION = long_description
LONG_DESCRIPTION_CONTENT_TYPE = 'text/markdown'
AUTHOR = 'Your Name'
AUTHOR_EMAIL = 'your.email@example.com'
URL = 'https://github.com/yourusername/django-4eyes'
PROJECT_URLS = {
    'Bug Tracker': 'https://github.com/yourusername/django-4eyes/issues',
    'Documentation': 'https://django-4eyes.readthedocs.io/',
    'Source': 'https://github.com/yourusername/django-4eyes',
}
LICENSE = 'MIT'
CLASSIFIERS = [
    'Development Status :: 4 - Beta',
    'Framework :: Django',
    'Framework :: Django :: 3.2',
    'Framework :: Django :: 4.0',
    'Framework :: Django :: 4.1',
    'Framework :: Django :: 4.2',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.8',
    'Programming Language :: Python :: 3.9',
    'Programming Language :: Python :: 3.10',
    'Programming Language :: Python :: 3.11',
    'Topic :: Software Development :: Libraries :: Python Modules',
]
KEYWORDS = ['django', 'approval', 'workflow', 'four-eyes', 'maker-checker', 'enterprise']

# Requirements
PYTHON_REQUIRES = '>=3.8'
INSTALL_REQUIRES = [
    'Django>=3.2',
]

# Packages
PACKAGES = find_packages(exclude=['tests', 'tests.*', 'example', 'example.*'])
INCLUDE_PACKAGE_DATA = True

setup(
    name=NAME,
    version=VERSION,
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type='text/markdown',
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    url=URL,
    project_urls=PROJECT_URLS,
    license=LICENSE,
    classifiers=CLASSIFIERS,
    keywords=KEYWORDS,
    packages=PACKAGES,
    include_package_data=True,
    python_requires=PYTHON_REQUIRES,
    install_requires=INSTALL_REQUIRES,
    entry_points={
        'console_scripts': [
            # Add any command-line scripts here if needed
        ],
    },
)