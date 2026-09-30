"""
.. module:: test_p32a_embed_routes_off_by_default_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The unfinished embeddable-views routes are not served unless asked for (ORC-07).

.. moduleauthor:: Code Craft AI LLC

The embeddable-views surface answered 200 for a catalog of five view kinds
that could not be embedded: signing a view's URL was unreachable (405), the
embed page loaded no script, four of the five component tags were defined by no
bundle, and the scopes the catalog declares are not in the permission
catalog. The service now registers the routes only when
``PYCHESTRATE_EMBED_ENABLED`` is set, and the OpenAPI document marks the
operations ``planned``. The routes are read in a child process because
registering every route imports the whole service.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import subprocess
import sys

from typing import Dict, List, Optional

import yaml

from ccai import testbase

from ccai.pychestrate.webservice.embed.restapi.v1 import embed_routes


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


def _repo_root() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "specs")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return current


def _embed_routes_registered(*, enabled: Optional[str]) -> List[str]:
    """The embed routes the application registers, as ``"METHOD path"``, with the switch set to ``enabled`` (``None`` removes it)."""
    env: Dict[str, str] = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([entry for entry in sys.path if entry])
    env.pop(embed_routes.EMBED_ENABLED_VARIABLE, None)
    if enabled is not None:
        env[embed_routes.EMBED_ENABLED_VARIABLE] = enabled
    done = subprocess.run(
        [sys.executable, "-c", ENUMERATE_ROUTES], cwd=_repo_root(), env=env, capture_output=True, text=True, timeout=300,
    )
    lines = [line for line in done.stdout.splitlines() if line.startswith("ROUTES_JSON=")]
    testbase.assert_equal((done.returncode, len(lines)), (0, 1), done.stderr[-2000:])
    routes = json.loads(lines[0][len("ROUTES_JSON="):])
    return ["{} {}".format(method, path) for method, path in routes if path.startswith("/api/v1/embed") or path.startswith("/embed")]


def test_the_application_serves_no_embed_route_unless_the_switch_is_on():
    """
    **Feature: hide unfinished embeds (ORC-07)**
    **Property: with PYCHESTRATE_EMBED_ENABLED unset or 0 the application
    registers no /api/v1/embed or /embed route; with it set to 1 it registers the
    catalog list, the sign route and the serving route.**
    """
    off = _embed_routes_registered(enabled=None)
    zero = _embed_routes_registered(enabled="0")
    on = _embed_routes_registered(enabled="1")

    testbase.assert_equal(
        (off, zero, on),
        (
            [],
            [],
            [
                "GET /api/v1/embed/views",
                "GET /embed/{view_key}",
                "POST /api/v1/embed/views/{view_key}:sign",
            ],
        ),
    )
    return


def test_only_a_plain_yes_turns_the_switch_on():
    """
    **Feature: hide unfinished embeds (ORC-07)**
    **Property: 1, true, yes and on (any case, padded) turn the embed routes
    on; unset, empty, 0, false and anything else leave them off.**
    """
    saved = os.environ.get(embed_routes.EMBED_ENABLED_VARIABLE)
    seen: Dict[str, bool] = {}
    try:
        for value in ("1", "true", "YES", " On ", "", "0", "false", "off", "maybe", "2"):
            os.environ[embed_routes.EMBED_ENABLED_VARIABLE] = value
            seen[value] = embed_routes.embed_views_enabled()
        os.environ.pop(embed_routes.EMBED_ENABLED_VARIABLE, None)
        seen["<unset>"] = embed_routes.embed_views_enabled()
    finally:
        if saved is None:
            os.environ.pop(embed_routes.EMBED_ENABLED_VARIABLE, None)
        else:
            os.environ[embed_routes.EMBED_ENABLED_VARIABLE] = saved

    testbase.assert_equal(
        seen,
        {
            "1": True, "true": True, "YES": True, " On ": True,
            "": False, "0": False, "false": False, "off": False, "maybe": False, "2": False, "<unset>": False,
        },
    )
    return


def test_the_openapi_document_says_the_embed_operations_are_not_served_yet():
    """
    **Feature: hide unfinished embeds (ORC-07)**
    **Property: the list and sign operations under /embed are flagged
    x-pychestrate-status: planned, so a client generated from the document does
    not offer calls that 404.**
    """
    with open(os.path.join(_repo_root(), "specs", "openapi", "pychestrate.yaml"), encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    flagged = {
        "{} {}".format(method.upper(), path): operation.get("x-pychestrate-status")
        for path, item in document["paths"].items() if path.startswith("/embed")
        for method, operation in item.items() if method in ("get", "post")
    }

    testbase.assert_equal(
        flagged,
        {"GET /embed/views": "planned", "POST /embed/views/{view_key}:sign": "planned"},
    )
    return
