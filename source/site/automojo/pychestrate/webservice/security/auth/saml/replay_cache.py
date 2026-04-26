"""
.. module:: security.auth.saml.replay_cache
    :synopsis: SAML 2.0 replay cache keyed on Response/@ID.

The SAML callback path consults this module to reject any
``samlp:Response`` whose top-level ``ID`` attribute the
service has already seen — that is the canonical replay
defense the OASIS spec mandates and the design.md target
calls out under "SAML: replay cache keyed on Response/@ID".

The cache is backed by the ``auth_saml_replay_cache`` table
(declared in :mod:`security.auth.models`):

* ``response_id`` — primary key, the Response's ``ID`` attribute.
* ``not_on_or_after`` — the assertion's
  ``Conditions/@NotOnOrAfter`` so the row can be pruned once
  the assertion can no longer be replayed against any
  conforming validator.

:func:`record_response_id` is the write-once gate the
callback path opens once the assertion has otherwise
validated; an attempt to record an id that has already
landed bubbles :class:`SamlReplayDetectedError`. Production
controllers wrap this call inside the same transaction
that opens the session row so a concurrent replay either
loses the row insert or sees the existing row.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.security.auth.models import (
    AuthSamlReplayCache,
)


class SamlReplayDetectedError(Exception):
    """
        Raised when :func:`record_response_id` is called
        with a ``response_id`` that has already been
        recorded — the caller MUST NOT seat a session
        against the assertion.
    """


def record_response_id(
        *,
        db_session: DbSession,
        response_id: str,
        not_on_or_after: datetime
    ) -> AuthSamlReplayCache:
    """
        Atomically record a ``Response/@ID`` in the replay
        cache.

        :param db_session: Active SQLAlchemy session.
        :param response_id: The Response's ``ID`` attribute.
        :param not_on_or_after: ``Conditions/@NotOnOrAfter``
                                from the assertion — used as
                                the prune horizon.

        :returns: Persisted :class:`AuthSamlReplayCache`.
        :raises: ValueError on missing inputs;
                 SamlReplayDetectedError when the id has
                 already been recorded.
    """
    if db_session is None:
        err_lines = ["record_response_id requires a db_session."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if response_id is None or len(response_id) == 0:
        err_lines = ["record_response_id requires a non-empty response_id."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if not_on_or_after is None:
        err_lines = [
            "record_response_id requires a non-None not_on_or_after.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    existing = (
        db_session.query(AuthSamlReplayCache)
        .filter(AuthSamlReplayCache.response_id == response_id)
        .first()
    )
    if existing is not None:
        err_lines = [
            "SAML response id has already been recorded — replay rejected.",
            "RESPONSE_ID: {}".format(response_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise SamlReplayDetectedError(err_msg) from None

    row = AuthSamlReplayCache(
        response_id=response_id,
        not_on_or_after=not_on_or_after,
    )
    db_session.add(row)
    db_session.flush()
    db_session.commit()
    rtnval = row
    return rtnval


def is_recorded(
        *,
        db_session: DbSession,
        response_id: str
    ) -> bool:
    """
        Return ``True`` when ``response_id`` is already
        present in the replay cache. Read-only helper used
        by tests and the M3 hardening pass.
    """
    if db_session is None:
        err_lines = ["is_recorded requires a db_session."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if response_id is None or len(response_id) == 0:
        err_lines = ["is_recorded requires a non-empty response_id."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    existing = (
        db_session.query(AuthSamlReplayCache)
        .filter(AuthSamlReplayCache.response_id == response_id)
        .first()
    )
    rtnval = existing is not None
    return rtnval


def sweep_expired(
        *,
        db_session: DbSession,
        now: Optional[datetime] = None
    ) -> int:
    """
        Drop every row whose ``not_on_or_after`` is at or
        before ``now``. Returns the number of rows deleted.

        Designed to be called from a periodic job — keeps
        the replay table from growing without bound across
        years of assertions.
    """
    if db_session is None:
        err_lines = ["sweep_expired requires a db_session."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    materialized_now = now if now is not None else _now_utc()
    rows = (
        db_session.query(AuthSamlReplayCache)
        .filter(AuthSamlReplayCache.not_on_or_after <= materialized_now)
        .all()
    )
    if rows is None or len(rows) == 0:
        return 0
    deleted = 0
    for row in rows:
        db_session.delete(row)
        deleted += 1
    db_session.flush()
    db_session.commit()
    rtnval = deleted
    return rtnval


def _now_utc() -> datetime:
    rtnval = datetime.now(tz=timezone.utc)
    return rtnval
