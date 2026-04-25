"""
.. module:: jobs.dispatch.factories.fifo
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: FifoDispatchStrategy — oldest-last-dispatch wins.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Optional, Sequence

from automojo.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
    DispatchStrategyProtocol,
)


FIFO_STRATEGY_NAME: str = "fifo"


class FifoDispatchStrategy(DispatchStrategyProtocol):
    """
        Default M1 strategy. Picks the candidate whose
        ``last_dispatched_at_iso`` is the smallest — an
        empty-string value sorts earliest, so a pod that has never
        received a dispatch wins over any that have. Ties break on
        ``inflight_dispatch_count`` (lower wins) and finally
        ``pod_id`` lexicographic for determinism.
    """

    factory_protocol_name: str = "dispatch_strategy"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def strategy_name(cls) -> str:
        rtnval = FIFO_STRATEGY_NAME
        return rtnval

    @classmethod
    def pick(
            cls,
            *,
            candidates: Sequence[DispatchCandidate]
        ) -> Optional[DispatchCandidate]:
        if candidates is None or len(candidates) == 0:
            return None
        sorted_candidates = sorted(
            candidates,
            key=lambda candidate: (
                candidate.last_dispatched_at_iso,
                candidate.inflight_dispatch_count,
                candidate.pod_id,
            ),
        )
        rtnval = sorted_candidates[0]
        return rtnval
