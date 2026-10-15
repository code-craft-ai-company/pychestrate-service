"""
.. module:: ingest.result.completion
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Job-kind-aware completion ingest for build / provision runs.

.. moduleauthor:: Code Craft AI LLC

The testbase result path (``ingest.result.scanner``) parses a
testbase result tree, persists per-test rows, and emits the
testbase ingest events. Build and provision runs ALSO flow a
``run_id`` through the same presigned-upload + ``results/complete``
surface, but their uploaded trees are NOT testbase trees -- they
carry no ``testrun_summary.json`` / per-test records, only raw
artifact files.

This module is the direct, non-testbase completion path for those
two job kinds. Given a ``ResultManifest`` whose ``format_tag`` is
``build`` or ``provision``, it:

* resolves the domain run (:class:`BuildRun` / :class:`InfraRun`)
  -- the domain run's primary key IS the run-state ``run_id`` the
  build / infra orchestrators stamp at trigger time, so the lookup
  is a direct primary-key fetch;
* advances the domain run to its terminal state
  (``COMPLETED`` / ``FAILED``) from the manifest's
  ``terminal_outcome``;
* records the uploaded artifact files against the domain run so
  the artifact read endpoints return them (a build-artifacts
  manifest for build runs; the ``output_digest`` + annotation
  reference for infra runs, which do not model a per-file
  artifact index);
* drives the run-state machine to a terminal state too, so a
  build / provision ``run_id`` does not stay stuck in
  ``DISPATCHING`` / ``RUNNING``.

The testbase path is untouched -- :mod:`ingest.result.scanner` and
the test result loop continue to behave exactly as before.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now

from ccai.pychestrate.webservice.jobs.run.state.advance import (
    advance_to_cancelled as _advance_to_cancelled,
)
from ccai.pychestrate.webservice.jobs.run.state.advance import (
    advance_to_terminal as _advance_to_terminal,
)
from ccai.pychestrate.webservice.orchestration.rpa import (
    service as rpa_service,
)
from ccai.pychestrate.webservice.orchestration.rpa.errors import (
    RpaJobNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.rpa.models import (
    RpaJobStatus,
)
from ccai.pychestrate.webservice.orchestration.build import (
    repository as build_repository,
)
from ccai.pychestrate.webservice.orchestration.build import (
    service as build_service,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts import (
    repository as build_artifacts_repository,
)
from ccai.pychestrate.webservice.orchestration.build.errors import (
    BuildRunNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.build.models import (
    BuildRunState,
)
from ccai.pychestrate.webservice.orchestration.infra.runs import (
    repository as infra_repository,
)
from ccai.pychestrate.webservice.orchestration.infra.runs import (
    service as infra_service,
)
from ccai.pychestrate.webservice.orchestration.infra.runs.errors import (
    InfraRunNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.infra.runs.models import (
    InfraRunState,
)


#: ``format_tag`` values this module owns. A manifest carrying any
#: other tag (notably ``testbase``) is NOT handled here -- the
#: caller routes it to :mod:`ingest.result.scanner` instead.
BUILD_FORMAT_TAG: str = "build"
PROVISION_FORMAT_TAG: str = "provision"
#: ``format_tag`` an RPA job result manifest carries (6-rpa-orchestration).
RPA_FORMAT_TAG: str = "rpa.result.v1"

#: ``TerminalOutcome`` enum values from the OpenAPI spec that map to
#: a successful build / provision completion. Anything else is
#: treated as a failure.
TERMINAL_OUTCOME_SUCCESS: str = "success"

#: ``TerminalOutcome`` value reported when an operator cancel stopped
#: the run. Both :class:`BuildRunState` and :class:`InfraRunState`
#: carry a ``CANCELLED`` member, so a cancelled build / provision run
#: records as cancelled rather than being folded into ``FAILED``.
TERMINAL_OUTCOME_CANCELLED: str = "cancelled"

#: Artifact-type string stamped on every entry the build-completion
#: path records. The uploaded files are registered as-is -- this PR
#: does not run an artifact-classification pipeline -- so a single
#: generic type is used. ``build_artifacts_repository.insert_entry``
#: persists the row directly, bypassing the registered-type
#: ``validate_payload`` path that ``synthesize_manifest`` enforces.
GENERIC_ARTIFACT_TYPE: str = "build-output-file"

_LOGGER = logging.getLogger("pychestrate.ingest.result.completion")


@dataclass(frozen=True)
class CompletionOutcome:
    """
        Result of one build / provision completion ingest.

        :param run_id: Run UUID.
        :param job_kind: ``"build"`` or ``"provision"``.
        :param domain_state: Terminal state value the domain run
                             row reached.
        :param run_state: Terminal state value the run-state
                          machine reached, or ``None`` when no
                          run-state row exists.
        :param artifacts_recorded: Number of artifact files
                                   registered against the run.
        :param manifest_id: Build-artifacts manifest UUID, or
                            ``None`` for provision runs.
    """
    run_id: str
    job_kind: str
    domain_state: str
    run_state: Optional[str]
    artifacts_recorded: int
    manifest_id: Optional[str]


def _pod_reason(*, manifest: Dict[str, Any], fallback: str) -> str:
    """
        The reason recorded for a run's end: the pod's own explanation (the manifest's ``notes``, for example "1 of 2 tests
        failed." or "RPA job exited with code 3: the packet asked to fail") when it gave one, which is also the text the run
        page, the run event and the failed-run notification show; else ``fallback`` (what the service knows: the outcome).
    """
    notes = str(manifest.get("notes", "") or "").strip()
    rtnval = notes if len(notes) > 0 else fallback
    return rtnval


def _is_success_outcome(*, terminal_outcome: str) -> bool:
    """
        Map a ``ResultManifest.terminal_outcome`` string to a
        success / failure boolean.

        :param terminal_outcome: ``TerminalOutcome`` enum value.

        :returns: True when the manifest reports a successful run.
    """
    rtnval = terminal_outcome == TERMINAL_OUTCOME_SUCCESS
    return rtnval


def _is_cancelled_outcome(*, terminal_outcome: str) -> bool:
    """
        Report whether the manifest says an operator cancel stopped
        the run.

        :param terminal_outcome: ``TerminalOutcome`` enum value.

        :returns: True when the manifest reports a cancelled run.
    """
    rtnval = terminal_outcome == TERMINAL_OUTCOME_CANCELLED
    return rtnval


def _advance_run_state_from_outcome(
        *,
        db_session: DbSession,
        run_id: str,
        terminal_outcome: str,
        reason: str
    ) -> Optional[str]:
    """
        Drive the run-state row terminal in the direction the
        manifest's ``terminal_outcome`` points.

        A cancelled run takes :func:`advance_to_cancelled` so it
        lands in ``CANCELLED`` with ``TerminalOutcome.CANCELLED``;
        anything else keeps the existing success / failure split.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.
        :param terminal_outcome: ``TerminalOutcome`` enum value.
        :param reason: Reason written to the state-audit row.

        :returns: The resulting run-state value string, or ``None``
                  when no run-state row exists.
    """
    actor = "system:result-ingest"

    cancelled = _is_cancelled_outcome(terminal_outcome=terminal_outcome)
    if cancelled is True:
        rtnval = _advance_to_cancelled(
            db_session=db_session,
            run_id=run_id,
            actor=actor,
            reason=reason,
        )
        return rtnval

    succeeded = _is_success_outcome(terminal_outcome=terminal_outcome)
    rtnval = _advance_to_terminal(
        db_session=db_session,
        run_id=run_id,
        succeeded=succeeded,
        actor=actor,
        reason=reason,
    )
    return rtnval


def artifact_files_from_manifest(
        *,
        manifest: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
    """
        Extract the walked artifact-file index the client carried
        in the manifest's ``extras.files`` member.

        The ``pychestrate-client`` result uploader records one
        entry per file it PUT to the shared results backend:
        ``{relative_path, size_bytes, sha256}``. A manifest with no
        ``extras.files`` yields an empty list -- the run still
        reaches terminal, it simply has no artifact rows.

        :param manifest: The decoded ``ResultManifest`` dict.

        :returns: List of artifact-file dicts.
    """
    rtnval: List[Dict[str, Any]] = []

    extras = manifest.get("extras", None)
    if not isinstance(extras, dict):
        return rtnval

    files = extras.get("files", None)
    if not isinstance(files, list):
        return rtnval

    for candidate in files:
        if isinstance(candidate, dict):
            rtnval.append(candidate)

    return rtnval


def _record_build_artifacts(
        *,
        db_session: DbSession,
        project_id: str,
        build_run_id: str,
        files: List[Dict[str, Any]],
        note: str
    ) -> Optional[str]:
    """
        Register the uploaded build artifact files as a
        build-artifacts manifest so
        ``GET /projects/{id}/builds/{id}/artifacts`` returns them.

        The files are registered as-is -- one
        :class:`BuildArtifactEntryIndex` row per uploaded file,
        carrying the generic :data:`GENERIC_ARTIFACT_TYPE`. The
        rows are inserted through the build-artifacts repository
        directly; the repository write skips the registered-type
        ``validate_payload`` gate that ``synthesize_manifest``
        applies, which is correct here because this PR registers
        raw build output rather than running a classification
        pipeline.

        Idempotent: a build run that already has a manifest (a
        re-posted ``results/complete``) returns the existing
        manifest id without inserting duplicates.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Owning project UUID.
        :param build_run_id: BuildRun UUID.
        :param files: Artifact-file dicts from the manifest.
        :param note: Manifest note string.

        :returns: The build-artifacts manifest UUID, or ``None``
                  when there were no files to record.
    """
    existing = build_artifacts_repository.find_manifest_by_build_run(
        db_session=db_session, build_run_id=build_run_id,
    )
    if existing is not None:
        rtnval = str(existing.manifest_id)
        return rtnval

    if len(files) == 0:
        rtnval = None
        return rtnval

    now = utc_now()
    manifest_row = build_artifacts_repository.insert_manifest(
        db_session=db_session,
        project_id=project_id,
        build_run_id=build_run_id,
        entry_count=len(files),
        note=note,
        synthesized_at=now,
    )
    manifest_id = str(manifest_row.manifest_id)

    seen_ids: List[str] = []
    for index, file_entry in enumerate(files):
        relative_path = str(file_entry.get("relative_path", ""))
        if len(relative_path) == 0:
            relative_path = "artifact-{}".format(index)

        artifact_id = relative_path
        if artifact_id in seen_ids:
            artifact_id = "{}#{}".format(relative_path, index)
        seen_ids.append(artifact_id)

        size_bytes = file_entry.get("size_bytes", 0)
        sha256 = str(file_entry.get("sha256", ""))

        build_artifacts_repository.insert_entry(
            db_session=db_session,
            manifest_id=manifest_id,
            artifact_id=artifact_id,
            artifact_type=GENERIC_ARTIFACT_TYPE,
            artifact_name=relative_path,
            storage_uri=relative_path,
            sha256=sha256,
            payload={
                "relative_path": relative_path,
                "size_bytes": size_bytes,
            },
        )

    db_session.commit()
    rtnval = manifest_id
    return rtnval


def complete_build_run(
        *,
        db_session: DbSession,
        run_id: str,
        manifest: Dict[str, Any]
    ) -> CompletionOutcome:
    """
        Ingest a ``format_tag=build`` ``ResultManifest``.

        Advances the :class:`BuildRun` row to ``COMPLETED`` /
        ``FAILED`` from ``manifest.terminal_outcome``, records the
        uploaded artifact files as a build-artifacts manifest, and
        drives the run-state machine row to a terminal state.

        Idempotent on an already-terminal build run -- the existing
        artifacts manifest id is returned without re-recording.

        :param db_session: Active SQLAlchemy session.
        :param run_id: BuildRun UUID (also the run-state run id).
        :param manifest: The decoded ``ResultManifest`` dict.

        :returns: A :class:`CompletionOutcome`.
        :raises: BuildRunNotFoundError when no build run matches.
    """
    build_run = build_repository.find_run_by_id(
        db_session=db_session, run_id=run_id,
    )
    if build_run is None:
        err_lines = ["Build run not found for build result manifest."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise BuildRunNotFoundError(err_msg) from None

    project_id = str(build_run.project_id)
    terminal_outcome = str(manifest.get("terminal_outcome", ""))
    succeeded = _is_success_outcome(terminal_outcome=terminal_outcome)
    cancelled = _is_cancelled_outcome(terminal_outcome=terminal_outcome)

    final_state = BuildRunState.COMPLETED
    if cancelled is True:
        final_state = BuildRunState.CANCELLED
    elif succeeded is False:
        final_state = BuildRunState.FAILED

    notes = str(manifest.get("notes", ""))
    reason = _pod_reason(manifest=manifest, fallback="build result manifest: outcome={}".format(terminal_outcome))

    files = artifact_files_from_manifest(manifest=manifest)

    # Record artifacts BEFORE flipping the build run terminal so the
    # artifact read endpoint is consistent the moment the run shows
    # COMPLETED.
    manifest_id = _record_build_artifacts(
        db_session=db_session,
        project_id=project_id,
        build_run_id=run_id,
        files=files,
        note=notes,
    )

    build_view = build_service.apply_run_terminal(
        db_session=db_session,
        run_id=run_id,
        final_state=final_state,
        reason=reason,
    )

    run_state = _advance_run_state_from_outcome(
        db_session=db_session,
        run_id=run_id,
        terminal_outcome=terminal_outcome,
        reason=reason,
    )

    _LOGGER.info(
        "pychestrate.ingest.result.completion.build run_id=%s state=%s"
        " run_state=%s artifacts=%d",
        run_id,
        build_view.state.value,
        run_state,
        len(files),
    )

    rtnval = CompletionOutcome(
        run_id=run_id,
        job_kind=BUILD_FORMAT_TAG,
        domain_state=build_view.state.value,
        run_state=run_state,
        artifacts_recorded=len(files),
        manifest_id=manifest_id,
    )
    return rtnval


def complete_rpa_run(
        *,
        db_session: DbSession,
        run_id: str,
        manifest: Dict[str, Any]
    ) -> CompletionOutcome:
    """
        Ingest a ``format_tag=rpa.result.v1`` ``ResultManifest``.

        Advances the :class:`RpaJob` row to ``SUCCEEDED`` / ``FAILED`` /
        ``TIMEOUT`` / ``CANCELLED`` from ``manifest.terminal_outcome`` and
        ``extras.rpa_status``, records the exit code and the uploaded
        result-tree prefix, and drives the run-state machine terminal.
        Idempotent on an already-terminal job.

        :raises: RpaJobNotFoundError when no RPA job matches.
    """
    terminal_outcome = str(manifest.get("terminal_outcome", ""))
    succeeded = _is_success_outcome(terminal_outcome=terminal_outcome)
    cancelled = _is_cancelled_outcome(terminal_outcome=terminal_outcome)

    extras = manifest.get("extras", None)
    if not isinstance(extras, dict):
        extras = {}
    rpa_status = str(extras.get("rpa_status", "") or "")
    exit_code: Optional[int] = None
    raw_exit = extras.get("exit_code", None)
    if isinstance(raw_exit, int) and not isinstance(raw_exit, bool):
        exit_code = raw_exit

    final_status = RpaJobStatus.SUCCEEDED
    if cancelled is True or rpa_status == "cancelled":
        final_status = RpaJobStatus.CANCELLED
    elif rpa_status == "timeout":
        final_status = RpaJobStatus.TIMEOUT
    elif succeeded is False:
        final_status = RpaJobStatus.FAILED

    reason = _pod_reason(manifest=manifest, fallback="rpa result manifest: outcome={}".format(terminal_outcome))
    result_root_key = str(manifest.get("backend_key_prefix", "") or "") or None

    job_view = rpa_service.apply_run_terminal(
        db_session=db_session,
        job_id=run_id,
        final_status=final_status,
        exit_code=exit_code,
        result_root_key=result_root_key,
        reason=reason,
    )

    # A job the pod says it cancelled (``rpa_status``) is a cancelled run whatever outcome the manifest names: a pod that reports a
    # cancel as a plain failure left the run FAILED beside a CANCELLED job, and a cancelled job in the "needs attention" list.
    run_outcome = TERMINAL_OUTCOME_CANCELLED if final_status == RpaJobStatus.CANCELLED else terminal_outcome
    run_state = _advance_run_state_from_outcome(
        db_session=db_session,
        run_id=run_id,
        terminal_outcome=run_outcome,
        reason=reason,
    )

    files = artifact_files_from_manifest(manifest=manifest)
    _LOGGER.info(
        "pychestrate.ingest.result.completion.rpa run_id=%s status=%s run_state=%s files=%d",
        run_id, job_view.status.value, run_state, len(files),
    )

    rtnval = CompletionOutcome(
        run_id=run_id,
        job_kind=RPA_FORMAT_TAG,
        domain_state=job_view.status.value,
        run_state=run_state,
        artifacts_recorded=len(files),
        manifest_id=None,
    )
    return rtnval


def complete_provision_run(
        *,
        db_session: DbSession,
        run_id: str,
        manifest: Dict[str, Any]
    ) -> CompletionOutcome:
    """
        Ingest a ``format_tag=provision`` ``ResultManifest``.

        Advances the :class:`InfraRun` row to ``COMPLETED`` /
        ``FAILED`` from ``manifest.terminal_outcome`` and drives the
        run-state machine row to a terminal state.

        Infra runs do not model a per-file artifact index (there is
        no infra-run-artifacts repository -- the infra domain
        carries plan summaries + an ``output_digest_sha256``). The
        uploaded artifact files therefore land on the shared
        results backend (via the presigned-upload path) and a
        reference -- the file count + the run's
        ``backend_key_prefix`` -- is recorded on the InfraRun's
        ``output_digest_sha256`` / ``final_state_reason`` so the
        completion is queryable. This is the minimal in-scope
        behaviour the task calls for; a first-class infra artifact
        index is out of scope.

        Idempotent on an already-terminal infra run.

        :param db_session: Active SQLAlchemy session.
        :param run_id: InfraRun UUID (also the run-state run id).
        :param manifest: The decoded ``ResultManifest`` dict.

        :returns: A :class:`CompletionOutcome`.
        :raises: InfraRunNotFoundError when no infra run matches.
    """
    infra_run = infra_repository.find_run_by_id(
        db_session=db_session, run_id=run_id,
    )
    if infra_run is None:
        err_lines = ["Infra run not found for provision result manifest."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise InfraRunNotFoundError(err_msg) from None

    terminal_outcome = str(manifest.get("terminal_outcome", ""))
    succeeded = _is_success_outcome(terminal_outcome=terminal_outcome)
    cancelled = _is_cancelled_outcome(terminal_outcome=terminal_outcome)

    final_state = InfraRunState.COMPLETED
    if cancelled is True:
        final_state = InfraRunState.CANCELLED
    elif succeeded is False:
        final_state = InfraRunState.FAILED

    files = artifact_files_from_manifest(manifest=manifest)
    backend_key_prefix = str(manifest.get("backend_key_prefix", ""))

    reason_lines = [
        "provision result manifest: outcome={}".format(terminal_outcome),
    ]
    reason_lines.append("artifact_files={}".format(len(files)))
    if len(backend_key_prefix) > 0:
        reason_lines.append("backend_key_prefix={}".format(backend_key_prefix))
    reason = _pod_reason(manifest=manifest, fallback=" ".join(reason_lines))

    # The InfraRun has no artifact table; carry the file count under
    # the manifest's ``extras`` digest if present, else leave the
    # output digest untouched. The artifact bytes themselves live on
    # the shared results backend under ``backend_key_prefix``.
    extras = manifest.get("extras", None)
    output_digest = ""
    if isinstance(extras, dict):
        candidate_digest = extras.get("output_digest_sha256", None)
        if isinstance(candidate_digest, str) and len(candidate_digest) == 64:
            output_digest = candidate_digest

    infra_view = infra_service.apply_run_terminal(
        db_session=db_session,
        run_id=run_id,
        final_state=final_state,
        output_digest_sha256=output_digest,
        reason=reason,
    )

    run_state = _advance_run_state_from_outcome(
        db_session=db_session,
        run_id=run_id,
        terminal_outcome=terminal_outcome,
        reason=reason,
    )

    _LOGGER.info(
        "pychestrate.ingest.result.completion.provision run_id=%s state=%s"
        " run_state=%s artifact_files=%d",
        run_id,
        infra_view.state.value,
        run_state,
        len(files),
    )

    rtnval = CompletionOutcome(
        run_id=run_id,
        job_kind=PROVISION_FORMAT_TAG,
        domain_state=infra_view.state.value,
        run_state=run_state,
        artifacts_recorded=len(files),
        manifest_id=None,
    )
    return rtnval


__all__ = [
    "BUILD_FORMAT_TAG",
    "PROVISION_FORMAT_TAG",
    "RPA_FORMAT_TAG",
    "complete_rpa_run",
    "TERMINAL_OUTCOME_CANCELLED",
    "TERMINAL_OUTCOME_SUCCESS",
    "GENERIC_ARTIFACT_TYPE",
    "CompletionOutcome",
    "artifact_files_from_manifest",
    "complete_build_run",
    "complete_provision_run",
]
