"""
.. module:: orchestration.test.live.sse_channel
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Server-Sent-Events framing helpers.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Mapping

from automojo.pychestrate.webservice.orchestration.test.live.snapshot import (
    ProgressEvent,
)


SSE_HEARTBEAT_INTERVAL_SECONDS: int = 15


def format_sse_frame(*, event: ProgressEvent) -> bytes:
    """
        Render ``event`` as one SSE wire frame (UTF-8 bytes).
        Format::

            id: <sequence>
            event: <kind>
            data: <json>

        Followed by an empty line. Browsers and EventSource
        clients honor the same shape.

        :param event: Event to render.

        :returns: UTF-8 frame bytes.
    """
    body = {
        "run_id": event.run_id,
        "project_id": event.project_id,
        "recorded_at": event.recorded_at.isoformat(),
        "payload": _normalize_for_json(value=event.payload),
    }
    rtnval = (
        "id: {}\n"
        "event: {}\n"
        "data: {}\n\n"
    ).format(
        event.sequence,
        event.kind,
        json.dumps(body, ensure_ascii=False, sort_keys=True),
    ).encode("utf-8")
    return rtnval


def sse_heartbeat_frame() -> bytes:
    """
        Render a heartbeat comment frame. SSE comments start with
        ``:`` and are ignored by clients but keep proxy
        connections alive.

        :returns: UTF-8 heartbeat bytes.
    """
    rtnval = b": heartbeat\n\n"
    return rtnval


def _normalize_for_json(*, value: Any) -> Any:
    """
        Materialize Mappings and tuples into JSON-serializable
        equivalents. Used so a frozen dataclass payload doesn't
        trip ``json.dumps``.
    """
    if isinstance(value, Mapping):
        rtnval = {key: _normalize_for_json(value=val) for key, val in value.items()}
        return rtnval
    if isinstance(value, (list, tuple)):
        rtnval = [_normalize_for_json(value=item) for item in value]
        return rtnval
    return value
