"""
.. module:: orchestration.infra.guards.factories.apply_requires_role_rule
    :synopsis: ApplyRequiresInfraOperatorRoleRule — role-gated apply / destroy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.orchestration.infra.guards.factories.rule_protocol import (
    GuardContext,
    GuardDecision,
    GuardRuleProtocol,
    GuardVerdict,
)


APPLY_REQUIRES_INFRA_OPERATOR_ROLE_RULE_ID: str = (
    "ApplyRequiresInfraOperatorRoleRule"
)
INFRA_OPERATOR_ROLE: str = "infra-operator"
GUARDED_ACTIONS = ("apply", "destroy")


class ApplyRequiresInfraOperatorRoleRule(GuardRuleProtocol):
    """
        Denies ``apply`` and ``destroy`` unless the actor's
        role-set includes ``infra-operator``.
    """

    factory_protocol_name: str = "guard_rule"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 200

    @classmethod
    def rule_id(cls) -> str:
        rtnval = APPLY_REQUIRES_INFRA_OPERATOR_ROLE_RULE_ID
        return rtnval

    @classmethod
    def description(cls) -> str:
        rtnval = (
            "Denies apply and destroy unless the caller's "
            "role-set includes the 'infra-operator' role."
        )
        return rtnval

    @classmethod
    def evaluate(cls, *, context: GuardContext) -> GuardDecision:
        if context.action in GUARDED_ACTIONS:
            if INFRA_OPERATOR_ROLE not in context.actor_role_set:
                rtnval = GuardDecision(
                    verdict=GuardVerdict.DENY,
                    reason=(
                        "action '{}' requires the '{}' role".format(
                            context.action, INFRA_OPERATOR_ROLE,
                        )
                    ),
                )
                return rtnval
        rtnval = GuardDecision(verdict=GuardVerdict.ALLOW)
        return rtnval
