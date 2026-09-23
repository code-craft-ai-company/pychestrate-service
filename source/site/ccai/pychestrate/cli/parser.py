"""
.. module:: cli.parser
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Build the ``pyc <noun> <verb>`` command tree from OpenAPI.

.. moduleauthor:: Code Craft AI LLC

The OpenAPI document is the source of truth for the CLI surface.
Each operation becomes one ``pyc <noun> <verb>`` command:

* **noun** -- the operation's first tag with ``_`` spelled ``-``
  (``resource_pools`` -> ``resource-pools``). An operation without
  tags falls back to the part of its ``operationId`` before the first
  ``_`` (``project_list`` -> ``project``).
* **verb** -- the ``operationId`` minus the tag prefix, with ``_``
  spelled ``-`` (``projects_get_by_slug`` under tag ``projects`` ->
  ``get-by-slug``); an id that does not start with its tag keeps the
  whole id.

Paths in the document are relative to its ``servers`` URL
(``https://host/api/v1``), so every command's path template is
prefixed with that URL's path -- ``/api/v1`` when the document names
none. Lookups accept ``_`` or ``-`` in verbs and the singular or
plural of a noun (``pyc project list`` finds ``projects list``).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import os
import urllib.parse

from typing import Dict, List, Optional, Tuple

from ccai.pychestrate.cli.exceptions import CommandTreeBuildError
from ccai.pychestrate.cli.models import (
    CommandDescriptor,
    CommandTree,
    RestOperation,
)


HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

#: Path prefix every Pychestrate REST route carries.
DEFAULT_API_BASE_PATH: str = "/api/v1"

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


def normalize_word(word: str) -> str:
    """
        CLI spelling of a noun or verb: lower case, ``_`` -> ``-``.

        :param word: Raw word.

        :returns: Normalized word.
    """
    rtnval = str(word).strip().lower().replace("_", "-")
    return rtnval


def _derive_noun_verb(*, operation_id: str, tags: List[str]) -> Optional[Tuple[str, str]]:
    """
        Derive ``(noun, verb)`` for an operation (see module docs).

        :param operation_id: ``operationId``.
        :param tags: The operation's ``tags``.

        :returns: ``(noun, verb)`` or ``None`` when no command can be
                  derived.
    """
    if operation_id is None or len(operation_id) == 0:
        return None

    if tags is not None and len(tags) > 0 and isinstance(tags[0], str) and len(tags[0]) > 0:
        tag = tags[0]
        tag_prefix = tag.replace("-", "_") + "_"
        if operation_id.startswith(tag_prefix) and len(operation_id) > len(tag_prefix):
            verb = operation_id[len(tag_prefix):]
        else:
            verb = operation_id
        rtnval = (normalize_word(tag), normalize_word(verb))
        return rtnval

    split = _split_operation_id(operation_id=operation_id)
    if split is None:
        return None
    rtnval = (normalize_word(split[0]), normalize_word(split[1]))
    return rtnval


def api_base_path(*, openapi_document: Dict) -> str:
    """
        The path prefix the document's paths are relative to: the path
        of its first ``servers`` URL (templated hosts are fine), else
        :data:`DEFAULT_API_BASE_PATH`.

        :param openapi_document: Parsed OpenAPI document.

        :returns: Prefix without a trailing slash (``"/api/v1"``).
    """
    servers = openapi_document.get("servers", None) if isinstance(openapi_document, dict) else None
    if isinstance(servers, list) and len(servers) > 0 and isinstance(servers[0], dict):
        url = str(servers[0].get("url", "") or "")
        # A templated host ("https://{host}/api/v1") is not a valid
        # netloc for urlsplit; take the path after the authority.
        if "://" in url:
            after_scheme = url.split("://", 1)[1]
            path = "/" + after_scheme.split("/", 1)[1] if "/" in after_scheme else ""
        else:
            path = urllib.parse.urlsplit(url).path
        path = path.rstrip("/")
        if len(path) > 0:
            return path
        return ""
    rtnval = DEFAULT_API_BASE_PATH
    return rtnval


def _gather_parameters(*, operation_block: Dict, shared_parameters: Optional[List] = None,
                       components: Optional[Dict] = None) -> Tuple[
        Tuple[str, ...],
        Tuple[str, ...],
        Tuple[str, ...],
        Tuple[str, ...],
    ]:
    """
        Walk the ``parameters`` of an operation (plus its path item's
        shared parameters, resolving ``$ref``) and split into path /
        query buckets plus their required-only subsets.

        :param operation_block: One operation dict.
        :param shared_parameters: The path item's ``parameters``.
        :param components: ``components.parameters`` for ``$ref``.

        :returns: 4-tuple of (path_param_names, query_param_names,
                  required_path, required_query).
    """
    parameters_raw = list(shared_parameters or []) + list(operation_block.get("parameters", None) or [])
    if len(parameters_raw) == 0:
        rtnval = (tuple(), tuple(), tuple(), tuple())
        return rtnval

    path_param_names: List[str] = []
    query_param_names: List[str] = []
    required_path: List[str] = []
    required_query: List[str] = []

    for parameter in parameters_raw:
        if not isinstance(parameter, dict):
            continue
        if "$ref" in parameter:
            ref_name = str(parameter["$ref"]).rsplit("/", 1)[-1]
            parameter = (components or {}).get(ref_name, {})
            if not isinstance(parameter, dict):
                continue
        location = parameter.get("in", "")
        name = parameter.get("name", "")
        required = bool(parameter.get("required", False))
        if len(name) == 0:
            continue
        if location == "path":
            if name in path_param_names:
                continue
            path_param_names.append(name)
            if required is True:
                required_path.append(name)
        elif location == "query":
            if name in query_param_names:
                continue
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


def _order_by_template(*, path_template: str, names: Tuple[str, ...]) -> Tuple[str, ...]:
    """
        Order path parameters as they appear in the template, so
        positionals read left to right like the URL.

        :param path_template: Path template.
        :param names: Declared path parameter names.

        :returns: Ordered names (undeclared placeholders appended).
    """
    ordered: List[str] = []
    remainder = path_template
    while "{" in remainder and "}" in remainder:
        start = remainder.index("{")
        end = remainder.index("}", start)
        name = remainder[start + 1:end]
        if name not in ordered:
            ordered.append(name)
        remainder = remainder[end + 1:]
    for name in names:
        if name not in ordered:
            ordered.append(name)
    rtnval = tuple(ordered)
    return rtnval


def _walk_operations(*, openapi_document: Dict) -> List[Tuple[str, str, Dict, List]]:
    """
        Collect ``(method, path, operation_block, shared_parameters)``
        for every operation declared in ``paths``.

        :param openapi_document: Parsed OpenAPI document.

        :returns: List of tuples.
    """
    paths = openapi_document.get("paths", {})
    if not isinstance(paths, dict):
        rtnval: List[Tuple[str, str, Dict, List]] = []
        return rtnval

    rows: List[Tuple[str, str, Dict, List]] = []
    for path_template in sorted(paths.keys()):
        path_item = paths[path_template]
        if not isinstance(path_item, dict):
            continue
        shared = path_item.get("parameters", None) or []
        for method in HTTP_METHODS:
            operation_block = path_item.get(method, None)
            if not isinstance(operation_block, dict):
                continue
            rows.append((method.upper(), path_template, operation_block, shared))

    rtnval = rows
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

    base_path = api_base_path(openapi_document=openapi_document)
    components = {}
    raw_components = openapi_document.get("components", {})
    if isinstance(raw_components, dict) and isinstance(raw_components.get("parameters", None), dict):
        components = raw_components["parameters"]

    rows = _walk_operations(openapi_document=openapi_document)
    commands: Dict[Tuple[str, str], CommandDescriptor] = {}

    for method, path_template, operation_block, shared in rows:
        operation_id = operation_block.get("operationId", "")
        derived = _derive_noun_verb(
            operation_id=operation_id, tags=operation_block.get("tags", None) or []
        )
        if derived is None:
            continue
        noun, verb = derived

        path_param_names, query_param_names, required_path, required_query = (
            _gather_parameters(
                operation_block=operation_block,
                shared_parameters=shared,
                components=components,
            )
        )
        full_template = base_path + path_template
        path_param_names = _order_by_template(path_template=full_template, names=path_param_names)

        operation = RestOperation(
            operation_id=operation_id,
            method=method,
            path_template=full_template,
            path_param_names=path_param_names,
            query_param_names=query_param_names,
            required_query_param_names=required_query,
            required_path_param_names=required_path,
            summary=str(operation_block.get("summary", "") or "").strip(),
            has_request_body=isinstance(operation_block.get("requestBody", None), dict),
        )
        commands[(noun, verb)] = CommandDescriptor(
            noun=noun, verb=verb, operation=operation
        )

    if len(commands) == 0:
        err_msg_lines = ["OpenAPI document yielded zero CLI commands."]
        err_msg_lines.append("PATHS_WALKED: {}".format(len(rows)))
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


def _noun_candidates(noun: str) -> List[str]:
    """
        Spellings to try for a noun: as typed, then plural / singular.

        :param noun: Normalized noun.

        :returns: Candidates in preference order.
    """
    candidates = [noun]
    if noun.endswith("s"):
        candidates.append(noun[:-1])
    else:
        candidates.append(noun + "s")
    rtnval = candidates
    return rtnval


def resolve_noun(*, tree: CommandTree, noun: str) -> Optional[str]:
    """
        The tree's spelling of ``noun`` (accepting ``_`` / ``-`` and
        singular / plural), or ``None``.

        :param tree: Parsed :class:`CommandTree`.
        :param noun: Noun as typed.

        :returns: Canonical noun or ``None``.
    """
    known = set(noun_key for (noun_key, _verb) in tree.commands.keys())
    for candidate in _noun_candidates(normalize_word(noun)):
        if candidate in known:
            return candidate
    return None


def verbs_for(*, tree: CommandTree, noun: str) -> List[CommandDescriptor]:
    """
        Every command under ``noun``, sorted by verb.

        :param tree: Parsed :class:`CommandTree`.
        :param noun: Canonical noun.

        :returns: Descriptors.
    """
    rtnval = [
        descriptor for (noun_key, _verb), descriptor in sorted(tree.commands.items())
        if noun_key == noun
    ]
    return rtnval


def lookup_command(
        *,
        tree: CommandTree,
        noun: str,
        verb: str
    ) -> Optional[CommandDescriptor]:
    """
        Return the :class:`CommandDescriptor` for ``(noun, verb)``,
        accepting ``_`` / ``-`` and singular / plural nouns.

        :param tree: Parsed :class:`CommandTree`.
        :param noun: First positional after ``pyc``.
        :param verb: Second positional after ``pyc <noun>``.

        :returns: :class:`CommandDescriptor` or ``None`` on miss.
    """
    exact = tree.commands.get((noun, verb), None)
    if exact is not None:
        return exact
    canonical_noun = resolve_noun(tree=tree, noun=noun)
    if canonical_noun is None:
        return None
    rtnval = tree.commands.get((canonical_noun, normalize_word(verb)), None)
    return rtnval
