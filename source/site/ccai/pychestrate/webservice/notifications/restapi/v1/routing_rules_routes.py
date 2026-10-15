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


from typing import Any

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.rest_authz import require_rest_permission
from ccai.pychestrate.webservice.notifications import repository as notification_repository
from ccai.pychestrate.webservice.notifications import service as notification_service
from ccai.pychestrate.webservice.notifications import rule_validation
from ccai.pychestrate.webservice.notifications.exceptions import (
    ChannelNotFoundError,
    RoutingRuleInvalidError,
)
from ccai.pychestrate.webservice.notifications.restapi.v1.channels_routes import (
    _ProblemAbort,
    _abort_problem,
    _decode_json_or_abort,
    _require_session,
    _resolve_actor_user_id,
)


ROUTING_RULES_PATH = "/notifications/routing-rules"

MAX_CHANNELS = rule_validation.MAX_CHANNELS
MAX_RECIPIENTS = rule_validation.MAX_RECIPIENTS


_is_uuid = rule_validation.is_uuid


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
    try:
        rtnval = rule_validation.validate_rule_fields(db_session=db_session, payload=payload)
    except RoutingRuleInvalidError as xcpt:
        _abort_problem(request=request, status=400, detail=xcpt.detail, extensions=xcpt.extensions)
    return rtnval


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
        try:
            if not _is_uuid(rule_id):
                raise ChannelNotFoundError(rule_id)
            rule = notification_service.set_routing_rule_disabled(db_session=db_session, rule_id=rule_id, disabled=payload["disabled"])
        except ChannelNotFoundError:
            _abort_problem(request=request, status=404, detail="No routing rule has the id {}.".format(rule_id), extensions={"rule_id": rule_id})
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
    read_permission = "system:notifications.read"
    write_permission = "system:notifications.write"
    app.attach_route(base, methods=["GET"])(require_rest_permission(handle_list_routing_rules, permission_key=read_permission))
    app.attach_route(base, methods=["POST"])(require_rest_permission(handle_create_routing_rule, permission_key=write_permission))
    app.attach_route(base + "/{rule_id}", methods=["PATCH"])(require_rest_permission(handle_update_routing_rule, permission_key=write_permission))
    app.attach_route(base + "/{rule_id}", methods=["DELETE"])(require_rest_permission(handle_delete_routing_rule, permission_key=write_permission))
    return


__all__ = [
    "ROUTING_RULES_PATH",
    "handle_create_routing_rule",
    "handle_delete_routing_rule",
    "handle_list_routing_rules",
    "handle_update_routing_rule",
    "register_routing_rules_routes",
]
