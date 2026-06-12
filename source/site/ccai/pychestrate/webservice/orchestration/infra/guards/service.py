"""
.. module:: orchestration.infra.guards.service
    :synopsis: Blast-radius-guards facade — attach / decide / explain.

M1 ships:

* :func:`set_attachment` — attach (or update) a rule on an
  environment; emits ATTACHMENT_SET.
* :func:`disable_attachment` — flips ``enabled = False``;
  emits ATTACHMENT_DISABLED.
* :func:`list_attachments_for_environment` — read helper.
* :func:`allow` — aggregate decision: looks up enabled
  attachments + invokes each rule; first DENY wins. Returns a
  :class:`GuardTrace` so callers can surface every per-rule
  verdict in error messages.
* :func:`explain` — admin-only counterpart to ``allow`` that
  walks every rule (attached or not) regardless of attachment
  state, useful for editor previews.
* :func:`list_rule_records` — enumerate registered rules.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.orchestration.infra.environment import (
    repository as env_repository,
)
from ccai.pychestrate.webservice.orchestration.infra.guards import (
    repository,
)
from ccai.pychestrate.webservice.orchestration.infra.guards.errors import (
    GuardAttachmentNotFoundError,
    GuardEnvironmentNotFoundError,
    GuardRuleUnknownError,
)
from ccai.pychestrate.webservice.orchestration.infra.guards.events import (
    GuardEventTopics,
)
from ccai.pychestrate.webservice.orchestration.infra.guards.factories.rule_protocol import (
    GuardContext,
    GuardDecision,
    GuardRuleProtocol,
    GuardVerdict,
)
from ccai.pychestrate.webservice.orchestration.infra.guards.models import (
    GuardAttachment,
)


GUARD_RULE_PROTOCOL: str = "guard_rule"


@dataclass(frozen=True)
class GuardAttachmentView:
    """
        Caller-facing attachment read-model.
    """
    project_id: str
    environment_id: str
    rule_id: str
    enabled: bool
    added_by: Optional[str]
    added_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class GuardRuleRecord:
    """
        Caller-facing record describing a registered rule.
    """
    rule_id: str
    description: str
    precedence: int


@dataclass(frozen=True)
class GuardTraceEntry:
    """
        Per-rule trace row.
    """
    rule_id: str
    verdict: GuardVerdict
    reason: str = ""


@dataclass(frozen=True)
class GuardTrace:
    """
        Aggregate decision surfaced to callers.

        :param allowed: True iff every evaluated rule returned
                        ALLOW.
        :param failing_rule_id: Stable identifier of the first
                                rule that denied; empty when
                                ``allowed`` is True.
        :param entries: Per-rule decision trace in evaluation
                        order.
    """
    allowed: bool
    failing_rule_id: str = ""
    entries: Tuple[GuardTraceEntry, ...] = ()


def set_attachment(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        rule_id: str,
        enabled: bool,
        actor_id: Optional[str] = None
    ) -> GuardAttachmentView:
    """
        Upsert a guard attachment.

        :raises: GuardEnvironmentNotFoundError when the env
                 does not exist or belongs to another project.
        :raises: GuardRuleUnknownError when ``rule_id`` has no
                 registered factory.
    """
    env = env_repository.find_by_id(
        db_session=db_session, environment_id=environment_id,
    )
    if env is None or str(env.project_id) != project_id:
        err_lines = ["Guard attachment env not found in project."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_msg = os.linesep.join(err_lines)
        raise GuardEnvironmentNotFoundError(err_msg) from None

    _resolve_rule(rule_id=rule_id)

    now = utc_now()
    row = repository.upsert_attachment(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
        rule_id=rule_id,
        enabled=enabled,
        actor_id=actor_id,
        now=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=GuardEventTopics.ATTACHMENT_SET,
            payload={
                "project_id": project_id,
                "environment_id": environment_id,
                "rule_id": rule_id,
                "enabled": enabled,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _attachment_to_view(row=row)
    return rtnval


def disable_attachment(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        rule_id: str,
        actor_id: Optional[str] = None
    ) -> GuardAttachmentView:
    """
        Flip an attachment to ``enabled = False``. Idempotent
        on already-disabled rows.

        :raises: GuardAttachmentNotFoundError on miss.
    """
    row = repository.find_attachment(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
        rule_id=rule_id,
    )
    if row is None:
        err_lines = ["Guard attachment not found."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_lines.append("RULE_ID: {}".format(rule_id))
        err_msg = os.linesep.join(err_lines)
        raise GuardAttachmentNotFoundError(err_msg) from None

    if row.enabled is False:
        rtnval = _attachment_to_view(row=row)
        return rtnval

    now = utc_now()
    row.enabled = False
    row.updated_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=GuardEventTopics.ATTACHMENT_DISABLED,
            payload={
                "project_id": project_id,
                "environment_id": environment_id,
                "rule_id": rule_id,
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _attachment_to_view(row=row)
    return rtnval


def list_attachments_for_environment(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        enabled_only: bool = False
    ) -> List[GuardAttachmentView]:
    """
        List attachments for an env. ``enabled_only=True``
        filters to currently-enabled rows.
    """
    rows = repository.list_attachments_for_environment(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
        enabled_only=enabled_only,
    )
    rtnval = [_attachment_to_view(row=r) for r in rows]
    return rtnval


def allow(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        action: str,
        actor_role_set: Tuple[str, ...] = (),
        requester_id: str = ""
    ) -> GuardTrace:
    """
        Resolve every enabled attachment, invoke each rule's
        ``evaluate``, and aggregate. First DENY wins. Returns
        a :class:`GuardTrace` with the per-rule decisions.

        Emits :data:`GuardEventTopics.DECIDED` with the
        resolved verdict + failing rule.

        :raises: GuardEnvironmentNotFoundError when the env
                 does not exist or belongs to another project.
    """
    env = env_repository.find_by_id(
        db_session=db_session, environment_id=environment_id,
    )
    if env is None or str(env.project_id) != project_id:
        err_lines = ["Guard env not found in project."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_msg = os.linesep.join(err_lines)
        raise GuardEnvironmentNotFoundError(err_msg) from None

    context = GuardContext(
        project_id=project_id,
        environment_id=environment_id,
        environment_state=env.state.value,
        environment_kind=env.kind_name,
        environment_attrs=dict(env.attrs or {}),
        actor_role_set=tuple(actor_role_set),
        action=action,
        requester_id=requester_id,
    )

    attachments = repository.list_attachments_for_environment(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
        enabled_only=True,
    )
    entries: List[GuardTraceEntry] = []
    failing_rule_id = ""
    allowed = True

    for attachment in attachments:
        rule_cls = _try_resolve_rule(rule_id=attachment.rule_id)
        if rule_cls is None:
            entries.append(
                GuardTraceEntry(
                    rule_id=attachment.rule_id,
                    verdict=GuardVerdict.DENY,
                    reason="rule '{}' has no registered factory".format(
                        attachment.rule_id,
                    ),
                )
            )
            allowed = False
            failing_rule_id = attachment.rule_id
            break
        decision = rule_cls.evaluate(context=context)
        entries.append(
            GuardTraceEntry(
                rule_id=attachment.rule_id,
                verdict=decision.verdict,
                reason=decision.reason,
            )
        )
        if decision.verdict != GuardVerdict.ALLOW:
            allowed = False
            failing_rule_id = attachment.rule_id
            break

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=GuardEventTopics.DECIDED,
            payload={
                "project_id": project_id,
                "environment_id": environment_id,
                "action": action,
                "allowed": allowed,
                "failing_rule_id": failing_rule_id,
                "entry_count": len(entries),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = GuardTrace(
        allowed=allowed,
        failing_rule_id=failing_rule_id,
        entries=tuple(entries),
    )
    return rtnval


def explain(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        action: str,
        actor_role_set: Tuple[str, ...] = (),
        requester_id: str = ""
    ) -> GuardTrace:
    """
        Walk every registered rule (regardless of attachment
        state) and return per-rule verdicts. The aggregate
        ``allowed`` flag is True iff every rule returns ALLOW.
        Useful for editor previews + admin troubleshooting.

        :raises: GuardEnvironmentNotFoundError when the env
                 does not exist or belongs to another project.
    """
    env = env_repository.find_by_id(
        db_session=db_session, environment_id=environment_id,
    )
    if env is None or str(env.project_id) != project_id:
        err_lines = ["Guard env not found in project."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_msg = os.linesep.join(err_lines)
        raise GuardEnvironmentNotFoundError(err_msg) from None

    context = GuardContext(
        project_id=project_id,
        environment_id=environment_id,
        environment_state=env.state.value,
        environment_kind=env.kind_name,
        environment_attrs=dict(env.attrs or {}),
        actor_role_set=tuple(actor_role_set),
        action=action,
        requester_id=requester_id,
    )

    candidates = list_factory_implementations(
        factory_protocol_name=GUARD_RULE_PROTOCOL,
    )
    entries: List[GuardTraceEntry] = []
    allowed = True
    failing_rule_id = ""
    for impl in candidates:
        decision = impl.evaluate(context=context)
        entries.append(
            GuardTraceEntry(
                rule_id=impl.rule_id(),
                verdict=decision.verdict,
                reason=decision.reason,
            )
        )
        if decision.verdict != GuardVerdict.ALLOW and allowed is True:
            allowed = False
            failing_rule_id = impl.rule_id()

    rtnval = GuardTrace(
        allowed=allowed,
        failing_rule_id=failing_rule_id,
        entries=tuple(entries),
    )
    return rtnval


def list_rule_records() -> Tuple[GuardRuleRecord, ...]:
    """
        Enumerate registered rule records in PRECEDENCE order.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=GUARD_RULE_PROTOCOL,
    )
    rtnval = tuple(
        GuardRuleRecord(
            rule_id=impl.rule_id(),
            description=impl.description(),
            precedence=getattr(impl, "PRECEDENCE", 1000),
        )
        for impl in candidates
    )
    return rtnval


