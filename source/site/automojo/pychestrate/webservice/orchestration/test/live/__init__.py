"""
.. module:: orchestration.test.live
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 6-live-run-view — SSE relay + snapshot endpoint.

.. moduleauthor:: Automation Mojo LLC

Public surface:

* :class:`ProgressSnapshot`, :class:`ProgressEvent` — IO shapes.
* :func:`merge_event` — delta-merge of an event into a snapshot.
* :class:`RunRelay` — per-run ring buffer + subscriber set.
* :func:`format_sse_frame` — SSE wire framing helper.
* :class:`LiveRunHub` — registry of live relays + subscribe API.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.orchestration.test.live.hub import (
    LiveRunHub,
)
from automojo.pychestrate.webservice.orchestration.test.live.relay import (
    RunRelay,
)
from automojo.pychestrate.webservice.orchestration.test.live.snapshot import (
    ProgressEvent,
    ProgressSnapshot,
    merge_event,
)
from automojo.pychestrate.webservice.orchestration.test.live.sse_channel import (
    SSE_HEARTBEAT_INTERVAL_SECONDS,
    format_sse_frame,
    sse_heartbeat_frame,
)
