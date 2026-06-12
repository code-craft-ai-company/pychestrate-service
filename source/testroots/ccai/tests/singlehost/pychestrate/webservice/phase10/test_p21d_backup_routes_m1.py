"""
.. module:: test_p21d_backup_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the backup / disaster-recovery REST endpoints (PR p21d).

.. moduleauthor:: Code Craft AI LLC

Covers the backup operations attached by
``register_backup_routes``:

* POST /api/v1/backups
* GET  /api/v1/backups
* GET  /api/v1/backups/{backup_id}
* POST /api/v1/backups/{backup_id}:restore

Auth (401/403), session boundary (503), record not-found (404),
malformed body (422), restore-stub (501), pagination, the
storage-backend factory, and the happy-path 2xx each get
explicit coverage.
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
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
    PROBLEM_TYPE_VALIDATION_FAILED,
)
from ccai.pychestrate.webservice.backup.factories.local_backend import (
    LocalFilesystemBackupBackend,
)
from ccai.pychestrate.webservice.backup.factories.storage_backend import (
    BackupArchiveWriteResult,
)
from ccai.pychestrate.webservice.backup.service import BackupRecordView
from ccai.pychestrate.webservice.backup.restapi.v1 import backup_routes


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
            raw_body: Optional[bytes] = None,
            db_session: Optional[Any] = None,
            auth_principal: Optional[Any] = None
        ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        if raw_body is not None:
            self.body: bytes = raw_body
        elif body is not None:
            self.body = json.dumps(body).encode("utf-8")
        else:
            self.body = b""
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
        backup_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _make_view(
        *,
        backup_id: str = "backup-1",
        status: str = "completed"
    ) -> BackupRecordView:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    rtnval = BackupRecordView(
        backup_id=backup_id,
        status=status,
        backend="local_filesystem",
        archive_uri="file:///tmp/pychestrate-backups/backup-1.backup.tar",
        archive_sha256="a" * 64,
        size_bytes=10240,
        manifest={
            "database": {"included": True, "table_count": 42},
            "object_store": {"included": True, "object_count": 0},
            "secrets": {"included": True, "entry_count": 0},
        },
        error_detail=None,
        note="",
        created_by="user-1",
        created_at=now,
        completed_at=now,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Storage-backend factory
# ---------------------------------------------------------------------------


def test_local_backend_round_trips_an_archive():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: LocalFilesystemBackupBackend writes an archive
    atomically and reports it through list_archives.**
    """
    import os
    import shutil
    import tempfile

    backup_root = tempfile.mkdtemp(prefix="p21d-backup-")
    os.environ["PYCHESTRATE_BACKUP_ROOT"] = backup_root
    try:
        result = LocalFilesystemBackupBackend.write_archive(
            backup_id="backup-xyz",
            archive_bytes=b"hello-backup",
        )
        testbase.assert_type(result, BackupArchiveWriteResult)
        testbase.assert_equal(result.size_bytes, len(b"hello-backup"))
        listed = LocalFilesystemBackupBackend.list_archives()
        testbase.assert_equal(len(listed), 1)
        testbase.assert_true(listed[0].endswith("backup-xyz.backup.tar"))
        testbase.assert_equal(
            LocalFilesystemBackupBackend.backend_kind(), "local_filesystem",
        )
    finally:
        del os.environ["PYCHESTRATE_BACKUP_ROOT"]
        shutil.rmtree(backup_root, ignore_errors=True)
    return


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_backup_routes_attaches_four_endpoints():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: register_backup_routes attaches the four
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    backup_routes.register_backup_routes(app=app, version_prefix="/api/v1")
    expected_pairs = (
        ("/api/v1/backups", ("GET",)),
        ("/api/v1/backups", ("POST",)),
        ("/api/v1/backups/{backup_id}", ("GET",)),
        ("/api/v1/backups/{backup_id}:restore", ("POST",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET list -- auth + session sweep
# ---------------------------------------------------------------------------


def test_list_returns_503_when_session_missing():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: GET backups returns 503 when no db_session is
    bound.**
    """
    request = _FakeRequest(path="/api/v1/backups", db_session=None)
    response = backup_routes.handle_list_backups(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_returns_401_when_no_principal():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: GET backups returns 401 when no AuthPrincipal is
    bound.**
    """
    request = _FakeRequest(
        path="/api/v1/backups",
        db_session=object(),
        auth_principal=None,
    )
    response = backup_routes.handle_list_backups(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_returns_403_when_permission_denied():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: GET backups returns 403 when the principal lacks
    system:backups.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/backups",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = backup_routes.handle_list_backups(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:backups.read",
    )
    return


def test_list_returns_400_on_bad_status_filter():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: GET backups returns 400 when the status query
    param is not a recognized enum value.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/backups",
            query={"status": "bogus"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = backup_routes.handle_list_backups(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    return


def test_list_returns_page_envelope_on_happy_path():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: GET backups returns an {items, meta} page with
    BackupRecord-shaped items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    list_patch = create_module_patch(
        backup_routes.backup_service, "list_backups",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: {"items": [_make_view()], "total": 1},
    )
    try:
        request = _FakeRequest(
            path="/api/v1/backups",
            query={"page": "1", "per_page": "10"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = backup_routes.handle_list_backups(request)
    finally:
        list_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["backup_id"], "backup-1")
    testbase.assert_equal(body["items"][0]["status"], "completed")
    testbase.assert_equal(body["meta"]["total"], 1)
    return


# ---------------------------------------------------------------------------
# POST create
# ---------------------------------------------------------------------------


def test_create_returns_201_on_happy_path():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: POST backups returns 201 with the completed
    backup record.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    trigger_patch = create_module_patch(
        backup_routes.backup_service, "trigger_backup",
    )
    trigger_mock = trigger_patch.activate()
    trigger_mock.configure(side_effect=lambda **kwargs: _make_view())
    try:
        request = _FakeRequest(
            path="/api/v1/backups",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"note": "manual backup"},
        )
        response = backup_routes.handle_create_backup(request)
    finally:
        trigger_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["backup_id"], "backup-1")
    testbase.assert_equal(body["status"], "completed")
    return


def test_create_returns_422_on_bad_flag_type():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: POST backups returns 422 when an include_* flag
    is not a boolean.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/backups",
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"include_database": "yes"},
        )
        response = backup_routes.handle_create_backup(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_create_returns_401_when_no_principal():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: POST backups returns 401 when the request is
    anonymous.**
    """
    request = _FakeRequest(
        path="/api/v1/backups",
        db_session=object(),
        auth_principal=None,
        body={},
    )
    response = backup_routes.handle_create_backup(request)
    testbase.assert_equal(response.status_code, 401)
    return


# ---------------------------------------------------------------------------
# GET read
# ---------------------------------------------------------------------------


def test_read_returns_404_when_unknown():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: GET backups/{backup_id} returns 404 when the
    record does not exist.**
    """
    from ccai.pychestrate.webservice.backup.errors import (
        BackupRecordNotFoundError,
    )

    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        backup_routes.backup_service, "get_backup",
    )
    get_mock = get_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise BackupRecordNotFoundError("Backup record not found: missing")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/backups/missing",
            path_params={"backup_id": "missing"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = backup_routes.handle_read_backup(request)
    finally:
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    return


def test_read_returns_200_on_happy_path():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: GET backups/{backup_id} returns 200 with the
    backup record and its manifest.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    get_patch = create_module_patch(
        backup_routes.backup_service, "get_backup",
    )
    get_mock = get_patch.activate()
    get_mock.configure(side_effect=lambda **kwargs: _make_view())
    try:
        request = _FakeRequest(
            path="/api/v1/backups/backup-1",
            path_params={"backup_id": "backup-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = backup_routes.handle_read_backup(request)
    finally:
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["backup_id"], "backup-1")
    testbase.assert_true("database" in body["manifest"])
    return


# ---------------------------------------------------------------------------
# POST restore -- documented 501 stub
# ---------------------------------------------------------------------------


def test_restore_returns_501_stub():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: POST backups/{backup_id}:restore returns 501 --
    the restore executor is a documented follow-on.**
    """
    from ccai.pychestrate.webservice.backup.errors import (
        BackupRestoreNotImplementedError,
    )

    perm_patch = _patch_check_permission(allowed=True)
    restore_patch = create_module_patch(
        backup_routes.backup_service, "request_restore",
    )
    restore_mock = restore_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise BackupRestoreNotImplementedError("not yet implemented")

    restore_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/backups/backup-1:restore",
            path_params={"backup_id": "backup-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={},
        )
        response = backup_routes.handle_restore_backup(request)
    finally:
        restore_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 501)
    return


def test_restore_returns_404_when_unknown():
    """
    **Feature: 10-backup-dr PR p21d**
    **Property: POST backups/{backup_id}:restore returns 404 when
    the target backup does not exist.**
    """
    from ccai.pychestrate.webservice.backup.errors import (
        BackupRecordNotFoundError,
    )

    perm_patch = _patch_check_permission(allowed=True)
    restore_patch = create_module_patch(
        backup_routes.backup_service, "request_restore",
    )
    restore_mock = restore_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise BackupRecordNotFoundError("Backup record not found: missing")

    restore_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/backups/missing:restore",
            path_params={"backup_id": "missing"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={},
        )
        response = backup_routes.handle_restore_backup(request)
    finally:
        restore_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return
