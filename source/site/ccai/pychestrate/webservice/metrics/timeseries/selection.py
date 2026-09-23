"""
.. module:: metrics.timeseries.selection
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Select the samples an SLO / alert rule reads.

.. moduleauthor:: Code Craft AI LLC

An SLO or alert rule names a metric and an optional ``label_filter``.
The selection reads every series of that metric whose labels
*include* the filter (a subset match), within an optional time
window, and scopes project-owned metrics to the rule's project: when
the metric declares a ``project_id`` label and the filter does not
set one, the rule's project is added.

Before audit ORC-04 the kinds matched a single series by the exact
signature of the filter, so an empty filter (the natural choice)
matched no series of any in-tree metric -- every in-tree metric
carries labels -- and SLOs / alerts never saw a sample.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.metrics.timeseries import repository as ts_repository
from ccai.pychestrate.webservice.metrics.timeseries.facade import (
    MetricDefinition,
    MetricKind,
    get_metric_registry,
)
from ccai.pychestrate.webservice.metrics.timeseries.models import (
    TimeseriesSample,
)


#: Upper bound on the samples one selection reads.
MAX_SELECTED_SAMPLES: int = 10000

#: Label a metric declares when its series belong to a project.
PROJECT_LABEL: str = "project_id"


def find_definition(*, metric_name: str) -> Optional[MetricDefinition]:
    """
        The registered definition of ``metric_name``, or ``None``.

        :param metric_name: Metric name.

        :returns: The definition or ``None``.
    """
    rtnval = get_metric_registry().find(name=metric_name)
    return rtnval


def is_counter(*, metric_name: str) -> bool:
    """
        Whether ``metric_name`` is a registered counter. Counter
        samples are increments, so readers sum them over a window.

        :param metric_name: Metric name.

        :returns: True for a registered counter.
    """
    definition = find_definition(metric_name=metric_name)
    rtnval = definition is not None and definition.kind == MetricKind.COUNTER
    return rtnval


def effective_label_filter(
        *,
        metric_name: str,
        label_filter: Mapping[str, str],
        project_id: Optional[str]
    ) -> Dict[str, str]:
    """
        The filter a rule actually applies: its own ``label_filter``
        plus ``project_id`` when the metric carries a project label and
        the filter does not set it.

        :param metric_name: Metric name.
        :param label_filter: The rule's label filter.
        :param project_id: The rule's project, or ``None``.

        :returns: The effective filter.
    """
    rtnval: Dict[str, str] = {str(key): str(value) for key, value in dict(label_filter or {}).items()}
    definition = find_definition(metric_name=metric_name)
    if definition is None or project_id is None or len(str(project_id)) == 0:
        return rtnval
    if PROJECT_LABEL in definition.label_names and PROJECT_LABEL not in rtnval:
        rtnval[PROJECT_LABEL] = str(project_id)
    return rtnval


def select_samples(
        *,
        db_session: DbSession,
        metric_name: str,
        label_filter: Mapping[str, str],
        project_id: Optional[str],
        since: Optional[datetime] = None
    ) -> List[TimeseriesSample]:
    """
        The samples of ``metric_name`` whose labels include the
        effective filter, newest first, observed at or after
        ``since`` when given.

        :param db_session: Active SQLAlchemy session.
        :param metric_name: Metric name.
        :param label_filter: The rule's label filter (subset match).
        :param project_id: The rule's project (see
                           :func:`effective_label_filter`).
        :param since: Optional window start (UTC).

        :returns: Matching sample rows, newest first.
    """
    wanted = effective_label_filter(
        metric_name=metric_name,
        label_filter=label_filter,
        project_id=project_id,
    )
    rows = ts_repository.list_samples_for_metric(
        db_session=db_session,
        metric_name=metric_name,
        limit=MAX_SELECTED_SAMPLES,
    )
    cutoff = _aware(since) if since is not None else None
    matches: List[TimeseriesSample] = []
    for row in rows:
        if cutoff is not None and _aware(row.observed_at) < cutoff:
            # Rows are newest first: everything after is older.
            break
        if _labels_include(labels=row.labels, wanted=wanted) is True:
            matches.append(row)
    rtnval = matches
    return rtnval


def _labels_include(*, labels: Any, wanted: Mapping[str, str]) -> bool:
    """
        Whether ``labels`` carries every key / value of ``wanted``.

        :param labels: A sample's label mapping (JSON column).
        :param wanted: Required key / values.

        :returns: True when every wanted pair is present.
    """
    present = labels if isinstance(labels, dict) else {}
    for key, value in wanted.items():
        if str(present.get(key, "")) != value:
            return False
    return True


def _aware(value: datetime) -> datetime:
    """
        Treat a naive datetime (SQLite round-trip) as UTC.

        :param value: A datetime.

        :returns: A timezone-aware datetime.
    """
    if value.tzinfo is None:
        rtnval = value.replace(tzinfo=timezone.utc)
        return rtnval
    return value


__all__ = [
    "MAX_SELECTED_SAMPLES",
    "PROJECT_LABEL",
    "effective_label_filter",
    "find_definition",
    "is_counter",
    "select_samples",
]
