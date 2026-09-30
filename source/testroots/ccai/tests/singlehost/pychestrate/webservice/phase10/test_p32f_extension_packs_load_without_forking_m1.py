"""
.. module:: test_p32f_extension_packs_load_without_forking_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: An installed extension pack loads without editing the service (DOC-11).

.. moduleauthor:: Code Craft AI LLC

The extension guide said teams could add drivers, strategies and resource kinds
"without forking the service", and then told them to edit the service's bootstrap
code to call their pack's ``register()``. The service now finds installed packs
that declare the ``pychestrate.extensions`` entry point and calls each pack's
function at start, and the pack generator produces a pack that is wired that
way (its package directories are importable, its manifest is valid YAML, its
``pyproject.toml`` declares the entry point). These tests cover the loader and the
generated pack, and run the service's own registration in a child process with
a pack installed.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import tomllib

from pathlib import Path
from typing import Any, Callable, Dict, List

import yaml

from ccai import testbase

from ccai.pychestrate.webservice.extension.pack_template import (
    PackGenerationRequest,
    PackGenerator,
    normalize_pack_name,
)
from ccai.pychestrate.webservice.extensions import discovery


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


class _CcaiStyleError(BaseException):
    """ccai's errors derive from BaseException, so ``except Exception`` misses them."""


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


def test_every_declared_pack_is_registered_in_name_order():
    """
    **Feature: extension packs without forking (DOC-11)**
    **Property: each declared pack's function is called once, in the order of the
    entry-point names, and each is reported as loaded.**
    """
    calls: List[str] = []
    entries = [
        _EntryPoint("zeta", lambda: calls.append("zeta")),
        _EntryPoint("alpha", lambda: calls.append("alpha")),
    ]
    entries.sort(key=lambda entry: entry.name)

    results = discovery.discover_and_register_extensions(entry_points=entries, strict=False)

    testbase.assert_equal((calls, [(result.name, result.loaded) for result in results]), (["alpha", "zeta"], [("alpha", True), ("zeta", True)]))
    return


def test_a_pack_that_fails_does_not_stop_the_others_and_the_failure_is_reported():
    """
    **Feature: extension packs without forking (DOC-11)**
    **Property: a pack that raises, one whose entry point does not import, one
    that points at something that is not callable, and one that raises a
    BaseException (as ccai's errors do) are each reported as failed with the
    error, and the pack after them still loads.**
    """
    calls: List[str] = []

    def _raises() -> None:
        raise ValueError("bad config")

    def _raises_base() -> None:
        raise _CcaiStyleError("semantic")

    entries = [
        _EntryPoint("a-raises", _raises),
        _EntryPoint("b-import", ImportError("no module named vendor_sdk")),
        _EntryPoint("c-not-callable", "just a string"),
        _EntryPoint("d-base", _raises_base),
        _EntryPoint("e-good", lambda: calls.append("e-good")),
    ]

    results = discovery.discover_and_register_extensions(entry_points=entries, strict=False)

    testbase.assert_equal(
        ([(result.name, result.loaded) for result in results], [result.error.split(":")[0] for result in results], calls),
        (
            [("a-raises", False), ("b-import", False), ("c-not-callable", False), ("d-base", False), ("e-good", True)],
            ["ValueError", "ImportError", "TypeError", "_CcaiStyleError", ""],
            ["e-good"],
        ),
    )
    return


def test_strict_mode_stops_at_the_first_failure_and_ctrl_c_is_never_swallowed():
    """
    **Feature: extension packs without forking (DOC-11)**
    **Property: with PYCHESTRATE_EXTENSIONS_STRICT set (or strict=True) the first pack
    that fails raises ExtensionLoadError naming it, and the packs after it are not
    loaded; a KeyboardInterrupt in a pack is never caught.**
    """
    calls: List[str] = []

    def _raises() -> None:
        raise ValueError("bad config")

    entries = [_EntryPoint("a-good", lambda: calls.append("a-good")), _EntryPoint("b-bad", _raises), _EntryPoint("c-good", lambda: calls.append("c-good"))]

    def _strict_by_variable() -> str:
        try:
            discovery.discover_and_register_extensions(entry_points=entries)
        except discovery.ExtensionLoadError as xcpt:
            return str(xcpt)
        return "no error"

    message = _with_environment({discovery.STRICT_EXTENSIONS_VARIABLE: "1"}, _strict_by_variable)

    interrupted = False

    def _interrupt() -> None:
        raise KeyboardInterrupt()

    try:
        discovery.discover_and_register_extensions(entry_points=[_EntryPoint("stop", _interrupt)], strict=False)
    except KeyboardInterrupt:
        interrupted = True

    testbase.assert_equal(
        (calls, "b-bad" in message and "PYCHESTRATE_EXTENSIONS_STRICT" in message and "ValueError: bad config" in message, interrupted),
        (["a-good"], True, True),
    )
    return


