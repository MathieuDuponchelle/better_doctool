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

# pylint: disable=too-many-lines

"""
Implements standalone markdown files parsing.
"""

import io
import os
import cPickle as pickle
from collections import namedtuple, defaultdict

from hotdoc.core.file_includer import find_md_file
from hotdoc.core.symbols import\
    (Symbol, FunctionSymbol, CallbackSymbol,
     FunctionMacroSymbol, ConstantSymbol, ExportedVariableSymbol,
     StructSymbol, EnumSymbol, AliasSymbol, SignalSymbol, PropertySymbol,
     VFunctionSymbol, ClassSymbol)
from hotdoc.core.links import Link
from hotdoc.parsers import cmark
from hotdoc.utils.utils import OrderedSet
from hotdoc.utils.simple_signals import Signal
from hotdoc.utils.loggable import info, debug


# pylint: disable=too-many-instance-attributes
class Page(object):
    "Banana banana"
    resolving_symbol_signal = Signal()
    formatting_signal = Signal()

    def __init__(self, source_file, ast):
        "Banana banana"
        name = os.path.splitext(os.path.basename(source_file))[0]
        pagename = '%s.html' % name

        self.link = Link(pagename, name, name)
        self.ast = ast
        self.extension_name = None
        self.source_file = source_file
        self.generated = False
        self.output_attrs = None
        self.subpages = OrderedSet()
        self.symbols = []
        self.typed_symbols = {}
        self.is_stale = True
        self.formatted_contents = None
        self.detailed_description = None
        if ast is not None:
            self.symbol_names = OrderedSet(cmark.symbol_names_in_ast(ast))
        else:
            self.symbol_names = OrderedSet()

    def __getstate__(self):
        return {'ast': None,
                'extension_name': self.extension_name,
                'link': self.link,
                'source_file': self.source_file,
                'generated': self.generated,
                'is_stale': False,
                'formatted_contents': None,
                'detailed_description': None,
                'output_attrs': None,
                'symbols': [],
                'typed_symbols': {},
                'subpages': self.subpages,
                'symbol_names': self.symbol_names}

    def resolve_symbols(self, doc_database, link_resolver):
        """
        When this method is called, the page's symbol names are queried
        from `doc_database`, and added to lists of actual symbols, sorted
        by symbol class.
        """
        typed_symbols_list = namedtuple(
            'TypedSymbolsList', ['name', 'symbols'])
        self.typed_symbols[Symbol] = typed_symbols_list('FIXME symbols', [])
        self.typed_symbols[FunctionSymbol] = typed_symbols_list(
            "Functions", [])
        self.typed_symbols[CallbackSymbol] = typed_symbols_list(
            "Callback Functions", [])
        self.typed_symbols[FunctionMacroSymbol] = typed_symbols_list(
            "Function Macros", [])
        self.typed_symbols[ConstantSymbol] = typed_symbols_list(
            "Constants", [])
        self.typed_symbols[ExportedVariableSymbol] = typed_symbols_list(
            "Exported Variables", [])
        self.typed_symbols[StructSymbol] = typed_symbols_list(
            "Data Structures", [])
        self.typed_symbols[EnumSymbol] = typed_symbols_list("Enumerations", [])
        self.typed_symbols[AliasSymbol] = typed_symbols_list("Aliases", [])
        self.typed_symbols[SignalSymbol] = typed_symbols_list("Signals", [])
        self.typed_symbols[PropertySymbol] = typed_symbols_list(
            "Properties", [])
        self.typed_symbols[VFunctionSymbol] = typed_symbols_list(
            "Virtual Methods", [])
        self.typed_symbols[ClassSymbol] = typed_symbols_list("Classes", [])

        new_syms = []
        for sym_name in self.symbol_names:
            sym = doc_database.get_symbol(sym_name)
            self.__query_extra_symbols(sym, new_syms, link_resolver)

        for sym in new_syms:
            self.symbol_names.add(sym.unique_name)

    def format(self, formatter, link_resolver, output):
        """
        Banana banana
        """
        if self.ast:
            self.formatted_contents =\
                cmark.ast_to_html(self.ast, link_resolver)

        self.output_attrs = defaultdict(lambda: defaultdict(dict))
        formatter.prepare_page_attributes(self)
        Page.formatting_signal(self, formatter)
        self.__format_symbols(formatter, link_resolver)
        self.detailed_description =\
            formatter.format_page(self)[0]
        formatter.write_page(self, output)

    # pylint: disable=no-self-use
    def get_title(self):
        """
        Banana banana
        """
        return 'hotdoc'

    def __format_symbols(self, formatter, link_resolver):
        for symbol in self.symbols:
            if symbol is None:
                continue
            debug('Formatting symbol %s in page %s' % (
                symbol.unique_name, self.source_file), 'formatting')
            symbol.skip = not formatter.format_symbol(symbol, link_resolver)

    def __query_extra_symbols(self, sym, new_syms, link_resolver):
        if sym:
            new_symbols = sum(Page.resolving_symbol_signal(self, sym),
                              [])

            self.__resolve_symbol(sym, link_resolver)

            for symbol in new_symbols:
                new_syms.append(symbol)
                self.__query_extra_symbols(symbol, new_syms, link_resolver)

    def __resolve_symbol(self, symbol, link_resolver):
        symbol.resolve_links(link_resolver)

        symbol.link.ref = "%s#%s" % (self.link.ref, symbol.unique_name)

        for link in symbol.get_extra_links():
            link.ref = "%s#%s" % (self.link.ref, link.id_)

        tsl = self.typed_symbols[type(symbol)]
        tsl.symbols.append(symbol)
        self.symbols.append(symbol)

        debug('Resolved symbol %s to page %s' %
              (symbol.display_name, self.link.ref), 'resolution')


