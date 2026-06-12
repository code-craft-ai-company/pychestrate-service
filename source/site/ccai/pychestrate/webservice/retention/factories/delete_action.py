"""
.. module:: retention.factories.delete_action
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference DeleteAction for 2-retention-policies M1.

.. moduleauthor:: Code Craft AI LLC

M1 ships a stub :class:`DeleteAction` that records an ``applied`` result
without performing any destructive side effects. M2 wires the action to
the concrete data-class back-end (run results, artifact-store objects,
log streams, audit records, metric samples) through per-kind erasure
APIs.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, Mapping

from ccai.pychestrate.webservice.retention.factories.action import (
    ActionApplication,
    RetentionActionProtocol,
)


class DeleteAction(RetentionActionProtocol):
    """
        Reference implementation of the ``delete`` retention action.

        The M1 implementation is a stub: it records that the action would
        apply, but does not touch downstream state. Callers gain the
        audit + bus emission surface without risking data loss while the
        per-kind erasure APIs are still landing.
    """

    factory_protocol_name: ClassVar[str] = "retention_action"
    action_name: ClassVar[str] = "delete"
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
        """
            Record that the delete action would apply. No destructive
            side effects at M1.

            :param entity_kind: Entity kind.
            :param entity_id: Entity id.
            :param parameters: Action parameters.
            :param dry_run: When True, treat exactly the same as M1
                            non-dry-run — both paths are stubs here.

            :returns: The :class:`ActionApplication`.
        """
        reason_bits = []
        reason_bits.append("M1 stub")
        reason_bits.append("entity={}/{}".format(entity_kind, entity_id))
        reason_bits.append("dry_run={}".format(bool(dry_run)))
        reason_bits.append("parameter_count={}".format(len(parameters) if parameters is not None else 0))

        rtnval = ActionApplication(
            outcome="applied",
            reason=" ; ".join(reason_bits),
            terminal=cls.terminal,
        )
        return rtnval
