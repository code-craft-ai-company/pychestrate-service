"""
.. module:: test_p19d_test_catalog_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the test-catalog REST endpoints (PR p19d).

.. moduleauthor:: Code Craft AI LLC

Covers the three planned ``test_catalog`` operations attached by
``register_test_catalog_routes``:

* GET  /api/v1/projects/{project_id}/test-catalog
* POST /api/v1/projects/{project_id}/test-catalog
* POST /api/v1/projects/{project_id}/test-catalog:import

Auth (401/403), session boundary (503), project not-found (404),
malformed body (422), and happy-path 200/202 each get explicit
coverage.
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
from ccai.pychestrate.webservice.orchestration.test.catalog.factories.testbase_project import (
    TestbaseProjectImporter,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.models import (
    TestCatalogEntry,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.payloads import (
    TestCatalogEntryView,
)
from ccai.pychestrate.webservice.orchestration.test.restapi.v1 import (
    test_catalog_routes,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
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
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
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


class _FakeProject:
    def __init__(self, *, project_id: str, slug: str = "proj-slug") -> None:
        self.project_id: str = project_id
        self.slug: str = slug
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(test_catalog_routes.rbac_evaluator, "check_permission")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(test_catalog_routes.projects_repo, "get_project_by_id")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


def _make_view(*, entry_id: str = "ent-1", project_id: str = "proj-1") -> TestCatalogEntryView:
    rtnval = TestCatalogEntryView(
        entry_id=entry_id,
        project_id=project_id,
        importer_tag="testbase-project",
        entry_key="tests.thing.test_x",
        display_name="Thing X",
        description="A thing",
        required_capability_tags=("linux",),
        param_schema={"includes": {"type": "array"}},
        raw_metadata={"runner_kind": "testbase"},
        canonical_digest="deadbeef",
        retired=False,
        created_at=datetime(2026, 5, 10, 9, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc),
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_test_catalog_routes_attaches_three_endpoints():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: register_test_catalog_routes attaches the three
    planned method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    test_catalog_routes.register_test_catalog_routes(app=app, version_prefix="/api/v1")
    expected_pairs = (
        ("/api/v1/projects/{project_id}/test-catalog", ("GET",)),
        ("/api/v1/projects/{project_id}/test-catalog", ("POST",)),
        ("/api/v1/projects/{project_id}/test-catalog:import", ("POST",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET /test-catalog -- auth + session sweep
# ---------------------------------------------------------------------------


def test_list_returns_503_when_session_missing():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: GET test-catalog returns 503 when no db_session is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/test-catalog",
        path_params={"project_id": "proj-1"},
        db_session=None,
    )
    response = test_catalog_routes.handle_list_test_catalog(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_returns_401_when_no_principal():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: GET test-catalog returns 401 when no AuthPrincipal is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/test-catalog",
        path_params={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = test_catalog_routes.handle_list_test_catalog(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_returns_403_when_permission_denied():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: GET test-catalog returns 403 when the principal does
    not hold system:test_catalog.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-catalog",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = test_catalog_routes.handle_list_test_catalog(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:test_catalog.read")
    return


def test_list_returns_404_when_project_missing():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: GET test-catalog returns 404 when the project does
    not exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/test-catalog",
            path_params={"project_id": "proj-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = test_catalog_routes.handle_list_test_catalog(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["project_id"], "proj-x")
    return


def test_list_returns_page_envelope_on_happy_path():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: GET test-catalog returns a {items, meta} page with
    TestCatalogEntry-shaped items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    list_patch = create_module_patch(test_catalog_routes.catalog, "list_entries")
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: [_make_view(entry_id="ent-1")])
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-catalog",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"page": "1", "per_page": "10"},
        )
        response = test_catalog_routes.handle_list_test_catalog(request)
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["entry_id"], "ent-1")
    testbase.assert_equal(body["items"][0]["importer_tag"], "testbase-project")
    testbase.assert_equal(
        body["items"][0]["required_capability_tags"], ["linux"],
    )
    testbase.assert_equal(
        body["items"][0]["created_at"], "2026-05-10T09:00:00+00:00",
    )
    testbase.assert_equal(
        body["items"][0]["updated_at"], "2026-05-17T12:00:00+00:00",
    )
    testbase.assert_equal(body["meta"]["page"], 1)
    testbase.assert_equal(body["meta"]["per_page"], 10)
    testbase.assert_equal(body["meta"]["total"], 1)
    return


# ---------------------------------------------------------------------------
# POST /test-catalog (upsert)
# ---------------------------------------------------------------------------


def test_upsert_returns_422_on_missing_body():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-catalog returns 422 problem when body is
    missing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-catalog",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body=None,
        )
        response = test_catalog_routes.handle_upsert_test_catalog(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_upsert_returns_422_on_missing_required_fields():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-catalog returns 422 listing the missing
    required fields when entry_key / display_name are absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-catalog",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"importer_tag": "testbase-project"},
        )
        response = test_catalog_routes.handle_upsert_test_catalog(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal("entry_key" in body["missing_fields"], True)
    testbase.assert_equal("display_name" in body["missing_fields"], True)
    return


def test_upsert_returns_200_on_happy_path():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-catalog returns 200 with the upserted
    TestCatalogEntry shape on a valid body.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    upsert_patch = create_module_patch(test_catalog_routes.catalog, "upsert_entry")
    upsert_mock = upsert_patch.activate()
    upsert_mock.configure(side_effect=lambda **kwargs: _make_view(entry_id="ent-9"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-catalog",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "importer_tag": "testbase-project",
                "entry_key": "tests.thing.test_x",
                "display_name": "Thing X",
                "description": "A thing",
                "required_capability_tags": ["linux"],
                "param_schema": {"includes": {"type": "array"}},
                "raw_metadata": {"runner_kind": "testbase"},
            },
        )
        response = test_catalog_routes.handle_upsert_test_catalog(request)
    finally:
        upsert_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["entry_id"], "ent-9")
    testbase.assert_equal(body["importer_tag"], "testbase-project")
    return


def test_upsert_returns_403_when_permission_denied():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-catalog returns 403 when the principal
    does not hold system:test_catalog.write.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-catalog",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "importer_tag": "testbase-project",
                "entry_key": "k",
                "display_name": "n",
            },
        )
        response = test_catalog_routes.handle_upsert_test_catalog(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:test_catalog.write")
    return


# ---------------------------------------------------------------------------
# POST /test-catalog:import
# ---------------------------------------------------------------------------


def test_import_returns_404_when_importer_tag_unknown():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-catalog:import returns 404 when no
    importer factory matches the supplied importer_tag.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    list_patch = create_module_patch(test_catalog_routes, "list_factory_implementations")
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: tuple())
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-catalog:import",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"importer_tag": "unknown-importer", "source": {}},
        )
        response = test_catalog_routes.handle_import_test_catalog(request)
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["importer_tag"], "unknown-importer")
    return


class _StubImporter:
    @classmethod
    def importer_tag(cls) -> str:
        return "testbase-project"

    @classmethod
    def import_entries(cls, *, project_id: str, source: Dict[str, Any]):
        from ccai.pychestrate.webservice.orchestration.test.catalog.payloads import (
            ImporterEntryPayload,
        )
        rtnval = [
            ImporterEntryPayload(
                entry_key="tests.thing.test_x",
                display_name="Thing X",
                description="",
                required_capability_tags=("linux",),
                param_schema={},
                raw_metadata={"runner_kind": "testbase"},
            ),
        ]
        return rtnval


def test_import_returns_202_with_summary_on_happy_path():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-catalog:import returns 202 with
    TestCatalogImportSummary-shaped body when the importer runs.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    list_patch = create_module_patch(test_catalog_routes, "list_factory_implementations")
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: (_StubImporter,))
    upsert_patch = create_module_patch(test_catalog_routes.catalog, "upsert_entry")
    upsert_mock = upsert_patch.activate()
    upsert_mock.configure(side_effect=lambda **kwargs: _make_view(entry_id="ent-imp-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-catalog:import",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"importer_tag": "testbase-project", "source": {}},
        )
        response = test_catalog_routes.handle_import_test_catalog(request)
    finally:
        upsert_patch.deactivate()
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["importer_tag"], "testbase-project")
    testbase.assert_equal(body["entries_imported"], 1)
    testbase.assert_equal(body["errors"], [])
    return


def test_import_returns_422_when_importer_tag_missing():
    """
    **Feature: 6-test-orchestration PR p19d**
    **Property: POST test-catalog:import returns 422 when
    importer_tag is missing from the body.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/test-catalog:import",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"source": {}},
        )
        response = test_catalog_routes.handle_import_test_catalog(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal("importer_tag" in body["missing_fields"], True)
    return


# ---------------------------------------------------------------------------
# Audit ORC-06 -- the testbase importer imports what it is given, and an
# import that finds nothing is refused instead of reported as complete.
# ---------------------------------------------------------------------------


IMPORT_PROJECT_UUID: str = "00000000-0000-4000-8000-0000000c0601"

INCLUDE_A: str = "ccai.tests.singlehost.feature.test_alpha"
INCLUDE_B: str = "ccai.tests.singlehost.feature.test_beta@#test_one"


def _raises_value_error(*, source: Dict[str, Any]) -> bool:
    raised = False
    try:
        TestbaseProjectImporter.import_entries(
            project_id=IMPORT_PROJECT_UUID, source=source,
        )
    except ValueError:
        raised = True
    return raised


def test_testbase_importer_creates_one_entry_per_include():
    """
    **Feature: 6-test-catalog (audit ORC-06)**
    **Property: the testbase importer turns each pasted include into a
    catalog entry keyed by the include.**
    """
    payloads = TestbaseProjectImporter.import_entries(
        project_id=IMPORT_PROJECT_UUID,
        source={"includes": [INCLUDE_A, INCLUDE_B]},
    )
    keys = [payload.entry_key for payload in payloads]
    testbase.assert_equal(keys, [INCLUDE_A, INCLUDE_B])
    return


def test_testbase_importer_records_the_run_metadata():
    """
    **Feature: 6-test-catalog (audit ORC-06)**
    **Property: an imported include carries the testbase runner kind,
    its include, the testbase root, and the branch in raw_metadata.**
    """
    payloads = TestbaseProjectImporter.import_entries(
        project_id=IMPORT_PROJECT_UUID,
        source={
            "includes": [INCLUDE_A],
            "root": "source/testroots/ccai",
            "ref": "main",
        },
    )
    testbase.assert_equal(
        payloads[0].raw_metadata,
        {
            "runner_kind": "testbase",
            "includes": [INCLUDE_A],
            "root": "source/testroots/ccai",
            "branch": "main",
        },
    )
    return


def test_testbase_importer_applies_capability_tags_to_every_include():
    """
    **Feature: 6-test-catalog (audit ORC-06)**
    **Property: required_capability_tags supplied with the includes are
    set on every imported entry.**
    """
    payloads = TestbaseProjectImporter.import_entries(
        project_id=IMPORT_PROJECT_UUID,
        source={
            "includes": [INCLUDE_A, INCLUDE_B],
            "required_capability_tags": ["linux"],
        },
    )
    tags = [payload.required_capability_tags for payload in payloads]
    testbase.assert_equal(tags, [("linux",), ("linux",)])
    return


def test_testbase_importer_refuses_a_source_with_only_root_and_ref():
    """
    **Feature: 6-test-catalog (audit ORC-06)**
    **Property: the source the old import form sent (root + ref, no
    tests) is refused rather than importing nothing.**
    """
    testbase.assert_equal(
        _raises_value_error(source={"root": "source/testroots/ccai", "ref": "main"}),
        True,
    )
    return


def test_testbase_importer_refuses_an_empty_source():
    """
    **Feature: 6-test-catalog (audit ORC-06)**
    **Property: an empty source is refused.**
    """
    testbase.assert_equal(_raises_value_error(source={}), True)
    return


def test_testbase_importer_refuses_a_malformed_include():
    """
    **Feature: 6-test-catalog (audit ORC-06)**
    **Property: an include that is not a testbase include expression
    refuses the whole import.**
    """
    testbase.assert_equal(
        _raises_value_error(source={"includes": [INCLUDE_A, "not a module path"]}),
        True,
    )
    return


def test_testbase_importer_refuses_an_entry_without_a_key():
    """
    **Feature: 6-test-catalog (audit ORC-06)**
    **Property: an entry without entry_key refuses the import instead of
    being skipped silently.**
    """
    testbase.assert_equal(
        _raises_value_error(source={"entries": [{"display_name": "no key"}]}),
        True,
    )
    return


def _import_request(*, session: Any, source: Dict[str, Any]) -> Any:
    request = _FakeRequest(
        path="/api/v1/projects/{}/test-catalog:import".format(IMPORT_PROJECT_UUID),
        path_params={"project_id": IMPORT_PROJECT_UUID},
        db_session=session,
        auth_principal=_FakePrincipal(),
        body={"importer_tag": "testbase-project", "source": source},
    )
    return request


def _run_import_route(*, session: Any, source: Dict[str, Any], importer: Any) -> Any:
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id=IMPORT_PROJECT_UUID))
    list_patch = create_module_patch(test_catalog_routes, "list_factory_implementations")
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: (importer,))
    try:
        response = test_catalog_routes.handle_import_test_catalog(
            _import_request(session=session, source=source),
        )
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    return response