def _resolve_rule(*, rule_id: str) -> Type[GuardRuleProtocol]:
    rule_cls = _try_resolve_rule(rule_id=rule_id)
    if rule_cls is not None:
        return rule_cls
    candidates = list_factory_implementations(
        factory_protocol_name=GUARD_RULE_PROTOCOL,
    )
    err_lines = ["No registered guard_rule for id."]
    err_lines.append("RULE_ID: {}".format(rule_id))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(impl.rule_id() for impl in candidates),
    ))
    err_msg = os.linesep.join(err_lines)
    raise GuardRuleUnknownError(err_msg) from None


def _try_resolve_rule(*, rule_id: str) -> Optional[Type[GuardRuleProtocol]]:
    candidates = list_factory_implementations(
        factory_protocol_name=GUARD_RULE_PROTOCOL,
    )
    for impl in candidates:
        if impl.rule_id() == rule_id:
            return impl
    return None


def _attachment_to_view(*, row: GuardAttachment) -> GuardAttachmentView:
    rtnval = GuardAttachmentView(
        project_id=str(row.project_id),
        environment_id=str(row.environment_id),
        rule_id=row.rule_id,
        enabled=row.enabled,
        added_by=str(row.added_by) if row.added_by is not None else None,
        added_at=row.added_at,
        updated_at=row.updated_at,
    )
    return rtnval
