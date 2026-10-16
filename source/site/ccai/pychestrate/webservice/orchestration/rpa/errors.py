"""
.. module:: orchestration.rpa.errors
    :synopsis: RPA-orchestration exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List, Optional, Tuple


class RpaError(Exception):
    """
        Base for recoverable RPA-orchestration errors.
    """


class RpaJobTypeNotFoundError(RpaError):
    """
        Raised when a job type lookup misses.
    """


class RpaJobTypeInvalidError(RpaError):
    """
        Raised when a job type or version payload violates an
        invariant (bad slug, unknown execution mode, entrypoint
        rejected by the execution-mode driver, ...).
    """


class RpaJobTypeRetiredError(RpaError):
    """
        Raised when a run is requested against a retired job type.
    """


class DuplicateRpaJobTypeError(RpaError):
    """
        Raised when a job type slug is already registered.
    """


class RpaVersionNotFoundError(RpaError):
    """
        Raised when a version lookup misses.
    """


class RpaVersionNotActiveError(RpaError):
    """
        Raised when a specification selects a version that is not
        active, or when ``latest-active`` finds no active version.
    """


class DuplicateVersionError(RpaError):
    """
        Raised when ``(type_id, version)`` is already published.
    """


class RpaSpecNotFoundError(RpaError):
    """
        Raised when a specification lookup misses.
    """


class RpaSpecInvalidError(RpaError):
    """
        Raised when a specification payload violates an invariant.
    """


class DuplicateRpaSpecError(RpaError):
    """
        Raised when a specification name is already used in the project.
    """


class RpaJobNotFoundError(RpaError):
    """
        Raised when a job lookup misses.
    """


class RpaJobNotCancellableError(RpaError):
    """
        Raised when cancel is requested for a job already terminal.
    """


class PacketValidationError(RpaError):
    """
        Raised when the merged work packet fails the job type's
        JSON schema. ``issues`` carries ``(json_pointer, message)``
        pairs, one per failing path.
    """

    def __init__(self, message: str, issues: Optional[List[Tuple[str, str]]] = None) -> None:
        super().__init__(message)
        self.issues: List[Tuple[str, str]] = list(issues or [])
        return


class RpaSecretReferenceError(PacketValidationError):
    """
        Raised when a vault secret reference in a packet cannot be used: the secret does not exist or has expired, the person saving or running it may
        not read it, or there is no signed-in user to check. ``issues`` carries ``(json_pointer, message)`` pairs, one per reference, and never a value.
    """


class PacketTooLargeError(RpaError):
    """
        Raised when the serialized work packet exceeds the size cap.
    """


class CapabilityMismatchError(RpaError):
    """
        Raised when no eligible pod advertises the capabilities the
        job type or specification requires.
    """


class RpaDispatchUnavailableError(RpaError):
    """
        Raised when no :class:`JobDispatcher` is wired.
    """


class RpaDispatchFailedError(RpaError):
    """
        Raised when the dispatcher rejected the job envelope. The
        job row is left ``FAILED`` with a ``final_state_reason``.
    """
