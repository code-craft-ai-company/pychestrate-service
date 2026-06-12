"""
.. module:: test_p10o_artifact_classifier_extension_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ArtifactClassifierExtension + testbase reference.

.. moduleauthor:: Code Craft AI LLC

The slice promotes ``ArtifactClassifierExtension`` from the published-
but-not-yet-implemented list (per ``8-plugin-api`` Requirement 2)
into the catalog. Tests cover the dataclass invariants, the
resource-base contract, every recognized testbase tree case in the
reference classifier, the ``no-match`` path, and the catalog walk.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension
from ccai.pychestrate.webservice.ingest.result.extensions.artifact_classifier import (
    CATEGORY_DIAGNOSTIC,
    CATEGORY_LOG,
    CATEGORY_OTHER,
    CATEGORY_REPORT,
    CATEGORY_TASKING,
    CLASSIFICATION_NO_MATCH,
    ArtifactClassification,
    ArtifactClassifierExtension,
)
from ccai.pychestrate.webservice.ingest.result.extensions.testbase_classifier import (
    TestbaseArtifactClassifier,
)
from ccai.pychestrate.webservice.plugin_api import build_catalog, is_class_published
from ccai.pychestrate.webservice.plugin_api.catalog_validator import (
    validate_catalog_against_code,
)


# ---------------------------------------------------------------------------
# Resource base contract
# ---------------------------------------------------------------------------

def test_artifact_classifier_extension_is_direct_resource_subclass():
    """
    **Feature: 8-plugin-api / 5-result-ingest-watcher**
    **Property: ArtifactClassifierExtension is a direct
    ResourceExtension subclass so the catalog walker enumerates it.**
    """
    testbase.assert_equal(
        issubclass(ArtifactClassifierExtension, ResourceExtension), True
    )
    testbase.assert_equal(
        ResourceExtension in ArtifactClassifierExtension.__bases__, True
    )
    return


def test_artifact_classifier_extension_default_classifier_name_is_empty():
    """
    **Feature: 5-result-ingest-watcher**
    **Property: The base declares classifier_name = '' so subclasses
    must override.**
    """
    testbase.assert_equal(ArtifactClassifierExtension.classifier_name, "")
    return


def test_artifact_classifier_extension_classify_raises_on_base():
    """
    **Feature: 5-result-ingest-watcher**
    **Property: Calling classify on the base raises NotImplementedError.**
    """
    raised = False
    try:
        ArtifactClassifierExtension.classify(
            relative_path="x", mime_type="", magic_prefix=b""
        )
    except NotImplementedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# Dataclass + sentinel
# ---------------------------------------------------------------------------

def test_artifact_classification_is_frozen():
    """
    **Feature: 5-result-ingest-watcher**
    **Property: ArtifactClassification is a frozen dataclass with
    category, tags, matched.**
    """
    classification = ArtifactClassification(
        category=CATEGORY_LOG, tags=("x",), matched=True
    )
    testbase.assert_equal(classification.category, CATEGORY_LOG)
    testbase.assert_equal(classification.tags, ("x",))
    testbase.assert_equal(classification.matched, True)

    raised = False
    try:
        classification.category = CATEGORY_OTHER
    except Exception:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_artifact_classification_default_tags_empty_and_matched_true():
    """
    **Feature: 5-result-ingest-watcher**
    **Property: ArtifactClassification defaults: tags=()
    matched=True.**
    """
    classification = ArtifactClassification(category=CATEGORY_LOG)
    testbase.assert_equal(classification.tags, tuple())
    testbase.assert_equal(classification.matched, True)
    return


def test_classification_no_match_sentinel_has_other_category_unmatched():
    """
    **Feature: 5-result-ingest-watcher**
    **Property: CLASSIFICATION_NO_MATCH carries category='other',
    empty tags, matched=False so ingest pipelines can detect a
    non-claim and try the next classifier.**
    """
    testbase.assert_equal(CLASSIFICATION_NO_MATCH.category, CATEGORY_OTHER)
    testbase.assert_equal(CLASSIFICATION_NO_MATCH.tags, tuple())
    testbase.assert_equal(CLASSIFICATION_NO_MATCH.matched, False)
    return


# ---------------------------------------------------------------------------
# TestbaseArtifactClassifier behavior
# ---------------------------------------------------------------------------

def test_testbase_classifier_inherits_from_base_only():
    """
    **Feature: 5-result-ingest-watcher (testbase reference)**
    **Property: TestbaseArtifactClassifier inherits from
    ArtifactClassifierExtension (not directly from
    ResourceExtension).**
    """
    testbase.assert_equal(
        issubclass(TestbaseArtifactClassifier, ArtifactClassifierExtension),
        True,
    )
    testbase.assert_equal(
        ArtifactClassifierExtension in TestbaseArtifactClassifier.__bases__,
        True,
    )
    testbase.assert_equal(
        ResourceExtension in TestbaseArtifactClassifier.__bases__, False
    )
    return


def test_testbase_classifier_recognizes_top_level_summary_files():
    """
    **Feature: 5-result-ingest-watcher (testbase reference)**
    **Property: testrun_summary.json / testrun_results.json /
    testrun_results_stream.jsos / testsummary.html land in
    CATEGORY_REPORT.**
    """
    for name in (
        "testrun_summary.json",
        "testrun_results.json",
        "testrun_results_stream.jsos",
        "testsummary.html",
    ):
        result = TestbaseArtifactClassifier.classify(
            relative_path=name, mime_type="", magic_prefix=b""
        )
        testbase.assert_equal(result.matched, True)
        testbase.assert_equal(result.category, CATEGORY_REPORT)
        testbase.assert_equal("testbase" in result.tags, True)
    return


def test_testbase_classifier_classifies_diagnostics_subtree():
    """
    **Feature: 5-result-ingest-watcher (testbase reference)**
    **Property: Files under diagnostics/ map to CATEGORY_DIAGNOSTIC.**
    """
    result = TestbaseArtifactClassifier.classify(
        relative_path="diagnostics/host.log", mime_type="", magic_prefix=b""
    )
    testbase.assert_equal(result.matched, True)
    testbase.assert_equal(result.category, CATEGORY_DIAGNOSTIC)
    return


def test_testbase_classifier_classifies_taskings_subtree():
    """
    **Feature: 5-result-ingest-watcher (testbase reference)**
    **Property: Files under taskings/ map to CATEGORY_TASKING.**
    """
    result = TestbaseArtifactClassifier.classify(
        relative_path="taskings/0001-task.json",
        mime_type="application/json",
        magic_prefix=b"{",
    )
    testbase.assert_equal(result.matched, True)
    testbase.assert_equal(result.category, CATEGORY_TASKING)
    return


def test_testbase_classifier_classifies_tc_by_products_subtree():
    """
    **Feature: 5-result-ingest-watcher (testbase reference)**
    **Property: Files under tc-by-products/ map to CATEGORY_LOG with
    a 'tc-by-product' tag.**
    """
    result = TestbaseArtifactClassifier.classify(
        relative_path="tc-by-products/test_alpha/console.log",
        mime_type="text/plain",
        magic_prefix=b"",
    )
    testbase.assert_equal(result.matched, True)
    testbase.assert_equal(result.category, CATEGORY_LOG)
    testbase.assert_equal("tc-by-product" in result.tags, True)
    return


def test_testbase_classifier_classifies_artifacts_subtree():
    """
    **Feature: 5-result-ingest-watcher (testbase reference)**
    **Property: Files under artifacts/ map to CATEGORY_LOG with an
    'artifact' tag.**
    """
    result = TestbaseArtifactClassifier.classify(
        relative_path="artifacts/run-001/build.log",
        mime_type="text/plain",
        magic_prefix=b"",
    )
    testbase.assert_equal(result.matched, True)
    testbase.assert_equal(result.category, CATEGORY_LOG)
    testbase.assert_equal("artifact" in result.tags, True)
    return


def test_testbase_classifier_returns_no_match_for_unknown_path():
    """
    **Feature: 5-result-ingest-watcher (testbase reference)**
    **Property: A path outside the canonical layout returns
    CLASSIFICATION_NO_MATCH so subsequent classifiers can claim it.**
    """
    result = TestbaseArtifactClassifier.classify(
        relative_path="custom-extension-output/data.bin",
        mime_type="",
        magic_prefix=b"",
    )
    testbase.assert_equal(result.matched, False)
    testbase.assert_equal(result.category, CATEGORY_OTHER)
    return


def test_testbase_classifier_empty_path_returns_no_match():
    """
    **Feature: 5-result-ingest-watcher (testbase reference)**
    **Property: An empty / None relative_path returns no-match
    rather than raising.**
    """
    result = TestbaseArtifactClassifier.classify(
        relative_path="", mime_type="", magic_prefix=b""
    )
    testbase.assert_equal(result.matched, False)
    return


def test_testbase_classifier_ignores_leading_slash_on_path():
    """
    **Feature: 5-result-ingest-watcher (testbase reference)**
    **Property: A leading '/' is normalized away so absolute /
    relative paths classify identically.**
    """
    result_relative = TestbaseArtifactClassifier.classify(
        relative_path="diagnostics/x.log", mime_type="", magic_prefix=b""
    )
    result_absolute = TestbaseArtifactClassifier.classify(
        relative_path="/diagnostics/x.log", mime_type="", magic_prefix=b""
    )
    testbase.assert_equal(result_relative.category, result_absolute.category)
    testbase.assert_equal(result_relative.matched, result_absolute.matched)
    return


# ---------------------------------------------------------------------------
# Catalog integration
# ---------------------------------------------------------------------------

def test_artifact_classifier_extension_is_published():
    rtnval = is_class_published(target_class=ArtifactClassifierExtension)
    testbase.assert_equal(rtnval, True)
    return


def test_catalog_includes_artifact_classifier_extension_entry():
    catalog = build_catalog()
    matched = None
    for entry in catalog.resource_entries:
        if entry.name == "ArtifactClassifierExtension":
            matched = entry
            break
    testbase.assert_equal(matched is not None, True)
    testbase.assert_equal(
        matched.metadata.reference.endswith(".TestbaseArtifactClassifier"),
        True,
    )
    return


def test_catalog_validator_resolves_artifact_classifier_reference():
    catalog = build_catalog()
    validate_catalog_against_code(catalog=catalog)
    return
