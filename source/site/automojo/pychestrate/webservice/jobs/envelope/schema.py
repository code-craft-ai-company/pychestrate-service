"""
.. module:: jobs.envelope.schema
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: JobEnvelope dataclass + required-field validation.

.. moduleauthor:: Automation Mojo LLC

The :class:`JobEnvelope` dataclass is the canonical shape that
Pychestrate emits and pod client agents parse. Every required field in
Requirement 1 of ``specs/5-job-envelope/requirements.md`` is modeled
here; extension-contributed claims land in ``extension_claims`` and
are forbidden from colliding with top-level field names at build time.

The schema version is a service-wide constant. A caller that reads an
envelope whose ``schema_version`` is outside
``SUPPORTED_SCHEMA_VERSIONS`` gets :class:`EnvelopeSchemaVersionError`;
the codec never silently upgrades or downgrades a payload.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Tuple


ENVELOPE_SCHEMA_VERSION: str = "2026-04-24"
SUPPORTED_SCHEMA_VERSIONS: Tuple[str, ...] = (ENVELOPE_SCHEMA_VERSION,)

# Discriminator values for the ``job_kind`` field. One envelope type
# carries every orchestration job class; the client's runner-resolution
# branches on ``job_kind`` first, then ``job_type``. ``test`` is the
# back-compat default so envelopes minted before the discriminator was
# introduced (or by callers that never set it) still parse cleanly.
JOB_KIND_TEST: str = "test"
JOB_KIND_BUILD: str = "build"
JOB_KIND_PROVISION: str = "provision"
SUPPORTED_JOB_KINDS: Tuple[str, ...] = (
    JOB_KIND_TEST,
    JOB_KIND_BUILD,
    JOB_KIND_PROVISION,
)
DEFAULT_JOB_KIND: str = JOB_KIND_TEST


@dataclass(frozen=True)
class JobRefs:
    """
        Source / build reference tuple carried on every envelope.

        :param branch: SCM branch name.
        :param build: Build identifier (e.g. ``"build-4421"``).
        :param flavor: Build flavor / configuration string.
        :param release: Release identifier / tag.
        :param commit_sha: Full-length commit hash for reproducibility.
    """
    branch: str
    build: str
    flavor: str
    release: str
    commit_sha: str


@dataclass(frozen=True)
class JobPipelineRef:
    """
        Optional pipeline instance reference. A job that is NOT part
        of a pipeline leaves this block ``None`` on the envelope.

        :param pipeline_id: Pipeline definition identifier.
        :param instance_id: Pipeline-run instance identifier.
    """
    pipeline_id: str
    instance_id: str


@dataclass(frozen=True)
class JobResultsLocator:
    """
        Where the client should write its result tree.

        :param backend_key_prefix: Per-run path allocated by the
                                   shared results backend.
        :param backend_driver: Driver name (``"smb"``, ``"s3"``, etc.)
                               — resolves through the
                               ``object_store_driver`` factory.
    """
    backend_key_prefix: str
    backend_driver: str


@dataclass(frozen=True)
class JobForwardingInfo:
    """
        Where the client should POST live progress summaries.
        Matches testbase's ``ForwardingInfo`` shape.

        :param progress_url: Absolute URL the client POSTs progress to.
        :param summary_url: Absolute URL for the final summary POST.
        :param auth_method: Either ``"bearer"`` or ``"mtls"``.
    """
    progress_url: str
    summary_url: str
    auth_method: str


@dataclass(frozen=True)
class JobDeadline:
    """
        Soft + hard deadlines the client agent honors.

        :param soft_deadline_at: After this, warn; progress may still
                                 continue.
        :param hard_deadline_at: After this, the client SHALL abort
                                 and report failure.
    """
    soft_deadline_at: datetime
    hard_deadline_at: datetime


@dataclass(frozen=True)
class ScopedSecret:
    """
        One short-lived credential materialized into the envelope.
        The envelope codec never persists the plaintext — it carries
        only what the client agent needs to make authenticated calls
        during the job's lifetime.

        :param name: Symbolic name the job references
                     (e.g. ``"ARTIFACT_UPLOAD_TOKEN"``).
        :param value: The short-lived credential value.
        :param expires_at: When the credential stops working (TTL
                           capped at ``hard_deadline_at + 300 s`` by
                           the dispatcher; schema does not enforce
                           the cap).
        :param token_type: ``"bearer"``, ``"vault-lease"``, etc.
    """
    name: str
    value: str
    expires_at: datetime
    token_type: str


@dataclass(frozen=True)
class JobEnvelope:
    """
        Canonical dispatch envelope shape. Every field in
        Requirement 1 AC #1 of
        ``specs/5-job-envelope/requirements.md`` is present. Extension
        claims live in ``extension_claims`` — the dict is empty on an
        M1 envelope.

        :param schema_version: Protocol version; clients that do not
                               recognize it fail the envelope.
        :param envelope_id: UUIDv7-style envelope id, unique per
                            dispatch.
        :param issued_at: UTC timestamp the service built the
                          envelope.
        :param issuer: Service DNS name + release string, e.g.
                       ``"pychestrate.example.com/0.3.1"``.
        :param project_id: Owning project UUID.
        :param job_id: Job-catalog UUID.
        :param job_name: Human-readable job identifier.
        :param job_kind: Job-class discriminator
                         (``"test"`` / ``"build"`` / ``"provision"``).
                         The client branches on this before resolving
                         the kind-specific runner; ``params`` then
                         carries the kind-specific payload. Defaults to
                         ``"test"`` for backward compatibility with
                         envelopes minted before the discriminator was
                         introduced.
        :param job_type: Job-type string consumed by the client's
                         runner resolution (``"testbase-singlehost"``,
                         ``"ansible-playbook"``, …).
        :param pipeline: Optional :class:`JobPipelineRef` when the
                         job is part of a pipeline.
        :param run_id: Server-assigned run UUID the client MUST echo
                       in progress and result submissions.
        :param client_id: Registered client UUID owning the pod.
        :param pod_id: Pod UUID the client is managing.
        :param refs: :class:`JobRefs` carrying build / branch / commit
                     reference.
        :param params: Caller-supplied typed parameter map. Must be
                       JSON-serializable.
        :param scoped_secrets: List of :class:`ScopedSecret` entries
                               materialized at dispatch time.
        :param results: :class:`JobResultsLocator` the client writes
                        its result tree to.
        :param forwarding: :class:`JobForwardingInfo` pointing at the
                           live progress / summary endpoints.
        :param deadline: :class:`JobDeadline` soft + hard deadlines.
        :param extension_claims: Dict keyed by
                                 ``EnvelopeFieldExtension.field_name``;
                                 empty on M1.
    """
    schema_version: str
    envelope_id: str
    issued_at: datetime
    issuer: str
    project_id: str
    job_id: str
    job_name: str
    job_type: str
    pipeline: Optional[JobPipelineRef]
    run_id: str
    client_id: str
    pod_id: str
    refs: JobRefs
    params: Dict[str, Any]
    scoped_secrets: Tuple[ScopedSecret, ...]
    results: JobResultsLocator
    forwarding: JobForwardingInfo
    deadline: JobDeadline
    extension_claims: Dict[str, Any]
    job_kind: str = DEFAULT_JOB_KIND


REQUIRED_TOP_LEVEL_FIELDS: Tuple[str, ...] = (
    "schema_version",
    "envelope_id",
    "issued_at",
    "issuer",
    "project_id",
    "job_id",
    "job_name",
    "job_type",
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
)


def assert_required_fields_present(
        *,
        candidate: Dict[str, Any]
    ) -> None:
    """
        Verify every top-level required field is present and non-empty
        in ``candidate``. Missing fields are collected into a single
        error message rather than failing on the first one so callers
        can fix multiple problems in a single pass.

        :param candidate: Dict representation of a candidate envelope.

        :returns: None.
        :raises: SemanticError naming every missing field.
    """
    from automojo.errors.exceptions import SemanticError

    missing = []
    for name in REQUIRED_TOP_LEVEL_FIELDS:
        if name not in candidate:
            missing.append(name)
            continue
        value = candidate[name]
        if value is None:
            missing.append(name)

    if len(missing) == 0:
        return

    err_lines = ["JobEnvelope construction missing required fields."]
    err_lines.append("MISSING: ({})".format(len(missing)))
    for name in missing:
        err_lines.append("    {}".format(name))
    err_lines.append("EXPECTED: {}".format(list(REQUIRED_TOP_LEVEL_FIELDS)))
    err_msg = os.linesep.join(err_lines)
    raise SemanticError(err_msg) from None
