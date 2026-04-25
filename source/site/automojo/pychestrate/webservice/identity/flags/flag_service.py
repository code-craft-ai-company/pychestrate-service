"""
.. module:: identity.flags.flag_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Feature-flag lifecycle API.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.identity.flags.events import FlagEventTopics
from automojo.pychestrate.webservice.identity.flags.exceptions import (
    FlagAlreadyExistsError,
    FlagAlreadyRetiredError,
    FlagKindImmutableError,
    FlagNotFoundError,
    FlagValueInvalidError,
)
from automojo.pychestrate.webservice.identity.flags.models import (
    FeatureFlag,
    FeatureFlagVersion,
    FlagKind,
    FlagState,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


DEFAULT_RETIRE_GRACE = timedelta(days=14)


def validate_value_for_kind(
        *,
        flag_kind: FlagKind,
        value: Any,
        rules: Optional[Dict] = None
    ) -> None:
    """
        Confirm that ``value`` matches ``flag_kind``.

        :raises: FlagValueInvalidError on mismatch;
                 SemanticError on an unrecognized kind.
    """
    if flag_kind == FlagKind.BOOLEAN:
        if not isinstance(value, bool):
            err_lines = ["Boolean flag value must be a Python bool."]
            err_lines.append("VALUE: {!r}".format(value))
            err_msg = os.linesep.join(err_lines)
            raise FlagValueInvalidError(err_msg) from None
        return
    if flag_kind == FlagKind.STRING:
        if not isinstance(value, str):
            err_lines = ["String flag value must be a Python str."]
            err_lines.append("VALUE: {!r}".format(value))
            err_msg = os.linesep.join(err_lines)
            raise FlagValueInvalidError(err_msg) from None
        return
    if flag_kind == FlagKind.ENUM:
        if not isinstance(value, str):
            err_lines = ["Enum flag value must be a Python str."]
            err_lines.append("VALUE: {!r}".format(value))
            err_msg = os.linesep.join(err_lines)
            raise FlagValueInvalidError(err_msg) from None
        choices: List[str] = []
        if rules is not None and isinstance(rules, dict):
            raw = rules.get("choices", [])
            if isinstance(raw, list):
                choices = [str(c) for c in raw]
        if len(choices) == 0:
            err_lines = [
                "Enum flag rules must declare a non-empty 'choices' list.",
            ]
            err_msg = os.linesep.join(err_lines)
            raise FlagValueInvalidError(err_msg) from None
        if value not in choices:
            err_lines = ["Enum flag value is not in the declared choices."]
            err_lines.append("VALUE: {!r}".format(value))
            err_lines.append("CHOICES: {}".format(", ".join(choices)))
            err_msg = os.linesep.join(err_lines)
            raise FlagValueInvalidError(err_msg) from None
        return
    if flag_kind == FlagKind.PERCENTAGE:
        # PERCENTAGE flags carry a bool default; the rollout
        # cutoff lives in rules['rollout_percentage_bp']. The
        # bucket-based decision is what makes them PERCENTAGE
        # rather than BOOLEAN; the value contract is the same.
        if not isinstance(value, bool):
            err_lines = [
                "Percentage flag default_value must be a Python bool.",
            ]
            err_lines.append("VALUE: {!r}".format(value))
            err_msg = os.linesep.join(err_lines)
            raise FlagValueInvalidError(err_msg) from None
        if rules is not None and isinstance(rules, dict):
            cutoff = rules.get("rollout_percentage_bp")
            if cutoff is not None:
                if isinstance(cutoff, bool):
                    err_lines = [
                        "rollout_percentage_bp must be an integer.",
                    ]
                    err_msg = os.linesep.join(err_lines)
                    raise FlagValueInvalidError(err_msg) from None
                if not isinstance(cutoff, int):
                    err_lines = [
                        "rollout_percentage_bp must be an integer.",
                    ]
                    err_lines.append("VALUE: {!r}".format(cutoff))
                    err_msg = os.linesep.join(err_lines)
                    raise FlagValueInvalidError(err_msg) from None
                if cutoff < 0 or cutoff > 10000:
                    err_lines = [
                        "rollout_percentage_bp must be in [0, 10000].",
                    ]
                    err_lines.append("VALUE: {!r}".format(cutoff))
                    err_msg = os.linesep.join(err_lines)
                    raise FlagValueInvalidError(err_msg) from None
        return
    err_lines = ["Unrecognized FlagKind in validate_value_for_kind."]
    err_lines.append("KIND: {!r}".format(flag_kind))
    err_msg = os.linesep.join(err_lines)
    raise SemanticError(err_msg) from None


def create_flag(
        *,
        db_session: DbSession,
        flag_key: str,
        flag_kind: FlagKind,
        default_value: Any,
        rules: Optional[Dict],
        actor_user_id: Optional[str]
    ) -> FeatureFlag:
    """
        Persist a new flag at version 1 and publish ``entity.flag.created``.

        :param db_session: Active SQLAlchemy session.
        :param flag_key: Unique flag key.
        :param flag_kind: :class:`FlagKind` for this flag.
        :param default_value: Encoded default value for the kind.
        :param rules: Rules payload (may be None — stored as empty dict).
        :param actor_user_id: Acting principal for audit attribution.

        :returns: The persisted :class:`FeatureFlag`.
        :raises: FlagAlreadyExistsError
    """
    existing = db_session.query(FeatureFlag).filter(FeatureFlag.flag_key == flag_key).first()
    if existing is not None:
        err_msg_lines = ["Cannot create feature flag — key already exists."]
        err_msg_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg = os.linesep.join(err_msg_lines)
        raise FlagAlreadyExistsError(err_msg) from None

    validate_value_for_kind(
        flag_kind=flag_kind, value=default_value, rules=rules,
    )

    now = utc_now()
    flag = FeatureFlag(
        flag_key=flag_key,
        flag_kind=flag_kind,
        current_version=1,
        state=FlagState.ACTIVE,
        retired_at=None,
        grace_expires_at=None,
        owner_user_id=actor_user_id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(flag)
    db_session.flush()

    rules_payload: Dict = {}
    if rules is not None:
        rules_payload = dict(rules)

    version = FeatureFlagVersion(
        version_id=new_uuid(),
        flag_key=flag_key,
        version=1,
        default_value=default_value,
        rules_json=rules_payload,
        created_at=now,
        created_by=actor_user_id,
    )
    db_session.add(version)
    db_session.flush()

    payload = {
        "flag_key": flag_key,
        "version": 1,
        "default_value": default_value,
        "actor_user_id": actor_user_id,
        "created_at": now.isoformat(),
    }
    event = EntityEvent(
        topic=FlagEventTopics.FLAG_CREATED,
        payload=payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=event)

    db_session.commit()

    rtnval = flag
    return rtnval


def update_flag_rules(
        *,
        db_session: DbSession,
        flag_key: str,
        default_value: Any,
        rules: Optional[Dict],
        actor_user_id: Optional[str],
        flag_kind: Optional[FlagKind] = None
    ) -> FeatureFlag:
    """
        Bump a flag's ``current_version``, persist a fresh
        :class:`FeatureFlagVersion` row, and emit
        :data:`FlagEventTopics.FLAG_UPDATED`. The flag's
        ``flag_kind`` is part of its identity contract and
        cannot change post-creation.

        :param flag_kind: Optional caller-supplied kind. When
                          provided, the helper raises
                          :class:`FlagKindImmutableError`
                          unless it matches the persisted kind.

        :raises: FlagNotFoundError on miss;
                 FlagKindImmutableError on attempted kind
                 change; FlagValueInvalidError on a value
                 that does not match the persisted kind;
                 SemanticError when the flag is past ACTIVE.
    """
    flag = (
        db_session.query(FeatureFlag)
        .filter(FeatureFlag.flag_key == flag_key)
        .first()
    )
    if flag is None:
        err_lines = ["Cannot update feature flag — key not found."]
        err_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg = os.linesep.join(err_lines)
        raise FlagNotFoundError(err_msg) from None
    if flag.state != FlagState.ACTIVE:
        err_lines = [
            "Cannot update feature flag — state is past ACTIVE.",
        ]
        err_lines.append("FLAG_KEY: {}".format(flag_key))
        err_lines.append("STATE: {}".format(flag.state.value))
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None
    if flag_kind is not None and flag_kind != flag.flag_kind:
        err_lines = ["Feature flag kind cannot change post-creation."]
        err_lines.append("FLAG_KEY: {}".format(flag_key))
        err_lines.append("CURRENT: {}".format(flag.flag_kind.value))
        err_lines.append("REQUESTED: {}".format(flag_kind.value))
        err_msg = os.linesep.join(err_lines)
        raise FlagKindImmutableError(err_msg) from None

    validate_value_for_kind(
        flag_kind=flag.flag_kind, value=default_value, rules=rules,
    )

    now = utc_now()
    new_version = (flag.current_version or 1) + 1
    rules_payload: Dict = {} if rules is None else dict(rules)
    version_row = FeatureFlagVersion(
        version_id=new_uuid(),
        flag_key=flag_key,
        version=new_version,
        default_value=default_value,
        rules_json=rules_payload,
        created_at=now,
        created_by=actor_user_id,
    )
    db_session.add(version_row)
    flag.current_version = new_version
    flag.updated_at = now
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=FlagEventTopics.FLAG_UPDATED,
            payload={
                "flag_key": flag_key,
                "version": new_version,
                "default_value": default_value,
                "actor_user_id": actor_user_id,
                "updated_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = flag
    return rtnval


def retire_flag(
        *,
        db_session: DbSession,
        flag_key: str,
        actor_user_id: Optional[str],
        grace_period: Optional[timedelta] = None
    ) -> FeatureFlag:
    """
        Flip a flag's state to ``RETIRED`` and stamp
        ``retired_at`` + ``grace_expires_at``. Emits
        :data:`FlagEventTopics.FLAG_RETIRED`.

        :param grace_period: Optional grace window before
                             :func:`finalize_retired_flag`
                             will permanently remove the row;
                             default 14 days.

        :raises: FlagNotFoundError on miss;
                 FlagAlreadyRetiredError when the flag is not
                 currently ACTIVE.
    """
    flag = (
        db_session.query(FeatureFlag)
        .filter(FeatureFlag.flag_key == flag_key)
        .first()
    )
    if flag is None:
        err_lines = ["Cannot retire feature flag — key not found."]
        err_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg = os.linesep.join(err_lines)
        raise FlagNotFoundError(err_msg) from None
    if flag.state != FlagState.ACTIVE:
        err_lines = ["Cannot retire feature flag — already past ACTIVE."]
        err_lines.append("FLAG_KEY: {}".format(flag_key))
        err_lines.append("STATE: {}".format(flag.state.value))
        err_msg = os.linesep.join(err_lines)
        raise FlagAlreadyRetiredError(err_msg) from None

    grace = (
        grace_period if grace_period is not None
        else DEFAULT_RETIRE_GRACE
    )
    now = utc_now()
    flag.state = FlagState.RETIRED
    flag.retired_at = now
    flag.grace_expires_at = now + grace
    flag.updated_at = now
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=FlagEventTopics.FLAG_RETIRED,
            payload={
                "flag_key": flag_key,
                "actor_user_id": actor_user_id,
                "retired_at": now.isoformat(),
                "grace_expires_at": flag.grace_expires_at.isoformat(),
                "grace_seconds": int(grace.total_seconds()),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = flag
    return rtnval


def remove_flag(
        *,
        db_session: DbSession,
        flag_key: str,
        actor_user_id: Optional[str],
        force: bool = False,
        now: Optional[datetime] = None
    ) -> bool:
    """
        Permanently delete a retired flag once its grace
        window has elapsed. With ``force=True`` the helper
        bypasses the grace check (used by the on-call leak
        path).

        Emits :data:`FlagEventTopics.FLAG_REMOVED` only when a
        row was deleted.

        :raises: FlagNotFoundError on miss;
                 SemanticError when the flag is still ACTIVE
                 (callers must :func:`retire_flag` first); or
                 when the grace deadline has not elapsed and
                 ``force=False``.
    """
    flag = (
        db_session.query(FeatureFlag)
        .filter(FeatureFlag.flag_key == flag_key)
        .first()
    )
    if flag is None:
        err_lines = ["Cannot remove feature flag — key not found."]
        err_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg = os.linesep.join(err_lines)
        raise FlagNotFoundError(err_msg) from None
    if flag.state == FlagState.ACTIVE:
        err_lines = [
            "Cannot remove feature flag — must retire first.",
        ]
        err_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None

    materialized_now = now if now is not None else utc_now()
    if force is False:
        deadline = flag.grace_expires_at
        if deadline is None:
            err_lines = [
                "Cannot remove feature flag — grace_expires_at unset.",
            ]
            err_lines.append("FLAG_KEY: {}".format(flag_key))
            err_msg = os.linesep.join(err_lines)
            raise SemanticError(err_msg) from None
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if materialized_now < deadline:
            err_lines = [
                "Cannot remove feature flag — grace window still pending.",
            ]
            err_lines.append("FLAG_KEY: {}".format(flag_key))
            err_lines.append(
                "GRACE_EXPIRES_AT: {}".format(deadline.isoformat()),
            )
            err_msg = os.linesep.join(err_lines)
            raise SemanticError(err_msg) from None

    db_session.delete(flag)
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=FlagEventTopics.FLAG_REMOVED,
            payload={
                "flag_key": flag_key,
                "actor_user_id": actor_user_id,
                "removed_at": materialized_now.isoformat(),
                "forced": bool(force),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return True


def sweep_retired_flags(
        *,
        db_session: DbSession,
        now: Optional[datetime] = None
    ) -> int:
    """
        Background-sweeper helper: walk every RETIRED flag
        whose ``grace_expires_at`` has elapsed and remove
        them. Returns the number of rows removed for operator
        metrics.
    """
    materialized_now = now if now is not None else utc_now()
    flags: List[FeatureFlag] = (
        db_session.query(FeatureFlag)
        .filter(FeatureFlag.state == FlagState.RETIRED)
        .all()
    )
    removed = 0
    for flag in flags:
        deadline = flag.grace_expires_at
        if deadline is None:
            continue
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if materialized_now < deadline:
            continue
        # Use remove_flag with force so the emit + delete path
        # is shared between manual and automated removal.
        remove_flag(
            db_session=db_session,
            flag_key=flag.flag_key,
            actor_user_id=None,
            force=True,
            now=materialized_now,
        )
        removed = removed + 1
    return removed
