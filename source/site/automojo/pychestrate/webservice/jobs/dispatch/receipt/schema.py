"""
.. module:: jobs.dispatch.receipt.schema
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Caller-facing IO shapes for dispatch receipts.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ReceiptRecord:
    """
        Caller-facing shape returned from :func:`record` and the
        ``lookup_*`` helpers. A stable read-model so callers do not
        depend on the ORM row.

        :param receipt_id: Server-side UUID persisted on the row.
        :param run_id: Owning run UUID.
        :param project_id: Owning project UUID.
        :param client_id: Client that produced the receipt.
        :param attempt_id: Linked ``dispatch_attempt`` UUID.
        :param envelope_id: Envelope the receipt acknowledges.
        :param client_local_run_id: Client-assigned local id that
                                    identifies the run inside the
                                    client's process tree. Unique
                                    per ``client_id``.
        :param received_at: UTC timestamp the service observed the
                            receipt.
        :param deadline_at: UTC timestamp the service expected the
                            receipt by — used to classify late
                            arrivals.
        :param late_arrival: ``True`` when ``received_at >
                             deadline_at``.
        :param launch_pid: Optional process id the client reports
                           (M3 scrubs this by default).
    """
    receipt_id: str
    run_id: str
    project_id: str
    client_id: str
    attempt_id: str
    envelope_id: str
    client_local_run_id: str
    received_at: datetime
    deadline_at: Optional[datetime]
    late_arrival: bool
    launch_pid: Optional[int]
