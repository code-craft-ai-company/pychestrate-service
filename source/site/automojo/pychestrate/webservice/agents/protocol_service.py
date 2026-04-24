"""
.. module:: agents.protocol_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 3-client-agent-protocol session + frame audit service.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, List, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.agents.events import (
    ClientAgentProtocolEventTopics,
)
from automojo.pychestrate.webservice.agents.exceptions import (
    FrameValidationError,
    SessionClosedError,
)
from automojo.pychestrate.webservice.agents.models import (
    ClientFrameAudit,
    ClientSession,
    FrameDirection,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


_ALLOWED_FRAME_KINDS = frozenset({
    "enroll",
    "heartbeat",
    "capability_advertisement",
    "register",
    "deregister",
    "dispatch",
    "progress",
    "result",
    "upgrade_offer",
    "upgrade_outcome",
})


def open_session(
        *,
        db_session: DbSession,
        transport_name: str,
        remote_addr: Optional[str],
        cert_serial: Optional[str],
        client_id: Optional[str]
    ) -> ClientSession:
    """
        Record a new client session and publish ``entity.client.session_opened``.
    """
    if transport_name is None or len(transport_name.strip()) == 0:
        raise SemanticError("transport_name is required")

    session_row = ClientSession(
        session_id=new_uuid(),
        client_id=client_id,
        transport_name=transport_name.strip(),
        remote_addr=remote_addr,
        cert_serial=cert_serial,
        opened_at=utc_now(),
    )
    db_session.add(session_row)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ClientAgentProtocolEventTopics.SESSION_OPENED,
            payload={
                "session_id": str(session_row.session_id),
                "transport_name": transport_name,
                "client_id": str(client_id) if client_id is not None else None,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return session_row


def close_session(
        *,
        db_session: DbSession,
        session_id: str,
        close_code: str
    ) -> None:
    """
        Mark a session as closed.
    """
    row = (
        db_session.query(ClientSession)
        .filter(ClientSession.session_id == session_id)
        .first()
    )
    if row is None:
        return
    if row.closed_at is not None:
        return
    row.closed_at = utc_now()
    row.close_code = close_code
    db_session.add(row)
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ClientAgentProtocolEventTopics.SESSION_CLOSED,
            payload={
                "session_id": str(session_id),
                "close_code": close_code,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def record_frame(
        *,
        db_session: DbSession,
        session_id: str,
        kind: str,
        direction: FrameDirection,
        size_bytes: int,
        accepted: bool,
        reject_reason: Optional[str]
    ) -> ClientFrameAudit:
    """
        Persist a :class:`ClientFrameAudit` row. Raises
        :class:`FrameValidationError` when the frame kind is unknown.
    """
    validate_frame_kind(kind=kind)

    session_row = (
        db_session.query(ClientSession)
        .filter(ClientSession.session_id == session_id)
        .first()
    )
    if session_row is None or session_row.closed_at is not None:
        err_msg_lines = ["Cannot record frame — session is closed or missing."]
        err_msg_lines.append("SESSION_ID: {}".format(session_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise SessionClosedError(err_msg) from None

    row = ClientFrameAudit(
        frame_id=new_uuid(),
        session_id=session_id,
        kind=kind,
        direction=direction,
        size_bytes=int(size_bytes),
        received_at=utc_now(),
        accepted=bool(accepted),
        reject_reason=reject_reason,
    )
    db_session.add(row)
    db_session.flush()

    if accepted is False:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=ClientAgentProtocolEventTopics.FRAME_REJECTED,
                payload={
                    "session_id": str(session_id),
                    "kind": kind,
                    "reason": reject_reason,
                },
                source_event_id=new_uuid(),
            ),
        )

    db_session.commit()
    return row


def heartbeat(
        *,
        db_session: DbSession,
        session_id: str,
        agent_version: Optional[str]
    ) -> None:
    """
        Emit a heartbeat event for session-level liveness tracking.
    """
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ClientAgentProtocolEventTopics.HEARTBEAT,
            payload={
                "session_id": str(session_id),
                "agent_version": agent_version,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def validate_frame_kind(*, kind: str) -> None:
    """
        Reject unknown frame kinds.

        :raises: FrameValidationError
    """
    if kind is None or kind not in _ALLOWED_FRAME_KINDS:
        err_msg_lines = ["Unknown frame kind."]
        err_msg_lines.append("KIND: {}".format(kind))
        err_msg_lines.append("ALLOWED: {}".format(sorted(_ALLOWED_FRAME_KINDS)))
        err_msg = os.linesep.join(err_msg_lines)
        raise FrameValidationError(err_msg)
    return
