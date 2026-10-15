"""
.. module:: webinterface.blueprints.config.routes_notifications
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Admin pages for notification channels and the rules that send through them (audit ORG-F08).

.. moduleauthor:: Code Craft AI LLC

Channels (an email server, a Slack or Teams webhook, PagerDuty, a generic webhook) are where messages go; rules say which events send to which channel.
Until this page they could only be made with the REST API or ``pyc``.

* ``GET  /admin/notifications``                                  -- channels, rules and recent deliveries.
* ``GET|POST /admin/notifications/channels/create``              -- add a channel: pick a type, then fill in its settings.
* ``GET  /admin/notifications/channels/{channel_id}``            -- one channel: settings, test message, secrets, switch, delete.
* ``POST /admin/notifications/channels/{channel_id}/test``       -- send a test message.
* ``POST /admin/notifications/channels/{channel_id}/state``      -- turn the channel off or on.
* ``POST /admin/notifications/channels/{channel_id}/secrets``    -- replace a secret.
* ``POST /admin/notifications/channels/{channel_id}/delete``     -- delete the channel and the secrets stored for it.
* ``GET|POST /admin/notifications/rules/create``                 -- add a rule (one per event ticked).
* ``POST /admin/notifications/rules/{rule_id}/state``            -- turn a rule off or on.
* ``POST /admin/notifications/rules/{rule_id}/delete``           -- delete a rule.

Reading needs ``system:notifications.read``; everything that changes something needs ``system:notifications.write``. A secret setting is typed once
(or pointed at an existing secrets-vault secret), stored in the vault, and never shown again: the page shows where it is stored.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import HTMLResponse, Response

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
    list_resource_extensions,
)
from ccai.pychestrate.webservice.jobs.run.state.events import RunStateEventTopics
from ccai.pychestrate.webservice.notifications import repository as notification_repository
from ccai.pychestrate.webservice.notifications import rule_validation
from ccai.pychestrate.webservice.notifications import service as notification_service
from ccai.pychestrate.webservice.notifications.channel_config import is_secret_ref, prepare_channel_config, secret_name_from_ref
from ccai.pychestrate.webservice.notifications.exceptions import (
    ChannelAlreadyExistsError,
    ChannelConfigInvalidError,
    ChannelInUseError,
    ChannelNotFoundError,
    ChannelSecretAccessDeniedError,
    RoutingRuleInvalidError,
)
from ccai.pychestrate.webservice.notifications.extensions.template import NotificationTemplateExtension
from ccai.pychestrate.webservice.notifications.models import ChannelScopeLevel, DispatchOutcome
from ccai.pychestrate.webservice.projects.models import Project
from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    CONFIG_PATH,
    MultiFormView,
    _attach_session_to_response,
    _build_default_template_context,
    _has_permission,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_admin_permission_for,
    _resolve_authenticated_request,
    _wrap_admin_handler_in_shell,
)


NOTIFICATIONS_READ_PERMISSION: str = "system:notifications.read"
NOTIFICATIONS_WRITE_PERMISSION: str = "system:notifications.write"

_ROUTE_TABLE = (
    ("config.notifications_overview", "/notifications", ("GET",)),
    ("config.notification_channel_create", "/notifications/channels/create", ("GET", "POST")),
    ("config.notification_channel_detail", "/notifications/channels/{channel_id}", ("GET",)),
    ("config.notification_channel_test", "/notifications/channels/{channel_id}/test", ("POST",)),
    ("config.notification_channel_state", "/notifications/channels/{channel_id}/state", ("POST",)),
    ("config.notification_channel_secrets", "/notifications/channels/{channel_id}/secrets", ("POST",)),
    ("config.notification_channel_delete", "/notifications/channels/{channel_id}/delete", ("POST",)),
    ("config.notification_rule_create", "/notifications/rules/create", ("GET", "POST")),
    ("config.notification_rule_state", "/notifications/rules/{rule_id}/state", ("POST",)),
    ("config.notification_rule_delete", "/notifications/rules/{rule_id}/delete", ("POST",)),
)

# A route that can change something (any POST, including the create forms' GET) needs the write permission; the read-only pages need the read one.
_ROUTE_PERMISSIONS = {
    endpoint_name: NOTIFICATIONS_WRITE_PERMISSION if "POST" in methods else NOTIFICATIONS_READ_PERMISSION
    for endpoint_name, _relative_path, methods in _ROUTE_TABLE
}

#: The events a rule can be made for, in the words an administrator uses.
EVENT_CHOICES: Tuple[Tuple[str, str], ...] = (
    (RunStateEventTopics.FAILED, "A run fails"),
    (RunStateEventTopics.COMPLETED, "A run completes"),
)

#: Labels of the form inputs, for the error summary.
CHANNEL_FIELD_LABELS: Dict[str, str] = {"name": "Name"}

RECENT_DELIVERIES: int = 20

_CONFIG_PREFIX: str = "cfg__"
_SECRET_PREFIX: str = "secret__"
_REF_PREFIX: str = "ref__"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _principal_for(*, auth: Any) -> Any:
    """
        The vault principal for the signed-in administrator.
    """
    from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind  # noqa: E402
    from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal  # noqa: E402

    rtnval = AuthPrincipal(
        user_id=str(auth.user_id), session_id="", provider_kind=AuthProviderKind.LOCAL, provider_name="local",
    )
    return rtnval


def _kinds() -> List[Any]:
    """
        The channel kinds that can be added, in the order the page lists them.
    """
    impls = list_factory_implementations(factory_protocol_name="notification_channel")
    seen: Dict[str, Any] = {}
    for impl in impls:
        kind = getattr(impl, "channel_kind", "")
        if len(kind) > 0 and kind not in seen:
            seen[kind] = impl
    rtnval = sorted(seen.values(), key=lambda impl: (impl.kind_label or impl.channel_kind).lower())
    return rtnval


def _protocol_for(kind: str) -> Optional[Any]:
    """
        The implementation of a kind, or None when none is registered (a channel left behind by a removed extension).
    """
    for impl in _kinds():
        if impl.channel_kind == kind:
            return impl
    return None


def _kind_label(kind: str) -> str:
    protocol = _protocol_for(kind)
    rtnval = (protocol.kind_label or kind) if protocol is not None else kind
    return rtnval


def event_label(pattern: str) -> str:
    """
        An event pattern in an administrator's words.

        :param pattern: ``entity.run.failed``, ``entity.run.completed`` or a glob.

        :returns: "A run fails", "A run completes", "A run fails or completes", or the pattern itself.
    """
    from ccai.pychestrate.webservice.notifications.router import pattern_matches  # noqa: E402

    labels = dict(EVENT_CHOICES)
    if pattern in labels:
        return labels[pattern]
    matched = [topic for topic, _label in EVENT_CHOICES if pattern_matches(pattern=pattern, topic=topic)]
    if len(matched) == len(EVENT_CHOICES):
        return "A run fails or completes"
    if len(matched) == 1:
        return labels[matched[0]]
    return pattern


def _template_for_topic(topic: str) -> Optional[str]:
    """
        The name of the message template that describes an event.
    """
    names = sorted(
        pack.template_name for pack in list_resource_extensions(base_class=NotificationTemplateExtension)
        if pack.is_test_message is False and topic in pack.event_topics
    )
    rtnval = names[0] if len(names) > 0 else None
    return rtnval


def _projects(db_session: Any) -> List[Any]:
    return db_session.query(Project).order_by(Project.display_name.asc()).all()


def _vault_secret_names(*, auth: Any, db_session: Any) -> List[str]:
    """
        The vault secrets the administrator may point a channel at; empty when they may not list the vault.
    """
    from ccai.pychestrate.webservice.secrets import secrets_service  # noqa: E402
    from ccai.pychestrate.webservice.secrets.exceptions import SecretAccessDeniedError  # noqa: E402

    try:
        records = secrets_service.list_secrets(db_session=db_session, principal=_principal_for(auth=auth))
    except SecretAccessDeniedError:
        db_session.rollback()
        return []
    rtnval = [record.secret_ref for record in records]
    return rtnval


def _delivery_row(*, attempt: Any, envelope: Any, channel_names: Dict[str, str]) -> Dict[str, Any]:
    outcome = attempt.outcome.value.lower() if isinstance(attempt.outcome, DispatchOutcome) else str(attempt.outcome).lower()
    rtnval = {
        "when": attempt.attempted_at,
        "event": envelope.event_topic,
        "event_label": event_label(envelope.event_topic) if envelope.event_topic.startswith("entity.run.") else "Test message",
        "channel": channel_names.get(str(envelope.channel_id), "(deleted channel)"),
        "channel_deleted": str(envelope.channel_id) not in channel_names,
        "channel_id": str(envelope.channel_id),
        "recipient": envelope.recipient,
        "outcome": outcome,
        "detail": attempt.error_message or "",
        "latency_ms": attempt.latency_ms,
    }
    return rtnval


def _channel_row(*, db_session: Any, channel: Any, project_names: Dict[str, str]) -> Dict[str, Any]:
    described = notification_service.describe_channel(channel=channel)
    last = notification_repository.latest_attempt_for_channel(db_session=db_session, channel_id=str(channel.channel_id))
    rtnval = {
        "channel": channel,
        "channel_id": str(channel.channel_id),
        "name": channel.name,
        "kind_label": _kind_label(channel.kind),
        "scope_label": project_names.get(str(channel.project_id), "One project") if channel.scope_level == ChannelScopeLevel.PROJECT else "All projects",
        "state": "disabled" if channel.disabled is True else "active",
        "unprotected": described["unprotected_secret_fields"],
        "last_outcome": last.outcome.value.lower() if last is not None else None,
        "last_when": last.attempted_at if last is not None else None,
    }
    return rtnval


def _flash_error(*, auth: Any, message: str) -> None:
    flash.add_flash(session=auth.session, message=message, category=flash.CATEGORY_ERROR)
    return


def _guard_csrf(*, auth: Any, form: Any, fallback_url: str) -> Optional[Response]:
    rtnval = auth_guard.enforce_csrf_or_redirect(form=form, session=auth.session, fallback_url=fallback_url)
    if rtnval is not None:
        _attach_session_to_response(response=rtnval, session=auth.session)
    return rtnval


def _overview_url() -> str:
    return _url_for_module.url_for("config.notifications_overview")


def _channel_url(channel_id: str) -> str:
    return _url_for_module.url_for("config.notification_channel_detail", channel_id=channel_id)


def _close(db_session: Any) -> None:
    try:
        db_session.close()
    except Exception:
        pass
    return


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def handle_notifications_overview(request: Request) -> Response:
    """
        ``GET /admin/notifications``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        projects = _projects(db_session)
        project_names = {str(project.project_id): project.display_name for project in projects}
        channels = notification_service.list_channels(db_session=db_session, scope_level=None, project_id=None)
        channel_rows = [_channel_row(db_session=db_session, channel=channel, project_names=project_names) for channel in channels]
        channel_names = {row["channel_id"]: row["name"] for row in channel_rows}

        rule_rows: List[Dict[str, Any]] = []
        for rule in notification_service.list_routing_rules(db_session=db_session, project_id=None):
            rule_rows.append({
                "rule_id": str(rule.rule_id),
                "event_label": event_label(rule.event_pattern),
                "project": project_names.get(str(rule.project_id), "One project") if rule.project_id is not None else "Every project",
                "channels": [channel_names.get(str(channel_id), "(deleted channel)") for channel_id in (rule.channel_ids or [])],
                "recipients": list(rule.recipients or []),
                "rate_limit": rule.rate_limit_per_minute,
                "state": "disabled" if rule.disabled is True else "active",
            })

        deliveries = [
            _delivery_row(attempt=attempt, envelope=envelope, channel_names=channel_names)
            for attempt, envelope in notification_repository.list_recent_deliveries(db_session=db_session, limit=RECENT_DELIVERIES)
        ]

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session, request_endpoint="config.notifications_overview", flashes=flashes, csrf_token=auth.csrf_token,
        )
        context["channels"] = channel_rows
        context["rules"] = rule_rows
        context["deliveries"] = deliveries
        context["can_manage"] = _has_permission(auth=auth, permission=NOTIFICATIONS_WRITE_PERMISSION)
        response = _render(template_name="config/notifications/overview.html", context=context)
        _attach_session_to_response(response=response, session=auth.session)
        return response
    finally:
        _close(db_session)


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

