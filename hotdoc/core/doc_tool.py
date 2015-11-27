import os, sys, argparse

reload(sys)  
sys.setdefaultencoding('utf8')

import cPickle as pickle
import glob
import json

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, mapper

from .naive_index import NaiveIndexFormatter
from .links import LinkResolver
from .symbols import *
from .base_extension import BaseExtension
from .alchemy_integration import Base
from .doc_tree import DocTree
from .wizard import QuickStartWizard, QUICKSTART_HELP, Skip, QuickStartArgument
from .comment_block import Tag, Comment

from ..utils.utils import all_subclasses
from ..utils.simple_signals import Signal
from ..utils.loggable import Loggable, TerminalController
from ..utils.loggable import init as loggable_init
from ..formatters.html.html_formatter import HtmlFormatter
from ..transition_scripts.patcher import GitInterface

from hotdoc.extensions.gi_raw_parser import GtkDocRawCommentParser

class ConfigError(Exception):
    pass

class ChangeTracker(object):
    def __init__(self):
        self.exts_mtimes = {}

    def update_extension_sources_mtimes(self, extension):
        ext_mtimes = {}
        source_files = extension.get_source_files()
        for source_file in source_files:
            mtime = os.path.getmtime(source_file)
            ext_mtimes[source_file] = mtime

        self.exts_mtimes[extension.EXTENSION_NAME] = ext_mtimes

    def mark_extension_stale_sources (self, extension):
        stale = []
        source_files = extension.get_source_files()

        if extension.EXTENSION_NAME in self.exts_mtimes:
            prev_mtimes = self.exts_mtimes[extension.EXTENSION_NAME]
        else:
            prev_mtimes = {}

        for source_file in source_files:
            if not source_file in prev_mtimes:
                stale.append(source_file)
            else:
                prev_mtime = prev_mtimes.get(source_file)
                mtime = os.path.getmtime(source_file)
                if prev_mtime != mtime:
                    stale.append(source_file)

        extension.set_stale_source_files(stale)

HOTDOC_ASCII =\
"""/**    __  __   ____     ______   ____     ____     ______
 *    / / / /  / __ \   /_  __/  / __ \   / __ \   / ____/
 *   / /_/ /  / / / /    / /    / / / /  / / / /  / /     
 *  / __  /  / /_/ /    / /    / /_/ /  / /_/ /  / /___   
 * /_/ /_/   \____/    /_/    /_____/   \____/   \____/   
 *
 * The Tastiest Documentation Tool.
 */                                                      
"""

PROMPT_GIT_REPO=\
"""
If you use git, I can commit the files created or
modified during setup, you will be prompted for confirmation
when that is the case.

The author name and mail address will be 'hotdoc' and
'hotdoc@hotdoc.net'.

Note: here as everywhere else, you can answer None to
skip the question.
"""

def validate_git_repo(wizard, path):
    try:
        git_interface = GitInterface(path)
        return True
    except Exception as e:
        print "This does not look like a git repo : %s" % path
        return False

PROMPT_ROOT_INDEX=\
"""
I can now create a root index to tie all your sub indexes
together, do you wish me to do that [y,n]? """

