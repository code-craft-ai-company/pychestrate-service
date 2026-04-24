"""
.. module:: retention.factories.action
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``retention_action`` factory protocol base.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


@dataclass(frozen=True)
class ActionApplication:
    """
        Result of applying one :class:`RetentionActionProtocol` to one entity.

        :param outcome: One of ``applied | skipped | failed``.
        :param reason: Free-form description.
        :param terminal: True when this action ends the entity's lifecycle.
    """
    outcome: str
    reason: str
    terminal: bool


class RetentionActionProtocol(FactoryProtocolBase):
    """
        Contract implemented by each retention action.
    """

    factory_protocol_name: ClassVar[str] = "retention_action"
    protocol_schema_version: ClassVar[int] = 1
    action_name: ClassVar[str] = ""
    terminal: ClassVar[bool] = False

    @classmethod
    def apply(
            cls,
            *,
            entity_kind: str,
            entity_id: str,
            parameters: Mapping[str, Any],
            dry_run: bool
        ) -> ActionApplication:
        """
            Apply this action to a single entity.

            :param entity_kind: Entity kind.
            :param entity_id: Entity id.
            :param parameters: Action parameters from the policy step.
            :param dry_run: When True, do not mutate anything.

            :returns: The :class:`ActionApplication`.
        """
        raise NotImplementedError("Subclasses must implement apply()")
