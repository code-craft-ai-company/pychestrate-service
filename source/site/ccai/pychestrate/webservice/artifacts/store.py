"""
.. module:: artifacts.store
    :synopsis: ArtifactStore — register / get / list facade.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.artifacts.cas_layout import build_cas_key
from ccai.pychestrate.webservice.artifacts.errors import (
    ArtifactBlobNotFoundError,
    ArtifactReferenceNotFoundError,
)
from ccai.pychestrate.webservice.artifacts.factories.promotion_strategy import (
    PromotionStrategyProtocol,
)
from ccai.pychestrate.webservice.artifacts.models import (
    ArtifactBlob,
    ArtifactRetentionPlan,
    RunArtifactReference,
)
from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event


PROMOTION_STRATEGY_PROTOCOL: str = "promotion_strategy"

ARTIFACT_INGESTED_TOPIC: str = "entity.artifact.registered"


@dataclass(frozen=True)
class ArtifactRegistration:
    """
        Inputs for one register call.

        :param run_id: Owning run UUID.
        :param project_id: Owning project UUID.
        :param label: Human-readable name unique per run.
        :param artifact_type: Type tag (``"build-image"``,
                              ``"sbom"``, ``"log"``, ...).
        :param cas_digest: SHA-256 hex digest of the blob.
        :param size_bytes: Length of the blob in bytes.
        :param content_type: Optional MIME type.
        :param backend_driver: Object-store driver tag.
    """
    run_id: str
    project_id: str
    label: str
    artifact_type: str
    cas_digest: str
    size_bytes: int
    content_type: Optional[str]
    backend_driver: str = "local-test"


class ArtifactStore:
    """
        Stateless facade over the artifact tables.
    """

    def register(
            self,
            *,
            db_session: DbSession,
            registration: ArtifactRegistration
        ) -> RunArtifactReference:
        """
            Idempotent register. If a blob with the same digest
            already exists its reference count is incremented;
            otherwise a fresh blob row is inserted. The
            ``(run_id, label)`` pair is unique — re-registering
            updates the existing reference instead of creating a
            duplicate.

            Emits ``entity.artifact.registered`` per call (per
            spec).
        """
        now = utc_now()
        blob = (
            db_session.query(ArtifactBlob)
            .filter(ArtifactBlob.cas_digest == registration.cas_digest)
            .first()
        )
        if blob is None:
            decision = self._evaluate_promotion(
                artifact_type=registration.artifact_type,
                size_bytes=registration.size_bytes,
                registered_at=now,
            )
            tier = "hot"
            if decision.target_tier == "cold" and decision.apply_at is None:
                tier = "cold"
            blob = ArtifactBlob(
                cas_digest=registration.cas_digest,
                cas_key=build_cas_key(digest=registration.cas_digest, tier=tier),
                backend_driver=registration.backend_driver,
                size_bytes=registration.size_bytes,
                content_type=registration.content_type,
                reference_count=0,
                tier=tier,
                first_seen_at=now,
                last_referenced_at=now,
            )
            db_session.add(blob)
            db_session.flush()
            if decision.target_tier == "cold" and decision.apply_at is not None:
                plan = ArtifactRetentionPlan(
                    plan_id=new_uuid(),
                    cas_digest=registration.cas_digest,
                    target_tier="cold",
                    apply_at=decision.apply_at,
                    reason=decision.reason,
                    created_at=now,
                )
                db_session.add(plan)
                db_session.flush()

        existing_ref = (
            db_session.query(RunArtifactReference)
            .filter(RunArtifactReference.run_id == registration.run_id)
            .filter(RunArtifactReference.label == registration.label)
            .first()
        )
        if existing_ref is None:
            ref = RunArtifactReference(
                reference_id=new_uuid(),
                run_id=registration.run_id,
                project_id=registration.project_id,
                label=registration.label,
                artifact_type=registration.artifact_type,
                cas_digest=registration.cas_digest,
                registered_at=now,
            )
            db_session.add(ref)
            blob.reference_count = int(blob.reference_count) + 1
            blob.last_referenced_at = now
        else:
            old_digest = existing_ref.cas_digest
            existing_ref.cas_digest = registration.cas_digest
            existing_ref.artifact_type = registration.artifact_type
            existing_ref.registered_at = now
            blob.last_referenced_at = now
            if old_digest != registration.cas_digest:
                blob.reference_count = int(blob.reference_count) + 1
                # Decrement the old blob's count (if it exists).
                old_blob = (
                    db_session.query(ArtifactBlob)
                    .filter(ArtifactBlob.cas_digest == old_digest)
                    .first()
                )
                if old_blob is not None and int(old_blob.reference_count) > 0:
                    old_blob.reference_count = int(old_blob.reference_count) - 1
            ref = existing_ref
        db_session.flush()

        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=ARTIFACT_INGESTED_TOPIC,
                payload={
                    "reference_id": str(ref.reference_id),
                    "run_id": registration.run_id,
                    "project_id": registration.project_id,
                    "label": registration.label,
                    "artifact_type": registration.artifact_type,
                    "cas_digest": registration.cas_digest,
                    "size_bytes": registration.size_bytes,
                    "tier": blob.tier,
                },
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
        return ref

    def get(
            self,
            *,
            db_session: DbSession,
            run_id: str,
            label: str
        ) -> RunArtifactReference:
        """
            Resolve a reference by ``(run_id, label)`` or raise.
        """
        ref = (
            db_session.query(RunArtifactReference)
            .filter(RunArtifactReference.run_id == run_id)
            .filter(RunArtifactReference.label == label)
            .first()
        )
        if ref is None:
            err_lines = ["Artifact reference not found."]
            err_lines.append("RUN_ID: {}".format(run_id))
            err_lines.append("LABEL: {}".format(label))
            err_msg = os.linesep.join(err_lines)
            raise ArtifactReferenceNotFoundError(err_msg) from None
        return ref

    def get_blob(
            self,
            *,
            db_session: DbSession,
            cas_digest: str
        ) -> ArtifactBlob:
        """
            Return the CAS blob row by digest, or raise.
        """
        blob = (
            db_session.query(ArtifactBlob)
            .filter(ArtifactBlob.cas_digest == cas_digest)
            .first()
        )
        if blob is None:
            err_lines = ["Artifact blob not found."]
            err_lines.append("CAS_DIGEST: {}".format(cas_digest))
            err_msg = os.linesep.join(err_lines)
            raise ArtifactBlobNotFoundError(err_msg) from None
        return blob

    def list_for_run(
            self,
            *,
            db_session: DbSession,
            run_id: str
        ) -> List[RunArtifactReference]:
        """
            Return every reference for ``run_id``.
        """
        rows = (
            db_session.query(RunArtifactReference)
            .filter(RunArtifactReference.run_id == run_id)
            .order_by(RunArtifactReference.label.asc())
            .all()
        )
        rtnval = list(rows)
        return rtnval

    def _evaluate_promotion(
            self,
            *,
            artifact_type: str,
            size_bytes: int,
            registered_at: datetime
        ):
        """
            Resolve the highest-precedence promotion strategy and
            invoke ``evaluate`` on it. Falls back to keeping the
            blob hot when no strategy is registered.
        """
        candidates = list_factory_implementations(
            factory_protocol_name=PROMOTION_STRATEGY_PROTOCOL,
        )
        if len(candidates) == 0:
            from datetime import timedelta
            from ccai.pychestrate.webservice.artifacts.factories.promotion_strategy import (
                PromotionDecision,
            )
            rtnval = PromotionDecision(
                target_tier="hot",
                apply_at=None,
                reason="no-strategy-registered",
            )
            return rtnval
        rtnval = candidates[0].evaluate(
            artifact_type=artifact_type,
            size_bytes=size_bytes,
            registered_at=registered_at,
        )
        return rtnval
