"""
.. module:: cli.parser
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Build the ``pyc <noun> <verb>`` command tree from OpenAPI.

.. moduleauthor:: Code Craft AI LLC

The OpenAPI document is the source of truth for the CLI surface.
Each operation becomes one ``pyc <noun> <verb>`` command, named as
:mod:`cli.command_names` describes: the operation's ``x-cli``
extension, else the explicit :data:`command_names.COMMAND_NAMES`
table, else derivation:

* **noun** -- the operation's first tag with ``_`` spelled ``-``
  (``resource_pools`` -> ``resource-pools``). An operation without
  tags falls back to the part of its ``operationId`` before the first
  ``_`` (``project_list`` -> ``project``).
* **verb** -- the ``operationId`` minus the tag prefix, with ``_``
  spelled ``-`` (``projects_get_by_slug`` under tag ``projects`` ->
  ``get-by-slug``); an id that does not start with its tag keeps the
  whole id. ``read`` and ``get-by-<x>`` are then spelled ``get`` and
  ``patch`` ``update`` when no other operation of the noun has that
  verb.

The derived name stays an alias of the command. Parameters (the
operation's and its path item's, ``$ref``s resolved) keep their
descriptions, types, allowed values and defaults so the generated
``--help`` can show them; the request body's top-level fields are
collected the same way.

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


import json
import os
import urllib.parse

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ccai.pychestrate.cli import command_names
from ccai.pychestrate.cli.exceptions import CommandTreeBuildError
from ccai.pychestrate.cli.models import (
    BodyField,
    CommandDescriptor,
    CommandTree,
    OperationParameter,
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

#: How the name of a command was chosen (see :func:`plan_command_names`).
NAMING_SOURCE_X_CLI: str = "x-cli"
NAMING_SOURCE_TABLE: str = "table"
NAMING_SOURCE_DERIVED: str = "derived"
NAMING_SOURCE_SYNONYM: str = "synonym"
NAMING_SOURCE_FALLBACK: str = "fallback"

#: Longest description kept for a parameter or body field.
_DESCRIPTION_LIMIT: int = 160

#: How many ``$ref`` hops :func:`resolve_ref` follows before giving up.
_MAX_REF_HOPS: int = 16


@dataclass
class PlannedCommand:
    """
        The name chosen for one operation, and why.

        :param operation_id: ``operationId``.
        :param method: HTTP method (upper case).
        :param path_template: Path relative to the document's servers.
        :param derived: ``(noun, verb)`` derived from tag + id.
        :param name: The canonical ``(noun, verb)``.
        :param source: One of the ``NAMING_SOURCE_*`` values.
    """
    operation_id: str
    method: str
    path_template: str
    derived: Tuple[str, str]
    name: Optional[Tuple[str, str]] = None
    source: str = ""


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


def _explicit_name(*, operation_id: str, operation_block: Dict) -> Optional[Tuple[str, str, str]]:
    """
        The explicit name of an operation: its ``x-cli`` extension,
        else its :data:`command_names.COMMAND_NAMES` entry.

        :param operation_id: ``operationId``.
        :param operation_block: The operation.

        :returns: ``(noun, verb, source)`` or ``None``.
    """
    extension = operation_block.get(command_names.X_CLI_EXTENSION, None)
    if isinstance(extension, dict):
        noun = normalize_word(extension.get("noun", "") or "")
        verb = normalize_word(extension.get("verb", "") or "")
        if command_names.is_well_formed_word(noun) and command_names.is_well_formed_word(verb):
            rtnval: Optional[Tuple[str, str, str]] = (noun, verb, NAMING_SOURCE_X_CLI)
            return rtnval

    table_entry = command_names.COMMAND_NAMES.get(operation_id, None)
    if table_entry is not None:
        noun, verb = table_entry
        rtnval = (noun, verb, NAMING_SOURCE_TABLE)
        return rtnval

    rtnval = None
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


def resolve_ref(*, openapi_document: Dict, node: Any) -> Any:
    """
        Follow ``$ref`` pointers (``#/components/...``) inside the
        document until a concrete node is reached.

        :param openapi_document: Parsed OpenAPI document.
        :param node: A node that may be ``{"$ref": "#/..."}``.

        :returns: The referenced node, ``node`` itself when it is not
                  a reference, or ``{}`` when the pointer does not
                  resolve (or loops).
    """
    current = node
    hops = 0
    while isinstance(current, dict) and "$ref" in current:
        hops = hops + 1
        if hops > _MAX_REF_HOPS:
            rtnval: Any = {}
            return rtnval
        pointer = str(current.get("$ref", ""))
        if not pointer.startswith("#/"):
            rtnval = {}
            return rtnval
        target: Any = openapi_document
        for raw_part in pointer[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if isinstance(target, dict) and part in target:
                target = target[part]
            else:
                rtnval = {}
                return rtnval
        current = target
    rtnval = current
    return rtnval


def _one_line(text: Any) -> str:
    """
        A description as one short line: whitespace collapsed, cut at
        :data:`_DESCRIPTION_LIMIT` characters.

        :param text: Description (any type).

        :returns: Text.
    """
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) > _DESCRIPTION_LIMIT:
        collapsed = collapsed[:_DESCRIPTION_LIMIT - 3].rstrip() + "..."
    rtnval = collapsed
    return rtnval


def _schema_type(*, openapi_document: Dict, schema: Any) -> str:
    """
        The JSON-schema type of ``schema`` (``$ref`` and ``allOf``
        followed; OpenAPI 3.1 ``["string", "null"]`` lists reduced to
        their non-null member).

        :param openapi_document: Document (for ``$ref``).
        :param schema: Schema node.

        :returns: Type name, or ``""`` when unspecified.
    """
    resolved = resolve_ref(openapi_document=openapi_document, node=schema)
    if not isinstance(resolved, dict):
        return ""
    declared = resolved.get("type", None)
    if isinstance(declared, list):
        non_null = [str(item) for item in declared if item != "null"]
        declared = non_null[0] if len(non_null) > 0 else None
    if isinstance(declared, str) and len(declared) > 0:
        return declared
    for combinator in ("allOf", "oneOf", "anyOf"):
        members = resolved.get(combinator, None)
        if isinstance(members, list):
            for member in members:
                member_type = _schema_type(openapi_document=openapi_document, schema=member)
                if len(member_type) > 0:
                    return member_type
    if isinstance(resolved.get("properties", None), dict):
        return "object"
    return ""


def _text_value(value: Any) -> str:
    """
        A schema value (default, enum member) as command-line text.

        :param value: Value.

        :returns: Text (booleans as ``true`` / ``false``).
    """
    if isinstance(value, bool):
        rtnval = "true" if value is True else "false"
        return rtnval
    if isinstance(value, (dict, list)):
        rtnval = json.dumps(value)
        return rtnval
    rtnval = str(value)
    return rtnval


def _parameter_from_block(*, openapi_document: Dict, block: Dict) -> Optional[OperationParameter]:
    """
        One :class:`OperationParameter` from a parameter object.

        :param openapi_document: Document (for ``$ref``).
        :param block: Parameter object (already resolved).

        :returns: The parameter, or ``None`` for header / cookie
                  parameters and nameless entries.
    """
    location = str(block.get("in", "") or "")
    name = str(block.get("name", "") or "")
    if location not in ("path", "query") or len(name) == 0:
        return None

    schema = resolve_ref(openapi_document=openapi_document, node=block.get("schema", {}) or {})
    if not isinstance(schema, dict):
        schema = {}
    value_type = _schema_type(openapi_document=openapi_document, schema=schema) or "string"
    choices: Tuple[str, ...] = tuple()
    enum_values = schema.get("enum", None)
    if isinstance(enum_values, list) and len(enum_values) > 0:
        choices = tuple(_text_value(item) for item in enum_values if item is not None)
    default: Optional[str] = None
    if "default" in schema and schema.get("default", None) is not None:
        default = _text_value(schema["default"])

    description = block.get("description", None) or schema.get("description", None) or ""
    rtnval = OperationParameter(
        name=name,
        location=location,
        required=bool(block.get("required", False)) or location == "path",
        description=_one_line(description),
        value_type=value_type,
        choices=choices,
        default=default,
    )
    return rtnval


def _gather_parameters(
        *,
        openapi_document: Dict,
        operation_block: Dict,
        shared_parameters: Optional[List] = None
    ) -> Tuple[OperationParameter, ...]:
    """
        The path and query parameters of an operation: the path
        item's shared ones plus the operation's own (an operation
        parameter replaces a shared one of the same name and
        location), ``$ref``s resolved.

        :param openapi_document: Document (for ``$ref``).
        :param operation_block: One operation dict.
        :param shared_parameters: The path item's ``parameters``.

        :returns: Parameters in declaration order.
    """
    by_key: Dict[Tuple[str, str], OperationParameter] = {}
    order: List[Tuple[str, str]] = []
    raw_blocks = list(shared_parameters or []) + list(operation_block.get("parameters", None) or [])
    for raw_block in raw_blocks:
        block = resolve_ref(openapi_document=openapi_document, node=raw_block)
        if not isinstance(block, dict):
            continue
        parameter = _parameter_from_block(openapi_document=openapi_document, block=block)
        if parameter is None:
            continue
        key = (parameter.location, parameter.name)
        if key not in by_key:
            order.append(key)
        by_key[key] = parameter

    rtnval = tuple(by_key[key] for key in order)
    return rtnval


def _schema_fields(*, openapi_document: Dict, schema: Any, depth: int = 0) -> Tuple[List[BodyField], List[str]]:
    """
        The top-level properties of a body schema (``allOf`` members
        merged, ``$ref`` followed).

        :param openapi_document: Document (for ``$ref``).
        :param schema: Schema node.
        :param depth: Recursion guard.

        :returns: ``(fields, required_names)``.
    """
    fields: List[BodyField] = []
    required_names: List[str] = []
    resolved = resolve_ref(openapi_document=openapi_document, node=schema)
    if not isinstance(resolved, dict) or depth > _MAX_REF_HOPS:
        rtnval = (fields, required_names)
        return rtnval

    for member in resolved.get("allOf", None) or []:
        member_fields, member_required = _schema_fields(
            openapi_document=openapi_document, schema=member, depth=depth + 1
        )
        fields.extend(member_fields)
        required_names.extend(member_required)

    declared_required = resolved.get("required", None)
    if isinstance(declared_required, list):
        required_names.extend(str(name) for name in declared_required)

    properties = resolved.get("properties", None)
    if isinstance(properties, dict):
        for name, property_schema in properties.items():
            resolved_property = resolve_ref(openapi_document=openapi_document, node=property_schema)
            description = ""
            if isinstance(resolved_property, dict):
                description = resolved_property.get("description", "") or ""
            if isinstance(property_schema, dict) and len(str(property_schema.get("description", "") or "")) > 0:
                description = property_schema.get("description", "")
            fields.append(
                BodyField(
                    name=str(name),
                    required=False,
                    value_type=_schema_type(openapi_document=openapi_document, schema=property_schema),
                    description=_one_line(description),
                )
            )

    rtnval = (fields, required_names)
    return rtnval


def _body_details(*, openapi_document: Dict, operation_block: Dict) -> Tuple[bool, bool, Tuple[BodyField, ...]]:
    """
        Whether the operation takes a request body, whether the body
        is required, and the body's top-level fields.

        :param openapi_document: Document (for ``$ref``).
        :param operation_block: The operation.

        :returns: ``(has_body, body_required, fields)``.
    """
    request_body = resolve_ref(
        openapi_document=openapi_document, node=operation_block.get("requestBody", None)
    )
    if not isinstance(request_body, dict):
        rtnval = (False, False, tuple())
        return rtnval

    body_required = bool(request_body.get("required", False))
    schema: Any = None
    content = request_body.get("content", None)
    if isinstance(content, dict):
        for media_type, media_block in content.items():
            if "json" in str(media_type).lower() and isinstance(media_block, dict):
                schema = media_block.get("schema", None)
                break

    fields: List[BodyField] = []
    if schema is not None:
        raw_fields, required_names = _schema_fields(openapi_document=openapi_document, schema=schema)
        seen: Dict[str, int] = {}
        for raw_field in raw_fields:
            marked = BodyField(
                name=raw_field.name,
                required=raw_field.name in required_names,
                value_type=raw_field.value_type,
                description=raw_field.description,
            )
            if raw_field.name in seen:
                fields[seen[raw_field.name]] = marked
                continue
            seen[raw_field.name] = len(fields)
            fields.append(marked)

    rtnval = (True, body_required, tuple(fields))
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


def plan_command_names(*, openapi_document: Dict) -> List[PlannedCommand]:
    """
        Choose the canonical ``(noun, verb)`` of every operation (see
        :mod:`cli.command_names`): explicit names first, then derived
        names, then the standard verb spellings where they are free.
        An operation whose explicit and derived names are both taken
        gets ``(derived noun, operationId)`` (source ``fallback``).

        :param openapi_document: Parsed OpenAPI document.

        :returns: One :class:`PlannedCommand` per named operation, in
                  document order.
    """
    planned: List[PlannedCommand] = []
    explicit_names: Dict[int, Tuple[str, str, str]] = {}
    for method, path_template, operation_block, _shared in _walk_operations(openapi_document=openapi_document):
        operation_id = str(operation_block.get("operationId", "") or "")
        derived = _derive_noun_verb(
            operation_id=operation_id, tags=operation_block.get("tags", None) or []
        )
        if derived is None:
            continue
        entry = PlannedCommand(
            operation_id=operation_id, method=method, path_template=path_template, derived=derived,
        )
        explicit = _explicit_name(operation_id=operation_id, operation_block=operation_block)
        if explicit is not None:
            explicit_names[len(planned)] = explicit
        planned.append(entry)

    taken: Dict[Tuple[str, str], int] = {}

    # 1. explicit names (x-cli, then the table)
    for index, entry in enumerate(planned):
        explicit = explicit_names.get(index, None)
        if explicit is None:
            continue
        noun, verb, source = explicit
        if (noun, verb) in taken:
            continue
        entry.name = (noun, verb)
        entry.source = source
        taken[(noun, verb)] = index

    # 2. derived names
    for index, entry in enumerate(planned):
        if entry.name is not None or entry.derived in taken:
            continue
        entry.name = entry.derived
        entry.source = NAMING_SOURCE_DERIVED
        taken[entry.derived] = index

    # 3. standard verb spellings, where free
    for index, entry in enumerate(planned):
        if entry.source != NAMING_SOURCE_DERIVED:
            continue
        noun, verb = entry.derived
        synonym = command_names.synonym_verb(verb)
        if synonym is None or (noun, synonym) in taken:
            continue
        del taken[entry.derived]
        entry.name = (noun, synonym)
        entry.source = NAMING_SOURCE_SYNONYM
        taken[entry.name] = index

    # 4. anything still unnamed collided twice
    for index, entry in enumerate(planned):
        if entry.name is not None:
            continue
        noun = entry.derived[0]
        verb = normalize_word(entry.operation_id)
        suffix = 2
        candidate = (noun, verb)
        while candidate in taken:
            candidate = (noun, "{}-{}".format(verb, suffix))
            suffix = suffix + 1
        entry.name = candidate
        entry.source = NAMING_SOURCE_FALLBACK
        taken[candidate] = index

    rtnval = planned
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
    rows = _walk_operations(openapi_document=openapi_document)
    planned_by_key: Dict[Tuple[str, str], PlannedCommand] = {}
    for entry in plan_command_names(openapi_document=openapi_document):
        planned_by_key[(entry.method, entry.path_template)] = entry

    commands: Dict[Tuple[str, str], CommandDescriptor] = {}
    derived_names: Dict[Tuple[str, str], Tuple[str, str]] = {}

    for method, path_template, operation_block, shared in rows:
        entry = planned_by_key.get((method, path_template), None)
        if entry is None or entry.name is None:
            continue
        noun, verb = entry.name

        parameters = _gather_parameters(
            openapi_document=openapi_document,
            operation_block=operation_block,
            shared_parameters=shared,
        )
        full_template = base_path + path_template
        declared_path_names = tuple(p.name for p in parameters if p.location == "path")
        path_param_names = _order_by_template(path_template=full_template, names=declared_path_names)
        for name in path_param_names:
            if name not in declared_path_names:
                parameters = parameters + (OperationParameter(name=name, location="path", required=True),)
        query_params = [p for p in parameters if p.location == "query"]
        has_body, body_required, body_fields = _body_details(
            openapi_document=openapi_document, operation_block=operation_block
        )

        operation = RestOperation(
            operation_id=entry.operation_id,
            method=method,
            path_template=full_template,
            path_param_names=path_param_names,
            query_param_names=tuple(p.name for p in query_params),
            required_query_param_names=tuple(p.name for p in query_params if p.required is True),
            required_path_param_names=path_param_names,
            summary=str(operation_block.get("summary", "") or "").strip(),
            has_request_body=has_body,
            parameters=parameters,
            body_fields=body_fields,
            body_required=body_required,
            description=str(operation_block.get("description", "") or "").strip(),
        )
        aliases: Tuple[Tuple[str, str], ...] = tuple()
        if entry.derived != entry.name:
            aliases = (entry.derived,)
            derived_names[entry.derived] = entry.name
        commands[(noun, verb)] = CommandDescriptor(
            noun=noun, verb=verb, operation=operation, aliases=aliases,
        )

    if len(commands) == 0:
        err_msg_lines = ["OpenAPI document yielded zero CLI commands."]
        err_msg_lines.append("PATHS_WALKED: {}".format(len(rows)))
        err_msg = os.linesep.join(err_msg_lines)
        raise CommandTreeBuildError(err_msg) from None

    # A derived name that is some other command's canonical name is
    # not an alias: the canonical name wins.
    aliases_map: Dict[Tuple[str, str], Tuple[str, str]] = {}
    for alias, canonical in derived_names.items():
        if alias not in commands:
            aliases_map[alias] = canonical

    rtnval = CommandTree(commands=dict(commands), aliases=aliases_map)
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


def canonical_nouns(*, tree: CommandTree) -> List[str]:
    """
        The canonical nouns of the tree, sorted.

        :param tree: Command tree.

        :returns: Nouns.
    """
    rtnval = sorted(set(noun_key for (noun_key, _verb) in tree.commands.keys()))
    return rtnval


def alias_nouns(*, tree: CommandTree) -> List[str]:
    """
        Nouns reachable only through aliases (``rpa`` for the
        ``rpa-*`` commands), sorted.

        :param tree: Command tree.

        :returns: Nouns.
    """
    canonical = set(canonical_nouns(tree=tree))
    rtnval = sorted(set(noun_key for (noun_key, _verb) in tree.aliases.keys()) - canonical)
    return rtnval


def resolve_noun(*, tree: CommandTree, noun: str) -> Optional[str]:
    """
        The tree's spelling of ``noun`` (accepting ``_`` / ``-`` and
        singular / plural): a canonical noun, else an alias noun.

        :param tree: Parsed :class:`CommandTree`.
        :param noun: Noun as typed.

        :returns: Noun or ``None``.
    """
    canonical = set(canonical_nouns(tree=tree))
    aliased = set(alias_nouns(tree=tree))
    candidates = _noun_candidates(normalize_word(noun))
    for candidate in candidates:
        if candidate in canonical:
            return candidate
    for candidate in candidates:
        if candidate in aliased:
            return candidate
    return None


def verbs_for(*, tree: CommandTree, noun: str) -> List[CommandDescriptor]:
    """
        Every command under a canonical ``noun``, sorted by verb.

        :param tree: Parsed :class:`CommandTree`.
        :param noun: Canonical noun.

        :returns: Descriptors.
    """
    rtnval = [
        descriptor for (noun_key, _verb), descriptor in sorted(tree.commands.items())
        if noun_key == noun
    ]
    return rtnval


def alias_verbs_for(*, tree: CommandTree, noun: str) -> List[Tuple[str, CommandDescriptor]]:
    """
        The aliases under ``noun``: ``(alias verb, command)`` pairs,
        sorted by alias verb.

        :param tree: Parsed :class:`CommandTree`.
        :param noun: Noun (canonical or alias-only).

        :returns: Pairs.
    """
    pairs: List[Tuple[str, CommandDescriptor]] = []
    for (alias_noun, alias_verb), canonical in sorted(tree.aliases.items()):
        if alias_noun != noun:
            continue
        descriptor = tree.commands.get(canonical, None)
        if descriptor is not None:
            pairs.append((alias_verb, descriptor))
    rtnval = pairs
    return rtnval


def lookup_command(
        *,
        tree: CommandTree,
        noun: str,
        verb: str
    ) -> Optional[CommandDescriptor]:
    """
        Return the :class:`CommandDescriptor` for ``(noun, verb)``,
        accepting ``_`` / ``-``, singular / plural nouns, and aliases.

        :param tree: Parsed :class:`CommandTree`.
        :param noun: First positional after ``pyc``.
        :param verb: Second positional after ``pyc <noun>``.

        :returns: :class:`CommandDescriptor` or ``None`` on miss.
    """
    exact = tree.commands.get((noun, verb), None)
    if exact is not None:
        return exact
    normalized_verb = normalize_word(verb)
    for candidate in _noun_candidates(normalize_word(noun)):
        found = tree.commands.get((candidate, normalized_verb), None)
        if found is not None:
            return found
    for candidate in _noun_candidates(normalize_word(noun)):
        canonical = tree.aliases.get((candidate, normalized_verb), None)
        if canonical is not None:
            rtnval = tree.commands.get(canonical, None)
            return rtnval
    return None


__all__ = [
    "DEFAULT_API_BASE_PATH",
    "HTTP_METHODS",
    "PlannedCommand",
    "alias_nouns",
    "alias_verbs_for",
    "api_base_path",
    "build_command_tree",
    "canonical_nouns",
    "lookup_command",
    "normalize_word",
    "plan_command_names",
    "resolve_noun",
    "resolve_ref",
    "verbs_for",
]
