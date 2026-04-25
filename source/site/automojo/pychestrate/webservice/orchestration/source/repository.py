"""
.. module:: orchestration.source.repository
    :synopsis: CRUD helpers for SCM rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.orchestration.source.models import (
    ScmLastSeenHead,
    ScmProjectConfig,
    ScmWebhookDelivery,
)


def upsert_project_config(
        *,
        db_session: DbSession,
        project_id: str,
        provider_name: str,
        repo_key: str,
        pipeline_file_path: str,
        use_polling: bool,
        polling_ref_glob: str,
        now: datetime
    ) -> ScmProjectConfig:
    row = (
        db_session.query(ScmProjectConfig)
        .filter(ScmProjectConfig.project_id == project_id)
        .first()
    )
    if row is None:
        row = ScmProjectConfig(
            project_id=project_id,
            provider_name=provider_name,
            repo_key=repo_key,
            pipeline_file_path=pipeline_file_path,
            use_polling=use_polling,
            polling_ref_glob=polling_ref_glob,
            last_poll_at=None,
            created_at=now,
            updated_at=now,
        )
        db_session.add(row)
    else:
        row.provider_name = provider_name
        row.repo_key = repo_key
        row.pipeline_file_path = pipeline_file_path
        row.use_polling = use_polling
        row.polling_ref_glob = polling_ref_glob
        row.updated_at = now
    db_session.flush()
    return row


def find_project_config(
        *,
        db_session: DbSession,
        project_id: str
    ) -> Optional[ScmProjectConfig]:
    rtnval = (
        db_session.query(ScmProjectConfig)
        .filter(ScmProjectConfig.project_id == project_id)
        .first()
    )
    return rtnval


def find_webhook_delivery(
        *,
        db_session: DbSession,
        project_id: str,
        delivery_id: str
    ) -> Optional[ScmWebhookDelivery]:
    rtnval = (
        db_session.query(ScmWebhookDelivery)
        .filter(ScmWebhookDelivery.project_id == project_id)
        .filter(ScmWebhookDelivery.delivery_id == delivery_id)
        .first()
    )
    return rtnval


def insert_webhook_delivery(
        *,
        db_session: DbSession,
        project_id: str,
        delivery_id: str,
        provider_name: str,
        event_kind: str,
        received_at: datetime
    ) -> ScmWebhookDelivery:
    row = ScmWebhookDelivery(
        project_id=project_id,
        delivery_id=delivery_id,
        provider_name=provider_name,
        event_kind=event_kind,
        received_at=received_at,
        first_seen_at=received_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def list_recent_deliveries(
        *,
        db_session: DbSession,
        project_id: str,
        limit: int
    ) -> List[ScmWebhookDelivery]:
    rows = (
        db_session.query(ScmWebhookDelivery)
        .filter(ScmWebhookDelivery.project_id == project_id)
        .order_by(ScmWebhookDelivery.received_at.desc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def upsert_last_seen_head(
        *,
        db_session: DbSession,
        project_id: str,
        ref: str,
        commit_sha: str,
        observed_at: datetime
    ) -> ScmLastSeenHead:
    row = (
        db_session.query(ScmLastSeenHead)
        .filter(ScmLastSeenHead.project_id == project_id)
        .filter(ScmLastSeenHead.ref == ref)
        .first()
    )
    if row is None:
        row = ScmLastSeenHead(
            project_id=project_id,
            ref=ref,
            commit_sha=commit_sha,
            observed_at=observed_at,
        )
        db_session.add(row)
    else:
        row.commit_sha = commit_sha
        row.observed_at = observed_at
    db_session.flush()
    return row


def find_last_seen_head(
        *,
        db_session: DbSession,
        project_id: str,
        ref: str
    ) -> Optional[ScmLastSeenHead]:
    rtnval = (
        db_session.query(ScmLastSeenHead)
        .filter(ScmLastSeenHead.project_id == project_id)
        .filter(ScmLastSeenHead.ref == ref)
        .first()
    )
    return rtnval
