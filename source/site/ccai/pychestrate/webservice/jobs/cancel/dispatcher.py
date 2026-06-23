"""
.. module:: jobs.cancel.dispatcher
    :synopsis: CancelDispatcher — cancel RPC + ack handling.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.jobs.cancel import repository
from ccai.pychestrate.webservice.jobs.cancel.errors import (
    CancelDuplicateRequestError,
    CancelTransportError,
)
from ccai.pychestrate.webservice.jobs.cancel.events import (
    CancelEventTopics,
)
from ccai.pychestrate.webservice.jobs.cancel.models import (
    CancelRequest,
    CancelStatus,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event


class CancelTransportProtocol:
    """
        Contract for cancel-RPC transports. Real implementations
        wrap the agent-protocol channel; M1 ships the
        :class:`InMemoryCancelTransport` for tests.
    """

    def transport_name(self) -> str:
        raise NotImplementedError("subclasses must implement transport_name")

    def send_cancel(
            self,
            *,
            run_id: str,
            client_id: str,
            request_id: str,
            reason: str
        ) -> None:
        """
            Deliver the cancel request to the target client. MUST
            raise :class:`CancelTransportError` on transport
            failure.
        """
        raise NotImplementedError("subclasses must implement send_cancel")


@dataclass(frozen=True)
class CancelTransportCall:
    """
        One recorded cancel transmission.
    """
    request_id: str
    run_id: str
    client_id: str
    reason: str


class InMemoryCancelTransport(CancelTransportProtocol):
    """
        Test transport. Records every send + supports failure
        injection.
    """

    def __init__(self) -> None:
        self._calls: List[CancelTransportCall] = []
        self._lock: threading.Lock = threading.Lock()
        self._next_failure: Optional[str] = None
        return

    def transport_name(self) -> str:
        rtnval = "in-memory-cancel"
        return rtnval

    def configure_failure(self, *, reason: Optional[str]) -> None:
        with self._lock:
            self._next_failure = reason
        return

    def send_cancel(
            self,
            *,
            run_id: str,
            client_id: str,
            request_id: str,
            reason: str
        ) -> None:
        with self._lock:
            pending = self._next_failure
            self._next_failure = None
        if pending is not None:
            raise CancelTransportError(pending) from None
        with self._lock:
            self._calls.append(
                CancelTransportCall(
                    request_id=request_id,
                    run_id=run_id,
                    client_id=client_id,
                    reason=reason,
                ),
            )
        return

    def calls(self) -> List[CancelTransportCall]:
        with self._lock:
            rtnval = list(self._calls)
        return rtnval


class CancelDispatcher:
    """
        Facade that owns the cancel-RPC transmit + ack lifecycle.
    """

    def __init__(self, *, transport: CancelTransportProtocol) -> None:
        self._transport: CancelTransportProtocol = transport
        return

    def transport(self) -> CancelTransportProtocol:
        rtnval = self._transport
        return rtnval

    def send_cancel_rpc(
            self,
            *,
            db_session: DbSession,
            run_id: str,
            project_id: str,
            client_id: str,
            requested_by: Optional[str],
            reason: str
        ) -> CancelRequest:
        """
            Open a fresh cancel request, transmit it, and persist
            the outcome. Raises :class:`CancelDuplicateRequestError`
            when an open request already exists for the run.
            Transport failures flip the row to FAILED and surface
            :class:`CancelTransportError`.
        """
        existing = repository.find_open_for_run(
            db_session=db_session, run_id=run_id,
        )
        if existing is not None:
            err_lines = ["Cancel request already open for run."]
            err_lines.append("RUN_ID: {}".format(run_id))
            err_lines.append("OPEN_REQUEST_ID: {}".format(existing.request_id))
            err_lines.append("OPEN_STATUS: {}".format(existing.status.value))
            err_msg = os.linesep.join(err_lines)
            raise CancelDuplicateRequestError(err_msg) from None

        now = utc_now()
        request = repository.insert_request(
            db_session=db_session,
            run_id=run_id,
            project_id=project_id,
            client_id=client_id,
            requested_by=requested_by,
            reason=reason,
            requested_at=now,
        )

        try:
            self._transport.send_cancel(
                run_id=run_id,
                client_id=client_id,
                request_id=str(request.request_id),
                reason=reason,
            )
        except CancelTransportError as xcpt:
            request.status = CancelStatus.FAILED
            request.failure_reason = str(xcpt)
            db_session.flush()
            enqueue_event(
                db_session=db_session,
                event=EntityEvent(
                    topic=CancelEventTopics.REQUEST_FAILED,
                    payload={
                        "request_id": str(request.request_id),
                        "run_id": run_id,
                        "project_id": project_id,
                        "client_id": client_id,
                        "reason": str(xcpt),
                    },
                    source_event_id=new_uuid(),
                ),
            )
            db_session.commit()
            raise

        request.status = CancelStatus.TRANSMITTED
        request.transmitted_at = utc_now()
        db_session.flush()
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=CancelEventTopics.REQUEST_TRANSMITTED,
                payload={
                    "request_id": str(request.request_id),
                    "run_id": run_id,
                    "project_id": project_id,
                    "client_id": client_id,
                    "reason": reason,
                },
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
        return request


def request_cancel(
        *,
        dispatcher: CancelDispatcher,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        client_id: str,
        requested_by: Optional[str],
        reason: str
    ) -> CancelRequest:
    """
        Module-level convenience over :class:`CancelDispatcher`.
    """
    rtnval = dispatcher.send_cancel_rpc(
        db_session=db_session,
        run_id=run_id,
        project_id=project_id,
        client_id=client_id,
        requested_by=requested_by,
        reason=reason,
    )
    return rtnval


def handle_ack(
        *,
        db_session: DbSession,
        request_id: str,
        acked_at: Optional[datetime] = None
    ) -> CancelRequest:
    """
        Mark a transmitted request acked by the client and emit
        ``entity.run.cancel_ack``.
    """
    row = repository.get_request(db_session=db_session, request_id=request_id)
    if row is None:
        err_lines = ["Cancel request not found."]
        err_lines.append("REQUEST_ID: {}".format(request_id))
        err_msg = os.linesep.join(err_lines)
        from ccai.pychestrate.webservice.jobs.cancel.errors import CancelError
        raise CancelError(err_msg) from None
    if row.status != CancelStatus.TRANSMITTED:
        err_lines = ["Cancel request is not in TRANSMITTED state."]
        err_lines.append("REQUEST_ID: {}".format(request_id))
        err_lines.append("STATE: {}".format(row.status.value))
        err_msg = os.linesep.join(err_lines)
        from ccai.pychestrate.webservice.jobs.cancel.errors import CancelError
        raise CancelError(err_msg) from None

    when = acked_at
    if when is None:
        when = utc_now()
    row.status = CancelStatus.ACKED
    row.acked_at = when
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=CancelEventTopics.ACK_RECEIVED,
            payload={
                "request_id": str(row.request_id),
                "run_id": str(row.run_id),
                "project_id": str(row.project_id),
                "client_id": str(row.client_id),
                "acked_at": when.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return row
