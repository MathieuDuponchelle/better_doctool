import os
from collections import namedtuple

from hotdoc.parsers.c_comment_scanner.c_comment_scanner import extract_comments

from hotdoc.core.symbols import *
from hotdoc.utils.loggable import debug, error


RawMacro = namedtuple('RawMacro', ['raw', 'filename'])


class CCommentExtractor:
    def __init__(self, extension, comment_parser):
        self.extension = extension
        self.app = extension.app
        self.project = extension.project
        self.__raw_comment_parser = comment_parser
        self.__raw_macros = []

    def parse_comments(self, filenames):
        for filename in filenames:
            with open(filename, 'r', encoding='utf-8') as f:
                debug('Getting comments in %s' % filename)
                lines = []
                header = filename.endswith('.h')
                skip_next_symbol = header
                # FIXME Use the lexer for that!
                for l in f.readlines():
                    lines.append(l)
                    if skip_next_symbol and l.startswith("#pragma once"):
                        skip_next_symbol = False

                cs = extract_comments(''.join(lines))
                for c in cs:
                    if c[3]:
                        line = lines[c[1] - 1]

                        comment = (len(line) - len(line.lstrip(' '))
                                   ) * ' ' + c[0]
                        block = self.__raw_comment_parser.parse_comment(comment,
                                                                        filename, c[1], c[2], self.project.include_paths)
                        if block is not None:
                            self.extension.add_comment(block)
                    elif not skip_next_symbol:
                        if header:
                            self.__raw_macros.append(RawMacro(c, filename))
                            # self.__create_macro_from_raw_text(c, filename, filter_names)
                    else:
                        skip_next_symbol = False

    def create_macro_symbols(self, filter_names=None, filenames=None):
        filenames = filenames or set()
        filter_names = filter_names or {}
        for raw_macro in self.__raw_macros:
            self.__create_macro_from_raw_text(
                raw_macro.raw, raw_macro.filename, filter_names, filenames)

    def __get_comment_filename(self, name, filenames):
        comment = self.app.database.get_comment(name)
        if comment and comment.filename:
            header = '%s.h' % os.path.splitext(comment.filename)[0]
            if header in filenames:
                return header
            elif comment.filename in filenames:
                return comment.filename

        return ""

    def __create_macro_from_raw_text(self, raw, filename, filter_names, filenames):
        mcontent = raw[0].replace('\t', ' ')
        mcontent = mcontent.split(' ', 1)[1]
        split = mcontent.split('(', 1)
        name = split[0]

        if name.strip() in filter_names and not self.app.database.get_comment(name.strip()):
            return None

        # `#define foo (x) ...` is *not* a function macro
        if not (' ' in name or '\t' in name) and len(split) == 2:
            args = split[1].split(')', 1)[0].split(',')
            if args:
                stripped_name = name.strip()
                filename = self.__get_comment_filename(
                    stripped_name, filenames) or filename
                return self.__create_function_macro_symbol(stripped_name,
                                                           filename, raw[1], raw[0])

        name = mcontent.split(' ', 1)[0]
        stripped_name = name.strip()
        filename = self.__get_comment_filename(
            stripped_name, filenames) or filename

        return self.__create_constant_symbol(stripped_name, filename, raw[1], raw[0])

    def __create_function_macro_symbol(self, name, filename, lineno, original_text):
        if name in self.extension.created_symbols:
            return None

        comment = self.app.database.get_comment(name)

        return_value = [None]
        if comment:
            return_tag = comment.tags.get('returns')
            if return_tag:
                return_value = [ReturnItemSymbol()]

        parameters = []

        if comment:
            for param_name in comment.params:
                parameter = ParameterSymbol(argname=param_name)
                parameters.append(parameter)
            if comment.filename:
                filename = '%s.h' % os.path.splitext(comment.filename)[0]

        sym = self.extension.create_symbol(
            FunctionMacroSymbol, return_value=return_value,
            parameters=parameters, original_text=original_text,
            display_name=name, filename=filename, lineno=lineno)

        return sym

    def __create_constant_symbol(self, name, filename, lineno, original_text):
        if name in self.extension.created_symbols:
            return None

        return self.extension.create_symbol(ConstantSymbol,
                                            original_text=original_text,
                                            display_name=name, filename=filename,
                                            lineno=lineno)
