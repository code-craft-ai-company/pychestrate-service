"""
.. module:: ingest.result.extensions.testbase_classifier
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference :class:`ArtifactClassifierExtension` — testbase tree.

.. moduleauthor:: Code Craft AI LLC

Classifies files emitted by ``codecraftai-testbase`` runs. The classifier
recognizes the canonical directory layout (``diagnostics/``,
``taskings/``, ``tc-by-products/``, ``artifacts/``) plus the top-level
summary / report files. Anything outside that map yields
``CLASSIFICATION_NO_MATCH`` so subsequent classifiers (extension-
contributed or downstream defaults) can claim the file.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar

from ccai.pychestrate.webservice.ingest.result.extensions.artifact_classifier import (
    CATEGORY_DIAGNOSTIC,
    CATEGORY_LOG,
    CATEGORY_REPORT,
    CATEGORY_TASKING,
    CLASSIFICATION_NO_MATCH,
    ArtifactClassification,
    ArtifactClassifierExtension,
)


_TESTBASE_TAG: str = "testbase"


_KNOWN_TOP_LEVEL_REPORTS = frozenset(
    {
        "testrun_summary.json",
        "testrun_results.json",
        "testrun_results_stream.jsos",
        "testsummary.html",
    }
)


class TestbaseArtifactClassifier(ArtifactClassifierExtension):
    """
        Reference :class:`ArtifactClassifierExtension` that maps the
        canonical ``codecraftai-testbase`` result-tree layout into the
        documented categories.
    """

    classifier_name: ClassVar[str] = "testbase"

    @classmethod
    def classify(
            cls,
            *,
            relative_path: str,
            mime_type: str,
            magic_prefix: bytes
        ) -> ArtifactClassification:
        if relative_path is None or len(relative_path) == 0:
            rtnval = CLASSIFICATION_NO_MATCH
            return rtnval

        normalized = relative_path.lstrip("/")

        if normalized in _KNOWN_TOP_LEVEL_REPORTS:
            rtnval = ArtifactClassification(
                category=CATEGORY_REPORT,
                tags=(_TESTBASE_TAG,),
                matched=True,
            )
            return rtnval

        first_segment, _, _ = normalized.partition("/")

        if first_segment == "diagnostics":
            rtnval = ArtifactClassification(
                category=CATEGORY_DIAGNOSTIC,
                tags=(_TESTBASE_TAG,),
                matched=True,
            )
            return rtnval

        if first_segment == "taskings":
            rtnval = ArtifactClassification(
                category=CATEGORY_TASKING,
                tags=(_TESTBASE_TAG,),
                matched=True,
            )
            return rtnval

        if first_segment == "tc-by-products":
            rtnval = ArtifactClassification(
                category=CATEGORY_LOG,
                tags=(_TESTBASE_TAG, "tc-by-product"),
                matched=True,
            )
            return rtnval

        if first_segment == "artifacts":
            rtnval = ArtifactClassification(
                category=CATEGORY_LOG,
                tags=(_TESTBASE_TAG, "artifact"),
                matched=True,
            )
            return rtnval

        rtnval = CLASSIFICATION_NO_MATCH
        return rtnval
