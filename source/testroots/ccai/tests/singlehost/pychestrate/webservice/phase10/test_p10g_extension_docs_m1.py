"""
.. module:: test_p10g_extension_docs_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for E-extension-docs M1 (skeleton).

.. moduleauthor:: Code Craft AI LLC

The walker consumes the published-surface catalog produced by
``8-plugin-api``. These tests import the protocol/resource modules
directly so the catalog walk over ``__subclasses__`` deterministically
covers the same set the M1 release will document.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import tempfile

from pathlib import Path

from ccai import testbase

from ccai.pychestrate.webservice.extension.docs_ext import (
    CatalogWalker,
    builtin_template_root,
    setup as docs_ext_setup,
)
from ccai.pychestrate.webservice.extension.docs_ext.models import (
    PAGE_KIND_PROTOCOL,
    PAGE_KIND_RESOURCE,
    DocPage,
)
from ccai.pychestrate.webservice.plugin_api import (
    PUBLISHED_STATUS_DEPRECATED,
    PUBLISHED_STATUS_SUPPORTED,
    PublishedSurfaceMetadata,
)
from ccai.pychestrate.webservice.plugin_api.catalog_builder import (
    Catalog,
    CatalogEntry,
)
from ccai.pychestrate.webservice.plugin_api import runtime as plugin_api_runtime

# Side-effect imports — load every annotated published module so
# __subclasses__ enumerations cover the live catalog.
from ccai.pychestrate.webservice.security.auth.factories.auth_provider import (  # noqa: F401
    AuthProviderProtocol,
)
from ccai.pychestrate.webservice.metrics.timeseries.factories.driver_protocol import (  # noqa: F401
    TimeseriesDriverProtocol,
)
from ccai.pychestrate.webservice.secrets.factories.secrets_backend import (  # noqa: F401
    SecretsBackendProtocol,
)
from ccai.pychestrate.webservice.notifications.factories.channel import (  # noqa: F401
    NotificationChannelProtocol,
)
from ccai.pychestrate.webservice.webhooks_in.factories.inbound_webhook_parser import (  # noqa: F401
    InboundWebhookParserProtocol,
)
from ccai.pychestrate.webservice.orchestration.source.factories.provider_protocol import (  # noqa: F401
    ScmProviderProtocol,
)
from ccai.pychestrate.webservice.orchestration.build.factories.runner_protocol import (  # noqa: F401
    BuildRunnerKindProtocol,
)
from ccai.pychestrate.webservice.orchestration.test.factories.runner_protocol import (  # noqa: F401
    TestRunnerKindProtocol,
)
from ccai.pychestrate.webservice.orchestration.infra.runs.factories.driver_protocol import (  # noqa: F401
    InfraToolDriverProtocol,
)
from ccai.pychestrate.webservice.ingest.progress.factories.parser_protocol import (  # noqa: F401
    ProgressParserProtocol,
)
from ccai.pychestrate.webservice.ingest.result.factories.parser_protocol import (  # noqa: F401
    ResultTreeParserProtocol,
)
from ccai.pychestrate.webservice.pods.extensions.member_kind import (  # noqa: F401
    PodMemberKindExtension,
)
from ccai.pychestrate.webservice.metrics.ingest.extensions.metric_definition import (  # noqa: F401
    MetricDefinitionExtension,
)
from ccai.pychestrate.webservice.notifications.extensions.template import (  # noqa: F401
    NotificationTemplateExtension,
)


def _build_synthetic_catalog() -> Catalog:
    """
        Build a small in-memory catalog used by the deterministic
        rendering tests. Avoids depending on the live catalog's
        ordering / counts.

        :returns: :class:`Catalog`.
    """
    factory_entries = (
        CatalogEntry(
            name="alpha_protocol",
            kind="factory_protocol",
            protocol_schema_version=2,
            metadata=PublishedSurfaceMetadata(
                status=PUBLISHED_STATUS_SUPPORTED,
                min_schema_version=1,
                deprecation_date=None,
                sunset_date=None,
                docs_url="https://docs.example.com/alpha",
                reference="example.module.AlphaImpl",
            ),
            declaring_class_qualname="example.module.AlphaProtocol",
        ),
        CatalogEntry(
            name="legacy_protocol",
            kind="factory_protocol",
            protocol_schema_version=1,
            metadata=PublishedSurfaceMetadata(
                status=PUBLISHED_STATUS_DEPRECATED,
                min_schema_version=1,
                deprecation_date="2025-09-01",
                sunset_date="2026-09-01",
                docs_url="https://docs.example.com/legacy",
                reference="example.module.LegacyImpl",
            ),
            declaring_class_qualname="example.module.LegacyProtocol",
        ),
    )

    resource_entries = (
        CatalogEntry(
            name="ExampleResourceBase",
            kind="resource_extension",
            protocol_schema_version=1,
            metadata=PublishedSurfaceMetadata(
                status=PUBLISHED_STATUS_SUPPORTED,
                min_schema_version=1,
                deprecation_date=None,
                sunset_date=None,
                docs_url="https://docs.example.com/ExampleResourceBase",
                reference="example.module.ExampleKind",
            ),
            declaring_class_qualname="example.module.ExampleResourceBase",
        ),
    )

    rtnval = Catalog(
        factory_entries=factory_entries,
        resource_entries=resource_entries,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Walker against a synthetic catalog
# ---------------------------------------------------------------------------

def test_walker_emits_one_protocol_page_per_entry():
    """
    **Feature: E-extension-docs M1 (T1.3)**
    **Property: emit_protocol_pages writes one .rst file per factory
    catalog entry.**
    """
    catalog = _build_synthetic_catalog()
    with tempfile.TemporaryDirectory() as out_str:
        out_dir = Path(out_str)
        walker = CatalogWalker(
            catalog=catalog,
            out_dir=out_dir,
            template_root=None,
            stability_filter=None,
        )
        written = walker.emit_protocol_pages()
        testbase.assert_equal(len(written), 2)
        testbase.assert_equal((out_dir / "protocols" / "alpha_protocol.rst").is_file(), True)
        testbase.assert_equal((out_dir / "protocols" / "legacy_protocol.rst").is_file(), True)
    return


def test_walker_emits_one_resource_page_per_entry():
    """
    **Feature: E-extension-docs M1 (T1.3)**
    **Property: emit_resource_pages writes one .rst file per resource
    catalog entry.**
    """
    catalog = _build_synthetic_catalog()
    with tempfile.TemporaryDirectory() as out_str:
        out_dir = Path(out_str)
        walker = CatalogWalker(
            catalog=catalog,
            out_dir=out_dir,
            template_root=None,
            stability_filter=None,
        )
        written = walker.emit_resource_pages()
        testbase.assert_equal(len(written), 1)
        testbase.assert_equal(
            (out_dir / "resources" / "ExampleResourceBase.rst").is_file(), True
        )
    return


def test_protocol_page_rst_carries_expected_metadata():
    """
    **Feature: E-extension-docs M1 (template)**
    **Property: A rendered protocol page carries name, schema version,
    docs URL, reference path, and deprecation block when applicable.**
    """
    catalog = _build_synthetic_catalog()
    with tempfile.TemporaryDirectory() as out_str:
        out_dir = Path(out_str)
        walker = CatalogWalker(
            catalog=catalog,
            out_dir=out_dir,
            template_root=None,
            stability_filter=None,
        )
        walker.emit_protocol_pages()

        legacy_text = (out_dir / "protocols" / "legacy_protocol.rst").read_text(
            encoding="utf-8"
        )
        testbase.assert_equal("legacy_protocol" in legacy_text, True)
        testbase.assert_equal(":Schema version: 1" in legacy_text, True)
        testbase.assert_equal("``deprecated``" in legacy_text, True)
        testbase.assert_equal(":Deprecated: 2025-09-01" in legacy_text, True)
        testbase.assert_equal(":Sunsets: 2026-09-01" in legacy_text, True)
        testbase.assert_equal("example.module.LegacyImpl" in legacy_text, True)

        alpha_text = (out_dir / "protocols" / "alpha_protocol.rst").read_text(
            encoding="utf-8"
        )
        testbase.assert_equal("``supported``" in alpha_text, True)
        testbase.assert_equal(":Deprecated:" not in alpha_text, True)
    return


def test_walker_emits_indexes_listing_each_entry():
    """
    **Feature: E-extension-docs M1 (T1.3 / index)**
    **Property: emit_indexes writes a protocols and resources index
    referencing every emitted page.**
    """
    catalog = _build_synthetic_catalog()
    with tempfile.TemporaryDirectory() as out_str:
        out_dir = Path(out_str)
        walker = CatalogWalker(
            catalog=catalog,
            out_dir=out_dir,
            template_root=None,
            stability_filter=None,
        )
        written = walker.emit_indexes()
        testbase.assert_equal(len(written), 2)

        protocol_index_text = (out_dir / "protocols" / "index.rst").read_text(
            encoding="utf-8"
        )
        testbase.assert_equal("alpha_protocol" in protocol_index_text, True)
        testbase.assert_equal("legacy_protocol" in protocol_index_text, True)
        testbase.assert_equal("toctree" in protocol_index_text, True)

        resource_index_text = (out_dir / "resources" / "index.rst").read_text(
            encoding="utf-8"
        )
        testbase.assert_equal("ExampleResourceBase" in resource_index_text, True)
    return


def test_emit_all_writes_protocols_resources_and_indexes():
    """
    **Feature: E-extension-docs M1 (T1.3)**
    **Property: emit_all writes the union of protocol pages, resource
    pages, and the per-category indexes.**
    """
    catalog = _build_synthetic_catalog()
    with tempfile.TemporaryDirectory() as out_str:
        out_dir = Path(out_str)
        walker = CatalogWalker(
            catalog=catalog,
            out_dir=out_dir,
            template_root=None,
            stability_filter=None,
        )
        written = walker.emit_all()
        # 2 protocols + 1 resource + 2 indexes
        testbase.assert_equal(len(written), 5)
    return


# ---------------------------------------------------------------------------
# Walker against the live catalog
# ---------------------------------------------------------------------------

def test_walker_against_live_catalog_emits_each_published_entry():
    """
    **Feature: E-extension-docs M1 (T1.3)**
    **Property: Running the walker against the live runtime catalog
    yields one .rst per published factory protocol and resource base.**
    """
    plugin_api_runtime.reset_for_testing()
    catalog = plugin_api_runtime.build_and_validate_catalog()

    with tempfile.TemporaryDirectory() as out_str:
        out_dir = Path(out_str)
        walker = CatalogWalker(
            catalog=catalog,
            out_dir=out_dir,
            template_root=None,
            stability_filter=None,
        )
        walker.emit_all()

        protocols_dir = out_dir / "protocols"
        resources_dir = out_dir / "resources"

        for entry in catalog.factory_entries:
            page_path = protocols_dir / "{}.rst".format(entry.name)
            testbase.assert_equal(page_path.is_file(), True)

        for entry in catalog.resource_entries:
            page_path = resources_dir / "{}.rst".format(entry.name)
            testbase.assert_equal(page_path.is_file(), True)
    return


# ---------------------------------------------------------------------------
# Sphinx setup hook
# ---------------------------------------------------------------------------

class _FakeSphinxApp:
    """
        Test double that records connected event names.
    """

    def __init__(self, srcdir: str) -> None:
        self.srcdir: str = srcdir
        self.connected_events: list = []

    def connect(self, event_name: str, callback) -> None:
        self.connected_events.append(event_name)
        return


def test_sphinx_setup_returns_metadata_and_connects_builder_inited():
    """
    **Feature: E-extension-docs M1 (T1.2)**
    **Property: ``setup(app)`` returns the documented metadata mapping
    and registers the ``builder-inited`` callback.**
    """
    with tempfile.TemporaryDirectory() as out_str:
        app = _FakeSphinxApp(srcdir=out_str)
        result = docs_ext_setup(app)
        testbase.assert_equal("version" in result, True)
        testbase.assert_equal(result.get("parallel_read_safe"), True)
        testbase.assert_equal(result.get("parallel_write_safe"), True)
        testbase.assert_equal("builder-inited" in app.connected_events, True)
    return


# ---------------------------------------------------------------------------
# DocPage / models
# ---------------------------------------------------------------------------

def test_doc_page_kind_constants_match_dataclass_values():
    """
    **Feature: E-extension-docs M1 (models)**
    **Property: PAGE_KIND_PROTOCOL / PAGE_KIND_RESOURCE constants are
    distinct strings.**
    """
    testbase.assert_equal(PAGE_KIND_PROTOCOL == PAGE_KIND_RESOURCE, False)
    return


def test_builtin_template_root_exists():
    """
    **Feature: E-extension-docs M1 (T1.2)**
    **Property: builtin_template_root resolves to an existing
    directory shipped alongside the package.**
    """
    template_root = builtin_template_root()
    testbase.assert_equal(template_root.is_dir(), True)
    testbase.assert_equal((template_root / "protocol_page.rst.jinja").is_file(), True)
    testbase.assert_equal((template_root / "resource_page.rst.jinja").is_file(), True)
    return