def _field_view(field: Any) -> Dict[str, Any]:
    """
        One declared setting as the template draws it.
    """
    rtnval = {
        "name": field.name, "label": field.label, "help": field.help, "required": field.required, "secret": field.secret,
        "field_type": field.field_type, "default": field.default,
        "cfg_id": _CONFIG_PREFIX + field.name, "secret_id": _SECRET_PREFIX + field.name, "ref_id": _REF_PREFIX + field.name,
    }
    return rtnval


def _render_channel_create(
        *, auth: Any, kind: Optional[str], form_data: Optional[MultiFormView], status_code: int = 200,
        errors: Optional[Dict[str, str]] = None
    ) -> HTMLResponse:
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session, request_endpoint="config.notification_channel_create", flashes=flashes, csrf_token=auth.csrf_token,
    )
    protocol = _protocol_for(kind) if kind is not None else None
    context["kinds"] = [{"kind": impl.channel_kind, "label": impl.kind_label or impl.channel_kind, "description": impl.kind_description} for impl in _kinds()]
    context["kind"] = protocol.channel_kind if protocol is not None else None
    context["kind_label"] = (protocol.kind_label or protocol.channel_kind) if protocol is not None else ""
    context["kind_description"] = protocol.kind_description if protocol is not None else ""
    # A mapping setting (extra headers) has no input on the page; the REST API accepts it.
    context["fields"] = [_field_view(field) for field in protocol.config_fields if field.field_type != "mapping"] if protocol is not None else []
    context["vault_secrets"] = _vault_secret_names(auth=auth, db_session=auth.db_session) if protocol is not None else []
    context["form_data"] = form_data
    context["errors"] = errors if errors is not None else {}
    context["error_labels"] = dict(CHANNEL_FIELD_LABELS)
    if protocol is not None:
        for field in protocol.config_fields:
            context["error_labels"][_CONFIG_PREFIX + field.name] = field.label
            context["error_labels"][_SECRET_PREFIX + field.name] = field.label
    response = _render(template_name="config/notifications/channel_create.html", context=context, status_code=status_code)
    _attach_session_to_response(response=response, session=auth.session)
    return response


