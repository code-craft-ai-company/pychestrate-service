"""
.. module:: test_p27p_pyc_command_names_m3
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The OpenAPI-driven ``pyc`` command generator (audit
               finding CLI-05): explicit names, REST <-> CLI parity,
               parameters with their descriptions and types, and
               request bodies.

.. moduleauthor:: Code Craft AI LLC

The parity tests build the command tree from the real contract
(``specs/openapi/pychestrate.yaml``, served at
``/api/v1/_meta/openapi.json``) and fail the suite when an operation
has no command, two operations share a name, a name is malformed, an
explicit name points at an operation that no longer exists, or a path
parameter / query parameter / body cannot be given on the command
line.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import copy
import re

from typing import Any, Dict, List

from ccai import testbase

from ccai.pychestrate.cli import command_names, exit_codes, parser
from ccai.pychestrate.cli.commands import api as api_commands
from ccai.pychestrate.cli.context import CliContext
from ccai.testshared.factories.pyc.pyc_harness import (
    PycFakeServer,
    PycSandbox,
    load_real_openapi_document,
    run_pyc,
)


#: Options every generated command owns; no query parameter may use
#: one of these names.
_RESERVED_OPTION_NAMES = (
    "data", "from_file", "set", "wait", "wait_timeout", "wait_interval", "help", "h",
    "profile", "server_url", "timeout",
)

SMALL_DOCUMENT: Dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Pychestrate", "version": "9.9.9"},
    "servers": [{"url": "/api/v1"}],
    "components": {
        "parameters": {
            "PerPage": {
                "name": "per_page", "in": "query", "description": "Page size.",
                "schema": {"type": "integer", "default": 50},
            },
        },
        "requestBodies": {
            "WidgetBody": {
                "required": True,
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/WidgetCreate"}}},
            },
        },
        "schemas": {
            "Named": {
                "type": "object", "required": ["name"],
                "properties": {"name": {"type": "string", "description": "Widget name."}},
            },
            "WidgetCreate": {
                "allOf": [
                    {"$ref": "#/components/schemas/Named"},
                    {"type": "object", "properties": {"size": {"type": "integer"}}},
                ],
            },
        },
    },
    "paths": {
        "/widgets": {
            "get": {
                "operationId": "widgets_list", "tags": ["widgets"], "summary": "List widgets.",
                "parameters": [
                    {"$ref": "#/components/parameters/PerPage"},
                    {"name": "state", "in": "query", "schema": {"type": "string", "enum": ["ACTIVE", "RETIRED"]}},
                    {"name": "enabled_only", "in": "query", "schema": {"type": "boolean"}},
                    {"name": "owner", "in": "query", "required": True, "schema": {"type": "string"}},
                ],
            },
            "post": {
                "operationId": "widgets_create", "tags": ["widgets"], "summary": "Create a widget.",
                "requestBody": {"$ref": "#/components/requestBodies/WidgetBody"},
            },
        },
        "/widgets/{widget_id}": {
            "parameters": [
                {"name": "widget_id", "in": "path", "required": True, "description": "The widget's id."},
            ],
            "get": {"operationId": "widgets_read", "tags": ["widgets"], "summary": "Read a widget."},
            "patch": {"operationId": "widgets_patch", "tags": ["widgets"], "summary": "Patch a widget."},
        },
        "/widgets/{widget_id}:spin": {
            "post": {
                "operationId": "widgets_spin_now", "tags": ["widgets"],
                "x-cli": {"noun": "widgets", "verb": "spin"},
            },
        },
        "/gadgets/{gadget_id}": {
            "get": {"operationId": "gadgets_get", "tags": ["gadgets"]},
        },
        "/gadgets/{gadget_id}/read": {
            "get": {"operationId": "gadgets_read", "tags": ["gadgets"]},
        },
    },
}


def _real_tree():
    rtnval = parser.build_command_tree(openapi_document=load_real_openapi_document())
    return rtnval


def _real_operation_ids() -> List[str]:
    document = load_real_openapi_document()
    operation_ids = []
    for path_item in document["paths"].values():
        for method, operation in path_item.items():
            if method in parser.HTTP_METHODS and isinstance(operation, dict) and operation.get("operationId"):
                operation_ids.append(operation["operationId"])
    rtnval = operation_ids
    return rtnval


def _small_fetcher() -> Dict[str, Any]:
    rtnval = copy.deepcopy(SMALL_DOCUMENT)
    return rtnval


# ===========================================================================
# REST <-> CLI parity against the real contract
# ===========================================================================


def test_every_operation_of_the_contract_has_exactly_one_command():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: the operationIds behind the command tree are exactly
    the contract's operationIds, one command each.**
    """
    tree = _real_tree()
    command_ids = sorted(d.operation.operation_id for d in tree.commands.values())
    testbase.assert_equal(command_ids, sorted(_real_operation_ids()))
    return


