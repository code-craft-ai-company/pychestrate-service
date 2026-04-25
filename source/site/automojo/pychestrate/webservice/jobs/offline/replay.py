"""
.. module:: jobs.offline.replay
    :synopsis: ReplayCoordinator — accept replayed progress with cursor checks.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.jobs.offline.errors import (
    ReplayAuthError,
    ReplaySeqGapError,
)
from automojo.pychestrate.webservice.jobs.offline.models import (
    ClientReplayCursor,
)


@dataclass(frozen=True)
class ReplayResult:
    """
        Outcome of one replay-record acceptance.

        :param accepted: Whether the record advanced the cursor.
        :param cursor_advanced_to: New ``next_expected_sequence``.
    """
    accepted: bool
    cursor_advanced_to: int


class ReplayCoordinator:
    """
        Owns the per-(client, run) monotonic cursor.
    """

    def accept_replay(
            self,
            *,
            db_session: DbSession,
            client_id: str,
            run_id: str,
            sequence: int,
            authenticated_client_id: str
        ) -> ReplayResult:
        """
            Advance the cursor for ``(client_id, run_id)`` to
            ``sequence + 1`` after verifying:

            * ``authenticated_client_id`` matches ``client_id``
              (raises :class:`ReplayAuthError`).
            * ``sequence`` equals the current
              ``next_expected_sequence`` — out-of-order or
              skipped records raise :class:`ReplaySeqGapError`.

            Idempotent on the same ``sequence`` only when it
            equals the cursor's current value; replaying a record
            whose sequence is already past advances neither
            cursor nor returns ``accepted=True``.
        """
        if authenticated_client_id != client_id:
            err_lines = ["Replay client mismatch."]
            err_lines.append("CURSOR_CLIENT: {}".format(client_id))
            err_lines.append("AUTHENTICATED_CLIENT: {}".format(authenticated_client_id))
            err_msg = os.linesep.join(err_lines)
            raise ReplayAuthError(err_msg) from None

        cursor = (
            db_session.query(ClientReplayCursor)
            .filter(ClientReplayCursor.client_id == client_id)
            .filter(ClientReplayCursor.run_id == run_id)
            .first()
        )
        if cursor is None:
            cursor = ClientReplayCursor(
                cursor_id=new_uuid(),
                client_id=client_id,
                run_id=run_id,
                next_expected_sequence=0,
            )
            db_session.add(cursor)
            db_session.flush()

        expected = int(cursor.next_expected_sequence)
        if sequence < expected:
            # Already-applied; idempotent no-op.
            rtnval = ReplayResult(accepted=False, cursor_advanced_to=expected)
            return rtnval
        if sequence > expected:
            err_lines = ["Replay sequence gap detected."]
            err_lines.append("CLIENT_ID: {}".format(client_id))
            err_lines.append("RUN_ID: {}".format(run_id))
            err_lines.append("EXPECTED: {}".format(expected))
            err_lines.append("RECEIVED: {}".format(sequence))
            err_msg = os.linesep.join(err_lines)
            raise ReplaySeqGapError(err_msg) from None

        cursor.next_expected_sequence = expected + 1
        cursor.updated_at = utc_now()
        db_session.flush()
        db_session.commit()

        rtnval = ReplayResult(
            accepted=True,
            cursor_advanced_to=cursor.next_expected_sequence,
        )
        return rtnval
