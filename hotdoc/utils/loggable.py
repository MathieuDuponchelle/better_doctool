"""
Banana banana
"""
import re
import sys
from collections import defaultdict

from hotdoc.utils.configurable import Configurable


# pylint: disable=too-few-public-methods
class TerminalController(object):
    """
    Banana banana
    """
    # Cursor movement:
    BOL = ''             # : Move the cursor to the beginning of the line
    # pylint: disable=invalid-name
    UP = ''              # : Move the cursor up one line
    DOWN = ''            # : Move the cursor down one line
    LEFT = ''            # : Move the cursor left one char
    RIGHT = ''           # : Move the cursor right one char

    # Deletion:
    CLEAR_SCREEN = ''    # : Clear the screen and move to home position
    CLEAR_EOL = ''       # : Clear to the end of the line.
    CLEAR_BOL = ''       # : Clear to the beginning of the line.
    CLEAR_EOS = ''       # : Clear to the end of the screen

    # Output modes:
    BOLD = ''            # : Turn on bold mode
    BLINK = ''           # : Turn on blink mode
    DIM = ''             # : Turn on half-bright mode
    REVERSE = ''         # : Turn on reverse-video mode
    NORMAL = ''          # : Turn off all modes

    # Cursor display:
    HIDE_CURSOR = ''     # : Make the cursor invisible
    SHOW_CURSOR = ''     # : Make the cursor visible

    # Terminal size:
    COLS = None          # : Width of the terminal (None for unknown)
    LINES = None         # : Height of the terminal (None for unknown)

    # Foreground colors:
    BLACK = BLUE = GREEN = CYAN = RED = MAGENTA = YELLOW = WHITE = ''

    # Background colors:
    BG_BLACK = BG_BLUE = BG_GREEN = BG_CYAN = ''
    BG_RED = BG_MAGENTA = BG_YELLOW = BG_WHITE = ''

    _STRING_CAPABILITIES = """
    BOL=cr UP=cuu1 DOWN=cud1 LEFT=cub1 RIGHT=cuf1
    CLEAR_SCREEN=clear CLEAR_EOL=el CLEAR_BOL=el1 CLEAR_EOS=ed BOLD=bold
    BLINK=blink DIM=dim REVERSE=rev UNDERLINE=smul NORMAL=sgr0
    HIDE_CURSOR=cinvis SHOW_CURSOR=cnorm""".split()
    _COLORS = """BLACK BLUE GREEN CYAN RED MAGENTA YELLOW WHITE""".split()
    _ANSICOLORS = "BLACK RED GREEN YELLOW BLUE MAGENTA CYAN WHITE".split()

    def __init__(self, term_stream=sys.stdout):
        # Curses isn't available on all platforms
        try:
            import curses
        except ImportError:
            return

        # If the stream isn't a tty, then assume it has no capabilities.
        if not term_stream.isatty():
            return

        # Check the terminal type.  If we fail, then assume that the
        # terminal has no capabilities.
        try:
            curses.setupterm()
        # pylint: disable=bare-except
        except:
            return

        # Look up numeric capabilities.
        TerminalController.COLS = curses.tigetnum('cols')
        TerminalController.LINES = curses.tigetnum('lines')

        # Look up string capabilities.
        for capability in self._STRING_CAPABILITIES:
            (attrib, cap_name) = capability.split('=')
            setattr(self, attrib, self._tigetstr(cap_name) or b'')

        # Colors
        set_fg = self._tigetstr('setf')
        if set_fg:
            for i, color in zip(list(range(len(self._COLORS))), self._COLORS):
                setattr(self, color, curses.tparm(set_fg, i) or b'')
        set_fg_ansi = self._tigetstr('setaf')
        if set_fg_ansi:
            for i, color in zip(list(range(len(self._ANSICOLORS))),
                                self._ANSICOLORS):
                setattr(self, color, curses.tparm(set_fg_ansi, i) or b'')
        set_bg = self._tigetstr('setb')
        if set_bg:
            for i, color in zip(list(range(len(self._COLORS))), self._COLORS):
                setattr(self, 'BG_' + color, curses.tparm(set_bg, i) or b'')
        set_bg_ansi = self._tigetstr('setab')
        if set_bg_ansi:
            for i, color in zip(list(range(len(self._ANSICOLORS))),
                                self._ANSICOLORS):
                setattr(
                    self, 'BG_' + color, curses.tparm(set_bg_ansi, i) or b'')

    # pylint: disable=no-self-use
    def _tigetstr(self, cap_name):
        import curses
        cap = curses.tigetstr(cap_name) or b''
        return re.sub(r'\$<\d+>[/*]?', '', cap.decode()).encode()


