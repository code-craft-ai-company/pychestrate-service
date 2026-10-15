"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_test_run_candidates_carry_tags_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A test that requires a capability tag can be dispatched to a pod that advertised it (E2E-18).

.. moduleauthor:: Code Craft AI LLC

The test-run route built every dispatch candidate with no capability tags, so a catalog entry that required one ("lab-browser") found no eligible pod even when the pod had advertised exactly
that tag (seen on a real pod once the client could advertise at all). Each candidate now carries the tags its client advertised.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from ccai import testbase

from ccai.pychestrate.webservice.agents.models import ClientCapability
from ccai.pychestrate.webservice.orchestration.build.restapi.v1 import build_runs_routes
from ccai.pychestrate.webservice.orchestration.infra.restapi.v1 import provisioning_runs_routes
from ccai.pychestrate.webservice.orchestration.pipelines.execution.orchestrator import PipelineOrchestrator
from ccai.pychestrate.webservice.orchestration.test import orchestrator as orchestrator_module
from ccai.pychestrate.webservice.orchestration.test.restapi.v1 import test_runs_routes
from ccai.pychestrate.webservice.pods.models import PodDefinition, PodRegistration, RegistrationState

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session


def _register(session: object, *, pod_id: str, client_id: str, tags: object) -> None:
    session.add(PodRegistration(
        registration_id=str(uuid.uuid4()), pod_id=pod_id, pod_definition_version=1, client_id=client_id, state=RegistrationState.REGISTERED, report_hash="x",
    ))
    if tags is not None:
        session.add(ClientCapability(
            capability_id=str(uuid.uuid4()), client_id=client_id, kind="rpa", value_json={"value": {"job_types": ["invoice@1"], "taskplus": None, "tags": tags}}, revision_token="r",
        ))
    session.flush()


def test_a_candidate_carries_the_tags_its_client_advertised():
    """
    **Feature: capability matching (E2E-18)**
    **Property: the candidates built for a pod have the capability kinds, ``rpa:<job type>`` labels and free-form tags their client advertised; a client that advertised nothing
    has none; a candidate whose tags include every required tag is eligible and one that lacks a required tag is not.**
    """
    _engine, session = build_in_memory_session()
    pod_a, client_a = str(uuid.uuid4()), str(uuid.uuid4())
    pod_b, client_b = str(uuid.uuid4()), str(uuid.uuid4())
    _register(session, pod_id=pod_a, client_id=client_a, tags=["lab-browser"])
    _register(session, pod_id=pod_b, client_id=client_b, tags=None)
    session.commit()

    advertised = test_runs_routes._candidates_for_pod(db_session=session, pod_id=pod_a)
    silent = test_runs_routes._candidates_for_pod(db_session=session, pod_id=pod_b)
    orchestrator = orchestrator_module.TestOrchestrator.__new__(orchestrator_module.TestOrchestrator)

    def _eligible(candidates: object, required: tuple) -> int:
        return len(orchestrator._filter_capability_matches(candidates=candidates, required_tags=required))

    testbase.assert_equal(
        (
            sorted(advertised[0].capability_tags), list(silent[0].capability_tags),
            _eligible(advertised, ("lab-browser",)), _eligible(advertised, ("rpa:invoice@1", "lab-browser")), _eligible(advertised, ("lab-gpu",)),
            _eligible(silent, ("lab-browser",)), _eligible(silent, ()),
        ),
        (["lab-browser", "rpa", "rpa:invoice@1"], [], 1, 1, 0, 0, 1),
    )
    return


def test_build_provisioning_and_pipeline_dispatch_see_the_advertised_tags_too():
    """
    **Feature: capability matching (E2E-18)**
    **Property: the build and provisioning routes' candidates and the pipeline orchestrator's (which dispatches a pipeline's test step, so a test needing a tag failed inside a
    pipeline on a real pod) carry the client's advertised tags, and none when it advertised nothing.**
    """
    _engine, session = build_in_memory_session()
    project, pod, client = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    session.add(PodDefinition(pod_id=pod, project_id=project, pod_name="lab-pod", current_version=1))
    _register(session, pod_id=pod, client_id=client, tags=["lab-browser"])
    quiet_pod, quiet_client = str(uuid.uuid4()), str(uuid.uuid4())
    session.add(PodDefinition(pod_id=quiet_pod, project_id=project, pod_name="quiet-pod", current_version=1))
    _register(session, pod_id=quiet_pod, client_id=quiet_client, tags=None)
    session.commit()

    def _tags(candidates: object) -> object:
        return {candidate.client_id: sorted(candidate.capability_tags) for candidate in candidates}

    pipeline = PipelineOrchestrator._eligible_candidates_for_project(db_session=session, project_id=project)
    testbase.assert_equal(
        (
            _tags(build_runs_routes._candidates_for_pod(db_session=session, pod_id=pod)),
            _tags(provisioning_runs_routes._candidates_for_pod(db_session=session, pod_id=pod)),
            _tags(pipeline),
        ),
        (
            {client: ["lab-browser", "rpa", "rpa:invoice@1"]},
            {client: ["lab-browser", "rpa", "rpa:invoice@1"]},
            {client: ["lab-browser", "rpa", "rpa:invoice@1"], quiet_client: []},
        ),
    )
    return
