"""
.. module:: artifacts.errors
    :synopsis: Artifact-store exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ArtifactError(Exception):
    """
        Base for artifact-store errors.
    """


class ArtifactBlobNotFoundError(ArtifactError):
    """
        Raised when a CAS digest does not match a persisted blob.
    """


class ArtifactReferenceNotFoundError(ArtifactError):
    """
        Raised when ``get`` cannot find a reference for the
        supplied ``(run_id, label)`` pair.
    """
