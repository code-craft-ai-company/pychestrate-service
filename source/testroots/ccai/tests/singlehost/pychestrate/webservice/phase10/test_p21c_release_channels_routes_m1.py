"""
.. module:: test_p21c_release_channels_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the release-channel REST endpoints (PR p21c).

.. moduleauthor:: Code Craft AI LLC

Covers the release-channel operations attached by
``register_release_channels_routes``:

* GET  /api/v1/release-channels
* POST /api/v1/release-channels
* GET  /api/v1/release-channels/{channel_id}

Auth (401/403), session boundary (503), entry not-found (404),
malformed body (422), conflict (409), pagination, and happy-path
2xx each get explicit coverage.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
    PROBLEM_TYPE_VALIDATION_FAILED,
)
from ccai.pychestrate.webservice.ops.release import manifest_signer
from ccai.pychestrate.webservice.ops.release.errors import (
    ReleaseConflictError,
    ReleaseSigningKeyUnavailableError,
)
from ccai.pychestrate.webservice.ops.release.models import (
    ReleaseChannel,
    ReleaseComponent,
    ReleaseStatus,
)
from ccai.pychestrate.webservice.ops.release.release_service import (
    ReleaseRecord,
)
from ccai.pychestrate.webservice.ops.release.restapi.v1 import (
    release_channels_routes,
)
from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import (
    GROUP_ADMIN,
    NAV_ENTRIES,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeQueryParams:
    def __init__(self, *, values: Optional[Dict[str, str]] = None) -> None:
        self._values: Dict[str, str] = values if values is not None else {}
        return

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        rtnval = self._values.get(key, default)
        return rtnval


class _FakeRequest:
    def __init__(
            self,
            *,
            path: str,
            path_params: Optional[Dict[str, Any]] = None,
            query: Optional[Dict[str, str]] = None,
            body: Any = None,
            db_session: Optional[Any] = None,
            auth_principal: Optional[Any] = None
        ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        return

    def json(self) -> Any:
        rtnval = self._body
        return rtnval


class _FakeApp:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[str, ...], Callable]] = []
        return

    def attach_route(
            self, path: str, methods: Optional[List[str]] = None
        ) -> Callable:
        resolved_methods = tuple(methods if methods is not None else ["GET"])

        def decorator(func: Callable) -> Callable:
            self.calls.append((path, resolved_methods, func))
            rtnval = func
            return rtnval

        rtnval = decorator
        return rtnval


class _FakePrincipal:
    def __init__(self, *, user_id: str = "user-1") -> None:
        self.user_id: str = user_id
        return


class _FakeDecision:
    def __init__(self, *, allowed: bool, reason: str = "") -> None:
        self.allowed: bool = allowed
        self.reason: str = reason
        return


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        release_channels_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _make_release_record(
        *,
        release_id: str = "rel-1",
        version: str = "1.2.3"
    ) -> Any:
    now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
    rtnval = ReleaseRecord(
        release_id=release_id,
        component=ReleaseComponent.SERVICE,
        version=version,
        channel=ReleaseChannel.CANARY,
        artifact_uri="https://artifacts.example/svc-1.2.3.tar.gz",
        artifact_sha256="a" * 64,
        manifest_bytes=b"{}",
        signature=b"sig",
        issuer_key_id="key-1",
        issued_at=now,
        issued_by="user-1",
        status=ReleaseStatus.ACTIVE,
        rollout_fraction=0.05,
        stage_started_at=now,
        previous_release_id=None,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_release_channels_routes_attaches_three_endpoints():
    """
    **Feature: 10-release-channels PR p21c**
    **Property: register_release_channels_routes attaches the
    three method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    release_channels_routes.register_release_channels_routes(
        app=app, version_prefix="/api/v1",
    )
    expected_pairs = (
        ("/api/v1/release-channels", ("GET",)),
        ("/api/v1/release-channels", ("POST",)),
        ("/api/v1/release-channels/{channel_id}", ("GET",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET list -- auth + session sweep
# ---------------------------------------------------------------------------


def test_list_returns_503_when_session_missing():
    """
    **Feature: 10-release-channels PR p21c**
    **Property: GET release-channels returns 503 when no
    db_session is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/release-channels",
        db_session=None,
    )
    response = release_channels_routes.handle_list_release_channels(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_returns_401_when_no_principal():
    """
    **Feature: 10-release-channels PR p21c**
    **Property: GET release-channels returns 401 when no
    AuthPrincipal is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/release-channels",
        db_session=object(),
        auth_principal=None,
    )
    response = release_channels_routes.handle_list_release_channels(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_returns_403_when_permission_denied():
    """
    **Feature: 10-release-channels PR p21c**
    **Property: GET release-channels returns 403 when the
    principal lacks system:release_channels.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/release-channels",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = release_channels_routes.handle_list_release_channels(
            request,
        )
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:release_channels.read",
    )
    return


def test_list_returns_400_on_bad_channel_filter():
    """
    **Feature: 10-release-channels PR p21c**
    **Property: GET release-channels returns 400 when the channel
    query param is not a recognized enum value.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/release-channels",
            query={"channel": "bogus"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = release_channels_routes.handle_list_release_channels(
            request,
        )
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    return


def test_list_returns_page_envelope_on_happy_path():
    """
    **Feature: 10-release-channels PR p21c**
    **Property: GET release-channels returns an {items, meta} page
    with ReleaseChannelEntry-shaped items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    list_patch = create_module_patch(
        release_channels_routes.release_service, "list_releases",
    )
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: [_make_release_record()])
    try:
        request = _FakeRequest(
            path="/api/v1/release-channels",
            query={"page": "1", "per_page": "10"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = release_channels_routes.handle_list_release_channels(
            request,
        )
    finally:
        list_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["channel_id"], "rel-1")
    testbase.assert_equal(body["items"][0]["channel"], "canary")
    testbase.assert_equal(body["meta"]["total"], 1)
    return


# ---------------------------------------------------------------------------
# POST create
# ---------------------------------------------------------------------------


def test_create_returns_422_on_missing_body():
    """
    **Feature: 10-release-channels PR p21c**
    **Property: POST release-channels returns 422 when the body is
    missing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/release-channels",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body=None,
        )
        response = release_channels_routes.handle_create_release_channel(
            request,
        )
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_create_returns_422_on_bad_component():
    """
    **Feature: 10-release-channels PR p21c**
    **Property: POST release-channels returns 422 when the
    component value is not a recognized enum member.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/release-channels",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "component": "bogus",
                "version": "1.2.3",
                "channel": "canary",
                "artifact_uri": "https://x/a.tar.gz",
                "artifact_sha256": "a" * 64,
            },
        )
        response = release_channels_routes.handle_create_release_channel(
            request,
        )
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    return


def test_create_returns_409_on_release_conflict():
    """
    **Feature: 10-release-channels PR p21c**
    **Property: POST release-channels returns 409 when the release
    facade raises ReleaseConflictError.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    publish_patch = create_module_patch(
        release_channels_routes.release_service, "publish_release",
    )
    publish_mock = publish_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise ReleaseConflictError("triple exists")

    publish_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/release-channels",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "component": "service",
                "version": "1.2.3",
                "channel": "canary",
                "artifact_uri": "https://x/a.tar.gz",
                "artifact_sha256": "a" * 64,
            },
        )
        response = release_channels_routes.handle_create_release_channel(
            request,
        )
    finally:
        publish_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    return


def test_create_returns_201_on_happy_path():
    """
    **Feature: 10-release-channels PR p21c**
    **Property: POST release-channels returns 201 with the
    published release-channel entry.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    publish_patch = create_module_patch(
        release_channels_routes.release_service, "publish_release",
    )
    publish_mock = publish_patch.activate()
    publish_mock.configure(
        side_effect=lambda **kwargs: _make_release_record(),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/release-channels",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "component": "service",
                "version": "1.2.3",
                "channel": "canary",
                "artifact_uri": "https://x/a.tar.gz",
                "artifact_sha256": "a" * 64,
            },
        )
        response = release_channels_routes.handle_create_release_channel(
            request,
        )
    finally:
        publish_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["version"], "1.2.3")
    testbase.assert_equal(body["component"], "service")
    return


# ---------------------------------------------------------------------------
# GET read
# ---------------------------------------------------------------------------


def test_read_returns_404_when_entry_missing():
    """
    **Feature: 10-release-channels PR p21c**
    **Property: GET release-channel returns 404 when the release
    facade returns None.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        release_channels_routes.release_service, "get_release",
    )
    get_mock = get_patch.activate()
    get_mock.configure(side_effect=lambda **kwargs: None)
    try:
        request = _FakeRequest(
            path="/api/v1/release-channels/rel-x",
            path_params={"channel_id": "rel-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = release_channels_routes.handle_read_release_channel(
            request,
        )
    finally:
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    return


def test_read_returns_200_on_happy_path():
    """
    **Feature: 10-release-channels PR p21c**
    **Property: GET release-channel returns 200 with the release
    entry.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        release_channels_routes.release_service, "get_release",
    )
    get_mock = get_patch.activate()
    get_mock.configure(side_effect=lambda **kwargs: _make_release_record())
    try:
        request = _FakeRequest(
            path="/api/v1/release-channels/rel-1",
            path_params={"channel_id": "rel-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = release_channels_routes.handle_read_release_channel(
            request,
        )
    finally:
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["channel_id"], "rel-1")
    return


# ---------------------------------------------------------------------------
# Audit ORC-31 -- "Pychestrate Updates": say why publishing is unavailable
# ---------------------------------------------------------------------------


def _list_with_publishing_state() -> Any:
    """
        Run GET release-channels (empty ledger) and return the decoded
        body.
    """
    perm_patch = _patch_check_permission(allowed=True)
    list_patch = create_module_patch(
        release_channels_routes.release_service, "list_releases",
    )
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: [])
    try:
        request = _FakeRequest(
            path="/api/v1/release-channels",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = release_channels_routes.handle_list_release_channels(request)
    finally:
        list_patch.deactivate()
        perm_patch.deactivate()
    rtnval = _decode_body(response)
    return rtnval


def test_list_meta_says_publishing_is_unavailable_without_a_signing_key():
    """
    **Feature: Pychestrate Updates -- audit ORC-31**
    **Property: with no release-signing key installed the list meta
    says publishing is unavailable and why, so the page can explain it
    instead of letting a publish end in a bare HTTP 503.**
    """
    manifest_signer.reset_for_testing()
    body = _list_with_publishing_state()
    testbase.assert_equal(
        (body["meta"]["publishing_available"], body["meta"]["publishing_unavailable_reason"]),
        (False, release_channels_routes.PUBLISHING_UNAVAILABLE_REASON),
    )
    return


def test_list_meta_says_publishing_is_available_with_a_signing_key():
    """
    **Feature: Pychestrate Updates -- audit ORC-31**
    **Property: once a release-signing key is installed the list meta
    says publishing is available.**
    """
    manifest_signer.set_active_signing_key(
        key=manifest_signer.generate_signing_key(issuer_key_id="orc31-test"),
    )
    try:
        body = _list_with_publishing_state()
    finally:
        manifest_signer.reset_for_testing()
    testbase.assert_equal(
        (body["meta"]["publishing_available"], body["meta"]["publishing_unavailable_reason"]),
        (True, None),
    )
    return


def test_create_without_a_signing_key_explains_the_missing_key():
    """
    **Feature: Pychestrate Updates -- audit ORC-31**
    **Property: a publish refused for the missing signing key answers
    503 with a detail that explains it and reason
    signing_key_missing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    publish_patch = create_module_patch(
        release_channels_routes.release_service, "publish_release",
    )
    publish_mock = publish_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise ReleaseSigningKeyUnavailableError("No active release signing key has been installed.")

    publish_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/release-channels",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "component": "service",
                "version": "1.2.3",
                "channel": "canary",
                "artifact_uri": "https://x/a.tar.gz",
                "artifact_sha256": "a" * 64,
            },
        )
        response = release_channels_routes.handle_create_release_channel(request)
    finally:
        publish_patch.deactivate()
        perm_patch.deactivate()
    body = _decode_body(response)
    testbase.assert_equal(
        (response.status_code, body["detail"], body["reason"]),
        (503, release_channels_routes.PUBLISHING_UNAVAILABLE_REASON, "signing_key_missing"),
    )
    return


def _updates_entry() -> Any:
    matches = [entry for entry in NAV_ENTRIES if entry.route == "/release-channels"]
    rtnval = matches[0]
    return rtnval


def test_updates_entry_is_named_for_what_it_is():
    """
    **Feature: Pychestrate Updates -- audit ORC-31**
    **Property: the sidebar entry for /release-channels reads
    "Pychestrate Updates", so it no longer collides with a project's
    release channels.**
    """
    testbase.assert_equal(_updates_entry().label, "Pychestrate Updates")
    return


def test_updates_entry_sits_under_admin():
    """
    **Feature: Pychestrate Updates -- audit ORC-31**
    **Property: the entry lives in the Admin group, not Operations.**
    """
    testbase.assert_equal(_updates_entry().group_id, GROUP_ADMIN)
    return


def test_updates_entry_is_not_a_build_surface():
    """
    **Feature: Pychestrate Updates -- audit ORC-31**
    **Property: the entry carries no UI-profile surface tag, so turning
    Build Automation off does not hide Pychestrate's own updates.**
    """
    testbase.assert_equal(_updates_entry().surfaces, ())
    return
