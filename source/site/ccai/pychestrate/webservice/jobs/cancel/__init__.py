"""
.. module:: jobs.cancel
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 5-cancel-reconcile cancel-RPC half.

.. moduleauthor:: Code Craft AI LLC

Public surface:

* :class:`CancelDispatcher` — sends the cancel RPC to the pod
  client and records the attempt.
* :func:`request_cancel`, :func:`handle_ack`, :func:`get_request`
  — service helpers.
* Persistence: :class:`CancelRequest`, :class:`CancelStatus`.
* Topics: :class:`CancelEventTopics`.
* Errors: :class:`CancelError`,
  :class:`CancelTransportError`,
  :class:`CancelDuplicateRequestError`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.jobs.cancel.dispatcher import (
    CancelDispatcher,
    CancelTransportProtocol,
    InMemoryCancelTransport,
    handle_ack,
    request_cancel,
)
from ccai.pychestrate.webservice.jobs.cancel.errors import (
    CancelDuplicateRequestError,
    CancelError,
    CancelTransportError,
)
from ccai.pychestrate.webservice.jobs.cancel.events import (
    CancelEventTopics,
)
from ccai.pychestrate.webservice.jobs.cancel.models import (
    CancelRequest,
    CancelStatus,
)
from ccai.pychestrate.webservice.jobs.cancel.repository import (
    get_request,
)
