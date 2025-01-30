# -*- coding: utf-8 -*-
#
# Copyright © 2015,2016 Mathieu Duponchelle <mathieu.duponchelle@opencreed.com>
# Copyright © 2015,2016 Collabora Ltd
#
# This library is free software; you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation; either version 2.1 of the License, or (at your option)
# any later version.
#
# This library is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library.  If not, see <http://www.gnu.org/licenses/>.

"""
Setup file for hotdoc.
"""

import os
import sys
import errno
import unittest
import contextlib
import argparse
import json
from distutils.command.build import build
from distutils.command.build_ext import build_ext
from distutils.core import Command
from distutils.errors import DistutilsExecError
from distutils.dep_util import newer_group
import distutils.spawn as spawn

from setuptools import find_packages, setup, Extension
from setuptools.command.bdist_egg import bdist_egg
from setuptools.command.develop import develop
from setuptools.command.sdist import sdist
from setuptools.command.test import test

from hotdoc.utils.setup_utils import (
    VERSION, require_clean_submodules, symlink, pkgconfig)

SOURCE_DIR = os.path.abspath(os.path.dirname(__file__))
CMARK_DIR = os.path.join(SOURCE_DIR, 'cmark')
CMARK_SRCDIR = os.path.join(CMARK_DIR, 'src')
CMARK_EXTDIR = os.path.join(CMARK_DIR, 'extensions')
CMARK_BUILD_DIR = os.path.join(SOURCE_DIR, 'build_cmark')
CMARK_BUILT_SRCDIR = os.path.join(CMARK_BUILD_DIR, 'src')
CMARK_INCLUDE_DIRS = [CMARK_SRCDIR, CMARK_BUILT_SRCDIR]

require_clean_submodules(SOURCE_DIR, ['cmark'])


def src(filename):
    return os.path.join(SOURCE_DIR, filename)

# pylint: disable=invalid-name
# pylint: disable=missing-docstring


@contextlib.contextmanager
def cd(path):
    CWD = os.getcwd()

    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(CWD)


# pylint: disable=too-few-public-methods
class CMarkExtension(Extension):
    """
    A custom extension that will run cmake in the cmark subdir
    before building itself.
    """
    # pylint: disable=no-self-use

    def __run_cmake(self):
        if spawn.find_executable('cmake') is None:
            print("cmake  is required")
            print("Please install cmake and re-run setup")
            sys.exit(-1)
        if spawn.find_executable('make') is None:
            print("make  is required")
            print("please get a version of make and re-run setup")
            sys.exit(-1)

        if not os.path.exists(CMARK_BUILD_DIR):
            os.mkdir(CMARK_BUILD_DIR)
        with cd(CMARK_BUILD_DIR):
            try:
                spawn.spawn(['cmake', CMARK_DIR])
                spawn.spawn(['make', 'cmarkextensions'])
            except spawn.DistutilsExecError:
                print("Error while running cmake")
                sys.exit(-1)

    # pylint: disable=missing-docstring
    def build_custom(self):
        self.__run_cmake()


CMARK_SOURCES = [os.path.join('hotdoc', 'parsers', f) for f in
                 ('cmark_module.c',
                  'cmark_gtkdoc_extension.c',
                  'cmark_gtkdoc_scanner.c',
                  'cmark_include_extension.c',
                  'cmark_include_scanner.c',)]

for filename in os.listdir(CMARK_SRCDIR):
    if filename.endswith('.c'):
        CMARK_SOURCES.append(os.path.join(CMARK_SRCDIR, filename))

for filename in os.listdir(CMARK_EXTDIR):
    if filename.endswith('.c'):
        CMARK_SOURCES.append(os.path.join(CMARK_EXTDIR, filename))

CMARK_MODULE = CMarkExtension('hotdoc.parsers.cmark',
                              sources=CMARK_SOURCES,
                              include_dirs=CMARK_INCLUDE_DIRS,
                              define_macros=[
                                  ('LIBDIR', '"%s"' % CMARK_BUILD_DIR)])

# We build our search index in C for performance reasons

SEARCH_SOURCES = [os.path.join('hotdoc', 'parsers', 'search_module.c'),
                  os.path.join('hotdoc', 'parsers', 'trie.c')]

try:
    search_flags = pkgconfig('libxml-2.0', 'glib-2.0', 'json-glib-1.0')
except Exception as e:
    print("libxml-2.0, glib-2.0 and json-glib-1.0 are required: %s" % str(e))
    sys.exit(1)

print(search_flags)

SEARCH_MODULE = Extension('hotdoc.parsers.search',
                          sources=SEARCH_SOURCES, **search_flags)

# The default theme

THEME_SRC_DIR = os.path.join(SOURCE_DIR, 'hotdoc', 'hotdoc_bootstrap_theme')
THEME_DIST_DIR = os.path.join(THEME_SRC_DIR, 'dist')
THEME_REL_DIR = os.path.relpath(THEME_DIST_DIR, start=os.path.join(SOURCE_DIR,
                                                                   'hotdoc'))
