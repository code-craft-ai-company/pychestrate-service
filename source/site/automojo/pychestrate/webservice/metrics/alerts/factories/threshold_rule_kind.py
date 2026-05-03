"""
.. module:: metrics.alerts.factories.threshold_rule_kind
    :synopsis: ThresholdAlertRuleKind — reference threshold rule.

Required config:

* ``metric_name`` — registered timeseries metric.
* ``threshold`` — numeric.
* ``op`` — one of ``"<"``, ``"<="``, ``">"``, ``">="``,
  ``"=="``, ``"!="``.

Optional config:

* ``label_filter`` — exact-match label dict.

Evaluation reads the latest sample from the timeseries facade
matching the label filter and applies ``op`` against
``threshold``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import hashlib
import json
import os

from typing import Any, Dict, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.metrics.alerts.factories.rule_kind_protocol import (
    AlertEvaluationOutcome,
    AlertRuleKindProtocol,
    AlertRuleKindRecord,
)
from automojo.pychestrate.webservice.metrics.timeseries import repository as ts_repository


THRESHOLD_RULE_KIND_NAME: str = "threshold"


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
                "Compare the latest sample of a metric against a numeric "
                "threshold using one of <, <=, >, >=, ==, !=."
            ),
            config_schema_keys=(
                "metric_name", "threshold", "op", "label_filter",
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

        signature = _label_signature(labels=label_filter)
        latest = ts_repository.latest_sample_for_signature(
            db_session=db_session,
            metric_name=metric_name,
            label_signature=signature,
        )
        if latest is None:
            rtnval = AlertEvaluationOutcome(
                fires=False,
                observed_value=None,
                threshold_value=threshold,
                reason="no sample yet for metric",
            )
            return rtnval

        observed = float(latest.value)
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


def _label_signature(*, labels: Mapping[str, str]) -> str:
    """
        Identical signature derivation as the timeseries
        facade so threshold reads hit the same row the writes
        produced.
    """
    canonical = json.dumps(
        {key: labels[key] for key in sorted(labels.keys())},
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    rtnval = digest[:32]
    return rtnval