def test_discovery_can_be_turned_off_and_strictness_reads_the_variable():
    """
    **Feature: extension packs without forking (DOC-11)**
    **Property: PYCHESTRATE_LOAD_EXTENSIONS=0 (false, no, off) loads nothing and any
    other value, or none, leaves discovery on; strict mode is on only for 1, true,
    yes or on.**
    """
    calls: List[str] = []
    entries = [_EntryPoint("a", lambda: calls.append("a"))]

    off = {word: _with_environment({discovery.LOAD_EXTENSIONS_VARIABLE: word}, discovery.discovery_enabled) for word in ("0", "false", "NO", " off ")}
    on = {word: _with_environment({discovery.LOAD_EXTENSIONS_VARIABLE: word}, discovery.discovery_enabled) for word in ("1", "true", "", "maybe")}
    disabled_results = _with_environment({discovery.LOAD_EXTENSIONS_VARIABLE: "0"}, lambda: discovery.discover_and_register_extensions(entry_points=entries))
    strict = {word: _with_environment({discovery.STRICT_EXTENSIONS_VARIABLE: word}, discovery.strict_mode) for word in ("1", "TRUE", "on", "0", "", "maybe")}

    testbase.assert_equal(
        (set(off.values()), set(on.values()), disabled_results, calls, strict),
        ({False}, {True}, [], [], {"1": True, "TRUE": True, "on": True, "0": False, "": False, "maybe": False}),
    )
    return


def test_with_no_pack_installed_discovery_finds_nothing():
    """
    **Feature: extension packs without forking (DOC-11)**
    **Property: the real lookup of installed entry points (group
    ``pychestrate.extensions``) runs and, with no pack installed, returns an empty
    list.**
    """
    testbase.assert_equal((discovery.EXTENSION_ENTRY_POINT_GROUP, discovery.discover_and_register_extensions()), ("pychestrate.extensions", []))
    return


def test_the_services_own_registration_calls_an_installed_pack():
    """
    **Feature: extension packs without forking (DOC-11)**
    **Property: when a pack is installed (an entry point in the group is
    visible), the service's ``register_service_extensions`` calls it, after the
    in-tree extensions and before the plugin catalog is built.**
    """
    script = r"""
import json
import importlib.metadata as md

calls = []

class Pack:
    name = "demo"
    value = "demo:register"
    def load(self):
        return lambda: calls.append("demo")

original = md.entry_points
def fake(**kwargs):
    if kwargs.get("group") == "pychestrate.extensions":
        return [Pack()]
    return original(**kwargs)
md.entry_points = fake

import app_pychestrate_main as service
service.register_service_extensions()
print("CALLS_JSON=" + json.dumps(calls))
"""
    root = Path(os.path.dirname(os.path.abspath(__file__)))
    while not (root / "specs").is_dir() and root != root.parent:
        root = root.parent
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([entry for entry in sys.path if entry])
    env.pop(discovery.LOAD_EXTENSIONS_VARIABLE, None)
    done = subprocess.run([sys.executable, "-c", script], cwd=str(root), env=env, capture_output=True, text=True, timeout=300)
    lines = [line for line in done.stdout.splitlines() if line.startswith("CALLS_JSON=")]

    testbase.assert_equal((done.returncode, [json.loads(line[len("CALLS_JSON="):]) for line in lines]), (0, [["demo"]]), done.stderr[-1500:])
    return


def _generate(*, name: str, target: Path, protocols: tuple = ("notification_channel",), resources: tuple = ()) -> Path:
    request = PackGenerationRequest(
        name=name, normalized_name=normalize_pack_name(raw=name), author="Test Author", license="MIT",
        protocol_names=protocols, resource_base_names=resources, target_dir=target,
    )
    return PackGenerator(corpus_root=None).generate(request=request, template_version=None)


def test_a_generated_pack_has_importable_directories_and_a_valid_manifest():
    """
    **Feature: extension packs without forking (DOC-11)**
    **Property: for a hyphenated name ("demo-notes") the generated package
    directories use underscores (a directory with a hyphen cannot be imported),
    and the manifest is valid YAML listing the protocol with its implementation
    module (with no protocols or resources it lists nothing, as an empty list).**
    """
    with tempfile.TemporaryDirectory() as parent:
        pack = _generate(name="demo-notes", target=Path(parent), protocols=("notification_channel",), resources=("ResourceKindExtension",))
        bare = _generate(name="empty-pack", target=Path(parent), protocols=(), resources=())
        source_parts = [part for path in (pack / "source").rglob("*") for part in path.relative_to(pack / "source").parts]
        manifest = yaml.safe_load((pack / "pychestrate_ext.yaml").read_text(encoding="utf-8"))
        bare_manifest = yaml.safe_load((bare / "pychestrate_ext.yaml").read_text(encoding="utf-8"))
        factory = pack / "source" / "packages" / "ccai" / "factories" / "pychestrate" / "demo_notes" / "sample_factory.py"

        testbase.assert_equal(
            (
                pack.name, any("-" in part for part in source_parts), factory.is_file(),
                manifest["factory_protocols"], manifest["resource_extensions"],
                bare_manifest["factory_protocols"], bare_manifest["resource_extensions"],
            ),
            (
                "pychestrate-ext-demo-notes", False, True,
                [{"name": "notification_channel", "implementation": "ccai.factories.pychestrate.demo_notes.sample_factory"}],
                [{"base": "ResourceKindExtension", "module": "ccai.extensions.pychestrate.demo_notes.sample_resource"}],
                [], [],
            ),
        )
    return


