"""
.. module:: ops.release.errors
    :synopsis: Release-channels exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ReleaseError(Exception):
    """
        Base for recoverable release errors.
    """


class ReleaseSigningKeyUnavailableError(ReleaseError):
    """
        Raised when the signer cannot produce a signature
        because the key is missing, expired, or the signer
        subprocess is unreachable.
    """


class ReleaseStageInProgressError(ReleaseError):
    """
        Raised when a publish would preempt an in-flight stage
        and the caller did not present
        ``system:release.preempt``.
    """


class ReleaseBakeNotMetError(ReleaseError):
    """
        Raised when a promote runs before the channel-policy
        bake window has elapsed (and no bypass was granted).
    """


class NoPriorReleaseError(ReleaseError):
    """
        Raised when ``rollback_channel`` is invoked but no
        prior release exists on the channel to restore.
    """


class ReleaseNotActiveError(ReleaseError):
    """
        Raised when a promote is called on a superseded /
        rolled-back / withdrawn release.
    """


class ManifestVerificationError(ReleaseError):
    """
        Raised when a manifest + signature pair fails the
        Ed25519 verification against
        ``trusted_issuer_keys``.
    """


class ReleaseConflictError(ReleaseError):
    """
        Raised when a (component, version, channel) triple is
        already on the ledger.
    """