# pylint: disable=too-many-instance-attributes
class DocTree(object):
    "Banana banana"
    resolve_placeholder_signal = Signal(optimized=True)
    update_signal = Signal()

    def __init__(self, private_folder, include_paths):
        "Banana banana"
        self.__include_paths = include_paths
        self.__priv_dir = private_folder

        try:
            self.__all_pages = self.__load_private('pages.p')
            self.__incremental = True
        except IOError:
            self.__all_pages = {}

        self.__placeholders = {}
        self.__root = None
        self.__dep_map = self.__create_dep_map()

    def __create_dep_map(self):
        dep_map = {}
        for pagename, page in self.__all_pages.items():
            for sym_name in page.symbol_names:
                dep_map[sym_name] = pagename
        return dep_map

    def __load_private(self, name):
        path = os.path.join(self.__priv_dir, name)
        return pickle.load(open(path, 'rb'))

    def __save_private(self, obj, name):
        path = os.path.join(self.__priv_dir, name)
        pickle.dump(obj, open(path, 'wb'))

    # pylint: disable=no-self-use
    def __parse_page(self, source_file):
        with io.open(source_file, 'r', encoding='utf-8') as _:
            contents = _.read()

        ast = cmark.hotdoc_to_ast(contents, None)
        return Page(source_file, ast)

    # pylint: disable=too-many-locals
    # pylint: disable=too-many-branches
    def __parse_pages(self, change_tracker, sitemap):
        source_files = []
        source_map = {}

        for fname in sitemap.get_all_sources().keys():
            resolved = self.resolve_placeholder_signal(
                self, fname, self.__include_paths)
            if resolved is None:
                source_file = find_md_file(fname, self.__include_paths)
                source_files.append(source_file)
                source_map[source_file] = fname
            else:
                resolved, ext_name = resolved
                if ext_name:
                    self.__placeholders[fname] = ext_name
                if resolved is not True:
                    source_files.append(resolved)
                    source_map[resolved] = fname
                else:
                    if fname not in self.__all_pages:
                        page = Page(fname, None)
                        page.generated = True
                        self.__all_pages[fname] = page

        stale, unlisted = change_tracker.get_stale_files(
            source_files, 'user-pages')

        old_user_symbols = set()
        new_user_symbols = set()

        for source_file in stale:
            pagename = source_map[source_file]

            prev_page = self.__all_pages.get(pagename)
            if prev_page:
                old_user_symbols |= prev_page.symbol_names

            page = self.__parse_page(source_file)
            new_user_symbols |= page.symbol_names

            newly_listed_symbols = page.symbol_names
            if prev_page:
                newly_listed_symbols -= prev_page.symbol_names

            self.stale_symbol_pages(newly_listed_symbols, page)

            self.__all_pages[pagename] = page

        unlisted_pagenames = set()

        for source_file in unlisted:
            prev_page = None
            rel_path = None

            for ipath in self.__include_paths:
                rel_path = os.path.relpath(source_file, ipath)
                prev_page = self.__all_pages.get(rel_path)
                if prev_page:
                    break

            if not prev_page:
                continue

            old_user_symbols |= prev_page.symbol_names
            self.__all_pages.pop(rel_path)
            unlisted_pagenames.add(rel_path)

        for source_file in source_files:
            page = self.__all_pages[source_map[source_file]]
            page.subpages |= sitemap.get_subpages(source_map[source_file])
            page.subpages -= unlisted_pagenames

        return old_user_symbols - new_user_symbols

    def __update_sitemap(self, sitemap):
        # We need a mutable variable
        level_and_name = [-1, 'core']

        def _update_sitemap(name, _, level):
            if name in self.__placeholders:
                level_and_name[1] = self.__placeholders[name]
                level_and_name[0] = level
            elif level == level_and_name[0]:
                level_and_name[1] = 'core'
                level_and_name[0] = -1

            page = self.__all_pages.get(name)
            page.extension_name = level_and_name[1]

        sitemap.walk(_update_sitemap)

    # pylint: disable=no-self-use
    def __setup_folder(self, folder):
        if not os.path.exists(folder):
            os.mkdir(folder)

    def __create_navigation_script(self, output, extensions):
        # Wrapping this is in a javascript file to allow
        # circumventing stupid chrome same origin policy
        formatter = extensions['core'].get_formatter('html')
        site_navigation = formatter.format_site_navigation(self.__root, self)

        if not site_navigation:
            return

        output = os.path.join(output, formatter.get_output_folder())

        with open(os.path.join(output, 'site_navigation.html'), 'w') as _:
            _.write(site_navigation)

        path = os.path.join(output,
                            'assets',
                            'js',
                            'site_navigation.js')
        site_navigation = site_navigation.replace('\n', '')
        site_navigation = site_navigation.replace('"', '\\"')
        js_wrapper = 'site_navigation_downloaded_cb("'
        js_wrapper += site_navigation
        js_wrapper += '");'
        with open(path, 'w') as _:
            _.write(js_wrapper.encode('utf-8'))

    def walk(self, parent=None):
        """Generator that yields pages in infix order

        Args:
            parent: hotdoc.core.doc_tree.Page, optional, the page to start
                traversal from. If None, defaults to the root of the doc_tree.

        Yields:
            hotdoc.core.doc_tree.Page: the next page
        """
        if parent is None:
            yield self.__root
            parent = self.__root

        for cpage_name in parent.subpages:
            cpage = self.__all_pages[cpage_name]
            yield cpage
            for page in self.walk(parent=cpage):
                yield page

    def add_page(self, parent, page):
        """
        Banana banana
        """
        self.__all_pages[page.source_file] = page
        parent.subpages.add(page.source_file)

    def stale_symbol_pages(self, symbols, new_page=None):
        """
        Banana banana
        """
        for sym in symbols:
            pagename = self.__dep_map.get(sym)
            page = self.__all_pages.get(pagename)
            if page:
                page.is_stale = True
                if new_page and new_page.source_file != page.source_file:
                    page.symbol_names.remove(sym)

    def parse_sitemap(self, change_tracker, sitemap):
        """
        Banana banana
        """
        unlisted_symbols = self.__parse_pages(change_tracker, sitemap)
        self.__root = self.__all_pages[sitemap.index_file]
        self.__update_sitemap(sitemap)
        self.update_signal(self, unlisted_symbols)

    def get_stale_pages(self):
        """
        Banana banana
        """
        stale = {}
        for pagename, page in self.__all_pages.items():
            if page.is_stale:
                stale[pagename] = page
        return stale

    def get_pages(self):
        """
        Banana banana
        """
        return self.__all_pages

    def get_pages_for_symbol(self, unique_name):
        """
        Banana banana
        """
        pagename = self.__dep_map.get(unique_name)
        if pagename is None:
            return {}
        page = self.__all_pages.get(pagename)
        if page is None:
            return {}

        return {pagename: page}

    def resolve_symbols(self, doc_database, link_resolver, page=None):
        """Will call resolve_symbols on all the stale subpages of the tree.
        Args:
          page: hotdoc.core.doc_tree.Page, the page to resolve symbols in,
          will recurse on potential subpages.
        """

        page = page or self.__root

        if page.is_stale:
            if page.ast is None and not page.generated:
                with open(page.source_file, 'r') as _:
                    page.ast = cmark.hotdoc_to_ast(_.read(), None)

            page.resolve_symbols(doc_database, link_resolver)

        for pagename in page.subpages:
            cpage = self.__all_pages[pagename]
            self.resolve_symbols(doc_database, link_resolver, page=cpage)

    def format(self, link_resolver, output, extensions):
        """Banana banana
        """
        info('Formatting documentation tree', 'formatting')
        self.__setup_folder(output)

        # Page.formatting_signal.connect(self.__formatting_page_cb)
        # Link.resolving_link_signal.connect(self.__link_referenced_cb)

        for page in self.walk():
            info('formatting %s' % page.source_file, 'formatting')
            extension = extensions[page.extension_name]
            extension.format_page(page, link_resolver, output)

        self.__create_navigation_script(output, extensions)

    def persist(self):
        """
        Banana banana
        """
        self.__save_private(self.__all_pages, 'pages.p')
