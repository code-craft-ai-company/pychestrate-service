"""
.. module:: extensions.phase5_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register the in-tree Phase-5 (Layer-5) extensions
               and start the Layer-5 background tasks.

.. moduleauthor:: Code Craft AI LLC

Naming: ``phaseN`` files correspond to spec *layers* (``phase5`` ->
Layer 5 -- the job-execution plane), matching the pattern
established by :mod:`phase1_bootstrap` / :mod:`phase2_bootstrap` /
:mod:`phase3_bootstrap`. Operator callers run
:func:`bootstrap_phase1_runtime` + ``phase2`` + ``phase3`` +
:func:`bootstrap_phase5_runtime` in sequence at service start.

PR p19b adds the bus-subscriber and periodic-task wiring that the
existing Layer-5 services need to actually run:

* the run-state outbox publisher drainer (``drain_once`` on a
  short interval),
* the dispatch-receipt timer-wheel ticker (``fire_expired``),
* the result-ingest watcher (poll-based, scaffolded for PR C's
  webhook),
* the offline-tolerance evaluator (pod-state re-evaluation +
  deferred-cancel TTL sweep),
* the run reconciler scan tick (counts non-terminal runs; the
  policy-driven scan lands in a subsequent PR).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.artifacts import (
    register_builtin_extensions as artifacts_register,
)
from ccai.pychestrate.webservice.ingest.progress import (
    register_builtin_extensions as progress_register,
)
from ccai.pychestrate.webservice.ingest.result import (
    register_builtin_extensions as result_register,
)
from ccai.pychestrate.webservice.jobs.dispatch import (
    register_builtin_extensions as dispatch_register,
)
from ccai.pychestrate.webservice.jobs.dispatch.receipt.timer_wheel import (
    default_timer_wheel,
)
from ccai.pychestrate.webservice.jobs.offline.cancel_queue import (
    DeferredCancelQueue,
)
from ccai.pychestrate.webservice.jobs.offline.pod_state import (
    PodOfflineStateService,
)
from ccai.pychestrate.webservice.jobs.reconcile.reconciler import (
    RunReconciler,
)
from ccai.pychestrate.webservice.jobs.run.state.outbox_publisher import (
    drain_once as outbox_drain_once,
)
from ccai.pychestrate.webservice.jobs.scheduling import (
    PeriodicTask,
    PeriodicTaskScheduler,
    SchedulerHandle,
    default_scheduler,
)

# Side-effect imports so Layer-5 model tables attach to the metadata.
from ccai.pychestrate.webservice.artifacts import models as _artifacts_models  # noqa: F401
from ccai.pychestrate.webservice.ingest.progress import models as _progress_models  # noqa: F401
from ccai.pychestrate.webservice.ingest.result import models as _result_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.cancel import models as _cancel_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.dispatch.receipt import models as _dispatch_receipt_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.envelope import models as _envelope_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.offline import models as _offline_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.reconcile import models as _reconcile_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.results import models as _shared_results_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.run.state import models as _run_state_models  # noqa: F401


logger = logging.getLogger(__name__)


SessionFactory = Callable[[], DbSession]


# Default interval seconds for each Phase-5 periodic task. Operators
# can override by constructing a custom :class:`Phase5BootstrapConfig`
# (M2+); PR A wires the defaults only.
DEFAULT_OUTBOX_DRAIN_INTERVAL_SECONDS: float = 1.5
DEFAULT_TIMER_WHEEL_TICK_INTERVAL_SECONDS: float = 1.0
DEFAULT_RECONCILER_SCAN_INTERVAL_SECONDS: float = 30.0
DEFAULT_OFFLINE_EVALUATOR_INTERVAL_SECONDS: float = 15.0
DEFAULT_RESULT_WATCHER_INTERVAL_SECONDS: float = 10.0

DEFAULT_OUTBOX_BATCH_SIZE: int = 256


@dataclass(frozen=True)
class Phase5BootstrapConfig:
    """
        Operator-supplied Phase-5 bootstrap configuration.

        :param session_factory: Session factory used by the
                                periodic tasks (each tick opens a
                                fresh session, performs its unit
                                of work, and closes). When
                                ``None``, the background-task
                                wiring is skipped -- this matches
                                the M1 register-only callsite in
                                ``register_service_extensions``.
        :param scheduler: Optional custom scheduler instance.
                          Defaults to the process-wide
                          :func:`default_scheduler` so a single
                          start / stop handle covers every
                          Phase-5 task.
        :param outbox_drain_interval_seconds: Override for the
                                              run-state outbox
                                              drainer cadence.
        :param timer_wheel_tick_interval_seconds: Override for the
                                                  dispatch-receipt
                                                  timer-wheel
                                                  ``fire_expired``
                                                  cadence.
        :param reconciler_scan_interval_seconds: Override for the
                                                 run reconciler
                                                 periodic scan.
        :param offline_evaluator_interval_seconds: Override for
                                                   the offline
                                                   tolerance
                                                   evaluator.
        :param result_watcher_interval_seconds: Override for the
                                                result-ingest poll
                                                cadence.
    """
    session_factory: Optional[SessionFactory]
    scheduler: Optional[PeriodicTaskScheduler] = None
    outbox_drain_interval_seconds: float = DEFAULT_OUTBOX_DRAIN_INTERVAL_SECONDS
    timer_wheel_tick_interval_seconds: float = DEFAULT_TIMER_WHEEL_TICK_INTERVAL_SECONDS
    reconciler_scan_interval_seconds: float = DEFAULT_RECONCILER_SCAN_INTERVAL_SECONDS
    offline_evaluator_interval_seconds: float = DEFAULT_OFFLINE_EVALUATOR_INTERVAL_SECONDS
    result_watcher_interval_seconds: float = DEFAULT_RESULT_WATCHER_INTERVAL_SECONDS


def register_phase5_builtin_extensions() -> None:
    """
        Register every in-tree Layer-5 factory implementation.

        :returns: None.
    """
    dispatch_register()
    progress_register()
    result_register()
    artifacts_register()
    return


def _make_outbox_drain_task(
        *,
        session_factory: SessionFactory,
        interval_seconds: float,
        batch_size: int
    ) -> PeriodicTask:
    """
        Build the run-state outbox drainer tick. Each invocation
        opens a fresh session, calls
        :func:`outbox_drain_once`, and closes the session.

        :param session_factory: Operator session factory.
        :param interval_seconds: Tick cadence.
        :param batch_size: ``drain_once`` batch size.

        :returns: :class:`PeriodicTask`.
    """
    def _tick() -> None:
        session = session_factory()
        try:
            published = outbox_drain_once(
                db_session=session, batch_size=batch_size,
            )
            if published > 0:
                logger.debug(
                    "phase5.outbox_drainer.published count=%s",
                    published,
                )
        finally:
            session.close()
        return

    rtnval = PeriodicTask(
        name="phase5.outbox_drainer",
        interval_seconds=interval_seconds,
        run=_tick,
    )
    return rtnval


def _make_timer_wheel_tick_task(
        *,
        interval_seconds: float
    ) -> PeriodicTask:
    """
        Build the dispatch-receipt timer-wheel ``fire_expired``
        tick. The wheel is the process-wide default returned by
        :func:`default_timer_wheel`. PR A wires the tick to the
        wheel; the actual on-timeout bus publish lands when the
        dispatcher passes its publisher callback down to the wheel
        (M2 scope).

        :param interval_seconds: Tick cadence.

        :returns: :class:`PeriodicTask`.
    """
    def _tick() -> None:
        wheel = default_timer_wheel()
        fired = wheel.fire_expired()
        if len(fired) > 0:
            logger.debug(
                "phase5.timer_wheel.fired count=%s", len(fired)
            )
        return

    rtnval = PeriodicTask(
        name="phase5.timer_wheel_tick",
        interval_seconds=interval_seconds,
        run=_tick,
    )
    return rtnval


def _make_reconciler_scan_task(
        *,
        session_factory: SessionFactory,
        interval_seconds: float
    ) -> PeriodicTask:
    """
        Build the run reconciler periodic-scan tick. Calls
        :meth:`RunReconciler.scan_once` so the scheduler exercises
        the entry point even before the policy-driven scan logic
        lands.

        :param session_factory: Operator session factory.
        :param interval_seconds: Tick cadence.

        :returns: :class:`PeriodicTask`.
    """
    reconciler = RunReconciler()

    def _tick() -> None:
        session = session_factory()
        try:
            observed = reconciler.scan_once(db_session=session)
            logger.debug(
                "phase5.reconciler.scanned non_terminal=%s", observed,
            )
        finally:
            session.close()
        return

    rtnval = PeriodicTask(
        name="phase5.reconciler_scan",
        interval_seconds=interval_seconds,
        run=_tick,
    )
    return rtnval


def _make_offline_evaluator_task(
        *,
        session_factory: SessionFactory,
        interval_seconds: float
    ) -> PeriodicTask:
    """
        Build the offline-tolerance evaluator tick. Walks every
        tracked pod via :meth:`PodOfflineStateService.evaluate_all_pods`
        (so DEGRADED pods transition to OFFLINE without further
        events) and sweeps the deferred-cancel queue for expired
        rows.

        :param session_factory: Operator session factory.
        :param interval_seconds: Tick cadence.

        :returns: :class:`PeriodicTask`.
    """
    pod_state = PodOfflineStateService()
    cancel_queue = DeferredCancelQueue(pod_state=pod_state)

    def _tick() -> None:
        session = session_factory()
        try:
            evaluated = pod_state.evaluate_all_pods(db_session=session)
            expired = cancel_queue.mark_expired_overdue(db_session=session)
            if len(evaluated) > 0 or expired > 0:
                logger.debug(
                    "phase5.offline_evaluator.tick pods=%s expired=%s",
                    len(evaluated), expired,
                )
        finally:
            session.close()
        return

    rtnval = PeriodicTask(
        name="phase5.offline_evaluator",
        interval_seconds=interval_seconds,
        run=_tick,
    )
    return rtnval


def _make_result_watcher_task(
        *,
        session_factory: SessionFactory,
        interval_seconds: float
    ) -> PeriodicTask:
    """
        Build the result-ingest watcher tick. Per PR p19b scope
        the body is a poll-based stub -- the per-run scan trigger
        lands when the agent webhook + run completion event are
        wired in a subsequent PR. The tick exists so the daemon
        thread is alive and the smoke test can assert the watcher
        was registered.

        :param session_factory: Operator session factory.
        :param interval_seconds: Tick cadence.

        :returns: :class:`PeriodicTask`.
    """
    # ``_`` keeps the operator-supplied session factory close so a
    # subsequent PR can drop in the real per-run polling loop
    # without changing the wiring surface.
    _ = session_factory

    def _tick() -> None:
        logger.debug("phase5.result_watcher.tick noop_pending_pr_c")
        return

    rtnval = PeriodicTask(
        name="phase5.result_watcher",
        interval_seconds=interval_seconds,
        run=_tick,
    )
    return rtnval


def _register_periodic_tasks(
        *,
        scheduler: PeriodicTaskScheduler,
        config: Phase5BootstrapConfig
    ) -> None:
    """
        Register every Phase-5 periodic task on ``scheduler``.
        Pulled out so tests can assert the registration order
        without starting the scheduler.

        :param scheduler: Target scheduler.
        :param config: Caller-supplied :class:`Phase5BootstrapConfig`.

        :returns: None.
    """
    session_factory = config.session_factory
    if session_factory is None:
        err_msg_lines = ["Phase-5 periodic-task wiring requires a session factory."]
        err_msg_lines.append("HINT: pass session_factory through Phase5BootstrapConfig.")
        err_msg = "\n".join(err_msg_lines)
        raise ValueError(err_msg)

    existing_names = set(scheduler.task_names())

    outbox_task = _make_outbox_drain_task(
        session_factory=session_factory,
        interval_seconds=config.outbox_drain_interval_seconds,
        batch_size=DEFAULT_OUTBOX_BATCH_SIZE,
    )
    if outbox_task.name not in existing_names:
        scheduler.register(task=outbox_task)

    timer_task = _make_timer_wheel_tick_task(
        interval_seconds=config.timer_wheel_tick_interval_seconds,
    )
    if timer_task.name not in existing_names:
        scheduler.register(task=timer_task)

    reconciler_task = _make_reconciler_scan_task(
        session_factory=session_factory,
        interval_seconds=config.reconciler_scan_interval_seconds,
    )
    if reconciler_task.name not in existing_names:
        scheduler.register(task=reconciler_task)

    offline_task = _make_offline_evaluator_task(
        session_factory=session_factory,
        interval_seconds=config.offline_evaluator_interval_seconds,
    )
    if offline_task.name not in existing_names:
        scheduler.register(task=offline_task)

    result_task = _make_result_watcher_task(
        session_factory=session_factory,
        interval_seconds=config.result_watcher_interval_seconds,
    )
    if result_task.name not in existing_names:
        scheduler.register(task=result_task)
    return


def bootstrap_phase5_runtime(
        *, config: Phase5BootstrapConfig
    ) -> Optional[SchedulerHandle]:
    """
        Register Layer-5 extensions and start the Phase-5
        background tasks against the process-wide scheduler.

        When ``config.session_factory`` is ``None``, only the
        extensions are registered -- this matches the register-only
        callsite ``register_service_extensions`` uses on every
        webworks startup. The runtime bootstrap path passes a real
        session factory so the periodic tasks actually start.

        :param config: Caller-supplied :class:`Phase5BootstrapConfig`.

        :returns: :class:`SchedulerHandle` when the scheduler was
                  started, ``None`` when extensions-only registration
                  was performed.
    """
    register_phase5_builtin_extensions()

    if config.session_factory is None:
        return None

    scheduler = config.scheduler
    if scheduler is None:
        scheduler = default_scheduler()

    _register_periodic_tasks(scheduler=scheduler, config=config)
    handle = scheduler.start()
    logger.info(
        "phase5.bootstrap.scheduler_started tasks=%s",
        scheduler.task_names(),
    )
    rtnval = handle
    return rtnval
