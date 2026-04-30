"""
.. module:: test_p24c_identity_rbacblueprints_webworks_m3
    :synopsis: Tests for P24c — identity + RBAC controllers on webworks.

Exercises the migrated identity (users + flags) and security/RBAC
controllers end-to-end through the webworks dispatcher and the
:class:`DbSessionMiddleware`. Each controller covers the most common
shapes (happy path, 503 missing middleware, 404 / 400 / 409 error
responses, query-param routing).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Dict, Tuple

from automojo import testbase

from automojo.webworks.devexp.testing.testclient import TestClient
from automojo.webworks.routing.dispatcher import Dispatcher
from automojo.webworks.routing.middleware import MiddlewarePipeline
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.router import Router

from automojo.pychestrate.webservice.identity.flags import flag_service
from automojo.pychestrate.webservice.identity.flags.models import FlagKind
from automojo.pychestrate.webservice.identity.flags.restapi.v1 import (
    flagsblueprint,
)
from automojo.pychestrate.webservice.identity.users import user_service
from automojo.pychestrate.webservice.identity.users.restapi.v1 import (
    identityusersblueprint,
)
from automojo.pychestrate.webservice.dbsessionmiddleware import (
    DbSessionMiddleware,
)
from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.security.rbac import binding_service
from automojo.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    PrincipalKind,
    RbacRole,
    RoleSource,
)
from automojo.pychestrate.webservice.security.rbac.restapi.v1 import (
    rbacblueprint,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


_ACTOR_UUID = "00000000-0000-4000-8000-000000400001"


def _build_app_callable(
        *,
        engine,
        blueprint_cls,
        install_db_session_middleware: bool = True,
    ):
    """
        Build a ``(method, path, headers, body) -> (status, headers,
        body)`` callable that dispatches into a webworks pipeline
        wired with the supplied blueprint.

        :param engine: SQLAlchemy engine to bind the session factory
                       against.
        :param blueprint_cls: A :class:`RestBlueprint` subclass to
                              register on the router.
        :param install_db_session_middleware: When True (default) the
                       db-session middleware is installed.

        :returns: An app callable suitable for :class:`TestClient`.
    """
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=engine)

    router = Router()
    blueprint_cls.register(router=router)

    pipeline = MiddlewarePipeline()
    if install_db_session_middleware is True:
        middleware = DbSessionMiddleware(session_factory=session_factory)
        pipeline.add(middleware=middleware, name=middleware.name)

    dispatcher = Dispatcher(router=router, pipeline=pipeline)

    def _app_callable(
            method: str,
            path: str,
            headers: Dict[str, str],
            body: bytes,
        ) -> Tuple[int, Dict[str, str], bytes]:
        if "?" in path:
            path_only, _, query_string_str = path.partition("?")
        else:
            path_only = path
            query_string_str = ""
        request = Request(
            method=method,
            path=path_only,
            query_string=query_string_str.encode("utf-8"),
            headers=headers,
            body=body,
        )
        response = dispatcher.dispatch(request=request)
        rtnval = (response.status_code, dict(response.headers), response.body)
        return rtnval

    return _app_callable


def _setup_users():
    reset_phase1_runtime()
    user_service.reset_for_testing()
    engine, session = build_in_memory_session()
    return engine, session


def _setup_flags():
    reset_phase1_runtime()
    engine, session = build_in_memory_session()
    return engine, session


def _setup_rbac():
    reset_phase1_runtime()
    engine, session = build_in_memory_session()
    return engine, session


# =====================================
# identityusersblueprint
# =====================================

def test_identityusersblueprint_create_then_read_round_trips_through_webworks():
    """
    **Feature: P24c identityusersblueprint migration (M3)**
    **Property: POST /api/v1/identity/users persists a new user
    record and the follow-up GET /api/v1/identity/users/{user_id}
    returns it. Both legs run through DbSessionMiddleware.**
    """
    engine, session = _setup_users()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=identityusersblueprint.IdentityUsersBlueprint,
        )
        client = TestClient(app=app_callable)

        create_response = client.post(
            path="/api/v1/identity/users",
            json={
                "login_name": "alice",
                "primary_email": "alice@example.com",
                "display_name": "Alice",
                "timezone": "UTC",
            },
        )

        testbase.assert_equal(create_response.status_code, 201)
        created = json.loads(create_response.body.decode("utf-8"))
        new_user_id = created["user_id"]
        testbase.assert_equal(created["login_name"], "alice")
        testbase.assert_equal(created["primary_email"], "alice@example.com")

        read_response = client.get(
            path="/api/v1/identity/users/{}".format(new_user_id),
        )
        testbase.assert_equal(read_response.status_code, 200)
        fetched = json.loads(read_response.body.decode("utf-8"))
        testbase.assert_equal(fetched["user_id"], new_user_id)
        testbase.assert_equal(fetched["display_name"], "Alice")
    finally:
        session.close()
    return


def test_identityusersblueprint_returns_409_on_duplicate_login_name():
    """
    **Feature: P24c identityusersblueprint migration (M3)**
    **Property: A second create with the same login_name surfaces
    UserAlreadyExistsError as HTTP 409 with detail body.**
    """
    engine, session = _setup_users()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=identityusersblueprint.IdentityUsersBlueprint,
        )
        client = TestClient(app=app_callable)

        first = client.post(
            path="/api/v1/identity/users",
            json={
                "login_name": "bob",
                "primary_email": "bob@example.com",
                "display_name": "Bob",
                "timezone": "UTC",
            },
        )
        testbase.assert_equal(first.status_code, 201)

        second = client.post(
            path="/api/v1/identity/users",
            json={
                "login_name": "bob",
                "primary_email": "bob2@example.com",
                "display_name": "Bob 2",
                "timezone": "UTC",
            },
        )
        testbase.assert_equal(second.status_code, 409)
    finally:
        session.close()
    return


def test_identityusersblueprint_returns_404_for_missing_user_id():
    """
    **Feature: P24c identityusersblueprint migration (M3)**
    **Property: GET /api/v1/identity/users/{unknown} surfaces
    UserNotFoundError as HTTP 404.**
    """
    engine, session = _setup_users()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=identityusersblueprint.IdentityUsersBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.get(
            path="/api/v1/identity/users/00000000-0000-4000-8000-000000000099",
        )
        testbase.assert_equal(response.status_code, 404)
    finally:
        session.close()
    return


def test_identityusersblueprint_returns_503_when_db_session_middleware_absent():
    """
    **Feature: P24c identityusersblueprint migration (M3)**
    **Property: With DbSessionMiddleware not installed, a create
    returns 503 surfacing the misconfiguration.**
    """
    engine, session = _setup_users()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=identityusersblueprint.IdentityUsersBlueprint,
            install_db_session_middleware=False,
        )
        client = TestClient(app=app_callable)

        response = client.post(
            path="/api/v1/identity/users",
            json={
                "login_name": "x",
                "primary_email": "x@example.com",
                "display_name": "X",
                "timezone": "UTC",
            },
        )
        testbase.assert_equal(response.status_code, 503)
    finally:
        session.close()
    return


# =====================================
# flagsblueprint
# =====================================

def test_flagsblueprint_create_returns_201_with_flag_view():
    """
    **Feature: P24c flagsblueprint migration (M3)**
    **Property: POST /api/v1/flags creates a BOOLEAN flag and
    returns the rendered view at status 201.**
    """
    engine, session = _setup_flags()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=flagsblueprint.FlagsBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.post(
            path="/api/v1/flags",
            json={
                "flag_key": "feature.x",
                "flag_kind": "BOOLEAN",
                "default_value": False,
            },
        )

        testbase.assert_equal(response.status_code, 201)
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal(body["flag_key"], "feature.x")
        testbase.assert_equal(body["flag_kind"], "BOOLEAN")
    finally:
        session.close()
    return


def test_flagsblueprint_read_returns_404_for_unknown_key():
    """
    **Feature: P24c flagsblueprint migration (M3)**
    **Property: GET /api/v1/flags/{unknown} returns 404 with the
    flag-not-found detail.**
    """
    engine, session = _setup_flags()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=flagsblueprint.FlagsBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.get(path="/api/v1/flags/never.was")
        testbase.assert_equal(response.status_code, 404)
    finally:
        session.close()
    return


def test_flagsblueprint_create_returns_400_for_unknown_flag_kind():
    """
    **Feature: P24c flagsblueprint migration (M3)**
    **Property: An unknown flag_kind value surfaces SemanticError
    as HTTP 400 (preserved through the migration).**
    """
    engine, session = _setup_flags()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=flagsblueprint.FlagsBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.post(
            path="/api/v1/flags",
            json={
                "flag_key": "feature.bad",
                "flag_kind": "NOT_A_KIND",
                "default_value": False,
            },
        )
        testbase.assert_equal(response.status_code, 400)
    finally:
        session.close()
    return


# =====================================
# rbacblueprint
# =====================================

def test_rbacblueprint_lists_permissions_from_registry():
    """
    **Feature: P24c rbacblueprint migration (M3)**
    **Property: GET /api/v1/rbac/permissions returns the registry
    permission catalog as a JSON array. The endpoint does not
    require DbSessionMiddleware.**
    """
    engine, session = _setup_rbac()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=rbacblueprint.RbacBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.get(path="/api/v1/rbac/permissions")
        testbase.assert_equal(response.status_code, 200)
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal(isinstance(body, list), True)
        testbase.assert_equal(len(body) > 0, True)
        first = body[0]
        testbase.assert_equal("permission_key" in first, True)
        testbase.assert_equal("description" in first, True)
        testbase.assert_equal("namespace" in first, True)
    finally:
        session.close()
    return


def test_rbacblueprint_lists_roles_with_permission_counts():
    """
    **Feature: P24c rbacblueprint migration (M3)**
    **Property: GET /api/v1/rbac/roles returns each registered
    role with its grant count.**
    """
    engine, session = _setup_rbac()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=rbacblueprint.RbacBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.get(path="/api/v1/rbac/roles")
        testbase.assert_equal(response.status_code, 200)
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal(isinstance(body, list), True)
        testbase.assert_equal(len(body) > 0, True)
        first = body[0]
        testbase.assert_equal("role_name" in first, True)
        testbase.assert_equal("permission_count" in first, True)
    finally:
        session.close()
    return


def test_rbacblueprint_check_returns_decision_with_reason():
    """
    **Feature: P24c rbacblueprint migration (M3)**
    **Property: POST /api/v1/rbac/check evaluates the requested
    permission and returns allowed/reason/permission_key fields.
    For an unbound principal the decision is deny.**
    """
    engine, session = _setup_rbac()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=rbacblueprint.RbacBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.post(
            path="/api/v1/rbac/check",
            json={
                "principal_id": _ACTOR_UUID,
                "permission_key": "system:audit.read",
            },
        )
        testbase.assert_equal(response.status_code, 200)
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal("allowed" in body, True)
        testbase.assert_equal("reason" in body, True)
        testbase.assert_equal(
            body["permission_key"], "system:audit.read",
        )
    finally:
        session.close()
    return


def test_rbacblueprint_list_bindings_filters_by_query_param():
    """
    **Feature: P24c rbacblueprint migration (M3)**
    **Property: GET /api/v1/rbac/bindings?principal_id=... reads
    the query parameter via request.query_params and applies it to
    the binding_service filter.**
    """
    engine, session = _setup_rbac()
    try:
        # Persist the role row so binding_service.assign_role can resolve it.
        role = RbacRole(
            role_id=new_uuid(),
            role_name="system-admin",
            source=RoleSource.BUILTIN,
            source_name="phase1",
            description="",
        )
        session.add(role)
        session.commit()

        # Seed two bindings, one for each of two different principals.
        principal_a = "00000000-0000-4000-8000-000000000aaa"
        principal_b = "00000000-0000-4000-8000-000000000bbb"
        binding_service.assign_role(
            db_session=session,
            role_name="system-admin",
            principal_kind=PrincipalKind.USER,
            principal_id=principal_a,
            scope_kind=BindingScope.SYSTEM,
            scope_id=None,
            inherits_into_project=False,
            actor_user_id=_ACTOR_UUID,
        )
        binding_service.assign_role(
            db_session=session,
            role_name="system-admin",
            principal_kind=PrincipalKind.USER,
            principal_id=principal_b,
            scope_kind=BindingScope.SYSTEM,
            scope_id=None,
            inherits_into_project=False,
            actor_user_id=_ACTOR_UUID,
        )
        session.commit()

        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=rbacblueprint.RbacBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.get(
            path="/api/v1/rbac/bindings",
            params={"principal_id": principal_a},
        )
        testbase.assert_equal(response.status_code, 200)
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal(isinstance(body, list), True)
        for view in body:
            testbase.assert_equal(view["principal_id"], principal_a)
        testbase.assert_equal(len(body) >= 1, True)
    finally:
        session.close()
    return
