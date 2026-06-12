"""
.. module:: orchestration.test.triage.service
    :synopsis: Triage facade — open / reclassify / link / read.

M1 ships:

* :func:`open_case` — runs the top-precedence triage classifier
  against caller-supplied :class:`TriageSignals` and persists a
  :class:`TriageCase`. Idempotent on the
  ``(run_id, test_case_identity_sha256)`` pair.
* :func:`reclassify_case` — operator override; appends a ledger
  row, updates the row, emits RECLASSIFIED.
* :func:`link_ticket` — calls a registered
  :class:`BugTrackerDriverProtocol`, persists the resulting
  link, emits TICKET_LINKED.
* :func:`get_case` / :func:`list_cases_for_run` — read helpers.

The bus subscribers that drive
:func:`open_case` from ``entity.run.completed`` plus the M2
signature-cache lookup land in M2.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import os

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.orchestration.test.triage import (
    repository,
)
from ccai.pychestrate.webservice.orchestration.test.triage.errors import (
    TriageCaseNotFoundError,
    TriageClassifierNotFoundError,
    TriageStackSignatureInvalidError,
    TriageTrackerNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.test.triage.events import (
    TriageEventTopics,
)
from ccai.pychestrate.webservice.orchestration.test.triage.factories.classifier_protocol import (
    TriageClassifierProtocol,
)
from ccai.pychestrate.webservice.orchestration.test.triage.factories.tracker_protocol import (
    BugTrackerDriverProtocol,
)
from ccai.pychestrate.webservice.orchestration.test.triage.models import (
    TriageCase,
    TriageClass,
)


TRIAGE_CLASSIFIER_PROTOCOL: str = "triage_classifier"
BUG_TRACKER_DRIVER_PROTOCOL: str = "bug_tracker_driver"
STACK_TRACE_MAX_LEN: int = 65536


@dataclass(frozen=True)
class TriageSignals:
    """
        Inputs the classifier reads. Producer is the M2 ingest
        worker; M1 callers populate the bundle directly.

        :param flake_class: Stringified :class:`FlakeClass` value
                            (``""`` when the test has no
                            classification yet).
        :param has_known_signature: True when the
                                    ``stack_signature_sha256``
                                    matches the M2 known-issue
                                    cache. M1 callers set this
                                    based on a manual lookup.
        :param stack_signature_sha256: The signature this case
                                       hashes to.
        :param failure_summary: Short one-line summary surfaced
                                in the rationale.
    """
    flake_class: str
    has_known_signature: bool
    stack_signature_sha256: str
    failure_summary: str = ""


@dataclass(frozen=True)
class TriageCaseView:
    """
        Caller-facing read-model.
    """
    case_id: str
    project_id: str
    run_id: str
    catalog_entry_id: str
    test_case_identity_sha256: str
    stack_signature_sha256: str
    classification: TriageClass
    confidence: float
    rationale: str
    classifier_name: str
    tracker: Optional[str]
    ticket_key: Optional[str]
    ticket_url: Optional[str]
    created_at: datetime
    updated_at: datetime


def compute_stack_signature(*, stack_trace: str) -> str:
    """
        Hex-encoded SHA-256 of a normalized stack trace. The
        normalization strips trailing whitespace from each line
        and drops empty lines so re-runs of the same failure
        produce identical signatures.

        :raises: TriageStackSignatureInvalidError on empty /
                 oversized inputs.
    """
    if stack_trace is None or len(stack_trace) == 0:
        err_lines = ["Stack trace must be a non-empty string."]
        err_msg = os.linesep.join(err_lines)
        raise TriageStackSignatureInvalidError(err_msg) from None
    if len(stack_trace) > STACK_TRACE_MAX_LEN:
        err_lines = ["Stack trace exceeds the M1 cap."]
        err_lines.append("LENGTH: {}".format(len(stack_trace)))
        err_lines.append("MAX: {}".format(STACK_TRACE_MAX_LEN))
        err_msg = os.linesep.join(err_lines)
        raise TriageStackSignatureInvalidError(err_msg) from None

    normalized_lines: List[str] = []
    for line in stack_trace.split("\n"):
        stripped = line.rstrip()
        if len(stripped) == 0:
            continue
        normalized_lines.append(stripped)
    normalized = "\n".join(normalized_lines)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest


def open_case(
        *,
        db_session: DbSession,
        project_id: str,
        run_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        signals: TriageSignals
    ) -> TriageCaseView:
    """
        Run the top-precedence triage classifier and persist a
        :class:`TriageCase`. Idempotent on
        ``(run_id, test_case_identity_sha256)`` — a duplicate
        call returns the existing view without re-emitting.

        :raises: TriageClassifierNotFoundError when no
                 classifier is registered.
    """
    existing = repository.find_case_for_run_test(
        db_session=db_session,
        run_id=run_id,
        test_case_identity_sha256=test_case_identity_sha256,
    )
    if existing is not None:
        rtnval = _to_view(row=existing)
        return rtnval

    classifier_cls = _resolve_top_classifier()
    decision = classifier_cls.classify(signals=signals)
    now = utc_now()
    row = repository.insert_case(
        db_session=db_session,
        project_id=project_id,
        run_id=run_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        stack_signature_sha256=signals.stack_signature_sha256,
        classification=decision.classification,
        confidence=decision.confidence,
        rationale=decision.rationale,
        classifier_name=classifier_cls.classifier_name(),
        created_at=now,
    )
    repository.insert_ledger_entry(
        db_session=db_session,
        case_id=str(row.case_id),
        actor_id=None,
        from_class=None,
        to_class=decision.classification,
        rationale=decision.rationale,
        at_ts=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=TriageEventTopics.OPENED,
            payload={
                "case_id": str(row.case_id),
                "project_id": project_id,
                "run_id": run_id,
                "catalog_entry_id": catalog_entry_id,
                "test_case_identity_sha256": test_case_identity_sha256,
                "classification": decision.classification.value,
                "classifier_name": classifier_cls.classifier_name(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def reclassify_case(
        *,
        db_session: DbSession,
        case_id: str,
        new_class: TriageClass,
        actor_id: Optional[str],
        rationale: str
    ) -> TriageCaseView:
    """
        Operator override of an existing case. Appends a ledger
        row recording the from/to transition and emits
        RECLASSIFIED.

        :raises: TriageCaseNotFoundError on miss.
    """
    row = repository.find_case_by_id(db_session=db_session, case_id=case_id)
    if row is None:
        err_lines = ["Triage case not found."]
        err_lines.append("CASE_ID: {}".format(case_id))
        err_msg = os.linesep.join(err_lines)
        raise TriageCaseNotFoundError(err_msg) from None

    if row.classification == new_class:
        rtnval = _to_view(row=row)
        return rtnval

    now = utc_now()
    from_class = row.classification
    row.classification = new_class
    row.rationale = rationale
    row.classifier_name = "manual"
    row.updated_at = now
    db_session.flush()
    repository.insert_ledger_entry(
        db_session=db_session,
        case_id=str(row.case_id),
        actor_id=actor_id,
        from_class=from_class,
        to_class=new_class,
        rationale=rationale,
        at_ts=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=TriageEventTopics.RECLASSIFIED,
            payload={
                "case_id": str(row.case_id),
                "from_class": from_class.value,
                "to_class": new_class.value,
                "actor_id": actor_id,
                "rationale": rationale,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def link_ticket(
        *,
        db_session: DbSession,
        case_id: str,
        tracker_name: str,
        actor_id: Optional[str],
        summary: str = ""
    ) -> TriageCaseView:
    """
        Ask the named bug-tracker driver to open or link a
        ticket. Persists the link on the case and emits
        TICKET_LINKED.

        :raises: TriageCaseNotFoundError, TriageTrackerNotFoundError.
    """
    row = repository.find_case_by_id(db_session=db_session, case_id=case_id)
    if row is None:
        err_lines = ["Triage case not found."]
        err_lines.append("CASE_ID: {}".format(case_id))
        err_msg = os.linesep.join(err_lines)
        raise TriageCaseNotFoundError(err_msg) from None

    driver_cls = _resolve_tracker(tracker_name=tracker_name)
    link = driver_cls.open_or_link_ticket(
        project_id=str(row.project_id),
        case_id=str(row.case_id),
        classification=row.classification.value,
        stack_signature_sha256=row.stack_signature_sha256,
        summary=summary,
        actor_id=actor_id,
    )
    now = utc_now()
    row.tracker = link.tracker
    row.ticket_key = link.ticket_key
    row.ticket_url = link.ticket_url
    row.updated_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=TriageEventTopics.TICKET_LINKED,
            payload={
                "case_id": str(row.case_id),
                "tracker": link.tracker,
                "ticket_key": link.ticket_key,
                "ticket_url": link.ticket_url,
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def get_case(
        *,
        db_session: DbSession,
        case_id: str
    ) -> TriageCaseView:
    """
        Read a triage case by id.

        :raises: TriageCaseNotFoundError on miss.
    """
    row = repository.find_case_by_id(db_session=db_session, case_id=case_id)
    if row is None:
        err_lines = ["Triage case not found."]
        err_lines.append("CASE_ID: {}".format(case_id))
        err_msg = os.linesep.join(err_lines)
        raise TriageCaseNotFoundError(err_msg) from None
    rtnval = _to_view(row=row)
    return rtnval


def list_cases_for_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[TriageCaseView]:
    """
        Return triage cases for ``run_id`` ordered by created
        time ascending.
    """
    rows = repository.list_cases_for_run(
        db_session=db_session, run_id=run_id,
    )
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def _resolve_top_classifier() -> Type[TriageClassifierProtocol]:
    candidates = list_factory_implementations(
        factory_protocol_name=TRIAGE_CLASSIFIER_PROTOCOL,
    )
    if len(candidates) == 0:
        err_lines = ["No triage_classifier implementation is registered."]
        err_msg = os.linesep.join(err_lines)
        raise TriageClassifierNotFoundError(err_msg) from None
    rtnval = candidates[0]
    return rtnval


def _resolve_tracker(*, tracker_name: str) -> Type[BugTrackerDriverProtocol]:
    candidates = list_factory_implementations(
        factory_protocol_name=BUG_TRACKER_DRIVER_PROTOCOL,
    )
    for impl in candidates:
        if impl.tracker_name() == tracker_name:
            return impl
    err_lines = ["No registered bug_tracker_driver for name."]
    err_lines.append("TRACKER_NAME: {}".format(tracker_name))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(impl.tracker_name() for impl in candidates),
    ))
    err_msg = os.linesep.join(err_lines)
    raise TriageTrackerNotFoundError(err_msg) from None


def _to_view(*, row: TriageCase) -> TriageCaseView:
    rtnval = TriageCaseView(
        case_id=str(row.case_id),
        project_id=str(row.project_id),
        run_id=str(row.run_id),
        catalog_entry_id=str(row.catalog_entry_id),
        test_case_identity_sha256=row.test_case_identity_sha256,
        stack_signature_sha256=row.stack_signature_sha256,
        classification=row.classification,
        confidence=row.confidence,
        rationale=row.rationale,
        classifier_name=row.classifier_name,
        tracker=row.tracker,
        ticket_key=row.ticket_key,
        ticket_url=row.ticket_url,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return rtnval
