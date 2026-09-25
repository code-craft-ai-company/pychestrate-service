"""
.. module:: jobs.cancel.client_cancel
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Queue an operator cancel for the pod client holding a run.

.. moduleauthor:: Code Craft AI LLC

A cancel only stops work when it reaches the pod: the service has no
inbound channel to a pod, so the request is queued here and delivered on
the client's next heartbeat (:class:`HeartbeatCancelTransport`). Every
path that cancels a dispatched run -- ``POST /runs/{run_id}/cancel`` and
the RPA job cancel -- goes through :func:`queue_client_cancel`, so none
of them can mark a run cancelled while the pod keeps running it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Any, Optional, Tuple

from ccai.pychestrate.webservice.jobs.cancel.dispatcher import CancelDispatcher
from ccai.pychestrate.webservice.jobs.cancel.errors import CancelDuplicateRequestError
from ccai.pychestrate.webservice.jobs.cancel.heartbeattransport import HeartbeatCancelTransport
from ccai.pychestrate.webservice.jobs.dispatch import repository as dispatch_repo


_LOGGER = logging.getLogger(__name__)


#: Transport every client-bound cancel is queued on (the runs cancel
#: endpoint and the RPA job cancel). A module-level seam so tests can
#: substitute the in-memory transport; see :func:`set_active_cancel_dispatcher`.
ACTIVE_CANCEL_DISPATCHER: Optional[CancelDispatcher] = CancelDispatcher(
    transport=HeartbeatCancelTransport(),
)


def set_active_cancel_dispatcher(
        *, dispatcher: Optional[CancelDispatcher]
    ) -> None:
    """
        Publish the :class:`CancelDispatcher` the cancel endpoint
        queues client-bound cancels through.

        :param dispatcher: Dispatcher instance (or ``None`` to
                           disable client-bound cancel delivery).

        :returns: None.
    """
    global ACTIVE_CANCEL_DISPATCHER
    ACTIVE_CANCEL_DISPATCHER = dispatcher
    return


def resolve_cancel_target_client(
        *, db_session: Any, run_id: str
    ) -> Optional[Tuple[str, str, str]]:
    """
        Resolve which pod client is holding a run, so the cancel can
        be addressed to it.

        The run row carries no client id -- the dispatch attempt
        does. The most recent attempt is the one that put the job on
        a pod, so that is the attempt whose client must be told to
        stop.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.

        :returns: A ``(client_id, pod_id, project_id)`` tuple, or
                  ``None`` when the run was never dispatched.
    """
    attempts = dispatch_repo.list_attempts_for_run(
        db_session=db_session, run_id=run_id,
    )
    if len(attempts) == 0:
        rtnval = None
        return rtnval

    latest = attempts[-1]
    client_id = str(latest.client_id)
    pod_id = str(latest.pod_id)
    project_id = str(latest.project_id)

    rtnval = (client_id, pod_id, project_id)
    return rtnval


def queue_client_cancel(
        *, db_session: Any, run_id: str, reason: str, actor_id: str
    ) -> Optional[str]:
    """
        Open a cancel request against the pod holding the run so the
        client heartbeat can deliver it.

        Without this the cancel is purely bookkeeping: the run row
        reads ``cancel_requested`` while the pod keeps running the
        job to completion, because nothing ever reaches the pod.

        Every failure here is logged rather than raised. The state
        transition the caller already performed is the authoritative
        record of the operator's intent, and denying the operator a
        200 because delivery could not be queued would tell them the
        cancel did not happen when in fact it did.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID being cancelled.
        :param reason: Operator-supplied cancel reason.
        :param actor_id: Actor tag of the requesting principal.

        :returns: The cancel-request UUID, or ``None`` when nothing
                  was queued.
    """
    dispatcher = ACTIVE_CANCEL_DISPATCHER
    if dispatcher is None:
        _LOGGER.warning(
            "pychestrate.runs.cancel.no_dispatcher run_id=%s", run_id,
        )
        rtnval = None
        return rtnval

    target = resolve_cancel_target_client(
        db_session=db_session, run_id=run_id,
    )
    if target is None:
        _LOGGER.info(
            "pychestrate.runs.cancel.not_dispatched run_id=%s", run_id,
        )
        rtnval = None
        return rtnval

    client_id, pod_id, project_id = target

    try:
        request_row = dispatcher.send_cancel_rpc(
            db_session=db_session,
            run_id=run_id,
            project_id=project_id,
            client_id=client_id,
            requested_by=None,
            reason=reason,
        )
    except CancelDuplicateRequestError as xcpt:
        # A cancel is already queued for this run.  Re-cancelling is
        # idempotent by design, so this is a normal outcome of an
        # operator clicking twice, not an error.
        _LOGGER.info(
            "pychestrate.runs.cancel.already_queued run_id=%s detail=%s",
            run_id,
            xcpt,
        )
        rtnval = None
        return rtnval
    except Exception as xcpt:
        _LOGGER.warning(
            "pychestrate.runs.cancel.queue_error run_id=%s client_id=%s"
            " err=%s",
            run_id,
            client_id,
            xcpt,
        )
        rtnval = None
        return rtnval

    _LOGGER.info(
        "pychestrate.runs.cancel.queued run_id=%s client_id=%s pod_id=%s"
        " request_id=%s actor=%s",
        run_id,
        client_id,
        pod_id,
        str(request_row.request_id),
        actor_id,
    )

    rtnval = str(request_row.request_id)
    return rtnval


__all__ = [
    "ACTIVE_CANCEL_DISPATCHER",
    "queue_client_cancel",
    "resolve_cancel_target_client",
    "set_active_cancel_dispatcher",
]
