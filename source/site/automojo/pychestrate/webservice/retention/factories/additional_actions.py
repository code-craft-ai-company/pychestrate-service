"""
.. module:: retention.factories.additional_actions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: M2 reference retention actions (TierMove / Archive / PermanentArchive).

.. moduleauthor:: Automation Mojo LLC

Like :class:`DeleteAction`, these M2 reference actions are stubs — they
record that the action would apply, but defer the real artifact-store
mutations to Phase 10. This gives the audit + bus surface something to
emit against while downstream integrations land.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, Mapping

from automojo.pychestrate.webservice.retention.factories.action import (
    ActionApplication,
    RetentionActionProtocol,
)


class TierMoveAction(RetentionActionProtocol):
    """
        Move an entity between storage tiers (hot → warm → cold).
    """

    factory_protocol_name: ClassVar[str] = "retention_action"
    action_name: ClassVar[str] = "tier_move"
    terminal: ClassVar[bool] = False
    PRECEDENCE: ClassVar[int] = 1000

    @classmethod
    def apply(
            cls,
            *,
            entity_kind: str,
            entity_id: str,
            parameters: Mapping[str, Any],
            dry_run: bool
        ) -> ActionApplication:
        target_tier = parameters.get("target_tier", "warm") if parameters is not None else "warm"
        reason = "M2 stub — would move {}/{} to tier {} (dry_run={})".format(
            entity_kind, entity_id, target_tier, bool(dry_run),
        )
        rtnval = ActionApplication(outcome="applied", reason=reason, terminal=cls.terminal)
        return rtnval


class ArchiveAction(RetentionActionProtocol):
    """
        Archive an entity to cold storage (non-terminal; still recoverable).
    """

    factory_protocol_name: ClassVar[str] = "retention_action"
    action_name: ClassVar[str] = "archive"
    terminal: ClassVar[bool] = False
    PRECEDENCE: ClassVar[int] = 1000

    @classmethod
    def apply(
            cls,
            *,
            entity_kind: str,
            entity_id: str,
            parameters: Mapping[str, Any],
            dry_run: bool
        ) -> ActionApplication:
        reason = "M2 stub — would archive {}/{} (dry_run={})".format(
            entity_kind, entity_id, bool(dry_run),
        )
        rtnval = ActionApplication(outcome="applied", reason=reason, terminal=cls.terminal)
        return rtnval


class PermanentArchiveAction(RetentionActionProtocol):
    """
        Permanent archive — terminal, recovery impossible by this system.
    """

    factory_protocol_name: ClassVar[str] = "retention_action"
    action_name: ClassVar[str] = "permanent_archive"
    terminal: ClassVar[bool] = True
    PRECEDENCE: ClassVar[int] = 1000

    @classmethod
    def apply(
            cls,
            *,
            entity_kind: str,
            entity_id: str,
            parameters: Mapping[str, Any],
            dry_run: bool
        ) -> ActionApplication:
        reason = "M2 stub — would permanently archive {}/{} (dry_run={})".format(
            entity_kind, entity_id, bool(dry_run),
        )
        rtnval = ActionApplication(outcome="applied", reason=reason, terminal=cls.terminal)
        return rtnval
