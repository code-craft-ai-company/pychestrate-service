"""
.. module:: security.rbac.inheritance
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Organization -> project binding inheritance seeding.

.. moduleauthor:: Code Craft AI LLC

When a new project is created, any organization-scope binding flagged
``inherits_into_project = True`` should take effect inside that project.
:func:`seed_project_permissions` reads the organization bindings and
creates matching project-scope bindings so the evaluator's
project-scope query picks them up directly (without a separate
cross-scope join on every evaluation).

:func:`wire_project_inheritance` subscribes ``seed_project_permissions``
to ``entity.project.created``. The session factory is injected so the
subscriber runs in a fresh transaction independent of the originating
request.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Callable, List

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent, subscribe
from ccai.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    RbacRoleBinding,
)


logger = logging.getLogger(__name__)


SessionFactory = Callable[[], DbSession]


_WIRED: bool = False


def seed_project_permissions(
        *,
        db_session: DbSession,
        project_id: str
    ) -> List[RbacRoleBinding]:
    """
        Materialize project-scope bindings for every organization-scope
        binding that has ``inherits_into_project = True``. Idempotent on
        the unique binding tuple so re-running for the same project is
        a no-op.

        :param db_session: Active SQLAlchemy session.
        :param project_id: UUID string of the newly-created project.

        :returns: The list of bindings that were inserted (excludes
                  existing rows).
    """
    inherited_rows = (
        db_session.query(RbacRoleBinding)
        .filter(RbacRoleBinding.scope_kind == BindingScope.ORGANIZATION)
        .filter(RbacRoleBinding.inherits_into_project == True)  # noqa: E712
        .all()
    )

    inserted: List[RbacRoleBinding] = []
    for org_binding in inherited_rows:
        existing = (
            db_session.query(RbacRoleBinding)
            .filter(RbacRoleBinding.role_id == org_binding.role_id)
            .filter(RbacRoleBinding.principal_kind == org_binding.principal_kind)
            .filter(RbacRoleBinding.principal_id == org_binding.principal_id)
            .filter(RbacRoleBinding.scope_kind == BindingScope.PROJECT)
            .filter(RbacRoleBinding.scope_id == project_id)
            .first()
        )
        if existing is not None:
            continue

        seed = RbacRoleBinding(
            binding_id=new_uuid(),
            role_id=org_binding.role_id,
            principal_kind=org_binding.principal_kind,
            principal_id=org_binding.principal_id,
            scope_kind=BindingScope.PROJECT,
            scope_id=project_id,
            inherits_into_project=False,
            created_at=utc_now(),
            created_by=org_binding.created_by,
        )
        db_session.add(seed)
        inserted.append(seed)

    if len(inserted) > 0:
        db_session.flush()

    return inserted


def _build_project_created_handler(*, session_factory: SessionFactory):
    """
        Return the bus subscriber closure that seeds project permissions
        on ``entity.project.created`` events.

        :param session_factory: Callable returning a fresh DbSession.

        :returns: Subscriber callable for the event bus.
    """

    def _handler(event: EntityEvent) -> None:
        payload = event.payload
        project_id = payload.get("project_id", None)
        if project_id is None:
            logger.info("rbac.inheritance.skip_project_created payload_missing_project_id")
            return
        session = session_factory()
        try:
            seed_project_permissions(
                db_session=session,
                project_id=str(project_id),
            )
            session.commit()
        except Exception as xcpt:  # noqa: BLE001 — subscriber isolation per messaging contract
            session.rollback()
            logger.exception(
                "rbac.inheritance.seed_failed project_id=%s error=%s",
                project_id, xcpt,
            )
        finally:
            session.close()
        return

    return _handler


def wire_project_inheritance(*, session_factory: SessionFactory) -> None:
    """
        Subscribe the project-inheritance seeder to
        ``entity.project.created``. Idempotent — safe to call multiple
        times at startup.

        :param session_factory: Callable returning a fresh DbSession.

        :returns: None.
    """
    global _WIRED
    if _WIRED is True:
        return
    _WIRED = True

    subscribe(
        topic="entity.project.created",
        subscriber=_build_project_created_handler(session_factory=session_factory),
    )
    return


def reset_for_testing() -> None:
    """
        Clear the wire-once guard. Test-only helper.

        :returns: None.
    """
    global _WIRED
    _WIRED = False
    return
