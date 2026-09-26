"""
.. module:: projects.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Public internal API for 2-projects.

.. moduleauthor:: Code Craft AI LLC

Implements the M1 skeleton of the ``2-projects`` spec:

- ``create_project`` — insert a new :class:`Project` row and publish
  ``entity.project.created``.
- ``read_project_by_slug`` — fetch a project by canonical slug.

Archive / delete / member APIs land in M2.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, List, Mapping, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.hardening import idempotency as hardening_idempotency
from ccai.pychestrate.webservice.hardening import logs as hardening_logs
from ccai.pychestrate.webservice.hardening import metrics as hardening_metrics
from ccai.pychestrate.webservice.hardening.rate_limit import (
    RateLimitExceeded,
    acquire as rate_limit_acquire,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.projects.events import ProjectEventTopics
from ccai.pychestrate.webservice.projects.exceptions import (
    LastAdminRemovalError,
    MemberBindingNotFoundError,
    MetadataFieldValidationError,
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectStateTransitionError,
)
from ccai.pychestrate.webservice.projects.metadata_registry import (
    load_registered_fields,
)
from ccai.pychestrate.webservice.projects.models import (
    Project,
    ProjectMemberBinding,
    ProjectState,
)
from ccai.pychestrate.webservice.projects import bridge as project_bridge
from ccai.pychestrate.webservice.projects import repository as project_repository
from ccai.pychestrate.webservice.projects.repository import (
    get_project_by_slug,
    insert_project,
)
from ccai.pychestrate.webservice.projects.slug import canonicalize_project_slug


PROJECT_OWNER_ROLE: str = "project-owner"

_CREATE_RATE_SESSION_CAPACITY: int = 10
_CREATE_RATE_SESSION_REFILL_PER_SEC: float = 10.0 / 60.0  # 10 / min
_CREATE_RATE_IP_CAPACITY: int = 30
_CREATE_RATE_IP_REFILL_PER_SEC: float = 30.0 / 60.0  # 30 / min

_IDEMPOTENCY_SCOPE_CREATE: str = "project.create"


def create_project(
        *,
        db_session: DbSession,
        slug: str,
        display_name: str,
        description: str,
        owning_group_id: Optional[str],
        template_id: Optional[str],
        template_version: Optional[str],
        actor_user_id: Optional[str],
        idempotency_key: Optional[str] = None,
        rate_limit_session_key: Optional[str] = None,
        rate_limit_ip_key: Optional[str] = None
    ) -> Project:
    """
        Create a new project.

        :param db_session: Active SQLAlchemy session.
        :param slug: Desired project slug; will be canonicalized.
        :param display_name: Human-facing name.
        :param description: Free-form description.
        :param owning_group_id: Optional owning group.
        :param template_id: Optional template identifier applied at creation.
        :param template_version: Optional template version (SemVer).
        :param actor_user_id: Acting principal for audit attribution.
        :param idempotency_key: Optional ``Idempotency-Key`` header value;
                                when present and the key is known, the
                                persisted project from the first call is
                                returned.
        :param rate_limit_session_key: Optional session identifier used
                                       to throttle creations at 10/min.
        :param rate_limit_ip_key: Optional IP / network identifier used
                                  to throttle creations at 30/min.

        :returns: The newly persisted :class:`Project`.
        :raises: ProjectAlreadyExistsError, SlugValidationError,
                 SemanticError, RateLimitExceeded
    """
    if display_name is None:
        raise SemanticError("create_project requires a non-None display_name")

    if rate_limit_session_key is not None and len(str(rate_limit_session_key).strip()) > 0:
        rate_limit_acquire(
            scope_name="project.create.session",
            scope_key=str(rate_limit_session_key),
            capacity=_CREATE_RATE_SESSION_CAPACITY,
            refill_per_second=_CREATE_RATE_SESSION_REFILL_PER_SEC,
        )

    if rate_limit_ip_key is not None and len(str(rate_limit_ip_key).strip()) > 0:
        rate_limit_acquire(
            scope_name="project.create.ip",
            scope_key=str(rate_limit_ip_key),
            capacity=_CREATE_RATE_IP_CAPACITY,
            refill_per_second=_CREATE_RATE_IP_REFILL_PER_SEC,
        )

    if idempotency_key is not None and len(str(idempotency_key).strip()) > 0:
        cached = hardening_idempotency.lookup(
            db_session=db_session,
            scope=_IDEMPOTENCY_SCOPE_CREATE,
            idempotency_key=idempotency_key,
        )
        if cached is not None and "project_id" in cached:
            existing_project = (
                db_session.query(Project)
                .filter(Project.project_id == cached["project_id"])
                .first()
            )
            if existing_project is not None:
                hardening_metrics.increment_counter(
                    name="project.create.idempotent_hit", labels={},
                )
                return existing_project

    canonical_slug = canonicalize_project_slug(raw_slug=slug)

    existing = get_project_by_slug(db_session=db_session, slug=canonical_slug)
    if existing is not None:
        _raise_already_exists(slug=canonical_slug)

    now = utc_now()
    project = Project(
        project_id=new_uuid(),
        slug=canonical_slug,
        display_name=display_name,
        description=description if description is not None else "",
        state=ProjectState.ACTIVE,
        owning_group_id=owning_group_id,
        template_id=template_id,
        template_version=template_version,
        extension_fields={},
        created_at=now,
        updated_at=now,
        archived_at=None,
    )

    try:
        insert_project(db_session=db_session, project=project)
    except IntegrityError:
        _raise_already_exists(slug=canonical_slug)

    event_payload = {
        "project_id": str(project.project_id),
        "slug": project.slug,
        "display_name": project.display_name,
        "owning_group_id": str(owning_group_id) if owning_group_id is not None else None,
        "template_id": template_id,
        "template_version": template_version,
        "actor_user_id": actor_user_id,
        "created_at": project.created_at.isoformat(),
    }
    event = EntityEvent(
        topic=ProjectEventTopics.PROJECT_CREATED,
        payload=event_payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=event)

    if idempotency_key is not None and len(str(idempotency_key).strip()) > 0:
        hardening_idempotency.record(
            db_session=db_session,
            scope=_IDEMPOTENCY_SCOPE_CREATE,
            idempotency_key=idempotency_key,
            response_payload={"project_id": str(project.project_id), "slug": project.slug},
        )

    # The web UI's pages work on a legacy project row; create it in the
    # same transaction so the project shows up there too (PRJ-06).
    if project_bridge.bridge_tables_present(db_session=db_session) is True:
        project_bridge.ensure_legacy_project(
            db_session=db_session, project=project, owner_user_id=actor_user_id,
        )

    db_session.commit()

    hardening_metrics.increment_counter(name="project.create.ok", labels={})
    hardening_logs.emit_event(
        event="project.create.ok",
        level="INFO",
        fields={"slug": project.slug, "project_id": str(project.project_id)},
    )

    rtnval = project
    return rtnval


def read_project_by_slug(*, db_session: DbSession, slug: str) -> Project:
    """
        Return the project with the given slug.

        :param db_session: Active SQLAlchemy session.
        :param slug: Slug to look up; canonicalized first.

        :returns: The :class:`Project`.
        :raises: ProjectNotFoundError, SlugValidationError
    """
    canonical_slug = canonicalize_project_slug(raw_slug=slug)
    project = get_project_by_slug(db_session=db_session, slug=canonical_slug)
    if project is None:
        err_msg_lines = ["Cannot read project — no row matched slug."]
        err_msg_lines.append("SLUG: {}".format(canonical_slug))
        err_msg = os.linesep.join(err_msg_lines)
        raise ProjectNotFoundError(err_msg) from None

    rtnval = project
    return rtnval


def archive_project(
        *,
        db_session: DbSession,
        slug: str,
        actor_user_id: Optional[str]
    ) -> Project:
    """
        Transition a project into ``ARCHIVED`` state.

        :raises: ProjectNotFoundError, ProjectStateTransitionError
    """
    project = read_project_by_slug(db_session=db_session, slug=slug)
    if project.state == ProjectState.ARCHIVED:
        rtnval = project
        return rtnval

    project.state = ProjectState.ARCHIVED
    project.archived_at = utc_now()
    project.updated_at = utc_now()
    db_session.add(project)
    db_session.flush()

    _publish_lifecycle(
        db_session=db_session,
        topic=ProjectEventTopics.PROJECT_ARCHIVED,
        project=project,
        actor_user_id=actor_user_id,
    )
    db_session.commit()

    rtnval = project
    return rtnval


def unarchive_project(
        *,
        db_session: DbSession,
        slug: str,
        actor_user_id: Optional[str]
    ) -> Project:
    """
        Transition a project from ``ARCHIVED`` back to ``ACTIVE``.
    """
    project = read_project_by_slug(db_session=db_session, slug=slug)
    if project.state == ProjectState.ACTIVE:
        rtnval = project
        return rtnval

    project.state = ProjectState.ACTIVE
    project.archived_at = None
    project.updated_at = utc_now()
    db_session.add(project)
    db_session.flush()

    _publish_lifecycle(
        db_session=db_session,
        topic=ProjectEventTopics.PROJECT_UNARCHIVED,
        project=project,
        actor_user_id=actor_user_id,
    )
    db_session.commit()

    rtnval = project
    return rtnval


def delete_project(
        *,
        db_session: DbSession,
        slug: str,
        actor_user_id: Optional[str]
    ) -> None:
    """
        Hard-delete an archived project; emits ``entity.project.deleted``.

        :raises: ProjectStateTransitionError if the project is not archived.
    """
    project = read_project_by_slug(db_session=db_session, slug=slug)
    if project.state != ProjectState.ARCHIVED:
        err_msg_lines = ["Cannot delete project — project must be archived first."]
        err_msg_lines.append("SLUG: {}".format(project.slug))
        err_msg_lines.append("STATE: {}".format(project.state.value))
        err_msg = os.linesep.join(err_msg_lines)
        raise ProjectStateTransitionError(err_msg) from None

    project_id_str = str(project.project_id)
    project_slug = project.slug

    # The web UI's legacy project goes with it (refused while it has
    # pending or running jobs: ProjectHasActiveJobsError).
    project_bridge.delete_legacy_project_for_registry(
        db_session=db_session, project=project, actor_user_id=actor_user_id,
    )
    # Role bindings scoped to the project would otherwise outlive it.
    project_bridge.revoke_project_bindings(
        db_session=db_session, project_id=project_id_str, actor_user_id=actor_user_id,
    )

    # Explicitly cascade member bindings before removing the project
    # row. Per 2-projects design the DB FK ``ON DELETE CASCADE`` is the
    # canonical mechanism on PostgreSQL; we also perform the cascade in
    # Python so the same semantics apply under SQLite (in-memory test
    # engine) and any backend that defaults FK enforcement off.
    bindings = project_repository.list_member_bindings(
        db_session=db_session, project_id=project_id_str,
    )
    for binding in bindings:
        project_repository.delete_member_binding(
            db_session=db_session, binding=binding,
        )

    project_repository.delete_project(db_session=db_session, project=project)

    event_payload = {
        "project_id": project_id_str,
        "slug": project_slug,
        "actor_user_id": actor_user_id,
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ProjectEventTopics.PROJECT_DELETED,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def patch_project(
        *,
        db_session: DbSession,
        slug: str,
        display_name: Optional[str],
        description: Optional[str],
        extension_fields: Optional[Mapping[str, Any]],
        actor_user_id: Optional[str]
    ) -> Project:
    """
        Update mutable project fields. ``extension_fields`` are validated
        against the registered :class:`ProjectMetadataFieldExtension` packs.

        :raises: ProjectNotFoundError, MetadataFieldValidationError
    """
    project = read_project_by_slug(db_session=db_session, slug=slug)

    if display_name is not None:
        project.display_name = display_name

    if description is not None:
        project.description = description

    if extension_fields is not None:
        validated = _validate_extension_fields(fields=extension_fields)
        merged = dict(project.extension_fields) if project.extension_fields is not None else {}
        merged.update(validated)
        project.extension_fields = merged

    project.updated_at = utc_now()
    db_session.add(project)
    db_session.flush()
    if description is not None:
        project_bridge.sync_legacy_from_registry(db_session=db_session, project=project)
    db_session.commit()

    rtnval = project
    return rtnval


def add_member(
        *,
        db_session: DbSession,
        slug: str,
        user_id: str,
        role_name: str,
        actor_user_id: Optional[str]
    ) -> ProjectMemberBinding:
    """
        Attach a :class:`ProjectMemberBinding` for ``(user_id, role_name)``.

        :raises: ProjectNotFoundError, SemanticError
    """
    if user_id is None or len(str(user_id).strip()) == 0:
        raise SemanticError("add_member requires a non-empty user_id")
    if role_name is None or len(role_name.strip()) == 0:
        raise SemanticError("add_member requires a non-empty role_name")

    project = read_project_by_slug(db_session=db_session, slug=slug)

    existing = project_repository.get_member_binding(
        db_session=db_session,
        project_id=str(project.project_id),
        user_id=user_id,
        role_name=role_name,
    )
    if existing is not None:
        rtnval = existing
        return rtnval

    binding = ProjectMemberBinding(
        binding_id=new_uuid(),
        project_id=project.project_id,
        user_id=user_id,
        role_name=role_name,
        added_at=utc_now(),
        added_by_user_id=actor_user_id,
    )
    project_repository.insert_member_binding(db_session=db_session, binding=binding)

    event_payload = {
        "project_id": str(project.project_id),
        "slug": project.slug,
        "user_id": str(user_id),
        "role_name": role_name,
        "actor_user_id": actor_user_id,
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ProjectEventTopics.PROJECT_MEMBER_ADDED,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    rtnval = binding
    return rtnval


def remove_member(
        *,
        db_session: DbSession,
        slug: str,
        user_id: str,
        role_name: str,
        actor_user_id: Optional[str],
        force: bool = False
    ) -> None:
    """
        Detach a :class:`ProjectMemberBinding`. If the binding being
        removed is the last :data:`PROJECT_OWNER_ROLE` on the project,
        :class:`LastAdminRemovalError` is raised so the project cannot
        become unmanaged. A caller with the appropriate system
        ``platform.admin`` privilege MAY pass ``force=True`` to override
        the guard; the REST layer is responsible for verifying that
        claim before forwarding.

        :param db_session: Active SQLAlchemy session.
        :param slug: Target project slug.
        :param user_id: Member to detach.
        :param role_name: Role preset name in the binding row.
        :param actor_user_id: Acting principal id (audit attribution).
        :param force: When ``True``, bypass the last-admin safeguard.

        :returns: None.
        :raises: ProjectNotFoundError, MemberBindingNotFoundError,
                 LastAdminRemovalError
    """
    project = read_project_by_slug(db_session=db_session, slug=slug)

    binding = project_repository.get_member_binding(
        db_session=db_session,
        project_id=str(project.project_id),
        user_id=user_id,
        role_name=role_name,
    )
    if binding is None:
        err_msg_lines = ["Cannot remove member — binding not found."]
        err_msg_lines.append("PROJECT: {}".format(project.slug))
        err_msg_lines.append("USER_ID: {}".format(user_id))
        err_msg_lines.append("ROLE: {}".format(role_name))
        err_msg = os.linesep.join(err_msg_lines)
        raise MemberBindingNotFoundError(err_msg) from None

    if role_name == PROJECT_OWNER_ROLE and force is False:
        owner_count = project_repository.count_role_holders(
            db_session=db_session,
            project_id=str(project.project_id),
            role_name=PROJECT_OWNER_ROLE,
        )
        if owner_count <= 1:
            err_msg_lines = ["Cannot remove last ProjectOwner binding."]
            err_msg_lines.append("PROJECT: {}".format(project.slug))
            err_msg_lines.append("ROLE: {}".format(PROJECT_OWNER_ROLE))
            err_msg_lines.append("HINT: pass force=True as platform.admin to override.")
            err_msg = os.linesep.join(err_msg_lines)
            raise LastAdminRemovalError(err_msg) from None

    project_repository.delete_member_binding(db_session=db_session, binding=binding)

    event_payload = {
        "project_id": str(project.project_id),
        "slug": project.slug,
        "user_id": str(user_id),
        "role_name": role_name,
        "actor_user_id": actor_user_id,
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ProjectEventTopics.PROJECT_MEMBER_REMOVED,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def list_members(
        *,
        db_session: DbSession,
        slug: str
    ) -> List[ProjectMemberBinding]:
    """
        Return every member binding for a project.

        :raises: ProjectNotFoundError
    """
    project = read_project_by_slug(db_session=db_session, slug=slug)
    rtnval = project_repository.list_member_bindings(
        db_session=db_session,
        project_id=str(project.project_id),
    )
    return rtnval


def cascade_user_deleted(*, db_session: DbSession, user_id: str) -> int:
    """
        Remove every :class:`ProjectMemberBinding` for a deleted user.

        Intended to be called by the ``entity.user.deleted`` bus subscriber.

        :returns: Count of removed bindings.
    """
    removed = project_repository.delete_bindings_for_user(
        db_session=db_session, user_id=user_id,
    )
    db_session.commit()
    rtnval = int(removed)
    return rtnval


def _publish_lifecycle(
        *,
        db_session: DbSession,
        topic: str,
        project: Project,
        actor_user_id: Optional[str]
    ) -> None:
    """
        Enqueue a lifecycle event referring to ``project``.
    """
    event_payload = {
        "project_id": str(project.project_id),
        "slug": project.slug,
        "state": project.state.value,
        "actor_user_id": actor_user_id,
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=topic,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )
    return


def _validate_extension_fields(*, fields: Mapping[str, Any]) -> Mapping[str, Any]:
    """
        Validate that every supplied extension field matches a registered
        :class:`ProjectMetadataFieldExtension` spec.

        :returns: The validated ``dict``.
        :raises: MetadataFieldValidationError
    """
    registry = load_registered_fields()

    rtnval = {}
    for name, value in fields.items():
        pack = registry.get(name, None)
        if pack is None:
            err_msg_lines = ["Unknown extension field."]
            err_msg_lines.append("FIELD_NAME: {}".format(name))
            err_msg = os.linesep.join(err_msg_lines)
            raise MetadataFieldValidationError(err_msg)

        pack.validate_value(value=value)
        rtnval[name] = value

    return rtnval


def _raise_already_exists(*, slug: str) -> None:
    """
        Construct and raise a :class:`ProjectAlreadyExistsError`.

        :param slug: The slug that collided.

        :returns: None — never returns.
        :raises: ProjectAlreadyExistsError
    """
    err_msg_lines = ["Cannot create project — slug already exists."]
    err_msg_lines.append("SLUG: {}".format(slug))
    err_msg = os.linesep.join(err_msg_lines)
    raise ProjectAlreadyExistsError(err_msg) from None
