"""
.. module:: extension.pack_template.cli
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: argparse-driven CLI for ``pychestrate-admin pack-template``.

.. moduleauthor:: Automation Mojo LLC

The console script declared by the service's ``pyproject.toml`` is
``pychestrate-admin``. This module hosts the ``pack-template``
subcommand tree. M1 ships ``new``; ``upgrade`` and ``list-versions``
arrive in M2 (T2.2 / T2.3).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import logging
import sys

from pathlib import Path
from typing import List, Optional, Sequence

from automojo.errors.exceptions import ConfigurationError, SemanticError

from automojo.pychestrate.webservice.extension.pack_template.generator import (
    PackGenerator,
    normalize_pack_name,
)
from automojo.pychestrate.webservice.extension.pack_template.models import (
    PackGenerationRequest,
)


logger = logging.getLogger(__name__)


SUBCOMMAND_NEW: str = "new"
SUBCOMMAND_LIST_VERSIONS: str = "list-versions"


def _build_parser() -> argparse.ArgumentParser:
    """
        Build the top-level ``pychestrate-admin pack-template`` parser.

        :returns: Configured :class:`argparse.ArgumentParser`.
    """
    top_parser = argparse.ArgumentParser(
        prog="pychestrate-admin pack-template",
        description="Pychestrate extension-pack template generator.",
    )
    subparsers = top_parser.add_subparsers(dest="subcommand")

    new_parser = subparsers.add_parser(
        SUBCOMMAND_NEW, help="Generate a new pychestrate-ext-<name>/ tree."
    )
    new_parser.add_argument(
        "--name", required=True, help="Raw pack name (will be normalized)."
    )
    new_parser.add_argument(
        "--author", required=False, default=None, help="Author / org string."
    )
    new_parser.add_argument(
        "--license", required=False, default=None, help="SPDX license identifier."
    )
    new_parser.add_argument(
        "--protocol",
        action="append",
        default=None,
        help="Factory protocol name to seed (repeatable).",
    )
    new_parser.add_argument(
        "--resource",
        action="append",
        default=None,
        help="Resource extension base name to seed (repeatable).",
    )
    new_parser.add_argument(
        "--target",
        required=False,
        default=None,
        help="Parent directory for the generated pack. Defaults to CWD.",
    )
    new_parser.add_argument(
        "--template-version",
        required=False,
        type=int,
        default=None,
        help="Override the corpus version. Defaults to latest.",
    )

    subparsers.add_parser(
        SUBCOMMAND_LIST_VERSIONS, help="List available corpus template versions."
    )

    return top_parser


def _build_request_from_args(*, args: argparse.Namespace) -> PackGenerationRequest:
    """
        Translate parsed argparse args into a :class:`PackGenerationRequest`.

        :param args: Parsed args from ``new``.

        :returns: :class:`PackGenerationRequest`.
        :raises: SemanticError on bad input names.
    """
    raw_name = args.name
    normalized = normalize_pack_name(raw=raw_name)

    if args.target is None:
        target_dir = Path.cwd()
    else:
        target_dir = Path(args.target).expanduser().resolve()

    if args.protocol is None:
        protocol_names: List[str] = []
    else:
        protocol_names = list(args.protocol)

    if args.resource is None:
        resource_base_names: List[str] = []
    else:
        resource_base_names = list(args.resource)

    rtnval = PackGenerationRequest(
        name=raw_name,
        normalized_name=normalized,
        author=args.author,
        license=args.license,
        protocol_names=tuple(protocol_names),
        resource_base_names=tuple(resource_base_names),
        target_dir=target_dir,
    )
    return rtnval


def _run_new(*, args: argparse.Namespace) -> int:
    """
        Execute the ``new`` subcommand.

        :param args: Parsed args.

        :returns: Process exit code.
    """
    try:
        request = _build_request_from_args(args=args)
    except SemanticError as xcpt:
        sys.stderr.write("error: {}\n".format(xcpt))
        rtnval = 2
        return rtnval

    generator = PackGenerator(corpus_root=None)
    try:
        pack_root = generator.generate(
            request=request, template_version=args.template_version
        )
    except (ConfigurationError, SemanticError) as xcpt:
        sys.stderr.write("error: {}\n".format(xcpt))
        rtnval = 1
        return rtnval

    sys.stdout.write("generated: {}\n".format(pack_root))
    rtnval = 0
    return rtnval


def _run_list_versions(*, args: argparse.Namespace) -> int:
    """
        Execute the ``list-versions`` subcommand.

        :param args: Parsed args.

        :returns: Process exit code.
    """
    generator = PackGenerator(corpus_root=None)
    versions = generator.list_versions()
    for version_int in versions:
        sys.stdout.write("v{}\n".format(version_int))
    rtnval = 0
    return rtnval


def main(*, argv: Optional[Sequence[str]]) -> int:
    """
        CLI entry point.

        :param argv: Override argv (mainly for tests). ``None`` defaults
                     to :data:`sys.argv` slicing.

        :returns: Process exit code.
    """
    if argv is None:
        argv_list: Sequence[str] = sys.argv[1:]
    else:
        argv_list = argv

    parser = _build_parser()
    args = parser.parse_args(argv_list)

    if args.subcommand == SUBCOMMAND_NEW:
        rtnval = _run_new(args=args)
        return rtnval

    if args.subcommand == SUBCOMMAND_LIST_VERSIONS:
        rtnval = _run_list_versions(args=args)
        return rtnval

    parser.print_help(sys.stderr)
    rtnval = 2
    return rtnval
