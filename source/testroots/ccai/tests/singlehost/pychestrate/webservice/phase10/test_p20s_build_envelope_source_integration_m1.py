"""
.. module:: test_p20s_build_envelope_source_integration_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for source integrations as a first-class build
               job envelope source reference (PR p20s).

.. moduleauthor:: Code Craft AI LLC

Covers the server-side source-integration wiring:

* A build triggered with a ``source_integration_id`` resolves the
  registered source-integration and embeds a structured ``source``
  block on the ``job_kind=build`` JobEnvelope.
* A build triggered WITHOUT a ``source_integration_id`` still works
  -- the envelope carries no ``source`` block (backward compat).
* The envelope still signs + verifies with the ``source`` block.
* An envelope dict minted WITHOUT a ``source`` key parses back
  cleanly with ``source=None`` (backward compat).
* An unknown ``source_integration_id`` raises
  :class:`BuildSourceIntegrationUnknownError`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Tuple

from ccai import testbase

from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.jobs.dispatch import (
    InMemoryTransport,
    JobDispatcher,
    register_builtin_extensions as dispatch_register,
)
from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from ccai.pychestrate.webservice.jobs.envelope import (
    EnvelopeSignerBootstrapConfig,
    JOB_KIND_BUILD,
    SOURCE_KIND_GIT,
    install_envelope_signer,
    verify as verify_envelope,
)
from ccai.pychestrate.webservice.jobs.envelope import signer as envelope_signer
from ccai.pychestrate.webservice.jobs.envelope.canonical import (
    dict_to_envelope,
    envelope_to_dict,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    reset_for_testing as reset_event_bus,
)
from ccai.pychestrate.webservice.orchestration.build import (
    register_builtin_extensions as build_register,
    service as build_service,
)
from ccai.pychestrate.webservice.orchestration.build.errors import (
    BuildSourceIntegrationUnknownError,
)
from ccai.pychestrate.webservice.orchestration.build.models import (
    BuildRunState,
)
from ccai.pychestrate.webservice.orchestration.source import (
    register_builtin_extensions as source_register,
    service as source_service,
)

# Side-effect imports so the Layer-5 + build + source model tables
# attach to the shared Phase-1 metadata before ``create_all`` runs.
from ccai.pychestrate.webservice.orchestration.build import models as _build_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.source import models as _source_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.run.state import models as _run_state_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.envelope import models as _envelope_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.results import models as _results_models  # noqa: F401

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-0000000020f0"
UNKNOWN_INTEGRATION_ID = "ffffffff-ffff-4000-8000-0000000020ff"


def _prepare_runtime() -> None:
    """
        Reset cross-test globals + register the build runner kind,
        the dispatch strategy, the SCM provider, and an ephemeral
        envelope signing key.

        :returns: None.
    """
    reset_registry_for_testing()
    reset_event_bus()
    envelope_signer.reset_for_testing()
    build_service.set_active_job_dispatcher(dispatcher=None)
    build_service.set_active_results_backend(backend=None)
    dispatch_register()
    build_register()
    source_register()
    os.environ["PYCHESTRATE_DEV_MODE"] = "1"
    try:
        install_envelope_signer(
            config=EnvelopeSignerBootstrapConfig(
                source="dev",
                file_path=None,
                env_var=None,
                key_id="test-p20s-source-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    return


def _build_inputs(
        *,
        source_integration_id=None
    ) -> build_service.BuildRunInputs:
    """
        A valid Makefile build-run input payload.

        :param source_integration_id: Optional source-integration id.

        :returns: :class:`BuildRunInputs`.
    """
    rtnval = build_service.BuildRunInputs(
        runner_kind="makefile",
        runner_inputs={"targets": ["all"]},
        input_files={"Makefile": "d" * 64},
        env={"CC": "gcc"},
        source_integration_id=source_integration_id,
    )
    return rtnval


def _one_candidate() -> Tuple[DispatchCandidate, ...]:
    """
        A single eligible dispatch candidate.

        :returns: One-element tuple of :class:`DispatchCandidate`.
    """
    rtnval = (
        DispatchCandidate(
            client_id="11111111-1111-4000-8000-0000000020f1",
            pod_id="22222222-2222-4000-8000-0000000020f2",
            capability_tags=tuple(),
            inflight_dispatch_count=0,
            last_dispatched_at_iso="",
        ),
    )
    return rtnval


def _register_source_integration(*, session) -> str:
    """
        Register a GitHub source integration for the test project
        and return its integration id.

        :param session: Active SQLAlchemy session.

        :returns: The registered integration id.
    """
    view = source_service.set_project_config(
        db_session=session,
        project_id=PROJECT_UUID,
        provider_name="github",
        repo_key="acme/widget",
        polling_ref_glob="release-1.x",
    )
    rtnval = view.project_id
    return rtnval


def test_build_with_source_integration_embeds_source_block():
    """
    **Feature: 6-source-integrations PR p20s**
    **Property: a build triggered with a source_integration_id
    embeds a structured `source` block (kind/url/ref/integration_id)
    on the job_kind=build JobEnvelope.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    build_service.set_active_job_dispatcher(
        dispatcher=JobDispatcher(transport=transport),
    )

    integration_id = _register_source_integration(session=session)

    view = build_service.trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_build_inputs(source_integration_id=integration_id),
        aspects=build_service.BuildTriggerAspects(
            candidates=_one_candidate(),
            project_slug="proj-slug",
        ),
    )
    testbase.assert_equal(view.state, BuildRunState.RUNNING)

    signed = transport.calls()[0].signed
    source = signed.envelope.source
    testbase.assert_equal(source is not None, True)
    testbase.assert_equal(source.kind, SOURCE_KIND_GIT)
    testbase.assert_equal(source.url, "https://github.com/acme/widget.git")
    testbase.assert_equal(source.ref, "release-1.x")
    testbase.assert_equal(source.integration_id, integration_id)
    testbase.assert_equal(source.credentials_ref, "")

    # The build-run view mirrors the resolved source block.
    testbase.assert_equal(view.source is not None, True)
    testbase.assert_equal(
        view.source["url"], "https://github.com/acme/widget.git",
    )
    return


