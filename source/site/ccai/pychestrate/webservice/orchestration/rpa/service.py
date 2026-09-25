"""
.. module:: orchestration.rpa.service
    :synopsis: 6-rpa-orchestration facade — job type registry, project
               specifications, and work-packet triggers that mint a
               ``job_kind=rpa`` envelope and dispatch it through Layer 5.

.. moduleauthor:: Code Craft AI LLC

The service mirrors :mod:`orchestration.build.service`: a caller
(REST route, web page, watch, pipeline step) invokes
:func:`trigger_job`; the service merges and validates the work packet,
resolves the job type version, persists an :class:`RpaJob`, creates the
Layer-5 run-state row, builds the signed envelope, and dispatches it
through the :class:`JobDispatcher` published on
:func:`set_active_job_dispatcher`. Terminal outcomes arrive through
:func:`apply_run_terminal` from the result-ingest completion path.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.jobs.cancel.client_cancel import (
    queue_client_cancel,
    resolve_cancel_target_client,
)
from ccai.pychestrate.webservice.jobs.dispatch import (
    DispatchRequestInputs,
    JobDispatcher,
)
from ccai.pychestrate.webservice.jobs.dispatch.errors import DispatchError
from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from ccai.pychestrate.webservice.jobs.envelope import (
    JOB_KIND_RPA,
    JobDeadline,
    JobForwardingInfo,
    JobRefs,
    JobResultsLocator,
    JobSourceRef,
)
from ccai.pychestrate.webservice.jobs.results import SharedResultsBackend
from ccai.pychestrate.webservice.jobs.run.state import (
    RunEvent,
    RunNotFoundError as RunStateNotFoundError,
    create_run as create_run_state,
    get_snapshot as get_run_state_snapshot,
    transition as transition_run_state,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.orchestration.rpa import repository
from ccai.pychestrate.webservice.orchestration.rpa.errors import (
    CapabilityMismatchError,
    DuplicateRpaJobTypeError,
    DuplicateRpaSpecError,
    DuplicateVersionError,
    RpaDispatchFailedError,
    RpaDispatchUnavailableError,
    RpaJobNotCancellableError,
    RpaJobNotFoundError,
    RpaJobTypeInvalidError,
    RpaJobTypeNotFoundError,
    RpaJobTypeRetiredError,
    RpaSpecInvalidError,
    RpaSpecNotFoundError,
    RpaVersionNotActiveError,
    RpaVersionNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.rpa.events import RpaEventTopics
from ccai.pychestrate.webservice.orchestration.rpa.factories.execution_mode_protocol import (
    RPA_EXECUTION_MODE_PROTOCOL,
    RpaExecutionModeProtocol,
)
from ccai.pychestrate.webservice.orchestration.rpa.factories.job_type_protocol import (
    RPA_JOB_TYPE_PROTOCOL,
    RpaJobTypeProtocol,
)
from ccai.pychestrate.webservice.orchestration.rpa.models import (
    VERSION_SELECTOR_LATEST_ACTIVE,
    RpaExecutionMode,
    RpaJob,
    RpaJobStatus,
    RpaJobType,
    RpaJobTypeState,
    RpaJobTypeVersion,
    RpaSourceKind,
    RpaSpec,
    RpaVersionState,
)
from ccai.pychestrate.webservice.orchestration.rpa.packet import (
    DEFAULT_MAX_PACKET_BYTES,
    canonical_project_uuid,
    enforce_packet_size,
    is_valid_type_id,
    merge_packet,
    packet_digest,
    redact_packet,
    validate_packet,
    validate_schema_document,
)


_LOGGER = logging.getLogger("pychestrate.rpa.service")

RPA_JOB_TYPE_PREFIX: str = "rpa-"
DEFAULT_RPA_ISSUER: str = "pychestrate.example.com/0.6.0"
DEFAULT_RPA_SOFT_DEADLINE_SECONDS: int = 3600
DEFAULT_RPA_HARD_DEADLINE_SECONDS: int = 7200
DEFAULT_IDEMPOTENCY_WINDOW_SECONDS: int = 60
LIST_JOBS_DEFAULT_LIMIT: int = 50
RPA_ACTOR: str = "system:rpa-orchestrator"

TERMINAL_STATUSES: Tuple[RpaJobStatus, ...] = (
    RpaJobStatus.SUCCEEDED,
    RpaJobStatus.FAILED,
    RpaJobStatus.TIMEOUT,
    RpaJobStatus.CANCELLED,
)
ACTIVE_STATUSES: Tuple[RpaJobStatus, ...] = (
    RpaJobStatus.PENDING,
    RpaJobStatus.DISPATCHING,
    RpaJobStatus.RUNNING,
)

#: Module-level seams the runtime bootstrap publishes.
ACTIVE_JOB_DISPATCHER: Optional[JobDispatcher] = None
ACTIVE_RESULTS_BACKEND: Optional[SharedResultsBackend] = None


def set_active_job_dispatcher(*, dispatcher: Optional[JobDispatcher]) -> None:
    """
        Publish the :class:`JobDispatcher` :func:`trigger_job` uses.
    """
    global ACTIVE_JOB_DISPATCHER
    ACTIVE_JOB_DISPATCHER = dispatcher
    return


def set_active_results_backend(*, backend: Optional[SharedResultsBackend]) -> None:
    """
        Publish the shared results backend used to allocate the
        per-job result prefix.
    """
    global ACTIVE_RESULTS_BACKEND
    ACTIVE_RESULTS_BACKEND = backend
    return


# ---------------------------------------------------------------------------
# IO shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RpaJobTypeInputs:
    """
        Caller-supplied job type registration.
    """
    type_id: str
    display_name: str
    description: str = ""
    execution_mode: str = RpaExecutionMode.PROCESS.value
    capability_requirements: Sequence[str] = ()
    packet_schema: Optional[Mapping[str, Any]] = None
    secret_fields: Sequence[str] = ()


@dataclass(frozen=True)
class RpaVersionInputs:
    """
        Caller-supplied version publication.
    """
    version: str
    source_kind: str = RpaSourceKind.GIT.value
    source_ref: str = ""
    entrypoint: Mapping[str, Any] = field(default_factory=dict)
    environment: Mapping[str, str] = field(default_factory=dict)
    timeout_minutes: int = 60


@dataclass(frozen=True)
class RpaSpecInputs:
    """
        Caller-supplied specification.
    """
    name: str
    type_id: str
    version_selector: str = VERSION_SELECTOR_LATEST_ACTIVE
    default_packet: Mapping[str, Any] = field(default_factory=dict)
    target_pod_id: Optional[str] = None
    required_capabilities: Sequence[str] = ()
    timeout_minutes: Optional[int] = None
    description: str = ""


@dataclass(frozen=True)
class RpaTriggerAspects:
    """
        Caller-tunable trigger knobs.

        :param actor_id: Principal id persisted on the job.
        :param candidates: Eligible dispatch candidates. Empty means
                           "no eligible pod" and yields
                           :class:`RpaDispatchFailedError`.
        :param project_slug: Sanitised into the results prefix.
        :param trigger_cause: ``{"kind": "manual" | "api" | "watch"
                             | "pipeline", ...}`` recorded on the job.
        :param idempotency_key: Caller key; ``None`` derives one from
                                ``(project, spec, packet digest,
                                cause kind)``.
    """
    actor_id: Optional[str] = None
    candidates: Sequence[DispatchCandidate] = field(default_factory=tuple)
    project_slug: str = ""
    issuer: str = DEFAULT_RPA_ISSUER
    soft_deadline_seconds: int = DEFAULT_RPA_SOFT_DEADLINE_SECONDS
    hard_deadline_seconds: int = DEFAULT_RPA_HARD_DEADLINE_SECONDS
    trigger_cause: Mapping[str, Any] = field(default_factory=lambda: {"kind": "manual"})
    idempotency_key: Optional[str] = None
    idempotency_window_seconds: int = DEFAULT_IDEMPOTENCY_WINDOW_SECONDS
    max_packet_bytes: int = DEFAULT_MAX_PACKET_BYTES


@dataclass(frozen=True)
class RpaJobTypeVersionView:
    version_id: str
    type_id: str
    version: str
    source_kind: str
    source_ref: str
    entrypoint: Mapping[str, Any]
    environment: Mapping[str, str]
    timeout_minutes: int
    state: RpaVersionState
    published_by_id: Optional[str]
    published_at: Optional[datetime]


@dataclass(frozen=True)
class RpaJobTypeView:
    type_id: str
    display_name: str
    description: str
    execution_mode: RpaExecutionMode
    capability_requirements: Tuple[str, ...]
    packet_schema: Optional[Mapping[str, Any]]
    secret_fields: Tuple[str, ...]
    state: RpaJobTypeState
    created_by_id: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    versions: Tuple[RpaJobTypeVersionView, ...] = ()
    active_version_count: int = 0
    latest_active_version: Optional[str] = None


@dataclass(frozen=True)
class RpaSpecView:
    spec_id: str
    project_id: str
    name: str
    type_id: str
    type_display_name: str
    execution_mode: RpaExecutionMode
    version_selector: str
    default_packet: Mapping[str, Any]
    target_pod_id: Optional[str]
    required_capabilities: Tuple[str, ...]
    timeout_minutes: Optional[int]
    description: str
    revision: int
    created_by_id: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    packet_schema: Optional[Mapping[str, Any]] = None
    resolved_version: Optional[str] = None
    # Packet paths the job type declares secret. ``default_packet``
    # above is the stored value (needed for merging); anything that
    # shows or returns it must redact these paths first.
    secret_fields: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RpaJobView:
    job_id: str
    project_id: str
    spec_id: Optional[str]
    spec_name: str
    spec_revision: int
    type_id: str
    resolved_version: str
    execution_mode: RpaExecutionMode
    work_packet: Mapping[str, Any]
    packet_digest: str
    status: RpaJobStatus
    exit_code: Optional[int]
    dispatch_attempt_id: Optional[str]
    envelope_id: Optional[str]
    client_id: Optional[str]
    pod_id: Optional[str]
    triggered_by_id: Optional[str]
    trigger_cause: Mapping[str, Any]
    result_root_key: Optional[str]
    final_state_reason: str
    created_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    run_state: Optional[str] = None
    duration_seconds: Optional[int] = None
    # True when trigger_job found an identical run inside the idempotency
    # window and returned that job instead of starting a new one.
    replayed: bool = False


@dataclass(frozen=True)
class RpaJobListView:
    jobs: Tuple[RpaJobView, ...]
    total: int
    offset: int
    limit: int


# ---------------------------------------------------------------------------
# Execution-mode drivers
# ---------------------------------------------------------------------------


def list_execution_modes() -> Tuple[Type[RpaExecutionModeProtocol], ...]:
    """
        Registered execution-mode drivers, precedence order.
    """
    rtnval = list_factory_implementations(
        factory_protocol_name=RPA_EXECUTION_MODE_PROTOCOL,
    )
    return rtnval


def list_code_defined_job_types() -> Tuple[Type[RpaJobTypeProtocol], ...]:
    """
        Registered ``rpa_job_type`` implementations (code-defined types).
    """
    rtnval = list_factory_implementations(factory_protocol_name=RPA_JOB_TYPE_PROTOCOL)
    return rtnval


def sync_code_defined_job_types(*, db_session: DbSession) -> List[str]:
    """
        Mirror every code-defined job type into the registry tables.

        A type the database already knows keeps its administrator-set
        fields (database wins); versions the database lacks are added,
        versions it has are left untouched. Invalid implementations are
        logged and skipped so one bad extension cannot break the
        registry.

        :returns: The type ids that were created or gained versions.
    """
    changed: List[str] = []
    for impl in list_code_defined_job_types():
        try:
            type_id = str(impl.type_id())
            row = repository.find_job_type(db_session=db_session, type_id=type_id)
            if row is None:
                register_job_type(
                    db_session=db_session,
                    inputs=RpaJobTypeInputs(
                        type_id=type_id,
                        display_name=str(impl.display_name()),
                        description=str(impl.description() or ""),
                        execution_mode=str(impl.execution_mode()),
                        capability_requirements=tuple(impl.capability_requirements() or ()),
                        packet_schema=impl.packet_schema(),
                        secret_fields=tuple(impl.secret_fields() or ()),
                    ),
                    actor_id="extension:{}.{}".format(impl.__module__, impl.__name__),
                )
                changed.append(type_id)
            elif row.state == RpaJobTypeState.RETIRED:
                _LOGGER.info(
                    "pychestrate.rpa.code_defined.skipped_retired type_id=%s implementation=%s",
                    type_id, impl.__name__,
                )
                continue
            for spec in impl.versions() or ():
                existing = repository.find_version(
                    db_session=db_session, type_id=type_id, version=str(spec.version),
                )
                if existing is not None:
                    continue
                publish_version(
                    db_session=db_session,
                    type_id=type_id,
                    inputs=RpaVersionInputs(
                        version=str(spec.version),
                        source_kind=str(spec.source_kind),
                        source_ref=str(spec.source_ref or ""),
                        entrypoint=dict(spec.entrypoint or {}),
                        environment=dict(spec.environment or {}),
                        timeout_minutes=int(spec.timeout_minutes or 60),
                    ),
                    actor_id="extension:{}.{}".format(impl.__module__, impl.__name__),
                )
                if type_id not in changed:
                    changed.append(type_id)
        except Exception as xcpt:
            _LOGGER.warning(
                "pychestrate.rpa.code_defined.sync_failed implementation=%s error=%s",
                getattr(impl, "__name__", impl), xcpt,
            )
            try:
                db_session.rollback()
            except Exception:
                pass
    return changed


def _resolve_execution_mode(*, execution_mode: str) -> Type[RpaExecutionModeProtocol]:
    candidates = list_execution_modes()
    for impl in candidates:
        if impl.execution_mode() == execution_mode:
            return impl
    err_lines = ["No registered rpa_execution_mode for name."]
    err_lines.append("EXECUTION_MODE: {}".format(execution_mode))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(impl.execution_mode() for impl in candidates),
    ))
    raise RpaJobTypeInvalidError(os.linesep.join(err_lines)) from None


# ---------------------------------------------------------------------------
# Job types
# ---------------------------------------------------------------------------


def _clean_string_list(value: Any, *, field_name: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise RpaJobTypeInvalidError("'{}' must be a list of strings".format(field_name))
    rtnval: List[str] = []
    for item in value:
        text = str(item).strip()
        if len(text) > 0:
            rtnval.append(text)
    return rtnval


def register_job_type(
        *,
        db_session: DbSession,
        inputs: RpaJobTypeInputs,
        actor_id: Optional[str] = None
    ) -> RpaJobTypeView:
    """
        Register a job type. Validates the slug, the execution mode
        against the registered drivers, and the packet schema.

        :raises: RpaJobTypeInvalidError, DuplicateRpaJobTypeError.
    """
    if is_valid_type_id(inputs.type_id) is False:
        err_lines = ["RPA job type id must be a lowercase slug of 3 to 64 characters."]
        err_lines.append("TYPE_ID: {!r}".format(inputs.type_id))
        raise RpaJobTypeInvalidError(os.linesep.join(err_lines)) from None
    display_name = str(inputs.display_name or "").strip()
    if len(display_name) == 0:
        raise RpaJobTypeInvalidError("RPA job type requires a display_name.") from None

    try:
        mode = RpaExecutionMode(str(inputs.execution_mode))
    except ValueError:
        err_lines = ["Unknown RPA execution mode."]
        err_lines.append("EXECUTION_MODE: {!r}".format(inputs.execution_mode))
        err_lines.append("SUPPORTED: {}".format(", ".join(m.value for m in RpaExecutionMode)))
        raise RpaJobTypeInvalidError(os.linesep.join(err_lines)) from None
    _resolve_execution_mode(execution_mode=mode.value)

    ok, issues = validate_schema_document(inputs.packet_schema)
    if ok is False:
        raise RpaJobTypeInvalidError(os.linesep.join(issues)) from None

    capability_requirements = _clean_string_list(
        inputs.capability_requirements, field_name="capability_requirements",
    )
    secret_fields = _clean_string_list(inputs.secret_fields, field_name="secret_fields")

    if repository.find_job_type(db_session=db_session, type_id=inputs.type_id) is not None:
        err_lines = ["RPA job type already registered."]
        err_lines.append("TYPE_ID: {}".format(inputs.type_id))
        raise DuplicateRpaJobTypeError(os.linesep.join(err_lines)) from None

    row = repository.insert_job_type(
        db_session=db_session,
        type_id=inputs.type_id,
        display_name=display_name,
        description=str(inputs.description or ""),
        execution_mode=mode,
        capability_requirements=capability_requirements,
        packet_schema=dict(inputs.packet_schema) if inputs.packet_schema else None,
        secret_fields=secret_fields,
        created_by_id=actor_id,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RpaEventTopics.JOB_TYPE_REGISTERED,
            payload={
                "type_id": row.type_id,
                "execution_mode": mode.value,
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = get_job_type(db_session=db_session, type_id=row.type_id)
    return rtnval


def update_job_type(
        *,
        db_session: DbSession,
        type_id: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        capability_requirements: Optional[Sequence[str]] = None,
        packet_schema: Any = ...,
        secret_fields: Optional[Sequence[str]] = None,
        actor_id: Optional[str] = None
    ) -> RpaJobTypeView:
    """
        Edit the display fields, schema, secret fields, or
        capabilities of a job type. ``packet_schema`` uses ``...`` as
        the "leave unchanged" sentinel so ``None`` can clear it.
        Publishes ``entity.rpa.job_type_updated`` naming the changed
        fields, so edits reach the audit log.

        :raises: RpaJobTypeNotFoundError, RpaJobTypeInvalidError.
    """
    row = _require_job_type_row(db_session=db_session, type_id=type_id)
    changed: List[str] = []
    if display_name is not None:
        text = str(display_name).strip()
        if len(text) == 0:
            raise RpaJobTypeInvalidError("display_name must not be empty.") from None
        row.display_name = text
        changed.append("display_name")
    if description is not None:
        row.description = str(description)
        changed.append("description")
    if capability_requirements is not None:
        row.capability_requirements = _clean_string_list(
            capability_requirements, field_name="capability_requirements",
        )
        changed.append("capability_requirements")
    if secret_fields is not None:
        row.secret_fields = _clean_string_list(secret_fields, field_name="secret_fields")
        changed.append("secret_fields")
    if packet_schema is not ...:
        ok, issues = validate_schema_document(packet_schema)
        if ok is False:
            raise RpaJobTypeInvalidError(os.linesep.join(issues)) from None
        row.packet_schema = dict(packet_schema) if packet_schema else None
        changed.append("packet_schema")
    row.updated_at = utc_now()
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RpaEventTopics.JOB_TYPE_UPDATED,
            payload={
                "type_id": row.type_id,
                "changed_fields": changed,
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = get_job_type(db_session=db_session, type_id=type_id)
    return rtnval


def retire_job_type(
        *,
        db_session: DbSession,
        type_id: str,
        actor_id: Optional[str] = None
    ) -> RpaJobTypeView:
    """
        Retire a job type: new runs are refused, existing jobs stay
        readable. Every active version is retired as well.

        :raises: RpaJobTypeNotFoundError.
    """
    row = _require_job_type_row(db_session=db_session, type_id=type_id)
    row.state = RpaJobTypeState.RETIRED
    row.updated_at = utc_now()
    for version_row in repository.list_versions(db_session=db_session, type_id=type_id):
        if version_row.state != RpaVersionState.RETIRED:
            version_row.state = RpaVersionState.RETIRED
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RpaEventTopics.JOB_TYPE_RETIRED,
            payload={"type_id": type_id, "actor_id": actor_id},
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = get_job_type(db_session=db_session, type_id=type_id)
    return rtnval


def publish_version(
        *,
        db_session: DbSession,
        type_id: str,
        inputs: RpaVersionInputs,
        actor_id: Optional[str] = None
    ) -> RpaJobTypeVersionView:
    """
        Publish a version for a job type. The execution-mode driver
        validates the entrypoint.

        :raises: RpaJobTypeNotFoundError, RpaJobTypeRetiredError,
                 RpaJobTypeInvalidError, DuplicateVersionError.
    """
    type_row = _require_job_type_row(db_session=db_session, type_id=type_id)
    if type_row.state == RpaJobTypeState.RETIRED:
        raise RpaJobTypeRetiredError(
            "RPA job type '{}' is retired; publish is refused.".format(type_id)
        ) from None

    version = str(inputs.version or "").strip()
    if len(version) == 0 or len(version) > 64 or "/" in version or " " in version:
        raise RpaJobTypeInvalidError(
            "version must be a non-empty label of at most 64 characters without spaces or slashes."
        ) from None
    if version == VERSION_SELECTOR_LATEST_ACTIVE:
        raise RpaJobTypeInvalidError(
            "'{}' is a reserved selector and cannot be a version label.".format(version)
        ) from None

    try:
        source_kind = RpaSourceKind(str(inputs.source_kind))
    except ValueError:
        raise RpaJobTypeInvalidError(
            "source_kind must be one of {}.".format(", ".join(k.value for k in RpaSourceKind))
        ) from None
    source_ref = str(inputs.source_ref or "").strip()
    if source_kind != RpaSourceKind.LOCAL and len(source_ref) == 0:
        raise RpaJobTypeInvalidError(
            "source_ref is required for source_kind '{}'.".format(source_kind.value)
        ) from None

    if not isinstance(inputs.entrypoint, Mapping):
        raise RpaJobTypeInvalidError("entrypoint must be a JSON object.") from None
    driver = _resolve_execution_mode(execution_mode=type_row.execution_mode.value)
    ok, issues = driver.validate_entrypoint(entrypoint=dict(inputs.entrypoint))
    if ok is False:
        err_lines = ["Execution mode '{}' rejected the entrypoint: {} issue(s).".format(
            type_row.execution_mode.value, len(issues),
        )]
        for index, issue in enumerate(issues):
            err_lines.append("  [{}] {}".format(index + 1, issue))
        raise RpaJobTypeInvalidError(os.linesep.join(err_lines)) from None

    environment: Dict[str, str] = {}
    if inputs.environment is not None:
        if not isinstance(inputs.environment, Mapping):
            raise RpaJobTypeInvalidError("environment must be a JSON object of strings.") from None
        for key, value in inputs.environment.items():
            environment[str(key)] = str(value)

    timeout_minutes = int(inputs.timeout_minutes or 0)
    if timeout_minutes <= 0:
        raise RpaJobTypeInvalidError("timeout_minutes must be a positive integer.") from None

    if repository.find_version(db_session=db_session, type_id=type_id, version=version) is not None:
        err_lines = ["RPA job type version already published."]
        err_lines.append("TYPE_ID: {}".format(type_id))
        err_lines.append("VERSION: {}".format(version))
        raise DuplicateVersionError(os.linesep.join(err_lines)) from None

    row = repository.insert_version(
        db_session=db_session,
        type_id=type_id,
        version=version,
        source_kind=source_kind,
        source_ref=source_ref,
        entrypoint=dict(inputs.entrypoint),
        environment=environment,
        timeout_minutes=timeout_minutes,
        published_by_id=actor_id,
    )
    type_row.updated_at = utc_now()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RpaEventTopics.JOB_TYPE_VERSION_PUBLISHED,
            payload={"type_id": type_id, "version": version, "actor_id": actor_id},
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _version_to_view(row)
    return rtnval


def set_version_state(
        *,
        db_session: DbSession,
        type_id: str,
        version: str,
        state: RpaVersionState
    ) -> RpaJobTypeVersionView:
    """
        Deprecate or retire (or re-activate) a version.

        :raises: RpaVersionNotFoundError.
    """
    row = repository.find_version(db_session=db_session, type_id=type_id, version=version)
    if row is None:
        err_lines = ["RPA job type version not found."]
        err_lines.append("TYPE_ID: {}".format(type_id))
        err_lines.append("VERSION: {}".format(version))
        raise RpaVersionNotFoundError(os.linesep.join(err_lines)) from None
    row.state = state
    db_session.flush()
    db_session.commit()
    rtnval = _version_to_view(row)
    return rtnval


def get_job_type(*, db_session: DbSession, type_id: str) -> RpaJobTypeView:
    """
        :raises: RpaJobTypeNotFoundError.
    """
    row = _require_job_type_row(db_session=db_session, type_id=type_id)
    versions = repository.list_versions(db_session=db_session, type_id=type_id)
    rtnval = _job_type_to_view(row, versions)
    return rtnval


def list_job_types(
        *,
        db_session: DbSession,
        state: Optional[RpaJobTypeState] = None
    ) -> List[RpaJobTypeView]:
    if len(list_code_defined_job_types()) > 0:
        sync_code_defined_job_types(db_session=db_session)
    rows = repository.list_job_types(db_session=db_session, state=state)
    rtnval: List[RpaJobTypeView] = []
    for row in rows:
        versions = repository.list_versions(db_session=db_session, type_id=row.type_id)
        rtnval.append(_job_type_to_view(row, versions))
    return rtnval


def _version_sort_key(version: str) -> Tuple[int, Any]:
    """
        Order versions: PEP 440 / semver versions first (by version),
        then arbitrary labels (lexically). Higher sorts last.
    """
    try:
        from packaging.version import InvalidVersion, Version  # noqa: E402
    except ImportError:  # pragma: no cover
        return (0, version)
    try:
        rtnval: Tuple[int, Any] = (1, Version(version))
    except InvalidVersion:
        rtnval = (0, version)
    return rtnval


def resolve_version(
        *,
        db_session: DbSession,
        type_id: str,
        selector: str
    ) -> RpaJobTypeVersion:
    """
        Resolve a version selector against the published versions of
        a job type. ``latest-active`` picks the highest active
        version; any other selector must name an active version.

        :raises: RpaJobTypeNotFoundError, RpaJobTypeRetiredError,
                 RpaVersionNotFoundError, RpaVersionNotActiveError.
    """
    type_row = _require_job_type_row(db_session=db_session, type_id=type_id)
    if type_row.state == RpaJobTypeState.RETIRED:
        raise RpaJobTypeRetiredError(
            "RPA job type '{}' is retired; new runs are refused.".format(type_id)
        ) from None

    selector_text = str(selector or VERSION_SELECTOR_LATEST_ACTIVE).strip()
    if selector_text == VERSION_SELECTOR_LATEST_ACTIVE or len(selector_text) == 0:
        active = repository.list_versions(
            db_session=db_session, type_id=type_id, state=RpaVersionState.ACTIVE,
        )
        if len(active) == 0:
            err_lines = ["RPA job type has no active version."]
            err_lines.append("TYPE_ID: {}".format(type_id))
            raise RpaVersionNotActiveError(os.linesep.join(err_lines)) from None
        rtnval = sorted(active, key=lambda r: _version_sort_key(r.version))[-1]
        return rtnval

    row = repository.find_version(db_session=db_session, type_id=type_id, version=selector_text)
    if row is None:
        err_lines = ["RPA job type version not found."]
        err_lines.append("TYPE_ID: {}".format(type_id))
        err_lines.append("VERSION: {}".format(selector_text))
        raise RpaVersionNotFoundError(os.linesep.join(err_lines)) from None
    if row.state != RpaVersionState.ACTIVE:
        err_lines = ["RPA job type version is not active."]
        err_lines.append("TYPE_ID: {}".format(type_id))
        err_lines.append("VERSION: {}".format(selector_text))
        err_lines.append("STATE: {}".format(row.state.value))
        raise RpaVersionNotActiveError(os.linesep.join(err_lines)) from None
    rtnval = row
    return rtnval


def _require_job_type_row(*, db_session: DbSession, type_id: str) -> RpaJobType:
    row = repository.find_job_type(db_session=db_session, type_id=type_id)
    if row is None and any(impl.type_id() == type_id for impl in list_code_defined_job_types()):
        sync_code_defined_job_types(db_session=db_session)
        row = repository.find_job_type(db_session=db_session, type_id=type_id)
    if row is None:
        err_lines = ["RPA job type not found."]
        err_lines.append("TYPE_ID: {}".format(type_id))
        raise RpaJobTypeNotFoundError(os.linesep.join(err_lines)) from None
    return row


# ---------------------------------------------------------------------------
# Specifications
# ---------------------------------------------------------------------------


def _validate_spec_inputs(*, db_session: DbSession, inputs: RpaSpecInputs) -> RpaJobType:
    name = str(inputs.name or "").strip()
    if len(name) == 0 or len(name) > 128:
        raise RpaSpecInvalidError("Specification name must be 1 to 128 characters.") from None
    type_row = _require_job_type_row(db_session=db_session, type_id=str(inputs.type_id))
    if type_row.state == RpaJobTypeState.RETIRED:
        raise RpaSpecInvalidError(
            "RPA job type '{}' is retired and cannot be bound to a specification.".format(
                type_row.type_id,
            )
        ) from None
    # A specification needs at least one active version to be runnable.
    resolve_version(
        db_session=db_session,
        type_id=type_row.type_id,
        selector=inputs.version_selector,
    )
    if not isinstance(inputs.default_packet, Mapping):
        raise RpaSpecInvalidError("default_packet must be a JSON object.") from None
    if inputs.timeout_minutes is not None and int(inputs.timeout_minutes) <= 0:
        raise RpaSpecInvalidError("timeout_minutes must be a positive integer when set.") from None
    return type_row


def _spec_snapshot(row: RpaSpec) -> Dict[str, Any]:
    rtnval = {
        "name": row.name,
        "type_id": row.type_id,
        "version_selector": row.version_selector,
        "default_packet": dict(row.default_packet or {}),
        "target_pod_id": row.target_pod_id,
        "required_capabilities": list(row.required_capabilities or []),
        "timeout_minutes": row.timeout_minutes,
        "description": row.description,
    }
    return rtnval


def create_spec(
        *,
        db_session: DbSession,
        project_id: str,
        inputs: RpaSpecInputs,
        actor_id: Optional[str] = None
    ) -> RpaSpecView:
    """
        Create a project specification.

        :raises: RpaSpecInvalidError, DuplicateRpaSpecError,
                 RpaJobTypeNotFoundError, RpaVersionNotActiveError.
    """
    project_ref = str(project_id)
    _validate_spec_inputs(db_session=db_session, inputs=inputs)
    name = str(inputs.name).strip()
    if repository.find_spec_by_name(db_session=db_session, project_id=project_ref, name=name) is not None:
        err_lines = ["An RPA specification with that name already exists in the project."]
        err_lines.append("NAME: {}".format(name))
        raise DuplicateRpaSpecError(os.linesep.join(err_lines)) from None

    row = repository.insert_spec(
        db_session=db_session,
        project_id=project_ref,
        name=name,
        type_id=str(inputs.type_id),
        version_selector=str(inputs.version_selector or VERSION_SELECTOR_LATEST_ACTIVE).strip(),
        default_packet=dict(inputs.default_packet or {}),
        target_pod_id=(str(inputs.target_pod_id).strip() or None) if inputs.target_pod_id else None,
        required_capabilities=_clean_string_list(
            inputs.required_capabilities, field_name="required_capabilities",
        ),
        timeout_minutes=int(inputs.timeout_minutes) if inputs.timeout_minutes else None,
        description=str(inputs.description or ""),
        created_by_id=actor_id,
    )
    repository.insert_spec_revision(
        db_session=db_session, spec_id=str(row.spec_id), revision=1, snapshot=_spec_snapshot(row),
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RpaEventTopics.SPEC_CREATED,
            payload={
                "spec_id": str(row.spec_id),
                "project_id": project_ref,
                "type_id": row.type_id,
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = get_spec(db_session=db_session, spec_id=str(row.spec_id))
    return rtnval


def update_spec(
        *,
        db_session: DbSession,
        spec_id: str,
        inputs: RpaSpecInputs,
        actor_id: Optional[str] = None
    ) -> RpaSpecView:
    """
        Replace a specification's fields, bump its revision, and
        snapshot the new revision.

        :raises: RpaSpecNotFoundError, RpaSpecInvalidError,
                 DuplicateRpaSpecError.
    """
    row = _require_spec_row(db_session=db_session, spec_id=spec_id)
    _validate_spec_inputs(db_session=db_session, inputs=inputs)
    name = str(inputs.name).strip()
    existing = repository.find_spec_by_name(
        db_session=db_session, project_id=row.project_id, name=name,
    )
    if existing is not None and str(existing.spec_id) != str(row.spec_id):
        raise DuplicateRpaSpecError(
            "An RPA specification named '{}' already exists in the project.".format(name)
        ) from None

    row.name = name
    row.type_id = str(inputs.type_id)
    row.version_selector = str(inputs.version_selector or VERSION_SELECTOR_LATEST_ACTIVE).strip()
    row.default_packet = dict(inputs.default_packet or {})
    row.target_pod_id = (str(inputs.target_pod_id).strip() or None) if inputs.target_pod_id else None
    row.required_capabilities = _clean_string_list(
        inputs.required_capabilities, field_name="required_capabilities",
    )
    row.timeout_minutes = int(inputs.timeout_minutes) if inputs.timeout_minutes else None
    row.description = str(inputs.description or "")
    row.revision = int(row.revision or 1) + 1
    row.updated_at = utc_now()
    db_session.flush()
    repository.insert_spec_revision(
        db_session=db_session, spec_id=str(row.spec_id), revision=row.revision,
        snapshot=_spec_snapshot(row),
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RpaEventTopics.SPEC_UPDATED,
            payload={
                "spec_id": str(row.spec_id),
                "project_id": row.project_id,
                "revision": row.revision,
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = get_spec(db_session=db_session, spec_id=str(row.spec_id))
    return rtnval


def delete_spec(*, db_session: DbSession, spec_id: str, actor_id: Optional[str] = None) -> None:
    """
        Delete a specification. Jobs keep their ``spec_name`` and
        revision; their ``spec_id`` is nulled by the foreign key.

        :raises: RpaSpecNotFoundError, RpaSpecInvalidError when
                 jobs are still active.
    """
    row = _require_spec_row(db_session=db_session, spec_id=spec_id)
    active = repository.count_active_jobs_for_spec(db_session=db_session, spec_id=str(row.spec_id))
    if active > 0:
        raise RpaSpecInvalidError(
            "Specification has {} active job(s); wait for them to finish or cancel them first.".format(
                active,
            )
        ) from None
    project_id = row.project_id
    db_session.delete(row)
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RpaEventTopics.SPEC_DELETED,
            payload={"spec_id": spec_id, "project_id": project_id, "actor_id": actor_id},
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def get_spec(*, db_session: DbSession, spec_id: str) -> RpaSpecView:
    """
        :raises: RpaSpecNotFoundError.
    """
    row = _require_spec_row(db_session=db_session, spec_id=spec_id)
    rtnval = _spec_to_view(db_session=db_session, row=row)
    return rtnval


def list_specs(
        *,
        db_session: DbSession,
        project_id: str,
        offset: int = 0,
        limit: int = 100
    ) -> Tuple[List[RpaSpecView], int]:
    """
        Specifications for a project plus the total count.
    """
    project_ref = str(project_id)
    rows = repository.list_specs(
        db_session=db_session, project_id=project_ref, offset=offset, limit=limit,
    )
    total = repository.count_specs(db_session=db_session, project_id=project_ref)
    views = [_spec_to_view(db_session=db_session, row=row) for row in rows]
    rtnval = (views, total)
    return rtnval


def _require_spec_row(*, db_session: DbSession, spec_id: str) -> RpaSpec:
    row = None
    try:
        row = repository.find_spec(db_session=db_session, spec_id=spec_id)
    except Exception:
        row = None
    if row is None:
        err_lines = ["RPA specification not found."]
        err_lines.append("SPEC_ID: {}".format(spec_id))
        raise RpaSpecNotFoundError(os.linesep.join(err_lines)) from None
    return row


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------


def _derive_idempotency_key(
        *,
        project_id: str,
        spec_id: str,
        digest: str,
        cause_kind: str
    ) -> str:
    import hashlib  # noqa: E402
    material = "{}|{}|{}|{}".format(project_id, spec_id, digest, cause_kind)
    rtnval = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return rtnval


def _check_capabilities(
        *,
        required: Sequence[str],
        candidates: Sequence[DispatchCandidate]
    ) -> Sequence[DispatchCandidate]:
    """
        Keep the candidates whose advertised tags cover ``required``.
        A candidate with no advertised tags is kept only when nothing
        is required (the M1 candidate builders advertise none).
    """
    needed = [str(r) for r in required if len(str(r)) > 0]
    if len(needed) == 0:
        return candidates
    kept: List[DispatchCandidate] = []
    for candidate in candidates:
        tags = set(str(t) for t in (getattr(candidate, "capability_tags", ()) or ()))
        if all(n in tags for n in needed):
            kept.append(candidate)
    if len(kept) == 0:
        advertised = sorted(set(
            str(t) for c in candidates for t in (getattr(c, "capability_tags", ()) or ())
        ))
        err_lines = ["No eligible pod advertises the capabilities this RPA job requires."]
        err_lines.append("REQUIRED: {}".format(", ".join(needed)))
        err_lines.append("ADVERTISED: {}".format(", ".join(advertised) or "(none)"))
        raise CapabilityMismatchError(os.linesep.join(err_lines)) from None
    return kept


def check_trigger_packet(
        *,
        db_session: DbSession,
        project_id: str,
        spec_id: str,
        work_packet: Optional[Mapping[str, Any]] = None,
        max_packet_bytes: int = DEFAULT_MAX_PACKET_BYTES
    ) -> Dict[str, Any]:
    """
        Run the checks :func:`trigger_job` applies to a work packet --
        specification in the project, job type runnable, a version to
        resolve, packet size and JSON Schema -- without creating
        anything. Callers run it before choosing pods, so a caller
        with a bad packet learns that, not "no pod available".

        :returns: The merged packet.
        :raises: RpaSpecNotFoundError, RpaJobTypeRetiredError,
                 RpaVersionNotActiveError, PacketValidationError,
                 PacketTooLargeError.
    """
    project_ref = str(project_id)
    spec_row = _require_spec_row(db_session=db_session, spec_id=spec_id)
    if spec_row.project_id != project_ref:
        err_lines = ["RPA specification does not belong to the project."]
        err_lines.append("SPEC_ID: {}".format(spec_id))
        err_lines.append("PROJECT_ID: {}".format(project_ref))
        raise RpaSpecNotFoundError(os.linesep.join(err_lines)) from None
    type_row = _require_job_type_row(db_session=db_session, type_id=spec_row.type_id)
    resolve_version(
        db_session=db_session, type_id=type_row.type_id, selector=spec_row.version_selector,
    )
    merged = merge_packet(
        default_packet=dict(spec_row.default_packet or {}),
        work_packet=dict(work_packet or {}),
    )
    enforce_packet_size(packet=merged, max_bytes=max_packet_bytes)
    validate_packet(packet=merged, schema=type_row.packet_schema)
    rtnval = merged
    return rtnval


def trigger_job(
        *,
        db_session: DbSession,
        project_id: str,
        spec_id: str,
        work_packet: Optional[Mapping[str, Any]] = None,
        aspects: Optional[RpaTriggerAspects] = None
    ) -> RpaJobView:
    """
        Merge and validate the packet, resolve the version, persist
        the job, create the run-state row, mint a ``job_kind=rpa``
        envelope, and dispatch it.

        :raises: RpaSpecNotFoundError, RpaJobTypeRetiredError,
                 RpaVersionNotActiveError, PacketValidationError,
                 PacketTooLargeError, CapabilityMismatchError,
                 RpaDispatchUnavailableError, RpaDispatchFailedError.
    """
    effective = aspects or RpaTriggerAspects()
    project_ref = str(project_id)

    spec_row = _require_spec_row(db_session=db_session, spec_id=spec_id)
    if spec_row.project_id != project_ref:
        err_lines = ["RPA specification does not belong to the project."]
        err_lines.append("SPEC_ID: {}".format(spec_id))
        err_lines.append("PROJECT_ID: {}".format(project_ref))
        raise RpaSpecNotFoundError(os.linesep.join(err_lines)) from None

    type_row = _require_job_type_row(db_session=db_session, type_id=spec_row.type_id)
    version_row = resolve_version(
        db_session=db_session, type_id=type_row.type_id, selector=spec_row.version_selector,
    )

    merged = merge_packet(
        default_packet=dict(spec_row.default_packet or {}),
        work_packet=dict(work_packet or {}),
    )
    enforce_packet_size(packet=merged, max_bytes=effective.max_packet_bytes)
    validate_packet(packet=merged, schema=type_row.packet_schema)
    digest = packet_digest(merged)
    redacted = redact_packet(packet=merged, secret_fields=list(type_row.secret_fields or []))

    cause = dict(effective.trigger_cause or {"kind": "manual"})
    cause_kind = str(cause.get("kind", "manual"))
    idempotency_key = effective.idempotency_key or _derive_idempotency_key(
        project_id=project_ref, spec_id=str(spec_row.spec_id), digest=digest, cause_kind=cause_kind,
    )
    if effective.idempotency_window_seconds > 0:
        not_before = utc_now() - timedelta(seconds=effective.idempotency_window_seconds)
        prior = repository.find_recent_job_by_idempotency_key(
            db_session=db_session, idempotency_key=idempotency_key, not_before=not_before,
        )
        if prior is not None:
            _LOGGER.info(
                "pychestrate.rpa.trigger.idempotent_replay job_id=%s key=%s",
                str(prior.job_id), idempotency_key,
            )
            rtnval = replace(get_job(db_session=db_session, job_id=str(prior.job_id)), replayed=True)
            return rtnval

    required = list(type_row.capability_requirements or []) + list(spec_row.required_capabilities or [])
    candidates = _check_capabilities(required=required, candidates=tuple(effective.candidates))

    job_id = new_uuid()
    job_row = repository.insert_job(
        db_session=db_session,
        job_id=job_id,
        project_id=project_ref,
        spec_id=str(spec_row.spec_id),
        spec_name=spec_row.name,
        spec_revision=int(spec_row.revision or 1),
        type_id=type_row.type_id,
        resolved_version=version_row.version,
        execution_mode=type_row.execution_mode,
        work_packet=redacted,
        packet_digest=digest,
        triggered_by_id=effective.actor_id,
        trigger_cause=cause,
        idempotency_key=idempotency_key,
    )
    job_type_string = RPA_JOB_TYPE_PREFIX + type_row.type_id

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RpaEventTopics.JOB_STARTED,
            payload={
                "job_id": job_id,
                "project_id": project_ref,
                "spec_id": str(spec_row.spec_id),
                "type_id": type_row.type_id,
                "version": version_row.version,
                "execution_mode": type_row.execution_mode.value,
                "trigger_cause": cause,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    layer5_project_id = canonical_project_uuid(project_ref)
    create_run_state(
        db_session=db_session,
        run_id=job_id,
        project_id=layer5_project_id,
        job_type=job_type_string,
    )
    transition_run_state(
        db_session=db_session,
        run_id=job_id,
        event=RunEvent.DISPATCH_STARTED,
        actor=RPA_ACTOR,
        reason="type_id={} version={}".format(type_row.type_id, version_row.version),
    )
    job_row.status = RpaJobStatus.DISPATCHING
    db_session.flush()

    timeout_minutes = int(spec_row.timeout_minutes or version_row.timeout_minutes or 60)
    dispatch_outcome = _dispatch_rpa_job(
        db_session=db_session,
        job_row=job_row,
        type_row=type_row,
        version_row=version_row,
        layer5_project_id=layer5_project_id,
        job_type_string=job_type_string,
        merged_packet=merged,
        digest=digest,
        timeout_minutes=timeout_minutes,
        aspects=effective,
        candidates=candidates,
    )

    job_row.status = RpaJobStatus.RUNNING
    job_row.started_at = utc_now()
    job_row.dispatch_attempt_id = dispatch_outcome.attempt_id
    job_row.envelope_id = dispatch_outcome.envelope_id
    job_row.client_id = dispatch_outcome.client_id
    job_row.pod_id = dispatch_outcome.pod_id
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RpaEventTopics.JOB_DISPATCHED,
            payload={
                "job_id": job_id,
                "project_id": project_ref,
                "type_id": type_row.type_id,
                "version": version_row.version,
                "dispatch_attempt_id": dispatch_outcome.attempt_id,
                "envelope_id": dispatch_outcome.envelope_id,
                "client_id": dispatch_outcome.client_id,
                "pod_id": dispatch_outcome.pod_id,
                "transport": dispatch_outcome.transport_name,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    _LOGGER.info(
        "pychestrate.rpa.dispatched job_id=%s type_id=%s version=%s envelope_id=%s client_id=%s pod_id=%s",
        job_id, type_row.type_id, version_row.version, dispatch_outcome.envelope_id,
        dispatch_outcome.client_id, dispatch_outcome.pod_id,
    )

    rtnval = get_job(db_session=db_session, job_id=job_id)
    return rtnval


def _source_ref_for_version(version_row: RpaJobTypeVersion) -> Optional[JobSourceRef]:
    """
        Build the structured envelope ``source`` block for a git
        version (``url#ref`` or ``url@ref``; bare url means ``main``).
        Non-git sources carry no ``source`` block -- the payload's
        ``source`` map describes them.
    """
    if version_row.source_kind != RpaSourceKind.GIT:
        return None
    text = str(version_row.source_ref or "").strip()
    if len(text) == 0:
        return None
    url = text
    ref = "main"
    for separator in ("#", "@@"):
        if separator in text:
            url, ref = text.rsplit(separator, 1)
            break
    rtnval = JobSourceRef(kind="git", url=url, ref=ref or "main", integration_id="", credentials_ref="")
    return rtnval


def _dispatch_rpa_job(
        *,
        db_session: DbSession,
        job_row: RpaJob,
        type_row: RpaJobType,
        version_row: RpaJobTypeVersion,
        layer5_project_id: str,
        job_type_string: str,
        merged_packet: Dict[str, Any],
        digest: str,
        timeout_minutes: int,
        aspects: RpaTriggerAspects,
        candidates: Sequence[DispatchCandidate]
    ):
    job_id = str(job_row.job_id)
    dispatcher = ACTIVE_JOB_DISPATCHER
    if dispatcher is None:
        _fail_job(db_session=db_session, job_id=job_id, reason="job dispatcher not wired")
        err_lines = ["RPA dispatch failed -- no JobDispatcher is wired."]
        err_lines.append("JOB_ID: {}".format(job_id))
        err_lines.append("HINT: the Phase-6 runtime bootstrap publishes the dispatcher via set_active_job_dispatcher().")
        raise RpaDispatchUnavailableError(os.linesep.join(err_lines)) from None

    backend = ACTIVE_RESULTS_BACKEND
    if backend is None:
        backend = SharedResultsBackend(backend_driver="local-test")
    allocation = backend.allocate(
        db_session=db_session,
        run_id=job_id,
        project_id=layer5_project_id,
        project_slug=aspects.project_slug,
        job_type=job_type_string,
    )

    source_ref = _source_ref_for_version(version_row)
    payload: Dict[str, Any] = {
        "type_id": type_row.type_id,
        "version": version_row.version,
        "execution_mode": type_row.execution_mode.value,
        "source": {"kind": version_row.source_kind.value, "ref": version_row.source_ref},
        "entrypoint": dict(version_row.entrypoint or {}),
        "environment": dict(version_row.environment or {}),
        "work_packet": merged_packet,
        "packet_digest": digest,
        "timeout_minutes": timeout_minutes,
        "spec_id": str(job_row.spec_id) if job_row.spec_id is not None else None,
        "spec_name": job_row.spec_name,
        "spec_revision": job_row.spec_revision,
    }

    triggered_at = utc_now()
    soft_deadline = triggered_at + timedelta(
        seconds=min(aspects.soft_deadline_seconds, timeout_minutes * 60),
    )
    hard_deadline = triggered_at + timedelta(
        seconds=max(aspects.hard_deadline_seconds, timeout_minutes * 60 + 300),
    )

    dispatch_inputs = DispatchRequestInputs(
        run_id=job_id,
        project_id=layer5_project_id,
        job_id=job_id,
        job_name="rpa:{}".format(type_row.type_id),
        job_type=job_type_string,
        job_kind=JOB_KIND_RPA,
        issuer=aspects.issuer,
        refs=JobRefs(
            branch=source_ref.ref if source_ref is not None else "main",
            build="",
            flavor=type_row.execution_mode.value,
            release=version_row.version,
            commit_sha="0" * 40,
        ),
        source=source_ref,
        params=payload,
        scoped_secrets=tuple(),
        results=JobResultsLocator(
            backend_key_prefix=allocation.backend_key_prefix,
            backend_driver=allocation.backend_driver,
        ),
        forwarding=JobForwardingInfo(
            progress_url="https://pychestrate.example.com/api/v1/runs/{}/progress".format(job_id),
            summary_url="https://pychestrate.example.com/api/v1/runs/{}/summary".format(job_id),
            auth_method="bearer",
        ),
        deadline=JobDeadline(soft_deadline_at=soft_deadline, hard_deadline_at=hard_deadline),
        pipeline=None,
        extension_claims={},
        candidates=tuple(candidates),
    )

    try:
        rtnval = dispatcher.dispatch(db_session=db_session, inputs=dispatch_inputs)
    except DispatchError as xcpt:
        _fail_job(
            db_session=db_session, job_id=job_id, reason="dispatch failed: {}".format(str(xcpt)),
        )
        err_lines = ["RPA dispatch failed."]
        err_lines.append("JOB_ID: {}".format(job_id))
        err_lines.append("REASON: {}".format(str(xcpt)))
        raise RpaDispatchFailedError(os.linesep.join(err_lines)) from xcpt
    return rtnval


def _fail_job(*, db_session: DbSession, job_id: str, reason: str) -> None:
    """
        Durably record a dispatch failure on the run-state machine and
        the job row. Best-effort.
    """
    try:
        transition_run_state(
            db_session=db_session,
            run_id=job_id,
            event=RunEvent.DISPATCH_ABORTED,
            actor=RPA_ACTOR,
            reason=reason,
        )
    except Exception:
        _LOGGER.warning(
            "pychestrate.rpa.dispatch_fail.run_state_transition_skipped job_id=%s", job_id,
        )
    row = repository.find_job(db_session=db_session, job_id=job_id)
    if row is not None and row.status not in TERMINAL_STATUSES:
        row.status = RpaJobStatus.FAILED
        row.completed_at = utc_now()
        row.final_state_reason = reason
        db_session.flush()
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=RpaEventTopics.JOB_FAILED,
                payload={
                    "job_id": job_id,
                    "project_id": row.project_id,
                    "status": RpaJobStatus.FAILED.value,
                    "reason": reason,
                },
                source_event_id=new_uuid(),
            ),
        )
    db_session.commit()
    return


# ---------------------------------------------------------------------------
# Terminal outcomes, cancel, reads
# ---------------------------------------------------------------------------


def apply_run_terminal(
        *,
        db_session: DbSession,
        job_id: str,
        final_status: RpaJobStatus,
        exit_code: Optional[int] = None,
        result_root_key: Optional[str] = None,
        reason: str = ""
    ) -> RpaJobView:
    """
        Mirror a Layer-5 outcome onto a job. Idempotent on
        already-terminal rows.

        :raises: RpaJobNotFoundError, RpaSpecInvalidError when
                 ``final_status`` is not terminal.
    """
    if final_status not in TERMINAL_STATUSES:
        err_lines = ["apply_run_terminal requires a terminal job status."]
        err_lines.append("RECEIVED: {}".format(final_status.value))
        raise RpaSpecInvalidError(os.linesep.join(err_lines)) from None
    row = _require_job_row(db_session=db_session, job_id=job_id)
    if row.status in TERMINAL_STATUSES:
        rtnval = get_job(db_session=db_session, job_id=job_id)
        return rtnval

    row.status = final_status
    row.exit_code = exit_code
    if result_root_key is not None:
        row.result_root_key = result_root_key
    row.completed_at = utc_now()
    row.final_state_reason = reason or ""
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RpaEventTopics.JOB_STATE_CHANGED,
            payload={"job_id": job_id, "project_id": row.project_id, "status": final_status.value},
            source_event_id=new_uuid(),
        ),
    )
    final_topic = RpaEventTopics.JOB_COMPLETED
    if final_status in (RpaJobStatus.FAILED, RpaJobStatus.TIMEOUT):
        final_topic = RpaEventTopics.JOB_FAILED
    elif final_status == RpaJobStatus.CANCELLED:
        final_topic = RpaEventTopics.JOB_CANCELLED
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=final_topic,
            payload={
                "job_id": job_id,
                "project_id": row.project_id,
                "type_id": row.type_id,
                "final_status": final_status.value,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.completed_at.isoformat() if row.completed_at else None,
                "result_root_key": row.result_root_key,
                "exit_code": exit_code,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = get_job(db_session=db_session, job_id=job_id)
    return rtnval


def cancel_job(
        *,
        db_session: DbSession,
        job_id: str,
        actor_id: Optional[str] = None
    ) -> RpaJobView:
    """
        Request cancellation of an active job and drive the run-state
        machine to cancel-requested (best effort).

        A job that was dispatched to a pod gets a client cancel queued
        (:func:`jobs.cancel.client_cancel.queue_client_cancel`, delivered
        on the pod's next heartbeat) and stays in its current status: it
        becomes ``CANCELLED`` when the pod reports the ``cancelled``
        outcome through Layer 5, or ends however the pod finished if the
        cancel arrived too late. Only a job that never reached a pod is
        marked ``CANCELLED`` at once -- nothing is running to stop.

        :raises: RpaJobNotFoundError, RpaJobNotCancellableError.
    """
    row = _require_job_row(db_session=db_session, job_id=job_id)
    if row.status in TERMINAL_STATUSES:
        raise RpaJobNotCancellableError(
            "RPA job {} is already {}.".format(job_id, row.status.value)
        ) from None
    actor = actor_id or RPA_ACTOR
    reason = "cancelled by {}".format(actor_id or "operator")
    try:
        transition_run_state(
            db_session=db_session,
            run_id=job_id,
            event=RunEvent.CANCEL_REQUESTED,
            actor=actor,
            reason="cancel requested",
        )
    except Exception:
        _LOGGER.warning("pychestrate.rpa.cancel.run_state_transition_skipped job_id=%s", job_id)

    target = resolve_cancel_target_client(db_session=db_session, run_id=job_id)
    if target is None:
        rtnval = apply_run_terminal(
            db_session=db_session,
            job_id=job_id,
            final_status=RpaJobStatus.CANCELLED,
            reason=reason,
        )
        return rtnval

    queue_client_cancel(
        db_session=db_session, run_id=job_id, reason=reason, actor_id=actor,
    )
    row.final_state_reason = "cancel requested by {}; waiting for the pod".format(
        actor_id or "operator")
    db_session.flush()
    db_session.commit()
    rtnval = get_job(db_session=db_session, job_id=job_id)
    return rtnval


def get_job(*, db_session: DbSession, job_id: str) -> RpaJobView:
    """
        :raises: RpaJobNotFoundError.
    """
    row = _require_job_row(db_session=db_session, job_id=job_id)
    rtnval = _job_to_view(row, run_state=_resolve_run_state(db_session=db_session, run_id=str(row.job_id)))
    return rtnval


def list_jobs(
        *,
        db_session: DbSession,
        project_id: Optional[str],
        spec_id: Optional[str] = None,
        status: Optional[RpaJobStatus] = None,
        offset: int = 0,
        limit: int = LIST_JOBS_DEFAULT_LIMIT
    ) -> RpaJobListView:
    """
        Jobs for a project (newest first) with the total count.
    """
    project_ref = str(project_id) if project_id is not None else None
    rows = repository.list_jobs(
        db_session=db_session, project_id=project_ref, spec_id=spec_id, status=status,
        offset=offset, limit=limit,
    )
    total = repository.count_jobs(
        db_session=db_session, project_id=project_ref, spec_id=spec_id, status=status,
    )
    views = tuple(_job_to_view(row, run_state=None) for row in rows)
    rtnval = RpaJobListView(jobs=views, total=total, offset=offset, limit=limit)
    return rtnval


def get_job_log_text(*, db_session: DbSession, job_id: str) -> str:
    """
        Assemble a plain-text log for a job from the generalized
        progress frames its client posted. Returns an empty string
        when no frame has arrived yet.
    """
    _require_job_row(db_session=db_session, job_id=job_id)
    try:
        from ccai.pychestrate.webservice.ingest.progress import service as progress_service  # noqa: E402
        frames = progress_service.list_frames(db_session=db_session, run_id=job_id)
    except Exception:
        return ""
    lines: List[str] = []
    for frame in frames:
        payload = dict(getattr(frame, "payload", {}) or {})
        raw_lines = payload.get("lines", None)
        if isinstance(raw_lines, list):
            for entry in raw_lines:
                if isinstance(entry, dict):
                    lines.append(str(entry.get("line", "")))
                else:
                    lines.append(str(entry))
            continue
        stamp = getattr(frame, "recorded_at", None)
        stamp_text = stamp.isoformat() if isinstance(stamp, datetime) else ""
        parts = [p for p in (
            stamp_text,
            str(getattr(frame, "phase", "") or ""),
            str(getattr(frame, "status", "") or ""),
            str(getattr(frame, "notes", "") or ""),
        ) if len(p) > 0]
        if len(parts) > 0:
            lines.append(" ".join(parts))
    rtnval = "\n".join(lines)
    return rtnval


def _require_job_row(*, db_session: DbSession, job_id: str) -> RpaJob:
    row = None
    try:
        row = repository.find_job(db_session=db_session, job_id=job_id)
    except Exception:
        row = None
    if row is None:
        err_lines = ["RPA job not found."]
        err_lines.append("JOB_ID: {}".format(job_id))
        raise RpaJobNotFoundError(os.linesep.join(err_lines)) from None
    return row


def _resolve_run_state(*, db_session: DbSession, run_id: str) -> Optional[str]:
    try:
        snapshot = get_run_state_snapshot(db_session=db_session, run_id=run_id)
    except RunStateNotFoundError:
        return None
    except Exception:
        return None
    rtnval = snapshot.state.value
    return rtnval


# ---------------------------------------------------------------------------
# View mappers
# ---------------------------------------------------------------------------


def _version_to_view(row: RpaJobTypeVersion) -> RpaJobTypeVersionView:
    rtnval = RpaJobTypeVersionView(
        version_id=str(row.version_id),
        type_id=row.type_id,
        version=row.version,
        source_kind=row.source_kind.value if row.source_kind else RpaSourceKind.GIT.value,
        source_ref=row.source_ref or "",
        entrypoint=dict(row.entrypoint or {}),
        environment=dict(row.environment or {}),
        timeout_minutes=int(row.timeout_minutes or 60),
        state=row.state,
        published_by_id=row.published_by_id,
        published_at=row.published_at,
    )
    return rtnval


def _job_type_to_view(row: RpaJobType, versions: List[RpaJobTypeVersion]) -> RpaJobTypeView:
    ordered = sorted(versions, key=lambda r: _version_sort_key(r.version), reverse=True)
    version_views = tuple(_version_to_view(v) for v in ordered)
    active = [v for v in ordered if v.state == RpaVersionState.ACTIVE]
    latest_active = active[0].version if len(active) > 0 else None
    rtnval = RpaJobTypeView(
        type_id=row.type_id,
        display_name=row.display_name or row.type_id,
        description=row.description or "",
        execution_mode=row.execution_mode,
        capability_requirements=tuple(row.capability_requirements or []),
        packet_schema=dict(row.packet_schema) if row.packet_schema else None,
        secret_fields=tuple(row.secret_fields or []),
        state=row.state,
        created_by_id=row.created_by_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        versions=version_views,
        active_version_count=len(active),
        latest_active_version=latest_active,
    )
    return rtnval


def _spec_to_view(*, db_session: DbSession, row: RpaSpec) -> RpaSpecView:
    type_row = repository.find_job_type(db_session=db_session, type_id=row.type_id)
    display_name = row.type_id
    mode = RpaExecutionMode.PROCESS
    schema: Optional[Dict[str, Any]] = None
    secret_fields: Tuple[str, ...] = ()
    if type_row is not None:
        display_name = type_row.display_name or type_row.type_id
        mode = type_row.execution_mode
        schema = dict(type_row.packet_schema) if type_row.packet_schema else None
        secret_fields = tuple(str(p) for p in (type_row.secret_fields or []))
    resolved: Optional[str] = None
    try:
        resolved = resolve_version(
            db_session=db_session, type_id=row.type_id, selector=row.version_selector,
        ).version
    except Exception:
        resolved = None
    rtnval = RpaSpecView(
        spec_id=str(row.spec_id),
        project_id=row.project_id,
        name=row.name,
        type_id=row.type_id,
        type_display_name=display_name,
        execution_mode=mode,
        version_selector=row.version_selector or VERSION_SELECTOR_LATEST_ACTIVE,
        default_packet=dict(row.default_packet or {}),
        target_pod_id=row.target_pod_id,
        required_capabilities=tuple(row.required_capabilities or []),
        timeout_minutes=row.timeout_minutes,
        description=row.description or "",
        revision=int(row.revision or 1),
        created_by_id=row.created_by_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        packet_schema=schema,
        resolved_version=resolved,
        secret_fields=secret_fields,
    )
    return rtnval


def _job_to_view(row: RpaJob, *, run_state: Optional[str]) -> RpaJobView:
    duration: Optional[int] = None
    if row.started_at is not None and row.completed_at is not None:
        try:
            duration = int((row.completed_at - row.started_at).total_seconds())
        except Exception:
            duration = None
    rtnval = RpaJobView(
        job_id=str(row.job_id),
        project_id=row.project_id,
        spec_id=str(row.spec_id) if row.spec_id is not None else None,
        spec_name=row.spec_name or "",
        spec_revision=int(row.spec_revision or 1),
        type_id=row.type_id,
        resolved_version=row.resolved_version,
        execution_mode=row.execution_mode,
        work_packet=dict(row.work_packet or {}),
        packet_digest=row.packet_digest or "",
        status=row.status,
        exit_code=row.exit_code,
        dispatch_attempt_id=str(row.dispatch_attempt_id) if row.dispatch_attempt_id else None,
        envelope_id=str(row.envelope_id) if row.envelope_id else None,
        client_id=str(row.client_id) if row.client_id else None,
        pod_id=str(row.pod_id) if row.pod_id else None,
        triggered_by_id=row.triggered_by_id,
        trigger_cause=dict(row.trigger_cause or {}),
        result_root_key=row.result_root_key,
        final_state_reason=row.final_state_reason or "",
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        run_state=run_state,
        duration_seconds=duration,
    )
    return rtnval