class HotdocWizard(QuickStartWizard):
    def __init__(self, *args, **kwargs):
        QuickStartWizard.__init__(self, *args, **kwargs)
        if self.parent == self:
            self.comments = {}
            self.symbols = {}
            self.tc = TerminalController()
            self.git_interface = GitInterface()
            self.config = {}
        else:
            self.comments = self.parent.comments
            self.symbols = self.parent.symbols
            self.tc = self.parent.tc
            self.git_interface = self.parent.git_interface

        self.tag_validators = {}

    def add_comment(self, comment):
        self.comments[comment.name] = comment

    def get_comment(self, name):
        return self.comments.get(name)

    def get_or_create_symbol(self, type_, **kwargs):
        unique_name = kwargs.get('unique_name')
        if not unique_name:
            unique_name = kwargs.get('display_name')
            kwargs['unique_name'] = unique_name

        filename = kwargs.get('filename')
        if filename:
            kwargs['filename'] = os.path.abspath(filename)

        symbol = type_()

        for key, value in kwargs.items():
            setattr(symbol, key, value)

        self.symbols[unique_name] = symbol

        return symbol

    def before_prompt(self):
        self.__clear_screen()

    def get_index_path(self):
        return None

    def get_index_name(self):
        return None

    def __create_root_index(self):
        contents = 'Welcome to our documentation!\n'

        for obj in self._qs_objects:
            if isinstance(obj, HotdocWizard):
                index_path = obj.get_index_path()
                index_name = obj.get_index_name()
                if index_path:
                    contents += '\n#### [%s](%s)\n' % (index_name, index_path)

        path = self.prompt_key('index_path',
                prompt='Path to save the created index in',
                store=False, validate_function=QuickStartWizard.validate_folder)

        path = os.path.join(path, 'index.markdown')

        with open (path, 'w') as f:
            f.write(contents)

        self.config['index'] = path

    def before_quick_start(self, obj):
        if type(obj) == QuickStartArgument and obj.argument.dest == 'index':
            if self.config.get('index'):
                return

            self.before_prompt() 
            if (self.ask_confirmation(PROMPT_ROOT_INDEX)):
                self.__create_root_index()
                raise Skip

    def main_prompt(self):
        prompt = self.tc.BOLD + "\nHotdoc started without arguments, starting setup\n" + self.tc.NORMAL
        prompt += self.tc.CYAN + QUICKSTART_HELP + self.tc.NORMAL

        prompt += '\nPress Enter to start setup '
        if not self.wait_for_continue(prompt):
            return False

        try:
            repo_path = self.prompt_key('git_repo', prompt=">>> Path to the git repo ? ",
                    title="the path to the root of the git repository",
                    extra_prompt=PROMPT_GIT_REPO,
                    validate_function=validate_git_repo)
            self.git_interface.set_repo_path(repo_path)
        except Skip:
            pass

        return True

    def __clear_screen(self):
        sys.stdout.write(self.tc.CLEAR_SCREEN)
        sys.stdout.write(self.tc.RED + self.tc.BOLD + HOTDOC_ASCII +
                self.tc.NORMAL)

    def _add_argument_override(self, group, *args, **kwargs):
        set_default = kwargs.get('default')
        kwargs['default'] = argparse.SUPPRESS
        res = QuickStartWizard._add_argument_override(self, group, *args, **kwargs)

        if set_default:
            self.config[res.dest] = set_default

        return res

SUBCOMMAND_DESCRIPTION="""
Valid subcommands.

Exactly one subcommand is required.
Run hotdoc {subcommand} -h for more info
"""

