"""
.. module:: orchestration.test.triage.factories.tracker_protocol
    :synopsis: ``bug_tracker_driver`` factory contract.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Optional

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


@dataclass(frozen=True)
class TrackerLink:
    """
        Result of a tracker open/comment call.

        :param tracker: Stable tracker name (``"jira"`` /
                        ``"github"`` / ``"linear"`` / ``"null"``).
        :param ticket_key: External ticket identifier.
        :param ticket_url: Browser-navigable URL.
    """
    tracker: str
    ticket_key: str
    ticket_url: str


class BugTrackerDriverProtocol(FactoryProtocolBase):
    """
        Contract for ``bug_tracker_driver`` extensions. M1 only
        wires :class:`NullBugTrackerDriver`; the live Jira /
        GitHub / Linear drivers land in M2 once the ops-config
        feature ships per-project tracker selection.
    """

    factory_protocol_name: str = "bug_tracker_driver"
    protocol_schema_version: int = 1

    @classmethod
    def tracker_name(cls) -> str:
        raise NotImplementedError("Subclasses must implement tracker_name")

    @classmethod
    def open_or_link_ticket(
            cls,
            *,
            project_id: str,
            case_id: str,
            classification: str,
            stack_signature_sha256: str,
            summary: str,
            actor_id: Optional[str]
        ) -> TrackerLink:
        """
            Open a fresh ticket or link to an existing one.
            Returns a :class:`TrackerLink` regardless of which
            path was taken.
        """
        raise NotImplementedError("Subclasses must implement open_or_link_ticket")