def _channel_inputs_from_form(*, protocol: Any, form: Any) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
    """
        Turn the submitted inputs into ``config`` and ``secrets`` for :func:`notification_service.create_channel`.

        :returns: ``(config, secrets, errors)`` where errors are inputs that could not even be read (a port that is not a number).
    """
    config: Dict[str, Any] = {}
    secrets: Dict[str, str] = {}
    errors: Dict[str, str] = {}
    for field in protocol.config_fields:
        if field.field_type == "mapping":
            continue
        if field.secret is True:
            typed = str(form.get(_SECRET_PREFIX + field.name, "") or "")
            chosen = str(form.get(_REF_PREFIX + field.name, "") or "").strip()
            if len(typed) > 0:
                secrets[field.name] = typed
            elif len(chosen) > 0:
                config[field.name] = "secret://" + chosen
            continue
        raw = form.get(_CONFIG_PREFIX + field.name, None)
        if field.field_type == "bool":
            config[field.name] = raw is not None and str(raw).lower() in ("1", "true", "on", "yes")
            continue
        text = str(raw or "").strip()
        if len(text) == 0:
            continue
        if field.field_type == "number":
            try:
                config[field.name] = int(text)
            except ValueError:
                errors[_CONFIG_PREFIX + field.name] = "{} must be a whole number.".format(field.label)
            continue
        config[field.name] = text
    return config, secrets, errors


