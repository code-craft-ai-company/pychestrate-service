"""
.. module:: workers.restapi.v1.metricsblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Prometheus exposition surface for the queue + workers.

.. moduleauthor:: Automation Mojo LLC

Exposes the same numbers as ``GET /api/v1/queue/stats`` but in
Prometheus text format (``text/plain; version=0.0.4``) so a
prometheus-compatible scraper can pull them on the standard
``/metrics`` path.

Why hand-rolled rather than depend on ``prometheus_client``:

* The format is small and stable — six-ish gauges plus
  comments. Pulling a dependency for a one-page emitter is
  worse than emitting it directly.
* Keeps the dependency graph thin (the service already
  ships without prometheus_client).
* Matching the OpenMetrics text format precisely is trivial;
  see :func:`render_metrics`.

Auth: the endpoint is intentionally public by default —
Prometheus scrapers don't carry cookies. Operators who need
admin-gating set ``PYCHESTRATE_METRICS_REQUIRE_ADMIN=true``;
the surface flips to ``system-admin`` at construction time.
The data exposed (counts of states) is not sensitive, but the
gate is available for those running pychestrate on a public
network.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, List, Optional, Tuple

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import Response
from automojo.webworks.security.accesspolicy import AccessPolicy

from automojo.pychestrate.webservice.workers import (
    jobservice,
    service as worker_service,
)


METRICS_PATH = "/metrics"
PROMETHEUS_CONTENT_TYPE = (
    "text/plain; version=0.0.4; charset=utf-8"
)


def _resolve_require_admin(
        *,
        environment: Optional[Dict[str, str]] = None,
    ) -> bool:
    """
        ``PYCHESTRATE_METRICS_REQUIRE_ADMIN`` controls whether
        the surface is public (default) or admin-gated. The
        truthy parser matches the rest of the service:
        ``1`` / ``true`` / ``yes`` / ``on`` (case-insensitive).
    """
    if environment is None:
        env = os.environ
    else:
        env = environment
    raw = env.get("PYCHESTRATE_METRICS_REQUIRE_ADMIN", None)
    if raw is None:
        return False
    if str(raw).strip().lower() in ("1", "true", "yes", "on"):
        return True
    return False


def _escape_label_value(*, value: str) -> str:
    """
        Prometheus label-value escaping: backslash, newline,
        and double-quote get escaped. Tag values like
        ``state="pending"`` are simple ASCII so this is mostly
        a no-op, but the rule is the rule.
    """
    rtnval = (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )
    return rtnval


def _render_gauge(
        *,
        name: str,
        help_text: str,
        samples: List[Tuple[Dict[str, str], float]],
    ) -> str:
    """
        Emit one gauge family in OpenMetrics text format.
    """
    lines: List[str] = []
    lines.append("# HELP {0} {1}".format(name, help_text))
    lines.append("# TYPE {0} gauge".format(name))
    if len(samples) == 0:
        rtnval = "\n".join(lines) + "\n"
        return rtnval
    for labels, value in samples:
        if len(labels) == 0:
            lines.append("{0} {1}".format(name, value))
        else:
            label_pairs = []
            for key, raw in labels.items():
                label_pairs.append('{0}="{1}"'.format(
                    key, _escape_label_value(value=raw),
                ))
            label_pairs.sort()
            lines.append("{0}{{{1}}} {2}".format(
                name, ",".join(label_pairs), value,
            ))
    rtnval = "\n".join(lines) + "\n"
    return rtnval


def render_metrics(
        *,
        db_session: Any,
    ) -> str:
    """
        Build the full Prometheus text payload from a single
        DB session. The numbers come straight from the same
        service-layer helpers backing ``/api/v1/queue/stats``,
        so dashboards and alerting agree by construction.
    """
    jobs_by_state = jobservice.count_jobs_by_state(
        db_session=db_session,
    )
    workers_by_status = worker_service.count_workers_by_status(
        db_session=db_session,
    )
    retry_scheduled = jobservice.count_retry_scheduled_jobs(
        db_session=db_session,
    )
    oldest_age = jobservice.oldest_pending_age_seconds(
        db_session=db_session,
    )

    in_flight = (
        jobs_by_state.get("claimed", 0)
        + jobs_by_state.get("running", 0)
    )

    parts: List[str] = []
    parts.append(_render_gauge(
        name="pychestrate_jobs_by_state",
        help_text="Number of worker jobs grouped by state.",
        samples=[
            ({"state": state}, count)
            for state, count in sorted(jobs_by_state.items())
        ],
    ))
    parts.append(_render_gauge(
        name="pychestrate_workers_by_status",
        help_text="Number of workers grouped by status.",
        samples=[
            ({"status": status}, count)
            for status, count in sorted(workers_by_status.items())
        ],
    ))
    parts.append(_render_gauge(
        name="pychestrate_jobs_in_flight",
        help_text=(
            "Number of jobs currently CLAIMED or RUNNING."
        ),
        samples=[({}, in_flight)],
    ))
    parts.append(_render_gauge(
        name="pychestrate_jobs_retry_scheduled",
        help_text=(
            "Number of PENDING jobs whose not_before is in the future "
            "(retries waiting on backoff)."
        ),
        samples=[({}, retry_scheduled)],
    ))
    if oldest_age is None:
        oldest_age_value = 0.0
    else:
        oldest_age_value = float(oldest_age)
    parts.append(_render_gauge(
        name="pychestrate_oldest_pending_age_seconds",
        help_text=(
            "Age of the oldest claimable PENDING job (0 when "
            "the queue is empty)."
        ),
        samples=[({}, oldest_age_value)],
    ))

    rtnval = "".join(parts)
    return rtnval


def _resolve_access_policy() -> AccessPolicy:
    if _resolve_require_admin() is True:
        return AccessPolicy(roles=("system-admin",))
    return AccessPolicy()  # public.


_METRICS_POLICY = _resolve_access_policy()


def _require_db_session(*, request: Request) -> Any:
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        err_lines = [
            "Request-scoped db_session not configured.",
            "DbSessionMiddleware must be installed in the pipeline.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise HTTPException(status_code=503, detail=err_msg)
    return db_session


class MetricsBlueprint(RestBlueprint):
    """
        Prometheus text-format exposition surface.
    """

    base_path = METRICS_PATH
    tags = ["metrics"]

    @RestBlueprint.attach_at(
        path=METRICS_PATH,
        methods=["GET"],
        doc=Doc(
            summary="Prometheus metrics",
            description=(
                "Returns queue + worker counts in Prometheus "
                "text format (``text/plain; version=0.0.4``). "
                "Public by default; flip to admin-gated via "
                "``PYCHESTRATE_METRICS_REQUIRE_ADMIN=true``."
            ),
        ),
        access_policy=_METRICS_POLICY,
    )
    def metrics_endpoint(request: Request) -> Response:
        db_session = _require_db_session(request=request)
        body_text = render_metrics(db_session=db_session)
        rtnval = Response(
            status_code=200,
            body=body_text.encode("utf-8"),
            headers={
                "Content-Type": PROMETHEUS_CONTENT_TYPE,
            },
        )
        return rtnval
