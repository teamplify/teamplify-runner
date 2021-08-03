#!/usr/bin/env python3
import sys

from setuptools import setup

import teamplify_runner


MIN_PYTHON_VER = (3, 6)
MIN_PYTHON_STR = '.'.join(map(str, MIN_PYTHON_VER))

if sys.version_info < MIN_PYTHON_VER:
    sys.exit(
        'Teamplify runner requires Python %s or later' % MIN_PYTHON_STR,
    )


def get_requirements(extra=None):
    filename = 'requirements-%s.txt' % extra if extra else 'requirements.txt'
    with open(filename) as fp:
        return [
            x.strip() for x in fp.read().split('\n') if not x.startswith('#')
        ]


setup(
    name='teamplify',
    version=teamplify_runner.__version__,
    description='Teamplify on-premise runner',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Teamplify',
    author_email='support@teamplify.com',
    url='https://github.com/teamplify/teamplify-runner/',
    install_requires=get_requirements(),
    extras_require={
        'tests': get_requirements('tests'),
    },
    packages=['teamplify_runner'],
    include_package_data=True,
    python_requires=">=%s" % MIN_PYTHON_STR,
    license='MIT',
    entry_points={
        'console_scripts': [
            'teamplify = teamplify_runner.cli:main',
        ],
    },
)
