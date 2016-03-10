# -*- coding: utf-8 -*-
#
# Copyright © 2016 Mathieu Duponchelle <mathieu.duponchelle@opencreed.com>
# Copyright © 2016 Collabora Ltd
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

# pylint: disable=missing-docstring
# pylint: disable=invalid-name

import os
import unittest
import shutil

from hotdoc.core.doc_tree import DocTree
from hotdoc.core.symbols import FunctionSymbol
from hotdoc.core.doc_database import DocDatabase
from hotdoc.core.change_tracker import ChangeTracker
from hotdoc.core.base_extension import BaseExtension
from hotdoc.core.comment_block import Comment, Tag
from hotdoc.utils.utils import OrderedSet


def touch(fname, times=None):
    with open(fname, 'a'):
        os.utime(fname, times)


class TestExtension(BaseExtension):
    EXTENSION_NAME = 'test-extension'

    def __init__(self, doc_repo, smart=False):
        self.formatters = {'html': None}
        super(TestExtension, self).__init__(doc_repo)
        doc_repo.doc_tree.page_parser.register_well_known_name(
            'test-api', self.test_index_handler)

        self.sources = ['foo.x', 'bar.x']
        self.smart = smart

    # pylint: disable=unused-argument
    def test_index_handler(self, doc_tree):
        if not self.smart:
            return self.create_naive_index(self.sources)
        else:
            return self.create_naive_index(
                self.sources, user_index='ext-index.markdown')

    def setup(self):
        self.get_or_create_symbol(
            FunctionSymbol, display_name='do_ze_foo', filename='foo.x')

        self.get_or_create_symbol(
            FunctionSymbol, display_name='do_ze_bar', filename='bar.x')

        self.update_naive_index(smart=self.smart)


