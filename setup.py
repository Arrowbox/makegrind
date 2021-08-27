# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Setup makegrind package.
"""

import os
import sys
from setuptools import setup, find_packages

pkg_name = 'makegrind'
setup(
    name=pkg_name,

    description='Makefile performance analysis',
    author='Jayson Messenger',
    author_email='messengerj@google.com',

    use_scm_version=True,

    packages=find_packages('src'),
    package_dir={'':'src'},
    include_package_data=True,

    entry_points={
        'console_scripts': [
            'makegrind = makegrind.__main__:main'
            ]
        },

    setup_requires=[
        'setuptools_scm',
        'pytest-runner',
        ],
    install_requires=[
        'networkx',
        'pyyaml',
        'click',
        ],
    tests_require=[
        'pytest',
        ]
)