(INFO,
 WARNING,
 ERROR) = range(3)


class Logger(Configurable):

    """Subclasses can inherit from this class to report recoverable errors."""

    _error_code_to_exception = defaultdict()
    _domain_codes = defaultdict(set)
    _warning_code_to_exception = defaultdict()
    journal = []
    fatal_warnings = False
    _ignored_codes = set()
    _ignored_domains = set()
    extra_log_data = None
    _last_checkpoint = 0
    _verbose = False

    @staticmethod
    def register_error_code(code, exception_type, domain='core'):
        """Register a new error code"""
        Logger._error_code_to_exception[code] = (exception_type, domain)
        Logger._domain_codes[domain].add(code)

    @staticmethod
    def register_warning_code(code, exception_type, domain='core'):
        """Register a new warning code"""
        Logger._warning_code_to_exception[code] = (exception_type, domain)
        Logger._domain_codes[domain].add(code)

    @staticmethod
    def _log(code, message, level, domain):
        """Call this to add an entry in the journal"""
        Logger.journal.append(
            (Logger.extra_log_data, level, domain, code, message))

    @staticmethod
    def error(code, message):
        """Call this to raise an exception and have it stored in the journal"""
        assert code in Logger._error_code_to_exception
        exc_type, domain = Logger._error_code_to_exception[code]
        Logger._log(code, message, ERROR, domain)
        raise exc_type(message)

    @staticmethod
    def warn(code, message):
        """
        Call this to store a warning in the journal.

        Will raise if `Logger.fatal_warnings` is set to True.
        """

        if code in Logger._ignored_codes:
            return

        assert code in Logger._warning_code_to_exception
        exc_type, domain = Logger._warning_code_to_exception[code]

        if domain in Logger._ignored_domains:
            return

        level = WARNING
        if Logger.fatal_warnings:
            level = ERROR

        Logger._log(code, message, level, domain)

        if Logger.fatal_warnings:
            raise exc_type(message)

    @staticmethod
    def info(message, domain):
        """Log simple info"""
        if not Logger._verbose:
            return

        if domain in Logger._ignored_domains:
            return

        Logger._log(None, message, INFO, domain)

    @staticmethod
    def add_ignored_code(code):
        """Add a code to ignore. Errors cannot be ignored."""
        Logger._ignored_codes.add(code)

    @staticmethod
    def add_ignored_domain(code):
        """Add a domain to ignore. Errors cannot be ignored."""
        Logger._ignored_domains.add(code)

    @staticmethod
    def checkpoint():
        """Add a checkpoint"""
        Logger._last_checkpoint = len(Logger.journal)

    @staticmethod
    def since_checkpoint():
        """Get journal since last checkpoint"""
        return Logger.journal[Logger._last_checkpoint:]

    @staticmethod
    def reset():
        """Resets Logger to its initial state"""
        Logger._error_code_to_exception = defaultdict()
        Logger._domain_codes = defaultdict(set)
        Logger._warning_code_to_exception = defaultdict()
        Logger.journal = []
        Logger.fatal_warnings = False
        Logger._ignored_codes = set()
        Logger._ignored_domains = set()
        Logger.extra_log_data = None
        Logger._verbose = False
        Logger._last_checkpoint = 0


def info(message, domain='core'):
    """Shortcut to `Logger.info`"""
    Logger.info(message, domain)
