"""
.. module:: clients.upgrades.factories.fixed_set_policy
    :synopsis: FixedSetRolloutPolicy reference at PRECEDENCE=100.

The fixed-set policy reads a hard-coded ``client_ids`` list
from ``params``. M2 ships percent / ring / canary policies on
top of the same protocol; the M1 reference keeps the test
surface pure-deterministic (the fleet snapshot is consulted
only to filter unknowns).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Mapping, Tuple

from ccai.pychestrate.webservice.clients.upgrades.dtos import FleetSnapshot
from ccai.pychestrate.webservice.clients.upgrades.factories.rollout_policy_protocol import (
    RolloutPolicyProtocol,
)


FIXED_SET_POLICY_NAME: str = "fixed_set"


class FixedSetRolloutPolicy(RolloutPolicyProtocol):
    """
        Reference policy that emits offers to a hard-coded
        list of client ids passed via
        ``params={"client_ids": [...]}`` and intersected with
        the supplied :class:`FleetSnapshot`.
    """

    factory_protocol_name: str = "rollout_policy"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 100

    @classmethod
    def policy_name(cls) -> str:
        rtnval = FIXED_SET_POLICY_NAME
        return rtnval

    @classmethod
    def compute_target_set(
            cls,
            *,
            rollout_id: str,
            fleet: FleetSnapshot,
            params: Mapping[str, Any]
        ) -> Tuple[str, ...]:
        raw = params.get("client_ids", []) if params is not None else []
        if not isinstance(raw, (list, tuple)):
            return tuple()
        known = set(member.client_id for member in fleet.members)
        chosen = []
        for client_id in raw:
            if not isinstance(client_id, str):
                continue
            if client_id not in known:
                continue
            if client_id in chosen:
                continue
            chosen.append(client_id)
        rtnval: Tuple[str, ...] = tuple(chosen)
        return rtnval
