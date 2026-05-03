"""
.. module:: metrics.timeseries.repository
    :synopsis: CRUD helpers for timeseries samples.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.metrics.timeseries.models import (
    TimeseriesSample,
)


def insert_sample(
        *,
        db_session: DbSession,
        metric_name: str,
        label_signature: str,
        labels: Dict[str, str],
        value: float,
        observed_at: datetime
    ) -> TimeseriesSample:
    row = TimeseriesSample(
        sample_id=new_uuid(),
        metric_name=metric_name,
        label_signature=label_signature,
        labels=dict(labels),
        value=value,
        observed_at=observed_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def list_samples_for_metric(
        *,
        db_session: DbSession,
        metric_name: str,
        limit: int
    ) -> List[TimeseriesSample]:
    rows = (
        db_session.query(TimeseriesSample)
        .filter(TimeseriesSample.metric_name == metric_name)
        .order_by(TimeseriesSample.observed_at.desc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def list_samples_for_signature(
        *,
        db_session: DbSession,
        metric_name: str,
        label_signature: str,
        limit: int
    ) -> List[TimeseriesSample]:
    rows = (
        db_session.query(TimeseriesSample)
        .filter(TimeseriesSample.metric_name == metric_name)
        .filter(TimeseriesSample.label_signature == label_signature)
        .order_by(TimeseriesSample.observed_at.desc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def latest_sample_for_signature(
        *,
        db_session: DbSession,
        metric_name: str,
        label_signature: str
    ) -> Optional[TimeseriesSample]:
    rtnval = (
        db_session.query(TimeseriesSample)
        .filter(TimeseriesSample.metric_name == metric_name)
        .filter(TimeseriesSample.label_signature == label_signature)
        .order_by(TimeseriesSample.observed_at.desc())
        .first()
    )
    return rtnval


def list_distinct_signatures(
        *,
        db_session: DbSession,
        metric_name: str
    ) -> List[str]:
    rows = (
        db_session.query(TimeseriesSample.label_signature)
        .filter(TimeseriesSample.metric_name == metric_name)
        .distinct()
        .all()
    )
    rtnval = [r[0] for r in rows]
    return rtnval
