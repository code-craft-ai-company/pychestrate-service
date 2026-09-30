"""
.. module:: webinterface.foundation.form_drafts
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Keep what a person typed when their sign-in or form token expires (XC-11).

.. moduleauthor:: Code Craft AI LLC

A form submitted after the session cookie expired, or with a stale anti-forgery token,
was answered with a redirect: to the sign-in page (a ``GET``, so the submitted text was
gone) or to an empty form with "Invalid request. Please try again." Everything typed
into a long form (a build specification, a release template) was lost.

This module keeps it, server-side and briefly:

* A WSGI wrapper (:func:`wrap_wsgi_app_with_form_capture`) notes the fields of an
  ordinary form ``POST`` to one of the paths in :data:`DRAFT_PATH_PREFIXES` for the
  duration of the request, and hands the body on unchanged.
* When the request ends in one of the two refusals (:func:`~auth_guard.require_login_or_redirect`
  or :func:`~auth_guard.enforce_csrf_or_redirect`), the guard calls :func:`attach_draft`,
  which saves the fields as a draft and adds ``?draft=<token>`` to the redirect (to the
  ``next`` address of a sign-in redirect, so the token survives the sign-in).
* The page the person lands on asks :func:`take_draft` for the draft (the shell document
  does, for every page); a draft is returned once, only to the path it was saved for, and
  is deleted as it is read. The shell puts the values back into the form and says so.

A draft holds text people typed, so it is kept for ten minutes, only for the form paths
that hold no secrets, never with a field whose name suggests a secret, and only as its
SHA-256 digest is looked up: the token itself is in the address of the page the person is
sent to, and nowhere else.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import io
import logging
import re
import secrets
import threading

from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, parse_qs, urlencode, urlsplit, urlunsplit

from ccai.pychestrate.core.defaults import new_uuid, utc_now


_LOGGER = logging.getLogger(__name__)


#: The address parameter that carries a draft's token.
DRAFT_QUERY_PARAM: str = "draft"

#: How long a draft is kept.
DRAFT_LIFETIME = timedelta(minutes=10)

#: Only forms under these paths are kept: they hold names, descriptions, JSON documents
#: and settings, not credentials. (Secrets, variables, API tokens, enrollment tokens and
#: the sign-in and password pages are not on the list.)
DRAFT_PATH_PREFIXES: Tuple[str, ...] = ("/projects/", "/resources/", "/admin/users", "/admin/roles", "/admin/rpa-job-types")

#: A field whose name says it may hold a secret is never kept.
SECRET_FIELD_NAME = re.compile(r"pass|secret|token|credential|csrf|pepper|otp|mfa|private", re.IGNORECASE)

MAX_BODY_BYTES: int = 256 * 1024
MAX_FIELDS: int = 200
MAX_VALUE_CHARS: int = 20000
MAX_TOTAL_CHARS: int = 100000

Field = Tuple[str, str]

_CURRENT = threading.local()


def keeps_forms_at(path: str) -> bool:
    """
        Whether forms posted to ``path`` are kept.

        :param path: The request path.

        :returns: ``True`` for a path under :data:`DRAFT_PATH_PREFIXES`.
    """
    return path.startswith(DRAFT_PATH_PREFIXES)


def keepable_fields(pairs: List[Field]) -> List[Field]:
    """
        The fields worth keeping from a submitted form: not a secret-looking name, not empty,
        within the size limits.

        :param pairs: The submitted ``(name, value)`` pairs in order.

        :returns: The pairs to store.
    """
    kept: List[Field] = []
    total = 0
    for name, value in pairs:
        if len(kept) >= MAX_FIELDS:
            break
        if len(value) == 0 or SECRET_FIELD_NAME.search(name) is not None or len(name) > 128:
            continue
        clipped = value[:MAX_VALUE_CHARS]
        if total + len(clipped) > MAX_TOTAL_CHARS:
            break
        total += len(clipped)
        kept.append((name, clipped))
    return kept


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_factory() -> Any:
    from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS  # noqa: E402
    return SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY


def save_draft(*, path: str, pairs: List[Field], session_factory: Any = None) -> Optional[str]:
    """
        Save a form's fields as a draft.

        :param path: The path of the form (the page the person is sent back to).
        :param pairs: The submitted ``(name, value)`` pairs.
        :param session_factory: Returns a new session; the service's own when ``None``.

        :returns: The draft's token, or ``None`` when there is nothing worth keeping or it
                  could not be stored (a draft is a courtesy and never blocks the redirect).
    """
    fields = keepable_fields(pairs)
    if len(fields) == 0:
        return None
    factory = session_factory if session_factory is not None else _session_factory()
    if factory is None:
        return None
    from ccai.pychestrate.webservice.security.auth.models import UiFormDraft  # noqa: E402

    token = secrets.token_urlsafe(32)
    now = utc_now()
    session = factory()
    try:
        session.query(UiFormDraft).filter(UiFormDraft.expires_at < now).delete()
        session.add(UiFormDraft(
            draft_id=new_uuid(), token_hash=_digest(token), path=path[:512],
            fields=[[name, value] for name, value in fields], created_at=now, expires_at=now + DRAFT_LIFETIME,
        ))
        session.commit()
    except Exception as xcpt:  # noqa: BLE001 -- best effort
        _LOGGER.warning("pychestrate.form_drafts.save_failed: %s: %s", type(xcpt).__name__, xcpt)
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
    finally:
        session.close()
    return token


def take_draft(*, token: str, path: str, session_factory: Any = None) -> Optional[List[Field]]:
    """
        Read a draft and delete it. A draft is returned once, only to the path it was saved
        for, and only while it has not expired; anything else leaves it where it is (a wrong
        path) or removes it (an expired draft) and returns ``None``.

        :param token: The token from the address.
        :param path: The path of the page asking.
        :param session_factory: Returns a new session; the service's own when ``None``.

        :returns: The ``(name, value)`` pairs, or ``None``.
    """
    if len(token) < 20 or len(token) > 128:
        return None
    factory = session_factory if session_factory is not None else _session_factory()
    if factory is None:
        return None
    from ccai.pychestrate.webservice.security.auth.models import UiFormDraft  # noqa: E402

    session = factory()
    try:
        row = session.query(UiFormDraft).filter(UiFormDraft.token_hash == _digest(token)).first()
        if row is None:
            return None
        if row.expires_at < utc_now():
            session.delete(row)
            session.commit()
            return None
        if row.path != path:
            return None
        pairs = [(str(name), str(value)) for name, value in (row.fields or [])]
        session.delete(row)
        session.commit()
        return pairs
    except Exception as xcpt:  # noqa: BLE001 -- best effort
        _LOGGER.warning("pychestrate.form_drafts.take_failed: %s: %s", type(xcpt).__name__, xcpt)
        return None
    finally:
        session.close()


class _Finishing:
    """The response body, which forgets the captured form when the server is done with it."""

    def __init__(self, result: Any) -> None:
        self._result = result

    def __iter__(self) -> Any:
        return iter(self._result)

    def close(self) -> None:
        try:
            close = getattr(self._result, "close", None)
            if close is not None:
                close()
        finally:
            end_capture()


class _Captured:
    def __init__(self, path: str, pairs: List[Field]) -> None:
        self.path = path
        self.pairs = pairs


def begin_capture(*, path: str, pairs: List[Field]) -> None:
    """Note the current request's form (tests use this; the WSGI wrapper calls it)."""
    _CURRENT.value = _Captured(path, pairs)


