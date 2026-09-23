"""
.. module:: extensions.phase7_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register the in-tree Layer-7 (metrics & dashboards)
               extensions and start the Layer-7 runtime.

.. moduleauthor:: Code Craft AI LLC

Layer 7 hosts the metrics + dashboards plane:

* ``0-timeseries-backend`` — :class:`NativePgTimeseriesDriver`
  (only in-tree driver at M1; ``timeseries_driver`` factory).
* ``7-metrics-ingest`` — :class:`MetricDefinitionExtension`
  packs registering the in-tree metric catalog.
* ``7-project-dashboards`` — the ``dashboard_tile_kind`` registry.
* ``7-alerts-budgets`` — the ``alert_rule_kind`` registry.
* ``7-slo-views`` — the ``slo_definition_kind`` registry.

:func:`register_phase7_builtin_extensions` seeds the registries (the
register-only path ``register_service_extensions`` runs on every
start). :func:`bootstrap_phase7_runtime`, given a session factory,
additionally:

* loads the registered metric definitions into the timeseries
  registry -- the metric catalog the Timeseries and dashboard views
  pick from;
* attaches the :class:`MetricIngestBusBridge`, the production metric
  writer that turns ``entity.*`` bus events into samples;
* starts the periodic alert evaluator, which evaluates every enabled
  alert rule so its live state (OK / FIRING) is current. Each run
  takes the ``metrics.alerts.evaluate`` housekeeping lease, so when
  several server processes run it only one evaluates at a time.

Before audit ORC-04 none of this was called: the registries were
empty, so creating an SLO, alert rule or dashboard tile failed with
"no registered kind", and the metric catalog was empty.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import threading

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.housekeeping.tasks import run_with_lease
from ccai.pychestrate.webservice.jobs.scheduling import (
    PeriodicTask,
    PeriodicTaskScheduler,
    SchedulerHandle,
)
from ccai.pychestrate.webservice.metrics.alerts import (
    register_builtin_extensions as alerts_register,
)
from ccai.pychestrate.webservice.metrics.alerts import (
    service as alerts_service,
)
from ccai.pychestrate.webservice.metrics.dashboards import (
    register_builtin_extensions as dashboards_register,
)
from ccai.pychestrate.webservice.metrics.ingest import (
    register_builtin_extensions as metrics_ingest_register,
)
from ccai.pychestrate.webservice.metrics.ingest.bus_bridge import (
    MetricIngestBusBridge,
)
from ccai.pychestrate.webservice.metrics.ingest.service import (
    reload_definitions_from_extensions,
)
from ccai.pychestrate.webservice.metrics.slos import (
    register_builtin_extensions as slos_register,
)
from ccai.pychestrate.webservice.metrics.timeseries import (
    register_builtin_extensions as timeseries_register,
)

# Side-effect imports so Layer-7 model tables attach to the metadata.
from ccai.pychestrate.webservice.metrics.alerts import models as _alerts_models  # noqa: F401
from ccai.pychestrate.webservice.metrics.dashboards import models as _dashboards_models  # noqa: F401
from ccai.pychestrate.webservice.metrics.slos import models as _slos_models  # noqa: F401
from ccai.pychestrate.webservice.metrics.timeseries import models as _timeseries_models  # noqa: F401


SessionFactory = Callable[[], DbSession]


_LOGGER = logging.getLogger("pychestrate.extensions.phase7")


#: Seconds between evaluations of every enabled alert rule.
DEFAULT_ALERT_EVALUATION_INTERVAL_SECONDS: float = 60.0

#: Name of the periodic alert-evaluator task and of its housekeeping
#: lease.
ALERT_EVALUATOR_TASK_NAME: str = "metrics.alerts.evaluate"

#: Lease time-to-live of one evaluator run; a run over a few hundred
#: rules takes seconds.
ALERT_EVALUATOR_LEASE_SECONDS: float = 300.0


@dataclass(frozen=True)
class Phase7BootstrapConfig:
    """
        Operator-supplied Phase-7 bootstrap configuration.

        :param session_factory: Session factory for the Layer-7
                                runtime (catalog load, metric
                                writer, alert evaluator). ``None``
                                runs the register-only path.
        :param scheduler: Optional scheduler for the alert evaluator.
                          Defaults to the process-wide Layer-7
                          scheduler (:func:`phase7_scheduler`); the
                          Layer-5 scheduler is already started by
                          then, and a started scheduler does not run
                          tasks registered afterwards.
        :param alert_evaluation_interval_seconds: Alert evaluator
                                                  cadence.
    """
    session_factory: Optional[SessionFactory]
    scheduler: Optional[PeriodicTaskScheduler] = None
    alert_evaluation_interval_seconds: float = DEFAULT_ALERT_EVALUATION_INTERVAL_SECONDS


@dataclass(frozen=True)
class Phase7BootstrapResult:
    """
        What :func:`bootstrap_phase7_runtime` wired.

        :param metric_names: The metric catalog loaded into the
                             timeseries registry.
        :param subscribed_topics: Topics the metric writer listens to.
        :param scheduler_handle: Handle of the scheduler running the
                                 alert evaluator, or ``None`` in the
                                 register-only path.
    """
    metric_names: Tuple[str, ...] = field(default_factory=tuple)
    subscribed_topics: Tuple[str, ...] = field(default_factory=tuple)
    scheduler_handle: Optional[SchedulerHandle] = None


_ACTIVE_BUS_BRIDGE: Optional[MetricIngestBusBridge] = None

_RUNTIME_LOCK = threading.RLock()

# The Layer-7 scheduler and the session factory its alert evaluator
# uses. Module-level so a repeated bootstrap (tests, a re-run of
# ``bootstrap_runtime``) re-uses one evaluator thread and points it at
# the newest session factory instead of starting another thread.
_PHASE7_SCHEDULER: Optional[PeriodicTaskScheduler] = None
_EVALUATOR_SESSION_FACTORY: Optional[SessionFactory] = None


def register_phase7_builtin_extensions() -> None:
    """
        Register every in-tree Layer-7 factory + resource
        extension. Must run before any service that emits
        metrics so the registry is non-empty. Idempotent.
    """
    timeseries_register()
    metrics_ingest_register()
    dashboards_register()
    alerts_register()
    slos_register()
    return


def load_metric_catalog(*, session_factory: SessionFactory) -> Tuple[str, ...]:
    """
        Load every registered metric definition into the timeseries
        registry -- the catalog ``GET /api/v1/metrics/catalog`` lists.

        :param session_factory: Session factory.

        :returns: The loaded metric names.
    """
    session = session_factory()
    try:
        views = reload_definitions_from_extensions(db_session=session)
    finally:
        session.close()
    rtnval = tuple(view.metric_name for view in views)
    return rtnval


def attach_metric_writer(*, session_factory: SessionFactory) -> MetricIngestBusBridge:
    """
        Attach the process-wide :class:`MetricIngestBusBridge`.
        Idempotent: a second call re-uses the attached bridge, points
        it at the newer session factory, and subscribes topics of
        extensions registered since.

        :param session_factory: Session factory for emissions.

        :returns: The active bridge.
    """
    global _ACTIVE_BUS_BRIDGE
    bridge = _ACTIVE_BUS_BRIDGE
    if bridge is None:
        bridge = MetricIngestBusBridge(session_factory=session_factory)
        _ACTIVE_BUS_BRIDGE = bridge
    else:
        bridge.use_session_factory(session_factory=session_factory)
    bridge.attach()
    rtnval = bridge
    return rtnval


def phase7_scheduler() -> PeriodicTaskScheduler:
    """
        The process-wide Layer-7 scheduler, created on first call.

        :returns: :class:`PeriodicTaskScheduler`.
    """
    global _PHASE7_SCHEDULER
    with _RUNTIME_LOCK:
        if _PHASE7_SCHEDULER is None:
            _PHASE7_SCHEDULER = PeriodicTaskScheduler()
        rtnval = _PHASE7_SCHEDULER
    return rtnval


def evaluate_alert_rules_once() -> int:
    """
        Evaluate every enabled alert rule with the evaluator's current
        session factory -- one tick of the alert evaluator. The run
        holds the :data:`ALERT_EVALUATOR_TASK_NAME` housekeeping lease;
        when another process holds it, this tick evaluates nothing.

        :returns: How many rules this tick evaluated (0 when no session
                  factory is configured, another process holds the
                  lease, or the rules cannot be read).
    """
    with _RUNTIME_LOCK:
        session_factory = _EVALUATOR_SESSION_FACTORY
    if session_factory is None:
        return 0

    evaluated: List[int] = [0]

    def _work(db_session: DbSession, keep_lease: Callable[[], bool]) -> str:
        results = alerts_service.evaluate_enabled_alert_rules(db_session=db_session)
        evaluated[0] = len(results)
        firing = len([result for result in results if result.state.value == "firing"])
        rtnval = "evaluated={} firing={}".format(len(results), firing)
        return rtnval

    try:
        run_with_lease(
            session_factory=session_factory,
            task_name=ALERT_EVALUATOR_TASK_NAME,
            ttl_seconds=ALERT_EVALUATOR_LEASE_SECONDS,
            work=_work,
        )
    except SQLAlchemyError as xcpt:
        # The lease or rule tables cannot be read (schema not created
        # yet, DB down): say so once per tick without a traceback and
        # retry on the next tick.
        _LOGGER.warning(
            "phase7.alert_evaluator.unreadable error=%s",
            xcpt.__class__.__name__,
        )
        return 0
    rtnval = evaluated[0]
    return rtnval


def make_alert_evaluator_task(
        *,
        session_factory: SessionFactory,
        interval_seconds: float
    ) -> PeriodicTask:
    """
        Build the periodic task that evaluates every enabled alert
        rule. Each tick opens a fresh session from the newest
        session factory handed to this function (or to
        :func:`bootstrap_phase7_runtime`).

        :param session_factory: Session factory.
        :param interval_seconds: Tick cadence.

        :returns: :class:`PeriodicTask`.
    """
    global _EVALUATOR_SESSION_FACTORY
    with _RUNTIME_LOCK:
        _EVALUATOR_SESSION_FACTORY = session_factory

    def _tick() -> None:
        evaluate_alert_rules_once()
        return

    rtnval = PeriodicTask(
        name=ALERT_EVALUATOR_TASK_NAME,
        interval_seconds=interval_seconds,
        run=_tick,
    )
    return rtnval


def bootstrap_phase7_runtime(*, config: Phase7BootstrapConfig) -> Phase7BootstrapResult:
    """
        Register the Layer-7 extensions and, with a session factory,
        load the metric catalog, attach the metric writer, and start
        the alert evaluator.

        :param config: Caller-supplied :class:`Phase7BootstrapConfig`.

        :returns: :class:`Phase7BootstrapResult`.
    """
    register_phase7_builtin_extensions()

    session_factory = config.session_factory
    if session_factory is None:
        rtnval = Phase7BootstrapResult()
        return rtnval

    metric_names = load_metric_catalog(session_factory=session_factory)
    bridge = attach_metric_writer(session_factory=session_factory)

    scheduler = config.scheduler
    if scheduler is None:
        scheduler = phase7_scheduler()
    task = make_alert_evaluator_task(
        session_factory=session_factory,
        interval_seconds=config.alert_evaluation_interval_seconds,
    )
    if ALERT_EVALUATOR_TASK_NAME not in scheduler.task_names():
        scheduler.register(task=task)
    handle = scheduler.start()

    _LOGGER.info(
        "phase7.bootstrap.ready metrics=%s writer_topics=%s alert_evaluator_interval=%s",
        len(metric_names),
        len(bridge.subscribed_topics),
        config.alert_evaluation_interval_seconds,
    )
    rtnval = Phase7BootstrapResult(
        metric_names=metric_names,
        subscribed_topics=bridge.subscribed_topics,
        scheduler_handle=handle,
    )
    return rtnval


def reset_phase7_runtime_for_testing() -> None:
    """
        Detach and forget the process-wide metric writer, stop and
        forget the Layer-7 scheduler. Test helper.

        :returns: None.
    """
    global _ACTIVE_BUS_BRIDGE, _PHASE7_SCHEDULER, _EVALUATOR_SESSION_FACTORY
    if _ACTIVE_BUS_BRIDGE is not None:
        _ACTIVE_BUS_BRIDGE.detach()
    _ACTIVE_BUS_BRIDGE = None
    with _RUNTIME_LOCK:
        scheduler = _PHASE7_SCHEDULER
        _PHASE7_SCHEDULER = None
        _EVALUATOR_SESSION_FACTORY = None
    if scheduler is not None:
        scheduler.stop()
    return
