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
from ccai.pychestrate.webservice.orchestration.rpa.candidates import resolve_dispatch_candidates
from ccai.pychestrate.webservice.pods.lifecycle_service import draining_note
from ccai.pychestrate.webservice.pods.models import PodDefinition, PodRegistration, PodRuntimeState, PodState, RegistrationState

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


def test_a_draining_or_released_pod_is_sent_no_new_work_by_any_dispatch_path():
    """
    **Feature: pod lifecycle (drain)**
    **Property: Drain changed the pod's state and nothing else (a draining pod on a real lab pod went on being sent new tests); a pod that is draining, released or failed is now offered to no
    dispatch path (test runs, builds, provisioning runs, pipeline stages, RPA jobs), while a ready or in-use pod, a pod whose client is lost (the dispatcher waits for it) and a pod with no recorded
    state still are.**
    """
    _engine, session = build_in_memory_session()
    project = str(uuid.uuid4())
    pods = {}
    for label, state in (
        ("ready", PodState.READY), ("in_use", PodState.IN_USE), ("draining", PodState.DRAINING), ("released", PodState.RELEASED), ("failed", PodState.FAILED),
        ("lost", PodState.CLIENT_LOST), ("unrecorded", None),
    ):
        pod, client = str(uuid.uuid4()), str(uuid.uuid4())
        pods[label] = pod
        session.add(PodDefinition(pod_id=pod, project_id=project, pod_name=label, current_version=1))
        _register(session, pod_id=pod, client_id=client, tags=None)
        if state is not None:
            session.add(PodRuntimeState(pod_id=pod, state=state))
    session.commit()
    by_pod = {pod: label for label, pod in pods.items()}

    def _offered(candidates: object) -> list:
        return sorted(by_pod[candidate.pod_id] for candidate in candidates)

    every_pod = []
    for label in pods:
        every_pod.extend(test_runs_routes._candidates_for_pod(db_session=session, pod_id=pods[label]))
    expected = ["in_use", "lost", "ready", "unrecorded"]
    testbase.assert_equal(
        (
            _offered(every_pod),
            _offered(c for label in pods for c in build_runs_routes._candidates_for_pod(db_session=session, pod_id=pods[label])),
            _offered(c for label in pods for c in provisioning_runs_routes._candidates_for_pod(db_session=session, pod_id=pods[label])),
            _offered(PipelineOrchestrator._eligible_candidates_for_project(db_session=session, project_id=project)),
            _offered(resolve_dispatch_candidates(db_session=session, project_id=project)),
            _offered(resolve_dispatch_candidates(db_session=session, project_id=project, target_pod_id=pods["draining"])),
        ),
        (expected, expected, expected, expected, expected, []),
    )
    return


def test_the_no_pod_answer_names_the_draining_pods_when_there_are_any():
    """
    **Feature: pod lifecycle (drain)**
    **Property: when the project has draining pods the "no enrolled pod matches" answer of the test, build and provisioning routes adds "Pods that are draining take no new work: <names>."
    (at most five, then "and n more"); with none draining it is unchanged; another project's draining pod is not named.**
    """
    _engine, session = build_in_memory_session()
    project, other = str(uuid.uuid4()), str(uuid.uuid4())
    for owner, name, state in ((project, "lab-pod-b", PodState.DRAINING), (project, "lab-pod-a", PodState.DRAINING), (project, "ready-pod", PodState.READY), (other, "elsewhere", PodState.DRAINING)):
        pod = str(uuid.uuid4())
        session.add(PodDefinition(pod_id=pod, project_id=owner, pod_name=name, current_version=1))
        session.add(PodRuntimeState(pod_id=pod, state=state))
    session.commit()
    for number in range(5):
        pod = str(uuid.uuid4())
        session.add(PodDefinition(pod_id=pod, project_id=other, pod_name="many-{}".format(number), current_version=1))
        session.add(PodRuntimeState(pod_id=pod, state=PodState.DRAINING))
    session.commit()

    import os

    from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES

    webservice = os.path.dirname(os.path.dirname(SITE_DIRECTORIES.DIR_STATIC))
    wired = [
        open(os.path.join(webservice, "orchestration", *parts), encoding="utf-8").read().count("draining_note(db_session=db_session, project_id=project_id)")
        for parts in (("test", "restapi", "v1", "test_runs_routes.py"), ("build", "restapi", "v1", "build_runs_routes.py"), ("infra", "restapi", "v1", "provisioning_runs_routes.py"))
    ]

    testbase.assert_equal(
        (draining_note(db_session=session, project_id=project), draining_note(db_session=session, project_id=str(uuid.uuid4())), draining_note(db_session=session, project_id=other).endswith("and 1 more."), wired),
        (" Pods that are draining take no new work: lab-pod-a, lab-pod-b.", "", True, [1, 1, 1]),
    )
    return
