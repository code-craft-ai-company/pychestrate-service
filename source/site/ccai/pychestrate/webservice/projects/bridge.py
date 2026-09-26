"""
.. module:: projects.bridge
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One owner for projects: keep the web UI's projects and the
               project registry the rest of the product uses in step.

.. moduleauthor:: Code Craft AI LLC

Two project systems grew side by side (PRJ-06). The web UI's
``/projects`` pages keep projects in the legacy ``projects`` table
(integer ids), and every feature manager behind those pages keys on that
id. The REST API, the CLI / MCP and every global view (builds, runs,
pipelines, test catalog, pods, clients, dashboards) use the project
registry (``projects_projects``, UUID + slug). A project created in the
UI existed nowhere else, and one created over REST never appeared in the
UI.

The registry now owns a project's identity. Every project has a registry
row, and a project the UI works with also has its legacy row, linked by
the registry's ``legacy_proj_id``. The UI's feature managers keep working
on the legacy id; everything else uses the registry UUID.

* Creating a project in the UI creates its registry row, and creating
  one over REST / MCP creates the legacy row the UI needs -- each in the
  same transaction (:class:`LegacyProjectListener`,
  :func:`ensure_legacy_project`).
* Renames, descriptions and deletions stay in step both ways.
* A member's role on a web-UI project is mirrored as the matching RBAC
  project role on the registry project (:func:`mirror_member_role`).
* :func:`reconcile_project_links` links or creates the missing half for
  projects that predate the bridge. It runs at startup and is idempotent.

A registry row created for an existing UI project gets the UUID
``uuid5("consumer-project:<legacy id>")``
(:func:`projects.legacy_identity.derived_project_uuid`) -- the id the RPA
pipeline and the enrollment page already used for that project -- so the
runs, pods and clients recorded under it belong to it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import re
import uuid

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.projects.events import ProjectEventTopics
from ccai.pychestrate.webservice.projects.legacy_identity import derived_project_uuid
from ccai.pychestrate.webservice.projects.models import (
    Project,
    ProjectMemberBinding,
    ProjectState,
)
from ccai.pychestrate.webservice.projects.repository import (
    get_project_by_id,
    get_project_by_legacy_id,
    get_project_by_slug,
)


#: Longest registry slug (``^[a-z][a-z0-9-]{1,62}$``).
MAX_SLUG_LENGTH: int = 63

#: Longest registry description.
MAX_DESCRIPTION_LENGTH: int = 2048

#: A web-UI project role -> the RBAC project role it grants on the
#: registry project, so a member can use the project in the global views
#: and REST API as well as in the UI.
LEGACY_ROLE_TO_RBAC_ROLE = {
    "owner": "project-owner",
    "administrator": "project-owner",
    "developer": "project-editor",
    "viewer": "project-viewer",
}

#: The RBAC project roles membership mirroring manages.
MIRRORED_RBAC_ROLES = ("project-owner", "project-editor", "project-viewer")

_LEGACY_TABLE: str = "projects"
_REGISTRY_TABLE: str = "projects_projects"
_NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")

_LOGGER = logging.getLogger("pychestrate.projects.bridge")


@dataclass
class ReconcileReport:
    """
        What :func:`reconcile_project_links` changed.

        :param linked: ``(legacy id, slug)`` pairs of existing projects
                       that were linked to each other.
        :param registry_created: Legacy ids that got a new registry project.
        :param legacy_created: Registry slugs that got a new legacy project.
        :param skipped: Registry slugs left without a legacy project (no
                        user exists to own one).
    """
    linked: List[Tuple[int, str]] = field(default_factory=list)
    registry_created: List[int] = field(default_factory=list)
    legacy_created: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)


def bridge_tables_present(*, db_session: DbSession) -> bool:
    """
        :param db_session: Active SQLAlchemy session.

        :returns: True when both project tables exist (a database built
                  from only one of the two model sets has nothing to
                  bridge).
    """
    # Inspect through the session's own connection: checking one out of
    # the engine's pool and returning it resets (rolls back) the
    # connection, which with a single shared connection (SQLite
    # in-memory, StaticPool) discards the session's pending work.
    try:
        inspector = sa.inspect(db_session.connection())
        rtnval = inspector.has_table(_LEGACY_TABLE) and inspector.has_table(_REGISTRY_TABLE)
    except Exception:
        rtnval = False
    return rtnval


def slug_for_legacy_name(*, name: str, legacy_proj_id: int) -> str:
    """
        A registry slug for a web-UI project name: lower-case, runs of
        anything but letters and digits become one hyphen, and a name
        that does not start with a letter gets a ``project-`` prefix.

        :param name: The legacy project name.
        :param legacy_proj_id: The legacy id, used when the name yields
                               nothing usable.

        :returns: A slug matching ``^[a-z][a-z0-9-]{1,62}$``.
    """
    base = _NON_SLUG_CHARS.sub("-", str(name or "").lower()).strip("-")
    if len(base) == 0:
        base = "project-{}".format(legacy_proj_id)
    elif base[0].isalpha() is False:
        base = "project-{}".format(base)
    base = base[:MAX_SLUG_LENGTH].rstrip("-")
    if len(base) < 2:
        base = "project-{}".format(legacy_proj_id)
    rtnval = base
    return rtnval


def _unique_slug(*, db_session: DbSession, base: str, legacy_proj_id: int) -> str:
    """
        ``base``, or ``base`` suffixed with the legacy id (then a short
        random tag) when another registry project already uses it.
    """
    candidates = [base]
    suffix = "-{}".format(legacy_proj_id)
    candidates.append(base[:MAX_SLUG_LENGTH - len(suffix)].rstrip("-") + suffix)
    tag = "-" + uuid.uuid4().hex[:8]
    candidates.append(base[:MAX_SLUG_LENGTH - len(tag)].rstrip("-") + tag)
    for candidate in candidates:
        if get_project_by_slug(db_session=db_session, slug=candidate) is None:
            return candidate
    rtnval = candidates[-1]
    return rtnval


def _legacy_model() -> Any:
    from ccai.pychestrate.core.orm import Project as LegacyProject  # noqa: E402
    return LegacyProject


def _enqueue_registry_event(*, db_session: DbSession, topic: str, payload: dict) -> None:
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(topic=topic, payload=payload, source_event_id=new_uuid()),
    )
    return


def registry_project_uuid_for_ref(*, db_session: DbSession, project_ref: Any) -> str:
    """
        The registry project UUID a project reference means: a UUID as
        given, and a web-UI project id through its link (falling back to
        its derived UUID when it has none yet -- the value used before the
        bridge).

        :param db_session: Active SQLAlchemy session.
        :param project_ref: A registry UUID or a web-UI project id.

        :returns: The registry project UUID, as text.
    """
    text = str(project_ref).strip()
    try:
        rtnval = str(uuid.UUID(text))
        return rtnval
    except (ValueError, AttributeError, TypeError):
        pass
    if text.isdigit() is True and bridge_tables_present(db_session=db_session) is True:
        linked = get_project_by_legacy_id(db_session=db_session, legacy_proj_id=int(text))
        if linked is not None:
            rtnval = str(linked.project_id)
            return rtnval
    rtnval = derived_project_uuid(text)
    return rtnval


# ---------------------------------------------------------------------------
# Legacy (web UI) project -> registry project
# ---------------------------------------------------------------------------


def ensure_registry_project(
        *,
        db_session: DbSession,
        legacy_project: Any,
        actor_user_id: Optional[str] = None
    ) -> Project:
    """
        The registry project for a web-UI project, linking an unlinked
        registry project of the same slug or creating one. Nothing is
        committed.

        :param db_session: Active SQLAlchemy session.
        :param legacy_project: The legacy ``Project`` row (flushed, so it
                               has its id).
        :param actor_user_id: Who created it, for the created event.

        :returns: The linked registry :class:`Project`.
    """
    rtnval, _outcome = _link_or_create_registry_project(
        db_session=db_session, legacy_project=legacy_project, actor_user_id=actor_user_id,
    )
    return rtnval


def _link_or_create_registry_project(
        *,
        db_session: DbSession,
        legacy_project: Any,
        actor_user_id: Optional[str]
    ) -> Tuple[Project, str]:
    """
        :returns: ``(registry project, outcome)``; outcome is
                  ``"existing"``, ``"linked"`` or ``"created"``.
    """
    legacy_id = int(legacy_project.id)
    existing = get_project_by_legacy_id(db_session=db_session, legacy_proj_id=legacy_id)
    if existing is not None:
        return existing, "existing"

    base_slug = slug_for_legacy_name(name=legacy_project.name, legacy_proj_id=legacy_id)
    same_slug = get_project_by_slug(db_session=db_session, slug=base_slug)
    if same_slug is not None and same_slug.legacy_proj_id is None:
        same_slug.legacy_proj_id = legacy_id
        db_session.flush()
        return same_slug, "linked"

    derived_id = derived_project_uuid(legacy_id)
    same_id = get_project_by_id(db_session=db_session, project_id=derived_id)
    if same_id is not None and same_id.legacy_proj_id is None:
        same_id.legacy_proj_id = legacy_id
        db_session.flush()
        return same_id, "linked"

    now = utc_now()
    project = Project(
        project_id=derived_id,
        slug=_unique_slug(db_session=db_session, base=base_slug, legacy_proj_id=legacy_id),
        display_name=str(legacy_project.name),
        description=str(legacy_project.description or "")[:MAX_DESCRIPTION_LENGTH],
        state=ProjectState.ACTIVE,
        owning_group_id=None,
        template_id=None,
        template_version=None,
        extension_fields={},
        created_at=legacy_project.created_at or now,
        updated_at=now,
        archived_at=None,
        legacy_proj_id=legacy_id,
    )
    db_session.add(project)
    db_session.flush()
    _enqueue_registry_event(
        db_session=db_session,
        topic=ProjectEventTopics.PROJECT_CREATED,
        payload={
            "project_id": str(project.project_id),
            "slug": project.slug,
            "display_name": project.display_name,
            "owning_group_id": None,
            "template_id": None,
            "template_version": None,
            "actor_user_id": str(actor_user_id) if actor_user_id is not None else None,
            "created_at": project.created_at.isoformat(),
            "legacy_proj_id": legacy_id,
        },
    )
    return project, "created"


def sync_registry_from_legacy(*, db_session: DbSession, legacy_project: Any) -> Optional[Project]:
    """
        Copy a web-UI project's name and description onto its registry
        project (the slug, the stable URL identifier, stays). Nothing is
        committed.

        :returns: The registry project, or None when it has none yet.
    """
    project = get_project_by_legacy_id(db_session=db_session, legacy_proj_id=int(legacy_project.id))
    if project is None:
        return None
    project.display_name = str(legacy_project.name)
    project.description = str(legacy_project.description or "")[:MAX_DESCRIPTION_LENGTH]
    project.updated_at = utc_now()
    db_session.flush()
    rtnval = project
    return rtnval


def delete_registry_project_for_legacy(
        *,
        db_session: DbSession,
        legacy_proj_id: int,
        actor_user_id: Optional[str]
    ) -> Optional[str]:
    """
        Delete the registry project linked to a web-UI project being
        deleted (with its member bindings). Nothing is committed.

        :returns: The deleted registry project id, or None.
    """
    project = get_project_by_legacy_id(db_session=db_session, legacy_proj_id=int(legacy_proj_id))
    if project is None:
        return None
    project_id = str(project.project_id)
    slug = project.slug
    revoke_project_bindings(db_session=db_session, project_id=project_id, actor_user_id=actor_user_id)
    (
        db_session.query(ProjectMemberBinding)
        .filter(ProjectMemberBinding.project_id == project.project_id)
        .delete(synchronize_session=False)
    )
    db_session.delete(project)
    db_session.flush()
    _enqueue_registry_event(
        db_session=db_session,
        topic=ProjectEventTopics.PROJECT_DELETED,
        payload={
            "project_id": project_id,
            "slug": slug,
            "actor_user_id": str(actor_user_id) if actor_user_id is not None else None,
        },
    )
    return project_id


def mirror_member_role(
        *,
        db_session: DbSession,
        legacy_proj_id: int,
        user_id: Any,
        legacy_role: Optional[str],
        actor_user_id: Optional[str] = None
    ) -> Optional[str]:
    """
        Make a user's RBAC project binding on a registry project match
        their role on its web-UI project (:data:`LEGACY_ROLE_TO_RBAC_ROLE`):
        bind the matching ``project-*`` role and remove any other one of
        them. ``legacy_role=None`` (no longer a member) removes them all.
        A no-op when the project is not linked or the roles were never
        seeded. Nothing is committed.

        :returns: The RBAC role now bound, or None.
    """
    from ccai.pychestrate.webservice.security.rbac import binding_service  # noqa: E402
    from ccai.pychestrate.webservice.security.rbac.models import (  # noqa: E402
        BindingScope,
        PrincipalKind,
        RbacRole,
        RbacRoleBinding,
    )

    project = get_project_by_legacy_id(db_session=db_session, legacy_proj_id=int(legacy_proj_id))
    if project is None:
        return None
    roles = {
        row.role_name: row for row in
        db_session.query(RbacRole).filter(RbacRole.role_name.in_(MIRRORED_RBAC_ROLES)).all()
    }
    if len(roles) == 0:
        return None
    target = LEGACY_ROLE_TO_RBAC_ROLE.get(str(legacy_role), None) if legacy_role is not None else None
    if target not in roles:
        target = None

    principal_id = str(uuid.UUID(str(user_id)))
    existing = (
        db_session.query(RbacRoleBinding)
        .filter(RbacRoleBinding.principal_kind == PrincipalKind.USER)
        .filter(RbacRoleBinding.principal_id == principal_id)
        .filter(RbacRoleBinding.scope_kind == BindingScope.PROJECT)
        .filter(RbacRoleBinding.scope_id == str(project.project_id))
        .filter(RbacRoleBinding.role_id.in_([row.role_id for row in roles.values()]))
        .all()
    )
    already_bound = False
    for binding in existing:
        if target is not None and binding.role_id == roles[target].role_id:
            already_bound = True
            continue
        binding_service.revoke_role(
            db_session=db_session, binding_id=str(binding.binding_id),
            actor_user_id=actor_user_id, commit=False,
        )
    if target is not None and already_bound is False:
        binding_service.assign_role(
            db_session=db_session, role_name=target, principal_kind=PrincipalKind.USER,
            principal_id=principal_id, scope_kind=BindingScope.PROJECT,
            scope_id=str(project.project_id), inherits_into_project=False,
            actor_user_id=actor_user_id, commit=False,
        )
    return target


def revoke_project_bindings(*, db_session: DbSession, project_id: str,
                            actor_user_id: Optional[str] = None) -> int:
    """
        Remove every RBAC binding scoped to a registry project being
        deleted. Nothing is committed.

        :returns: How many bindings were removed.
    """
    from ccai.pychestrate.webservice.security.rbac import binding_service  # noqa: E402
    from ccai.pychestrate.webservice.security.rbac.models import (  # noqa: E402
        BindingScope,
        RbacRoleBinding,
    )

    bindings = (
        db_session.query(RbacRoleBinding)
        .filter(RbacRoleBinding.scope_kind == BindingScope.PROJECT)
        .filter(RbacRoleBinding.scope_id == str(project_id))
        .all()
    )
    for binding in bindings:
        binding_service.revoke_role(
            db_session=db_session, binding_id=str(binding.binding_id),
            actor_user_id=actor_user_id, commit=False,
        )
    rtnval = len(bindings)
    return rtnval


def _mirror_all_members(*, db_session: DbSession, legacy_proj_id: int) -> None:
    from ccai.pychestrate.core.orm import ProjectMember  # noqa: E402

    for member in db_session.query(ProjectMember).filter(ProjectMember.project_id == int(legacy_proj_id)).all():
        mirror_member_role(
            db_session=db_session, legacy_proj_id=legacy_proj_id,
            user_id=member.user_id, legacy_role=member.role,
        )
    return


class LegacyProjectListener:
    """
        The web UI's :class:`ProjectManager` lifecycle listener: keeps each
        web-UI project's registry project in step, inside the UI's
        transaction.
    """

    def project_created(self, db_session: DbSession, legacy_project: Any, user_id: Any) -> None:
        if bridge_tables_present(db_session=db_session) is True:
            ensure_registry_project(
                db_session=db_session, legacy_project=legacy_project, actor_user_id=user_id,
            )
            _mirror_all_members(db_session=db_session, legacy_proj_id=int(legacy_project.id))
        return

    def project_updated(self, db_session: DbSession, legacy_project: Any, user_id: Any) -> None:
        if bridge_tables_present(db_session=db_session) is True:
            if sync_registry_from_legacy(db_session=db_session, legacy_project=legacy_project) is None:
                ensure_registry_project(
                    db_session=db_session, legacy_project=legacy_project, actor_user_id=user_id,
                )
        return

    def project_deleting(self, db_session: DbSession, legacy_proj_id: int, user_id: Any) -> None:
        if bridge_tables_present(db_session=db_session) is True:
            delete_registry_project_for_legacy(
                db_session=db_session, legacy_proj_id=legacy_proj_id, actor_user_id=user_id,
            )
        return

    def member_changed(self, db_session: DbSession, legacy_proj_id: int, user_id: Any,
                       role: Optional[str], actor_user_id: Any) -> None:
        if bridge_tables_present(db_session=db_session) is True:
            mirror_member_role(
                db_session=db_session, legacy_proj_id=legacy_proj_id, user_id=user_id,
                legacy_role=role,
                actor_user_id=str(actor_user_id) if actor_user_id is not None else None,
            )
        return


# ---------------------------------------------------------------------------
# Registry project -> legacy (web UI) project
# ---------------------------------------------------------------------------


def _user_exists(*, db_session: DbSession, user_id: Any) -> bool:
    from ccai.pychestrate.core.orm import User  # noqa: E402

    try:
        parsed = uuid.UUID(str(user_id))
    except (TypeError, ValueError, AttributeError):
        return False
    rtnval = db_session.query(User.id).filter(User.id == parsed).first() is not None
    return rtnval


def _fallback_owner(*, db_session: DbSession) -> Optional[str]:
    """
        An owner for a legacy project whose creator is unknown: the
        earliest user holding a system-wide ``system-admin`` binding,
        else the earliest user.
    """
    from ccai.pychestrate.core.orm import User  # noqa: E402
    from ccai.pychestrate.webservice.security.rbac.models import (  # noqa: E402
        BindingScope,
        PrincipalKind,
        RbacRole,
        RbacRoleBinding,
    )

    try:
        admin = (
            db_session.query(RbacRoleBinding.principal_id)
            .join(RbacRole, RbacRole.role_id == RbacRoleBinding.role_id)
            .filter(RbacRole.role_name == "system-admin")
            .filter(RbacRoleBinding.principal_kind == PrincipalKind.USER)
            .filter(RbacRoleBinding.scope_kind == BindingScope.SYSTEM)
            .first()
        )
    except Exception:
        admin = None
    if admin is not None and _user_exists(db_session=db_session, user_id=admin[0]) is True:
        return str(admin[0])
    earliest = db_session.query(User.id).order_by(User.created_at.asc()).first()
    rtnval = str(earliest[0]) if earliest is not None else None
    return rtnval


def ensure_legacy_project(
        *,
        db_session: DbSession,
        project: Project,
        owner_user_id: Optional[str]
    ) -> Optional[Any]:
    """
        The web-UI (legacy) project for a registry project, linking an
        unlinked legacy project of the same name (compared
        case-insensitively) or creating one owned by ``owner_user_id``
        (or, when that is not a user, by :func:`_fallback_owner`).
        Nothing is committed.

        :param db_session: Active SQLAlchemy session.
        :param project: The registry project.
        :param owner_user_id: Who creates it; becomes the legacy owner.

        :returns: The legacy ``Project`` row, or None when no user exists
                  to own one (it is created later by the reconcile).
    """
    rtnval, _outcome = _link_or_create_legacy_project(
        db_session=db_session, project=project, owner_user_id=owner_user_id,
    )
    return rtnval


def _link_or_create_legacy_project(
        *,
        db_session: DbSession,
        project: Project,
        owner_user_id: Optional[str]
    ) -> Tuple[Optional[Any], str]:
    """
        :returns: ``(legacy project or None, outcome)``; outcome is
                  ``"existing"``, ``"linked"``, ``"created"`` or
                  ``"skipped"``.
    """
    from ccai.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectCreateRequest,
        ProjectManager,
    )

    LegacyProject = _legacy_model()
    if project.legacy_proj_id is not None:
        linked = db_session.query(LegacyProject).filter(LegacyProject.id == project.legacy_proj_id).first()
        if linked is not None:
            return linked, "existing"
        project.legacy_proj_id = None

    linked_ids = {
        row[0] for row in
        db_session.query(Project.legacy_proj_id).filter(Project.legacy_proj_id.isnot(None)).all()
    }
    for candidate in (
            db_session.query(LegacyProject)
            .filter(sa.func.lower(LegacyProject.name) == project.slug.lower())
            .all()):
        if int(candidate.id) not in linked_ids:
            project.legacy_proj_id = int(candidate.id)
            db_session.flush()
            return candidate, "linked"

    owner = owner_user_id if _user_exists(db_session=db_session, user_id=owner_user_id) else None
    if owner is None:
        owner = _fallback_owner(db_session=db_session)
    if owner is None:
        _LOGGER.warning("pychestrate.projects.bridge.no_owner_for_legacy_project slug=%s", project.slug)
        return None, "skipped"

    name = project.slug
    if db_session.query(LegacyProject.id).filter(LegacyProject.name == name).first() is not None:
        name = "{}-{}".format(project.slug, uuid.uuid4().hex[:8])
    created = ProjectManager(db_session).create_project(
        ProjectCreateRequest(
            name=name,
            description=str(project.description or ""),
            metadata={"registry_project_id": str(project.project_id)},
        ),
        owner,
        commit=False,
    )
    project.legacy_proj_id = int(created.id)
    db_session.flush()
    _mirror_all_members(db_session=db_session, legacy_proj_id=int(created.id))
    legacy = db_session.query(LegacyProject).filter(LegacyProject.id == int(created.id)).first()
    return legacy, "created"


def sync_legacy_from_registry(*, db_session: DbSession, project: Project) -> None:
    """
        Copy a registry project's description onto its legacy project.
        The legacy name is left alone: it is the UI's unique identifier
        and allows fewer characters than a display name. Nothing is
        committed.
    """
    if project.legacy_proj_id is None or bridge_tables_present(db_session=db_session) is False:
        return
    LegacyProject = _legacy_model()
    legacy = db_session.query(LegacyProject).filter(LegacyProject.id == project.legacy_proj_id).first()
    if legacy is not None:
        legacy.description = str(project.description or "")
        legacy.updated_at = utc_now()
        db_session.flush()
    return


def delete_legacy_project_for_registry(
        *,
        db_session: DbSession,
        project: Project,
        actor_user_id: Optional[str]
    ) -> None:
    """
        Delete the legacy project of a registry project being deleted,
        with everything the UI keeps for it. Nothing is committed.

        :raises: ProjectHasActiveJobsError when the UI project still has
                 pending or running jobs.
    """
    from ccai.pychestrate.core.managers.project_manager import ProjectManager  # noqa: E402

    if project.legacy_proj_id is None or bridge_tables_present(db_session=db_session) is False:
        return
    LegacyProject = _legacy_model()
    if db_session.query(LegacyProject.id).filter(LegacyProject.id == project.legacy_proj_id).first() is None:
        return
    ProjectManager(db_session).delete_project(
        int(project.legacy_proj_id), str(actor_user_id or ""), commit=False,
    )
    return


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------


def reconcile_project_links(*, db_session: DbSession) -> ReconcileReport:
    """
        Give every web-UI project a registry project and every registry
        project a web-UI project, linking same-named pairs first, and
        mirror every web-UI membership onto its registry project.
        Idempotent; commits. Another process reconciling at the same time
        makes this pass stop early (the next start finishes it).

        :param db_session: Active SQLAlchemy session.

        :returns: :class:`ReconcileReport`.
    """
    report = ReconcileReport()
    if bridge_tables_present(db_session=db_session) is False:
        return report

    LegacyProject = _legacy_model()
    try:
        for legacy in db_session.query(LegacyProject).order_by(LegacyProject.id.asc()).all():
            project, outcome = _link_or_create_registry_project(
                db_session=db_session, legacy_project=legacy, actor_user_id=None,
            )
            if outcome == "created":
                report.registry_created.append(int(legacy.id))
            elif outcome == "linked":
                report.linked.append((int(legacy.id), project.slug))

        unlinked = (
            db_session.query(Project)
            .filter(Project.legacy_proj_id.is_(None))
            .order_by(Project.created_at.asc())
            .all()
        )
        for project in unlinked:
            legacy, outcome = _link_or_create_legacy_project(
                db_session=db_session, project=project, owner_user_id=None,
            )
            if outcome == "created":
                report.legacy_created.append(project.slug)
            elif outcome == "linked":
                report.linked.append((int(legacy.id), project.slug))
            elif outcome == "skipped":
                report.skipped.append(project.slug)

        for (legacy_id,) in db_session.query(LegacyProject.id).all():
            _mirror_all_members(db_session=db_session, legacy_proj_id=int(legacy_id))
        db_session.commit()
    except IntegrityError:
        db_session.rollback()
        _LOGGER.info("pychestrate.projects.bridge.reconcile_raced; another process is reconciling")
    return report


__all__ = [
    "LegacyProjectListener",
    "ReconcileReport",
    "bridge_tables_present",
    "delete_legacy_project_for_registry",
    "delete_registry_project_for_legacy",
    "ensure_legacy_project",
    "ensure_registry_project",
    "mirror_member_role",
    "reconcile_project_links",
    "registry_project_uuid_for_ref",
    "revoke_project_bindings",
    "slug_for_legacy_name",
    "sync_legacy_from_registry",
    "sync_registry_from_legacy",
]
