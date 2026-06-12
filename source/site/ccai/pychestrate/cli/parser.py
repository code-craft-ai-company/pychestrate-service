"""
.. module:: cli.parser
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Build the ``pyc <noun> <verb>`` argparse tree from OpenAPI.

.. moduleauthor:: Code Craft AI LLC

The OpenAPI document is the source of truth for the CLI surface — the
``operationId`` of each path item maps to a ``(noun, verb)`` pair via
the convention ``operationId = "<noun>_<verb>"`` (e.g.,
``project_list``, ``project_get``). Operations missing an
``operationId`` or that don't match the convention are skipped with a
diagnostic (the parity check in M3 fails the build on any such miss).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import os

from typing import Dict, List, Optional, Tuple

from ccai.pychestrate.cli.exceptions import CommandTreeBuildError
from ccai.pychestrate.cli.models import (
    CommandDescriptor,
    CommandTree,
    RestOperation,
)


HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

OPERATION_VERB_LIST: str = "list"
OPERATION_VERB_GET: str = "get"
OPERATION_VERB_CREATE: str = "create"
OPERATION_VERB_UPDATE: str = "update"
OPERATION_VERB_DELETE: str = "delete"


def _split_operation_id(*, operation_id: str) -> Optional[Tuple[str, str]]:
    """
        Split ``noun_verb`` operation IDs into ``(noun, verb)`` pairs.

        :param operation_id: ``operationId`` value from the OpenAPI doc.

        :returns: ``(noun, verb)`` tuple or ``None`` when the id does not
                  match the convention.
    """
    if operation_id is None or len(operation_id) == 0:
        rtnval: Optional[Tuple[str, str]] = None
        return rtnval

    parts = operation_id.split("_", 1)
    if len(parts) != 2:
        rtnval = None
        return rtnval

    noun, verb = parts
    if len(noun) == 0 or len(verb) == 0:
        rtnval = None
        return rtnval

    rtnval = (noun, verb)
    return rtnval


def _gather_parameters(*, operation_block: Dict) -> Tuple[
        Tuple[str, ...],
        Tuple[str, ...],
        Tuple[str, ...],
        Tuple[str, ...],
    ]:
    """
        Walk the ``parameters`` array on an operation and split into
        path / query buckets plus their required-only subsets.

        :param operation_block: One operation dict (e.g.,
                                ``paths['/projects'].get``).

        :returns: 4-tuple of (path_param_names, query_param_names,
                  required_path, required_query).
    """
    parameters_raw = operation_block.get("parameters", None)
    if parameters_raw is None:
        rtnval = (tuple(), tuple(), tuple(), tuple())
        return rtnval

    path_param_names: List[str] = []
    query_param_names: List[str] = []
    required_path: List[str] = []
    required_query: List[str] = []

    for parameter in parameters_raw:
        location = parameter.get("in", "")
        name = parameter.get("name", "")
        required = bool(parameter.get("required", False))
        if len(name) == 0:
            continue
        if location == "path":
            path_param_names.append(name)
            if required is True:
                required_path.append(name)
        elif location == "query":
            query_param_names.append(name)
            if required is True:
                required_query.append(name)

    rtnval = (
        tuple(path_param_names),
        tuple(query_param_names),
        tuple(required_path),
        tuple(required_query),
    )
    return rtnval


def _walk_operations(*, openapi_document: Dict) -> List[Tuple[str, str, Dict]]:
    """
        Yield ``(method, path, operation_block)`` triples for every
        operation declared in ``paths``.

        :param openapi_document: Parsed OpenAPI document.

        :returns: List of ``(method, path_template, operation_block)``.
    """
    paths = openapi_document.get("paths", {})
    if not isinstance(paths, dict):
        rtnval: List[Tuple[str, str, Dict]] = []
        return rtnval

    triples: List[Tuple[str, str, Dict]] = []
    for path_template in sorted(paths.keys()):
        path_item = paths[path_template]
        if not isinstance(path_item, dict):
            continue
        for method in HTTP_METHODS:
            operation_block = path_item.get(method, None)
            if not isinstance(operation_block, dict):
                continue
            triples.append((method.upper(), path_template, operation_block))

    rtnval = triples
    return rtnval


def build_command_tree(*, openapi_document: Dict) -> CommandTree:
    """
        Build a :class:`CommandTree` from an OpenAPI document.

        :param openapi_document: Parsed OpenAPI dict.

        :returns: Populated :class:`CommandTree`.
        :raises: CommandTreeBuildError when no operations were
                 discoverable.
    """
    if not isinstance(openapi_document, dict):
        err_msg_lines = ["build_command_tree requires a dict OpenAPI document."]
        err_msg_lines.append("RECEIVED: {}".format(type(openapi_document).__name__))
        err_msg = os.linesep.join(err_msg_lines)
        raise CommandTreeBuildError(err_msg) from None

    triples = _walk_operations(openapi_document=openapi_document)
    commands: Dict[Tuple[str, str], CommandDescriptor] = {}

    for method, path_template, operation_block in triples:
        operation_id = operation_block.get("operationId", "")
        split = _split_operation_id(operation_id=operation_id)
        if split is None:
            continue
        noun, verb = split

        path_param_names, query_param_names, required_path, required_query = (
            _gather_parameters(operation_block=operation_block)
        )

        operation = RestOperation(
            operation_id=operation_id,
            method=method,
            path_template=path_template,
            path_param_names=path_param_names,
            query_param_names=query_param_names,
            required_query_param_names=required_query,
            required_path_param_names=required_path,
        )
        commands[(noun, verb)] = CommandDescriptor(
            noun=noun, verb=verb, operation=operation
        )

    if len(commands) == 0:
        err_msg_lines = ["OpenAPI document yielded zero CLI commands."]
        err_msg_lines.append("PATHS_WALKED: {}".format(len(triples)))
        err_msg = os.linesep.join(err_msg_lines)
        raise CommandTreeBuildError(err_msg) from None

    rtnval = CommandTree(commands=dict(commands))
    return rtnval


def build_argparse_for_tree(*, tree: CommandTree, prog: str) -> argparse.ArgumentParser:
    """
        Build a real :class:`argparse.ArgumentParser` from a
        :class:`CommandTree`. Each ``(noun, verb)`` becomes a nested
        subparser; verbs accept their declared path / query parameters
        as arguments. Path parameters are required positionals; query
        parameters are optional ``--<name>`` flags (required ones are
        marked).

        :param tree: Parsed :class:`CommandTree`.
        :param prog: ``prog`` for the parser banner.

        :returns: Argparse parser ready to ``parse_args``.
    """
    top_parser = argparse.ArgumentParser(prog=prog, description="Pychestrate CLI.")
    top_parser.add_argument(
        "--profile",
        required=False,
        default=None,
        help="Credentials profile to use; defaults to PYC_PROFILE or 'default'.",
    )
    top_parser.add_argument(
        "--server-url",
        required=False,
        default=None,
        help="Override the profile's server_url for this invocation.",
    )

    noun_subparsers = top_parser.add_subparsers(dest="noun")

    nouns_seen: Dict[str, argparse._SubParsersAction] = {}
    for (noun, verb), descriptor in sorted(tree.commands.items()):
        if noun not in nouns_seen:
            noun_parser = noun_subparsers.add_parser(noun, help="{} commands".format(noun))
            nouns_seen[noun] = noun_parser.add_subparsers(dest="verb")
        verb_subparsers = nouns_seen[noun]
        verb_parser = verb_subparsers.add_parser(
            verb, help="{} {} ({})".format(noun, verb, descriptor.operation.operation_id)
        )

        for path_param in descriptor.operation.path_param_names:
            verb_parser.add_argument(path_param, help="Path parameter {}".format(path_param))

        for query_param in descriptor.operation.query_param_names:
            is_required = query_param in descriptor.operation.required_query_param_names
            verb_parser.add_argument(
                "--{}".format(query_param),
                required=is_required,
                default=None,
                help="Query parameter {}{}".format(
                    query_param, " (required)" if is_required else ""
                ),
            )

    rtnval = top_parser
    return rtnval


def lookup_command(
        *,
        tree: CommandTree,
        noun: str,
        verb: str
    ) -> Optional[CommandDescriptor]:
    """
        Return the :class:`CommandDescriptor` for ``(noun, verb)``.

        :param tree: Parsed :class:`CommandTree`.
        :param noun: First positional after ``pyc``.
        :param verb: Second positional after ``pyc <noun>``.

        :returns: :class:`CommandDescriptor` or ``None`` on miss.
    """
    rtnval = tree.commands.get((noun, verb), None)
    return rtnval
