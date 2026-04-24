"""
.. module:: project_templates.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Public internal API for 2-project-templates (M1).

.. moduleauthor:: Automation Mojo LLC

M1 surface: ``list_templates``, ``read_template``. M2 adds apply-at-create
and reapply flows with diff support.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.project_templates.extensions.template import (
    ProjectTemplateExtension,
)
from automojo.pychestrate.webservice.project_templates import registry as template_registry


OVERWRITE_POLICIES = frozenset({"skip_existing", "overwrite", "fail_on_conflict"})


@dataclass(frozen=True)
class TemplateSummary:
    """
        Public view over a registered :class:`ProjectTemplateExtension`.
    """
    template_id: str
    template_version: str
    display_name: str
    description: str
    variable_count: int
    tag_count: int
    notification_rule_count: int
    recommended_roles: Tuple[str, ...] = field(default_factory=tuple)


def list_templates() -> List[TemplateSummary]:
    """
        Return a :class:`TemplateSummary` per registered template.

        :returns: List of summaries sorted by template id.
    """
    registry = template_registry.load_registered_templates()

    rtnval: List[TemplateSummary] = []
    for template_id in sorted(registry.keys()):
        pack = registry[template_id]
        summary = _build_summary(pack=pack)
        rtnval.append(summary)

    return rtnval


def read_template(*, template_id: str) -> TemplateSummary:
    """
        Return a summary for one registered template.

        :param template_id: The template id to look up.

        :returns: The :class:`TemplateSummary`.
        :raises: TemplateNotRegisteredError
    """
    pack = template_registry.get_template(template_id=template_id)
    rtnval = _build_summary(pack=pack)
    return rtnval


@dataclass(frozen=True)
class TemplateApplyDiff:
    """
        Summary of the changes a template application produced.
    """
    variables_added: Tuple[str, ...] = field(default_factory=tuple)
    variables_skipped: Tuple[str, ...] = field(default_factory=tuple)
    variables_overwritten: Tuple[str, ...] = field(default_factory=tuple)
    tags_added: Tuple[str, ...] = field(default_factory=tuple)
    tags_skipped: Tuple[str, ...] = field(default_factory=tuple)
    notification_rules_added: Tuple[str, ...] = field(default_factory=tuple)
    notification_rules_skipped: Tuple[str, ...] = field(default_factory=tuple)


def apply_template(
        *,
        db_session: DbSession,
        project_id: str,
        template_id: str,
        overwrite_policy: str,
        actor_user_id: Optional[str]
    ) -> TemplateApplyDiff:
    """
        Apply a registered template to an existing project.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Target project id.
        :param template_id: Registered template id.
        :param overwrite_policy: One of :data:`OVERWRITE_POLICIES`.
        :param actor_user_id: Acting principal.

        :returns: The :class:`TemplateApplyDiff`.
    """
    if overwrite_policy not in OVERWRITE_POLICIES:
        raise ValueError("overwrite_policy must be one of {}".format(sorted(OVERWRITE_POLICIES)))

    pack = template_registry.get_template(template_id=template_id)
    diff = _apply_pack(
        db_session=db_session,
        project_id=project_id,
        pack=pack,
        overwrite_policy=overwrite_policy,
    )
    _publish_template_event(
        db_session=db_session,
        topic="entity.project.template_applied",
        project_id=project_id,
        template_id=template_id,
        template_version=pack.template_version,
        actor_user_id=actor_user_id,
        diff=diff,
    )
    db_session.commit()
    rtnval = diff
    return rtnval


def reapply_template(
        *,
        db_session: DbSession,
        project_id: str,
        template_id: str,
        template_version: str,
        overwrite_policy: str,
        actor_user_id: Optional[str]
    ) -> TemplateApplyDiff:
    """
        Re-apply the currently registered version of a template.

        :raises: ValueError when ``template_version`` does not match the
                 registered pack (callers must upgrade explicitly).
    """
    if overwrite_policy not in OVERWRITE_POLICIES:
        raise ValueError("overwrite_policy must be one of {}".format(sorted(OVERWRITE_POLICIES)))

    pack = template_registry.get_template(template_id=template_id)
    if template_version is not None and len(template_version.strip()) > 0:
        if pack.template_version != template_version:
            raise ValueError(
                "Registered template_version {} does not match requested {}".format(
                    pack.template_version, template_version,
                )
            )

    diff = _apply_pack(
        db_session=db_session,
        project_id=project_id,
        pack=pack,
        overwrite_policy=overwrite_policy,
    )
    _publish_template_event(
        db_session=db_session,
        topic="entity.project.template_reapplied",
        project_id=project_id,
        template_id=template_id,
        template_version=pack.template_version,
        actor_user_id=actor_user_id,
        diff=diff,
    )
    db_session.commit()
    rtnval = diff
    return rtnval


def preview_template(*, template_id: str) -> dict:
    """
        Return a structured preview of what a template would apply.
    """
    pack = template_registry.get_template(template_id=template_id)
    rtnval = {
        "template_id": pack.template_id,
        "template_version": pack.template_version,
        "variables": [
            {"name": v.name, "value_type": v.value_type, "default_value": v.default_value, "description": v.description}
            for v in pack.variables
        ],
        "tags": [
            {"taxonomy_name": t.taxonomy_name, "canonical_value": t.canonical_value}
            for t in pack.tags
        ],
        "notification_rules": [
            {
                "event_pattern": r.event_pattern,
                "template_name": r.template_name,
                "channel_names": list(r.channel_names),
                "recipients": list(r.recipients),
            }
            for r in pack.notification_rules
        ],
        "recommended_roles": list(pack.recommended_roles),
    }
    return rtnval


def _apply_pack(
        *,
        db_session: DbSession,
        project_id: str,
        pack,
        overwrite_policy: str
    ) -> TemplateApplyDiff:
    """
        Materialize a template's specs against the project's scope within
        a SAVEPOINT so a raised exception cleanly rolls back partial work.
    """
    savepoint = db_session.begin_nested()
    try:
        rtnval = _apply_pack_inner(
            db_session=db_session,
            project_id=project_id,
            pack=pack,
            overwrite_policy=overwrite_policy,
        )
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        raise
    return rtnval


def _apply_pack_inner(
        *,
        db_session: DbSession,
        project_id: str,
        pack,
        overwrite_policy: str
    ) -> TemplateApplyDiff:
    """
        Materialize a template's specs against the project's scope.
    """
    from automojo.pychestrate.webservice.notifications import service as notification_service
    from automojo.pychestrate.webservice.tagging import service as tag_service
    from automojo.pychestrate.webservice.variables import service as variable_service
    from automojo.pychestrate.webservice.variables.models import (
        VariableScope,
        VariableValueType,
    )

    variables_added: List[str] = []
    variables_skipped: List[str] = []
    variables_overwritten: List[str] = []
    for spec in pack.variables:
        existing = None
        try:
            existing = variable_service.get_variable(
                db_session=db_session,
                scope=VariableScope.PROJECT,
                scope_id=project_id,
                name=spec.name,
            )
        except Exception:  # noqa: BLE001 — absence is expected
            existing = None

        if existing is not None and overwrite_policy == "skip_existing":
            variables_skipped.append(spec.name)
            continue

        try:
            value_type = VariableValueType[spec.value_type.upper()]
        except KeyError:
            variables_skipped.append(spec.name)
            continue

        variable_service.set_variable(
            db_session=db_session,
            scope=VariableScope.PROJECT,
            scope_id=project_id,
            name=spec.name,
            value=spec.default_value,
            value_type=value_type,
            actor_user_id=None,
        )
        if existing is None:
            variables_added.append(spec.name)
        else:
            variables_overwritten.append(spec.name)

    tags_added: List[str] = []
    tags_skipped: List[str] = []
    for tag_spec in pack.tags:
        raw_tag = "{}:{}".format(tag_spec.taxonomy_name, tag_spec.canonical_value)
        try:
            tag_service.assign_tag(
                db_session=db_session,
                entity_kind="project",
                entity_id=project_id,
                raw_tag=raw_tag,
                actor_user_id=None,
            )
            tags_added.append(raw_tag)
        except Exception:  # noqa: BLE001 — duplicates / missing taxonomy ok for preview
            tags_skipped.append(raw_tag)

    rules_added: List[str] = []
    rules_skipped: List[str] = []
    for rule_spec in pack.notification_rules:
        try:
            notification_service.create_routing_rule(
                db_session=db_session,
                project_id=project_id,
                event_pattern=rule_spec.event_pattern,
                template_name=rule_spec.template_name,
                channel_ids=[],  # resolution by name lands post-M2
                recipients=list(rule_spec.recipients),
                filter_tag_expression=None,
                rate_limit_per_minute=None,
                actor_user_id=None,
            )
            rules_added.append(rule_spec.event_pattern)
        except Exception:  # noqa: BLE001 — tolerate partial wiring
            rules_skipped.append(rule_spec.event_pattern)

    rtnval = TemplateApplyDiff(
        variables_added=tuple(variables_added),
        variables_skipped=tuple(variables_skipped),
        variables_overwritten=tuple(variables_overwritten),
        tags_added=tuple(tags_added),
        tags_skipped=tuple(tags_skipped),
        notification_rules_added=tuple(rules_added),
        notification_rules_skipped=tuple(rules_skipped),
    )
    return rtnval


def _publish_template_event(
        *,
        db_session: DbSession,
        topic: str,
        project_id: str,
        template_id: str,
        template_version: str,
        actor_user_id: Optional[str],
        diff: TemplateApplyDiff
    ) -> None:
    """
        Enqueue a template lifecycle bus event.
    """
    event_payload = {
        "project_id": str(project_id),
        "template_id": template_id,
        "template_version": template_version,
        "actor_user_id": actor_user_id,
        "diff": {
            "variables_added": list(diff.variables_added),
            "variables_skipped": list(diff.variables_skipped),
            "variables_overwritten": list(diff.variables_overwritten),
            "tags_added": list(diff.tags_added),
            "tags_skipped": list(diff.tags_skipped),
            "notification_rules_added": list(diff.notification_rules_added),
            "notification_rules_skipped": list(diff.notification_rules_skipped),
        },
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


def _build_summary(*, pack) -> TemplateSummary:
    """
        Compose a :class:`TemplateSummary` from a registered pack.

        :param pack: The registered :class:`ProjectTemplateExtension` class.

        :returns: The summary.
    """
    recommended = tuple(getattr(pack, "recommended_roles", ()) or ())

    rtnval = TemplateSummary(
        template_id=getattr(pack, "template_id", ""),
        template_version=getattr(pack, "template_version", "0.0.0"),
        display_name=getattr(pack, "display_name", ""),
        description=getattr(pack, "description", ""),
        variable_count=len(getattr(pack, "variables", ()) or ()),
        tag_count=len(getattr(pack, "tags", ()) or ()),
        notification_rule_count=len(getattr(pack, "notification_rules", ()) or ()),
        recommended_roles=recommended,
    )
    return rtnval
