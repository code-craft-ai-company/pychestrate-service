"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_pack_load_report_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: What became of each installed extension pack is kept and listed (DOC-11).

.. moduleauthor:: Code Craft AI LLC

A pack that fails to load is logged and the service starts without it, so a person who installed a pack and sees none of its routes had
only the log to look at. The loader now keeps what it did, and ``GET /api/v1/ext`` lists each installed pack (name, entry point, whether it
loaded, the error if not) and whether loading packs is switched on.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os

from typing import Any, Callable, Dict, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.extensions import discovery
from ccai.pychestrate.webservice.plugin_api.restapi.v1 import catalog_routes
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


class _EntryPoint:
    """Stands in for an installed ``importlib.metadata.EntryPoint``."""

    def __init__(self, name: str, target: Any, value: str = "pack:register") -> None:
        self.name = name
        self.value = value
        self._target = target

    def load(self) -> Any:
        if isinstance(self._target, BaseException):
            raise self._target
        return self._target


class _Query:
    def get(self, key: str, default: Any = None) -> Any:
        return default


class _Request:
    def __init__(self) -> None:
        self.path = "/api/v1/ext"
        self.query_params = _Query()
        self.auth_principal = object()
        self.db_session = object()


class _Decision:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed


def _body(response: Any) -> Dict[str, Any]:
    raw = getattr(response, "body", None) or getattr(response, "_body", b"")
    return json.loads(raw.decode("utf-8"))


def _with_environment(changes: Dict[str, str], action: Callable[[], Any]) -> Any:
    saved = {key: os.environ.get(key) for key in changes}
    try:
        for key, value in changes.items():
            os.environ[key] = value
        return action()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _listing() -> Dict[str, Any]:
    patch = create_module_patch(rbac_evaluator, "check_permission")
    patch.activate().configure(side_effect=lambda *, db_session, principal, permission_key, now: _Decision(True))
    try:
        return _body(catalog_routes.handle_list_ext(_Request()))
    finally:
        patch.deactivate()


def test_the_report_names_each_pack_and_the_error_of_one_that_failed():
    """
    **Feature: extension pack load report (DOC-11)**
    **Property: after discovery the report lists every declared pack in name order with its entry point, whether it loaded and, for the one
    that raised, ``ExceptionType: message``; loading is reported as enabled.**
    """
    discovery.reset_load_report_for_testing()
    entries = [
        _EntryPoint("zeta", lambda: None, value="zeta_pack:register"),
        _EntryPoint("alpha", RuntimeError("no database driver"), value="alpha_pack:register"),
    ]
    entries.sort(key=lambda entry: entry.name)

    discovery.discover_and_register_extensions(entry_points=entries, strict=False)
    report = discovery.load_report()
    discovery.reset_load_report_for_testing()

    testbase.assert_equal(
        report,
        {
            "enabled": True,
            "packs": [
                {"name": "alpha", "target": "alpha_pack:register", "loaded": False, "error": "RuntimeError: no database driver"},
                {"name": "zeta", "target": "zeta_pack:register", "loaded": True, "error": ""},
            ],
        },
    )
    return


def test_turned_off_and_strict_and_not_yet_run_are_each_reported():
    """
    **Feature: extension pack load report (DOC-11)**
    **Property: with discovery switched off the report says so and lists nothing; in strict mode the packs seen before the failing one are
    kept (and the error is raised); before any discovery the report is enabled and empty; the report is a copy a caller cannot change.**
    """
    discovery.reset_load_report_for_testing()
    before = discovery.load_report()

    _with_environment(
        {discovery.LOAD_EXTENSIONS_VARIABLE: "0"},
        lambda: discovery.discover_and_register_extensions(entry_points=[_EntryPoint("skipped", lambda: None)]),
    )
    off = discovery.load_report()

    stopped = False
    try:
        discovery.discover_and_register_extensions(
            entry_points=[_EntryPoint("a-fine", lambda: None), _EntryPoint("b-broken", ValueError("bad manifest"))], strict=True,
        )
    except discovery.ExtensionLoadError:
        stopped = True
    strict = discovery.load_report()

    strict["packs"].append({"name": "intruder"})
    unchanged = len(discovery.load_report()["packs"])
    discovery.reset_load_report_for_testing()

    testbase.assert_equal(
        (before, off, stopped, [(pack["name"], pack["loaded"]) for pack in strict["packs"][:2]], unchanged),
        (
            {"enabled": True, "packs": []},
            {"enabled": False, "packs": []},
            True,
            [("a-fine", True), ("b-broken", False)],
            2,
        ),
    )
    return


def test_the_extension_listing_carries_the_packs():
    """
    **Feature: extension pack load report (DOC-11)**
    **Property: ``GET /api/v1/ext`` returns ``packs`` (each with name, target, loaded, error) and ``packs_enabled`` next to the routes, and
    reports ``packs_enabled`` false when discovery was off.**
    """
    discovery.reset_load_report_for_testing()
    discovery.discover_and_register_extensions(entry_points=[_EntryPoint("demo", RuntimeError("boom"), value="demo:register")], strict=False)
    with_pack = _listing()
    _with_environment({discovery.LOAD_EXTENSIONS_VARIABLE: "off"}, lambda: discovery.discover_and_register_extensions(entry_points=[]))
    switched_off = _listing()
    discovery.reset_load_report_for_testing()

    testbase.assert_equal(
        (
            with_pack["packs"], with_pack["packs_enabled"], "items" in with_pack and "total" in with_pack,
            switched_off["packs"], switched_off["packs_enabled"],
        ),
        (
            [{"name": "demo", "target": "demo:register", "loaded": False, "error": "RuntimeError: boom"}], True, True,
            [], False,
        ),
    )
    return