class TestDocTree(unittest.TestCase):

    def setUp(self):
        here = os.path.dirname(__file__)
        self.__md_dir = os.path.abspath(os.path.join(
            here, 'tmp-markdown-files'))
        self.__priv_dir = os.path.abspath(os.path.join(
            here, 'tmp-private'))
        self.__remove_tmp_dirs()
        os.mkdir(self.__md_dir)
        os.mkdir(self.__priv_dir)
        os.mkdir(self.get_generated_doc_folder())
        self.include_paths = OrderedSet([self.__md_dir])
        self.include_paths.add(self.get_generated_doc_folder())
        self.doc_tree = DocTree(self.include_paths,
                                os.path.join(here, 'tmp-private'))
        # FIXME: this is costly
        self.doc_database = DocDatabase()
        self.doc_database.setup(self.__priv_dir)

        self.change_tracker = ChangeTracker()

    def tearDown(self):
        self.__remove_tmp_dirs()
        self.doc_database.finalize()

    def get_generated_doc_folder(self):
        return os.path.join(self.__priv_dir, 'generated')

    def get_private_folder(self):
        return self.__priv_dir

    def __remove_tmp_dirs(self):
        shutil.rmtree(self.__md_dir, ignore_errors=True)
        shutil.rmtree(self.__priv_dir, ignore_errors=True)
        shutil.rmtree(self.get_generated_doc_folder(), ignore_errors=True)

    def __create_md_file(self, name, contents):
        with open(os.path.join(self.__md_dir, name), 'w') as _:
            _.write(contents)

    def __add_topic_symbol(self, topic, name):
        tags = {'topic': Tag('topic', description='', value=topic)}
        comment = Comment(name=name, tags=tags)
        # FIXME: make this unneeded
        self.doc_database.add_comment(comment)
        return self.doc_database.get_or_create_symbol(
            FunctionSymbol, display_name=name, comment=comment)

    def __persist(self):
        here = os.path.dirname(__file__)
        self.doc_tree.persist()
        self.doc_database.persist()
        self.doc_tree = DocTree([self.__md_dir],
                                os.path.join(here, 'tmp-private'))
        self.doc_database = DocDatabase()
        self.doc_database.setup(self.__priv_dir)

    def test_symbols_topics(self):
        self.__create_md_file('index.markdown',
                              "## Topic based documentation\n"
                              "\n"
                              "### [My topic]()\n")

        index_path = os.path.abspath(
            os.path.join(self.__md_dir, 'index.markdown'))

        root = self.doc_tree.build_tree(index_path)
        self.__add_topic_symbol('My topic', 'foo')
        self.assertSetEqual(set(root.symbol_names), {'foo'})

        # Now test incremental rebuild

        self.__persist()
        root = self.doc_tree.build_tree(index_path)
        self.assertFalse(root.is_stale)
        self.assertSetEqual(set(root.symbol_names), {'foo'})

        self.__persist()
        touch(index_path)
        root = self.doc_tree.build_tree(index_path)
        self.assertTrue(root.is_stale)
        self.assertSetEqual(set(root.symbol_names), {'foo'})

        self.__persist()
        root = self.doc_tree.build_tree(index_path)
        # We simulate staling of the "source file"
        self.__add_topic_symbol('My topic', 'foo')
        self.assertTrue(root.is_stale)
        self.assertSetEqual(set(root.symbol_names), {'foo'})

    def test_naive_index(self):
        self.__create_md_file('index.markdown',
                              "## Generated documentation\n"
                              "\n"
                              "### [Test well known name](test-api)\n")
        extension = TestExtension(self)
        index_path = os.path.abspath(
            os.path.join(self.__md_dir, 'index.markdown'))

        self.doc_tree.build_tree(index_path)

        extension.setup()

        self.assertSetEqual(
            set(self.doc_tree.pages.keys()),
            set((os.path.join(self.get_generated_doc_folder(),
                              'gen-foo.markdown'),
                 os.path.join(self.get_generated_doc_folder(),
                              'gen-bar.markdown'),
                 os.path.join(self.get_generated_doc_folder(),
                              'test-extension-index.markdown'),
                 os.path.join(self.__md_dir,
                              'index.markdown'))))

        bar_page = self.doc_tree.pages[os.path.join(
            self.get_generated_doc_folder(), 'gen-bar.markdown')]

        self.assertSetEqual(set(bar_page.symbol_names),
                            set((u'do_ze_bar',)))

    def test_smart_index(self):
        self.__create_md_file('index.markdown',
                              "## Generated documentation\n"
                              "\n"
                              "### [Test well known name](test-api)\n")
        self.__create_md_file('ext-index.markdown',
                              "## Smart extension index\n")
        self.__create_md_file('bar.markdown',
                              "## Smart symbol list\n")

        extension = TestExtension(self, smart=True)
        index_path = os.path.abspath(
            os.path.join(self.__md_dir, 'index.markdown'))

        self.doc_tree.build_tree(index_path)

        extension.setup()

        gen_index = os.path.join(self.get_generated_doc_folder(),
                                 'test-extension-index.markdown')

        self.assertSetEqual(
            set(self.doc_tree.pages.keys()),
            set((os.path.join(self.get_generated_doc_folder(),
                              'gen-foo.markdown'),
                 os.path.join(self.get_generated_doc_folder(),
                              'gen-bar.markdown'),
                 os.path.join(self.get_generated_doc_folder(),
                              'test-extension-index.markdown'),
                 os.path.join(self.__md_dir,
                              'index.markdown'))))

        with open(gen_index, 'r') as _:
            contents = _.read()

        self.assertEqual(contents,
                         "## Smart extension index\n"
                         "\n"
                         "#### [bar](gen-bar.markdown)\n"
                         "#### [foo](gen-foo.markdown)\n")

        gen_bar_path = os.path.join(
            self.get_generated_doc_folder(), 'gen-bar.markdown')

        bar_page = self.doc_tree.pages[gen_bar_path]

        self.assertSetEqual(set(bar_page.symbol_names),
                            set((u'do_ze_bar',)))

        with open(gen_bar_path, 'r') as _:
            contents = _.read()

        self.assertEqual(contents,
                         "## Smart symbol list\n"
                         "\n"
                         "* [do\\_ze\\_bar]()\n")
