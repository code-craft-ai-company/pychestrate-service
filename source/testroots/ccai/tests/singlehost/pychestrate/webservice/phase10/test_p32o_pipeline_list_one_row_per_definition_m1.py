"""
.. module:: test_p32o_pipeline_list_one_row_per_definition_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A pipeline saved from several commits is listed once (ORC-37).

.. moduleauthor:: Code Craft AI LLC

The pipelines list returned one row per cached ``(commit, filename)``, but a
pipeline is identified by the digest of its document: saving the same document
from a second commit (or saving it again) added a row with the same ``pipeline_id``
and the list looked as if it held duplicates. The list now has one entry per
definition, with its newest source in ``commit_sha``/``filename`` and the older ones
in ``other_sources``; ``meta.total`` counts definitions.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
    service as definition_service,
)
from ccai.pychestrate.webservice.orchestration.pipelines.restapi.v1 import (
    pipeline_definitions_routes,
)


class _Query:
    def __init__(self, values: Dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._values.get(key, default)


class _Request:
    def __init__(self, query: Dict[str, str]) -> None:
        self.path = "/api/v1/projects/proj-1/pipelines"
        self.path_params = {"project_id": "proj-1"}
        self.query_params = _Query(query)
        self.db_session = object()
        self.auth_principal = type("Principal", (), {"user_id": "user-1"})()


def _view(*, pipeline_id: str, commit: str, filename: str, hour: int) -> Any:
    return definition_service.PipelineDefinitionView(
        pipeline_id=pipeline_id, project_id="proj-1", name="ci", schema_version=1, commit_sha=commit, filename=filename,
        stages=(), cached_at=datetime(2026, 9, 29, hour, 0, 0, tzinfo=timezone.utc),
    )


def _list(views: List[Any], query: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    checks = create_module_patch(pipeline_definitions_routes.rbac_evaluator, "check_permission")
    checks.activate().configure(side_effect=lambda **kwargs: type("Decision", (), {"allowed": True, "reason": ""})())
    project = create_module_patch(pipeline_definitions_routes.projects_repo, "get_project_by_id")
    project.activate().configure(side_effect=lambda **kwargs: type("Project", (), {"project_id": "proj-1", "slug": "p"})())
    listing = create_module_patch(pipeline_definitions_routes.definition_service, "list_definitions")
    listing.activate().configure(side_effect=lambda **kwargs: views)
    try:
        response = pipeline_definitions_routes.handle_list_pipelines(_Request(query or {}))
    finally:
        listing.deactivate()
        project.deactivate()
        checks.deactivate()
    return json.loads(response.body.decode("utf-8"))


def test_the_same_document_saved_from_several_sources_is_listed_once_with_the_others_named():
    """
    **Feature: one row per definition (ORC-37)**
    **Property: three cache rows, two of them the same document, list as two pipelines; the
    repeated one shows its newest source and names the older one; the other has none; the
    total counts definitions.**
    """
    body = _list([
        _view(pipeline_id="aaa", commit="c3333333", filename="ci.yaml", hour=12),
        _view(pipeline_id="bbb", commit="c2222222", filename="deploy.yaml", hour=11),
        _view(pipeline_id="aaa", commit="c1111111", filename="ci.yaml", hour=10),
    ])
    first, second = body["items"]

    testbase.assert_equal(
        (
            [item["pipeline_id"] for item in body["items"]], body["meta"]["total"],
            first["commit_sha"], first["other_sources"], second["other_sources"],
        ),
        (
            ["aaa", "bbb"], 2, "c3333333",
            [{"filename": "ci.yaml", "commit_sha": "c1111111", "cached_at": "2026-09-29T10:00:00+00:00"}], [],
        ),
    )
    return


def test_paging_counts_definitions_not_cache_rows():
    """
    **Feature: one row per definition (ORC-37)**
    **Property: with five rows holding three definitions and a page size of two, page 2 has the
    third definition and the total is 3.**
    """
    views = [
        _view(pipeline_id="d1", commit="a", filename="x.yaml", hour=12),
        _view(pipeline_id="d1", commit="b", filename="x.yaml", hour=11),
        _view(pipeline_id="d2", commit="a", filename="y.yaml", hour=10),
        _view(pipeline_id="d2", commit="b", filename="y.yaml", hour=9),
        _view(pipeline_id="d3", commit="a", filename="z.yaml", hour=8),
    ]
    body = _list(views, {"page": "2", "per_page": "2"})

    testbase.assert_equal(
        ([item["pipeline_id"] for item in body["items"]], body["meta"]["total"]),
        (["d3"], 3),
    )
    return


# ---------------------------------------------------------------------------
# Deleting a pipeline removes every copy of it
# ---------------------------------------------------------------------------


_DOCUMENT = b"""
schema_version: 1
name: ci-pipeline
stages:
  - id: build
    steps:
      - id: build-image
        kind: build
        inputs:
          image: registry.example.com/app
          commands:
            - make build
"""

_OTHER_DOCUMENT = _DOCUMENT.replace(b"ci-pipeline", b"other-pipeline")

_PROJECT = "00000000-0000-4000-8000-000000010001"


def test_deleting_a_pipeline_removes_every_commit_and_file_it_was_saved_from():
    """
    **Feature: one row per definition (ORC-37)**
    **Property: a document saved from two commits and a second document saved once leave three
    cache rows; deleting the first document's pipeline removes both of its rows (so the list does
    not show it again under its older source) and leaves the other pipeline; deleting it again is
    "not found".**
    """
    from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing
    from ccai.pychestrate.webservice.messaging.event_bus import reset_for_testing as reset_event_bus
    from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
        PipelineRunNotFoundError,
        register_builtin_extensions,
    )
    from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session

    reset_registry_for_testing()
    reset_event_bus()
    register_builtin_extensions()
    _engine, session = build_in_memory_session()
    first = definition_service.upsert_definition(db_session=session, project_id=_PROJECT, commit_sha="c1", filename="ci.yaml", document_bytes=_DOCUMENT)
    again = definition_service.upsert_definition(db_session=session, project_id=_PROJECT, commit_sha="c2", filename="ci.yaml", document_bytes=_DOCUMENT)
    other = definition_service.upsert_definition(db_session=session, project_id=_PROJECT, commit_sha="c1", filename="other.yaml", document_bytes=_OTHER_DOCUMENT)
    rows_before = len(definition_service.list_definitions(db_session=session, project_id=_PROJECT, limit=100))

    definition_service.delete_definition(db_session=session, project_id=_PROJECT, pipeline_id=first.pipeline_id)
    left = [view.pipeline_id for view in definition_service.list_definitions(db_session=session, project_id=_PROJECT, limit=100)]
    not_found = False
    try:
        definition_service.delete_definition(db_session=session, project_id=_PROJECT, pipeline_id=first.pipeline_id)
    except PipelineRunNotFoundError:
        not_found = True

    testbase.assert_equal(
        (first.pipeline_id == again.pipeline_id, first.pipeline_id != other.pipeline_id, rows_before, left, not_found),
        (True, True, 3, [other.pipeline_id], True),
    )
    return
