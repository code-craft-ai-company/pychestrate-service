"""
.. module:: orchestration.rpa.packet
    :synopsis: Work-packet helpers — merge, digest, redaction, schema
               validation, and the consumer-project UUID bridge.

.. moduleauthor:: Code Craft AI LLC

A **work packet** is the JSON document an RPA job processes. The
trigger path merges the caller's packet over the specification's
``default_packet`` (packet keys win), validates the result against the
job type's JSON schema, stores a redacted copy on the job row, and
places the full packet in the signed envelope only.
"""

__author__ = "Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import copy
import hashlib
import json
import os
import re
import uuid

from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from ccai.pychestrate.webservice.orchestration.rpa.errors import (
    PacketTooLargeError,
    PacketValidationError,
)


#: Marker written in place of a secret value on the persisted packet.
REDACTION_MARKER: str = "***REDACTED***"

#: Default cap on the canonical JSON size of a merged packet (1 MiB).
DEFAULT_MAX_PACKET_BYTES: int = 1024 * 1024

#: Slug rule for job type ids: lowercase, digits, hyphen; 3-64 chars.
TYPE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,63}$")

#: UUID5 namespace used to map consumer-UI integer project ids onto a
#: stable UUID for the UUID-typed Layer-5 tables.
CONSUMER_PROJECT_NAMESPACE = uuid.UUID("7f4b6a2e-5c8d-4e1f-9a3b-2d6c8e0f1a5b")


def is_valid_type_id(candidate: Any) -> bool:
    """
        Whether ``candidate`` is a well-formed job type slug.

        :param candidate: Value to check.

        :returns: True for a lowercase slug of 3 to 64 characters.
    """
    if not isinstance(candidate, str):
        return False
    rtnval = TYPE_ID_PATTERN.match(candidate) is not None
    return rtnval


def canonical_project_uuid(project_ref: str) -> str:
    """
        Map a project reference onto a UUID string for the
        UUID-typed Layer-5 tables (run state, dispatch, envelope,
        results).

        A reference that already parses as a UUID is returned in
        canonical form. Any other reference (the consumer web UI's
        integer project ids) is mapped through a UUID5 in a fixed
        namespace so the same project always yields the same UUID.

        :param project_ref: Project id as given by the caller.

        :returns: Canonical UUID string.
    """
    text = str(project_ref).strip()
    try:
        rtnval = str(uuid.UUID(text))
        return rtnval
    except (ValueError, AttributeError, TypeError):
        pass
    rtnval = str(uuid.uuid5(CONSUMER_PROJECT_NAMESPACE, "consumer-project:{}".format(text)))
    return rtnval


def canonical_json(value: Any) -> str:
    """
        Deterministic JSON serialisation (sorted keys, compact).

        :param value: JSON-serializable value.

        :returns: Canonical JSON text.
    """
    rtnval = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return rtnval


def merge_packet(*, default_packet: Mapping[str, Any], work_packet: Mapping[str, Any]) -> Dict[str, Any]:
    """
        Merge ``work_packet`` over ``default_packet``. Top-level keys
        from the work packet win; nested objects are replaced, not
        deep-merged, so a job sees exactly what the caller sent for a
        key it supplied.

        :param default_packet: Specification defaults.
        :param work_packet: Caller-supplied packet.

        :returns: New merged dict.
    """
    rtnval: Dict[str, Any] = {}
    for key, value in dict(default_packet or {}).items():
        rtnval[str(key)] = copy.deepcopy(value)
    for key, value in dict(work_packet or {}).items():
        rtnval[str(key)] = copy.deepcopy(value)
    return rtnval


def packet_digest(packet: Mapping[str, Any]) -> str:
    """
        SHA-256 of the canonical JSON of ``packet``.

        :param packet: Merged packet.

        :returns: Hex digest.
    """
    rtnval = hashlib.sha256(canonical_json(dict(packet)).encode("utf-8")).hexdigest()
    return rtnval


def packet_size_bytes(packet: Mapping[str, Any]) -> int:
    """
        Size of the canonical JSON of ``packet`` in bytes.
    """
    rtnval = len(canonical_json(dict(packet)).encode("utf-8"))
    return rtnval


def enforce_packet_size(*, packet: Mapping[str, Any], max_bytes: int = DEFAULT_MAX_PACKET_BYTES) -> None:
    """
        Raise :class:`PacketTooLargeError` when the packet exceeds
        ``max_bytes``.
    """
    size = packet_size_bytes(packet)
    if size > max_bytes:
        err_lines = ["Work packet exceeds the size limit."]
        err_lines.append("SIZE_BYTES: {}".format(size))
        err_lines.append("LIMIT_BYTES: {}".format(max_bytes))
        err_lines.append("HINT: pass large inputs by reference (an artifact key) instead.")
        raise PacketTooLargeError(os.linesep.join(err_lines))
    return


def _split_pointer(pointer: str) -> List[str]:
    """
        Split a JSON pointer (``/a/b/0``) or a dotted path (``a.b.0``)
        into segments.
    """
    text = str(pointer or "").strip()
    if len(text) == 0:
        return []
    if text.startswith("/"):
        parts = text[1:].split("/")
        rtnval = [p.replace("~1", "/").replace("~0", "~") for p in parts]
        return rtnval
    rtnval = text.split(".")
    return rtnval


def _redact_at(node: Any, segments: List[str]) -> None:
    if len(segments) == 0:
        return
    head = segments[0]
    rest = segments[1:]
    if isinstance(node, dict):
        if head not in node:
            return
        if len(rest) == 0:
            node[head] = REDACTION_MARKER
            return
        _redact_at(node[head], rest)
        return
    if isinstance(node, list):
        if head == "*":
            for child in node:
                if len(rest) == 0:
                    continue
                _redact_at(child, rest)
            return
        try:
            index = int(head)
        except ValueError:
            return
        if index < 0 or index >= len(node):
            return
        if len(rest) == 0:
            node[index] = REDACTION_MARKER
            return
        _redact_at(node[index], rest)
    return


