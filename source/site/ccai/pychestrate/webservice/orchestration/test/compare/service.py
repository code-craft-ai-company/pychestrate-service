"""
.. module:: orchestration.test.compare.service
    :synopsis: Compare-runs facade — diff / build / fetch / view.

M1 ships:

* :func:`compute_test_diffs` — pure function over two outcome
  sets, no side effects.
* :func:`build_compare_report` — runs the diff against caller-
  supplied outcome sets, persists a CompareReport, emits BUILT;
  cache-hits return the existing report and emit CACHE_HIT.
* :func:`get_compare_report` — read by id.
* :func:`select_diff_viewer` — picks a registered
  :class:`ArtifactDiffViewerProtocol` for a path pair.

The lazy result-tree fetch + signed-download fallback land in
M2 once the object-store boundary plumbs through this module.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import os

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.orchestration.test.compare import (
    repository,
)
from ccai.pychestrate.webservice.orchestration.test.compare.errors import (
    CompareInputInvalidError,
    CompareReportNotFoundError,
    NoMatchingDiffViewerError,
)
from ccai.pychestrate.webservice.orchestration.test.compare.events import (
    CompareEventTopics,
)
from ccai.pychestrate.webservice.orchestration.test.compare.factories.diff_viewer_protocol import (
    ArtifactDiffViewerProtocol,
    DIFF_CONFIDENCE_NONE,
    DiffViewerRecord,
)
from ccai.pychestrate.webservice.orchestration.test.compare.models import (
    CompareReport,
    CompareStatus,
)


ARTIFACT_DIFF_VIEWER_PROTOCOL: str = "artifact_diff_viewer"
DEFAULT_REPORT_TTL_HOURS: int = 72


class TestDiffStatus(str, enum.Enum):
    """
        Per-test diff status — the categorical change between
        the base and candidate runs.
    """
    PASS_TO_FAIL = "pass_to_fail"
    FAIL_TO_PASS = "fail_to_pass"
    UNCHANGED = "unchanged"
    NEW = "new"
    REMOVED = "removed"
    BOTH_FAILED = "both_failed"
    OTHER = "other"


@dataclass(frozen=True)
class OutcomeForRun:
    """
        Per-test outcome surfaced to the diff engine. Caller
        builds these from the per-run outcome ledger.

        :param test_case_identity_sha256: SHA-256 hex of the raw
                                          test-case identity.
        :param outcome: Stringified outcome — ``"pass"`` /
                        ``"fail"`` / etc. The diff engine only
                        looks at ``"pass"`` vs anything else for
                        the M1 status set.
        :param duration_ms: Per-test duration; M1 keeps it on
                            the diff for the M2 reordering step.
    """
    test_case_identity_sha256: str
    outcome: str
    duration_ms: int = 0


@dataclass(frozen=True)
class TestDiff:
    """
        One per-test diff row.
    """
    test_case_identity_sha256: str
    base_outcome: Optional[str]
    candidate_outcome: Optional[str]
    status: TestDiffStatus
    base_duration_ms: int = 0
    candidate_duration_ms: int = 0


@dataclass(frozen=True)
class CompareReportView:
    """
        Caller-facing read-model for a compare report.
    """
    report_id: str
    project_id: str
    base_run_id: str
    candidate_run_id: str
    status: CompareStatus
    per_test_count: int
    per_test: Tuple[TestDiff, ...]
    warnings: Tuple[str, ...]
    note: str
    computed_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class DiffArtifactRef:
    """
        Caller-supplied artifact pair fed to
        :func:`select_diff_viewer`.
    """
    base_run_id: str
    candidate_run_id: str
    path: str
    name: str
    content_type: str = ""
    classifier_tag: str = ""


@dataclass(frozen=True)
class DiffViewerChoice:
    """
        Caller-facing read-model — the WebComponent the M2
        front-end mounts plus the cache TTL.
    """
    component_tag: str
    bundle_url: str
    confidence: int
    ttl_seconds: int
    artifact_path: str


def compute_test_diffs(
        *,
        base_outcomes: List[OutcomeForRun],
        candidate_outcomes: List[OutcomeForRun]
    ) -> List[TestDiff]:
    """
        Pure function — produce the per-test diff list.

        Identity matching is exact on
        ``test_case_identity_sha256``. The diff status follows
        the M1 status set:

        * ``PASS_TO_FAIL`` — base passed, candidate did not.
        * ``FAIL_TO_PASS`` — base failed, candidate passed.
        * ``UNCHANGED`` — both passed.
        * ``BOTH_FAILED`` — neither passed.
        * ``NEW`` — only candidate has this test.
        * ``REMOVED`` — only base has this test.
    """
    base_index: Dict[str, OutcomeForRun] = {}
    for sample in base_outcomes:
        base_index[sample.test_case_identity_sha256] = sample
    candidate_index: Dict[str, OutcomeForRun] = {}
    for sample in candidate_outcomes:
        candidate_index[sample.test_case_identity_sha256] = sample

    seen: List[str] = []
    rtnval: List[TestDiff] = []
    for identity, base in base_index.items():
        seen.append(identity)
        candidate = candidate_index.get(identity, None)
        rtnval.append(_diff_row(
            identity=identity, base=base, candidate=candidate,
        ))

    for identity, candidate in candidate_index.items():
        if identity in seen:
            continue
        rtnval.append(_diff_row(
            identity=identity, base=None, candidate=candidate,
        ))

    rtnval.sort(key=lambda r: r.test_case_identity_sha256)
    return rtnval


def build_compare_report(
        *,
        db_session: DbSession,
        project_id: str,
        base_run_id: str,
        candidate_run_id: str,
        base_outcomes: List[OutcomeForRun],
        candidate_outcomes: List[OutcomeForRun],
        ttl_hours: int = DEFAULT_REPORT_TTL_HOURS,
        warnings: Optional[List[str]] = None
    ) -> CompareReportView:
    """
        Persist a compare report. Idempotent on the
        ``(base_run_id, candidate_run_id)`` pair — a hit
        returns the existing report and emits CACHE_HIT.

        :raises: CompareInputInvalidError when ``base_run_id ==
                 candidate_run_id``.
    """
    if base_run_id == candidate_run_id:
        err_lines = ["base_run_id and candidate_run_id must differ."]
        err_lines.append("RUN_ID: {}".format(base_run_id))
        err_msg = os.linesep.join(err_lines)
        raise CompareInputInvalidError(err_msg) from None

    cached = repository.find_report_by_run_pair(
        db_session=db_session,
        base_run_id=base_run_id,
        candidate_run_id=candidate_run_id,
    )
    if cached is not None:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=CompareEventTopics.CACHE_HIT,
                payload={
                    "report_id": str(cached.report_id),
                    "base_run_id": base_run_id,
                    "candidate_run_id": candidate_run_id,
                },
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
        rtnval = _to_view(row=cached)
        return rtnval

    diffs = compute_test_diffs(
        base_outcomes=base_outcomes,
        candidate_outcomes=candidate_outcomes,
    )
    payload = [_diff_to_payload(diff=d) for d in diffs]

    now = utc_now()
    expires = now + timedelta(hours=ttl_hours)
    row = repository.insert_report(
        db_session=db_session,
        project_id=project_id,
        base_run_id=base_run_id,
        candidate_run_id=candidate_run_id,
        per_test_count=len(diffs),
        per_test_payload=payload,
        warnings=list(warnings or []),
        note="",
        computed_at=now,
        expires_at=expires,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=CompareEventTopics.BUILT,
            payload={
                "report_id": str(row.report_id),
                "project_id": project_id,
                "base_run_id": base_run_id,
                "candidate_run_id": candidate_run_id,
                "per_test_count": len(diffs),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def get_compare_report(
        *,
        db_session: DbSession,
        report_id: str
    ) -> CompareReportView:
    """
        Read a compare report by id.

        :raises: CompareReportNotFoundError on miss.
    """
    row = repository.find_report_by_id(
        db_session=db_session, report_id=report_id,
    )
    if row is None:
        err_lines = ["Compare report not found."]
        err_lines.append("REPORT_ID: {}".format(report_id))
        err_msg = os.linesep.join(err_lines)
        raise CompareReportNotFoundError(err_msg) from None
    rtnval = _to_view(row=row)
    return rtnval


def select_diff_viewer(*, artifact: DiffArtifactRef) -> DiffViewerChoice:
    """
        Walk the registered diff viewers and pick the highest-
        confidence match. The generic two-pane viewer is the
        fallback at PRECEDENCE=1000.

        :raises: NoMatchingDiffViewerError when no viewer
                 accepts the artifact (no fallback registered).
    """
    candidates = list_factory_implementations(
        factory_protocol_name=ARTIFACT_DIFF_VIEWER_PROTOCOL,
    )

    best_impl: Optional[Type[ArtifactDiffViewerProtocol]] = None
    best_confidence: int = DIFF_CONFIDENCE_NONE
    best_ttl: int = 0

    for impl in candidates:
        decision = impl.match(artifact=artifact)
        if decision.confidence > best_confidence:
            best_confidence = decision.confidence
            best_impl = impl
            best_ttl = decision.ttl_seconds

    if best_impl is None or best_confidence == DIFF_CONFIDENCE_NONE:
        err_lines = ["No registered diff viewer accepted the artifact."]
        err_lines.append("PATH: {}".format(artifact.path))
        err_lines.append("CONTENT_TYPE: {}".format(artifact.content_type))
        err_msg = os.linesep.join(err_lines)
        raise NoMatchingDiffViewerError(err_msg) from None

    record = best_impl.viewer_record()
    rtnval = DiffViewerChoice(
        component_tag=record.component_tag,
        bundle_url=record.bundle_url,
        confidence=best_confidence,
        ttl_seconds=best_ttl,
        artifact_path=artifact.path,
    )
    return rtnval


def _diff_row(
        *,
        identity: str,
        base: Optional[OutcomeForRun],
        candidate: Optional[OutcomeForRun]
    ) -> TestDiff:
    base_outcome = base.outcome if base is not None else None
    candidate_outcome = candidate.outcome if candidate is not None else None
    base_duration = base.duration_ms if base is not None else 0
    candidate_duration = candidate.duration_ms if candidate is not None else 0

    if base is None and candidate is not None:
        status = TestDiffStatus.NEW
    elif candidate is None and base is not None:
        status = TestDiffStatus.REMOVED
    else:
        base_pass = (base.outcome == "pass") if base is not None else False
        candidate_pass = (
            candidate.outcome == "pass" if candidate is not None else False
        )
        if base_pass is True and candidate_pass is True:
            status = TestDiffStatus.UNCHANGED
        elif base_pass is True and candidate_pass is False:
            status = TestDiffStatus.PASS_TO_FAIL
        elif base_pass is False and candidate_pass is True:
            status = TestDiffStatus.FAIL_TO_PASS
        elif base_pass is False and candidate_pass is False:
            if base.outcome == candidate.outcome:
                status = TestDiffStatus.BOTH_FAILED
            else:
                status = TestDiffStatus.OTHER
        else:
            status = TestDiffStatus.OTHER

    rtnval = TestDiff(
        test_case_identity_sha256=identity,
        base_outcome=base_outcome,
        candidate_outcome=candidate_outcome,
        status=status,
        base_duration_ms=base_duration,
        candidate_duration_ms=candidate_duration,
    )
    return rtnval


def _diff_to_payload(*, diff: TestDiff) -> Dict[str, Any]:
    rtnval = {
        "test_case_identity_sha256": diff.test_case_identity_sha256,
        "base_outcome": diff.base_outcome,
        "candidate_outcome": diff.candidate_outcome,
        "status": diff.status.value,
        "base_duration_ms": diff.base_duration_ms,
        "candidate_duration_ms": diff.candidate_duration_ms,
    }
    return rtnval


def _payload_to_diff(*, payload: Dict[str, Any]) -> TestDiff:
    rtnval = TestDiff(
        test_case_identity_sha256=payload.get("test_case_identity_sha256", ""),
        base_outcome=payload.get("base_outcome", None),
        candidate_outcome=payload.get("candidate_outcome", None),
        status=TestDiffStatus(payload.get("status", TestDiffStatus.OTHER.value)),
        base_duration_ms=payload.get("base_duration_ms", 0),
        candidate_duration_ms=payload.get("candidate_duration_ms", 0),
    )
    return rtnval


def _to_view(*, row: CompareReport) -> CompareReportView:
    diffs = tuple(
        _payload_to_diff(payload=item) for item in (row.per_test_payload or [])
    )
    rtnval = CompareReportView(
        report_id=str(row.report_id),
        project_id=str(row.project_id),
        base_run_id=str(row.base_run_id),
        candidate_run_id=str(row.candidate_run_id),
        status=row.status,
        per_test_count=row.per_test_count,
        per_test=diffs,
        warnings=tuple(row.warnings or []),
        note=row.note,
        computed_at=row.computed_at,
        expires_at=row.expires_at,
    )
    return rtnval
