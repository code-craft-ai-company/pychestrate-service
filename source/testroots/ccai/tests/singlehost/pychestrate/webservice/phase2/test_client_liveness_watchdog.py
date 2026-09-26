"""
.. module:: test_client_liveness_watchdog
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Client liveness follows heartbeat silence (RES-36).

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import timedelta

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.clients.enums import ClientStatus, LivenessState
from ccai.pychestrate.webservice.clients.liveness_watchdog import (
    DEFAULT_DEGRADED_AFTER_SECONDS,
    DEFAULT_LOST_AFTER_SECONDS,
    derive_liveness,
    pod_availability_warning,
    scan_client_liveness,
)
from ccai.pychestrate.webservice.clients.models import Client
from ccai.pychestrate.webservice.clients.registry.service import (
    get_client,
    record_heartbeat,
    register_client,
)
from ccai.pychestrate.webservice.jobs.reconcile.reconciler import RunReconciler

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _client(*, session, last_seen_ago=None, enrolled_ago: float = 0.0,
            status: ClientStatus = ClientStatus.ACTIVE) -> str:
    client = register_client(
        db_session=session, project_id=new_uuid(), pod_name="pod-{}".format(new_uuid()[:8]),
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )
    now = utc_now()
    client.enrolled_at = now - timedelta(seconds=enrolled_ago)
    client.last_seen = None if last_seen_ago is None else now - timedelta(seconds=last_seen_ago)
    client.status = status
    session.commit()
    rtnval = str(client.client_id)
    return rtnval


def _liveness(*, session, client_id: str) -> LivenessState:
    row = session.query(Client).filter(Client.client_id == client_id).one()
    rtnval = row.liveness_state
    return rtnval


def test_derive_liveness_thresholds():
    """
    **Feature: client liveness watchdog (RES-36)**
    **Property: silence below the degraded threshold is ALIVE, then
    DEGRADED, then LOST; a client that never heartbeated counts its
    silence from enrollment.**
    """
    now = utc_now()

    def _at(seconds_ago, *, seen=True):
        moment = now - timedelta(seconds=seconds_ago)
        rtnval = derive_liveness(
            last_seen=moment if seen else None, enrolled_at=moment, now=now,
        )
        return rtnval

    testbase.assert_equal(
        [_at(10), _at(DEFAULT_DEGRADED_AFTER_SECONDS), _at(DEFAULT_LOST_AFTER_SECONDS),
         _at(10, seen=False), _at(DEFAULT_LOST_AFTER_SECONDS + 1, seen=False)],
        [LivenessState.ALIVE, LivenessState.DEGRADED, LivenessState.LOST,
         LivenessState.ALIVE, LivenessState.LOST],
    )
    return


def test_scan_moves_silent_clients_and_leaves_revoked_ones():
    """
    **Feature: client liveness watchdog (RES-36)**
    **Property: the scan marks a quiet client DEGRADED and a long-silent
    or never-seen one LOST, leaves a fresh one ALIVE, and ignores a
    revoked client.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    fresh = _client(session=session, last_seen_ago=5)
    quiet = _client(session=session, last_seen_ago=DEFAULT_DEGRADED_AFTER_SECONDS + 10)
    silent = _client(session=session, last_seen_ago=3600)
    never = _client(session=session, enrolled_ago=3600)
    revoked = _client(session=session, last_seen_ago=3600, status=ClientStatus.REVOKED)

    changes = scan_client_liveness(db_session=session)
    states = [_liveness(session=session, client_id=cid) for cid in (fresh, quiet, silent, never, revoked)]
    testbase.assert_equal(
        (states, sorted(change.client_id for change in changes)),
        ([LivenessState.ALIVE, LivenessState.DEGRADED, LivenessState.LOST,
          LivenessState.LOST, LivenessState.ALIVE],
         sorted([quiet, silent, never])),
    )
    return


def test_a_heartbeat_heals_a_lost_client_and_the_scan_keeps_it_alive():
    """
    **Feature: client liveness watchdog (RES-36)**
    **Property: a LOST client that heartbeats again is ALIVE, and the
    next scan does not undo that.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    client_id = _client(session=session, last_seen_ago=3600)
    scan_client_liveness(db_session=session)
    lost = _liveness(session=session, client_id=client_id)

    record_heartbeat(db_session=session, client_id=client_id, received_at=utc_now(),
                     agent_version="1.0.0", transport_name=None)
    scan_client_liveness(db_session=session)
    testbase.assert_equal(
        (lost, get_client(db_session=session, client_id=client_id).liveness_state),
        (LivenessState.LOST, LivenessState.ALIVE),
    )
    return


def test_reconciler_scan_applies_the_liveness_watchdog():
    """
    **Feature: client liveness watchdog (RES-36)**
    **Property: the reconciler's periodic scan runs the watchdog, so a
    stopped pod stops showing ALIVE without anyone touching it.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    client_id = _client(session=session, last_seen_ago=3600)
    RunReconciler().scan_once(db_session=session)
    testbase.assert_equal(_liveness(session=session, client_id=client_id), LivenessState.LOST)
    return


def test_pod_availability_warning_names_offline_and_never_seen_pods():
    """
    **Feature: waiting for pod (E2E-16)**
    **Property: a trigger against a heartbeating pod carries no warning;
    one against a silent or never-seen pod says the run is queued and
    when the pod was last heard from.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    alive = _client(session=session, last_seen_ago=5)
    silent = _client(session=session, last_seen_ago=600)
    never = _client(session=session, enrolled_ago=30)

    warnings = [pod_availability_warning(db_session=session, client_id=cid)
                for cid in (alive, silent, never, None)]
    testbase.assert_equal(
        (warnings[0], "10 minute(s) ago" in warnings[1], "never checked in" in warnings[2], warnings[3]),
        (None, True, True, None),
    )
    return


def test_run_detail_describes_the_assigned_client():
    """
    **Feature: waiting for pod (E2E-16)**
    **Property: the single-run payload names the assigned client's pod,
    liveness and last contact, so the run page can say what it waits
    for.**
    """
    from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes

    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    client_id = _client(session=session, last_seen_ago=3600)
    scan_client_liveness(db_session=session)

    block = runs_routes._assigned_client_block(db_session=session, client_id=client_id)
    testbase.assert_equal(
        (block["client_id"], block["pod_name"].startswith("pod-"), block["liveness_state"],
         block["last_seen"] is not None,
         runs_routes._assigned_client_block(db_session=session, client_id=None)),
        (client_id, True, "LOST", True, None),
    )
    return
