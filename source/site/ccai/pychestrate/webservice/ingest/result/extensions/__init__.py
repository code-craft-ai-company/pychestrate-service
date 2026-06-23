"""
.. module:: ingest.result.extensions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``ArtifactClassifierExtension`` resource base + references.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.ingest.result.extensions.artifact_classifier import (
    ArtifactClassification,
    ArtifactClassifierExtension,
    CATEGORY_DIAGNOSTIC,
    CATEGORY_LOG,
    CATEGORY_OTHER,
    CATEGORY_REPORT,
    CATEGORY_TASKING,
)
from ccai.pychestrate.webservice.ingest.result.extensions.testbase_classifier import (
    TestbaseArtifactClassifier,
)


__all__ = [
    "ArtifactClassification",
    "ArtifactClassifierExtension",
    "CATEGORY_DIAGNOSTIC",
    "CATEGORY_LOG",
    "CATEGORY_OTHER",
    "CATEGORY_REPORT",
    "CATEGORY_TASKING",
    "TestbaseArtifactClassifier",
]
