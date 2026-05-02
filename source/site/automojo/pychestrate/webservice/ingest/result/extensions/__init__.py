"""
.. module:: ingest.result.extensions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``ArtifactClassifierExtension`` resource base + references.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.ingest.result.extensions.artifact_classifier import (
    ArtifactClassification,
    ArtifactClassifierExtension,
    CATEGORY_DIAGNOSTIC,
    CATEGORY_LOG,
    CATEGORY_OTHER,
    CATEGORY_REPORT,
    CATEGORY_TASKING,
)
from automojo.pychestrate.webservice.ingest.result.extensions.testbase_classifier import (
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
