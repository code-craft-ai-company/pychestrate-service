"""
.. module:: pods.definitions_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 3-pod-definitions service surface.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json
import os

from typing import Any, List, Mapping, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
    list_resource_extensions,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.pods.events import PodDefinitionEventTopics
from automojo.pychestrate.webservice.pods.exceptions import (
    MemberKindNotRegisteredError,
    PodDefinitionAlreadyExistsError,
    PodDefinitionNotFoundError,
    PodSpecValidationError,
)
from automojo.pychestrate.webservice.pods.extensions.member_kind import (
    PodMemberKindExtension,
)
from automojo.pychestrate.webservice.pods.factories.validator import (
    PodSpecValidatorProtocol,
    ValidationReport,
)
from automojo.pychestrate.webservice.pods.models import (
    PodDefinition,
    PodDefinitionVersion,
)


def create_pod_definition(
        *,
        db_session: DbSession,
        project_id: str,
        pod_name: str,
        spec: Mapping[str, Any],
        actor_user_id: Optional[str]
    ) -> PodDefinition:
    """
        Create a pod definition at version 1 after running every
        registered :class:`PodSpecValidatorProtocol`.

        :raises: PodSpecValidationError, PodDefinitionAlreadyExistsError,
                 MemberKindNotRegisteredError, SemanticError
    """
    if pod_name is None or len(pod_name.strip()) == 0:
        raise SemanticError("create_pod_definition requires a non-empty pod_name")

    report = _run_validators(spec=spec)
    _require_registered_member_kinds(spec=spec)

    if report.ok is False:
        event_payload = {
            "project_id": str(project_id),
            "pod_name": pod_name.strip(),
            "errors": list(report.errors),
            "actor_user_id": actor_user_id,
        }
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=PodDefinitionEventTopics.DEFINITION_VALIDATION_FAILED,
                payload=event_payload,
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()

        err_msg_lines = ["Pod spec failed validation."]
        for err in report.errors:
            err_msg_lines.append("- {}".format(err))
        err_msg = os.linesep.join(err_msg_lines)
        raise PodSpecValidationError(err_msg)

    pod_id = new_uuid()
    now = utc_now()
    definition = PodDefinition(
        pod_id=pod_id,
        project_id=project_id,
        pod_name=pod_name.strip(),
        current_version=1,
        created_at=now,
        created_by=actor_user_id,
        deleted_at=None,
    )

    spec_bytes = json.dumps(spec or {}, sort_keys=True).encode("utf-8")
    spec_hash = hashlib.sha256(spec_bytes).hexdigest()

    version = PodDefinitionVersion(
        pod_id=pod_id,
        version=1,
        spec_json=dict(spec or {}),
        spec_hash=spec_hash,
        validator_report={"ok": report.ok, "errors": list(report.errors), "warnings": list(report.warnings)},
        created_at=now,
        created_by=actor_user_id,
    )

    try:
        db_session.add(definition)
        db_session.add(version)
        db_session.flush()
    except IntegrityError:
        err_msg_lines = ["Cannot create pod definition — name already exists in project."]
        err_msg_lines.append("PROJECT: {}".format(project_id))
        err_msg_lines.append("POD_NAME: {}".format(pod_name.strip()))
        err_msg = os.linesep.join(err_msg_lines)
        raise PodDefinitionAlreadyExistsError(err_msg) from None

    event_payload = {
        "pod_id": str(pod_id),
        "project_id": str(project_id),
        "pod_name": definition.pod_name,
        "version": 1,
        "spec_hash": spec_hash,
        "actor_user_id": actor_user_id,
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PodDefinitionEventTopics.DEFINITION_CREATED,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )

    db_session.commit()

    rtnval = definition
    return rtnval


def read_pod_definition(
        *,
        db_session: DbSession,
        pod_id: str
    ) -> PodDefinition:
    """
        Return the :class:`PodDefinition` with the given id.
    """
    definition = (
        db_session.query(PodDefinition).filter(PodDefinition.pod_id == pod_id).first()
    )
    if definition is None:
        err_msg_lines = ["Pod definition not found."]
        err_msg_lines.append("POD_ID: {}".format(pod_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise PodDefinitionNotFoundError(err_msg) from None
    rtnval = definition
    return rtnval


def read_pod_definition_version(
        *,
        db_session: DbSession,
        pod_id: str,
        version: int
    ) -> PodDefinitionVersion:
    """
        Return a specific :class:`PodDefinitionVersion` row.
    """
    row = (
        db_session.query(PodDefinitionVersion)
        .filter(PodDefinitionVersion.pod_id == pod_id)
        .filter(PodDefinitionVersion.version == version)
        .first()
    )
    if row is None:
        err_msg_lines = ["Pod definition version not found."]
        err_msg_lines.append("POD_ID: {}".format(pod_id))
        err_msg_lines.append("VERSION: {}".format(version))
        err_msg = os.linesep.join(err_msg_lines)
        raise PodDefinitionNotFoundError(err_msg) from None
    rtnval = row
    return rtnval


def update_pod_definition(
        *,
        db_session: DbSession,
        pod_id: str,
        spec: Mapping[str, Any],
        actor_user_id: Optional[str]
    ) -> PodDefinitionVersion:
    """
        Append a new :class:`PodDefinitionVersion` row for an existing pod
        and bump ``PodDefinition.current_version``. Publishes
        ``entity.pod.definition_created`` against the new version number.

        :raises: PodDefinitionNotFoundError, PodSpecValidationError,
                 MemberKindNotRegisteredError
    """
    definition = read_pod_definition(db_session=db_session, pod_id=pod_id)
    report = _run_validators(spec=spec)
    _require_registered_member_kinds(spec=spec)

    if report.ok is False:
        err_msg_lines = ["Pod spec failed validation (update)."]
        for err in report.errors:
            err_msg_lines.append("- {}".format(err))
        err_msg = os.linesep.join(err_msg_lines)
        raise PodSpecValidationError(err_msg)

    next_version = int(definition.current_version) + 1
    spec_bytes = json.dumps(spec or {}, sort_keys=True).encode("utf-8")
    spec_hash = hashlib.sha256(spec_bytes).hexdigest()
    now = utc_now()

    version = PodDefinitionVersion(
        pod_id=definition.pod_id,
        version=next_version,
        spec_json=dict(spec or {}),
        spec_hash=spec_hash,
        validator_report={"ok": report.ok, "errors": list(report.errors), "warnings": list(report.warnings)},
        created_at=now,
        created_by=actor_user_id,
    )
    db_session.add(version)
    definition.current_version = next_version
    db_session.add(definition)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PodDefinitionEventTopics.DEFINITION_CREATED,
            payload={
                "pod_id": str(definition.pod_id),
                "project_id": str(definition.project_id),
                "pod_name": definition.pod_name,
                "version": next_version,
                "spec_hash": spec_hash,
                "actor_user_id": actor_user_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    rtnval = version
    return rtnval


def soft_delete_pod_definition(
        *,
        db_session: DbSession,
        pod_id: str,
        actor_user_id: Optional[str]
    ) -> None:
    """
        Mark a pod definition deleted and emit a lifecycle bus event.
    """
    definition = read_pod_definition(db_session=db_session, pod_id=pod_id)
    if definition.deleted_at is not None:
        return

    definition.deleted_at = utc_now()
    db_session.add(definition)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic="entity.pod.definition_deleted",
            payload={
                "pod_id": str(definition.pod_id),
                "project_id": str(definition.project_id),
                "actor_user_id": actor_user_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def list_pod_definitions(
        *,
        db_session: DbSession,
        project_id: str
    ) -> List[PodDefinition]:
    """
        Return every active :class:`PodDefinition` in a project.
    """
    query = db_session.query(PodDefinition).filter(PodDefinition.project_id == project_id)
    query = query.filter(PodDefinition.deleted_at.is_(None))
    query = query.order_by(PodDefinition.pod_name.asc())
    rtnval = query.all()
    return rtnval


def _run_validators(*, spec: Mapping[str, Any]) -> ValidationReport:
    """
        Walk every registered :class:`PodSpecValidatorProtocol` in
        PRECEDENCE order and aggregate the reports.
    """
    impls = list_factory_implementations(factory_protocol_name="pod_spec_validator")
    aggregate_errors: List[str] = []
    aggregate_warnings: List[str] = []
    for impl in impls:
        report = impl.validate(spec=spec)
        aggregate_errors.extend(report.errors)
        aggregate_warnings.extend(report.warnings)

    ok = len(aggregate_errors) == 0
    rtnval = ValidationReport(ok=ok, errors=aggregate_errors, warnings=aggregate_warnings)
    return rtnval


def _require_registered_member_kinds(*, spec: Mapping[str, Any]) -> None:
    """
        Reject specs whose member kinds are not registered with a
        :class:`PodMemberKindExtension`.

        :raises: MemberKindNotRegisteredError
    """
    if spec is None:
        return

    packs = list_resource_extensions(base_class=PodMemberKindExtension)
    registered = set()
    for pack in packs:
        registered.add(getattr(pack, "kind_name", ""))

    members = spec.get("members", None)
    if isinstance(members, list) is False:
        return

    for index, member in enumerate(members):
        if isinstance(member, Mapping) is False:
            continue
        kind = member.get("kind", None)
        if kind is None or kind in registered:
            continue
        err_msg_lines = ["members[{}] references unregistered kind.".format(index)]
        err_msg_lines.append("KIND: {}".format(kind))
        err_msg_lines.append("REGISTERED: {}".format(sorted(registered)))
        err_msg = os.linesep.join(err_msg_lines)
        raise MemberKindNotRegisteredError(err_msg)

    return
