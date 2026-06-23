"""
.. module:: webinterface.foundation.flash
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One-shot user-facing messages keyed off the
               cookie-backed UI session.

.. moduleauthor:: Code Craft AI LLC

Handlers call ``add_flash(session, 'message', 'category')`` to
queue a user-facing message that the next request renders and
discards. Messages live in the cookie-backed UI session; on the
next request the template calls :func:`consume_flashes` to drain
them.

This module exposes that pattern:

* :func:`add_flash` -- append a ``(category, message)`` pair to
  the session's flash queue.

* :func:`consume_flashes` -- drain the queue, returning the
  list of pairs and clearing the session entry. The caller's
  template iterates the result.

* :func:`peek_flashes` -- read without draining (test-friendly /
  for debugging).

The flash queue is stored under :data:`SESSION_KEY` in the
session dict; the handler that triggers a flash MUST re-write
the session cookie on the response (typically via the
auth-guard helper that already manages the session-cookie
write-back).

Categories
----------

The conventional categories are ``"info"`` / ``"success"`` /
``"warning"`` / ``"error"``. This module accepts arbitrary
strings -- the existing config blueprint passes ``"warning"`` /
``"error"`` / ``"success"`` and templates branch on those
exact strings.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Tuple


SESSION_KEY: str = "flashes"

CATEGORY_INFO: str = "info"
CATEGORY_SUCCESS: str = "success"
CATEGORY_WARNING: str = "warning"
CATEGORY_ERROR: str = "error"


def add_flash(
        *,
        session: Dict[str, Any],
        message: str,
        category: str = CATEGORY_INFO
    ) -> None:
    """
        Append a flash message to the session's queue.

        :param session: Session dict (from
                        :func:`cookie_session.read_session_from_request`).
        :param message: User-facing message string.
        :param category: Category for template branching
                         (info / success / warning / error).

        :returns: None.
    """
    queue = session.get(SESSION_KEY, None)
    if not isinstance(queue, list):
        queue = []
    queue.append([category, message])
    session[SESSION_KEY] = queue
    return


def consume_flashes(
        *, session: Dict[str, Any]
    ) -> List[Tuple[str, str]]:
    """
        Drain the flash queue, returning the messages and clearing
        the session entry. The handler that calls this MUST re-
        write the session cookie on the response so the consumed
        messages do not re-render on the next request.

        :param session: Session dict.

        :returns: List of ``(category, message)`` tuples in
                  insertion order. Empty list when the queue is
                  empty.
    """
    raw_queue = session.get(SESSION_KEY, None)
    if not isinstance(raw_queue, list):
        if SESSION_KEY in session:
            del session[SESSION_KEY]
        return []

    rtnval: List[Tuple[str, str]] = []
    for entry in raw_queue:
        if isinstance(entry, list) and len(entry) >= 2:
            rtnval.append((str(entry[0]), str(entry[1])))
    if SESSION_KEY in session:
        del session[SESSION_KEY]
    return rtnval


def peek_flashes(
        *, session: Dict[str, Any]
    ) -> List[Tuple[str, str]]:
    """
        Read the flash queue without draining. Useful for tests
        that want to verify a flash was queued without consuming
        it.

        :param session: Session dict.

        :returns: List of ``(category, message)`` tuples.
    """
    raw_queue = session.get(SESSION_KEY, None)
    if not isinstance(raw_queue, list):
        return []

    rtnval: List[Tuple[str, str]] = []
    for entry in raw_queue:
        if isinstance(entry, list) and len(entry) >= 2:
            rtnval.append((str(entry[0]), str(entry[1])))
    return rtnval


__all__ = [
    "SESSION_KEY",
    "CATEGORY_INFO",
    "CATEGORY_SUCCESS",
    "CATEGORY_WARNING",
    "CATEGORY_ERROR",
    "add_flash",
    "consume_flashes",
    "peek_flashes",
]
