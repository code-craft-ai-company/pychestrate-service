"""
.. module:: audit.bus_subscriber
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bridges entity.* topics into audit capture calls.

.. moduleauthor:: Code Craft AI LLC

The subscriber registers one callback per ``source_topic`` declared by an
``AuditEventTypeExtension``. When the in-process bus delivers an event,
the subscriber invokes :func:`capture_event` against the caller-supplied
session factory. The session factory is injected so the subscriber stays
testable without importing the request context directly.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.audit.audit_writer import capture_event
from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension
from ccai.pychestrate.webservice.extensions.registry import list_resource_extensions
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent, subscribe


SessionFactory = Callable[[], DbSession]


def wire_bus_subscribers(*, session_factory: SessionFactory) -> None:
    """
        Register a subscriber for every known ``source_topic`` in the
        registered audit event catalog. The handler runs inside a fresh
        session produced by ``session_factory`` so the audit insert lands
        outside the originating request's transaction.

        :param session_factory: Callable returning a new SQLAlchemy session.

        :returns: None.
    """
    packs = list_resource_extensions(base_class=AuditEventTypeExtension)
    topic_to_kind: Dict[str, str] = {}
    topic_to_actor_keys: Dict[str, Tuple[str, ...]] = {}
    for pack in packs:
        # Producers that capture the record inline (secrets_service)
        # publish the topic for other subscribers only; capturing it
        # here as well wrote every such event twice.
        if bool(getattr(pack, "captured_inline", False)) is True:
            continue
        topic_to_kind[pack.source_topic] = pack.kind
        topic_to_actor_keys[pack.source_topic] = tuple(
            getattr(pack, "actor_payload_keys", ("actor_user_id",))
        )

    # Rows a signed-in user changes in the web UI's core.orm stores
    # reach the audit log through the data-change bridge's
    # ``entity.data.*`` events (see audit.data_change_bridge).
    from ccai.pychestrate.webservice.audit.data_change_bridge import (  # noqa: E402
        install_data_change_bridge,
    )
    install_data_change_bridge()

    for topic, kind in topic_to_kind.items():
        # Idempotent: the phase-1 and phase-2 bootstraps both call this
        # (the phase-2 pass picks up audit kinds registered after phase
        # 1). Wiring a topic twice would insert every audit record twice
        # and the second insert violates the ``source_event_id`` unique
        # constraint, so a topic whose handler is still subscribed is
        # skipped. A bus reset (tests) drops the handler and the topic
        # is wired again.
        # The guard is keyed by (topic, session factory): the same
        # factory wired twice is a no-op, while a test harness that
        # supplies its own factory still gets a handler writing to its
        # database.
        already = False
        for wired_factory, wired_handler in _WIRED_HANDLERS.get(topic, []):
            if wired_factory is session_factory and _is_subscribed(topic=topic, subscriber=wired_handler):
                already = True
                break
        if already:
            continue
        handler = _build_handler(
            session_factory=session_factory,
            kind=kind,
            topic=topic,
            actor_payload_keys=topic_to_actor_keys.get(topic, ("actor_user_id",)),
        )
        subscribe(topic=topic, subscriber=handler)
        _WIRED_HANDLERS.setdefault(topic, []).append((session_factory, handler))

    return


#: ``topic -> [(session_factory, handler), ...]`` for every subscriber
#: this module has wired.
_WIRED_HANDLERS: Dict[str, List[Tuple[Any, Callable[[EntityEvent], None]]]] = {}


def _is_subscribed(*, topic: str, subscriber: Callable[[EntityEvent], None]) -> bool:
    """
        Whether ``subscriber`` is currently registered on the bus for
        ``topic``. Falls back to ``False`` (re-wire) when the bus does not
        expose its registry.
    """
    try:
        from ccai.pychestrate.webservice.messaging import event_bus as _bus  # noqa: E402
        registry = getattr(_bus, "_SUBSCRIBERS", None)
        if registry is None:
            return False
        bucket = registry.get(topic, [])
        rtnval = any(candidate is subscriber for candidate in bucket)
        return rtnval
    except Exception:
        return False


def unwire_bus_subscribers(*, session_factory: SessionFactory) -> int:
    """
        Unsubscribe every handler :func:`wire_bus_subscribers` wired for
        ``session_factory`` (the inverse of wiring; lets a caller that
        wired a private store detach it again).

        :param session_factory: The factory the handlers were wired with.

        :returns: Number of handlers removed.
    """
    from ccai.pychestrate.webservice.messaging.event_bus import unsubscribe  # noqa: E402

    removed = 0
    for topic in list(_WIRED_HANDLERS.keys()):
        kept: List[Tuple[Any, Callable[[EntityEvent], None]]] = []
        for wired_factory, wired_handler in _WIRED_HANDLERS[topic]:
            if wired_factory is session_factory:
                unsubscribe(topic=topic, subscriber=wired_handler)
                removed = removed + 1
            else:
                kept.append((wired_factory, wired_handler))
        _WIRED_HANDLERS[topic] = kept
    rtnval = removed
    return rtnval


def reset_wiring_for_testing() -> None:
    """
        Forget every handler this module wired (tests reset the bus too).
    """
    _WIRED_HANDLERS.clear()
    return


_MAX_SERVICE_IDENTITY_LENGTH: int = 128
_MAX_TARGET_REF_LENGTH: int = 256


def resolve_event_actor(
        *,
        payload: Dict[str, Any],
        actor_payload_keys: Tuple[str, ...]
    ) -> Tuple[Optional[str], Optional[str]]:
    """
        Find the acting principal of an event. The first non-empty
        value among ``actor_payload_keys`` wins: a UUID is a user and
        becomes ``actor_user_id``; anything else (``extension:...``,
        ``system:rpa``) is a service identity. RPA and UI-profile
        events carry ``actor_id``, not ``actor_user_id``, which is why
        their records had no actor.

        :param payload: The event payload.
        :param actor_payload_keys: Keys to try, in order.

        :returns: ``(actor_user_id, actor_service_identity)``.
    """
    for key in actor_payload_keys:
        value = payload.get(key, None)
        if value is None:
            continue
        text = str(value).strip()
        if len(text) == 0:
            continue
        try:
            rtnval = (str(uuid.UUID(text)), None)
        except ValueError:
            rtnval = (None, text[:_MAX_SERVICE_IDENTITY_LENGTH])
        return rtnval
    return (None, None)


def _resolve_target_ref(*, payload: Dict[str, Any]) -> Optional[str]:
    """
        The record's target reference: the payload's ``target_ref`` when
        present, else ``<table>:<id>`` for data-change events, else
        ``user:<id>`` / ``secret:<ref>`` style references for the
        identity and secret events.

        :param payload: The event payload.

        :returns: Target reference or None.
    """
    explicit = payload.get("target_ref", None)
    if explicit is not None:
        rtnval = str(explicit)[:_MAX_TARGET_REF_LENGTH]
        return rtnval
    candidates = (
        ("table", "entity_id"),
        ("principal_kind", "principal_id"),
    )
    for kind_key, id_key in candidates:
        kind_value = payload.get(kind_key, None)
        id_value = payload.get(id_key, None)
        if kind_value is not None and id_value is not None:
            rtnval = "{}:{}".format(str(kind_value).lower(), id_value)[:_MAX_TARGET_REF_LENGTH]
            return rtnval
    simple_refs = (
        ("user_id", "user"),
        ("role_id", "role"),
        ("session_id", "session"),
        ("secret_ref", "secret"),
        ("project_id", "project"),
        ("job_id", "job"),
        ("type_id", "rpa_job_type"),
        ("login_name", "login"),
    )
    for id_key, prefix in simple_refs:
        id_value = payload.get(id_key, None)
        if id_value is not None:
            rtnval = "{}:{}".format(prefix, id_value)[:_MAX_TARGET_REF_LENGTH]
            return rtnval
    return None


def _build_handler(
        *,
        session_factory: SessionFactory,
        kind: str,
        topic: str,
        actor_payload_keys: Tuple[str, ...] = ("actor_user_id",)
    ):
    """
        Return a closure that captures the event into audit under the given kind.

        :param session_factory: Callable returning a new SQLAlchemy session.
        :param kind: Audit kind registered for ``topic``.
        :param topic: Originating bus topic.
        :param actor_payload_keys: Payload keys naming the actor.

        :returns: A callable suitable for :func:`subscribe`.
    """

    def _handler(event: EntityEvent) -> None:
        session = session_factory()
        try:
            payload = dict(event.payload)
            actor_user_id, actor_service_identity = resolve_event_actor(
                payload=payload, actor_payload_keys=actor_payload_keys
            )
            target_ref = _resolve_target_ref(payload=payload)
            capture_event(
                db_session=session,
                source_event_id=event.source_event_id,
                source_topic=topic,
                kind=kind,
                actor_user_id=actor_user_id,
                actor_service_identity=actor_service_identity,
                target_ref=target_ref,
                payload=payload,
            )
            session.commit()
        finally:
            session.close()
        return

    return _handler
