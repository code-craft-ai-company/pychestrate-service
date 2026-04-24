"""
.. module:: jobs.envelope.codec
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: EnvelopeCodec — build / sign / parse / verify facade.

.. moduleauthor:: Automation Mojo LLC

The codec is the single entry point callers use to turn dispatch
inputs into a :class:`SignedJobEnvelope`, archive it, and — on the
receiving side — verify and parse. The design deliberately keeps the
codec thin: structural validation lives in :mod:`schema`, canonical
bytes in :mod:`canonical`, and Ed25519 in :mod:`signer`. The codec
stitches them together and keeps the service-wide defaults (issuer
string, max age, envelope-id generation) in one place.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import uuid

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from automojo.pychestrate.webservice.jobs.envelope import canonical, signer
from automojo.pychestrate.webservice.jobs.envelope.errors import (
    EnvelopeSerializationError,
)
from automojo.pychestrate.webservice.jobs.envelope.schema import (
    ENVELOPE_SCHEMA_VERSION,
    JobDeadline,
    JobEnvelope,
    JobForwardingInfo,
    JobPipelineRef,
    JobRefs,
    JobResultsLocator,
    ScopedSecret,
    assert_required_fields_present,
)


DEFAULT_MAX_ENVELOPE_AGE_SECONDS: int = 300


@dataclass(frozen=True)
class DispatchRequest:
    """
        Callable-supplied bundle that drives :func:`build`. The request
        captures everything the dispatcher has resolved — refs, params,
        scoped-secret mints, results backend path, forwarding URLs,
        deadlines — and leaves the codec to enforce field presence and
        canonicalize.

        :param project_id: Owning project UUID.
        :param job_id: Job-catalog UUID.
        :param job_name: Human-readable job identifier.
        :param job_type: Job-type string.
        :param run_id: Server-assigned run UUID.
        :param client_id: Registered client UUID.
        :param pod_id: Target pod UUID.
        :param issuer: Fully-qualified issuer string.
        :param pipeline: Optional pipeline reference.
        :param refs: Build / branch / commit references.
        :param params: JSON-serializable parameter map.
        :param scoped_secrets: Tuple of materialized short-lived creds.
        :param results: Results-backend path + driver.
        :param forwarding: Live progress / summary endpoints.
        :param deadline: Soft + hard deadlines.
        :param extension_claims: Extension-contributed claims (empty
                                 on M1).
    """
    project_id: str
    job_id: str
    job_name: str
    job_type: str
    run_id: str
    client_id: str
    pod_id: str
    issuer: str
    pipeline: Optional[JobPipelineRef]
    refs: JobRefs
    params: Dict[str, Any]
    scoped_secrets: Tuple[ScopedSecret, ...]
    results: JobResultsLocator
    forwarding: JobForwardingInfo
    deadline: JobDeadline
    extension_claims: Dict[str, Any]


@dataclass(frozen=True)
class SignedJobEnvelope:
    """
        An envelope plus its detached signature and ``key_id``.

        :param envelope: The unsigned :class:`JobEnvelope`.
        :param canonical_payload: Canonical bytes the signature was
                                  computed over.
        :param signature: Detached Ed25519 signature.
        :param key_id: Identifier of the signing key (JWKS lookup).
        :param signed_at: UTC moment :func:`sign` ran.
    """
    envelope: JobEnvelope
    canonical_payload: bytes
    signature: bytes
    key_id: str
    signed_at: datetime


def build(*, request: DispatchRequest) -> JobEnvelope:
    """
        Construct a :class:`JobEnvelope` from a :class:`DispatchRequest`.
        Assigns a fresh ``envelope_id`` and ``issued_at``; validates
        that every required field is supplied.

        :param request: Populated :class:`DispatchRequest`.

        :returns: Unsigned :class:`JobEnvelope`.
        :raises: SemanticError when a required field is missing.
    """
    now = datetime.now(timezone.utc)
    envelope_id = str(uuid.uuid4())
    envelope = JobEnvelope(
        schema_version=ENVELOPE_SCHEMA_VERSION,
        envelope_id=envelope_id,
        issued_at=now,
        issuer=request.issuer,
        project_id=request.project_id,
        job_id=request.job_id,
        job_name=request.job_name,
        job_type=request.job_type,
        pipeline=request.pipeline,
        run_id=request.run_id,
        client_id=request.client_id,
        pod_id=request.pod_id,
        refs=request.refs,
        params=dict(request.params),
        scoped_secrets=tuple(request.scoped_secrets),
        results=request.results,
        forwarding=request.forwarding,
        deadline=request.deadline,
        extension_claims=dict(request.extension_claims),
    )
    # Validate via the dict shape so missing fields surface identically
    # whether the caller built a dict or a DispatchRequest.
    candidate = canonical.envelope_to_dict(envelope=envelope)
    assert_required_fields_present(candidate=candidate)
    return envelope


def sign(*, envelope: JobEnvelope) -> SignedJobEnvelope:
    """
        Serialize the envelope to canonical bytes and produce a
        detached Ed25519 signature with the active key.

        :param envelope: Envelope returned by :func:`build`.

        :returns: :class:`SignedJobEnvelope`.
        :raises: EnvelopeSigningKeyMissingError when no key is
                 installed.
    """
    payload = canonical.serialize_canonical(envelope=envelope)
    handle = signer.get_active_signing_key()
    signature_bytes = signer.sign(payload=payload)
    rtnval = SignedJobEnvelope(
        envelope=envelope,
        canonical_payload=payload,
        signature=signature_bytes,
        key_id=handle.key_id,
        signed_at=datetime.now(timezone.utc),
    )
    return rtnval


def parse(*, canonical_payload: bytes) -> JobEnvelope:
    """
        Parse canonical bytes back into a :class:`JobEnvelope`.

        :param canonical_payload: UTF-8 encoded canonical JSON.

        :returns: Envelope instance.
        :raises: EnvelopeSerializationError, EnvelopeSchemaVersionError.
    """
    rtnval = canonical.parse_canonical(canonical_bytes=canonical_payload)
    return rtnval


def verify(
        *,
        signed: SignedJobEnvelope,
        max_age_seconds: int = DEFAULT_MAX_ENVELOPE_AGE_SECONDS,
        now: Optional[datetime] = None
    ) -> signer.VerificationResult:
    """
        Verify the detached signature on ``signed`` against the
        JWKS-style verify set AND check the signed-at age against
        ``max_age_seconds``. Returns a structured result rather than
        raising so transport callers can log the reason.

        :param signed: :class:`SignedJobEnvelope`.
        :param max_age_seconds: Maximum allowed age in seconds.
        :param now: Optional override for the current time (tests).

        :returns: :class:`VerificationResult`.
    """
    effective_now = now
    if effective_now is None:
        effective_now = datetime.now(timezone.utc)
    age_cutoff = effective_now - timedelta(seconds=max_age_seconds)
    if signed.signed_at < age_cutoff:
        rtnval = signer.VerificationResult(valid=False, reason="expired")
        return rtnval

    rtnval = signer.verify(
        payload=signed.canonical_payload,
        signature=signed.signature,
        key_id=signed.key_id,
    )
    return rtnval
