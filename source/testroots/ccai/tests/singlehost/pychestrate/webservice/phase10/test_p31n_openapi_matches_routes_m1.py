"""
.. module:: test_p31n_openapi_matches_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The OpenAPI document and the routes the service registers
               describe the same API (DOC-06).

.. moduleauthor:: Code Craft AI LLC

The document called itself the single source of truth for ``/api/v1``
while 77 operations that the service serves still carried
``x-pychestrate-status: planned``, 11 served operations were missing
(release templates, run variables, cancelling a run, the UI metrics
beacon) and two documented operations had no route. A client generated
from it offered calls that 404 and hid calls that work.

The routes are read in a child process: registering every route imports
the whole service and must not run inside a process where another test
has already started the application.

The document also had no examples, and a first pass at adding them showed
why it needed some: 12 of the 20 most used operations answered with a
different shape than their schema said (a bare array where the document
said a page, ``state`` where it said ``status``, upper-case enums). Every
example is now a body captured from the service, and a test holds each
one to its schema so the two cannot drift apart again.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Set, Tuple

import jsonschema
import yaml
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from ccai import testbase


API_PREFIX: str = "/api/v1"

#: Child-process script: print every route the service registers.
ENUMERATE_ROUTES: str = r"""
import json
import app_pychestrate_main as service
service.register_service_extensions()
found = []
for descriptor in service.app._pending_routes:
    for method in descriptor.methods:
        found.append([method.upper(), descriptor.path])