def _add_setting_errors(*, errors: Dict[str, str], protocol: Any, xcpt: ChannelConfigInvalidError) -> None:
    """
        Put each problem about one setting beside its input (the first problem for an input wins), in words without the setting's internal name.
    """
    for setting, problem in xcpt.field_problems.items():
        field = next((item for item in protocol.config_fields if item.name == setting), None)
        prefix = _SECRET_PREFIX if field is not None and field.secret is True else _CONFIG_PREFIX
        errors.setdefault(prefix + setting, problem.replace(" ('{}')".format(setting), ""))
    return


def handle_channel_create(request: Request) -> Response:
    """
        ``GET|POST /admin/notifications/channels/create``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        if request.method.upper() == "GET":
            kind = request.query_params.get("kind", None)
            return _render_channel_create(auth=auth, kind=kind, form_data=None)

        single_form = _parse_form_or_empty(request=request)
        form_view = MultiFormView(data=_parse_form_multi(request=request))
        csrf_redirect = _guard_csrf(auth=auth, form=single_form, fallback_url=_url_for_module.url_for("config.notification_channel_create"))
        if csrf_redirect is not None:
            return csrf_redirect

        kind = str(single_form.get("kind", "") or "").strip()
        protocol = _protocol_for(kind)
        if protocol is None:
            _flash_error(auth=auth, message="Choose the type of channel to add.")
            return _render_channel_create(auth=auth, kind=None, form_data=form_view, status_code=400)

        name = str(single_form.get("name", "") or "").strip()
        config, secrets, errors = _channel_inputs_from_form(protocol=protocol, form=single_form)
        if len(name) == 0:
            errors["name"] = "Give the channel a name."
        # Check the settings first, without storing anything, so every problem shows at once.
        try:
            prepare_channel_config(fields=protocol.config_fields, kind=kind, config=config, secrets=secrets)
        except ChannelConfigInvalidError as xcpt:
            _add_setting_errors(errors=errors, protocol=protocol, xcpt=xcpt)
        if len(errors) == 0:
            try:
                channel = notification_service.create_channel(
                    db_session=db_session, name=name, kind=kind, scope_level=ChannelScopeLevel.SYSTEM, project_id=None,
                    config=config, actor_user_id=str(auth.user_id), secrets=secrets, principal=_principal_for(auth=auth),
                )
            except ChannelAlreadyExistsError:
                db_session.rollback()
                errors["name"] = "A channel named {} already exists.".format(name)
            except ChannelConfigInvalidError as xcpt:
                db_session.rollback()
                _add_setting_errors(errors=errors, protocol=protocol, xcpt=xcpt)
                if len(errors) == 0:
                    for problem in xcpt.problems:
                        _flash_error(auth=auth, message=problem)
            except ChannelSecretAccessDeniedError as xcpt:
                db_session.rollback()
                _flash_error(auth=auth, message=str(xcpt))
            else:
                return _redirect_with_flash(
                    session=auth.session, url=_channel_url(str(channel.channel_id)),
                    message='Channel "{}" added. Send a test message to check that it works.'.format(channel.name),
                    category=flash.CATEGORY_SUCCESS,
                )
        return _render_channel_create(auth=auth, kind=kind, form_data=form_view, status_code=400, errors=errors)
    finally:
        _close(db_session)


def _load_channel_or_redirect(*, auth: Any, channel_id: str) -> Any:
    """
        The channel, or a redirect to the overview saying it is gone.
    """
    try:
        if rule_validation.is_uuid(channel_id) is False:
            raise ChannelNotFoundError(channel_id)
        channel = notification_service.read_channel(db_session=auth.db_session, channel_id=channel_id)
    except ChannelNotFoundError:
        auth.db_session.rollback()
        return None, _redirect_with_flash(
            session=auth.session, url=_overview_url(), message="That channel no longer exists.", category=flash.CATEGORY_WARNING,
        )
    return channel, None


def handle_channel_detail(request: Request) -> Response:
    """
        ``GET /admin/notifications/channels/{channel_id}``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        channel_id = str(request.path_params.get("channel_id", ""))
        channel, missing = _load_channel_or_redirect(auth=auth, channel_id=channel_id)
        if missing is not None:
            return missing
        protocol = _protocol_for(channel.kind)
        described = notification_service.describe_channel(channel=channel)
        settings: List[Dict[str, Any]] = []
        declared = list(protocol.config_fields) if protocol is not None else []
        by_name = {field.name: field for field in declared}
        for name, value in described["config"].items():
            field = by_name.get(name, None)
            is_secret = field.secret if field is not None else name in described["unprotected_secret_fields"]
            settings.append({
                "name": name,
                "label": field.label if field is not None else name,
                "secret": is_secret,
                "value": value,
                "in_vault": is_secret_ref(value=value),
                "vault_name": secret_name_from_ref(ref=value) if is_secret_ref(value=value) else "",
                "unprotected": name in described["unprotected_secret_fields"],
                "is_mapping": isinstance(value, dict),
            })
        secret_fields = [_field_view(field) for field in declared if field.secret is True]
        using_rules = [
            rule for rule in notification_service.list_routing_rules(db_session=db_session, project_id=None)
            if str(channel.channel_id) in [str(item) for item in (rule.channel_ids or [])]
        ]
        channel_names = {str(channel.channel_id): channel.name}
        deliveries = [
            _delivery_row(attempt=attempt, envelope=envelope, channel_names=channel_names)
            for attempt, envelope in notification_repository.list_recent_deliveries(db_session=db_session, limit=200)
            if str(envelope.channel_id) == str(channel.channel_id)
        ][:10]

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session, request_endpoint="config.notification_channel_detail", flashes=flashes, csrf_token=auth.csrf_token,
        )
        context["channel_id"] = str(channel.channel_id)
        context["channel_name"] = channel.name
        context["kind_label"] = _kind_label(channel.kind)
        context["state"] = "disabled" if channel.disabled is True else "active"
        context["created_at"] = channel.created_at
        context["settings"] = settings
        context["unprotected"] = described["unprotected_secret_fields"]
        context["secret_fields"] = secret_fields
        context["recipient_help"] = protocol.recipient_help if protocol is not None else ""
        context["using_rules"] = [{"rule_id": str(rule.rule_id), "event_label": event_label(rule.event_pattern)} for rule in using_rules]
        context["deliveries"] = deliveries
        context["can_manage"] = _has_permission(auth=auth, permission=NOTIFICATIONS_WRITE_PERMISSION)
        response = _render(template_name="config/notifications/channel_detail.html", context=context)
        _attach_session_to_response(response=response, session=auth.session)
        return response
    finally:
        _close(db_session)


