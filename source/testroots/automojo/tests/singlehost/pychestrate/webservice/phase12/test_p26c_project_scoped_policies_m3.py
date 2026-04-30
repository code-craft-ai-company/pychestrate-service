"""
.. module:: test_p26c_project_scoped_policies_m3
    :synopsis: Verify project-scoped policies accept project roles.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import tempfile

from typing import Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.webworks.authentication.core import (
    AuthenticationContext,
    Principal,
)
from automojo.webworks.routing.request import Request

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_app() -> Tuple[PychestrateApplication, str]:
    reset_phase1_runtime()
    fd, path = tempfile.mkstemp(prefix="pych_p26c_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
    )
    return app, path


def _principal_with(*, roles) -> AuthenticationContext:
    rtnval = AuthenticationContext(
        principal=Principal(
            identifier="00000000-0000-4000-8000-00000000c000",
            display_name="Test",
            roles=set(roles),
        ),
        scheme="test-injection",
    )
    return rtnval


def _wrap(*, app, context: Optional[AuthenticationContext]) -> None:
    original = app.dispatcher.dispatch

    def _wrapped(*, request):
        request.auth = context
        rtnval = original(request=request)
        return rtnval

    app.dispatcher.dispatch = _wrapped
    return


def test_project_owner_can_archive_project_without_system_admin():
    """
    **Feature: P26c project-scoped policies (M3)**
    **Property: A user with project-owner (and NOT system-admin)
    clears the gate on POST /api/v1/projects/{slug}/archive — the
    handler then runs and emits a 4xx for the missing project rather
    than 401/403 from the policy gate.**
    """
    app, path = _build_app()
    _wrap(app=app, context=_principal_with(roles={"project-owner"}))
    try:
        request = Request(
            method="POST",
            path="/api/v1/projects/some-slug/archive",
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code != 401, True)
        testbase.assert_equal(response.status_code != 403, True)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_project_editor_can_patch_project_without_system_admin():
    """
    **Feature: P26c project-scoped policies (M3)**
    **Property: A user with project-editor (no system-admin) clears
    the gate on PATCH /api/v1/projects/{slug} — that gate now uses
    _PROJECT_WRITE rather than _ADMIN_POLICY.**
    """
    app, path = _build_app()
    _wrap(app=app, context=_principal_with(roles={"project-editor"}))
    try:
        request = Request(
            method="PATCH",
            path="/api/v1/projects/some-slug",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"display_name": "New name"}).encode(),
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code != 401, True)
        testbase.assert_equal(response.status_code != 403, True)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_project_viewer_blocked_from_pod_definition_create():
    """
    **Feature: P26c project-scoped policies (M3)**
    **Property: project-viewer is read-only; POST pod-definitions
    rejects with 403 (the gate accepts owner/editor/admin only).**
    """
    app, path = _build_app()
    _wrap(app=app, context=_principal_with(roles={"project-viewer"}))
    try:
        request = Request(
            method="POST",
            path="/api/v1/projects/00000000-0000-4000-8000-0000000000aa/pod-definitions",
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 403)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_project_creation_still_requires_system_admin():
    """
    **Feature: P26c project-scoped policies (M3)**
    **Property: project-owner alone is NOT enough to create a new
    project (POST /api/v1/projects). That gate stays admin-only;
    once the project exists, project-scoped roles take over.**
    """
    app, path = _build_app()
    _wrap(app=app, context=_principal_with(roles={"project-owner"}))
    try:
        request = Request(
            method="POST",
            path="/api/v1/projects",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "slug": "denied-by-tier",
                "display_name": "Denied",
                "description": "",
            }).encode(),
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 403)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return
