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
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import sys

from typing import Any, Optional, TextIO

from ccai.pychestrate.cli.exceptions import CliUsageError


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

    def error(self, message: str) -> None:
        self.print_usage(self._err_stream)
        raise CliUsageError("{}: {}".format(self.prog, message))


__all__ = [
    "CliArgumentParser",
    "ParserExit",
]
