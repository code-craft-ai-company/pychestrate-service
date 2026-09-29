"""
.. module:: runs.restapi.v1.task_results
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One stored test result shaped for the results API (ORC-10).

.. moduleauthor:: Code Craft AI LLC

The ingest tables keep every test's result and its raw testbase record, but
nothing exposed them, so a failed run showed counts and no reason. This module
turns a stored :class:`~ingest.result.models.TaskResult` into the JSON the
``GET /api/v1/runs/{run_id}/results`` endpoint returns: the test, its result and
duration, and for each failure, error or warning the exception type, its
message and the stack frames with the source lines around them.

The raw record is pod output, so every piece is bounded (message length, number
of frames, lines per frame) and every value is coerced to text; nothing from it
is passed through unexamined.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Optional


#: The longest exception message returned; a longer one is cut.
MAX_MESSAGE_CHARS: int = 4000

#: Stack frames returned per problem.
MAX_FRAMES: int = 12

#: Source lines returned per frame.
MAX_CODE_LINES: int = 10

#: Problems returned per test (failures + errors + warnings).
MAX_PROBLEMS: int = 10

_PROBLEM_KINDS = (("failures", "failure"), ("errors", "error"), ("warnings", "warning"))


def _text(value: Any, limit: int) -> str:
    """
        ``value`` as text, cut at ``limit`` characters.

        :param value: Anything.
        :param limit: The longest text returned.

        :returns: The text; an ellipsis marks a cut.
    """
    text = "" if value is None else str(value)
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _frame(trace: Any) -> Optional[Dict[str, Any]]:
    """
        One stack frame from a raw trace entry.

        :param trace: A ``{"origin": {"file", "lineno", "scope"}, "call", "code"}`` entry.

        :returns: ``{"file", "line", "scope", "code"}``, or ``None`` when the entry is not a mapping.
    """
    if not isinstance(trace, dict):
        return None
    origin = trace.get("origin")
    origin = origin if isinstance(origin, dict) else {}
    code = trace.get("code")
    lines = [_text(line, 300) for line in code[:MAX_CODE_LINES]] if isinstance(code, list) else []
    line_number = origin.get("lineno")
    rtnval = {
        "file": _text(origin.get("file"), 500),
        "line": line_number if isinstance(line_number, int) and not isinstance(line_number, bool) else None,
        "scope": _text(origin.get("scope"), 200),
        "code": lines,
    }
    return rtnval


def _problem(kind: str, entry: Any) -> Dict[str, Any]:
    """
        One failure, error or warning.

        :param kind: ``failure``, ``error`` or ``warning``.
        :param entry: The raw record entry (a mapping, or plain text).

        :returns: ``{"kind", "type", "message", "frames"}``.
    """
    if not isinstance(entry, dict):
        return {"kind": kind, "type": "", "message": _text(entry, MAX_MESSAGE_CHARS), "frames": []}
    arguments = entry.get("exargs")
    message = "\n".join(str(part) for part in arguments) if isinstance(arguments, list) else _text(arguments, MAX_MESSAGE_CHARS)
    traces = entry.get("traces")
    frames: List[Dict[str, Any]] = []
    if isinstance(traces, list):
        for trace in traces[:MAX_FRAMES]:
            frame = _frame(trace)
            if frame is not None:
                frames.append(frame)
    rtnval = {
        "kind": kind,
        "type": _text(entry.get("extype"), 200),
        "message": _text(message, MAX_MESSAGE_CHARS),
        "frames": frames,
    }
    return rtnval


def task_result_to_dict(row: Any) -> Dict[str, Any]:
    """
        Shape a stored test result for the API.

        :param row: A :class:`TaskResult` row.

        :returns: ``{"task_id", "test_name", "result", "started_at",
                  "finished_at", "duration_seconds", "problems"}``.
    """
    raw = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    detail = raw.get("detail")
    detail = detail if isinstance(detail, dict) else {}
    problems: List[Dict[str, Any]] = []
    for key, kind in _PROBLEM_KINDS:
        entries = detail.get(key)
        if isinstance(entries, list):
            for entry in entries:
                if len(problems) < MAX_PROBLEMS:
                    problems.append(_problem(kind, entry))
    duration: Optional[float] = None
    if row.started_at is not None and row.finished_at is not None:
        duration = max(0.0, (row.finished_at - row.started_at).total_seconds())
    rtnval = {
        "task_id": str(row.task_id),
        "test_name": row.test_name,
        "result": row.result,
        "started_at": row.started_at.isoformat() if row.started_at is not None else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at is not None else None,
        "duration_seconds": duration,
        "problems": problems,
    }
    return rtnval


__all__ = [
    "MAX_CODE_LINES",
    "MAX_FRAMES",
    "MAX_MESSAGE_CHARS",
    "MAX_PROBLEMS",
    "task_result_to_dict",
]