def end_capture() -> None:
    """Forget the current request's form."""
    _CURRENT.value = None


def attach_draft(url: str, *, session_factory: Any = None) -> str:
    """
        Add the current request's form, saved as a draft, to a redirect address. A no-op
        (the address comes back unchanged) when the request is not a kept form.

        For a sign-in address the token goes into its ``next`` parameter, so it is still there
        when the person is sent on after signing in; for any other address it becomes a
        ``draft`` parameter of the address itself.

        :param url: The address the guard is about to redirect to.
        :param session_factory: Returns a new session; the service's own when ``None``.

        :returns: The address, with the draft's token in it when one was saved.
    """
    captured = getattr(_CURRENT, "value", None)
    if captured is None or len(captured.pairs) == 0:
        return url
    token = save_draft(path=captured.path, pairs=captured.pairs, session_factory=session_factory)
    if token is None:
        return url
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    for index, (name, value) in enumerate(query):
        if name == "next" and value.startswith("/") and value.startswith("//") is False:
            inner = urlsplit(value)
            inner_query = [pair for pair in parse_qsl(inner.query, keep_blank_values=True) if pair[0] != DRAFT_QUERY_PARAM]
            inner_query.append((DRAFT_QUERY_PARAM, token))
            query[index] = ("next", urlunsplit(("", "", inner.path, urlencode(inner_query), inner.fragment)))
            return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    query = [pair for pair in query if pair[0] != DRAFT_QUERY_PARAM]
    query.append((DRAFT_QUERY_PARAM, token))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def wrap_wsgi_app_with_form_capture(*, wsgi_app: Any) -> Any:
    """
        Wrap a WSGI application so an ordinary form ``POST`` to a kept path is noted for the
        length of the request (see the module note). The body is read and handed on
        unchanged; anything else (another method, a multipart upload, a large body, another
        path) passes straight through.

        :param wsgi_app: The application to wrap.

        :returns: The wrapping application.
    """

    def _application(environ: Dict[str, Any], start_response: Any) -> Any:
        noted = False
        try:
            if (
                str(environ.get("REQUEST_METHOD", "")).upper() == "POST"
                and str(environ.get("CONTENT_TYPE", "")).split(";")[0].strip().lower() == "application/x-www-form-urlencoded"
                and keeps_forms_at(str(environ.get("PATH_INFO", "")))
            ):
                try:
                    length = int(environ.get("CONTENT_LENGTH") or 0)
                except ValueError:
                    length = 0
                if 0 < length <= MAX_BODY_BYTES:
                    body = environ["wsgi.input"].read(length)
                    environ["wsgi.input"] = io.BytesIO(body)
                    begin_capture(path=str(environ["PATH_INFO"]), pairs=parse_qsl(body.decode("utf-8", "replace"), keep_blank_values=True))
                    noted = True
            result = wsgi_app(environ, start_response)
        except BaseException:
            if noted:
                end_capture()
            raise
        if noted is False:
            return result
        return _Finishing(result)

    return _application


__all__ = [
    "DRAFT_LIFETIME",
    "DRAFT_PATH_PREFIXES",
    "DRAFT_QUERY_PARAM",
    "SECRET_FIELD_NAME",
    "attach_draft",
    "begin_capture",
    "end_capture",
    "keepable_fields",
    "keeps_forms_at",
    "save_draft",
    "take_draft",
    "wrap_wsgi_app_with_form_capture",
]