print("ROUTES_JSON=" + json.dumps(sorted(found)))
"""

METHODS: Tuple[str, ...] = ("get", "put", "post", "patch", "delete")

_CACHE: Dict[str, Any] = {}


def _normalize(path: str) -> str:
    rtnval = re.sub(r"\{[^}]*\}", "{}", path)
    return rtnval


def _repo_root() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "specs")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return current


def _registered() -> Set[Tuple[str, str]]:
    """
        Every ``(METHOD, path)`` the service registers under
        ``/api/v1``, path parameters normalized, prefix removed.
    """
    if "registered" not in _CACHE:
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([entry for entry in sys.path if entry])
        done = subprocess.run(
            [sys.executable, "-c", ENUMERATE_ROUTES],
            cwd=_repo_root(), env=env, capture_output=True, text=True, timeout=300,
        )
        lines = [line for line in done.stdout.splitlines() if line.startswith("ROUTES_JSON=")]
        testbase.assert_equal(
            (done.returncode, len(lines)), (0, 1), done.stderr[-2000:],
        )
        routes: List[List[str]] = json.loads(lines[0][len("ROUTES_JSON="):])
        found: Set[Tuple[str, str]] = set()
        for method, path in routes:
            if path.startswith(API_PREFIX + "/"):
                found.add((method, _normalize(path[len(API_PREFIX):])))
        _CACHE["registered"] = found
    return _CACHE["registered"]


def _documented() -> Tuple[Set[Tuple[str, str]], Set[Tuple[str, str]]]:
    """
        ``(all documented operations, the ones flagged planned)``,
        each as ``(METHOD, normalized path)``.
    """
    if "documented" not in _CACHE:
        spec_path = os.path.join(_repo_root(), "specs", "openapi", "pychestrate.yaml")
        with open(spec_path, "r", encoding="utf-8") as handle:
            document = yaml.safe_load(handle)
        every: Set[Tuple[str, str]] = set()
        planned: Set[Tuple[str, str]] = set()
        for path, item in document["paths"].items():
            for method, operation in item.items():
                if method not in METHODS:
                    continue
                key = (method.upper(), _normalize(path))
                every.add(key)
                if operation.get("x-pychestrate-status", None) == "planned":
                    planned.add(key)
        _CACHE["documented"] = (every, planned)
    return _CACHE["documented"]


def _show(entries: Set[Tuple[str, str]]) -> List[str]:
    return ["{} {}".format(method, path) for method, path in sorted(entries)]


def test_every_route_the_service_serves_is_documented():
    """
    **Feature: OpenAPI document (DOC-06)**
    **Property: no operation under /api/v1 is served without being in
    the document.**
    """
    every, _planned = _documented()
    testbase.assert_equal(_show(_registered() - every), [])
    return


def test_every_documented_operation_is_served_or_flagged_planned():
    """
    **Feature: OpenAPI document (DOC-06)**
    **Property: an operation in the document that no route serves says
    so with x-pychestrate-status: planned.**
    """
    every, planned = _documented()
    testbase.assert_equal(_show(every - _registered() - planned), [])
    return


def test_no_served_operation_is_flagged_planned():
    """
    **Feature: OpenAPI document (DOC-06)**
    **Property: once an operation is served its planned flag is gone,
    so the flag keeps meaning "not served yet".**
    """
    _every, planned = _documented()
    testbase.assert_equal(_show(planned & _registered()), [])
    return


#: The document's own spec URI for resolving ``#/components/...`` references.
SPEC_URI: str = "urn:pychestrate-spec"

#: Operations that must carry an example. The ones an integrator meets
#: first: who am I, projects, enrolling a pod, tests, runs, health.
MINIMUM_OPERATIONS_WITH_EXAMPLES: int = 20


def _as_json_schema(node: Any) -> Any:
    """
        The document's schemas in the dialect the validator speaks:
        ``nullable: true`` (the OpenAPI 3.0 spelling the document uses)
        becomes a union with null, and references point at the document.
    """
    if isinstance(node, dict):
        nullable = node.get("nullable", None) is True
        rebuilt = {key: _as_json_schema(value) for key, value in node.items() if key != "nullable"}
        reference = rebuilt.get("$ref", None)
        if isinstance(reference, str) and reference.startswith("#/"):
            rebuilt["$ref"] = SPEC_URI + reference
        if nullable:
            rebuilt = {"anyOf": [rebuilt, {"type": "null"}]}
        return rebuilt
    if isinstance(node, list):
        return [_as_json_schema(value) for value in node]
    return node


def _examples() -> List[Tuple[str, Any, Any]]:
    """
        Every ``(label, schema, example)`` in the document: request
        bodies and responses, with ``$ref`` responses resolved.
    """
    spec_path = os.path.join(_repo_root(), "specs", "openapi", "pychestrate.yaml")
    with open(spec_path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    document = _as_json_schema(raw)
    found: List[Tuple[str, Any, Any]] = []
    for path, item in document["paths"].items():
        for method, operation in item.items():
            if method not in METHODS:
                continue
            media_types: List[Tuple[str, Dict[str, Any]]] = []
            body = operation.get("requestBody", None)
            if body is not None:
                for name, media in body.get("content", {}).items():
                    media_types.append(("request " + name, media))
            for code, response in operation.get("responses", {}).items():
                reference = response.get("$ref", None) if isinstance(response, dict) else None
                if reference is not None:
                    response = document["components"]["responses"][reference.split("/")[-1]]
                for name, media in response.get("content", {}).items():
                    media_types.append(("{} {}".format(code, name), media))
            for kind, media in media_types:
                if "example" in media and "schema" in media:
                    found.append(("{} {} {}".format(method.upper(), path, kind), media["schema"], media["example"]))
    _CACHE["document"] = document
    return found


def test_every_example_fits_its_schema():
    """
    **Feature: OpenAPI document (DOC-06)**
    **Property: each example in the document is valid against the schema
    beside it, so an example cannot show a body the schema forbids.**
    """
    examples = _examples()
    registry = Registry().with_resource(
        SPEC_URI, Resource.from_contents(_CACHE["document"], default_specification=DRAFT202012),
    )
    misfits: List[str] = []
    for label, schema, example in examples:
        validator = jsonschema.Draft202012Validator(schema, registry=registry)
        for problem in validator.iter_errors(example):
            misfits.append("{}: {} at /{}".format(label, str(problem.message)[:120], "/".join(str(step) for step in problem.absolute_path)))
    testbase.assert_equal(misfits, [])
    return


def test_the_most_used_operations_carry_examples():
    """
    **Feature: OpenAPI document (DOC-06)**
    **Property: at least twenty operations show an example request or
    response.**
    """
    labelled = {label.split(" ", 2)[0] + " " + label.split(" ", 2)[1] for label, _schema, _example in _examples()}
    testbase.assert_true(
        len(labelled) >= MINIMUM_OPERATIONS_WITH_EXAMPLES,
        "only {} operations have an example".format(len(labelled)),
    )
    return
