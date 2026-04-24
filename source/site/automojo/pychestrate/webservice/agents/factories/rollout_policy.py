"""
.. module:: agents.factories.rollout_policy
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``rollout_policy`` factory protocol base + reference impl.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar, Sequence

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


class RolloutPolicyProtocol(FactoryProtocolBase):
    """
        Contract for rollout policies — given a candidate client set,
        choose which subset to include in the current stage.
    """

    factory_protocol_name: ClassVar[str] = "rollout_policy"
    protocol_schema_version: ClassVar[int] = 1
    policy_name: ClassVar[str] = ""

    @classmethod
    def pick_targets(
            cls,
            *,
            candidate_client_ids: Sequence[str],
            target_size: int
        ) -> Sequence[str]:
        raise NotImplementedError("Subclasses must implement pick_targets()")


class FixedSetRolloutPolicy(RolloutPolicyProtocol):
    """
        Reference policy: return the first ``target_size`` candidates.
    """

    factory_protocol_name: ClassVar[str] = "rollout_policy"
    policy_name: ClassVar[str] = "fixed_set"
    PRECEDENCE: ClassVar[int] = 100

    @classmethod
    def pick_targets(
            cls,
            *,
            candidate_client_ids: Sequence[str],
            target_size: int
        ) -> Sequence[str]:
        if candidate_client_ids is None:
            rtnval = []
            return rtnval
        rtnval = list(candidate_client_ids)[: int(target_size)]
        return rtnval
