"""
.. module:: orchestration.test.flake.service
    :synopsis: Flake-tracking facade — record / classify / quarantine.

M1 ships:

* :func:`record_outcome` — idempotent insert keyed on
  ``(run_id, test_case_identity_sha256)``; emits OUTCOME_RECORDED.
* :func:`classify_for_test_case` — resolve top-precedence
  classifier, build the history window, persist the result;
  emits CLASSIFIED on every change.
* :func:`set_quarantine` / :func:`clear_quarantine` — manual
  ledger ops that override the classifier output; emit
  QUARANTINED / QUARANTINE_CLEARED.
* :func:`list_history_for_test_case` /
  :func:`get_classification` — read helpers.

The async ingest worker that subscribes to ``entity.run.completed``
and the broken-alerted notifier land in M2 once the result-ingest
plumbing exposes the per-test outcome stream.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.orchestration.test.flake import (
    repository,
)
from automojo.pychestrate.webservice.orchestration.test.flake.errors import (
    FlakeClassificationNotFoundError,
    FlakeClassifierNotFoundError,
    OutcomeIdentityInvalidError,
)
from automojo.pychestrate.webservice.orchestration.test.flake.events import (
    FlakeEventTopics,
)
from automojo.pychestrate.webservice.orchestration.test.flake.factories.classifier_protocol import (
    FlakeClassifierProtocol,
)
from automojo.pychestrate.webservice.orchestration.test.flake.models import (
    FlakeClass,
    FlakeClassification,
    Outcome,
    QuarantineAction,
    TestOutcome,
)


FLAKE_CLASSIFIER_PROTOCOL: str = "flake_classifier"
DEFAULT_HISTORY_LIMIT: int = 200
RAW_IDENTITY_MAX_LEN: int = 4096


@dataclass(frozen=True)
class OutcomeSample:
    """
        One sample inside a :class:`TestHistoryWindow`.
    """
    run_id: str
    outcome: Outcome
    duration_ms: int
    started_at: datetime
    runtime_env_digest: str


@dataclass(frozen=True)
class TestHistoryWindow:
    """
        Frozen-dataclass view passed to a classifier. ``outcomes``
        is sorted newest-first.
    """
    project_id: str
    catalog_entry_id: str
    test_case_identity_sha256: str
    runtime_env_digest: Optional[str]
    outcomes: Tuple[OutcomeSample, ...] = ()
    window_max_size: int = 0
    window_min_samples: int = 0


@dataclass(frozen=True)
class FlakeClassificationView:
    """
        Caller-facing read-model for a classification row.
    """
    project_id: str
    catalog_entry_id: str
    test_case_identity_sha256: str
    runtime_env_digest: str
    classification: FlakeClass
    classifier_name: str
    classifier_version: str
    sample_count: int
    rationale_tag: str
    last_computed_at: datetime


def hash_test_case_identity(*, raw_identity: str) -> str:
    """
        Hex-encoded SHA-256 of the raw test-case identity string.
        Validates against an empty / oversized input.

        :raises: OutcomeIdentityInvalidError.
    """
    if raw_identity is None or len(raw_identity) == 0:
        err_lines = ["Raw test-case identity must be a non-empty string."]
        err_msg = os.linesep.join(err_lines)
        raise OutcomeIdentityInvalidError(err_msg) from None
    if len(raw_identity) > RAW_IDENTITY_MAX_LEN:
        err_lines = ["Raw test-case identity exceeds the M1 cap."]
        err_lines.append("LENGTH: {}".format(len(raw_identity)))
        err_lines.append("MAX: {}".format(RAW_IDENTITY_MAX_LEN))
        err_msg = os.linesep.join(err_lines)
        raise OutcomeIdentityInvalidError(err_msg) from None
    digest = hashlib.sha256(raw_identity.encode("utf-8")).hexdigest()
    return digest


def record_outcome(
        *,
        db_session: DbSession,
        project_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        run_id: str,
        runtime_env_digest: str,
        outcome: Outcome,
        duration_ms: int,
        started_at: Optional[datetime] = None
    ) -> TestOutcome:
    """
        Persist one per-test outcome. Idempotent on the
        ``(run_id, test_case_identity_sha256)`` pair — a
        duplicate insert returns the existing row without
        re-emitting the topic.
    """
    existing = repository.find_outcome_by_run_and_identity(
        db_session=db_session,
        run_id=run_id,
        test_case_identity_sha256=test_case_identity_sha256,
    )
    if existing is not None:
        return existing

    when = started_at if started_at is not None else utc_now()
    row = repository.insert_test_outcome(
        db_session=db_session,
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        run_id=run_id,
        runtime_env_digest=runtime_env_digest,
        outcome=outcome,
        duration_ms=duration_ms,
        started_at=when,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=FlakeEventTopics.OUTCOME_RECORDED,
            payload={
                "outcome_id": str(row.outcome_id),
                "project_id": project_id,
                "catalog_entry_id": catalog_entry_id,
                "run_id": run_id,
                "test_case_identity_sha256": test_case_identity_sha256,
                "outcome": outcome.value,
                "duration_ms": duration_ms,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return row


def list_history_for_test_case(
        *,
        db_session: DbSession,
        project_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        runtime_env_digest: Optional[str] = None,
        limit: int = DEFAULT_HISTORY_LIMIT
    ) -> TestHistoryWindow:
    """
        Build a :class:`TestHistoryWindow` from persisted
        outcomes, newest-first. The ``runtime_env_digest`` filter
        is optional — ``None`` returns rows across every env.
    """
    rows = repository.list_history_for_test_case(
        db_session=db_session,
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=runtime_env_digest,
        limit=limit,
    )
    samples = tuple(
        OutcomeSample(
            run_id=str(r.run_id),
            outcome=r.outcome,
            duration_ms=r.duration_ms,
            started_at=r.started_at,
            runtime_env_digest=r.runtime_env_digest,
        )
        for r in rows
    )
    rtnval = TestHistoryWindow(
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=runtime_env_digest,
        outcomes=samples,
        window_max_size=limit,
        window_min_samples=0,
    )
    return rtnval


def classify_for_test_case(
        *,
        db_session: DbSession,
        project_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        runtime_env_digest: Optional[str] = None
    ) -> FlakeClassificationView:
    """
        Resolve the top-precedence classifier, build a window
        from persisted outcomes, persist the result, and emit
        :data:`FlakeEventTopics.CLASSIFIED` on every change.

        Existing manual-quarantine ledger entries are honored —
        a row whose latest action is ``QUARANTINE`` stays
        ``quarantined`` regardless of the classifier's output.
    """
    classifier_cls = _resolve_top_classifier()
    window_cfg = classifier_cls.window_config()

    history_rows = repository.list_history_for_test_case(
        db_session=db_session,
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=runtime_env_digest,
        limit=window_cfg.max_window_size,
    )
    samples = tuple(
        OutcomeSample(
            run_id=str(r.run_id),
            outcome=r.outcome,
            duration_ms=r.duration_ms,
            started_at=r.started_at,
            runtime_env_digest=r.runtime_env_digest,
        )
        for r in history_rows
    )
    window = TestHistoryWindow(
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=runtime_env_digest,
        outcomes=samples,
        window_max_size=window_cfg.max_window_size,
        window_min_samples=window_cfg.min_samples,
    )
    decision = classifier_cls.classify(history=window)

    env_digest = runtime_env_digest if runtime_env_digest is not None else ""

    # Honor a sticky manual quarantine override.
    existing = repository.find_classification(
        db_session=db_session,
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=env_digest,
    )
    final_class = decision.classification
    final_rationale = decision.rationale_tag
    if existing is not None and existing.classification == FlakeClass.QUARANTINED:
        final_class = FlakeClass.QUARANTINED
        final_rationale = existing.rationale_tag

    now = utc_now()
    row = repository.upsert_classification(
        db_session=db_session,
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=env_digest,
        classification=final_class,
        classifier_name=classifier_cls.classifier_name(),
        classifier_version=classifier_cls.classifier_version(),
        sample_count=len(samples),
        rationale_tag=final_rationale,
        last_computed_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=FlakeEventTopics.CLASSIFIED,
            payload={
                "project_id": project_id,
                "catalog_entry_id": catalog_entry_id,
                "test_case_identity_sha256": test_case_identity_sha256,
                "runtime_env_digest": env_digest,
                "classification": final_class.value,
                "classifier_name": classifier_cls.classifier_name(),
                "classifier_version": classifier_cls.classifier_version(),
                "sample_count": len(samples),
                "rationale_tag": final_rationale,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_classification_view(row=row)
    return rtnval


def set_quarantine(
        *,
        db_session: DbSession,
        project_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        runtime_env_digest: Optional[str],
        actor_id: Optional[str],
        reason: str
    ) -> FlakeClassificationView:
    """
        Force a classification row to ``QUARANTINED`` and
        append a ``QUARANTINE`` ledger entry. Emits
        :data:`FlakeEventTopics.QUARANTINED`.
    """
    env_digest = runtime_env_digest if runtime_env_digest is not None else ""
    now = utc_now()

    row = repository.upsert_classification(
        db_session=db_session,
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=env_digest,
        classification=FlakeClass.QUARANTINED,
        classifier_name="manual",
        classifier_version="1",
        sample_count=0,
        rationale_tag="manual-quarantine",
        last_computed_at=now,
    )
    repository.insert_ledger_entry(
        db_session=db_session,
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=env_digest,
        action=QuarantineAction.QUARANTINE,
        actor_id=actor_id,
        reason=reason,
        at_ts=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=FlakeEventTopics.QUARANTINED,
            payload={
                "project_id": project_id,
                "catalog_entry_id": catalog_entry_id,
                "test_case_identity_sha256": test_case_identity_sha256,
                "runtime_env_digest": env_digest,
                "actor_id": actor_id,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_classification_view(row=row)
    return rtnval


def clear_quarantine(
        *,
        db_session: DbSession,
        project_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        runtime_env_digest: Optional[str],
        actor_id: Optional[str],
        reason: str
    ) -> FlakeClassificationView:
    """
        Clear a manual quarantine. Recomputes the classification
        immediately so the row reflects the current history.
        Emits :data:`FlakeEventTopics.QUARANTINE_CLEARED`
        followed by a fresh CLASSIFIED via
        :func:`classify_for_test_case`.
    """
    env_digest = runtime_env_digest if runtime_env_digest is not None else ""
    now = utc_now()
    repository.insert_ledger_entry(
        db_session=db_session,
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=env_digest,
        action=QuarantineAction.CLEAR,
        actor_id=actor_id,
        reason=reason,
        at_ts=now,
    )

    # Reset the classification to INSUFFICIENT_DATA before
    # re-running the classifier so the override is gone.
    repository.upsert_classification(
        db_session=db_session,
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=env_digest,
        classification=FlakeClass.INSUFFICIENT_DATA,
        classifier_name="manual",
        classifier_version="1",
        sample_count=0,
        rationale_tag="cleared-pre-recompute",
        last_computed_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=FlakeEventTopics.QUARANTINE_CLEARED,
            payload={
                "project_id": project_id,
                "catalog_entry_id": catalog_entry_id,
                "test_case_identity_sha256": test_case_identity_sha256,
                "runtime_env_digest": env_digest,
                "actor_id": actor_id,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    rtnval = classify_for_test_case(
        db_session=db_session,
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=runtime_env_digest,
    )
    return rtnval


def get_classification(
        *,
        db_session: DbSession,
        project_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        runtime_env_digest: Optional[str] = None
    ) -> FlakeClassificationView:
    """
        Read the persisted classification row.

        :raises: FlakeClassificationNotFoundError on miss.
    """
    env_digest = runtime_env_digest if runtime_env_digest is not None else ""
    row = repository.find_classification(
        db_session=db_session,
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=env_digest,
    )
    if row is None:
        err_lines = ["No flake classification for the test case."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("CATALOG_ENTRY_ID: {}".format(catalog_entry_id))
        err_lines.append(
            "IDENTITY_SHA256: {}".format(test_case_identity_sha256),
        )
        err_lines.append("RUNTIME_ENV_DIGEST: {}".format(env_digest))
        err_msg = os.linesep.join(err_lines)
        raise FlakeClassificationNotFoundError(err_msg) from None
    rtnval = _to_classification_view(row=row)
    return rtnval


def _resolve_top_classifier() -> Type[FlakeClassifierProtocol]:
    """
        Return the highest-priority registered classifier.

        :raises: FlakeClassifierNotFoundError when nothing is
                 registered.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=FLAKE_CLASSIFIER_PROTOCOL,
    )
    if len(candidates) == 0:
        err_lines = ["No flake_classifier implementation is registered."]
        err_msg = os.linesep.join(err_lines)
        raise FlakeClassifierNotFoundError(err_msg) from None
    rtnval = candidates[0]
    return rtnval


def _to_classification_view(
        *, row: FlakeClassification
    ) -> FlakeClassificationView:
    rtnval = FlakeClassificationView(
        project_id=str(row.project_id),
        catalog_entry_id=str(row.catalog_entry_id),
        test_case_identity_sha256=row.test_case_identity_sha256,
        runtime_env_digest=row.runtime_env_digest,
        classification=row.classification,
        classifier_name=row.classifier_name,
        classifier_version=row.classifier_version,
        sample_count=row.sample_count,
        rationale_tag=row.rationale_tag,
        last_computed_at=row.last_computed_at,
    )
    return rtnval
