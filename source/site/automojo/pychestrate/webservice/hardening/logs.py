"""
.. module:: hardening.logs
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Structured log emitter for Layer-2 M3.

.. moduleauthor:: Automation Mojo LLC

Wraps :mod:`logging` with a single helper that emits a JSON-serializable
record with a fixed schema. The central loggers for each feature call
this helper so the service emits consistent structured logs without
each call site re-implementing the shape.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging
import threading

from typing import Any, List, Mapping


_logger = logging.getLogger("pychestrate.layer2")

_LOCK = threading.RLock()
_CAPTURED: List[Mapping[str, Any]] = []
_CAPTURE_ENABLED: List[bool] = [False]


def emit_event(
        *,
        event: str,
        level: str,
        fields: Mapping[str, Any]
    ) -> None:
    """
        Log a structured event.

        :param event: Dotted event name, e.g. ``project.create.ok``.
        :param level: ``DEBUG | INFO | WARN | ERROR``.
        :param fields: Additional fields to include in the structured log.

        :returns: None.
    """
    payload = {"event": event, "level": level}
    if fields is not None:
        for key, value in fields.items():
            payload[key] = value

    method = getattr(_logger, level.lower(), _logger.info)
    try:
        serialized = json.dumps(payload, default=str, sort_keys=True)
    except (TypeError, ValueError):
        serialized = str(payload)
    method(serialized)

    with _LOCK:
        if _CAPTURE_ENABLED[0] is True:
            _CAPTURED.append(dict(payload))

    return


def start_capture_for_testing() -> None:
    """
        Start capturing emitted events in-memory. Test-only.
    """
    with _LOCK:
        _CAPTURED.clear()
        _CAPTURE_ENABLED[0] = True
    return


def stop_capture_for_testing() -> List[Mapping[str, Any]]:
    """
        Stop capturing and return the accumulated events. Test-only.
    """
    with _LOCK:
        _CAPTURE_ENABLED[0] = False
        rtnval = list(_CAPTURED)
        _CAPTURED.clear()
    return rtnval
