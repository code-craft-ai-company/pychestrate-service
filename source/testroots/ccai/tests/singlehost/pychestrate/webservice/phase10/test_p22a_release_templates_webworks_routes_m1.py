"""
.. module:: test_p22a_release_templates_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the project-scoped release-templates
               webworks consumer UI routes.

.. moduleauthor:: Code Craft AI LLC

Verifies that ``register_release_templates_routes`` (the UI
variant under
:mod:`webinterface.blueprints.projects.routes_release_templates`)
attaches the documented routes and that the local CSV / JSON form
parsers behave as expected.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, List, Optional

from ccai.pychestrate.webservice.webinterface.blueprints.projects import (
    routes_release_templates as ui_routes_module,
)


class _FakeApp:
    """
        Minimal webworks app stub.
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


def test_register_release_templates_ui_attaches_documented_routes():
    """
        Every documented webworks UI route + methods tuple must be
        attached.
    """
    app = _FakeApp()
    ui_routes_module.register_release_templates_routes(app=app)

    actual = {(path, methods) for path, methods, _ in app.calls}

    base = "/projects/{project_id}/release-templates"
    expected = {
        (base, ("GET",)),
        (base + "/create", ("GET", "POST")),
        (base + "/{template_id}", ("GET",)),
        (base + "/{template_id}/edit", ("GET", "POST")),
        (base + "/{template_id}/delete", ("POST",)),
    }
    assert expected.issubset(actual)
    return


def test_parse_repo_id_csv_handles_normal_input():
    """
        Comma-separated integer lists must parse cleanly.
    """
    assert ui_routes_module._parse_repo_id_csv(raw="1, 2, 3") == [1, 2, 3]
    assert ui_routes_module._parse_repo_id_csv(raw="") == []
    assert ui_routes_module._parse_repo_id_csv(raw=None) == []
    return


def test_parse_repo_id_csv_raises_on_non_integer():
    """
        Non-integer tokens must raise ``ValueError``.
    """
    raised = False
    try:
        ui_routes_module._parse_repo_id_csv(raw="1, abc")
    except ValueError:
        raised = True

    assert raised is True
    return


def test_parse_json_object_or_none_returns_none_for_blank():
    """
        Blank / whitespace-only input must yield ``None``.
    """
    result = ui_routes_module._parse_json_object_or_none(
        raw="", field_label="default_pipeline"
    )
    assert result is None

    result2 = ui_routes_module._parse_json_object_or_none(
        raw="   ", field_label="default_pipeline"
    )
    assert result2 is None
    return


def test_parse_json_object_or_none_rejects_non_object():
    """
        Non-object JSON must raise ``ValueError``.
    """
    raised = False
    try:
        ui_routes_module._parse_json_object_or_none(
            raw="[1, 2, 3]", field_label="default_pipeline"
        )
    except ValueError:
        raised = True

    assert raised is True
    return


def test_parse_json_object_or_none_accepts_valid_object():
    """
        Valid JSON-object input must be returned as a dict.
    """
    result = ui_routes_module._parse_json_object_or_none(
        raw='{"stages": []}', field_label="default_pipeline"
    )
    assert result == {"stages": []}
    return
