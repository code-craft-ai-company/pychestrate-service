"""
.. module:: identity.flags.flag_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Feature-flag lifecycle API.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import datetime
import os

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.identity.flags.events import FlagEventTopics
from ccai.pychestrate.webservice.identity.flags.exceptions import (
    FlagAlreadyExistsError,
    FlagNotFoundError,
)
from ccai.pychestrate.webservice.identity.flags.models import (
    FeatureFlag,
    FeatureFlagVersion,
    FlagKind,
    FlagState,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event


DEFAULT_GRACE_SECONDS: int = 7 * 24 * 3600


def _validate_rules_for_kind(*, flag_kind: FlagKind, rules: Optional[Dict]) -> Dict:
    """
        Validate ``rules`` against the kind-specific schema and return a normalized dict.

        :param flag_kind: The kind being created or updated.
        :param rules: Caller-supplied rules payload (may be None).

        :returns: A dict suitable for persistence.
        :raises: SemanticError on rule shape violations.
    """
    rules_dict: Dict = {}
    if rules is not None:
        rules_dict = dict(rules)

    if flag_kind == FlagKind.PERCENTAGE:
        rollout_raw = rules_dict.get("rollout_percentage_bp", 0)
        try:
            rollout_value = int(rollout_raw)
        except (TypeError, ValueError):
            err_msg_lines = ["PERCENTAGE flag requires integer 'rollout_percentage_bp'."]
            err_msg_lines.append("VALUE: {}".format(rollout_raw))
            err_msg = os.linesep.join(err_msg_lines)
            raise SemanticError(err_msg) from None
        if rollout_value < 0 or rollout_value > 10000:
            err_msg_lines = ["PERCENTAGE 'rollout_percentage_bp' must be in [0, 10000]."]
            err_msg_lines.append("VALUE: {}".format(rollout_value))
            err_msg = os.linesep.join(err_msg_lines)
            raise SemanticError(err_msg) from None
        rules_dict["rollout_percentage_bp"] = rollout_value

    if flag_kind == FlagKind.ENUM:
        choices_raw = rules_dict.get("enum_choices", None)
        if choices_raw is None:
            err_msg_lines = ["ENUM flag requires non-empty 'enum_choices' in rules."]
            err_msg = os.linesep.join(err_msg_lines)
            raise SemanticError(err_msg) from None
        if len(choices_raw) == 0:
            err_msg_lines = ["ENUM flag requires at least one entry in 'enum_choices'."]
            err_msg = os.linesep.join(err_msg_lines)
            raise SemanticError(err_msg) from None
        normalized_choices: List[str] = []
        for choice in choices_raw:
            normalized_choices.append(str(choice))
        rules_dict["enum_choices"] = normalized_choices

    matches_raw = rules_dict.get("attribute_matches", None)
    if matches_raw is not None:
        normalized_matches: List[Dict] = []
        for match in matches_raw:
            attr_name = match.get("attr", None)
            equals_value = match.get("equals", None)
            return_value = match.get("return", None)
            if attr_name is None or equals_value is None:
                err_msg_lines = ["attribute_matches entry requires 'attr' and 'equals'."]
                err_msg_lines.append("ENTRY: {}".format(match))
                err_msg = os.linesep.join(err_msg_lines)
                raise SemanticError(err_msg) from None
            normalized_match: Dict = {
                "attr": str(attr_name),
                "equals": str(equals_value),
                "return": return_value,
            }
            normalized_matches.append(normalized_match)
        rules_dict["attribute_matches"] = normalized_matches

    rtnval = rules_dict
    return rtnval


def _validate_default_for_kind(*, flag_kind: FlagKind, default_value: Any, rules: Dict) -> None:
    """
        Validate ``default_value`` against ``flag_kind``.

        :param flag_kind: The flag kind.
        :param default_value: Caller-supplied default value.
        :param rules: Normalized rules dict (used for ENUM choice membership).

        :returns: None.
        :raises: SemanticError on type mismatch.
    """
    if flag_kind == FlagKind.BOOLEAN:
        if not isinstance(default_value, bool):
            err_msg_lines = ["BOOLEAN flag requires bool 'default_value'."]
            err_msg_lines.append("VALUE: {!r}".format(default_value))
            err_msg = os.linesep.join(err_msg_lines)
            raise SemanticError(err_msg) from None

    if flag_kind == FlagKind.STRING:
        if not isinstance(default_value, str):
            err_msg_lines = ["STRING flag requires str 'default_value'."]
            err_msg_lines.append("VALUE: {!r}".format(default_value))
            err_msg = os.linesep.join(err_msg_lines)
            raise SemanticError(err_msg) from None

    if flag_kind == FlagKind.ENUM:
        if not isinstance(default_value, str):
            err_msg_lines = ["ENUM flag requires str 'default_value' from 'enum_choices'."]
            err_msg_lines.append("VALUE: {!r}".format(default_value))
            err_msg = os.linesep.join(err_msg_lines)
            raise SemanticError(err_msg) from None
        choices = rules.get("enum_choices", [])
        if default_value not in choices:
            err_msg_lines = ["ENUM 'default_value' must be one of 'enum_choices'."]
            err_msg_lines.append("VALUE: {!r}".format(default_value))
            err_msg_lines.append("CHOICES: {!r}".format(choices))
            err_msg = os.linesep.join(err_msg_lines)
            raise SemanticError(err_msg) from None

    return


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
        :raises: FlagAlreadyExistsError, SemanticError
    """
    existing = db_session.query(FeatureFlag).filter(FeatureFlag.flag_key == flag_key).first()
    if existing is not None:
        err_msg_lines = ["Cannot create feature flag — key already exists."]
        err_msg_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg = os.linesep.join(err_msg_lines)
        raise FlagAlreadyExistsError(err_msg) from None

    rules_payload = _validate_rules_for_kind(flag_kind=flag_kind, rules=rules)
    _validate_default_for_kind(
        flag_kind=flag_kind, default_value=default_value, rules=rules_payload
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
        flag_kind: Optional[FlagKind],
        default_value: Any,
        rules: Optional[Dict],
        actor_user_id: Optional[str]
    ) -> FeatureFlag:
    """
        Persist a new immutable version with updated rules / default.

        ``flag_kind`` and ``flag_key`` are immutable after creation per
        Requirement 2.4 — passing a different ``flag_kind`` raises
        :class:`SemanticError`. To switch kinds, retire and re-create.

        :param db_session: Active SQLAlchemy session.
        :param flag_key: Existing flag key.
        :param flag_kind: Optional kind for redundant-validation; must
                          equal the persisted kind.
        :param default_value: Updated default value (kind-checked).
        :param rules: Updated rules payload.
        :param actor_user_id: Acting principal for audit attribution.

        :returns: The updated :class:`FeatureFlag` (refreshed view).
        :raises: FlagNotFoundError, SemanticError
    """
    flag = db_session.query(FeatureFlag).filter(FeatureFlag.flag_key == flag_key).first()
    if flag is None:
        err_msg_lines = ["Cannot update feature flag — key not found."]
        err_msg_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg = os.linesep.join(err_msg_lines)
        raise FlagNotFoundError(err_msg) from None

    if flag.state == FlagState.RETIRED:
        err_msg_lines = ["Cannot update a retired feature flag."]
        err_msg_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg = os.linesep.join(err_msg_lines)
        raise SemanticError(err_msg) from None

    if flag_kind is not None and flag_kind != flag.flag_kind:
        err_msg_lines = ["flag_kind is immutable after creation; retire and re-create."]
        err_msg_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg_lines.append("PERSISTED_KIND: {}".format(flag.flag_kind.value))
        err_msg_lines.append("REQUESTED_KIND: {}".format(flag_kind.value))
        err_msg = os.linesep.join(err_msg_lines)
        raise SemanticError(err_msg) from None

    rules_payload = _validate_rules_for_kind(flag_kind=flag.flag_kind, rules=rules)
    _validate_default_for_kind(
        flag_kind=flag.flag_kind, default_value=default_value, rules=rules_payload
    )

    now = utc_now()
    old_version = int(flag.current_version)
    new_version = old_version + 1

    new_version_row = FeatureFlagVersion(
        version_id=new_uuid(),
        flag_key=flag_key,
        version=new_version,
        default_value=default_value,
        rules_json=rules_payload,
        created_at=now,
        created_by=actor_user_id,
    )
    db_session.add(new_version_row)

    flag.current_version = new_version
    flag.updated_at = now
    db_session.flush()

    payload = {
        "flag_key": flag_key,
        "old_version": old_version,
        "new_version": new_version,
        "actor_user_id": actor_user_id,
        "updated_at": now.isoformat(),
    }
    event = EntityEvent(
        topic=FlagEventTopics.FLAG_UPDATED,
        payload=payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=event)

    db_session.commit()

    rtnval = flag
    return rtnval


