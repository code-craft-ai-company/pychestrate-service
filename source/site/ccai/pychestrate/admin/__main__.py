"""
.. module:: pychestrate.admin.__main__
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pychestrate-admin`` entry point dispatcher.

.. moduleauthor:: Code Craft AI LLC

Routes the first positional argument to a registered subsystem:
``pack-template`` and ``backup`` (create / list / verify / restore
backups, see :mod:`ccai.pychestrate.webservice.backup.cli`); future
subsystems (``manifest``, ``extensions``, …) register themselves here.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import sys

from typing import List, Optional, Sequence

from ccai.pychestrate.webservice.extension.pack_template import cli as pack_template_cli


SUBSYSTEM_PACK_TEMPLATE: str = "pack-template"
SUBSYSTEM_BACKUP: str = "backup"


_SUBSYSTEM_HELP_LINES: List[str] = [
    "usage: pychestrate-admin <subsystem> [args]",
    "",
    "subsystems:",
    "  pack-template   Generate / upgrade pychestrate-ext-<name> packs.",
    "  backup          Create, list, verify and restore backups.",
    "",
]


def _print_top_level_help() -> None:
    """
        Print the top-level help summary.

        :returns: None.
    """
    sys.stderr.write("\n".join(_SUBSYSTEM_HELP_LINES))
    return


def main(*, argv: Optional[Sequence[str]]) -> int:
    """
        Dispatch a ``pychestrate-admin`` invocation.

        :param argv: Override argv (mainly for tests). ``None`` defaults
                     to :data:`sys.argv` slicing.

        :returns: Process exit code.
    """
    if argv is None:
        argv_list: Sequence[str] = sys.argv[1:]
    else:
        argv_list = argv

    if len(argv_list) == 0:
        _print_top_level_help()
        rtnval = 2
        return rtnval

    subsystem = argv_list[0]
    remainder: List[str] = list(argv_list[1:])

    if subsystem == SUBSYSTEM_PACK_TEMPLATE:
        rtnval = pack_template_cli.main(argv=remainder)
        return rtnval

    if subsystem == SUBSYSTEM_BACKUP:
        # Imported here: the backup command pulls in SQLAlchemy and the
        # service models, which pack-template does not need.
        from ccai.pychestrate.webservice.backup import cli as backup_cli
        rtnval = backup_cli.main(argv=remainder)
        return rtnval

    if subsystem in ("-h", "--help", "help"):
        _print_top_level_help()
        rtnval = 0
        return rtnval

    sys.stderr.write("error: unknown subsystem '{}'\n".format(subsystem))
    _print_top_level_help()
    rtnval = 2
    return rtnval


def console_main() -> None:
    """
        The ``pychestrate-admin`` console script's entry point (declared in
        ``pyproject.toml``): runs :func:`main` on :data:`sys.argv` and exits with
        its code. ``main`` takes ``argv`` as a keyword-only argument, so a console
        script cannot name it directly.

        :returns: None (raises :class:`SystemExit`).
    """
    sys.exit(main(argv=None))


if __name__ == "__main__":
    console_main()
