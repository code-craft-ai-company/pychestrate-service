"""
.. module:: resources.conflict.rules.shared_rule
    :synopsis: SharedModeRule — accept-shared-when-no-exclusive.

The :class:`ExclusiveModeRule` already handles the
exclusive-vs-shared case; :class:`SharedModeRule` is a no-op
accept that exists primarily to demonstrate the rule-extension
surface and to leave a hook where future operators register
shared-mode-specific policies (e.g. cap on concurrent shared
reservations).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.resources.conflict.rules.rule_protocol import (
    ConflictRuleProtocol,
    RuleDecision,
)


SHARED_RULE_NAME: str = "shared-mode"


class SharedModeRule(ConflictRuleProtocol):
    """
        Reference shared-mode rule — always accepts (the heavy
        lifting is done by :class:`ExclusiveModeRule`).
    """

    factory_protocol_name: str = "conflict_rule"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 200

    @classmethod
    def rule_name(cls) -> str:
        rtnval = SHARED_RULE_NAME
        return rtnval

    @classmethod
    def evaluate(
            cls,
            *,
            candidate,
            active_reservations
        ) -> RuleDecision:
        rtnval = RuleDecision(
            accepted=True, reason="", rule_name=SHARED_RULE_NAME,
        )
        return rtnval
