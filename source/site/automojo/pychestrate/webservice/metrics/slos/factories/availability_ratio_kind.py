"""
.. module:: metrics.slos.factories.availability_ratio_kind
    :synopsis: AvailabilityRatioSloKind — reference availability SLO.

The availability-ratio kind reads two registered counter
metrics and returns ``good / total`` over the window.

Required config:

* ``good_metric_name`` — counter that increments on a good
  outcome (e.g. ``pychestrate_runs_succeeded_total``).
* ``total_metric_name`` — counter that increments on every
  outcome (e.g. ``pychestrate_runs_total``).

Optional config:

* ``label_filter`` — exact-match label dict applied to both
  metrics.

The window-based aggregation is implemented in pure Python
over ``metrics_timeseries_sample`` rows so the M1 stack stays
SQLite-friendly. M2's PromQL-shaped queries replace this with
the driver's range query.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json

from datetime import datetime, timedelta, timezone
from typing import Any, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import utc_now

from automojo.pychestrate.webservice.metrics.slos.factories.kind_protocol import (
    SLOComputationOutcome,
    SLODefinitionProtocol,
    SLOKindRecord,
)
from automojo.pychestrate.webservice.metrics.timeseries import repository as ts_repository


AVAILABILITY_RATIO_KIND_NAME: str = "availability_ratio"


class AvailabilityRatioSloKind(SLODefinitionProtocol):
    """
        Reference availability-ratio SLO.
    """

    factory_protocol_name: str = "slo_definition_kind"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def kind_name(cls) -> str:
        rtnval = AVAILABILITY_RATIO_KIND_NAME
        return rtnval

    @classmethod
    def record(cls) -> SLOKindRecord:
        rtnval = SLOKindRecord(
            kind=AVAILABILITY_RATIO_KIND_NAME,
            description=(
                "Achieved ratio = good_metric / total_metric "
                "over the SLO window."
            ),
            config_schema_keys=(
                "good_metric_name", "total_metric_name", "label_filter",
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
        for field in ("good_metric_name", "total_metric_name"):
            value = config.get(field, None)
            if value is None:
                issues.append("'{}' is required".format(field))
                continue
            if not isinstance(value, str) or len(value) == 0:
                issues.append(
                    "'{}' must be a non-empty string".format(field),
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
    def compute(
            cls,
            *,
            db_session: DbSession,
            project_id: str,
            config: Mapping[str, Any],
            window_seconds: int
        ) -> SLOComputationOutcome:
        good_metric = config["good_metric_name"]
        total_metric = config["total_metric_name"]
        label_filter = dict(config.get("label_filter", {}))
        signature = _label_signature(labels=label_filter)
        cutoff = utc_now() - timedelta(seconds=max(window_seconds, 0))

        good_rows = ts_repository.list_samples_for_signature(
            db_session=db_session,
            metric_name=good_metric,
            label_signature=signature,
            limit=10000,
        )
        total_rows = ts_repository.list_samples_for_signature(
            db_session=db_session,
            metric_name=total_metric,
            label_signature=signature,
            limit=10000,
        )

        # SQLite returns tz-naive datetimes; normalize to UTC-
        # aware before comparing so the test backend matches
        # Postgres semantics.
        def _aware(value: datetime) -> datetime:
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        good_in_window = sum(
            row.value for row in good_rows
            if _aware(row.observed_at) >= cutoff
        )
        total_in_window = sum(
            row.value for row in total_rows
            if _aware(row.observed_at) >= cutoff
        )

        if total_in_window <= 0:
            rtnval = SLOComputationOutcome(
                achieved_ratio=None,
                good_count=int(good_in_window),
                total_count=int(total_in_window),
                reason="no observations in window",
            )
            return rtnval

        ratio = float(good_in_window) / float(total_in_window)
        rtnval = SLOComputationOutcome(
            achieved_ratio=ratio,
            good_count=int(good_in_window),
            total_count=int(total_in_window),
            reason="good={} total={} ratio={:.6f}".format(
                int(good_in_window), int(total_in_window), ratio,
            ),
        )
        return rtnval


def _label_signature(*, labels: Mapping[str, str]) -> str:
    """
        Identical signature derivation as the timeseries
        facade.
    """
    canonical = json.dumps(
        {key: labels[key] for key in sorted(labels.keys())},
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    rtnval = digest[:32]
    return rtnval
