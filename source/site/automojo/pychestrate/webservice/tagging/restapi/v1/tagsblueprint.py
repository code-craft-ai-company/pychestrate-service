"""
.. module:: tagging.restapi.v1.tagsblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/tags.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict

from automojo.errors.exceptions import SemanticError

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.dbsessionmiddleware import (
    get_request_actor_user_id,
)
from automojo.pychestrate.webservice.tagging import service as tag_service
from automojo.pychestrate.webservice.tagging.exceptions import (
    TagAssignmentNotFoundError,
    TagValueValidationError,
    TaxonomyNotFoundError,
)


TAGS_BASE_PATH = "/api/v1/tags"


def _assignment_to_dict(assignment) -> Dict[str, Any]:
    """
        Render a :class:`TagAssignment` as the REST response dict.
    """
    if assignment.assigned_at is not None:
        assigned_at_field = assignment.assigned_at.isoformat()
    else:
        assigned_at_field = None
    rtnval = {
        "assignment_id": str(assignment.assignment_id),
        "entity_kind": assignment.entity_kind,
        "entity_id": str(assignment.entity_id),
        "taxonomy_name": assignment.taxonomy_name,
        "canonical_value": assignment.canonical_value,
        "assigned_at": assigned_at_field,
    }
    return rtnval


def _require_db_session(*, request: Request) -> Any:
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        err_lines = [
            "Request-scoped db_session not configured.",
            "DbSessionMiddleware must be installed in the pipeline.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise HTTPException(status_code=503, detail=err_msg)
    return db_session


def _read_json_body(*, request: Request) -> Dict[str, Any]:
    raw_body = request.body
    if raw_body is None:
        raise HTTPException(status_code=400, detail="request body required")
    if len(raw_body) == 0:
        raise HTTPException(status_code=400, detail="request body required")
    try:
        decoded = request.json()
    except Exception as exc:
        err_msg = "request body must be valid JSON"
        raise HTTPException(status_code=400, detail=err_msg) from exc
    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object",
        )
    rtnval = decoded
    return rtnval


class TagsBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/tags`` endpoints.
    """

    base_path = TAGS_BASE_PATH
    tags = ["tags", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/tags/taxonomies",
        methods=["GET"],
        doc=Doc(
            summary="List registered taxonomies",
            description=(
                "Return registered taxonomies with their allowed-value "
                "and case-sensitivity metadata."
            ),
        ),
    )
    def list_taxonomies(request: Request) -> JSONResponse:
        """
            List registered taxonomies.
        """
        from automojo.pychestrate.webservice.tagging.registry import (
            load_registered_taxonomies,
        )
        registry = load_registered_taxonomies()

        entries = []
        for name, pack in sorted(registry.items()):
            allowed = getattr(pack, "allowed_values", None)
            if allowed is not None:
                allowed_field = sorted(list(allowed))
            else:
                allowed_field = None
            entries.append({
                "taxonomy_name": name,
                "case_sensitive_value": bool(
                    getattr(pack, "case_sensitive_value", False),
                ),
                "allowed_values": allowed_field,
                "color_hex": getattr(pack, "color_hex", "#888888"),
                "description": getattr(pack, "description", ""),
            })
        rtnval = JSONResponse(content=entries, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/tags/search",
        methods=["GET"],
        doc=Doc(
            summary="Search by tag expression",
            description=(
                "Return entity ids matching a boolean tag expression."
            ),
        ),
    )
    def search_tags(request: Request) -> JSONResponse:
        """
            Search entities by boolean tag expression.
        """
        db_session = _require_db_session(request=request)
        kind = request.query_params.get("kind", "")
        expr = request.query_params.get("expr", "")

        try:
            entity_ids = tag_service.search_entities(
                db_session=db_session,
                entity_kind=kind,
                expression=expr,
            )
        except SemanticError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except TagValueValidationError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        body = {"entity_kind": kind, "entity_ids": entity_ids}
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/tags/{entity_kind}/{entity_id}",
        methods=["POST"],
        doc=Doc(
            summary="Assign tag to entity",
            description="Assign a taxonomy:value tag to an entity.",
        ),
    )
    def assign_tag(request: Request) -> JSONResponse:
        """
            Assign a tag to an entity.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        entity_kind = request.path_params.get("entity_kind", "")
        entity_id = request.path_params.get("entity_id", "")

        try:
            assignment = tag_service.assign_tag(
                db_session=db_session,
                entity_kind=entity_kind,
                entity_id=entity_id,
                raw_tag=payload.get("tag", ""),
                actor_user_id=actor_user_id,
            )
        except SemanticError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except TaxonomyNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        except TagValueValidationError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        body = _assignment_to_dict(assignment=assignment)
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/tags/{entity_kind}/{entity_id}",
        methods=["GET"],
        doc=Doc(
            summary="List entity tags",
            description="List all tags assigned to an entity.",
        ),
    )
    def list_entity_tags(request: Request) -> JSONResponse:
        """
            List all tags on an entity.
        """
        db_session = _require_db_session(request=request)
        entity_kind = request.path_params.get("entity_kind", "")
        entity_id = request.path_params.get("entity_id", "")

        try:
            rows = tag_service.list_tags(
                db_session=db_session,
                entity_kind=entity_kind,
                entity_id=entity_id,
            )
        except SemanticError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        body = [_assignment_to_dict(assignment=row) for row in rows]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/tags/{entity_kind}/{entity_id}/{tag}",
        methods=["DELETE"],
        doc=Doc(
            summary="Remove tag from entity",
            description="Remove a single tag from an entity.",
        ),
    )
    def remove_tag(request: Request) -> Response:
        """
            Remove a tag from an entity.
        """
        db_session = _require_db_session(request=request)
        entity_kind = request.path_params.get("entity_kind", "")
        entity_id = request.path_params.get("entity_id", "")
        tag = request.path_params.get("tag", "")

        try:
            tag_service.remove_tag(
                db_session=db_session,
                entity_kind=entity_kind,
                entity_id=entity_id,
                raw_tag=tag,
            )
        except SemanticError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except TaxonomyNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        except TagValueValidationError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except TagAssignmentNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc

        rtnval = Response(status_code=204, body=b"")
        return rtnval