def retire_flag(
        *,
        db_session: DbSession,
        flag_key: str,
        grace_seconds: int,
        actor_user_id: Optional[str]
    ) -> FeatureFlag:
    """
        Mark a flag retired and schedule removal at grace end.

        :param db_session: Active SQLAlchemy session.
        :param flag_key: Existing flag key.
        :param grace_seconds: Grace window during which evaluations
                              continue to return the final default.
        :param actor_user_id: Acting principal for audit attribution.

        :returns: The retired :class:`FeatureFlag`.
        :raises: FlagNotFoundError
    """
    if grace_seconds < 0:
        err_msg_lines = ["retire_flag requires non-negative grace_seconds."]
        err_msg_lines.append("VALUE: {}".format(grace_seconds))
        err_msg = os.linesep.join(err_msg_lines)
        raise SemanticError(err_msg) from None

    flag = db_session.query(FeatureFlag).filter(FeatureFlag.flag_key == flag_key).first()
    if flag is None:
        err_msg_lines = ["Cannot retire feature flag — key not found."]
        err_msg_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg = os.linesep.join(err_msg_lines)
        raise FlagNotFoundError(err_msg) from None

    if flag.state == FlagState.RETIRED:
        rtnval = flag
        return rtnval

    now = utc_now()
    grace_expires_at = now + datetime.timedelta(seconds=grace_seconds)

    flag.state = FlagState.RETIRED
    flag.retired_at = now
    flag.grace_expires_at = grace_expires_at
    flag.updated_at = now
    db_session.flush()

    payload = {
        "flag_key": flag_key,
        "actor_user_id": actor_user_id,
        "retired_at": now.isoformat(),
        "grace_expires_at": grace_expires_at.isoformat(),
    }
    event = EntityEvent(
        topic=FlagEventTopics.FLAG_RETIRED,
        payload=payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=event)

    db_session.commit()

    rtnval = flag
    return rtnval


