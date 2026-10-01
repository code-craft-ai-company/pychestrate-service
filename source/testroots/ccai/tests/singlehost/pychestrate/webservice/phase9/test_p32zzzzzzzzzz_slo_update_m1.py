"""
.. module:: test_p32zzzzzzzzzz_slo_update_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: An SLO can be edited (ORC-26): service rules, the PUT route and the event.

.. moduleauthor:: Code Craft AI LLC

An SLO could only be created or deleted: fixing a typo in a name or tightening a target meant deleting the objective and
losing its history. ``update_slo`` replaces the editable definition under the rules of create (unique name, a target in
0..1, a positive window, a config the kind accepts), keeps the kind and the project, bumps the version and says what
changed; ``PUT .../slos/{slo_id}`` is its REST face.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from ccai import testbase

from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.metrics.restapi.v1 import slos_routes
from ccai.pychestrate.webservice.metrics.slos import (
    SLOConfigInvalidError,
    SLOConflictError,
    SLOEventTopics,
    SLONotFoundError,
    create_slo,
    get_slo,
    register_builtin_extensions as slos_register,
    update_slo,
)
from ccai.pychestrate.webservice.metrics.timeseries import (
    register_builtin_extensions as timeseries_register,
    reset_for_testing,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session
from ccai.tests.singlehost.pychestrate.webservice.phase9.test_p9c_slo_views_m1 import (
    PROJECT_UUID,
    _seed_metrics,
    _valid_config,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10.test_p21c_slos_routes_m1 import (
    _FakePrincipal,
    _FakeProject,
    _FakeRequest,
    _decode_body,
    _patch_check_permission,
    _patch_project_exists,
)


def _prepare():
    reset_registry_for_testing()
    reset_event_bus()
    reset_for_testing()
    timeseries_register()
    slos_register()
    _engine, session = build_in_memory_session()
    _seed_metrics(session=session)
    return session


def _create(session, *, name="checkout", target=0.99):
    rtnval = create_slo(
        db_session=session, project_id=PROJECT_UUID, name=name, kind="availability_ratio", target=target,
        window_seconds=604800, definition_config=_valid_config(),
    )
    return rtnval


def test_update_changes_the_fields_bumps_the_version_and_names_what_changed():
    """
    **Feature: SLO edit (ORC-26)**
    **Property: update_slo stores the new name, target, window and description on the same SLO (same id, kind and
    project), bumps the version, and publishes entity.slo.updated naming exactly the fields that changed.**
    """
    session = _prepare()
    created = _create(session)
    updated_events: List[EntityEvent] = []
    subscribe(topic=SLOEventTopics.UPDATED, subscriber=lambda e: updated_events.append(e))

    after = update_slo(
        db_session=session, slo_id=created.slo_id, name="checkout availability", target=0.995, window_seconds=604800,
        description="the checkout path", definition_config=_valid_config(),
    )
    stored = get_slo(db_session=session, slo_id=created.slo_id)

    testbase.assert_equal(
        (
            stored.slo_id == created.slo_id, stored.kind, stored.project_id,
            stored.name, stored.target, stored.window_seconds, stored.description, stored.version, after.version,
            len(updated_events), sorted(updated_events[0].payload["changed"]), updated_events[0].payload["version"],
        ),
        (
            True, "availability_ratio", PROJECT_UUID,
            "checkout availability", 0.995, 604800, "the checkout path", 2, 2,
            1, ["description", "name", "target"], 2,
        ),
    )
    return


def test_update_that_changes_nothing_writes_nothing_and_says_nothing():
    """
    **Feature: SLO edit (ORC-26)**
    **Property: saving an SLO exactly as it is leaves the version where it was and publishes no event.**
    """
    session = _prepare()
    created = _create(session)
    updated_events: List[EntityEvent] = []
    subscribe(topic=SLOEventTopics.UPDATED, subscriber=lambda e: updated_events.append(e))

    after = update_slo(
        db_session=session, slo_id=created.slo_id, name=created.name, target=created.target,
        window_seconds=created.window_seconds, description=created.description, definition_config=_valid_config(),
    )
    testbase.assert_equal((after.version, len(updated_events)), (1, 0))
    return


def test_update_applies_the_rules_of_create():
    """
    **Feature: SLO edit (ORC-26)**
    **Property: an empty name, a target outside 0..1, a non-positive window and a config the kind refuses are
    refused with the create errors; a name another SLO in the project has is a conflict (an SLO may keep its own
    name); an unknown id is not found; and after every refusal the SLO is as it was.**
    """
    session = _prepare()
    first = _create(session, name="checkout")
    _create(session, name="search")
    common = dict(db_session=session, slo_id=first.slo_id, name="checkout", target=0.99, window_seconds=604800, description="", definition_config=_valid_config())

    def refused(**changes):
        arguments = dict(common)
        arguments.update(changes)
        try:
            update_slo(**arguments)
        except (SLOConfigInvalidError, SLOConflictError, SLONotFoundError) as xcpt:
            return type(xcpt).__name__
        return "accepted"

    outcomes = (
        refused(name=""),
        refused(target=1.5),
        refused(target=-0.1),
        refused(window_seconds=0),
        refused(definition_config={"good_metric_name": ""}),
        refused(name="search"),
        refused(slo_id="00000000-0000-4000-8000-00000000dead"),
        refused(name="checkout"),
    )
    stored = get_slo(db_session=session, slo_id=first.slo_id)
    testbase.assert_equal(
        (outcomes, stored.name, stored.target, stored.version),
        (
            (
                "SLOConfigInvalidError", "SLOConfigInvalidError", "SLOConfigInvalidError", "SLOConfigInvalidError",
                "SLOConfigInvalidError", "SLOConflictError", "SLONotFoundError", "accepted",
            ),
            "checkout", 0.99, 1,
        ),
    )
    return


def _put(session, *, slo, body, project_id=PROJECT_UUID):
    perm = _patch_check_permission(allowed=True)
    proj = _patch_project_exists(project=_FakeProject(project_id=project_id))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/{}/slos/{}".format(project_id, slo.slo_id),
            path_params={"project_id": project_id, "slo_id": slo.slo_id},
            db_session=session, auth_principal=_FakePrincipal(), body=body,
        )
        response = slos_routes.handle_update_slo(request)
    finally:
        proj.deactivate()
        perm.deactivate()
    return response, _decode_body(response)


def test_put_route_edits_and_refuses_a_kind_change_a_clash_and_a_bad_target():
    """
    **Feature: SLO edit (ORC-26)**
    **Property: PUT .../slos/{id} answers 200 with the SLO after the edit (version 2); a different kind is a 422
    that says to create a new SLO; a name another SLO has is a 409; a target above 1 is a 422; fields left out of the
    body keep their stored values.**
    """
    session = _prepare()
    first = _create(session, name="checkout")
    _create(session, name="search")

    ok, ok_body = _put(session, slo=first, body={"name": "checkout web", "kind": "availability_ratio", "target": 0.97})
    kind, kind_body = _put(session, slo=first, body={"name": "checkout web", "kind": "latency", "target": 0.97})
    clash, _clash_body = _put(session, slo=first, body={"name": "search", "kind": "availability_ratio", "target": 0.97})
    bad, _bad_body = _put(session, slo=first, body={"name": "checkout web", "kind": "availability_ratio", "target": 1.5})
    stored = get_slo(db_session=session, slo_id=first.slo_id)

    testbase.assert_equal(
        (
            ok.status_code, ok_body["name"], ok_body["version"], ok_body["window_seconds"], ok_body["definition_config"] == _valid_config(),
            kind.status_code, "create a new SLO" in kind_body["detail"], clash.status_code, bad.status_code,
            stored.name, stored.target, stored.version,
        ),
        (200, "checkout web", 2, 604800, True, 422, True, 409, 422, "checkout web", 0.97, 2),
    )
    return
