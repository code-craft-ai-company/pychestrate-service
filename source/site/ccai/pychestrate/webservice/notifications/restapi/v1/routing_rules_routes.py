"""
.. module:: notifications.restapi.v1.routing_rules_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for /api/v1/notifications/routing-rules (ORG-F08).

.. moduleauthor:: Code Craft AI LLC

A routing rule says "when this kind of run event happens (in this project, or in any),
send this template through these channels to these recipients". Without one nothing is
ever sent, and the rules could be stored in the service layer but not created through the
API. Four routes, like the channels' (system administrators, ``system:ui.admin.view``):

* ``POST   /api/v1/notifications/routing-rules``
* ``GET    /api/v1/notifications/routing-rules`` (optional ``project_id``)
* ``PATCH  /api/v1/notifications/routing-rules/{rule_id}`` (``{"disabled": true|false}``)
* ``DELETE /api/v1/notifications/routing-rules/{rule_id}``

A rule that could never fire is refused when it is created, with the reason: a pattern
that matches none of the run events the service publishes, an unknown template, a channel
that does not exist, no recipient. ``filter_tag_expression`` (tag filters, M2 of
``specs/2-notification-hub``) is refused too rather than stored and ignored.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.rest_authz import require_rest_permission
from ccai.pychestrate.webservice.notifications import repository as notification_repository
from ccai.pychestrate.webservice.notifications import service as notification_service
from ccai.pychestrate.webservice.notifications.exceptions import (
    ChannelNotFoundError,
    TemplateNotFoundError,
)
from ccai.pychestrate.webservice.notifications.restapi.v1.channels_routes import (
    _ProblemAbort,
    _abort_problem,
    _decode_json_or_abort,
    _require_session,
    _resolve_actor_user_id,
)
from ccai.pychestrate.webservice.notifications.router import pattern_matches
from ccai.pychestrate.webservice.notifications.run_notifier import NOTIFIED_TOPICS
from ccai.pychestrate.webservice.projects.models import Project


ROUTING_RULES_PATH = "/notifications/routing-rules"

#: Deliveries one rule may ask for (channels times recipients), so a typo cannot fan out to hundreds.
MAX_CHANNELS = 5
MAX_RECIPIENTS = 20


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _rule_to_dict(rule: Any) -> dict:
    """
        A routing rule as the REST response.

        :param rule: A :class:`NotificationRoutingRule` row.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "rule_id": str(rule.rule_id),
        "project_id": str(rule.project_id) if rule.project_id is not None else None,
        "event_pattern": rule.event_pattern,
        "template_name": rule.template_name,
        "channel_ids": [str(channel_id) for channel_id in (rule.channel_ids or [])],
        "recipients": list(rule.recipients or []),
        "rate_limit_per_minute": rule.rate_limit_per_minute,
        "disabled": bool(rule.disabled),
        "created_at": rule.created_at.isoformat() if rule.created_at is not None else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at is not None else None,
    }
    return rtnval


def _validated_create_fields(*, request: Request, db_session: Any, payload: dict) -> dict:
    """Check a create body, aborting with a 400 that says what is wrong; returns the cleaned fields."""
    if payload.get("filter_tag_expression", None) not in (None, ""):
        _abort_problem(request=request, status=400, detail="filter_tag_expression is not supported yet; a rule matches on event_pattern and project_id only.")

    pattern = str(payload.get("event_pattern", "") or "").strip()
    if len(pattern) == 0:
        _abort_problem(request=request, status=400, detail="event_pattern is required (for example 'entity.run.failed').")
    if not any(pattern_matches(pattern=pattern, topic=topic) for topic in NOTIFIED_TOPICS):
        _abort_problem(
            request=request, status=400,
            detail="event_pattern '{}' matches none of the events that can be notified: {}.".format(pattern, ", ".join(NOTIFIED_TOPICS)),
            extensions={"event_pattern": pattern},
        )

    template_name = str(payload.get("template_name", "") or "").strip()
    if len(template_name) == 0:
        _abort_problem(request=request, status=400, detail="template_name is required (for example 'run_failed').")
    try:
        template = notification_service._resolve_template(template_name=template_name)
    except TemplateNotFoundError:
        _abort_problem(request=request, status=400, detail="No notification template is named '{}'.".format(template_name), extensions={"template_name": template_name})
    fitting = [topic for topic in NOTIFIED_TOPICS if pattern_matches(pattern=pattern, topic=topic) and (len(template.event_topics) == 0 or topic in template.event_topics)]
    if len(fitting) == 0:
        _abort_problem(
            request=request, status=400,
            detail="Template '{}' describes {}, and event_pattern '{}' matches none of them, so this rule would never send.".format(
                template_name, ", ".join(template.event_topics), pattern),
            extensions={"template_name": template_name, "event_pattern": pattern},
        )

    channel_ids = payload.get("channel_ids", None)
    if not isinstance(channel_ids, list) or len(channel_ids) == 0 or len(channel_ids) > MAX_CHANNELS:
        _abort_problem(request=request, status=400, detail="channel_ids must list between 1 and {} channel ids.".format(MAX_CHANNELS))
    for channel_id in channel_ids:
        if not _is_uuid(channel_id):
            _abort_problem(request=request, status=400, detail="channel_ids holds a value that is not a channel id: {!r}.".format(channel_id))
        try:
            notification_service.read_channel(db_session=db_session, channel_id=str(channel_id))
        except ChannelNotFoundError:
            _abort_problem(request=request, status=400, detail="No notification channel has the id {}.".format(channel_id), extensions={"channel_id": str(channel_id)})

    recipients = payload.get("recipients", None)
    if not isinstance(recipients, list) or len(recipients) == 0 or len(recipients) > MAX_RECIPIENTS:
        _abort_problem(request=request, status=400, detail="recipients must list between 1 and {} addresses.".format(MAX_RECIPIENTS))
    cleaned_recipients: List[str] = []
    for recipient in recipients:
        if not isinstance(recipient, str) or len(recipient.strip()) == 0 or len(recipient) > 320:
            _abort_problem(request=request, status=400, detail="recipients holds a value that is not an address: {!r}.".format(recipient))
        cleaned_recipients.append(recipient.strip())

    project_id: Optional[str] = None
    if payload.get("project_id", None) not in (None, ""):
        project_id = str(payload["project_id"])
        if not _is_uuid(project_id) or db_session.query(Project.project_id).filter(Project.project_id == project_id).first() is None:
            _abort_problem(request=request, status=400, detail="No project has the id {}.".format(project_id), extensions={"project_id": project_id})

    rate_limit = payload.get("rate_limit_per_minute", None)
    if rate_limit is not None and (isinstance(rate_limit, bool) or not isinstance(rate_limit, int) or rate_limit < 1 or rate_limit > 10000):
        _abort_problem(request=request, status=400, detail="rate_limit_per_minute must be a whole number from 1 to 10000, or left out for no limit.")

    return {
        "project_id": project_id, "event_pattern": pattern, "template_name": template_name,
        "channel_ids": [str(channel_id) for channel_id in channel_ids], "recipients": cleaned_recipients,
        "rate_limit_per_minute": rate_limit,
    }


