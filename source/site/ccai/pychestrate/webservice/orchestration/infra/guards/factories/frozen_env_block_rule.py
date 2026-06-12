"""
.. module:: orchestration.infra.guards.factories.frozen_env_block_rule
    :synopsis: FrozenEnvBlockRule — denies destructive actions on frozen envs.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.orchestration.infra.guards.factories.rule_protocol import (
    GuardContext,
    GuardDecision,
    GuardRuleProtocol,
    GuardVerdict,
)


FROZEN_ENV_BLOCK_RULE_ID: str = "FrozenEnvBlockRule"
DESTRUCTIVE_ACTIONS = ("apply", "destroy")


class FrozenEnvBlockRule(GuardRuleProtocol):
    """
        Denies ``apply`` and ``destroy`` on frozen environments
        regardless of role set or other attrs.
    """

    factory_protocol_name: str = "guard_rule"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 100

    @classmethod
    def rule_id(cls) -> str:
        rtnval = FROZEN_ENV_BLOCK_RULE_ID
        return rtnval

    @classmethod
    def description(cls) -> str:
        rtnval = (
            "Denies apply and destroy actions on frozen "
            "environments. Plan is always allowed."
        )
        return rtnval

    @classmethod
    def evaluate(cls, *, context: GuardContext) -> GuardDecision:
        if context.environment_state == "frozen":
            if context.action in DESTRUCTIVE_ACTIONS:
                rtnval = GuardDecision(
                    verdict=GuardVerdict.DENY,
                    reason=(
                        "environment is frozen; '{}' is blocked".format(
                            context.action,
                        )
                    ),
                )
                return rtnval
        rtnval = GuardDecision(verdict=GuardVerdict.ALLOW)
        return rtnval
