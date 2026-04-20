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

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.identity.flags.events import FlagEventTopics
from automojo.pychestrate.webservice.identity.flags.exceptions import FlagAlreadyExistsError
from automojo.pychestrate.webservice.identity.flags.models import (
    FeatureFlag,
    FeatureFlagVersion,
    FlagKind,
    FlagState,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


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
