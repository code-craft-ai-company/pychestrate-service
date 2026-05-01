"""
.. module:: test_p10d_pack_template_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for E-extension-pack-template M1 (skeleton).

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import tempfile

from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from automojo import testbase

from automojo.errors.exceptions import ConfigurationError, SemanticError

from automojo.pychestrate.admin import __main__ as admin_main
from automojo.pychestrate.webservice.extension.pack_template import (
    PackGenerationRequest,
    PackGenerator,
    normalize_pack_name,
)
from automojo.pychestrate.webservice.extension.pack_template import cli as pack_cli
from automojo.pychestrate.webservice.extension.pack_template.corpus_loader import (
    builtin_corpus_root,
    discover_corpus_versions,
    load_template_manifest,
)


# ---------------------------------------------------------------------------
# T1.5 — normalize_pack_name
# ---------------------------------------------------------------------------

def test_normalize_pack_name_lowercases_and_replaces_underscores():
    """
    **Feature: E-extension-pack-template M1 (T1.5)**
    **Property: Mixed-case + underscored input lowercases and dash-separates.**
    """
    rtnval = normalize_pack_name(raw="My_Cool_Pack")
    testbase.assert_equal(rtnval, "my-cool-pack")
    return


def test_normalize_pack_name_collapses_repeated_dashes():
    """
    **Feature: E-extension-pack-template M1 (T1.5)**
    **Property: Runs of non-alphanumerics collapse to a single dash.**
    """
    rtnval = normalize_pack_name(raw="hello   world!!__cool")
    testbase.assert_equal(rtnval, "hello-world-cool")
    return


def test_normalize_pack_name_strips_non_ascii():
    """
    **Feature: E-extension-pack-template M1 (T1.5)**
    **Property: Non-ASCII characters are dropped after NFKD decompose.**
    """
    rtnval = normalize_pack_name(raw="café-bar")
    testbase.assert_equal(rtnval, "cafe-bar")
    return


def test_normalize_pack_name_prefixes_when_first_char_is_digit():
    """
    **Feature: E-extension-pack-template M1 (T1.5)**
    **Property: A leading digit triggers the 'ext-' prefix.**
    """
    rtnval = normalize_pack_name(raw="42-pack")
    testbase.assert_equal(rtnval, "ext-42-pack")
    return


def test_normalize_pack_name_is_idempotent():
    """
    **Feature: E-extension-pack-template M1 (T1.5)**
    **Property: normalize(normalize(x)) == normalize(x) across varied inputs.**
    """
    samples = [
        "MyPack",
        "my-pack",
        "weird _name__here",
        "café-bar",
        "42-pack",
        "ABC",
        "Already-OK",
    ]
    for sample in samples:
        once = normalize_pack_name(raw=sample)
        twice = normalize_pack_name(raw=once)
        testbase.assert_equal(twice, once)
    return


def test_normalize_pack_name_rejects_empty():
    """
    **Feature: E-extension-pack-template M1 (T1.5)**
    **Property: Empty / whitespace-only / non-alpha-reducible input raises SemanticError.**
    """
    raised = False
    try:
        normalize_pack_name(raw="   ")
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# T1.1 — corpus loader / version discovery
# ---------------------------------------------------------------------------

def test_corpus_loader_discovers_v1():
    """
    **Feature: E-extension-pack-template M1 (T1.1)**
    **Property: discover_corpus_versions returns at least the v1 baseline.**
    """
    versions = discover_corpus_versions(corpus_root=builtin_corpus_root())
    testbase.assert_equal(1 in versions, True)
    return


def test_corpus_manifest_v1_is_non_empty_and_includes_jinja_files():
    """
    **Feature: E-extension-pack-template M1 (T1.1 / T1.3)**
    **Property: v1 manifest contains at least one Jinja and one
    ``__NAME__``-templated path so the generator has something to render.**
    """
    manifest = load_template_manifest(corpus_root=builtin_corpus_root(), version=1)
    testbase.assert_equal(len(manifest.files) > 0, True)

    jinja_count = sum(1 for f in manifest.files if f.render_mode == "jinja")
    placeholder_count = sum(1 for f in manifest.files if "__NAME__" in f.relative_path)
    testbase.assert_equal(jinja_count > 0, True)
    testbase.assert_equal(placeholder_count > 0, True)
    return


# ---------------------------------------------------------------------------
# T1.3 — PackGenerator.generate
# ---------------------------------------------------------------------------

def _build_request(*, name: str, target: Path, protocols=("example_protocol",)):
    """
        Convenience helper constructing a fully-populated request.
    """
    normalized = normalize_pack_name(raw=name)
    rtnval = PackGenerationRequest(
        name=name,
        normalized_name=normalized,
        author="Test Author",
        license="MIT",
        protocol_names=tuple(protocols),
        resource_base_names=("ResourceKindExtension",),
        target_dir=target,
    )
    return rtnval


def test_generate_creates_pack_root_with_expected_layout():
    """
    **Feature: E-extension-pack-template M1 (T1.3)**
    **Property: PackGenerator.generate produces the documented files
    inside ``pychestrate-ext-<name>/``.**
    """
    with tempfile.TemporaryDirectory() as parent_str:
        parent = Path(parent_str)
        request = _build_request(name="example", target=parent)
        generator = PackGenerator(corpus_root=None)
        pack_root = generator.generate(request=request, template_version=None)

        testbase.assert_equal(pack_root.is_dir(), True)
        testbase.assert_equal(pack_root.name, "pychestrate-ext-example")
        testbase.assert_equal((pack_root / "pychestrate_ext.yaml").is_file(), True)
        testbase.assert_equal((pack_root / "pyproject.toml").is_file(), True)
        testbase.assert_equal((pack_root / "README.rst").is_file(), True)
        testbase.assert_equal((pack_root / "AGENTS.md").is_file(), True)
        testbase.assert_equal((pack_root / "_meta.yaml").is_file(), True)

        sample_factory = (
            pack_root
            / "source"
            / "packages"
            / "automojo"
            / "factories"
            / "pychestrate"
            / "example"
            / "sample_factory.py"
        )
        testbase.assert_equal(sample_factory.is_file(), True)

        sample_resource = (
            pack_root
            / "source"
            / "packages"
            / "automojo"
            / "extensions"
            / "pychestrate"
            / "example"
            / "sample_resource.py"
        )
        testbase.assert_equal(sample_resource.is_file(), True)
    return


def test_generate_substitutes_name_in_manifest_and_factory():
    """
    **Feature: E-extension-pack-template M1 (T1.3)**
    **Property: Rendered files contain the normalized name in the
    expected places.**
    """
    with tempfile.TemporaryDirectory() as parent_str:
        parent = Path(parent_str)
        request = _build_request(name="my-pack", target=parent, protocols=("object_store_driver",))
        generator = PackGenerator(corpus_root=None)
        pack_root = generator.generate(request=request, template_version=None)

        manifest_text = (pack_root / "pychestrate_ext.yaml").read_text(encoding="utf-8")
        testbase.assert_equal("name: my-pack" in manifest_text, True)
        testbase.assert_equal("object_store_driver" in manifest_text, True)

        factory_text = (
            pack_root
            / "source"
            / "packages"
            / "automojo"
            / "factories"
            / "pychestrate"
            / "my-pack"
            / "sample_factory.py"
        ).read_text(encoding="utf-8")
        testbase.assert_equal('factory_protocol_name: str = "object_store_driver"' in factory_text, True)
    return


def test_generate_refuses_non_empty_target_pack_directory():
    """
    **Feature: E-extension-pack-template M1 (Requirement 1.2)**
    **Property: Generation refuses when the target pack root already
    has content.**
    """
    with tempfile.TemporaryDirectory() as parent_str:
        parent = Path(parent_str)
        existing = parent / "pychestrate-ext-example"
        existing.mkdir()
        (existing / "leftover.txt").write_text("old content", encoding="utf-8")

        request = _build_request(name="example", target=parent)
        generator = PackGenerator(corpus_root=None)

        raised = False
        try:
            generator.generate(request=request, template_version=None)
        except ConfigurationError:
            raised = True
        testbase.assert_equal(raised, True)
        testbase.assert_equal((existing / "leftover.txt").read_text(), "old content")
    return


def test_generate_rejects_unknown_template_version():
    """
    **Feature: E-extension-pack-template M1 (T1.3)**
    **Property: An unknown corpus version is rejected with ConfigurationError.**
    """
    with tempfile.TemporaryDirectory() as parent_str:
        parent = Path(parent_str)
        request = _build_request(name="example", target=parent)
        generator = PackGenerator(corpus_root=None)

        raised = False
        try:
            generator.generate(request=request, template_version=999)
        except ConfigurationError:
            raised = True
        testbase.assert_equal(raised, True)
    return


def test_generate_uses_fallback_protocol_name_when_none_supplied():
    """
    **Feature: E-extension-pack-template M1 (T1.3)**
    **Property: Generating without --protocol still produces a
    coherent factory stub using the documented fallback name.**
    """
    with tempfile.TemporaryDirectory() as parent_str:
        parent = Path(parent_str)
        normalized = normalize_pack_name(raw="bare")
        request = PackGenerationRequest(
            name="bare",
            normalized_name=normalized,
            author=None,
            license=None,
            protocol_names=tuple(),
            resource_base_names=tuple(),
            target_dir=parent,
        )
        generator = PackGenerator(corpus_root=None)
        pack_root = generator.generate(request=request, template_version=None)

        factory_text = (
            pack_root
            / "source"
            / "packages"
            / "automojo"
            / "factories"
            / "pychestrate"
            / "bare"
            / "sample_factory.py"
        ).read_text(encoding="utf-8")
        testbase.assert_equal(
            'factory_protocol_name: str = "example_protocol"' in factory_text, True
        )
    return


# ---------------------------------------------------------------------------
# T1.4 — CLI surface
# ---------------------------------------------------------------------------

def test_cli_new_subcommand_generates_pack():
    """
    **Feature: E-extension-pack-template M1 (T1.4)**
    **Property: The CLI 'new' subcommand drives PackGenerator and writes to --target.**
    """
    with tempfile.TemporaryDirectory() as parent_str:
        parent = Path(parent_str)
        captured = io.StringIO()
        with redirect_stdout(captured):
            exit_code = pack_cli.main(
                argv=[
                    "new",
                    "--name=alpha",
                    "--author=Test",
                    "--target={}".format(parent),
                    "--protocol=auth_provider",
                ]
            )
        testbase.assert_equal(exit_code, 0)
        output = captured.getvalue()
        testbase.assert_equal("generated:" in output, True)
        testbase.assert_equal((parent / "pychestrate-ext-alpha").is_dir(), True)
    return


def test_cli_new_subcommand_rejects_bad_name():
    """
    **Feature: E-extension-pack-template M1 (T1.4)**
    **Property: A name that normalizes to empty exits with code 2.**
    """
    with tempfile.TemporaryDirectory() as parent_str:
        parent = Path(parent_str)
        captured_err = io.StringIO()
        with redirect_stderr(captured_err):
            exit_code = pack_cli.main(
                argv=[
                    "new",
                    "--name=   ",
                    "--target={}".format(parent),
                ]
            )
        testbase.assert_equal(exit_code, 2)
    return


def test_cli_list_versions_prints_v1():
    """
    **Feature: E-extension-pack-template M1 (T1.4)**
    **Property: list-versions emits the v1 line.**
    """
    captured = io.StringIO()
    with redirect_stdout(captured):
        exit_code = pack_cli.main(argv=["list-versions"])
    testbase.assert_equal(exit_code, 0)
    output = captured.getvalue()
    testbase.assert_equal("v1" in output, True)
    return


def test_admin_dispatcher_routes_to_pack_template():
    """
    **Feature: E-extension-pack-template M1 (T1.4)**
    **Property: The pychestrate-admin dispatcher routes
    'pack-template list-versions' through to the pack-template CLI.**
    """
    captured = io.StringIO()
    with redirect_stdout(captured):
        exit_code = admin_main.main(argv=["pack-template", "list-versions"])
    testbase.assert_equal(exit_code, 0)
    output = captured.getvalue()
    testbase.assert_equal("v1" in output, True)
    return


def test_admin_dispatcher_unknown_subsystem_exits_two():
    """
    **Feature: E-extension-pack-template M1 (T1.4)**
    **Property: Unknown top-level subsystem returns exit code 2.**
    """
    captured_err = io.StringIO()
    with redirect_stderr(captured_err):
        exit_code = admin_main.main(argv=["bogus"])
    testbase.assert_equal(exit_code, 2)
    return
