"""
.. module:: test_p22a_release_templates_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the project-scoped release-templates REST
               surface.

.. moduleauthor:: Code Craft AI LLC

Verifies that ``register_release_templates_routes`` attaches the
documented routes to a webworks app and that the input validation
helpers behave as expected.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

from ccai.pychestrate.webservice.projects.restapi.v1 import (
    release_templates_routes as routes_module,
)


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------


class _FakeApp:
    """
        Minimal webworks app stub. Captures every ``attach_route``
        call as a ``(path, methods, handler)`` triple.
    """

    def __init__(self) -> None:
        self.calls: List[Any] = []
        return

    def attach_route(
            self,
            path: str,
            methods: Optional[List[str]] = None
        ) -> Callable:
        resolved_methods = tuple(
            methods if methods is not None else ["GET"]
        )

        def decorator(func: Callable) -> Callable:
            self.calls.append((path, resolved_methods, func))
            return func

        return decorator


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_register_release_templates_routes_attaches_documented_paths():
    """
        ``register_release_templates_routes`` must attach the five
        documented route + method pairs.
    """
    app = _FakeApp()
    routes_module.register_release_templates_routes(
        app=app, version_prefix="/api/v1"
    )

    actual = {(path, tuple(sorted(methods))) for path, methods, _ in app.calls}
    base = "/api/v1/projects/{project_id}/release-templates"
    detail = base + "/{template_id}"
    expected = {
        (base, ("GET",)),
        (base, ("POST",)),
        (detail, ("GET",)),
        (detail, ("PATCH",)),
        (detail, ("DELETE",)),
    }
    assert expected.issubset(actual)
    return


def test_register_release_templates_routes_handlers_match_module_funcs():
    """
        Each attached route's handler must be the corresponding
        public ``handle_*`` function from the routes module.
    """
    app = _FakeApp()
    routes_module.register_release_templates_routes(
        app=app, version_prefix="/api/v1"
    )

    handlers_by_method: Dict[str, Any] = {}
    for path, methods, handler in app.calls:
        if path.endswith("/release-templates"):
            handlers_by_method[(path, methods)] = handler

    base = "/api/v1/projects/{project_id}/release-templates"
    list_handler = handlers_by_method.get((base, ("GET",)))
    create_handler = handlers_by_method.get((base, ("POST",)))

    assert list_handler is routes_module.handle_list_release_templates
    assert create_handler is routes_module.handle_create_release_template
    return


def test_release_templates_permission_keys_exposed():
    """
        Read and write permission keys must follow the ``system:*``
        convention and be exported by the module.
    """
    assert (
        routes_module.RELEASE_TEMPLATES_READ_PERMISSION_KEY
        == "system:release_templates.read"
    )
    assert (
        routes_module.RELEASE_TEMPLATES_WRITE_PERMISSION_KEY
        == "system:release_templates.write"
    )
    return


def test_template_to_dict_renders_all_fields():
    """
        The internal ``_template_to_dict`` helper must surface every
        documented response key.
    """
    from datetime import datetime, timezone

    class _FakeResponse:
        id = 7
        project_id = 3
        name = "ga"
        description = "desc"
        default_channel = "stable"
        version_pattern = "^v.*$"
        default_repo_ids = [1, 2]
        default_pipeline = {"stages": []}
        default_schedule = {"cron": "* * * * *"}
        created_at = datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc)
        updated_at = datetime(2026, 5, 23, 9, 30, tzinfo=timezone.utc)

    payload = routes_module._template_to_dict(_FakeResponse())

    assert payload["template_id"] == 7
    assert payload["project_id"] == 3
    assert payload["name"] == "ga"
    assert payload["default_repo_ids"] == [1, 2]
    assert payload["default_pipeline"] == {"stages": []}
    assert payload["default_schedule"] == {"cron": "* * * * *"}
    assert payload["created_at"].startswith("2026-05-23T09:00")
    return


# ---------------------------------------------------------------------------
# POST .../create-release (PRJ-09)
# ---------------------------------------------------------------------------


class _FakeRestRequest:
    """
        Just enough of a webworks request for the create-release
        handler: path params, a JSON body, and the session / actor the
        session middleware attaches.
    """

    def __init__(
            self, *, db_session: Any, path_params: Dict[str, str], body: Dict[str, Any]
        ) -> None:
        self.db_session = db_session
        self.path_params = path_params
        self.path = "/api/v1/projects/{project_id}/release-templates/{template_id}/create-release".format(
            **path_params
        )
        self.actor_user_id = "3f6c1a2e-4b5d-4e6f-8a9b-0c1d2e3f4a5b"
        self.auth_principal = object()
        self._body = body
        return

    def json(self) -> Dict[str, Any]:
        return self._body


def _project_with_template() -> Any:
    """
        An in-memory database with one project and one release template
        whose version pattern is ``^\\d+\\.\\d+\\.\\d+$``.

        :returns: Tuple of (session, project_id, template_id).
    """
    import uuid

    import sqlalchemy as sa

    from sqlalchemy.orm import sessionmaker

    from ccai.pychestrate.core.managers.release_template_manager import (
        ReleaseTemplateManager,
    )
    from ccai.pychestrate.core.orm import Project, PychestrateModelBase

    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    project = Project(name="alpha", owner_id=uuid.uuid4(), metadata_json={})
    session.add(project)
    session.commit()
    template = ReleaseTemplateManager(db_session=session).create(
        project.id, name="standard", default_channel="stable",
        version_pattern=r"^\d+\.\d+\.\d+$",
    )
    rtnval = (session, project.id, template.id)
    return rtnval


def _post_create_release(*, body: Dict[str, Any]) -> Any:
    """
        Call the create-release handler with permission checks stubbed
        out (they are covered by the route-permission suites).

        :returns: Tuple of (response, session).
    """
    from ccai.testbase.mocking import create_module_patch

    session, project_id, template_id = _project_with_template()
    patch = create_module_patch(routes_module, "_require_permission")
    patch.activate()
    try:
        response = routes_module.handle_create_release_from_template(
            _FakeRestRequest(
                db_session=session,
                path_params={"project_id": str(project_id), "template_id": str(template_id)},
                body=body,
            )
        )
    finally:
        patch.deactivate()
    rtnval = (response, session)
    return rtnval


def test_create_release_from_template_answers_201_with_the_release():
    """
    **Feature: projects release templates REST (PRJ-09)**
    **Property: POST .../create-release answers 201 with the new
    release (it used to commit the release and then fail with a 500
    because the response was built with ``body=`` instead of
    ``content=``).**
    """
    import json

    response, _session = _post_create_release(body={"version": "1.4.0"})

    payload = json.loads(response.body.decode("utf-8"))
    assert (response.status_code, payload["version"], payload["metadata"]["template_name"]) == (
        201, "1.4.0", "standard",
    )
    return


def test_create_release_from_template_rejects_a_version_outside_the_pattern():
    """
    **Feature: projects release templates REST (PRJ-09)**
    **Property: a semantic version that does not match the template's
    version pattern (a pre-release against ``x.y.z``) answers 400 and
    creates no release.**
    """
    from ccai.pychestrate.core.orm import ProjectRelease

    response, session = _post_create_release(body={"version": "1.4.0-rc1"})

    assert (response.status_code, session.query(ProjectRelease).count()) == (400, 0)
    return
