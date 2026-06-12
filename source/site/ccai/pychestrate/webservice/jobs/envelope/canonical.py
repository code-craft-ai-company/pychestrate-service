"""
.. module:: jobs.envelope.canonical
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Canonical JSON serialize / parse for JobEnvelope.

.. moduleauthor:: Code Craft AI LLC

RFC 8785 (JCS) defines a deterministic serialization of a JSON value.
The M1 implementation uses a subset sufficient for JobEnvelope
payloads:

* Object keys are UTF-16 code-unit sorted (matches JCS).
* No whitespace between tokens.
* Strings are serialized with the default Python JSON escapes
  (JCS mandates the same escape set for control characters and
  quote / backslash).
* Numbers are restricted to integers and floats that round-trip
  cleanly through ``json.loads(json.dumps(v))`` — floats with more
  than 15 significant digits MAY differ between producer and consumer
  runtimes, so the schema forbids them (callers must pass either an
  int or a decimal-string wrapper if they need high precision).

M3 will swap this implementation for a full JCS library so extensions
that stuff floats / Unicode-high-plane strings into
``extension_claims`` round-trip bit-identically. For M1 everything we
put into the envelope is ASCII / integer / ISO-8601 and the subset is
safe.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from ccai.pychestrate.webservice.jobs.envelope.errors import (
    EnvelopeSerializationError,
    EnvelopeSchemaVersionError,
)
from ccai.pychestrate.webservice.jobs.envelope.schema import (
    DEFAULT_JOB_KIND,
    JobDeadline,
    JobEnvelope,
    JobForwardingInfo,
    JobPipelineRef,
    JobRefs,
    JobResultsLocator,
    JobSourceRef,
    ScopedSecret,
    SUPPORTED_JOB_KINDS,
    SUPPORTED_SCHEMA_VERSIONS,
    assert_required_fields_present,
)


def envelope_to_dict(*, envelope: JobEnvelope) -> Dict[str, Any]:
    """
        Convert a :class:`JobEnvelope` to a JSON-serializable dict.
        Nested dataclasses are expanded recursively; ``datetime``
        fields are rendered as RFC 3339 UTC strings with microsecond
        precision.

        :param envelope: Structured envelope instance.

        :returns: Dict safe to pass through :func:`serialize_canonical`.
    """
    rtnval: Dict[str, Any] = {
        "schema_version": envelope.schema_version,
        "envelope_id": envelope.envelope_id,
        "issued_at": _iso_utc(envelope.issued_at),
        "issuer": envelope.issuer,
        "project_id": envelope.project_id,
        "job_id": envelope.job_id,
        "job_name": envelope.job_name,
        "job_type": envelope.job_type,
        "job_kind": envelope.job_kind,
        "pipeline": _pipeline_to_dict(pipeline=envelope.pipeline),
        "source": _source_to_dict(source=envelope.source),
        "run_id": envelope.run_id,
        "client_id": envelope.client_id,
        "pod_id": envelope.pod_id,
        "refs": asdict(envelope.refs),
        "params": dict(envelope.params),
        "scoped_secrets": [_scoped_secret_to_dict(ss=ss) for ss in envelope.scoped_secrets],
        "results": asdict(envelope.results),
        "forwarding": asdict(envelope.forwarding),
        "deadline": {
            "soft_deadline_at": _iso_utc(envelope.deadline.soft_deadline_at),
            "hard_deadline_at": _iso_utc(envelope.deadline.hard_deadline_at),
        },
        "extension_claims": dict(envelope.extension_claims),
    }
    return rtnval


def dict_to_envelope(*, candidate: Dict[str, Any]) -> JobEnvelope:
    """
        Re-hydrate a canonical envelope dict into a
        :class:`JobEnvelope` instance. Every required field is
        validated; unknown top-level keys are rejected.

        :param candidate: Dict produced by :func:`envelope_to_dict` or
                          an equivalent deserializer.

        :returns: Populated :class:`JobEnvelope`.
        :raises: EnvelopeSerializationError when top-level keys are
                 unexpected; EnvelopeSchemaVersionError when
                 ``schema_version`` is unsupported; SemanticError when
                 a required field is missing.
    """
    assert_required_fields_present(candidate=candidate)

    schema_version = candidate["schema_version"]
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        err_lines = ["JobEnvelope schema_version is not supported by this service."]
        err_lines.append("ENVELOPE_VERSION: {}".format(schema_version))
        err_lines.append("SUPPORTED: {}".format(list(SUPPORTED_SCHEMA_VERSIONS)))
        err_msg = os.linesep.join(err_lines)
        raise EnvelopeSchemaVersionError(err_msg) from None

    allowed_keys = set(_envelope_to_dict_keys())
    actual_keys = set(candidate.keys())
    extras = actual_keys - allowed_keys
    if len(extras) > 0:
        err_lines = ["JobEnvelope carries unexpected top-level keys."]
        err_lines.append("UNEXPECTED: {}".format(sorted(extras)))
        err_lines.append("ALLOWED: {}".format(sorted(allowed_keys)))
        err_msg = os.linesep.join(err_lines)
        raise EnvelopeSerializationError(err_msg) from None

    # ``job_kind`` is an optional top-level field. Envelopes minted
    # before the discriminator was introduced omit it entirely; those
    # parse back as ``test`` so the existing test-run loop is unaffected.
    job_kind = candidate.get("job_kind", DEFAULT_JOB_KIND)
    if job_kind is None:
        job_kind = DEFAULT_JOB_KIND
    if job_kind not in SUPPORTED_JOB_KINDS:
        err_lines = ["JobEnvelope job_kind is not a recognized job class."]
        err_lines.append("JOB_KIND: {}".format(job_kind))
        err_lines.append("SUPPORTED: {}".format(list(SUPPORTED_JOB_KINDS)))
        err_msg = os.linesep.join(err_lines)
        raise EnvelopeSerializationError(err_msg) from None

    refs = JobRefs(**candidate["refs"])
    results = JobResultsLocator(**candidate["results"])
    forwarding = JobForwardingInfo(**candidate["forwarding"])

    pipeline_raw = candidate.get("pipeline", None)
    pipeline = None
    if pipeline_raw is not None:
        pipeline = JobPipelineRef(**pipeline_raw)

    # ``source`` is an optional top-level field. Envelopes minted
    # before the structured source block was introduced omit it
    # entirely; those parse back with ``source=None`` so the
    # client's ``runner_inputs.git_url`` fallback still applies.
    source_raw = candidate.get("source", None)
    source = None
    if source_raw is not None:
        source = JobSourceRef(**source_raw)

    scoped_secrets = tuple(
        ScopedSecret(
            name=item["name"],
            value=item["value"],
            expires_at=_parse_iso(raw=item["expires_at"]),
            token_type=item["token_type"],
        )
        for item in candidate["scoped_secrets"]
    )

    deadline_raw = candidate["deadline"]
    deadline = JobDeadline(
        soft_deadline_at=_parse_iso(raw=deadline_raw["soft_deadline_at"]),
        hard_deadline_at=_parse_iso(raw=deadline_raw["hard_deadline_at"]),
    )

    rtnval = JobEnvelope(
        schema_version=schema_version,
        envelope_id=candidate["envelope_id"],
        issued_at=_parse_iso(raw=candidate["issued_at"]),
        issuer=candidate["issuer"],
        project_id=candidate["project_id"],
        job_id=candidate["job_id"],
        job_name=candidate["job_name"],
        job_type=candidate["job_type"],
        job_kind=job_kind,
        pipeline=pipeline,
        source=source,
        run_id=candidate["run_id"],
        client_id=candidate["client_id"],
        pod_id=candidate["pod_id"],
        refs=refs,
        params=dict(candidate["params"]),
        scoped_secrets=scoped_secrets,
        results=results,
        forwarding=forwarding,
        deadline=deadline,
        extension_claims=dict(candidate["extension_claims"]),
    )
    return rtnval


def serialize_canonical(*, envelope: JobEnvelope) -> bytes:
    """
        Produce the canonical JSON bytes for an envelope. Uses
        UTF-16-ordered keys, no whitespace, and the Python JSON
        encoder's default escape rules — sufficient for our
        ASCII-dominated payload set in M1.

        :param envelope: Envelope to serialize.

        :returns: UTF-8 encoded canonical bytes.
    """
    as_dict = envelope_to_dict(envelope=envelope)
    rtnval = json.dumps(
        as_dict,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return rtnval


def parse_canonical(*, canonical_bytes: bytes) -> JobEnvelope:
    """
        Reverse of :func:`serialize_canonical`.

        :param canonical_bytes: UTF-8 encoded canonical JSON.

        :returns: :class:`JobEnvelope` instance.
        :raises: EnvelopeSerializationError on malformed payload;
                 EnvelopeSchemaVersionError on unsupported version.
    """
    try:
        text = canonical_bytes.decode("utf-8")
    except UnicodeDecodeError as xcpt:
        err_lines = ["JobEnvelope canonical payload is not valid UTF-8."]
        err_lines.append("REASON: {}".format(str(xcpt)))
        err_msg = os.linesep.join(err_lines)
        raise EnvelopeSerializationError(err_msg) from xcpt

    try:
        candidate = json.loads(text)
    except json.JSONDecodeError as xcpt:
        err_lines = ["JobEnvelope canonical payload is not valid JSON."]
        err_lines.append("REASON: {}".format(str(xcpt)))
        err_msg = os.linesep.join(err_lines)
        raise EnvelopeSerializationError(err_msg) from xcpt

    rtnval = dict_to_envelope(candidate=candidate)
    return rtnval


def _envelope_to_dict_keys() -> list:
    """
        Enumerate every key produced by :func:`envelope_to_dict`.
        Used by :func:`dict_to_envelope` to reject unknown keys.

        :returns: Sorted list of the top-level key names.
    """
    rtnval = [
        "schema_version",
        "envelope_id",
        "issued_at",
        "issuer",
        "project_id",
        "job_id",
        "job_name",
        "job_type",
        "job_kind",
        "pipeline",
        "source",
        "run_id",
        "client_id",
        "pod_id",
        "refs",
        "params",
        "scoped_secrets",
        "results",
        "forwarding",
        "deadline",
        "extension_claims",
    ]
    return rtnval


def _pipeline_to_dict(*, pipeline) -> Any:
    """
        Convert an optional :class:`JobPipelineRef` to its dict form
        (or ``None``). Broken out so the top-level serializer stays
        readable.

        :param pipeline: Optional pipeline reference.

        :returns: Dict or ``None``.
    """
    if pipeline is None:
        return None
    rtnval = asdict(pipeline)
    return rtnval


def _source_to_dict(*, source) -> Any:
    """
        Convert an optional :class:`JobSourceRef` to its dict form
        (or ``None``). Broken out so the top-level serializer stays
        readable and so envelopes without a resolved source
        integration round-trip with an explicit ``null``.

        :param source: Optional source reference.

        :returns: Dict or ``None``.
    """
    if source is None:
        return None
    rtnval = asdict(source)
    return rtnval


def _scoped_secret_to_dict(*, ss: ScopedSecret) -> Dict[str, Any]:
    """
        Convert a :class:`ScopedSecret` to its dict form with the
        timestamp normalized.

        :param ss: Scoped secret entry.

        :returns: JSON-serializable dict.
    """
    rtnval = {
        "name": ss.name,
        "value": ss.value,
        "expires_at": _iso_utc(ss.expires_at),
        "token_type": ss.token_type,
    }
    return rtnval


def _iso_utc(dt: datetime) -> str:
    """
        Render a datetime as an RFC 3339 UTC string. Naive datetimes
        are treated as UTC (a pragmatic choice for M1 — M2 will tighten
        this to raise when a naive datetime reaches serialization).

        :param dt: Datetime (naive or tz-aware).

        :returns: RFC 3339 UTC string.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    normalized = dt.astimezone(timezone.utc)
    rtnval = normalized.isoformat().replace("+00:00", "Z")
    return rtnval


def _parse_iso(*, raw: str) -> datetime:
    """
        Parse an RFC 3339 UTC string back to a tz-aware datetime.

        :param raw: ISO-formatted timestamp string.

        :returns: tz-aware datetime in UTC.
        :raises: EnvelopeSerializationError on malformed input.
    """
    if raw is None or len(raw) == 0:
        err_msg = "datetime field is empty"
        raise EnvelopeSerializationError(err_msg) from None
    normalized = raw
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        rtnval = datetime.fromisoformat(normalized)
    except ValueError as xcpt:
        err_lines = ["datetime field did not parse as ISO 8601."]
        err_lines.append("VALUE: {}".format(raw))
        err_lines.append("REASON: {}".format(str(xcpt)))
        err_msg = os.linesep.join(err_lines)
        raise EnvelopeSerializationError(err_msg) from xcpt
    if rtnval.tzinfo is None:
        rtnval = rtnval.replace(tzinfo=timezone.utc)
    return rtnval
