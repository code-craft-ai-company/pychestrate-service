"""
.. module:: jobs.dispatch.errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception hierarchy for the dispatcher.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class DispatchError(Exception):
    """
        Base class for recoverable dispatcher errors. Subclasses
        classify specific failure modes so REST / wire translators
        can map each to a distinct status code.
    """


class DispatchNoCandidatesError(DispatchError):
    """
        Raised when eligibility filtering returns no candidate
        clients for a dispatch request. The request is recorded as
        ``dispatch_failed`` so operators can inspect why no pod
        qualified.
    """


class DispatchTransportError(DispatchError):
    """
        Raised when the transport adapter fails to transmit an
        envelope. The attempt row captures the underlying reason;
        callers decide whether to retry via the backoff queue (M2).
    """


class DispatchSigningUnavailableError(DispatchError):
    """
        Raised when the dispatch envelope cannot be signed because the
        service has no envelope signing key installed. Raised before
        any envelope or attempt row is written, so callers record the
        job as dispatch-failed exactly as for any other
        :class:`DispatchError` (the underlying
        ``EnvelopeSigningKeyMissingError`` used to escape those
        handlers and leave a half-created job behind).
    """


class DispatchStrategyNotRegisteredError(DispatchError):
    """
        Raised when :func:`resolve_factory_implementation` cannot
        find a :class:`DispatchStrategyProtocol` implementation.
        Service bootstrap SHOULD register
        :class:`FifoDispatchStrategy` before any dispatch can fire.
    """
