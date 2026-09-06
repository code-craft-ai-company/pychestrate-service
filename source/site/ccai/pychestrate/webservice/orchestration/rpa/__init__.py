"""
.. module:: orchestration.rpa
    :synopsis: 6-rpa-orchestration — Robotic Process Automation jobs.

Public surface:

* :class:`RpaJobType`, :class:`RpaJobTypeVersion`, :class:`RpaSpec`,
  :class:`RpaSpecRevision`, :class:`RpaJob` + enums — persistence rows.
* :class:`RpaJobTypeInputs`, :class:`RpaVersionInputs`,
  :class:`RpaSpecInputs`, :class:`RpaTriggerAspects` — IO shapes.
* :class:`RpaJobTypeView`, :class:`RpaJobTypeVersionView`,
  :class:`RpaSpecView`, :class:`RpaJobView`, :class:`RpaJobListView`.
* :func:`register_job_type`, :func:`publish_version`,
  :func:`resolve_version`, :func:`create_spec`, :func:`trigger_job`,
  :func:`apply_run_terminal`, :func:`cancel_job`, :func:`get_job`,
  :func:`list_jobs`.
* :class:`RpaExecutionModeProtocol` factory contract + reference
  :class:`ProcessExecutionMode` / :class:`TaskplusExecutionMode`.
* :class:`RpaEventTopics`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.orchestration.rpa.errors import (
    CapabilityMismatchError,
    DuplicateRpaJobTypeError,
    DuplicateRpaSpecError,
    DuplicateVersionError,
    PacketTooLargeError,
    PacketValidationError,
    RpaDispatchFailedError,
    RpaDispatchUnavailableError,
    RpaError,
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
    RpaExecutionModeProtocol,
)
from ccai.pychestrate.webservice.orchestration.rpa.factories.job_type_protocol import (
    CodeDefinedVersion,
    ProcessJobType,
    RpaJobTypeProtocol,
    TaskplusJobType,
)
from ccai.pychestrate.webservice.orchestration.rpa.factories.process_execution_mode import (
    ProcessExecutionMode,
)
from ccai.pychestrate.webservice.orchestration.rpa.factories.taskplus_execution_mode import (
    TaskplusExecutionMode,
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
    RpaSpecRevision,
    RpaVersionState,
)
from ccai.pychestrate.webservice.orchestration.rpa.packet import (
    REDACTION_MARKER,
    canonical_project_uuid,
    merge_packet,
    packet_digest,
    redact_packet,
    validate_packet,
)
from ccai.pychestrate.webservice.orchestration.rpa.service import (
    RpaJobListView,
    RpaJobTypeInputs,
    RpaJobTypeVersionView,
    RpaJobTypeView,
    RpaJobView,
    RpaSpecInputs,
    RpaSpecView,
    RpaTriggerAspects,
    RpaVersionInputs,
    apply_run_terminal,
    cancel_job,
    create_spec,
    delete_spec,
    get_job,
    get_job_log_text,
    get_job_type,
    get_spec,
    list_code_defined_job_types,
    list_execution_modes,
    sync_code_defined_job_types,
    list_job_types,
    list_jobs,
    list_specs,
    publish_version,
    register_job_type,
    resolve_version,
    retire_job_type,
    set_active_job_dispatcher,
    set_active_results_backend,
    set_version_state,
    trigger_job,
    update_job_type,
    update_spec,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree execution-mode drivers.
    """
    register_factory_implementation(implementation=ProcessExecutionMode)
    register_factory_implementation(implementation=TaskplusExecutionMode)
    return
