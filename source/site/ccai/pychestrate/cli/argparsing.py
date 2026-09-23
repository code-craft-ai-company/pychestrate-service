"""
.. module:: cli.argparsing
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: An :class:`argparse.ArgumentParser` that writes to the
               invocation's streams and never exits the process.

.. moduleauthor:: Code Craft AI LLC

``pyc`` is callable in-process (tests, embedding), so a parser must
not call :func:`sys.exit` or write to the real ``sys.stdout``. Help
output goes to the context's stdout and raises :class:`ParserExit`
with status 0; a parse error raises :class:`CliUsageError`, which the
dispatcher reports and turns into exit code 2.

Options must be spelled out (no ``--per`` for ``--per-page``), and an
unrecognized option is reported with the closest known ones
("did you mean '--state'?").
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import sys

from typing import Any, List, Optional, TextIO

from ccai.pychestrate.cli import suggestions
from ccai.pychestrate.cli.exceptions import CliUsageError


_UNRECOGNIZED_PREFIX: str = "unrecognized arguments: "


class ParserExit(Exception):
    """
        Raised instead of :func:`sys.exit` when a parser finishes early
        (``--help``).

        :param status: Exit status the parser asked for.
    """

    def __init__(self, status: int) -> None:
        super().__init__("parser exit {}".format(status))
        self.status: int = status
        return


class CliArgumentParser(argparse.ArgumentParser):
    """
        Argument parser bound to explicit output streams.
    """

    def __init__(self, *args: Any, out_stream: TextIO, err_stream: TextIO, **kwargs: Any) -> None:
        kwargs.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)
        self._out_stream: TextIO = out_stream
        self._err_stream: TextIO = err_stream
        return

    def _print_message(self, message: str, file: Optional[TextIO] = None) -> None:
        if not message:
            return
        if file is None or file is sys.stdout:
            self._out_stream.write(message)
        else:
            self._err_stream.write(message)
        return

    def exit(self, status: int = 0, message: Optional[str] = None) -> None:
        if message:
            self._err_stream.write(message)
        raise ParserExit(status)

    def known_option_strings(self) -> List[str]:
        """
            Every listed option spelling of this parser (hidden
            aliases excluded).

            :returns: Option strings.
        """
        known: List[str] = []
        for action in self._actions:
            if action.help == argparse.SUPPRESS:
                continue
            known.extend(action.option_strings)
        rtnval = known
        return rtnval

    def _suggest_for_unrecognized(self, message: str) -> str:
        """
            Add "did you mean" hints to argparse's "unrecognized
            arguments" message.

            :param message: argparse's message.

            :returns: Message (unchanged when nothing is close).
        """
        if not message.startswith(_UNRECOGNIZED_PREFIX):
            return message
        hints: List[str] = []
        for token in message[len(_UNRECOGNIZED_PREFIX):].split():
            if not token.startswith("-"):
                continue
            option = token.split("=", 1)[0]
            hint = suggestions.did_you_mean(word=option, candidates=self.known_option_strings())
            if len(hint) > 0:
                hints.append("{}: {}".format(option, hint))
        if len(hints) == 0:
            return message
        rtnval = "{} ({})".format(message, "; ".join(hints))
        return rtnval

    def error(self, message: str) -> None:
        self.print_usage(self._err_stream)
        raise CliUsageError("{}: {}".format(self.prog, self._suggest_for_unrecognized(message)))


__all__ = [
    "CliArgumentParser",
    "ParserExit",
]
