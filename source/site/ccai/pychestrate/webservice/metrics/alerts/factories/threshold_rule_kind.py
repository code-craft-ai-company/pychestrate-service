"""
.. module:: metrics.alerts.factories.threshold_rule_kind
    :synopsis: ThresholdAlertRuleKind — reference threshold rule.

Required config:

* ``metric_name`` — registered timeseries metric.
* ``threshold`` — numeric.
* ``op`` — one of ``"<"``, ``"<="``, ``">"``, ``">="``,
  ``"=="``, ``"!="``.

Optional config:

* ``label_filter`` — label dict. A series matches when its
  labels *include* every pair of the filter, so an empty filter
  reads every series of the metric. When the metric declares a
  ``project_id`` label and the filter does not set one, the
  rule's own project is added.
* ``window_seconds`` — positive integer. For a counter metric
  the observed value is the sum of the increments recorded in
  the last ``window_seconds`` (default
  :data:`DEFAULT_COUNTER_WINDOW_SECONDS`), so "failures > 0"
  fires while failures keep arriving and resolves once a window
  passes without one. For a gauge the observed value is the
  latest matching sample; with ``window_seconds`` set, samples
  older than the window are ignored.

Evaluation applies ``op`` between the observed value and
``threshold``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from datetime import timedelta
from typing import Any, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.metrics.alerts.factories.rule_kind_protocol import (
    AlertEvaluationOutcome,
    AlertRuleKindProtocol,
    AlertRuleKindRecord,
)
from ccai.pychestrate.core.defaults import utc_now

from ccai.pychestrate.webservice.metrics.timeseries.selection import (
    is_counter,
    select_samples,
)


THRESHOLD_RULE_KIND_NAME: str = "threshold"

#: Window a counter rule sums increments over when the config
#: sets no ``window_seconds``.
DEFAULT_COUNTER_WINDOW_SECONDS: int = 3600


class ComparisonOp(str, enum.Enum):
    """
        Comparison ops a threshold rule may use.
    """
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    EQ = "=="
    NE = "!="


SUPPORTED_OPS: Tuple[str, ...] = (
    ComparisonOp.LT.value,
    ComparisonOp.LE.value,
    ComparisonOp.GT.value,
    ComparisonOp.GE.value,
    ComparisonOp.EQ.value,
    ComparisonOp.NE.value,
)


class ThresholdAlertRuleKind(AlertRuleKindProtocol):
    """
        Reference threshold rule.
    """

    factory_protocol_name: str = "alert_rule_kind"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def kind_name(cls) -> str:
        rtnval = THRESHOLD_RULE_KIND_NAME
        return rtnval

    @classmethod
    def record(cls) -> AlertRuleKindRecord:
        rtnval = AlertRuleKindRecord(
            kind=THRESHOLD_RULE_KIND_NAME,
            description=(
                "Compare a metric against a numeric threshold using one "
                "of <, <=, >, >=, ==, !=. Counters are summed over "
                "window_seconds (default 3600); gauges use the latest "
                "sample."
            ),
            config_schema_keys=(
                "metric_name", "threshold", "op", "label_filter",
                "window_seconds",
            ),
        )
        return rtnval

    @classmethod
    def validate_config(
            cls,
            *,
            config: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        issues: List[str] = []
        metric_name = config.get("metric_name", None)
        if metric_name is None:
            issues.append("'metric_name' is required")
        elif not isinstance(metric_name, str) or len(metric_name) == 0:
            issues.append("'metric_name' must be a non-empty string")

        threshold = config.get("threshold", None)
        if threshold is None:
            issues.append("'threshold' is required")
        else:
            if isinstance(threshold, bool):
                issues.append("'threshold' must be numeric, not bool")
            elif not isinstance(threshold, (int, float)):
                issues.append("'threshold' must be a number")

        op = config.get("op", None)
        if op is None:
            issues.append("'op' is required")
        elif op not in SUPPORTED_OPS:
            issues.append(
                "'op' must be one of {}".format(", ".join(SUPPORTED_OPS)),
            )

        label_filter = config.get("label_filter", {})
        if not isinstance(label_filter, dict):
            issues.append("'label_filter' must be a mapping when present")
        else:
            for key, value in label_filter.items():
                if not isinstance(key, str) or len(key) == 0:
                    issues.append("'label_filter' keys must be non-empty strings")
                    break
                if not isinstance(value, str):
                    issues.append("'label_filter' values must be strings")
                    break

        window_seconds = config.get("window_seconds", None)
        if window_seconds is not None:
            if isinstance(window_seconds, bool) or not isinstance(window_seconds, int) or window_seconds <= 0:
                issues.append("'window_seconds' must be a positive integer when present")

        if len(issues) > 0:
            rtnval: Tuple[bool, Tuple[str, ...]] = (False, tuple(issues))
            return rtnval
        rtnval = (True, ())
        return rtnval

    @classmethod
    def evaluate(
            cls,
            *,
            db_session: DbSession,
            project_id: str,
            config: Mapping[str, Any]
        ) -> AlertEvaluationOutcome:
        metric_name = config["metric_name"]
        threshold = float(config["threshold"])
        op = config["op"]
        label_filter = dict(config.get("label_filter", {}))
        window_seconds = config.get("window_seconds", None)

        observed_value = _observed_value(
            db_session=db_session,
            project_id=project_id,
            metric_name=metric_name,
            label_filter=label_filter,
            window_seconds=window_seconds,
        )
        if observed_value is None:
            rtnval = AlertEvaluationOutcome(
                fires=False,
                observed_value=None,
                threshold_value=threshold,
                reason="no sample yet for metric",
            )
            return rtnval

        observed = float(observed_value)
        fires = _compare(observed=observed, op=op, threshold=threshold)
        if fires is True:
            reason = "{} {} {}".format(observed, op, threshold)
        else:
            reason = "{} not {} {}".format(observed, op, threshold)
        rtnval = AlertEvaluationOutcome(
            fires=fires,
            observed_value=observed,
            threshold_value=threshold,
            reason=reason,
        )
        return rtnval


def _compare(*, observed: float, op: str, threshold: float) -> bool:
    if op == "<":
        rtnval = observed < threshold
    elif op == "<=":
        rtnval = observed <= threshold
    elif op == ">":
        rtnval = observed > threshold
    elif op == ">=":
        rtnval = observed >= threshold
    elif op == "==":
        rtnval = observed == threshold
    elif op == "!=":
        rtnval = observed != threshold
    else:
        # validate_config rejects unknown ops; this branch is
        # defensive only.
        rtnval = False
    return rtnval


def _observed_value(
        *,
        db_session: DbSession,
        project_id: str,
        metric_name: str,
        label_filter: Mapping[str, str],
        window_seconds: Optional[int]
    ) -> Optional[float]:
    """
        The value a threshold rule compares: the windowed sum of a
        counter's increments, or a gauge's latest matching sample.

        :param db_session: Active SQLAlchemy session.
        :param project_id: The rule's project.
        :param metric_name: Metric the rule reads.
        :param label_filter: The rule's label filter (subset match).
        :param window_seconds: The rule's window, or ``None``.

        :returns: The observed value, or ``None`` when a gauge has no
                  matching sample (a counter with no increments in
                  its window observes ``0.0``).
    """
    if is_counter(metric_name=metric_name) is True:
        window = window_seconds if window_seconds is not None else DEFAULT_COUNTER_WINDOW_SECONDS
        rows = select_samples(
            db_session=db_session,
            metric_name=metric_name,
            label_filter=label_filter,
            project_id=project_id,
            since=utc_now() - timedelta(seconds=int(window)),
        )
        rtnval: Optional[float] = float(sum(row.value for row in rows))
        return rtnval

    since = None
    if window_seconds is not None:
        since = utc_now() - timedelta(seconds=int(window_seconds))
    rows = select_samples(
        db_session=db_session,
        metric_name=metric_name,
        label_filter=label_filter,
        project_id=project_id,
        since=since,
    )
    if len(rows) == 0:
        rtnval = None
        return rtnval
    rtnval = float(rows[0].value)
    return rtnval