require_clean_submodules(os.path.dirname(THEME_SRC_DIR),
                         'hotdoc_bootstrap_theme')


class BuildDefaultTheme(Command):
    """
    This will build the default theme.
    """
    user_options = []
    description = ("Build default html theme, the following dependencies are "
                   "required: GNU make, npm")

    # pylint: disable=missing-docstring
    def initialize_options(self):
        pass

    # pylint: disable=missing-docstring
    def finalize_options(self):
        pass

    # pylint: disable=missing-docstring
    # pylint: disable=no-self-use
    def run(self):
        if spawn.find_executable('gmake') is not None:
            gmake = 'gmake'
        elif spawn.find_executable('make') is not None:
            gmake = 'make'
        else:
            print("GNU make  is required")
            print("please get a version of GNU make and re-run setup")
            sys.exit(-1)
        if spawn.find_executable('npm') is None:
            print("npm is required")
            print("please get a version of npm and re-run setup")
            sys.exit(-1)

        with cd(THEME_SRC_DIR):
            try:
                spawn.spawn(['npm', 'install'])
                spawn.spawn(['./node_modules/bower/bin/bower',
                            'install', '--allow-root'])
                os.environ['LESS_INCLUDE_PATH'] = os.path.join(
                    SOURCE_DIR, 'hotdoc', 'less')
                spawn.spawn([gmake])
                del os.environ['LESS_INCLUDE_PATH']
                with open(os.path.join(THEME_DIST_DIR, 'theme.json'), 'w') as _:
                    _.write(json.dumps({
                        'prism-theme': 'prism-tomorrow',
                        'prism-light-theme': 'prism',
                        'hotdoc-version': VERSION}))
            except spawn.DistutilsExecError as e:
                print("Error while building default theme", e)
                sys.exit(-1)


# pylint: disable=missing-docstring
# pylint: disable=too-few-public-methods
class CustomDevelop(develop):

    def run(self):
        self.run_command('build_default_theme')
        return develop.run(self)


# pylint: disable=missing-docstring
class CustomBuild(build):

    def run(self):
        if not os.path.exists(THEME_DIST_DIR):
            self.run_command('build_default_theme')
        return build.run(self)


# pylint: disable=missing-docstring
class CustomSDist(sdist):

    def run(self):
        self.run_command('build_default_theme')
        return sdist.run(self)


class CustomBuildExt(build_ext):
    def run(self):
        for extension in self.extensions:
            if hasattr(extension, 'build_custom'):
                extension.build_custom()

        build_ext.run(self)
        return True


# pylint: disable=missing-docstring
class CustomBDistEgg(bdist_egg):

    def run(self):
        # This will not run when installing from pip, thus
        # avoiding a few dependencies.
        if not os.path.exists(THEME_DIST_DIR):
            self.run_command('build_default_theme')
        return bdist_egg.run(self)


# From http://stackoverflow.com/a/17004263/2931197
def discover_and_run_tests(forever):
    # use the default shared TestLoader instance
    test_loader = unittest.defaultTestLoader

    # use the basic test runner that outputs to sys.stderr
    test_runner = unittest.TextTestRunner()

    # automatically discover all tests
    # NOTE: only works for python 2.7 and later
    test_suite = test_loader.discover(SOURCE_DIR)

    # run the test suite
    loop = True
    while loop:
        res = test_runner.run(test_suite)
        if res.errors or res.failures or not forever:
            loop = False


class DiscoverTest(test):
    user_options = test.user_options + [('forever', None, 'Run until failure')]

    def __init__(self, *args, **kwargs):
        test.__init__(self, *args, **kwargs)
        self.test_args = []
        self.test_suite = True
        self.forever = False

    def initialize_options(self):
        test.initialize_options(self)
        self.forever = False

    def finalize_options(self):
        test.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        discover_and_run_tests(self.forever)


INSTALL_REQUIRES = [
    'pyyaml>=6',
    'lxml',
    'schema',
    'appdirs',
    'wheezy.template',
    'toposort>=1.4',
    'importlib_metadata; python_version<"3.10"',
    'backports.entry_points_selectable',
]

# dbus-deviation requires sphinx, which requires python 3.5
if sys.version_info[1] >= 5:
    INSTALL_REQUIRES += ['dbus-deviation>=0.4.0']

EXTRAS_REQUIRE = {
    'dev': ['git-pylint-commit-hook',
            'git-pep8-commit-hook'],
    'feedgen': ['feedgen']
}

# Extensions

SYN_EXT_DIR = os.path.join(SOURCE_DIR, 'hotdoc', 'extensions',
                           'syntax_highlighting')
require_clean_submodules(SYN_EXT_DIR, ['prism'])

ext_modules = [CMARK_MODULE, SEARCH_MODULE]

