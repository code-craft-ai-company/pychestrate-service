"""
.. module:: test_p40g_resource_housekeeping_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the periodic resource housekeeping tasks and the
               leases that keep one server process per task.

.. moduleauthor:: Code Craft AI LLC

Audit findings RES-11, RES-12 and RES-39: reservations never turned into
allocations, overdue allocations never expired, and health checks ran
only when someone pressed a button, inside the web request. Four
periodic tasks now do that work on the process-wide scheduler, each
under a database lease so that several server processes never run the
same task at once.

**Feature: resources (RES-11/RES-12/RES-39 housekeeping)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import http.server
import threading
import uuid

from datetime import timedelta
from typing import Any, Dict, List, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.managers import health_monitor
from ccai.pychestrate.core.orm import (
    Allocation,
    HealthCheckConfig,
    IPAllocation,
    IPPool,
    PychestrateModelBase,
    Reservation,
    Resource,
)
from ccai.pychestrate.webservice import runtime_bootstrap
from ccai.pychestrate.webservice.housekeeping import (
    TASK_ACTIVATE_RESERVATIONS,
    TASK_EXPIRE_ALLOCATIONS,
    TASK_EXPIRE_IP_ALLOCATIONS,
    TASK_RUN_DUE_HEALTH_CHECKS,
    HousekeepingLease,
    acquire_lease,
    build_housekeeping_tasks,
    register_housekeeping_tasks,
    release_lease,
    renew_lease,
    run_with_lease,
)
from ccai.pychestrate.webservice.jobs.scheduling import PeriodicTaskScheduler
from ccai.pychestrate.webservice.metadata import (
    RUNTIME_ENVIRONMENTS,
    SITE_SHARED_GLOBALS,
)
from ccai.pychestrate.webservice.runtime_bootstrap import (
    RuntimeBootstrapConfig,
    bootstrap_runtime,
)


def _database() -> Any:
    """
        A session factory over one in-memory database holding the legacy
        resource tables and the lease table, shared by every session and
        thread.
    """
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False},
    )
    PychestrateModelBase.metadata.create_all(engine)
    HousekeepingLease.__table__.create(engine)
    rtnval = sessionmaker(bind=engine, expire_on_commit=False)
    return rtnval


def _task(name: str, session_factory: Any) -> Any:
    """
        The housekeeping task called ``name``, acting as one process.
    """
    tasks = build_housekeeping_tasks(session_factory=session_factory, holder_id="process-a")
    rtnval = [task for task in tasks if task.name == name][0]
    return rtnval


def _device(session: Any, name: str = "phone-7") -> Resource:
    resource = Resource(name=name, resource_type="device", metadata_json={}, sensitive_fields=[])
    session.add(resource)
    session.flush()
    rtnval = resource
    return rtnval


# ---------------------------------------------------------------------------
# Leases
# ---------------------------------------------------------------------------


def test_a_second_process_cannot_take_a_live_lease():
    """
    **Feature: resources (RES-11/RES-12/RES-39 housekeeping)**
    **Property: while one process holds a task's lease, another process
    asking for it is refused.**
    """
    factory = _database()
    now = utc_now()
    first = acquire_lease(factory(), task_name="t", holder_id="a", ttl_seconds=60, now=now)
    second = acquire_lease(factory(), task_name="t", holder_id="b", ttl_seconds=60, now=now + timedelta(seconds=59))
    testbase.assert_equal((first, second), (True, False))
    return


def test_a_lapsed_lease_passes_to_the_next_process():
    """
    **Feature: resources (RES-11/RES-12/RES-39 housekeeping)**
    **Property: a lease its holder never released (the process died)
    can be taken by another process once its time-to-live has passed.**
    """
    factory = _database()
    now = utc_now()
    acquire_lease(factory(), task_name="t", holder_id="a", ttl_seconds=60, now=now)
    taken = acquire_lease(factory(), task_name="t", holder_id="b", ttl_seconds=60, now=now + timedelta(seconds=61))
    testbase.assert_equal(taken, True)
    return


def test_a_holder_that_lost_its_lease_cannot_renew_it():
    """
    **Feature: resources (RES-11/RES-12/RES-39 housekeeping)**
    **Property: once a lapsed lease has passed to another process, the
    old holder's renewal fails, telling it to stop working.**
    """
    factory = _database()
    now = utc_now()
    acquire_lease(factory(), task_name="t", holder_id="a", ttl_seconds=60, now=now)
    acquire_lease(factory(), task_name="t", holder_id="b", ttl_seconds=60, now=now + timedelta(seconds=61))
    renewed = renew_lease(factory(), task_name="t", holder_id="a", ttl_seconds=60, now=now + timedelta(seconds=62))
    testbase.assert_equal(renewed, False)
    return


def test_a_released_lease_is_free_at_once_and_keeps_the_outcome():
    """
    **Feature: resources (RES-11/RES-12/RES-39 housekeeping)**
    **Property: releasing a lease lets another process take it straight
    away and records what the finished run did.**
    """
    factory = _database()
    now = utc_now()
    acquire_lease(factory(), task_name="t", holder_id="a", ttl_seconds=300, now=now)
    release_lease(factory(), task_name="t", holder_id="a", outcome="expired 2 allocation(s)", now=now)
    taken = acquire_lease(factory(), task_name="t", holder_id="b", ttl_seconds=300, now=now)
    lease = factory().get(HousekeepingLease, "t")
    testbase.assert_equal((taken, lease.holder_id, lease.last_outcome), (True, "b", "expired 2 allocation(s)"))
    return


def test_work_does_not_run_while_another_process_holds_the_lease():
    """
    **Feature: resources (RES-11/RES-12/RES-39 housekeeping)**
    **Property: when a second process ticks while the first is still
    running a task, the second skips the work instead of repeating it.**
    """
    factory = _database()
    ran: List[str] = []

    def second_process_work(db_session: Any, keep_lease: Any) -> str:
        ran.append("b")
        return "b"

    def first_process_work(db_session: Any, keep_lease: Any) -> str:
        ran.append("a")
        skipped = run_with_lease(
            session_factory=factory, task_name="t", ttl_seconds=60,
            work=second_process_work, holder_id="b",
        )
        ran.append("b returned {}".format(skipped))
        return "a"

    run_with_lease(session_factory=factory, task_name="t", ttl_seconds=60, work=first_process_work, holder_id="a")
    testbase.assert_equal(ran, ["a", "b returned None"])
    return


def test_a_failing_run_is_rolled_back_and_recorded_on_the_lease():
    """
    **Feature: resources (RES-11/RES-12/RES-39 housekeeping)**
    **Property: when a task's work raises, its uncommitted changes are
    rolled back, the failure is recorded on the lease, and the lease is
    released for the next tick.**
    """
    factory = _database()

    def failing_work(db_session: Any, keep_lease: Any) -> str:
        _device(db_session, name="half-written")
        raise RuntimeError("probe backend unavailable")

    outcome = run_with_lease(session_factory=factory, task_name="t", ttl_seconds=60, work=failing_work, holder_id="a")
    retaken = acquire_lease(factory(), task_name="t", holder_id="b", ttl_seconds=60)
    written = factory().query(Resource).filter(Resource.name == "half-written").count()
    testbase.assert_equal(
        (outcome, retaken, written),
        ("failed: probe backend unavailable", True, 0),
    )
    return


# ---------------------------------------------------------------------------
# The tasks
# ---------------------------------------------------------------------------


def test_the_reservation_task_turns_a_due_reservation_into_an_allocation():
    """
    **Feature: resources (RES-11 reservations activate)**
    **Property: a pending reservation whose start time has passed becomes
    an active allocation of its resource on the next run of the
    reservation task, without anyone opening a page.**
    """
    factory = _database()
    session = factory()
    device = _device(session)
    now = utc_now()
    reservation = Reservation(
        resource_id=device.id, user_id=uuid.uuid4(), mode="exclusive", status="pending",
        start_time=now - timedelta(minutes=1), end_time=now + timedelta(hours=2),
    )
    session.add(reservation)
    session.commit()
    reservation_id = reservation.id

    _task(TASK_ACTIVATE_RESERVATIONS, factory).run()

    check = factory()
    stored = check.get(Reservation, reservation_id)
    allocations = check.query(Allocation).filter(Allocation.resource_id == device.id).all()
    testbase.assert_equal(
        (stored.status, [allocation.status for allocation in allocations],
         stored.allocation_id == allocations[0].id if allocations else False),
        ("active", ["active"], True),
    )
    return


def test_the_allocation_task_expires_an_overdue_allocation():
    """
    **Feature: resources (RES-11 allocations expire)**
    **Property: an active allocation past its expected check-in is
    expired by the allocation task, freeing the resource.**
    """
    factory = _database()
    session = factory()
    device = _device(session)
    now = utc_now()
    allocation = Allocation(
        resource_id=device.id, user_id=uuid.uuid4(), mode="exclusive", status="active",
        checkout_time=now - timedelta(hours=3), expected_checkin=now - timedelta(minutes=5),
        metadata_snapshot={},
    )
    session.add(allocation)
    session.commit()
    allocation_id = allocation.id

    _task(TASK_EXPIRE_ALLOCATIONS, factory).run()

    testbase.assert_equal(factory().get(Allocation, allocation_id).status, "expired")
    return


def test_the_ip_allocation_task_expires_an_overdue_ip_allocation():
    """
    **Feature: resources (RES-11 allocations expire)**
    **Property: an active IP address allocation past its expected
    check-in is expired by the IP allocation task.**
    """
    factory = _database()
    session = factory()
    pool = IPPool(
        name="lab-net", cidr="10.0.4.0/24", ip_version="ipv4", network_address="10.0.4.0",
        subnet_mask="255.255.255.0", dns_servers=[], reserved_ips=[],
    )
    session.add(pool)
    session.flush()
    now = utc_now()
    allocation = IPAllocation(
        pool_id=pool.id, ip_address="10.0.4.21", user_id=uuid.uuid4(), status="active",
        checkout_time=now - timedelta(hours=3), expected_checkin=now - timedelta(minutes=5),
    )
    session.add(allocation)
    session.commit()
    allocation_id = allocation.id

    _task(TASK_EXPIRE_IP_ALLOCATIONS, factory).run()

    testbase.assert_equal(factory().get(IPAllocation, allocation_id).status, "expired")
    return


class _HealthyHandler(http.server.BaseHTTPRequestHandler):
    """
        A device health endpoint that always answers 200.
    """

    def do_GET(self) -> None:  # noqa: N802 — http.server naming
        self.send_response(200)
        self.end_headers()
        return

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — http.server signature
        return


def test_the_health_task_probes_a_due_check_off_the_web_request():
    """
    **Feature: resources (RES-12/RES-39 scheduled health checks)**
    **Property: the health task probes a device whose check is due and
    records the result, so a degraded device comes back online on the
    configured interval without anyone pressing "Run check".**
    """
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _HealthyHandler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    # The probe guard refuses loopback targets; this device stands in for
    # a lab device on the test host.
    guard = create_module_patch(health_monitor, "validate_probe_url")
    guard.activate().configure(return_value=None)
    try:
        factory = _database()
        session = factory()
        device = _device(session)
        device.health_status = "degraded"
        session.add(HealthCheckConfig(
            resource_id=device.id, enabled=True, interval_seconds=60, timeout_seconds=5,
            probe_url="http://127.0.0.1:{}/health".format(server.server_address[1]),
        ))
        session.commit()
        device_id = device.id

        _task(TASK_RUN_DUE_HEALTH_CHECKS, factory).run()

        check = factory()
        config = check.query(HealthCheckConfig).filter(HealthCheckConfig.resource_id == device_id).one()
        lease = check.get(HousekeepingLease, TASK_RUN_DUE_HEALTH_CHECKS)
        observed: Tuple[Any, ...] = (
            check.get(Resource, device_id).health_status,
            config.last_check_result,
            lease.last_outcome,
        )
    finally:
        guard.deactivate()
        server.shutdown()
        server.server_close()
    testbase.assert_equal(observed, ("online", True, "checked 1 resource(s), 1 status change(s)"))
    return


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_registration_adds_the_four_tasks_once():
    """
    **Feature: resources (RES-11/RES-12/RES-39 housekeeping)**
    **Property: registering the housekeeping tasks adds each of the four
    once; registering again (a second bootstrap in one process) adds
    nothing instead of raising on duplicate names.**
    """
    scheduler = PeriodicTaskScheduler()
    factory = _database()
    first = register_housekeeping_tasks(scheduler=scheduler, session_factory=factory)
    second = register_housekeeping_tasks(scheduler=scheduler, session_factory=factory)
    testbase.assert_equal(
        (first, second),
        ([TASK_ACTIVATE_RESERVATIONS, TASK_EXPIRE_ALLOCATIONS, TASK_EXPIRE_IP_ALLOCATIONS,
          TASK_RUN_DUE_HEALTH_CHECKS], []),
    )
    return


def test_runtime_bootstrap_registers_housekeeping_before_the_scheduler_starts():
    """
    **Feature: resources (RES-11/RES-12/RES-39 housekeeping)**
    **Property: the service's runtime bootstrap puts the housekeeping
    tasks on the process-wide scheduler before phase 5 starts it (tasks
    registered after the start would never run).**
    """
    scheduler = PeriodicTaskScheduler()
    seen_at_phase5: Dict[str, Any] = {}

    class _Kek:
        kek_id: str = "test-kek-1"

    def fake_phase5(*, config: Any) -> Any:
        seen_at_phase5["names"] = scheduler.task_names()
        return None

    fakes = {
        "bootstrap_phase1_runtime": lambda *, config: _Kek(),
        "bootstrap_phase2_runtime": lambda *, config: None,
        "bootstrap_phase3_runtime": lambda *, config: None,
        "bootstrap_phase5_runtime": fake_phase5,
        "bootstrap_phase6_runtime": lambda *, config: None,
        "default_scheduler": lambda: scheduler,
    }
    patches = []
    for name, fake in fakes.items():
        patch = create_module_patch(runtime_bootstrap, name)
        patch.activate().configure(side_effect=fake)
        patches.append(patch)
    engine_before = SITE_SHARED_GLOBALS.DATABASE_ENGINE
    factory_before = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    cookie_secret_before = SITE_SHARED_GLOBALS.UI_COOKIE_SECRET
    try:
        bootstrap_runtime(config=RuntimeBootstrapConfig(
            database_url="sqlite:///:memory:",
            runtime_environment=RUNTIME_ENVIRONMENTS.TESTING,
            kek_source="file",
            kek_id="test-kek-1",
            kek_file_path=None,
            kek_env_var=None,
            password_pepper_source=None,
            password_pepper_file_path=None,
            password_pepper_env_var=None,
            ui_cookie_secret_source=None,
            ui_cookie_secret_file_path=None,
            ui_cookie_secret_env_var=None,
            auto_create_schema=False,
            sql_echo=False,
        ))
    finally:
        for patch in patches:
            patch.deactivate()
        SITE_SHARED_GLOBALS.DATABASE_ENGINE = engine_before
        SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = factory_before
        SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = cookie_secret_before
    testbase.assert_equal(
        seen_at_phase5.get("names"),
        [TASK_ACTIVATE_RESERVATIONS, TASK_EXPIRE_ALLOCATIONS, TASK_EXPIRE_IP_ALLOCATIONS,
         TASK_RUN_DUE_HEALTH_CHECKS],
    )
    return
