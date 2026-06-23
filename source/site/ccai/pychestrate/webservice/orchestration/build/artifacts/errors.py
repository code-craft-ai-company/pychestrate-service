"""
.. module:: orchestration.build.artifacts.errors
    :synopsis: Build-artifacts exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class BuildArtifactsError(Exception):
    """
        Base for recoverable build-artifacts errors.
    """


class BuildArtifactManifestNotFoundError(BuildArtifactsError):
    """
        Raised when a manifest lookup misses.
    """


class ArtifactTypeUnknownError(BuildArtifactsError):
    """
        Raised when an entry references an unknown
        ``artifact_type``.
    """


class ArtifactEntryInvalidError(BuildArtifactsError):
    """
        Raised when an entry's payload fails the artifact
        type's input validation.
    """