def test_build_without_source_integration_still_works():
    """
    **Feature: 6-source-integrations PR p20s**
    **Property: a build triggered WITHOUT a source_integration_id
    still dispatches; the envelope carries no `source` block.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    build_service.set_active_job_dispatcher(
        dispatcher=JobDispatcher(transport=transport),
    )

    view = build_service.trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_build_inputs(source_integration_id=None),
        aspects=build_service.BuildTriggerAspects(
            candidates=_one_candidate(),
            project_slug="proj-slug",
        ),
    )
    testbase.assert_equal(view.state, BuildRunState.RUNNING)

    signed = transport.calls()[0].signed
    testbase.assert_equal(signed.envelope.source, None)
    testbase.assert_equal(view.source, None)
    return


def test_envelope_with_source_block_signs_and_verifies():
    """
    **Feature: 5-job-envelope PR p20s**
    **Property: an envelope carrying a `source` block signs and
    verifies; the signed canonical payload round-trips.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    build_service.set_active_job_dispatcher(
        dispatcher=JobDispatcher(transport=transport),
    )

    integration_id = _register_source_integration(session=session)
    build_service.trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_build_inputs(source_integration_id=integration_id),
        aspects=build_service.BuildTriggerAspects(
            candidates=_one_candidate(),
            project_slug="proj-slug",
        ),
    )

    signed = transport.calls()[0].signed
    testbase.assert_equal(signed.envelope.job_kind, JOB_KIND_BUILD)
    verification = verify_envelope(signed=signed)
    testbase.assert_equal(verification.valid, True)

    # The source block survives a canonical round-trip.
    rehydrated = dict_to_envelope(
        candidate=envelope_to_dict(envelope=signed.envelope),
    )
    testbase.assert_equal(
        rehydrated.source.integration_id, integration_id,
    )
    testbase.assert_equal(
        rehydrated.source.url, "https://github.com/acme/widget.git",
    )
    return


def test_envelope_without_source_key_parses_with_source_none():
    """
    **Feature: 5-job-envelope PR p20s**
    **Property: an envelope dict minted WITHOUT a `source` key
    parses back cleanly with source == None -- pre-source-block
    envelopes still validate.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    build_service.set_active_job_dispatcher(
        dispatcher=JobDispatcher(transport=transport),
    )

    build_service.trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_build_inputs(source_integration_id=None),
        aspects=build_service.BuildTriggerAspects(
            candidates=_one_candidate(),
            project_slug="proj-slug",
        ),
    )
    signed = transport.calls()[0].signed
    envelope_dict = envelope_to_dict(envelope=signed.envelope)

    # Drop the source key entirely -- simulate a pre-source envelope.
    del envelope_dict["source"]
    rehydrated = dict_to_envelope(candidate=envelope_dict)
    testbase.assert_equal(rehydrated.source, None)
    return


def test_unknown_source_integration_id_raises():
    """
    **Feature: 6-source-integrations PR p20s**
    **Property: triggering a build with an unknown
    source_integration_id raises BuildSourceIntegrationUnknownError
    and persists no build run.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    build_service.set_active_job_dispatcher(
        dispatcher=JobDispatcher(transport=InMemoryTransport()),
    )

    raised = False
    try:
        build_service.trigger_run(
            db_session=session,
            project_id=PROJECT_UUID,
            inputs=_build_inputs(
                source_integration_id=UNKNOWN_INTEGRATION_ID,
            ),
            aspects=build_service.BuildTriggerAspects(
                candidates=_one_candidate(),
                project_slug="proj-slug",
            ),
        )
    except BuildSourceIntegrationUnknownError:
        raised = True
    testbase.assert_equal(raised, True)

    runs = build_service.list_build_runs_for_project(
        db_session=session, project_id=PROJECT_UUID,
    )
    testbase.assert_equal(len(runs), 0)
    return