def test_a_generated_pack_declares_the_entry_point_and_the_service_can_load_it():
    """
    **Feature: extension packs without forking (DOC-11)**
    **Property: the generated ``pyproject.toml`` declares the entry point in the group
    ``pychestrate.extensions``, its target module exists in the tree, and loading
    that target the way the service does (import, then call ``register``) succeeds and
    registers nothing (the scaffold's sample factory raises, so it must not be
    registered).**
    """
    with tempfile.TemporaryDirectory() as parent:
        pack = _generate(name="demo-notes", target=Path(parent))
        project = tomllib.loads((pack / "pyproject.toml").read_text(encoding="utf-8"))
        declared = project["tool"]["poetry"]["plugins"]["pychestrate.extensions"]
        target = declared["demo-notes"]
        module_name, function_name = target.split(":")
        module_file = pack / "source" / "packages" / Path(*module_name.split(".")).with_suffix(".py")

        spec = importlib.util.spec_from_file_location("generated_demo_notes_register", module_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        entry = _EntryPoint("demo-notes", getattr(module, function_name), value=target)
        results = discovery.discover_and_register_extensions(entry_points=[entry], strict=True)

        testbase.assert_equal(
            (declared, module_file.is_file(), [(result.name, result.loaded) for result in results]),
            ({"demo-notes": "ccai.extensions.pychestrate.demo_notes.register:register"}, True, [("demo-notes", True)]),
        )
    return


def test_the_pychestrate_admin_command_is_a_console_script():
    """
    **Feature: extension packs without forking (DOC-11)**
    **Property: ``pyproject.toml`` declares the ``pychestrate-admin`` console script
    (the command the pack generator, the backup commands and the guides name), it
    points at ``console_main``, which exists, and calling it with ``--help`` exits 0
    instead of failing on ``main``'s keyword-only argument.**
    """
    from ccai.pychestrate.admin import __main__ as admin_main

    root = Path(os.path.dirname(os.path.abspath(__file__)))
    while not (root / "pyproject.toml").is_file() and root != root.parent:
        root = root.parent
    scripts = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["poetry"]["scripts"]

    saved = sys.argv
    exit_code = None
    try:
        sys.argv = ["pychestrate-admin", "--help"]
        try:
            admin_main.console_main()
        except SystemExit as xcpt:
            exit_code = xcpt.code
    finally:
        sys.argv = saved

    testbase.assert_equal(
        (scripts.get("pychestrate-admin"), callable(getattr(admin_main, "console_main", None)), exit_code),
        ("ccai.pychestrate.admin.__main__:console_main", True, 0),
    )
    return


def test_the_real_lookup_reads_an_installed_packs_entry_point():
    """
    **Feature: extension packs without forking (DOC-11)**
    **Property: a pack that is really installed (a ``*.dist-info`` directory with an
    ``entry_points.txt`` in the group ``pychestrate.extensions``, on the import path)
    is found by the loader's own lookup, imported and called, with no entry points
    passed in.**
    """
    with tempfile.TemporaryDirectory() as parent:
        site = Path(parent)
        (site / "demo_installed_pack.py").write_text("CALLS = []\n\ndef register():\n    CALLS.append('registered')\n", encoding="utf-8")
        info = site / "demo_installed_pack-0.1.0.dist-info"
        info.mkdir()
        (info / "METADATA").write_text("Metadata-Version: 2.1\nName: demo-installed-pack\nVersion: 0.1.0\n", encoding="utf-8")
        (info / "entry_points.txt").write_text("[pychestrate.extensions]\ndemo-installed = demo_installed_pack:register\n", encoding="utf-8")

        sys.path.insert(0, str(site))
        try:
            results = discovery.discover_and_register_extensions(strict=True)
            calls = list(sys.modules["demo_installed_pack"].CALLS)
        finally:
            sys.path.remove(str(site))
            sys.modules.pop("demo_installed_pack", None)

    testbase.assert_equal(
        ([(result.name, result.target, result.loaded) for result in results], calls),
        ([("demo-installed", "demo_installed_pack:register", True)], ["registered"]),
    )
    return