def redact_packet(*, packet: Mapping[str, Any], secret_fields: Iterable[str]) -> Dict[str, Any]:
    """
        Return a deep copy of ``packet`` with every path named in
        ``secret_fields`` replaced by :data:`REDACTION_MARKER`.
        Paths may be JSON pointers (``/auth/token``) or dotted
        (``auth.token``); ``*`` matches every list element.

        :param packet: Merged packet.
        :param secret_fields: Paths to redact.

        :returns: Redacted copy. The input is not modified.
    """
    rtnval = copy.deepcopy(dict(packet))
    for field in list(secret_fields or []):
        _redact_at(rtnval, _split_pointer(field))
    return rtnval


def secret_top_level_keys(*, secret_fields: Iterable[str]) -> List[str]:
    """
        Top-level packet keys that contain at least one secret path.

        Packets merge at the top level (see :func:`merge_packet`), so a
        form or client that must not see a secret has to leave out the
        whole top-level key holding it; the stored default then applies.

        :param secret_fields: Secret paths declared by the job type.

        :returns: Sorted, de-duplicated top-level keys.
    """
    keys = set()
    for field_path in list(secret_fields or []):
        segments = _split_pointer(field_path)
        if len(segments) > 0:
            keys.add(segments[0])
    rtnval = sorted(keys)
    return rtnval


def _value_at(node: Any, segments: List[str]) -> Any:
    """
        Read the value at ``segments`` (no wildcards), or raise
        ``KeyError`` when the path does not exist.
    """
    current = node
    for segment in segments:
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list):
            index = int(segment)
            current = current[index]
        else:
            raise KeyError(segment)
    return current


def _set_at(node: Any, segments: List[str], value: Any) -> None:
    """
        Write ``value`` at ``segments`` (no wildcards) when the parent
        path exists.
    """
    parent = _value_at(node, segments[:-1])
    last = segments[-1]
    if isinstance(parent, dict):
        parent[last] = value
    elif isinstance(parent, list):
        parent[int(last)] = value
    return


def restore_redacted_secrets(
        *,
        incoming: Mapping[str, Any],
        stored: Mapping[str, Any],
        secret_fields: Iterable[str]
    ) -> Dict[str, Any]:
    """
        Replace :data:`REDACTION_MARKER` values at secret paths in
        ``incoming`` with the stored value, so a client that saves back
        a packet it read (redacted) does not overwrite the real secret
        with the marker. Wildcard paths are not restored.

        :param incoming: Packet the caller submitted.
        :param stored: Packet currently stored.
        :param secret_fields: Secret paths declared by the job type.

        :returns: A copy of ``incoming`` with markers restored.
    """
    rtnval = copy.deepcopy(dict(incoming or {}))
    for field_path in list(secret_fields or []):
        segments = _split_pointer(field_path)
        if len(segments) == 0 or "*" in segments:
            continue
        try:
            submitted = _value_at(rtnval, segments)
        except (KeyError, IndexError, ValueError, TypeError):
            continue
        if submitted != REDACTION_MARKER:
            continue
        try:
            original = _value_at(stored, segments)
        except (KeyError, IndexError, ValueError, TypeError):
            continue
        _set_at(rtnval, segments, copy.deepcopy(original))
    return rtnval


def validate_packet(*, packet: Mapping[str, Any], schema: Optional[Mapping[str, Any]]) -> None:
    """
        Validate ``packet`` against ``schema`` (JSON Schema draft
        2020-12). A ``None`` or empty schema accepts every packet.

        :param packet: Merged packet.
        :param schema: JSON Schema dict or ``None``.

        :raises: PacketValidationError listing every failing path.
    """
    if schema is None or len(dict(schema)) == 0:
        return
    try:
        import jsonschema  # noqa: E402
    except ImportError:  # pragma: no cover - dependency is pinned
        return

    validator_cls = jsonschema.validators.validator_for(dict(schema))
    validator = validator_cls(dict(schema))
    issues: List[Tuple[str, str]] = []
    for error in sorted(validator.iter_errors(dict(packet)), key=lambda e: list(e.absolute_path)):
        pointer = "/" + "/".join(str(p) for p in error.absolute_path)
        issues.append((pointer, error.message))
    if len(issues) == 0:
        return
    err_lines = ["Work packet failed schema validation: {} issue(s).".format(len(issues))]
    for index, (pointer, message) in enumerate(issues):
        err_lines.append("  [{}] {}: {}".format(index + 1, pointer, message))
    raise PacketValidationError(os.linesep.join(err_lines), issues=issues)


def validate_schema_document(schema: Any) -> Tuple[bool, Tuple[str, ...]]:
    """
        Check that ``schema`` is itself a valid JSON Schema document.

        :returns: ``(True, ())`` or ``(False, (reason, ...))``.
    """
    if schema is None:
        return (True, ())
    if not isinstance(schema, dict):
        return (False, ("'packet_schema' must be a JSON object",))
    try:
        import jsonschema  # noqa: E402
    except ImportError:  # pragma: no cover
        return (True, ())
    try:
        validator_cls = jsonschema.validators.validator_for(schema)
        validator_cls.check_schema(schema)
    except jsonschema.exceptions.SchemaError as xcpt:
        return (False, ("'packet_schema' is not a valid JSON Schema: {}".format(xcpt.message),))
    return (True, ())