def test_every_command_name_is_well_formed():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: every noun and verb is lower-case words joined by '-'
    (no spaces or underscores, unlike the old 'blast radius_guards_create').**
    """
    tree = _real_tree()
    malformed = [
        "{} {}".format(noun, verb) for (noun, verb) in tree.commands.keys()
        if not (command_names.is_well_formed_word(noun) and command_names.is_well_formed_word(verb))
    ]
    testbase.assert_equal(malformed, [])
    return


def test_no_command_needed_a_fallback_name():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: no two operations compete for a name, so none falls
    back to its raw operationId.**
    """
    plan = parser.plan_command_names(openapi_document=load_real_openapi_document())
    fallbacks = [entry.operation_id for entry in plan if entry.source == parser.NAMING_SOURCE_FALLBACK]
    testbase.assert_equal(fallbacks, [])
    return


def test_every_explicit_name_names_an_operation_of_the_contract():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: the explicit name table has no entry for an operation
    the contract no longer declares.**
    """
    stale = sorted(set(command_names.COMMAND_NAMES.keys()) - set(_real_operation_ids()))
    testbase.assert_equal(stale, [])
    return


def test_nouns_have_no_singular_plural_duplicates():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: no noun exists in both its singular and plural
    spelling (the old tree had both 'project' and 'projects').**
    """
    nouns = set(parser.canonical_nouns(tree=_real_tree()))
    duplicates = sorted(noun for noun in nouns if noun + "s" in nouns)
    testbase.assert_equal(duplicates, [])
    return


def test_every_path_placeholder_is_a_positional_argument():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: each command takes every {placeholder} of its REST path
    as a positional (the old generator dropped them for 150 of 209
    commands).**
    """
    mismatched = []
    for descriptor in _real_tree().commands.values():
        operation = descriptor.operation
        placeholders = tuple(re.findall(r"{([^}]+)}", operation.path_template))
        if placeholders != operation.path_param_names:
            mismatched.append(operation.operation_id)
    testbase.assert_equal(mismatched, [])
    return


def test_every_query_parameter_is_a_kebab_case_flag():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: each command's parser accepts every query parameter as
    a --kebab-case flag.**
    """
    import io  # noqa: E402

    ctx = CliContext(stdout=io.StringIO(), stderr=io.StringIO(), stdin=io.StringIO(), environ={})
    missing = []
    for descriptor in _real_tree().commands.values():
        command_parser = api_commands.build_command_parser(ctx=ctx, descriptor=descriptor)
        known = set(command_parser._option_string_actions.keys())
        for name in descriptor.operation.query_param_names:
            if api_commands.flag_for(name) not in known:
                missing.append("{} {}".format(descriptor.operation.operation_id, name))
    testbase.assert_equal(missing, [])
    return