def _post_on_channel(request: Request, *, act: Callable[[Any, Any, Any, Any], Response]) -> Response:
    """
        The shared frame of the POST routes on one channel: sign-in, CSRF, load, then ``act(auth, channel, form, detail_url)``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        channel_id = str(request.path_params.get("channel_id", ""))
        detail_url = _channel_url(channel_id)
        form = _parse_form_or_empty(request=request)
        csrf_redirect = _guard_csrf(auth=auth, form=form, fallback_url=detail_url)
        if csrf_redirect is not None:
            return csrf_redirect
        channel, missing = _load_channel_or_redirect(auth=auth, channel_id=channel_id)
        if missing is not None:
            return missing
        return act(auth, channel, form, detail_url)
    finally:
        _close(db_session)


def handle_channel_test(request: Request) -> Response:
    """
        ``POST /admin/notifications/channels/{channel_id}/test``.
    """
    def act(auth: Any, channel: Any, form: Any, detail_url: str) -> Response:
        recipient = str(form.get("recipient", "") or "").strip()
        if len(recipient) == 0:
            return _redirect_with_flash(
                session=auth.session, url=detail_url, message="Enter who to send the test message to.", category=flash.CATEGORY_ERROR,
            )
        outcome = notification_service.send_test_message(
            db_session=auth.db_session, channel_id=str(channel.channel_id), recipient=recipient, sent_by=str(auth.user_id),
        )
        if outcome.delivered is True:
            return _redirect_with_flash(
                session=auth.session, url=detail_url,
                message="Test message delivered to {} through {} in {} ms.".format(recipient, channel.name, outcome.latency_ms),
                category=flash.CATEGORY_SUCCESS,
            )
        return _redirect_with_flash(
            session=auth.session, url=detail_url,
            message="The test message was not delivered: {}".format(outcome.error_message),
            category=flash.CATEGORY_ERROR,
        )
    return _post_on_channel(request, act=act)


def handle_channel_state(request: Request) -> Response:
    """
        ``POST /admin/notifications/channels/{channel_id}/state`` with ``disabled`` = ``1`` or ``0``.
    """
    def act(auth: Any, channel: Any, form: Any, detail_url: str) -> Response:
        disable = str(form.get("disabled", "") or "") == "1"
        notification_service.update_channel(db_session=auth.db_session, channel_id=str(channel.channel_id), disabled=disable)
        message = (
            'Channel "{}" is off: nothing is sent through it until you turn it on.'.format(channel.name) if disable is True
            else 'Channel "{}" is on.'.format(channel.name)
        )
        return _redirect_with_flash(session=auth.session, url=detail_url, message=message, category=flash.CATEGORY_SUCCESS)
    return _post_on_channel(request, act=act)


def handle_channel_secrets(request: Request) -> Response:
    """
        ``POST /admin/notifications/channels/{channel_id}/secrets`` with ``setting`` and ``value`` (or ``ref``).
    """
    def act(auth: Any, channel: Any, form: Any, detail_url: str) -> Response:
        setting = str(form.get("setting", "") or "").strip()
        value = str(form.get("value", "") or "")
        chosen = str(form.get("ref", "") or "").strip()
        if len(setting) == 0 or (len(value) == 0 and len(chosen) == 0):
            return _redirect_with_flash(
                session=auth.session, url=detail_url, message="Enter the new value to replace the secret with.", category=flash.CATEGORY_ERROR,
            )
        try:
            if len(value) > 0:
                notification_service.update_channel(
                    db_session=auth.db_session, channel_id=str(channel.channel_id), secrets={setting: value}, principal=_principal_for(auth=auth),
                )
            else:
                notification_service.update_channel(
                    db_session=auth.db_session, channel_id=str(channel.channel_id), config={setting: "secret://" + chosen}, principal=_principal_for(auth=auth),
                )
        except ChannelConfigInvalidError as xcpt:
            auth.db_session.rollback()
            return _redirect_with_flash(session=auth.session, url=detail_url, message=" ".join(xcpt.problems), category=flash.CATEGORY_ERROR)
        except ChannelSecretAccessDeniedError as xcpt:
            auth.db_session.rollback()
            return _redirect_with_flash(session=auth.session, url=detail_url, message=str(xcpt), category=flash.CATEGORY_ERROR)
        return _redirect_with_flash(
            session=auth.session, url=detail_url,
            message="The secret was replaced. Send a test message to check that the channel still works.", category=flash.CATEGORY_SUCCESS,
        )
    return _post_on_channel(request, act=act)


def handle_channel_delete(request: Request) -> Response:
    """
        ``POST /admin/notifications/channels/{channel_id}/delete``.
    """
    def act(auth: Any, channel: Any, form: Any, detail_url: str) -> Response:
        name = channel.name
        try:
            notification_service.delete_channel(
                db_session=auth.db_session, channel_id=str(channel.channel_id), principal=_principal_for(auth=auth),
            )
        except ChannelInUseError:
            auth.db_session.rollback()
            return _redirect_with_flash(
                session=auth.session, url=detail_url,
                message="Delete the rules that send through {} first.".format(name), category=flash.CATEGORY_ERROR,
            )
        return _redirect_with_flash(
            session=auth.session, url=_overview_url(),
            message='Channel "{}" deleted, with the secrets stored for it.'.format(name), category=flash.CATEGORY_SUCCESS,
        )
    return _post_on_channel(request, act=act)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _render_rule_create(
        *, auth: Any, form_data: Optional[MultiFormView], status_code: int = 200, errors: Optional[Dict[str, str]] = None
    ) -> HTMLResponse:
    db_session = auth.db_session
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session, request_endpoint="config.notification_rule_create", flashes=flashes, csrf_token=auth.csrf_token,
    )
    channels = notification_service.list_channels(db_session=db_session, scope_level=None, project_id=None)
    context["events"] = [{"topic": topic, "label": label} for topic, label in EVENT_CHOICES]
    context["channels"] = [
        {"channel_id": str(channel.channel_id), "name": channel.name, "kind_label": _kind_label(channel.kind),
         "recipient_help": (_protocol_for(channel.kind).recipient_help if _protocol_for(channel.kind) is not None else ""),
         "disabled": channel.disabled is True}
        for channel in channels
    ]
    context["projects"] = [{"project_id": str(project.project_id), "name": project.display_name} for project in _projects(db_session)]
    context["form_data"] = form_data
    context["errors"] = errors if errors is not None else {}
    context["error_labels"] = {"events": "When", "channel_ids": "Send through", "recipients": "To", "project_id": "Project", "rate_limit_per_minute": "Limit"}
    response = _render(template_name="config/notifications/rule_create.html", context=context, status_code=status_code)
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_rule_create(request: Request) -> Response:
    """
        ``GET|POST /admin/notifications/rules/create``: one rule for each event ticked, each with the message that describes the event.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        if request.method.upper() == "GET":
            return _render_rule_create(auth=auth, form_data=None)

        single_form = _parse_form_or_empty(request=request)
        form_view = MultiFormView(data=_parse_form_multi(request=request))
        csrf_redirect = _guard_csrf(auth=auth, form=single_form, fallback_url=_url_for_module.url_for("config.notification_rule_create"))
        if csrf_redirect is not None:
            return csrf_redirect

        errors: Dict[str, str] = {}
        topics = [topic for topic in form_view.getlist("events") if topic in dict(EVENT_CHOICES)]
        channel_ids = [value for value in form_view.getlist("channel_ids") if len(value.strip()) > 0]
        recipients = [part.strip() for part in str(single_form.get("recipients", "") or "").replace(",", "\n").splitlines() if len(part.strip()) > 0]
        project_id = str(single_form.get("project_id", "") or "").strip() or None
        limit_text = str(single_form.get("rate_limit_per_minute", "") or "").strip()
        rate_limit: Optional[int] = None
        if len(limit_text) > 0:
            try:
                rate_limit = int(limit_text)
            except ValueError:
                errors["rate_limit_per_minute"] = "Enter a whole number of messages per minute, or leave it empty for no limit."
        if len(topics) == 0:
            errors["events"] = "Tick at least one event."
        if len(channel_ids) == 0:
            errors["channel_ids"] = "Choose at least one channel."
        if len(recipients) == 0:
            errors["recipients"] = "Enter at least one recipient."

        created: List[Any] = []
        if len(errors) == 0:
            prepared: List[Dict[str, Any]] = []
            try:
                for topic in topics:
                    template_name = _template_for_topic(topic)
                    if template_name is None:
                        raise RoutingRuleInvalidError("There is no message text for the event \"{}\".".format(dict(EVENT_CHOICES)[topic]))
                    prepared.append(rule_validation.validate_rule_fields(db_session=db_session, payload={
                        "event_pattern": topic, "template_name": template_name, "channel_ids": channel_ids, "recipients": recipients,
                        "project_id": project_id, "rate_limit_per_minute": rate_limit,
                    }))
            except RoutingRuleInvalidError as xcpt:
                db_session.rollback()
                errors[_error_field_for(xcpt)] = xcpt.detail
            else:
                for fields in prepared:
                    created.append(notification_service.create_routing_rule(
                        db_session=db_session, filter_tag_expression=None, actor_user_id=str(auth.user_id), **fields,
                    ))
        if len(created) > 0:
            words = " and ".join(event_label(rule.event_pattern).lower() for rule in created)
            return _redirect_with_flash(
                session=auth.session, url=_overview_url(),
                message="Rule added: send a message when {}. Try the channel's test message to check the route end to end.".format(words),
                category=flash.CATEGORY_SUCCESS,
            )
        return _render_rule_create(auth=auth, form_data=form_view, status_code=400, errors=errors)
    finally:
        _close(db_session)


