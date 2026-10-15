"""
.. module:: notifications.router
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Turn a bus event into deliveries through the routing rules (ORG-F08).

.. moduleauthor:: Code Craft AI LLC

The notification service could render a template and send it (``dispatch_envelope``)
and store routing rules, but nothing connected the two: no run failure ever
produced a message. This module is the missing middle. Given an event topic and
payload it finds the enabled rules that apply (the rule's project, or every project
when the rule names none, and an event pattern that matches the topic), and for each
rule delivers one message per ``(channel, recipient)`` through
:func:`~ccai.pychestrate.webservice.notifications.service.dispatch_envelope`.

A delivery that cannot be made (a disabled or missing channel, an unknown template,
a channel that reports failure) is recorded and reported in the result; it never stops
the other deliveries and never raises to the caller, because the caller is a background
worker reacting to a run that has already ended.

M1 of ``specs/2-notification-hub`` (T1.7, T1.8): event-pattern globs and a per-rule
rate limit; tag filters, per-user preferences, quiet hours and digests are M2.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import fnmatch
import logging
import threading
import time

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.notifications import repository as notification_repository
from ccai.pychestrate.webservice.notifications import service as notification_service


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Route:
    """
        One delivery a rule asks for.

        :ivar rule_id: The rule that asked for it.
        :ivar template_name: The template to render.
        :ivar channel_id: The channel to send through.
        :ivar recipient: The address (an email address, a URL, ...).
    """
    rule_id: str
    template_name: str
    channel_id: str
    recipient: str


@dataclass(frozen=True)
class RouteOutcome:
    """
        What became of one :class:`Route`.

        :ivar route: The delivery.
        :ivar delivered: ``True`` when the channel reported success.
        :ivar skipped_reason: Why nothing was sent (``rate_limited``, ``channel_disabled``,
                              ``template_not_for_event``), or "".
        :ivar error: The failure, as ``ExceptionType: message``, or "".
    """
    route: Route
    delivered: bool
    skipped_reason: str = ""
    error: str = ""


def pattern_matches(*, pattern: str, topic: str) -> bool:
    """
        Whether an event pattern covers a topic. A pattern is a topic (``entity.run.failed``)
        or a glob over topics (``entity.run.*``); matching is case-sensitive.

        :param pattern: The rule's ``event_pattern``.
        :param topic: The event's topic.

        :returns: ``True`` when the topic matches.
    """
    rtnval = fnmatch.fnmatchcase(topic, pattern.strip())
    return rtnval


def compute_routes(*, rules: List[Any], topic: str, project_id: Optional[str]) -> List[Route]:
    """
        The deliveries the rules ask for an event: every enabled rule whose project is the
        event's (or that names none) and whose pattern matches the topic yields one route
        per channel and recipient.

        :param rules: :class:`NotificationRoutingRule` rows (or objects with the same fields).
        :param topic: The event's topic.
        :param project_id: The project the event belongs to, or ``None``.

        :returns: The routes, in rule order.
    """
    wanted = str(project_id) if project_id is not None else None
    rtnval: List[Route] = []
    for rule in rules:
        if bool(rule.disabled) is True:
            continue
        rule_project = str(rule.project_id) if rule.project_id is not None else None
        if rule_project is not None and rule_project != wanted:
            continue
        if pattern_matches(pattern=str(rule.event_pattern), topic=topic) is False:
            continue
        for channel_id in list(rule.channel_ids or []):
            for recipient in list(rule.recipients or []):
                rtnval.append(Route(
                    rule_id=str(rule.rule_id), template_name=str(rule.template_name),
                    channel_id=str(channel_id), recipient=str(recipient),
                ))
    return rtnval


class RuleRateLimiter:
    """
        At most ``per_minute`` deliveries per rule in any sliding minute (a rule with no
        limit is never limited). In memory and per process: a rule's budget is per worker,
        which is what protects a recipient from one worker's alert storm; the spec's
        per-recipient digest is M2.
    """

    def __init__(self, *, clock: Any = None) -> None:
        self._clock = clock if clock is not None else time.monotonic
        self._lock = threading.Lock()
        self._sent: Dict[str, Deque[float]] = {}

    def allow(self, *, rule_id: str, per_minute: Optional[int]) -> bool:
        """
            Record a delivery for ``rule_id`` and say whether it is within its limit.

            :param rule_id: The rule.
            :param per_minute: The rule's ``rate_limit_per_minute`` (``None`` or less than 1: no limit).

            :returns: ``False`` when the rule has already had its share this minute.
        """
        if per_minute is None or per_minute < 1:
            return True
        now = float(self._clock())
        with self._lock:
            window = self._sent.setdefault(rule_id, deque())
            while len(window) > 0 and now - window[0] >= 60.0:
                window.popleft()
            if len(window) >= per_minute:
                return False
            window.append(now)
        return True


def route_event(
        *,
        db_session: DbSession,
        topic: str,
        payload: Mapping[str, Any],
        limiter: Optional[RuleRateLimiter] = None
    ) -> List[RouteOutcome]:
    """
        Deliver an event to everything its rules ask for.

        :param db_session: A session for the routing rules, the channels and the delivery records.
        :param topic: The event's topic.
        :param payload: The template payload (``run_id``, ``project_slug``, ``reason``, ...);
                        ``project_id`` in it selects the project's rules.
        :param limiter: The rate limiter to consult; a fresh one when ``None`` (no memory of earlier calls).

        :returns: One :class:`RouteOutcome` per delivery asked for; empty when no rule applies.
    """
    limits = limiter if limiter is not None else RuleRateLimiter()
    rules = notification_repository.list_routing_rules(db_session=db_session, project_id=None)
    routes = compute_routes(rules=rules, topic=topic, project_id=payload.get("project_id", None))
    per_minute = {str(rule.rule_id): rule.rate_limit_per_minute for rule in rules}

    outcomes: List[RouteOutcome] = []
    for route in routes:
        if limits.allow(rule_id=route.rule_id, per_minute=per_minute.get(route.rule_id, None)) is False:
            _LOGGER.info("pychestrate.notifications.rate_limited: rule=%s recipient=%s", route.rule_id, route.recipient)
            outcomes.append(RouteOutcome(route=route, delivered=False, skipped_reason="rate_limited"))
            continue
        try:
            template = notification_service._resolve_template(template_name=route.template_name)
            if template.is_test_message is True or (len(template.event_topics) > 0 and topic not in template.event_topics):
                outcomes.append(RouteOutcome(route=route, delivered=False, skipped_reason="template_not_for_event"))
                continue
            channel = notification_service.read_channel(db_session=db_session, channel_id=route.channel_id)
            if bool(channel.disabled) is True:
                outcomes.append(RouteOutcome(route=route, delivered=False, skipped_reason="channel_disabled"))
                continue
            notification_service.dispatch_envelope(
                db_session=db_session, channel_id=route.channel_id, recipient=route.recipient,
                event_topic=topic, template_name=route.template_name, payload=payload,
            )
            outcomes.append(RouteOutcome(route=route, delivered=True))
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as xcpt:  # noqa: BLE001 -- ccai errors are BaseException subclasses
            failure = "{}: {}".format(type(xcpt).__name__, xcpt)
            _LOGGER.error(
                "pychestrate.notifications.delivery_failed: rule=%s channel=%s recipient=%s error=%s",
                route.rule_id, route.channel_id, route.recipient, failure.replace("\n", " | "),
            )
            try:
                db_session.rollback()
            except Exception:  # noqa: BLE001
                pass
            outcomes.append(RouteOutcome(route=route, delivered=False, error=failure))
    return outcomes


__all__ = [
    "Route",
    "RouteOutcome",
    "RuleRateLimiter",
    "compute_routes",
    "pattern_matches",
    "route_event",
]