def remove_expired_retired_flags(*, db_session: DbSession) -> List[str]:
    """
        Sweep retired flags whose grace window has expired and remove them.

        Intended to be invoked periodically by a scheduler. Each removal
        publishes ``entity.flag.removed``.

        :param db_session: Active SQLAlchemy session.

        :returns: Tuple of removed flag keys (sorted).
    """
    now = utc_now()
    expired_flags = (
        db_session.query(FeatureFlag)
        .filter(FeatureFlag.state == FlagState.RETIRED)
        .filter(FeatureFlag.grace_expires_at != None)  # noqa: E711 — SQL NULL-safe compare
        .filter(FeatureFlag.grace_expires_at <= now)
        .all()
    )

    removed_keys: List[str] = []
    for flag in expired_flags:
        flag_key = flag.flag_key
        db_session.query(FeatureFlagVersion).filter(
            FeatureFlagVersion.flag_key == flag_key
        ).delete()
        db_session.delete(flag)
        db_session.flush()

        payload = {
            "flag_key": flag_key,
            "removed_at": now.isoformat(),
        }
        event = EntityEvent(
            topic=FlagEventTopics.FLAG_REMOVED,
            payload=payload,
            source_event_id=new_uuid(),
        )
        enqueue_event(db_session=db_session, event=event)
        removed_keys.append(flag_key)

    if len(removed_keys) > 0:
        db_session.commit()

    removed_keys.sort()
    rtnval = removed_keys
    return rtnval


def list_flags(*, db_session: DbSession) -> List[FeatureFlag]:
    """
        List all registered flags ordered by ``flag_key``.

        :param db_session: Active SQLAlchemy session.

        :returns: List of :class:`FeatureFlag`.
    """
    rows = (
        db_session.query(FeatureFlag)
        .order_by(FeatureFlag.flag_key.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def list_flag_versions(*, db_session: DbSession, flag_key: str) -> List[FeatureFlagVersion]:
    """
        List all version rows for ``flag_key`` ordered ascending.

        :param db_session: Active SQLAlchemy session.
        :param flag_key: Existing flag key.

        :returns: List of :class:`FeatureFlagVersion`.
        :raises: FlagNotFoundError
    """
    flag = db_session.query(FeatureFlag).filter(FeatureFlag.flag_key == flag_key).first()
    if flag is None:
        err_msg_lines = ["Cannot list versions — flag key not found."]
        err_msg_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg = os.linesep.join(err_msg_lines)
        raise FlagNotFoundError(err_msg) from None

    rows = (
        db_session.query(FeatureFlagVersion)
        .filter(FeatureFlagVersion.flag_key == flag_key)
        .order_by(FeatureFlagVersion.version.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval
