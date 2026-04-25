"""
.. module:: orchestration.test.triage.factories.null_tracker_driver
    :synopsis: NullBugTrackerDriver — local-only triage links.

The null driver is the in-tree default. It synthesizes a
deterministic local key derived from the case id so triage cases
have a non-empty link before a real tracker is wired up.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Optional

from automojo.pychestrate.webservice.orchestration.test.triage.factories.tracker_protocol import (
    BugTrackerDriverProtocol,
    TrackerLink,
)


NULL_TRACKER_NAME: str = "null"


class NullBugTrackerDriver(BugTrackerDriverProtocol):
    """
        No-op tracker driver — produces a stable internal link.
    """

    factory_protocol_name: str = "bug_tracker_driver"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def tracker_name(cls) -> str:
        rtnval = NULL_TRACKER_NAME
        return rtnval

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
        ticket_key = "PYC-{}".format(case_id[:8].upper())
        ticket_url = "/internal/triage/{}".format(case_id)
        rtnval = TrackerLink(
            tracker=NULL_TRACKER_NAME,
            ticket_key=ticket_key,
            ticket_url=ticket_url,
        )
        return rtnval
