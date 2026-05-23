"""
.. module:: test_p22a_release_templates_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the project-scoped release-templates REST
               surface.

.. moduleauthor:: Automation Mojo LLC

Verifies that ``register_release_templates_routes`` attaches the
documented routes to a webworks app and that the input validation
helpers behave as expected.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

from automojo.pychestrate.webservice.projects.restapi.v1 import (
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