PACKAGE_DATA = {
    'hotdoc.core': ['templates/*', 'assets/*'],
    'hotdoc': [os.path.join(THEME_REL_DIR, 'templates', '*'),
               os.path.join(THEME_REL_DIR, 'js', '*'),
               os.path.join(THEME_REL_DIR, 'js', 'search', '*'),
               os.path.join(THEME_REL_DIR, 'css', '*'),
               os.path.join(THEME_REL_DIR, 'images', '*'),
               os.path.join(THEME_REL_DIR, 'fonts', '*'),
               os.path.join(THEME_REL_DIR, 'theme.json'),
               'VERSION.txt'],
    'hotdoc.utils': ['hotdoc.m4', 'hotdoc.mk'],
    'hotdoc.extensions.syntax_highlighting': [
        'prism/components/*',
        'prism/themes/*',
        'prism/plugins/autoloader/prism-autoloader.js',
        'prism/plugins/keep-markup/prism-keep-markup.js',
        'prism_autoloader_path_override.js'],
    'hotdoc.extensions.search': [
        '*.js',
        'stopwords.txt'],
    'hotdoc.extensions.devhelp': [
        'devhelp.css'],
    'hotdoc.extensions.license': [
        'data/*',
        'html_templates/*'],
    'hotdoc.extensions.comment_on_github': [
        'scripts/github-comment-loader.js',
        'templates/*']
}

build_c_extension = os.environ.get('HOTDOC_BUILD_C_EXTENSION', 'auto')


class FlexExtension (Extension):
    def __init__(self, flex_sources, *args, **kwargs):
        Extension.__init__(self, *args, **kwargs)
        self.__flex_sources = [src(s) for s in flex_sources]

    def __build_flex(self):
        src_dir = os.path.dirname(self.__flex_sources[0])
        built_scanner_path = src(os.path.join(src_dir, 'scanner.c'))

        self.sources.append(built_scanner_path)
        if newer_group(self.__flex_sources, built_scanner_path):
            cmd = ['flex', '-o', built_scanner_path]
            for s in self.__flex_sources:
                cmd.append(s)
            spawn.spawn(cmd, verbose=1)

    def build_custom(self):
        if self.__flex_sources:
            self.__build_flex()


if build_c_extension not in ('enabled', 'disabled', 'auto'):
    print(
        'HOTDOC_BUILD_C_EXTENSION environment variable must be one of [enabled, disabled, auto]')
    sys.exit(1)


def check_c_extension():
    if spawn.find_executable('flex') is None:
        print('Flex not installed on your system')
        return False

    return True


if build_c_extension != 'disabled':
    if not check_c_extension():
        if build_c_extension == 'enabled':
            print('Requirements for C extension not met')
            sys.exit(1)
        print('Not enabling C extension')
    else:
        print('Enabling C extension')
        ext_modules += [FlexExtension(
            ['hotdoc/parsers/c_comment_scanner/scanner.l'],
            'hotdoc.parsers.c_comment_scanner.c_comment_scanner',
            sources=['hotdoc/parsers/c_comment_scanner/scannermodule.c'],
            depends=['hotdoc/parsers/c_comment_scanner/scanner.l',
                     'hotdoc/parsers/c_comment_scanner/scanner.h'])]
        INSTALL_REQUIRES += [
            'pkgconfig',
            'networkx>=2.5'
        ]
        PACKAGE_DATA['hotdoc.extensions.gi'] = ['html_templates/*']
        PACKAGE_DATA['hotdoc.extensions.gi.transition_scripts'] = [
            'translate_sections.sh']


setup(
    name='hotdoc',
    version=VERSION,
    description='A documentation tool micro-framework',
    keywords='documentation',
    url='https://github.com/hotdoc/hotdoc',
    author='Mathieu Duponchelle',
    author_email='mathieu.duponchelle@opencreed.com',
    license='LGPLv2.1+',
    packages=find_packages(),
    ext_modules=ext_modules,

    cmdclass={'build': CustomBuild,
              'build_ext': CustomBuildExt,
              'sdist': CustomSDist,
              'bdist_egg': CustomBDistEgg,
              'develop': CustomDevelop,
              'test': DiscoverTest,
              'build_default_theme': BuildDefaultTheme},
    package_data=PACKAGE_DATA,
    install_requires=INSTALL_REQUIRES,
    extras_require=EXTRAS_REQUIRE,
    entry_points={
        'hotdoc.extensions': ('get_extension_classes = '
                              'hotdoc.extensions:get_extension_classes'),
        'hotdoc.extensions.gi.languages':  ('get_language_classes = '
                                            'hotdoc.extensions.gi.languages:get_language_classes'),
        'console_scripts': [
            'hotdoc=hotdoc.run_hotdoc:main',
            'hotdoc_dep_printer=hotdoc.hotdoc_dep_printer:main']},
    classifiers=[
        "Programming Language :: Python :: 3"])