def test_import_route_refuses_a_source_that_lists_no_tests():
    """
    **Feature: 6-test-catalog (audit ORC-06)**
    **Property: POST test-catalog:import answers 422 with
    entries_imported 0 when the source lists no tests.**
    """
    _engine, session = build_in_memory_session()
    try:
        response = _run_import_route(
            session=session,
            source={"root": "source/testroots/ccai", "ref": "main"},
            importer=TestbaseProjectImporter,
        )
    finally:
        session.close()
    body = _decode_body(response)
    testbase.assert_equal(
        (response.status_code, body.get("entries_imported")),
        (422, 0),
    )
    return


class _EmptyImporter:
    @classmethod
    def importer_tag(cls) -> str:
        return "testbase-project"

    @classmethod
    def import_entries(cls, *, project_id: str, source: Dict[str, Any]):
        return []


def test_import_route_refuses_an_import_that_finds_nothing():
    """
    **Feature: 6-test-catalog (audit ORC-06)**
    **Property: when an importer returns no entries the route answers
    422 instead of a 202 "0 imported" summary.**
    """
    response = _run_import_route(
        session=object(),
        source={"anything": True},
        importer=_EmptyImporter,
    )
    testbase.assert_equal(response.status_code, 422)
    return


def test_import_route_catalogs_pasted_includes():
    """
    **Feature: 6-test-catalog (audit ORC-06)**
    **Property: importing two pasted includes answers 202 with
    entries_imported 2 and persists both catalog entries.**
    """
    _engine, session = build_in_memory_session()
    try:
        response = _run_import_route(
            session=session,
            source={"includes": [INCLUDE_A, INCLUDE_B]},
            importer=TestbaseProjectImporter,
        )
        stored = sorted(
            row.entry_key for row in session.query(TestCatalogEntry).all()
        )
    finally:
        session.close()
    body = _decode_body(response)
    testbase.assert_equal(
        (response.status_code, body["entries_imported"], stored),
        (202, 2, sorted([INCLUDE_A, INCLUDE_B])),
    )
    return
