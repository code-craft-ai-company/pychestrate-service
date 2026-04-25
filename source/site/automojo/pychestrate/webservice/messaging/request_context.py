"""
.. module:: messaging.request_context
    :synopsis: Ambient request_id ContextVar for the M2 message bus.

The web app host stamps a per-request ``request_id`` on the
ambient :class:`ContextVar` at the start of every request.
The M2 dispatcher reads that value with :func:`current_request_id`
and folds it into every published :class:`Event` so a
subscriber can correlate downstream activity back to the
originating request without the publisher having to thread
the id through every call site.

The ContextVar is process-local but propagates correctly
across asyncio tasks (each task inherits the parent's
context). Synchronous worker threads do *not* inherit the
context — the M2 dispatcher captures the request_id at
publish time on the publisher's thread and passes it
through the subscriber-queue payload, then the worker
thread re-installs it via :func:`bind_request_id` for the
duration of the subscriber callback.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional


_REQUEST_ID: ContextVar[Optional[str]] = ContextVar(
    "pychestrate.messaging.request_id", default=None,
)


def current_request_id() -> Optional[str]:
    """
        Return the request_id bound to the current context, or
        ``None`` when no caller has stamped one.
    """
    rtnval = _REQUEST_ID.get()
    return rtnval


def set_request_id(*, request_id: Optional[str]):
    """
        Imperative setter that stamps ``request_id`` on the
        current context. Returns the
        :class:`contextvars.Token` the caller passes to
        :func:`reset_request_id` once the request boundary
        ends.

        Most callers should use the :func:`bound_request_id`
        context manager instead — it guarantees the reset
        runs even on exception.
    """
    rtnval = _REQUEST_ID.set(request_id)
    return rtnval


def reset_request_id(*, token) -> None:
    """
        Restore the prior request_id binding using the token
        returned by :func:`set_request_id`. Tolerates a
        ``None`` token so the caller can roll back without
        bookkeeping.
    """
    if token is None:
        return
    _REQUEST_ID.reset(token)
    return


@contextmanager
def bound_request_id(*, request_id: Optional[str]) -> Iterator[Optional[str]]:
    """
        Context manager that stamps ``request_id`` on the
        ambient ContextVar for the duration of the ``with``
        block and restores the prior value on exit.

        Use this at the request boundary in the web host and
        inside subscriber workers when re-installing the
        captured publisher request_id.
    """
    token = _REQUEST_ID.set(request_id)
    try:
        yield request_id
    finally:
        _REQUEST_ID.reset(token)
    return


def reset_for_testing() -> None:
    """
        Drop the binding back to the default ``None``. Tests
        use this to keep prior set_request_id calls from
        leaking across cases. The default-token reset path
        sidesteps the rebind-token machinery so it works
        even when no token was returned.
    """
    _REQUEST_ID.set(None)
    return
