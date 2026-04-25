"""
.. module:: orchestration.test.artifact_browser.errors
    :synopsis: Artifact-browser exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ArtifactBrowserError(Exception):
    """
        Base for recoverable artifact-browser errors.
    """


class NoMatchingRendererError(ArtifactBrowserError):
    """
        Raised when no registered :class:`ArtifactRendererProtocol`
        accepts the supplied artifact reference.
    """


class ArtifactPathInvalidError(ArtifactBrowserError):
    """
        Raised on path-traversal attempts or malformed paths.
    """
