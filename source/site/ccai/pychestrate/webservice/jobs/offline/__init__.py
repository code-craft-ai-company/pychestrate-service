"""
.. module:: jobs.offline
    :synopsis: 5-offline-tolerance — pod offline state + deferred cancel.

Public surface:

* :class:`PodOfflineStateService` — observe-and-arm timers for
  ``entity.client.session_dropped`` /
  ``entity.client.reconnected``.
* :class:`DeferredCancelQueue` — queue cancel requests against
  offline pods and replay on reconnect.
* :class:`ReplayCoordinator` — accept replayed progress with
  monotonic-cursor enforcement.
* Persistence: :class:`PodOfflineState`,
  :class:`ClientReplayCursor`, :class:`DeferredCancel`.
* Errors: :class:`OfflineError`,
  :class:`ReplaySeqGapError`,
  :class:`ReplayAuthError`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.jobs.offline.cancel_queue import (
    DeferredCancelQueue,
)
from ccai.pychestrate.webservice.jobs.offline.errors import (
    OfflineError,
    ReplayAuthError,
    ReplaySeqGapError,
)
from ccai.pychestrate.webservice.jobs.offline.models import (
    ClientReplayCursor,
    DeferredCancel,
    DeferredCancelStatus,
    PodLivenessTier,
    PodOfflineState,
)
from ccai.pychestrate.webservice.jobs.offline.pod_state import (
    PodOfflineStateService,
)
from ccai.pychestrate.webservice.jobs.offline.replay import (
    ReplayCoordinator,
    ReplayResult,
)
