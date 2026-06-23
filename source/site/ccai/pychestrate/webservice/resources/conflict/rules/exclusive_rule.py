"""
.. module:: resources.conflict.rules.exclusive_rule
    :synopsis: ExclusiveModeRule — exclusive reservations are exclusive.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.resources.conflict.rules.rule_protocol import (
    ConflictRuleProtocol,
    RuleDecision,
)


EXCLUSIVE_RULE_NAME: str = "exclusive-mode"


class ExclusiveModeRule(ConflictRuleProtocol):
    """
        Vetoes a candidate when:

        * the candidate is exclusive AND any reservation on the
          resource exists, or
        * the candidate is shared AND any existing reservation is
          exclusive.

        Together with :class:`SharedModeRule` (which is a no-op
        accept), this implements the standard exclusive/shared
        sharing semantics.
    """

    factory_protocol_name: str = "conflict_rule"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 100

    @classmethod
    def rule_name(cls) -> str:
        rtnval = EXCLUSIVE_RULE_NAME
        return rtnval

    @classmethod
    def evaluate(
            cls,
            *,
            candidate,
            active_reservations
        ) -> RuleDecision:
        if candidate.mode == "exclusive":
            if len(active_reservations) > 0:
                rtnval = RuleDecision(
                    accepted=False,
                    reason=(
                        "exclusive request blocked by {} active "
                        "reservation(s)"
                    ).format(len(active_reservations)),
                    rule_name=EXCLUSIVE_RULE_NAME,
                )
                return rtnval
        else:
            for active in active_reservations:
                if active.mode == "exclusive":
                    rtnval = RuleDecision(
                        accepted=False,
                        reason="shared request blocked by active exclusive reservation",
                        rule_name=EXCLUSIVE_RULE_NAME,
                    )
                    return rtnval
        rtnval = RuleDecision(
            accepted=True, reason="", rule_name=EXCLUSIVE_RULE_NAME,
        )
        return rtnval
