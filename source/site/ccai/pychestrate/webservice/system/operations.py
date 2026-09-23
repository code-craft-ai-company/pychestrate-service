"""
.. module:: system.operations
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Liveness, readiness and Prometheus metrics for operators.

.. moduleauthor:: Code Craft AI LLC

The monitoring surface a load balancer, systemd watchdog, Kubernetes
or Prometheus needs, answered without a session:

* **Liveness** (``/livez``, ``/__health/live``) -- the process answers
  HTTP. No dependency is consulted, so a slow database never gets a
  healthy process restarted.
* **Readiness** (``/readyz``, ``/healthz``, ``/__health/ready``) -- the
  process can serve: the database answers ``SELECT 1`` within
  :data:`READINESS_TIMEOUT_SECONDS`. 503 with the names of the failing
  checks otherwise. Readiness does not depend on the setup wizard
  (the wizard must stay reachable while setup is pending).
* **Metrics** (``/metrics``) -- Prometheus text exposition: process
  start, HTTP request counts and latency (per worker process), the
  readiness checks, runs by state, backups by status and the time of
  the newest completed backup, and the service's internal event
  counters.

The probe bodies carry only a status word and check names -- no
versions, hostnames, error messages or data. ``/metrics`` exposes
operational aggregates, so its exposure is an explicit operator
choice:

* ``PYCHESTRATE_METRICS_TOKEN_FILE`` (or ``PYCHESTRATE_METRICS_TOKEN``)
  set -- scrapers must send ``Authorization: Bearer <token>``;
* ``PYCHESTRATE_METRICS_PUBLIC=true`` -- served without a token (a
  deployment that restricts the path at the proxy or network);
* neither -- ``/metrics`` answers 403 saying how to enable it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import concurrent.futures
import hmac
import logging
import os
import platform
import re
import time

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from ccai.pychestrate.webservice.system.prometheus import (
    CounterMetric,
    HistogramMetric,
    MetricFamily,
    render_exposition,
)


_LOGGER = logging.getLogger("pychestrate.system.operations")


LIVENESS_PATHS: Tuple[str, ...] = ("/livez", "/__health/live")
READINESS_PATHS: Tuple[str, ...] = ("/readyz", "/healthz", "/__health/ready")
METRICS_PATH: str = "/metrics"

#: Every operations endpoint, for the setup gate and the anonymous
#: access inventory.
OPERATIONS_PATHS: Tuple[str, ...] = LIVENESS_PATHS + READINESS_PATHS + (METRICS_PATH,)

ENV_METRICS_TOKEN: str = "PYCHESTRATE_METRICS_TOKEN"
ENV_METRICS_TOKEN_FILE: str = "PYCHESTRATE_METRICS_TOKEN_FILE"
ENV_METRICS_PUBLIC: str = "PYCHESTRATE_METRICS_PUBLIC"

#: A readiness check that has not answered by then counts as failing.
READINESS_TIMEOUT_SECONDS: float = 3.0

#: Unix time this worker process imported the module (~ started).
PROCESS_START_TIME: float = time.time()

HTTP_REQUESTS_TOTAL = CounterMetric(
    name="pychestrate_http_requests_total",
    help="HTTP responses served by this worker process, by method and status class.",
    label_names=("method", "status_class"),
)

HTTP_REQUEST_DURATION = HistogramMetric(
    name="pychestrate_http_request_duration_seconds",
    help="Time this worker process took to produce a response, by method.",
    label_names=("method",),
)

#: Bounded pool for readiness checks, so a hung database connection
#: cannot pile up request threads.
_READINESS_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="pychestrate-readiness",
)

_KNOWN_METHODS = frozenset(("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"))

_LABEL_NAME_UNSAFE = re.compile(r"[^a-zA-Z0-9_]")


@dataclass(frozen=True)
class ReadinessResult:
    """
        Outcome of the readiness checks.

        :ivar ready: Whether every check passed.
        :ivar checks: ``{check name: passed}``.
    """
    ready: bool
    checks: Dict[str, bool] = field(default_factory=dict)

    def failing(self) -> List[str]:
        """
            Names of the failing checks.

            :returns: Sorted list.
        """
        rtnval = sorted(name for name, passed in self.checks.items() if passed is False)
        return rtnval


@dataclass(frozen=True)
class MetricsAccess:
    """
        Whether a ``/metrics`` request may be served.

        :ivar allowed: Serve the metrics.
        :ivar status: HTTP status to answer when not allowed.
        :ivar detail: Explanation for a refusal.
    """
    allowed: bool
    status: int = 200
    detail: str = ""


# ---------------------------------------------------------------------------
# Request metrics (fed by the platform WSGI layer)
# ---------------------------------------------------------------------------


def record_http_request(*, method: str, status_code: int, duration_seconds: float) -> None:
    """
        Count one response and its latency.

        :param method: HTTP method (unknown methods count as ``OTHER``).
        :param status_code: Response status.
        :param duration_seconds: Time to produce the response.

        :returns: None.
    """
    upper = str(method).upper()
    method_label = upper if upper in _KNOWN_METHODS else "OTHER"
    status_class = "{}xx".format(int(status_code) // 100) if 100 <= int(status_code) <= 599 else "other"
    HTTP_REQUESTS_TOTAL.inc(labels=(method_label, status_class))
    HTTP_REQUEST_DURATION.observe(value=max(0.0, float(duration_seconds)), labels=(method_label,))
    return


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------


def _default_session_factory() -> Optional[Callable[[], Any]]:
    """
        The running service's database session factory.

        :returns: Session factory or ``None`` before bootstrap.
    """
    from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS

    rtnval = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    return rtnval


def _database_answers(session_factory: Callable[[], Any]) -> bool:
    """
        Run ``SELECT 1`` on a fresh session -- a server round trip on
        PostgreSQL. On SQLite ``SELECT 1`` never reads the database
        file, so ``PRAGMA schema_version`` (one header read) is run as
        well to catch an unreadable or corrupt file.

        :param session_factory: Session factory.

        :returns: True when the queries succeeded.
    """
    from sqlalchemy import text as sa_text

    session = session_factory()
    try:
        session.execute(sa_text("SELECT 1")).scalar()
        bind = session.get_bind()
        if getattr(getattr(bind, "dialect", None), "name", "") == "sqlite":
            session.execute(sa_text("PRAGMA schema_version")).scalar()
    finally:
        session.close()
    return True


def evaluate_readiness(
        *,
        session_factory: Optional[Callable[[], Any]] = None,
        timeout_seconds: float = READINESS_TIMEOUT_SECONDS
    ) -> ReadinessResult:
    """
        Run the readiness checks.

        :param session_factory: Database session factory; the service's
                                own when omitted.
        :param timeout_seconds: Budget per check.

        :returns: :class:`ReadinessResult`.
    """
    factory = session_factory if session_factory is not None else _default_session_factory()
    checks: Dict[str, bool] = {}
    if factory is None:
        checks["database"] = False
    else:
        future = _READINESS_POOL.submit(_database_answers, factory)
        try:
            checks["database"] = future.result(timeout=timeout_seconds) is True
        except concurrent.futures.TimeoutError:
            _LOGGER.warning("pychestrate.readiness.database_timeout seconds=%s", timeout_seconds)
            checks["database"] = False
        except Exception as xcpt:  # noqa: BLE001 -- a probe reports, never raises
            _LOGGER.warning("pychestrate.readiness.database_failed cause=%s", type(xcpt).__name__)
            checks["database"] = False
    rtnval = ReadinessResult(ready=all(checks.values()), checks=checks)
    return rtnval


# ---------------------------------------------------------------------------
# /metrics access
# ---------------------------------------------------------------------------


def _configured_metrics_token(*, environ: Mapping[str, str]) -> Optional[str]:
    """
        The bearer token scrapers must present, if one is configured
        (the file wins over the variable; read on each scrape so a
        rotated file takes effect without a restart).

        :param environ: Environment.

        :returns: Token or ``None``.
    """
    token_file = str(environ.get(ENV_METRICS_TOKEN_FILE, "") or "")
    if len(token_file) > 0:
        try:
            with open(token_file, "r", encoding="utf-8") as handle:
                token = handle.read().strip()
        except OSError as xcpt:
            _LOGGER.error("pychestrate.metrics.token_file_unreadable path=%s cause=%s", token_file, xcpt)
            # Fail closed: an unreadable token must not open the endpoint.
            return "\x00unreadable-token-file\x00"
        if len(token) > 0:
            return token
    token = str(environ.get(ENV_METRICS_TOKEN, "") or "").strip()
    rtnval = token if len(token) > 0 else None
    return rtnval


def metrics_access(*, authorization: Optional[str], environ: Optional[Mapping[str, str]] = None) -> MetricsAccess:
    """
        Decide whether a ``/metrics`` request may be served.

        :param authorization: The request's ``Authorization`` header.
        :param environ: Environment (defaults to :data:`os.environ`).

        :returns: :class:`MetricsAccess`.
    """
    env = environ if environ is not None else os.environ
    token = _configured_metrics_token(environ=env)
    if token is not None:
        presented = ""
        if authorization is not None and str(authorization).lower().startswith("bearer "):
            presented = str(authorization)[len("bearer "):].strip()
        if len(presented) > 0 and hmac.compare_digest(presented.encode("utf-8"), token.encode("utf-8")):
            return MetricsAccess(allowed=True)
        rtnval = MetricsAccess(
            allowed=False, status=401,
            detail="Metrics require the scrape token: send 'Authorization: Bearer <token>'.",
        )
        return rtnval

    public = str(env.get(ENV_METRICS_PUBLIC, "") or "").strip().lower() in ("1", "true", "yes")
    if public is True:
        return MetricsAccess(allowed=True)
    rtnval = MetricsAccess(
        allowed=False, status=403,
        detail=(
            "Metrics exposure is not enabled. Set {} (a file holding the bearer"
            " token scrapers send) or {}=true.".format(ENV_METRICS_TOKEN_FILE, ENV_METRICS_PUBLIC)
        ),
    )
    return rtnval


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------


def _process_families(*, runtime_environment: str) -> List[MetricFamily]:
    """
        Process identity and start time.

        :param runtime_environment: ``PYCHESTRATE_RUNTIME_ENVIRONMENT``.

        :returns: Families.
    """
    info = MetricFamily(name="pychestrate_info", kind="gauge",
                        help="Constant 1, labelled with the runtime environment and Python version.")
    info.add(value=1, labels=[("runtime_environment", runtime_environment),
                              ("python_version", platform.python_version())])
    start = MetricFamily(name="pychestrate_process_start_time_seconds", kind="gauge",
                         help="Unix time this worker process started.")
    start.add(value=PROCESS_START_TIME, labels=[("pid", str(os.getpid()))])
    rtnval = [info, start]
    return rtnval


def _readiness_families(*, readiness: ReadinessResult) -> List[MetricFamily]:
    """
        Readiness as gauges.

        :param readiness: Current readiness.

        :returns: Families.
    """
    up = MetricFamily(name="pychestrate_up", kind="gauge",
                      help="1 when every readiness check passes, else 0.")
    up.add(value=1 if readiness.ready else 0)
    checks = MetricFamily(name="pychestrate_readiness_check", kind="gauge",
                          help="Result of each readiness check (1 passing, 0 failing).")
    for name, passed in sorted(readiness.checks.items()):
        checks.add(value=1 if passed else 0, labels=[("check", name)])
    rtnval = [up, checks]
    return rtnval


def _enum_text(value: Any) -> str:
    """
        Text of an enum member (its value) or of a plain value.

        :param value: Column value.

        :returns: Text.
    """
    rtnval = str(getattr(value, "value", value))
    return rtnval


def _database_families(*, session_factory: Optional[Callable[[], Any]]) -> List[MetricFamily]:
    """
        Aggregates read from the database: runs by state, backups by
        status and the newest completed backup. A failing query drops
        its family and is reported by ``pychestrate_metrics_collector_up``.

        :param session_factory: Session factory.

        :returns: Families.
    """
    from sqlalchemy import func

    collector_up = MetricFamily(name="pychestrate_metrics_collector_up", kind="gauge",
                                help="1 when a metrics collector could read its data, else 0.")
    families: List[MetricFamily] = []
    if session_factory is None:
        collector_up.add(value=0, labels=[("collector", "database")])
        return [collector_up]

    session = session_factory()
    try:
        try:
            from ccai.pychestrate.webservice.jobs.run.state.models import Run

            runs = MetricFamily(name="pychestrate_runs", kind="gauge", help="Runs by state.")
            for state, count in session.query(Run.state, func.count()).group_by(Run.state).all():
                runs.add(value=count, labels=[("state", _enum_text(state))])
            families.append(runs)
            collector_up.add(value=1, labels=[("collector", "runs")])
        except Exception as xcpt:  # noqa: BLE001 -- keep the other families
            session.rollback()
            _LOGGER.warning("pychestrate.metrics.collector_failed collector=runs cause=%s", type(xcpt).__name__)
            collector_up.add(value=0, labels=[("collector", "runs")])

        try:
            from ccai.pychestrate.webservice.backup.models import BackupRecord, BackupStatus

            backups = MetricFamily(name="pychestrate_backups", kind="gauge", help="Backup runs by status.")
            for status, count in session.query(BackupRecord.status, func.count()).group_by(BackupRecord.status).all():
                backups.add(value=count, labels=[("status", _enum_text(status))])
            families.append(backups)
            newest = (
                session.query(func.max(BackupRecord.completed_at))
                .filter(BackupRecord.status == BackupStatus.COMPLETED)
                .scalar()
            )
            last = MetricFamily(
                name="pychestrate_backup_last_success_timestamp_seconds", kind="gauge",
                help="Unix time the newest completed backup finished (absent until one completes).",
            )
            if newest is not None:
                last.add(value=_timestamp(newest))
            families.append(last)
            collector_up.add(value=1, labels=[("collector", "backups")])
        except Exception as xcpt:  # noqa: BLE001 -- keep the other families
            session.rollback()
            _LOGGER.warning("pychestrate.metrics.collector_failed collector=backups cause=%s", type(xcpt).__name__)
            collector_up.add(value=0, labels=[("collector", "backups")])
    finally:
        session.close()
    rtnval = families + [collector_up]
    return rtnval


def _timestamp(value: Any) -> float:
    """
        Unix time of a (possibly naive, assumed UTC) datetime.

        :param value: Datetime.

        :returns: Seconds since the epoch.
    """
    from datetime import timezone

    if getattr(value, "tzinfo", None) is None:
        value = value.replace(tzinfo=timezone.utc)
    rtnval = value.timestamp()
    return rtnval


def _service_event_families() -> List[MetricFamily]:
    """
        The service's internal event counters (``hardening.metrics``).

        :returns: Families.
    """
    from ccai.pychestrate.webservice.hardening import metrics as hardening_metrics

    events = MetricFamily(name="pychestrate_service_events_total", kind="counter",
                          help="Internal service events counted by this worker process.")
    pid = ("pid", str(os.getpid()))
    for (name, labels), value in sorted(hardening_metrics.snapshot_counters().items()):
        label_pairs = [("event", name)]
        for label_name, label_value in labels:
            safe = _LABEL_NAME_UNSAFE.sub("_", str(label_name))
            if len(safe) == 0 or safe[0].isdigit() or safe in ("event", "pid"):
                safe = "label_" + safe
            label_pairs.append((safe, str(label_value)))
        events.add(value=value, labels=label_pairs + [pid])
    rtnval = [events]
    return rtnval


def collect_metric_families(
        *,
        runtime_environment: str,
        session_factory: Optional[Callable[[], Any]] = None,
        readiness: Optional[ReadinessResult] = None
    ) -> List[MetricFamily]:
    """
        Gather every family ``/metrics`` exposes.

        :param runtime_environment: ``PYCHESTRATE_RUNTIME_ENVIRONMENT``.
        :param session_factory: Database session factory; the service's
                                own when omitted.
        :param readiness: Readiness to report; evaluated when omitted.

        :returns: Families in exposition order.
    """
    factory = session_factory if session_factory is not None else _default_session_factory()
    current = readiness if readiness is not None else evaluate_readiness(session_factory=factory)
    pid = [("pid", str(os.getpid()))]
    families: List[MetricFamily] = []
    families.extend(_process_families(runtime_environment=runtime_environment))
    families.extend(_readiness_families(readiness=current))
    families.append(HTTP_REQUESTS_TOTAL.collect(extra_labels=pid))
    families.append(HTTP_REQUEST_DURATION.collect(extra_labels=pid))
    families.extend(_database_families(session_factory=factory))
    families.extend(_service_event_families())
    for extra in list(_EXTRA_COLLECTORS):
        try:
            families.extend(extra())
        except Exception as xcpt:  # noqa: BLE001 -- one bad collector must not blank /metrics
            _LOGGER.warning("pychestrate.metrics.collector_failed collector=%s cause=%s",
                            getattr(extra, "__name__", "extra"), type(xcpt).__name__)
    rtnval = families
    return rtnval


#: Collectors other features register (``() -> List[MetricFamily]``).
_EXTRA_COLLECTORS: List[Callable[[], List[MetricFamily]]] = []


def register_metrics_collector(*, collector: Callable[[], List[MetricFamily]]) -> None:
    """
        Add a collector whose families ``/metrics`` renders (e.g. the
        UI metrics beacon's aggregates). Registering the same callable
        twice is a no-op.

        :param collector: Zero-argument callable returning families.

        :returns: None.
    """
    if collector not in _EXTRA_COLLECTORS:
        _EXTRA_COLLECTORS.append(collector)
    return


def render_metrics(
        *,
        runtime_environment: str,
        session_factory: Optional[Callable[[], Any]] = None
    ) -> str:
    """
        The ``/metrics`` body.

        :param runtime_environment: ``PYCHESTRATE_RUNTIME_ENVIRONMENT``.
        :param session_factory: Database session factory override.

        :returns: Exposition text.
    """
    rtnval = render_exposition(families=collect_metric_families(
        runtime_environment=runtime_environment, session_factory=session_factory,
    ))
    return rtnval


__all__ = [
    "ENV_METRICS_PUBLIC",
    "ENV_METRICS_TOKEN",
    "ENV_METRICS_TOKEN_FILE",
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUEST_DURATION",
    "LIVENESS_PATHS",
    "METRICS_PATH",
    "MetricsAccess",
    "OPERATIONS_PATHS",
    "READINESS_PATHS",
    "ReadinessResult",
    "collect_metric_families",
    "evaluate_readiness",
    "metrics_access",
    "record_http_request",
    "register_metrics_collector",
    "render_metrics",
]
