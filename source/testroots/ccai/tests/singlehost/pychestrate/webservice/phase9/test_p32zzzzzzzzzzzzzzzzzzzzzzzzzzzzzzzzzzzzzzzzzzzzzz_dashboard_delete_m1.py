"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_dashboard_delete_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A dashboard can be deleted over REST (ORC-26).

.. moduleauthor:: Code Craft AI LLC

A dashboard could be created, renamed and re-tiled but never removed, although the service already deleted one on request. ``DELETE`` on
``.../dashboards/{dashboard_id}`` exposes it: ``204`` and the dashboard and its tiles are gone; ``404`` for an unknown dashboard or one in another
project; ``403`` without ``system:dashboards.write``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List

from ccai import testbase

from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.metrics.dashboards import (
    DashboardEventTopics,
    TileInstance,
    create_dashboard,
    get_dashboard,
    list_dashboards_for_project,
    register_builtin_extensions as dashboards_register,
)
from ccai.pychestrate.webservice.metrics.dashboards.errors import DashboardNotFoundError
from ccai.pychestrate.webservice.metrics.ingest import register_builtin_extensions as metrics_ingest_register
from ccai.pychestrate.webservice.metrics.restapi.v1 import dashboards_routes
from ccai.pychestrate.webservice.metrics.timeseries import (
    register_builtin_extensions as timeseries_register,
    reset_for_testing,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session
from ccai.tests.singlehost.pychestrate.webservice.phase10.test_p20f_dashboards_routes_m1 import (
    _FakePrincipal,
    _FakeProject,
    _FakeRequest,
    _patch_check_permission,
    _patch_project_exists,
)


PROJECT = "00000000-0000-4000-8000-0000000a0001"
OTHER_PROJECT = "00000000-0000-4000-8000-0000000a0002"


def _prepare() -> Any:
    reset_registry_for_testing()
    reset_event_bus()
    reset_for_testing()
    timeseries_register()
    metrics_ingest_register()
    dashboards_register()
    _engine, session = build_in_memory_session()
    return session


def _board(session: Any, *, name: str, project: str = PROJECT) -> Any:
    tile = TileInstance(tile_id="t1", kind="metric-line-chart", x=0, y=0, w=6, h=3, config={"metric_name": "m1", "label_filter": {}, "range_seconds": 60})
    return create_dashboard(db_session=session, project_id=project, name=name, tiles=[tile])


def _delete(session: Any, dashboard_id: str, *, project: str = PROJECT, allowed: bool = True) -> Any:
    permission = _patch_check_permission(allowed=allowed)
    exists = _patch_project_exists(project=_FakeProject(project_id=project))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/{}/dashboards/{}".format(project, dashboard_id),
            path_params={"project_id": project, "dashboard_id": dashboard_id}, db_session=session, auth_principal=_FakePrincipal(),
        )
        return dashboards_routes.handle_delete_dashboard(request)
    finally:
        exists.deactivate()
        permission.deactivate()


def test_delete_answers_204_removes_the_dashboard_and_says_so_on_the_bus():
    """
    **Feature: dashboard delete (ORC-26)**
    **Property: DELETE answers 204; the dashboard (with its tile) is gone and listing the project no longer shows it; entity.dashboard.deleted is
    published with its id; the project's other dashboard is untouched; a second DELETE is 404.**
    """
    session = _prepare()
    doomed = _board(session, name="doomed")
    kept = _board(session, name="kept")
    events: List[EntityEvent] = []
    subscribe(topic=DashboardEventTopics.DELETED, subscriber=lambda event: events.append(event))

    first = _delete(session, doomed.dashboard_id)
    names = sorted(view.name for view in list_dashboards_for_project(db_session=session, project_id=PROJECT))
    gone = "still there"
    try:
        get_dashboard(db_session=session, dashboard_id=doomed.dashboard_id)
    except DashboardNotFoundError:
        gone = "gone"
    second = _delete(session, doomed.dashboard_id)

    testbase.assert_equal(
        (first.status_code, names, gone, len(events), events[0].payload["dashboard_id"] == doomed.dashboard_id, second.status_code, get_dashboard(db_session=session, dashboard_id=kept.dashboard_id).name),
        (204, ["kept"], "gone", 1, True, 404, "kept"),
    )
    return


def test_another_projects_dashboard_and_a_caller_without_write_are_refused_and_nothing_goes():
    """
    **Feature: dashboard delete (ORC-26)**
    **Property: deleting a dashboard through another project's address is 404 and the dashboard stays; a caller without the write permission gets 403
    and the dashboard stays.**
    """
    session = _prepare()
    mine = _board(session, name="mine")
    foreign = _board(session, name="foreign", project=OTHER_PROJECT)

    wrong_project = _delete(session, foreign.dashboard_id)
    forbidden = _delete(session, mine.dashboard_id, allowed=False)

    testbase.assert_equal(
        (
            wrong_project.status_code, forbidden.status_code,
            get_dashboard(db_session=session, dashboard_id=foreign.dashboard_id).name, get_dashboard(db_session=session, dashboard_id=mine.dashboard_id).name,
        ),
        (404, 403, "foreign", "mine"),
    )
    return
