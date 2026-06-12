"""
.. module:: jobs.dispatch.factories.strategy
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: DispatchStrategyProtocol — factory-protocol contract.

.. moduleauthor:: Code Craft AI LLC

A dispatch strategy picks one candidate client + pod pair out of the
eligible set for a given dispatch request. Strategies are swappable
via the :class:`FactoryProtocolBase` registry — operators register a
strategy with a lower ``PRECEDENCE`` to override the default.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Optional, Sequence

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


@dataclass(frozen=True)
class DispatchCandidate:
    """
        One eligible dispatch target. Strategies receive a list of
        these from :func:`eligibility.filter_candidates` and return
        one (or ``None`` if no candidate qualifies under their
        policy).

        :param client_id: Registered client UUID.
        :param pod_id: Target pod UUID the client manages.
        :param capability_tags: Free-form capability strings the
                                pod advertised. Strategies may use
                                these to break ties.
        :param inflight_dispatch_count: Number of dispatches
                                        currently transmitted (not
                                        yet acked) to the pod.
                                        Used by strategies that
                                        cap concurrency.
        :param last_dispatched_at_iso: ISO-8601 string of the
                                       pod's most recent dispatch
                                       for FIFO-ish fairness, or
                                       ``""`` if never dispatched.
    """
    client_id: str
    pod_id: str
    capability_tags: Sequence[str]
    inflight_dispatch_count: int
    last_dispatched_at_iso: str


class DispatchStrategyProtocol(FactoryProtocolBase):
    """
        Strategies decide *where* to send a dispatch request. They
        do not build envelopes, touch the run state, or record
        attempt rows — the dispatcher handles those uniformly.
    """

    factory_protocol_name: str = "dispatch_strategy"
    protocol_schema_version: int = 1

    @classmethod
    def strategy_name(cls) -> str:
        """
            Short identifier that downstream metrics / audit rows
            record alongside each dispatch attempt. Must be stable
            across releases of the same strategy.

            :returns: Algorithm string.
        """
        raise NotImplementedError("Subclasses must implement strategy_name")

    @classmethod
    def pick(
            cls,
            *,
            candidates: Sequence[DispatchCandidate]
        ) -> Optional[DispatchCandidate]:
        """
            Return one candidate from ``candidates`` or ``None``
            when no candidate qualifies. Strategies SHOULD be
            deterministic for the same input list so re-dispatch
            picks the same target absent state changes.

            :param candidates: Non-empty sequence of eligible
                               candidates.

            :returns: Chosen candidate or ``None``.
        """
        raise NotImplementedError("Subclasses must implement pick")
