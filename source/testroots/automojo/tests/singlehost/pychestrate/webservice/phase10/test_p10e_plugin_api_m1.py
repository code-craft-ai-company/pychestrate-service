"""
.. module:: test_p10e_plugin_api_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 8-plugin-api M1 (catalog skeleton).

.. moduleauthor:: Automation Mojo LLC

These tests import every protocol module that ships an
``is_published = True`` annotation so the catalog walk over
``__subclasses__`` of :class:`FactoryProtocolBase` and
:class:`ResourceExtension` includes them deterministically. Tests
exercise each part of the M1 surface independently:

* Annotation reader (:func:`is_class_published`,
  :func:`extract_published_metadata`).
* Builder (:func:`build_catalog`).
* Validator (:func:`validate_catalog_against_code`).
* Runtime cache (:mod:`runtime`).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase
from automojo.pychestrate.webservice.extensions.resource_extension import ResourceExtension
from automojo.pychestrate.webservice.plugin_api import (
    CatalogEntry,
    PUBLISHED_STATUS_SUPPORTED,
    build_catalog,
    catalog_to_jsonable,
    extract_published_metadata,
    is_class_published,
    validate_catalog_against_code,
)
from automojo.pychestrate.webservice.plugin_api import runtime as plugin_api_runtime

# Side-effect imports — load every annotated protocol/resource module
# so __subclasses__ enumerations see them.
from automojo.pychestrate.webservice.security.auth.factories.auth_provider import (  # noqa: F401
    AuthProviderProtocol,
)
from automojo.pychestrate.webservice.metrics.timeseries.factories.driver_protocol import (  # noqa: F401
    TimeseriesDriverProtocol,
)
from automojo.pychestrate.webservice.secrets.factories.secrets_backend import (  # noqa: F401
    SecretsBackendProtocol,
)
from automojo.pychestrate.webservice.notifications.factories.channel import (  # noqa: F401
    NotificationChannelProtocol,
)
from automojo.pychestrate.webservice.webhooks_in.factories.inbound_webhook_parser import (  # noqa: F401
    InboundWebhookParserProtocol,
)
from automojo.pychestrate.webservice.orchestration.source.factories.provider_protocol import (  # noqa: F401
    ScmProviderProtocol,
)
from automojo.pychestrate.webservice.orchestration.build.factories.runner_protocol import (  # noqa: F401
    BuildRunnerKindProtocol,
)
from automojo.pychestrate.webservice.orchestration.test.factories.runner_protocol import (  # noqa: F401
    TestRunnerKindProtocol,
)
from automojo.pychestrate.webservice.orchestration.infra.runs.factories.driver_protocol import (  # noqa: F401
    InfraToolDriverProtocol,
)
from automojo.pychestrate.webservice.ingest.progress.factories.parser_protocol import (  # noqa: F401
    ProgressParserProtocol,
)
from automojo.pychestrate.webservice.ingest.result.factories.parser_protocol import (  # noqa: F401
    ResultTreeParserProtocol,
)
from automojo.pychestrate.webservice.pods.extensions.member_kind import (  # noqa: F401
    PodMemberKindExtension,
)
from automojo.pychestrate.webservice.metrics.ingest.extensions.metric_definition import (  # noqa: F401
    MetricDefinitionExtension,
)
from automojo.pychestrate.webservice.notifications.extensions.template import (  # noqa: F401
    NotificationTemplateExtension,
)
from automojo.pychestrate.webservice.extensions.rest_endpoint_protocol import (  # noqa: F401
    RestEndpointExtension,
)
from automojo.pychestrate.cli.extensions.cli_subcommand import (  # noqa: F401
    CLISubcommandExtension,
)
from automojo.pychestrate.webservice.security.auth.extensions.mfa_method import (  # noqa: F401
    MFAMethodExtension,
)
from automojo.pychestrate.webservice.ingest.result.extensions.artifact_classifier import (  # noqa: F401
    ArtifactClassifierExtension,
)


PUBLISHED_FACTORY_NAMES = (
    "auth_provider",
    "timeseries_driver",
    "secrets_backend",
    "notification_channel",
    "inbound_webhook_parser",
    "scm_provider",
    "build_runner_kind",
    "test_runner_kind",
    "infra_tool_driver",
    "progress_parser",
    "result_tree_parser",
)


PUBLISHED_RESOURCE_NAMES = (
    "PodMemberKindExtension",
    "MetricDefinitionExtension",
    "NotificationTemplateExtension",
    "RestEndpointExtension",
    "CLISubcommandExtension",
    "MFAMethodExtension",
    "ArtifactClassifierExtension",
)


# ---------------------------------------------------------------------------
# Annotation reader
# ---------------------------------------------------------------------------

def test_is_class_published_returns_true_for_annotated_class():
    """
    **Feature: 8-plugin-api M1 (annotations)**
    **Property: is_class_published reads ``is_published`` ClassVar.**
    """
    rtnval = is_class_published(target_class=AuthProviderProtocol)
    testbase.assert_equal(rtnval, True)
    return


def test_is_class_published_returns_false_for_unannotated_class():
    """
    **Feature: 8-plugin-api M1 (annotations)**
    **Property: is_class_published returns False when the attribute
    is absent.**
    """

    class UnannotatedProtocol(FactoryProtocolBase):
        factory_protocol_name: str = "unannotated_for_testing"
        protocol_schema_version: int = 1

    rtnval = is_class_published(target_class=UnannotatedProtocol)
    testbase.assert_equal(rtnval, False)
    return


def test_extract_published_metadata_returns_defaults():
    """
    **Feature: 8-plugin-api M1 (annotations)**
    **Property: extract_published_metadata returns defaults when only
    ``is_published`` is set.**
    """
    metadata = extract_published_metadata(target_class=AuthProviderProtocol)
    testbase.assert_equal(metadata.status, PUBLISHED_STATUS_SUPPORTED)
    testbase.assert_equal(metadata.min_schema_version, 1)
    testbase.assert_equal(metadata.deprecation_date, None)
    testbase.assert_equal(metadata.sunset_date, None)
    testbase.assert_equal(len(metadata.docs_url) > 0, True)
    testbase.assert_equal(len(metadata.reference) > 0, True)
    return


# ---------------------------------------------------------------------------
# Catalog builder
# ---------------------------------------------------------------------------

def test_build_catalog_includes_every_published_factory():
    """
    **Feature: 8-plugin-api M1 (T1.2)**
    **Property: build_catalog returns an entry for every annotated
    factory protocol.**
    """
    catalog = build_catalog()
    seen_names = {entry.name for entry in catalog.factory_entries}
    for expected in PUBLISHED_FACTORY_NAMES:
        testbase.assert_equal(expected in seen_names, True)
    return


def test_build_catalog_includes_every_published_resource():
    """
    **Feature: 8-plugin-api M1 (T1.2)**
    **Property: build_catalog returns an entry for every annotated
    resource base.**
    """
    catalog = build_catalog()
    seen_names = {entry.name for entry in catalog.resource_entries}
    for expected in PUBLISHED_RESOURCE_NAMES:
        testbase.assert_equal(expected in seen_names, True)
    return


def test_build_catalog_orders_factories_by_name():
    """
    **Feature: 8-plugin-api M1 (T1.2)**
    **Property: factory_entries are sorted by ``factory_protocol_name``.**
    """
    catalog = build_catalog()
    names = [entry.name for entry in catalog.factory_entries]
    testbase.assert_equal(names, sorted(names))
    return


def test_build_catalog_marks_kinds_correctly():
    """
    **Feature: 8-plugin-api M1 (T1.2)**
    **Property: factory_entries carry kind ``factory_protocol``;
    resource_entries carry ``resource_extension``.**
    """
    catalog = build_catalog()
    for entry in catalog.factory_entries:
        testbase.assert_equal(entry.kind, "factory_protocol")
    for entry in catalog.resource_entries:
        testbase.assert_equal(entry.kind, "resource_extension")
    return


def test_catalog_entry_for_auth_provider_has_expected_reference():
    """
    **Feature: 8-plugin-api M1 (T1.1)**
    **Property: The published reference for auth_provider points at
    LocalCredentialAuthProvider.**
    """
    catalog = build_catalog()
    matched = None
    for entry in catalog.factory_entries:
        if entry.name == "auth_provider":
            matched = entry
            break
    testbase.assert_equal(matched is not None, True)
    testbase.assert_equal(
        matched.metadata.reference.endswith(".LocalCredentialAuthProvider"), True
    )
    return


# ---------------------------------------------------------------------------
# Catalog validator
# ---------------------------------------------------------------------------

def test_validate_catalog_resolves_every_reference():
    """
    **Feature: 8-plugin-api M1 (T1.3)**
    **Property: Every published_reference in the catalog imports cleanly.**
    """
    catalog = build_catalog()
    validated = validate_catalog_against_code(catalog=catalog)
    factory_count = len(catalog.factory_entries)
    resource_count = len(catalog.resource_entries)
    testbase.assert_equal(len(validated), factory_count + resource_count)
    return


def test_validator_rejects_missing_module_reference():
    """
    **Feature: 8-plugin-api M1 (T1.3)**
    **Property: A reference whose module cannot import raises
    ConfigurationError.**
    """
    bad_entry = CatalogEntry(
        name="synthetic_protocol_missing_module",
        kind="factory_protocol",
        protocol_schema_version=1,
        metadata=extract_published_metadata(target_class=AuthProviderProtocol).__class__(
            status=PUBLISHED_STATUS_SUPPORTED,
            min_schema_version=1,
            deprecation_date=None,
            sunset_date=None,
            docs_url="",
            reference="automojo.pychestrate.webservice.does_not_exist.MissingClass",
        ),
        declaring_class_qualname="automojo.synthetic.SyntheticProtocol",
    )

    from automojo.pychestrate.webservice.plugin_api.catalog_builder import Catalog

    bad_catalog = Catalog(factory_entries=(bad_entry,), resource_entries=tuple())

    raised = False
    try:
        validate_catalog_against_code(catalog=bad_catalog)
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_validator_rejects_missing_attribute_in_module():
    """
    **Feature: 8-plugin-api M1 (T1.3)**
    **Property: A reference whose attribute is absent from the resolved
    module raises ConfigurationError.**
    """
    bad_entry = CatalogEntry(
        name="synthetic_protocol_missing_attr",
        kind="factory_protocol",
        protocol_schema_version=1,
        metadata=extract_published_metadata(target_class=AuthProviderProtocol).__class__(
            status=PUBLISHED_STATUS_SUPPORTED,
            min_schema_version=1,
            deprecation_date=None,
            sunset_date=None,
            docs_url="",
            reference=(
                "automojo.pychestrate.webservice.security.auth.factories.local_provider"
                ".ClassDoesNotExistInThisModule"
            ),
        ),
        declaring_class_qualname="automojo.synthetic.SyntheticProtocol",
    )

    from automojo.pychestrate.webservice.plugin_api.catalog_builder import Catalog

    bad_catalog = Catalog(factory_entries=(bad_entry,), resource_entries=tuple())

    raised = False
    try:
        validate_catalog_against_code(catalog=bad_catalog)
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# Runtime cache
# ---------------------------------------------------------------------------

def test_runtime_build_and_validate_catalog_caches_result():
    """
    **Feature: 8-plugin-api M1 (T1.4 / NFR-4)**
    **Property: build_and_validate_catalog populates the runtime cache;
    a subsequent get_active_catalog returns the same object.**
    """
    plugin_api_runtime.reset_for_testing()

    built = plugin_api_runtime.build_and_validate_catalog()
    cached = plugin_api_runtime.get_active_catalog()
    testbase.assert_equal(cached is built, True)
    return


def test_runtime_get_active_catalog_lazy_builds_on_first_use():
    """
    **Feature: 8-plugin-api M1 (T1.4)**
    **Property: get_active_catalog builds on demand if no cached
    catalog exists.**
    """
    plugin_api_runtime.reset_for_testing()
    catalog = plugin_api_runtime.get_active_catalog()
    factory_count = len(catalog.factory_entries)
    resource_count = len(catalog.resource_entries)
    testbase.assert_equal(factory_count > 0, True)
    testbase.assert_equal(resource_count > 0, True)
    return


# ---------------------------------------------------------------------------
# JSON renderer
# ---------------------------------------------------------------------------

def test_catalog_to_jsonable_structure():
    """
    **Feature: 8-plugin-api M1 (T1.5)**
    **Property: catalog_to_jsonable returns the documented top-level
    keys with list values.**
    """
    catalog = build_catalog()
    rendered = catalog_to_jsonable(catalog=catalog)
    testbase.assert_equal("factory_protocols" in rendered, True)
    testbase.assert_equal("resource_extensions" in rendered, True)
    testbase.assert_equal(isinstance(rendered["factory_protocols"], list), True)
    testbase.assert_equal(isinstance(rendered["resource_extensions"], list), True)

    if len(rendered["factory_protocols"]) > 0:
        first_entry = rendered["factory_protocols"][0]
        for key in (
            "name",
            "kind",
            "protocol_schema_version",
            "min_schema_version",
            "status",
            "deprecation_date",
            "sunset_date",
            "docs_url",
            "reference",
            "declaring_class",
        ):
            testbase.assert_equal(key in first_entry, True)
    return


# ---------------------------------------------------------------------------
# Sanity check: no internal-only protocols leak into the catalog
# ---------------------------------------------------------------------------

def test_internal_only_protocol_does_not_appear_in_catalog():
    """
    **Feature: 8-plugin-api M1 (T1.2)**
    **Property: A protocol without ``is_published = True`` does not
    appear in the catalog even when its module is imported.**
    """
    # feature_flag_backend is internal-only and should not be published.
    catalog = build_catalog()
    seen_names = {entry.name for entry in catalog.factory_entries}
    testbase.assert_equal("feature_flag_backend" in seen_names, False)
    return
