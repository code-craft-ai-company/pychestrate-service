"""
.. module:: notifications.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Repository for notification aggregate rows.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.notifications.models import (
    ChannelScopeLevel,
    NotificationChannel,
    NotificationDeadLetter,
    NotificationDispatchAttempt,
    NotificationDispatchEnvelope,
    NotificationRoutingRule,
    UserNotificationPreferences,
)


def insert_channel(*, db_session: DbSession, channel: NotificationChannel) -> NotificationChannel:
    """
        Persist a new :class:`NotificationChannel` row.

        :param db_session: Active SQLAlchemy session.
        :param channel: The channel to persist.

        :returns: The persisted row.
    """
    db_session.add(channel)
    db_session.flush()
    rtnval = channel
    return rtnval


def get_channel_by_id(
        *,
        db_session: DbSession,
        channel_id: str
    ) -> Optional[NotificationChannel]:
    """
        Look up a channel by id.

        :param db_session: Active SQLAlchemy session.
        :param channel_id: Target channel id.

        :returns: The :class:`NotificationChannel` or None.
    """
    rtnval = (
        db_session.query(NotificationChannel)
        .filter(NotificationChannel.channel_id == channel_id)
        .first()
    )
    return rtnval


def get_channel_by_name(
        *,
        db_session: DbSession,
        scope_level: ChannelScopeLevel,
        project_id: Optional[str],
        name: str
    ) -> Optional[NotificationChannel]:
    """
        Look up a channel by its scope + name uniqueness key.

        :param db_session: Active SQLAlchemy session.
        :param scope_level: SYSTEM or PROJECT.
        :param project_id: Project id when scope_level=PROJECT, else None.
        :param name: Channel name.

        :returns: The :class:`NotificationChannel` or None.
    """
    query = db_session.query(NotificationChannel).filter(
        NotificationChannel.scope_level == scope_level
    )
    if project_id is None:
        query = query.filter(NotificationChannel.project_id.is_(None))
    else:
        query = query.filter(NotificationChannel.project_id == project_id)

    query = query.filter(NotificationChannel.name == name)

    rtnval = query.first()
    return rtnval


def list_channels(
        *,
        db_session: DbSession,
        scope_level: Optional[ChannelScopeLevel],
        project_id: Optional[str]
    ) -> List[NotificationChannel]:
    """
        Return channels filtered by scope.

        :param db_session: Active SQLAlchemy session.
        :param scope_level: Optional scope filter.
        :param project_id: Optional project filter.

        :returns: List of :class:`NotificationChannel`.
    """
    query = db_session.query(NotificationChannel)
    if scope_level is not None:
        query = query.filter(NotificationChannel.scope_level == scope_level)
    if project_id is not None:
        query = query.filter(NotificationChannel.project_id == project_id)

    query = query.order_by(NotificationChannel.created_at.asc())

    rtnval = query.all()
    return rtnval


def insert_envelope(
        *,
        db_session: DbSession,
        envelope: NotificationDispatchEnvelope
    ) -> NotificationDispatchEnvelope:
    """
        Persist a dispatch envelope.

        :param db_session: Active SQLAlchemy session.
        :param envelope: The envelope to persist.

        :returns: The persisted row.
    """
    db_session.add(envelope)
    db_session.flush()
    rtnval = envelope
    return rtnval


def insert_routing_rule(
        *,
        db_session: DbSession,
        rule: NotificationRoutingRule
    ) -> NotificationRoutingRule:
    """
        Persist a routing rule.
    """
    db_session.add(rule)
    db_session.flush()
    rtnval = rule
    return rtnval


def get_routing_rule(
        *,
        db_session: DbSession,
        rule_id: str
    ) -> Optional[NotificationRoutingRule]:
    """
        Look up a routing rule by id.
    """
    rtnval = (
        db_session.query(NotificationRoutingRule)
        .filter(NotificationRoutingRule.rule_id == rule_id)
        .first()
    )
    return rtnval


def list_routing_rules(
        *,
        db_session: DbSession,
        project_id: Optional[str]
    ) -> List[NotificationRoutingRule]:
    """
        List routing rules, optionally filtered by project id.
    """
    query = db_session.query(NotificationRoutingRule)
    if project_id is not None:
        query = query.filter(NotificationRoutingRule.project_id == project_id)
    query = query.order_by(NotificationRoutingRule.created_at.asc())
    rtnval = query.all()
    return rtnval


def delete_routing_rule(
        *,
        db_session: DbSession,
        rule: NotificationRoutingRule
    ) -> None:
    """
        Remove a routing rule.
    """
    db_session.delete(rule)
    db_session.flush()
    return


def upsert_user_preferences(
        *,
        db_session: DbSession,
        preferences: UserNotificationPreferences
    ) -> UserNotificationPreferences:
    """
        Insert or update the per-user preferences row.
    """
    db_session.merge(preferences)
    db_session.flush()
    rtnval = preferences
    return rtnval


def get_user_preferences(
        *,
        db_session: DbSession,
        user_id: str
    ) -> Optional[UserNotificationPreferences]:
    """
        Look up a user's preferences row.
    """
    rtnval = (
        db_session.query(UserNotificationPreferences)
        .filter(UserNotificationPreferences.user_id == user_id)
        .first()
    )
    return rtnval


def park_dead_letter(
        *,
        db_session: DbSession,
        dead_letter: NotificationDeadLetter
    ) -> NotificationDeadLetter:
    """
        Write or merge a dead-letter row.
    """
    db_session.merge(dead_letter)
    db_session.flush()
    rtnval = dead_letter
    return rtnval


def get_dead_letter(
        *,
        db_session: DbSession,
        envelope_id: str
    ) -> Optional[NotificationDeadLetter]:
    """
        Look up a dead-letter row.
    """
    rtnval = (
        db_session.query(NotificationDeadLetter)
        .filter(NotificationDeadLetter.envelope_id == envelope_id)
        .first()
    )
    return rtnval


def list_dead_letters(
        *,
        db_session: DbSession,
        offset: int,
        limit: int
    ) -> List[NotificationDeadLetter]:
    """
        Paginate dead-letter rows.
    """
    query = db_session.query(NotificationDeadLetter).order_by(
        NotificationDeadLetter.parked_at.asc()
    )
    rtnval = query.offset(offset).limit(limit).all()
    return rtnval


def delete_dead_letter(
        *,
        db_session: DbSession,
        dead_letter: NotificationDeadLetter
    ) -> None:
    """
        Remove a dead-letter row.
    """
    db_session.delete(dead_letter)
    db_session.flush()
    return


def insert_attempt(
        *,
        db_session: DbSession,
        attempt: NotificationDispatchAttempt
    ) -> NotificationDispatchAttempt:
    """
        Persist a dispatch attempt.

        :param db_session: Active SQLAlchemy session.
        :param attempt: The attempt to persist.

        :returns: The persisted row.
    """
    db_session.add(attempt)
    db_session.flush()
    rtnval = attempt
    return rtnval


def latest_attempt_for_channel(
        *,
        db_session: DbSession,
        channel_id: str
    ) -> Optional[NotificationDispatchAttempt]:
    """
        The most recent delivery attempt made through a channel.

        :param db_session: Active SQLAlchemy session.
        :param channel_id: The channel.

        :returns: The attempt, or None when nothing was ever sent through it.
    """
    rtnval = (
        db_session.query(NotificationDispatchAttempt)
        .join(
            NotificationDispatchEnvelope,
            NotificationDispatchEnvelope.envelope_id == NotificationDispatchAttempt.envelope_id,
        )
        .filter(NotificationDispatchEnvelope.channel_id == channel_id)
        .order_by(NotificationDispatchAttempt.attempted_at.desc())
        .first()
    )
    return rtnval


def list_recent_deliveries(
        *,
        db_session: DbSession,
        limit: int
    ) -> List[Tuple[NotificationDispatchAttempt, NotificationDispatchEnvelope]]:
    """
        The most recent delivery attempts across all channels, newest first.

        :param db_session: Active SQLAlchemy session.
        :param limit: How many to return.

        :returns: ``(attempt, envelope)`` pairs.
    """
    rows = (
        db_session.query(NotificationDispatchAttempt, NotificationDispatchEnvelope)
        .join(
            NotificationDispatchEnvelope,
            NotificationDispatchEnvelope.envelope_id == NotificationDispatchAttempt.envelope_id,
        )
        .order_by(NotificationDispatchAttempt.attempted_at.desc())
        .limit(int(limit))
        .all()
    )
    rtnval = [(attempt, envelope) for attempt, envelope in rows]
    return rtnval


def delete_channel_history(
        *,
        db_session: DbSession,
        channel_id: str
    ) -> int:
    """
        Remove every message recorded through a channel: its envelopes, their attempts and their dead letters. A database that enforces the
        foreign keys cascades these anyway when the channel goes; SQLite does not, and would leave dead letters that can never be replayed.

        :param db_session: Active SQLAlchemy session.
        :param channel_id: The channel.

        :returns: How many envelopes were removed.
    """
    envelope_ids = [
        row[0] for row in db_session.query(NotificationDispatchEnvelope.envelope_id)
        .filter(NotificationDispatchEnvelope.channel_id == channel_id).all()
    ]
    if len(envelope_ids) == 0:
        return 0
    db_session.query(NotificationDeadLetter).filter(NotificationDeadLetter.envelope_id.in_(envelope_ids)).delete(synchronize_session=False)
    db_session.query(NotificationDispatchAttempt).filter(NotificationDispatchAttempt.envelope_id.in_(envelope_ids)).delete(synchronize_session=False)
    db_session.query(NotificationDispatchEnvelope).filter(NotificationDispatchEnvelope.envelope_id.in_(envelope_ids)).delete(synchronize_session=False)
    rtnval = len(envelope_ids)
    return rtnval
