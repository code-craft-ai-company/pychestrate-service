"""
.. module:: webinterface.site_shell.preferences_models
    :synopsis: Per-user preference rows (9-ui-profiles M2).

.. moduleauthor:: Code Craft AI LLC

A generic ``(user_id, key) -> value_json`` table. ``user_id`` is the
authenticated principal's id as a string (the consumer UI and the
REST surface both hand it over as text), deliberately without a
foreign key so the table serves whichever identity store issued it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import Column, DateTime, PrimaryKeyConstraint, String
from sqlalchemy.types import JSON

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class UserPreference(PychestratePhase1Base, SerializableModel):
    """
        One preference value for one user.
    """

    __tablename__ = "ui_user_preference"

    user_id = Column(String(64), nullable=False)
    key = Column(String(128), nullable=False)
    value_json = Column(JSON, nullable=False, default=dict)
    updated_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "key", name="pk_ui_user_preference"),
    )


#: Preference key holding a user's surface override (JSON list).
PREFERENCE_KEY_UI_SURFACES: str = "ui.surfaces"
