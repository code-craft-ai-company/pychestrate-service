"""
.. module:: jobs.dispatch.receipt
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-5 DispatchReceipt — client-issued local-run-id correlation.

.. moduleauthor:: Automation Mojo LLC

Public surface:

* :class:`DispatchReceipt` — persistence row.
* :class:`ReceiptRecord` — caller-facing IO shape.
* :func:`record`, :func:`lookup_by_local`, :func:`lookup_by_run` —
  service API.
* :class:`TimerWheel` + :func:`expect` / :func:`cancel` /
  :func:`fire_expired` — in-memory ack-timeout timers
  (:mod:`.timer_wheel`).
* :class:`DispatchReceiptError`,
  :class:`DuplicateRunReceiptError`,
  :class:`ReceiptEnvelopeMismatchError` — exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.jobs.dispatch.receipt.errors import (
    DispatchReceiptError,
    DuplicateRunReceiptError,
    ReceiptEnvelopeMismatchError,
    ReceiptNotFoundError,
)
from automojo.pychestrate.webservice.jobs.dispatch.receipt.models import (
    DispatchReceipt,
)
from automojo.pychestrate.webservice.jobs.dispatch.receipt.schema import (
    ReceiptRecord,
)
from automojo.pychestrate.webservice.jobs.dispatch.receipt.service import (
    lookup_by_local,
    lookup_by_run,
    record,
)
from automojo.pychestrate.webservice.jobs.dispatch.receipt.timer_wheel import (
    TimerWheel,
)