def test_every_operation_with_a_body_takes_body_options():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: every operation that declares a request body accepts
    --data, --from-file and --set.**
    """
    import io  # noqa: E402

    ctx = CliContext(stdout=io.StringIO(), stderr=io.StringIO(), stdin=io.StringIO(), environ={})
    missing = []
    for descriptor in _real_tree().commands.values():
        if descriptor.operation.has_request_body is False:
            continue
        command_parser = api_commands.build_command_parser(ctx=ctx, descriptor=descriptor)
        known = set(command_parser._option_string_actions.keys())
        if not {"--data", "--from-file", "--set"}.issubset(known):
            missing.append(descriptor.operation.operation_id)
    testbase.assert_equal(missing, [])
    return


def test_no_query_parameter_collides_with_a_pyc_option():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: no query parameter of the contract is named like an
    option pyc itself owns (--data, --set, --wait, --profile ...).**
    """
    collisions = []
    for descriptor in _real_tree().commands.values():
        for name in descriptor.operation.query_param_names:
            if name in _RESERVED_OPTION_NAMES:
                collisions.append("{} {}".format(descriptor.operation.operation_id, name))
    testbase.assert_equal(collisions, [])
    return


def test_rpa_job_trigger_takes_the_project_and_the_specification():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: 'pyc rpa-jobs trigger' takes PROJECT_ID and SPEC_ID
    (the audit found 'rpa jobs_trigger' captured neither).**
    """
    descriptor = _real_tree().commands[("rpa-jobs", "trigger")]
    testbase.assert_equal(descriptor.operation.path_param_names, ("project_id", "spec_id"))
    return


def test_renamed_commands_keep_their_derived_spelling():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: the tag + operationId spelling of a renamed command
    ('pyc rpa jobs-trigger') still reaches it.**
    """
    descriptor = parser.lookup_command(tree=_real_tree(), noun="rpa", verb="jobs-trigger")
    testbase.assert_equal(descriptor.operation.operation_id, "rpa_jobs_trigger")
    return


# ===========================================================================
# Naming rules
# ===========================================================================


def test_x_cli_extension_names_the_command():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: an operation's x-cli extension ({noun, verb}) is its
    command name.**
    """
    tree = parser.build_command_tree(openapi_document=_small_fetcher())
    testbase.assert_equal(tree.commands[("widgets", "spin")].operation.operation_id, "widgets_spin_now")
    return


def test_explicit_table_names_a_command():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: an operationId in the explicit table gets the table's
    name (rpa_jobs_trigger -> 'rpa-jobs trigger').**
    """
    document = {
        "paths": {"/rpa/specs/{spec_id}/trigger": {"post": {"operationId": "rpa_jobs_trigger", "tags": ["rpa"]}}},
    }
    tree = parser.build_command_tree(openapi_document=document)
    testbase.assert_equal(list(tree.commands.keys()), [("rpa-jobs", "trigger")])
    return


def test_read_is_spelled_get_when_the_verb_is_free():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: a derived 'read' verb is spelled 'get', with 'read' kept
    as an alias.**
    """
    tree = parser.build_command_tree(openapi_document=_small_fetcher())
    testbase.assert_equal(
        (("widgets", "get") in tree.commands, tree.aliases.get(("widgets", "read"))),
        (True, ("widgets", "get")),
    )
    return


def test_patch_is_spelled_update():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: a derived 'patch' verb is spelled 'update'.**
    """
    tree = parser.build_command_tree(openapi_document=_small_fetcher())
    testbase.assert_equal(tree.commands[("widgets", "update")].operation.operation_id, "widgets_patch")
    return


def test_standard_spelling_yields_to_a_real_verb():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: when a noun already has a 'get' operation, another
    operation's 'read' verb stays 'read'.**
    """
    tree = parser.build_command_tree(openapi_document=_small_fetcher())
    testbase.assert_equal(
        (tree.commands[("gadgets", "get")].operation.operation_id,
         tree.commands[("gadgets", "read")].operation.operation_id),
        ("gadgets_get", "gadgets_read"),
    )
    return


# ===========================================================================
# Parameters and bodies
# ===========================================================================


def test_parameter_references_keep_their_description_and_default():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: a $ref'd query parameter keeps its description, type and
    server default.**
    """
    tree = parser.build_command_tree(openapi_document=_small_fetcher())
    parameter = tree.commands[("widgets", "list")].operation.find_parameter("per_page")
    testbase.assert_equal(
        (parameter.description, parameter.value_type, parameter.default),
        ("Page size.", "integer", "50"),
    )
    return


