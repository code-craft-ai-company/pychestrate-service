"""
.. module:: jobs.results.errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception types for the shared-results backend.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class SharedResultsError(Exception):
    """
        Base class for shared-results backend errors.
    """


class AllocationNotFoundError(SharedResultsError):
    """
        Raised by :meth:`SharedResultsBackend.resolve` when no
        allocation row exists for the given run id.
    """


class PathComponentInvalidError(SharedResultsError):
    """
        Raised by :func:`canonicalize_component` when a component
        cannot be sanitized into a safe filesystem segment (empty
        after sanitization, or excessively long).
    """


class ArtifactPathInvalidError(SharedResultsError):
    """
        Raised by :func:`presign.canonicalize_relative_path` when a
        client-supplied relative artifact path is empty, absolute,
        carries a ``..`` traversal segment, or is otherwise unsafe
        to map onto the run's result-tree prefix.
    """


class TooManyArtifactPathsError(SharedResultsError):
    """
        Raised by :func:`presign.validate_artifact_path_batch` when
        a single ``:presign`` request asks for more paths -- or a
        greater summed path length -- than the configured caps.
    """


class PresignSignatureInvalidError(SharedResultsError):
    """
        Raised by :func:`presign.verify_upload_signature` when a
        presented local-fs upload signature is missing, malformed,
        does not match the server-held secret, or has expired.
    """