def _error_field_for(xcpt: RoutingRuleInvalidError) -> str:
    """
        The rule form input a refusal is about.
    """
    extensions = xcpt.extensions or {}
    if "channel_id" in extensions or xcpt.detail.startswith("channel_ids"):
        return "channel_ids"
    if "project_id" in extensions:
        return "project_id"
    if xcpt.detail.startswith("recipients"):
        return "recipients"
    if xcpt.detail.startswith("rate_limit"):
        return "rate_limit_per_minute"
    return "events"


def _is_bad_rule_id(rule_id: str) -> bool:
    """
        Whether a path value cannot be a rule id.
    """
    return rule_validation.is_uuid(rule_id) is False


def _post_on_rule(request: Request, *, act: Callable[[Any, str, Any], Response]) -> Response:
    """
        The shared frame of the POST routes on one rule: sign-in, CSRF, then ``act(auth, rule_id, form)``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        rule_id = str(request.path_params.get("rule_id", ""))
        form = _parse_form_or_empty(request=request)
        csrf_redirect = _guard_csrf(auth=auth, form=form, fallback_url=_overview_url())
        if csrf_redirect is not None:
            return csrf_redirect
        return act(auth, rule_id, form)
    finally:
        _close(db_session)


def handle_rule_state(request: Request) -> Response:
    """
        ``POST /admin/notifications/rules/{rule_id}/state`` with ``disabled`` = ``1`` or ``0``.
    """
    def act(auth: Any, rule_id: str, form: Any) -> Response:
        disable = str(form.get("disabled", "") or "") == "1"
        try:
            if _is_bad_rule_id(rule_id):
                raise ChannelNotFoundError(rule_id)
            notification_service.set_routing_rule_disabled(db_session=auth.db_session, rule_id=rule_id, disabled=disable)
        except ChannelNotFoundError:
            auth.db_session.rollback()
            return _redirect_with_flash(session=auth.session, url=_overview_url(), message="That rule no longer exists.", category=flash.CATEGORY_WARNING)
        message = "The rule is off: it sends nothing until you turn it on." if disable is True else "The rule is on."
        return _redirect_with_flash(session=auth.session, url=_overview_url(), message=message, category=flash.CATEGORY_SUCCESS)
    return _post_on_rule(request, act=act)


def handle_rule_delete(request: Request) -> Response:
    """
        ``POST /admin/notifications/rules/{rule_id}/delete``.
    """
    def act(auth: Any, rule_id: str, form: Any) -> Response:
        try:
            if _is_bad_rule_id(rule_id):
                raise ChannelNotFoundError(rule_id)
            notification_service.delete_routing_rule(db_session=auth.db_session, rule_id=rule_id)
        except ChannelNotFoundError:
            auth.db_session.rollback()
            return _redirect_with_flash(session=auth.session, url=_overview_url(), message="That rule no longer exists.", category=flash.CATEGORY_WARNING)
        return _redirect_with_flash(session=auth.session, url=_overview_url(), message="Rule deleted.", category=flash.CATEGORY_SUCCESS)
    return _post_on_rule(request, act=act)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "config.notifications_overview": handle_notifications_overview,
    "config.notification_channel_create": handle_channel_create,
    "config.notification_channel_detail": handle_channel_detail,
    "config.notification_channel_test": handle_channel_test,
    "config.notification_channel_state": handle_channel_state,
    "config.notification_channel_secrets": handle_channel_secrets,
    "config.notification_channel_delete": handle_channel_delete,
    "config.notification_rule_create": handle_rule_create,
    "config.notification_rule_state": handle_rule_state,
    "config.notification_rule_delete": handle_rule_delete,
}


def register_notifications_routes(*, app: Any) -> None:
    """
        Attach the Notifications admin routes to a webworks app.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = CONFIG_PATH + relative_path
        _url_for_module.register_endpoint(endpoint=endpoint_name, pattern=full_path)
        wrapped_handler = _require_admin_permission_for(
            _wrap_admin_handler_in_shell(_HANDLERS_BY_ENDPOINT[endpoint_name]),
            permission=_ROUTE_PERMISSIONS[endpoint_name],
        )
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_notifications_routes",
    "event_label",
    "handle_notifications_overview",
    "handle_channel_create",
    "handle_channel_detail",
    "handle_channel_test",
    "handle_channel_state",
    "handle_channel_secrets",
    "handle_channel_delete",
    "handle_rule_create",
    "handle_rule_state",
    "handle_rule_delete",
]