def test_request_body_references_and_allof_are_resolved():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: a body given by $ref to components.requestBodies with an
    allOf schema lists every field, with the required ones marked.**
    """
    tree = parser.build_command_tree(openapi_document=_small_fetcher())
    operation = tree.commands[("widgets", "create")].operation
    testbase.assert_equal(
        [(body_field.name, body_field.required) for body_field in operation.body_fields],
        [("name", True), ("size", False)],
    )
    return


def test_help_shows_kebab_case_flags_with_descriptions():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: --help lists '--per-page N' with the parameter's
    description and default, not a bare snake_case 'Query parameter
    per_page'.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        sandbox.cache_command_list(document=_small_fetcher())
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["widgets", "list", "--help"], opener=PycFakeServer())
        testbase.assert_equal(
            (rc, "--per-page N" in out, "Page size. Server default: 50." in out, "--per_page" in out),
            (exit_codes.EXIT_OK, True, True, False),
        )
    finally:
        sandbox.close()
    return


def test_help_names_the_rest_endpoint():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: a command's --help names its method, full path and
    operationId.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        sandbox.cache_command_list(document=_small_fetcher())
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["widgets", "get", "--help"], opener=PycFakeServer())
        testbase.assert_equal("GET /api/v1/widgets/{widget_id}  (operationId widgets_read)" in out, True)
    finally:
        sandbox.close()
    return


def test_help_lists_the_request_body_fields():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: a command with a body lists its fields (type, required)
    under --help.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        sandbox.cache_command_list(document=_small_fetcher())
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["widgets", "create", "--help"], opener=PycFakeServer())
        testbase.assert_equal(
            ("request body fields" in out, "string, required -- Widget name." in out),
            (True, True),
        )
    finally:
        sandbox.close()
    return


def test_integer_query_value_is_checked_before_sending():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: a non-integer --per-page exits 2 and sends nothing.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer()
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["widgets", "list", "--owner", "me", "--per-page", "ten"],
                                opener=server, openapi_fetcher=_small_fetcher)
        testbase.assert_equal(
            (rc, "invalid int value" in err, server.paths()),
            (exit_codes.EXIT_USAGE_ERROR, True, []),
        )
    finally:
        sandbox.close()
    return


def test_enumerated_query_value_matches_without_case():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: '--state active' sends the document's spelling
    'state=ACTIVE'.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer({("GET", "/api/v1/widgets"): {"items": []}})
        run_pyc(sandbox=sandbox, argv=["widgets", "list", "--owner", "me", "--state", "active"],
                opener=server, openapi_fetcher=_small_fetcher)
        testbase.assert_equal(server.requests[-1]["query"], "state=ACTIVE&owner=me")
    finally:
        sandbox.close()
    return


def test_enumerated_query_value_outside_the_choices_is_rejected():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: a --state value the document does not allow exits 2
    listing the allowed values, and sends nothing.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer()
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["widgets", "list", "--owner", "me", "--state", "gone"],
                                opener=server, openapi_fetcher=_small_fetcher)
        testbase.assert_equal(
            (rc, "ACTIVE" in err, server.paths()), (exit_codes.EXIT_USAGE_ERROR, True, [])
        )
    finally:
        sandbox.close()
    return


def test_boolean_query_value_is_normalized():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: '--enabled-only yes' sends enabled_only=true.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer({("GET", "/api/v1/widgets"): {"items": []}})
        run_pyc(sandbox=sandbox, argv=["widgets", "list", "--owner", "me", "--enabled-only", "yes"],
                opener=server, openapi_fetcher=_small_fetcher)
        testbase.assert_equal(server.requests[-1]["query"], "enabled_only=true&owner=me")
    finally:
        sandbox.close()
    return


def test_required_query_parameter_is_enforced():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: leaving out a query parameter the contract requires
    exits 2 naming its flag, and sends nothing.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer()
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["widgets", "list"],
                                opener=server, openapi_fetcher=_small_fetcher)
        testbase.assert_equal(
            (rc, "--owner" in err, server.paths()), (exit_codes.EXIT_USAGE_ERROR, True, [])
        )
    finally:
        sandbox.close()
    return


def test_from_file_sends_the_file_as_the_body():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: --from-file PATH sends the file's JSON as the body.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        body_file = sandbox.root / "widget.json"
        body_file.write_text('{"name": "from-file", "size": 3}', encoding="utf-8")
        server = PycFakeServer({("POST", "/api/v1/widgets"): {"widget_id": "w-1"}})
        run_pyc(sandbox=sandbox, argv=["widgets", "create", "--from-file", str(body_file)],
                opener=server, openapi_fetcher=_small_fetcher)
        testbase.assert_equal(server.requests[-1]["body"], {"name": "from-file", "size": 3})
    finally:
        sandbox.close()
    return


def test_from_file_dash_reads_standard_input():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: --from-file - sends standard input's JSON as the body.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer({("POST", "/api/v1/widgets"): {"widget_id": "w-1"}})
        run_pyc(sandbox=sandbox, argv=["widgets", "create", "--from-file", "-"],
                opener=server, openapi_fetcher=_small_fetcher, stdin_text='{"name": "piped"}')
        testbase.assert_equal(server.requests[-1]["body"], {"name": "piped"})
    finally:
        sandbox.close()
    return


def test_set_overrides_fields_of_the_file_body():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: --set applied after --from-file overrides that field.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        body_file = sandbox.root / "widget.json"
        body_file.write_text('{"name": "a", "size": 3}', encoding="utf-8")
        server = PycFakeServer({("POST", "/api/v1/widgets"): {"widget_id": "w-1"}})
        run_pyc(sandbox=sandbox, argv=["widgets", "create", "--from-file", str(body_file), "--set", "size=5"],
                opener=server, openapi_fetcher=_small_fetcher)
        testbase.assert_equal(server.requests[-1]["body"], {"name": "a", "size": 5})
    finally:
        sandbox.close()
    return


def test_data_and_from_file_together_is_a_usage_error():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: giving both --data and --from-file exits 2 and sends
    nothing.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer()
        rc, _out, _err = run_pyc(
            sandbox=sandbox, argv=["widgets", "create", "--data", "{}", "--from-file", "-"],
            opener=server, openapi_fetcher=_small_fetcher,
        )
        testbase.assert_equal((rc, server.paths()), (exit_codes.EXIT_USAGE_ERROR, []))
    finally:
        sandbox.close()
    return


def test_missing_required_body_is_a_usage_error():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: a command whose body has required fields, run with no
    body at all, exits 2 naming the fields and sends nothing.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer()
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["widgets", "create"],
                                opener=server, openapi_fetcher=_small_fetcher)
        testbase.assert_equal(
            (rc, "needs a request body with name" in err, server.paths()),
            (exit_codes.EXIT_USAGE_ERROR, True, []),
        )
    finally:
        sandbox.close()
    return


def test_unknown_set_field_is_noted_with_a_suggestion():
    """
    **Feature: pyc command generator (CLI-05)**
    **Property: --set with a field the body does not declare prints a
    note suggesting the closest field (the request is still sent).**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer({("POST", "/api/v1/widgets"): {"widget_id": "w-1"}})
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["widgets", "create", "--set", "nmae=x"],
                                opener=server, openapi_fetcher=_small_fetcher)
        testbase.assert_equal(
            (rc, "'nmae' is not a field" in err, "did you mean 'name'?" in err),
            (exit_codes.EXIT_OK, True, True),
        )
    finally:
        sandbox.close()
    return