class DocTool(Loggable):
    def __init__(self):
        Loggable.__init__(self)

        self.session = None
        self.output = None
        self.index_file = None
        self.doc_parser = None
        self.__extension_classes = {}
        self.extensions = {}
        self.__comments = {}
        self.__symbols = {}
        self.tag_validators = {}
        self.raw_comment_parser = GtkDocRawCommentParser(self)
        self.link_resolver = LinkResolver(self)
        self.incremental = False
        self.comment_updated_signal = Signal()
        self.symbol_updated_signal = Signal()

    def get_symbol(self, name, prefer_class=False):
        sym = self.__symbols.get(name)
        if not sym:
            sym = self.session.query(Symbol).filter(Symbol.unique_name ==
                    name).first()

        if sym:
            # Faster look up next time around
            self.__symbols[name] = sym
            sym.resolve_links(self.link_resolver)
        return sym

    def __update_symbol_comment(self, comment):
        self.session.query(Symbol).filter(Symbol.unique_name ==
                comment.name).update({'comment': comment})
        esym = self.__symbols.get(comment.name)
        if esym:
            esym.comment = comment
        self.comment_updated_signal(comment)

    def register_tag_validator(self, validator):
        self.tag_validators[validator.name] = validator

    def format_symbol(self, symbol_name):
        # FIXME this will be API, raise meaningful errors
        pages = self.doc_tree.symbol_maps.get(symbol_name)
        if not pages:
            return None

        page = pages.values()[0]

        if page.extension_name is None:
            self.formatter = HtmlFormatter(self, [])
        else:
            self.formatter = self.get_formatter(page.extension_name)

        sym = self.get_symbol(symbol_name)
        if not sym:
            return None

        self.update_doc_parser(page.extension_name)

        self.formatter.format_symbol(sym) 

        return sym.detailed_description

    def get_or_create_symbol(self, type_, **kwargs):
        unique_name = kwargs.get('unique_name')
        if not unique_name:
            unique_name = kwargs.get('display_name')
            kwargs['unique_name'] = unique_name

        filename = kwargs.get('filename')
        if filename:
            kwargs['filename'] = os.path.abspath(filename)

        symbol = self.session.query(type_).filter(type_.unique_name == unique_name).first()

        if not symbol:
            symbol = type_()
            self.session.add(symbol)

        for key, value in kwargs.items():
            setattr(symbol, key, value)

        if not symbol.comment:
            symbol.comment = Comment(symbol.unique_name)
            self.add_comment(symbol.comment)

        symbol.resolve_links(self.link_resolver)

        if self.incremental:
            self.symbol_updated_signal(symbol)

        self.__symbols[unique_name] = symbol

        return symbol

    def __setup_database(self):
        if self.session is not None:
            return

        db_path = os.path.join(self.get_private_folder(), 'hotdoc.db')
        self.engine = create_engine('sqlite:///%s' % db_path)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self.session.autoflush = False
        Base.metadata.create_all(self.engine)

    def __create_change_tracker(self):
        try:
            self.change_tracker = pickle.load(open(os.path.join(self.get_private_folder(),
                'change_tracker.p'), 'rb'))
            self.incremental = True
        except IOError:
            self.change_tracker = ChangeTracker()

    def get_formatter(self, extension_name):
        ext = self.extensions.get(extension_name)
        if ext:
            return ext.get_formatter(self.output_format)
        return None

    def update_doc_parser(self, extension_name):
        ext = self.extensions.get(extension_name)
        self.doc_parser = None
        if ext:
            self.doc_parser = ext.get_doc_parser()

    def setup(self, args):
        from datetime import datetime

        n = datetime.now()
        self.__setup(args)

        print "core setup takes", datetime.now() - n

        for extension in self.extensions.values():
            n = datetime.now()
            self.change_tracker.mark_extension_stale_sources(extension)
            extension.setup ()
            self.change_tracker.update_extension_sources_mtimes(extension)
            self.session.flush()
            print "extension", extension.EXTENSION_NAME, 'takes', datetime.now() - n

        n = datetime.now()
        self.doc_tree.resolve_symbols(self)
        print "symbol resolution takes", datetime.now() - n

        n = datetime.now()
        self.session.flush()
        print "flushing takes", datetime.now() - n

    def format (self):
        from datetime import datetime

        n = datetime.now()
        self.__setup_folder(self.output)
        self.formatter = HtmlFormatter(self, [])
        self.formatter.format(self.doc_tree.root)
        print "formatting takes", datetime.now() - n

    def add_comment(self, comment):
        self.__comments[comment.name] = comment
        for validator in self.tag_validators.values():
            if validator.default and not validator.name in comment.tags:
                comment.tags[validator.name] = Tag(name=validator.name,
                        description=validator.default)
        if self.incremental:
            self.__update_symbol_comment (comment)

    def get_comment (self, name):
        comment = self.__comments.get(name)
        if not comment:
            esym = self.get_symbol(name)
            if esym:
                comment = esym.comment
        return comment

    def __setup (self, args):
        if os.name == 'nt':
            self.datadir = os.path.join(os.path.dirname(__file__), '..', 'share')
        else:
            self.datadir = "/usr/share"

        self.parser = \
                argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,)

        subparsers = self.parser.add_subparsers(title='commands', dest='cmd',
                description=SUBCOMMAND_DESCRIPTION)
        run_parser = subparsers.add_parser('run', help='run hotdoc')
        run_parser.add_argument('--conf-file', help='Path to the config file',
                dest='conf_file', default='hotdoc.json')

        conf_parser = subparsers.add_parser('conf', help='configure hotdoc')
        conf_parser.add_argument('--quickstart', help='run a quickstart wizard',
                action='store_true')
        conf_parser.add_argument('--conf-file', help='Path to the config file',
                dest='conf_file', default='hotdoc.json')

        wizard = HotdocWizard(self.parser)

        extension_subclasses = all_subclasses (BaseExtension)

        for subclass in extension_subclasses:
            subclass.add_arguments (self.parser)
            self.__extension_classes[subclass.EXTENSION_NAME] = subclass

        self.parser.add_argument ("-i", "--index", action="store",
                dest="index", help="location of the index file")
        self.parser.add_argument ("-o", "--output", action="store",
                dest="output", help="where to output the rendered documentation")
        self.parser.add_argument ("--output-format", action="store",
                dest="output_format", help="format for the output")
        self.parser.add_argument ("-I", "--include-path", action="append",
                dest="include_paths", help="markdown include paths")
        self.parser.add_argument ("--html-theme", action="store",
                dest="html_theme", help="html theme to use")
        self.parser.add_argument ("-", action="store_true", no_prompt=True,
                help="Separator to allow finishing a list of arguments before a command",
                dest="whatever")

        loggable_init("DOC_DEBUG")

        args = self.parser.parse_args(args)
        conf_file = args.conf_file
        self.load_config(args, conf_file, wizard)

        exit_now = False

        if args.cmd == 'run':
            self.parse_config(wizard.config)
        elif args.cmd == 'conf':
            if args.quickstart == True:
                exit_now = True
                if wizard.quick_start():
                    print "Setup complete, building the documentation now"
                    if wizard.wait_for_continue("Setup complete, press Enter to build the doc now "):
                        self.parse_config(wizard.config)
                        exit_now = False

        with open(conf_file, 'w') as f:
            f.write(json.dumps(wizard.config, indent=4))

        if exit_now:
            sys.exit(0)

    def load_config(self, args, conf_file, wizard):
        try:
            with open(conf_file, 'r') as f:
                contents = f.read()
        except IOError:
            contents = '{}'

        try:
            config = json.loads(contents)
        except ValueError:
            config = {}

        wizard.config.update(config)
        cli = dict(vars(args))
        cli.pop('cmd', None)
        cli.pop('quickstart', None)
        cli.pop('conf_file', None)

        wizard.config.update(cli)

    def __setup_folder(self, folder):
        if os.path.exists (folder):
            if not os.path.isdir (folder):
                self.error ("Folder %s exists but is not a directory", folder)
                raise ConfigError ()
        else:
            os.mkdir (folder)

    def __create_extensions (self, args):
        for ext_class in self.__extension_classes.values():
            ext = ext_class(self, args)
            self.extensions[ext.EXTENSION_NAME] = ext

    def get_private_folder(self):
        return os.path.abspath('hotdoc-private')

    def parse_config (self, config):
        module_path = os.path.dirname(__file__)
        default_theme_path = os.path.join(module_path, '..', 'default_theme')
        default_theme_path = os.path.abspath(default_theme_path)

        self.output = config.get('output')
        self.output_format = config.get('output_format')
        self.include_paths = config.get('include_paths')
        self.html_theme_path = config.get('html_theme', default_theme_path)

        if self.output_format not in ["html"]:
            raise ConfigError ("Unsupported output format : %s" %
                    self.output_format)

        self.__setup_folder('hotdoc-private')

        # FIXME: we might actually want not to be naive
        #if not config.index:
        #    nif = NaiveIndexFormatter (self.c_source_scanner.symbols)
        #    config.index = "tmp_markdown_files/tmp_index.markdown"

        self.index_file = config.get('index')

        prefix = os.path.dirname(self.index_file)
        self.doc_tree = DocTree(self, prefix)

        self.__create_extensions (config)

        self.doc_tree.build_tree(self.index_file)
        self.doc_tree.fill_symbol_maps()

        self.__create_change_tracker()
        self.__setup_database()

    def persist(self):
        self.session.commit()
        pickle.dump(self.change_tracker, open(os.path.join(self.get_private_folder(),
            'change_tracker.p'), 'wb'))
        #pickle.dump(self.args, open(os.path.join(self.get_private_folder(),
        #    'args.p'), 'wb'))
        self.doc_tree.persist()

    def finalize (self):
        self.session.close()