def handle_create_routing_rule(request: Request) -> Response:
    """
        ``POST /api/v1/notifications/routing-rules`` -- create a rule; 201 with the rule.

        :param request: Incoming webworks request.

        :returns: JSON response (201), or a problem response.
    """
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        fields = _validated_create_fields(request=request, db_session=db_session, payload=payload)
        rule = notification_service.create_routing_rule(
            db_session=db_session, filter_tag_expression=None, actor_user_id=_resolve_actor_user_id(request=request), **fields,
        )
        rtnval: Response = JSONResponse(content=_rule_to_dict(rule), status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_list_routing_rules(request: Request) -> Response:
    """
        ``GET /api/v1/notifications/routing-rules`` -- list rules, optionally for one ``project_id``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a list of rules, or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        project_arg = request.query_params.get("project_id", None)
        if project_arg is not None and not _is_uuid(project_arg):
            _abort_problem(request=request, status=400, detail="project_id must be a project id.", extensions={"query_param": "project_id"})
        rules = notification_service.list_routing_rules(db_session=db_session, project_id=project_arg)
        rtnval: Response = JSONResponse(content=[_rule_to_dict(rule) for rule in rules], status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_update_routing_rule(request: Request) -> Response:
    """
        ``PATCH /api/v1/notifications/routing-rules/{rule_id}`` -- turn a rule off or on
        (``{"disabled": true}``); nothing else about a rule changes (delete and create instead).

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the rule, or a problem response.
    """
    rule_id = str(request.path_params.get("rule_id", ""))
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        if not isinstance(payload.get("disabled", None), bool) or set(payload.keys()) != {"disabled"}:
            _abort_problem(request=request, status=400, detail="The body must be {\"disabled\": true} or {\"disabled\": false}.")
        rule = notification_repository.get_routing_rule(db_session=db_session, rule_id=rule_id) if _is_uuid(rule_id) else None
        if rule is None:
            _abort_problem(request=request, status=404, detail="No routing rule has the id {}.".format(rule_id), extensions={"rule_id": rule_id})
        rule.disabled = payload["disabled"]
        db_session.commit()
        rtnval: Response = JSONResponse(content=_rule_to_dict(rule), status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_delete_routing_rule(request: Request) -> Response:
    """
        ``DELETE /api/v1/notifications/routing-rules/{rule_id}`` -- remove a rule; 204.

        :param request: Incoming webworks request.

        :returns: An empty 204 response, or a problem response.
    """
    rule_id = str(request.path_params.get("rule_id", ""))
    try:
        db_session = _require_session(request=request)
        if not _is_uuid(rule_id):
            _abort_problem(request=request, status=404, detail="No routing rule has the id {}.".format(rule_id), extensions={"rule_id": rule_id})
        try:
            notification_service.delete_routing_rule(db_session=db_session, rule_id=rule_id)
        except ChannelNotFoundError:
            _abort_problem(request=request, status=404, detail="No routing rule has the id {}.".format(rule_id), extensions={"rule_id": rule_id})
        rtnval: Response = Response(status_code=204, body=b"")
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def register_routing_rules_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the routing-rule routes to a webworks application (the collection path before
        the ``{rule_id}`` one, as the router resolves overlapping patterns by registration order).

        :param app: The webworks application.
        :param version_prefix: The versioned API prefix (``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + ROUTING_RULES_PATH
    permission = "system:ui.admin.view"
    app.attach_route(base, methods=["GET"])(require_rest_permission(handle_list_routing_rules, permission_key=permission))
    app.attach_route(base, methods=["POST"])(require_rest_permission(handle_create_routing_rule, permission_key=permission))
    app.attach_route(base + "/{rule_id}", methods=["PATCH"])(require_rest_permission(handle_update_routing_rule, permission_key=permission))
    app.attach_route(base + "/{rule_id}", methods=["DELETE"])(require_rest_permission(handle_delete_routing_rule, permission_key=permission))
    return


__all__ = [
    "ROUTING_RULES_PATH",
    "handle_create_routing_rule",
    "handle_delete_routing_rule",
    "handle_list_routing_rules",
    "handle_update_routing_rule",
    "register_routing_rules_routes",
]
