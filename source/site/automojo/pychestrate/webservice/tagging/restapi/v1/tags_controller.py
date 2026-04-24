"""
.. module:: tagging.restapi.v1.tags_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/tags.

.. moduleauthor:: Automation Mojo LLC

Implements the 2-tagging M1 endpoints for the ``project`` entity kind:

* ``POST   /api/v1/tags/{entity_kind}/{entity_id}``
* ``DELETE /api/v1/tags/{entity_kind}/{entity_id}/{tag}``
* ``GET    /api/v1/tags/{entity_kind}/{entity_id}``
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import request
from flask_restx import Namespace, Resource, fields

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.tagging import service as tag_service
from automojo.pychestrate.webservice.tagging.exceptions import (
    TagAssignmentNotFoundError,
    TagValueValidationError,
    TaxonomyNotFoundError,
)


TAGS_NAMESPACE_PATH = "/tags"


tags_ns = Namespace(
    "Tags v1",
    description="Tag assignments with taxonomy validation (2-tagging).",
)


tag_assign_model = tags_ns.model(
    "TagAssignRequest",
    {
        "tag": fields.String(required=True, description="Tag in taxonomy:value form"),
    },
)


tag_response_model = tags_ns.model(
    "TagResponse",
    {
        "assignment_id": fields.String(description="Server-generated UUID"),
        "entity_kind": fields.String(description="Target entity kind"),
        "entity_id": fields.String(description="Target entity id"),
        "taxonomy_name": fields.String(description="Taxonomy name"),
        "canonical_value": fields.String(description="Canonicalized tag value"),
        "assigned_at": fields.String(description="ISO-8601 timestamp"),
    },
)


def _assignment_to_dict(assignment) -> dict:
    """
        Render a :class:`TagAssignment` as the REST response dict.

        :param assignment: The row to render.

        :returns: A plain dict.
    """
    rtnval = {
        "assignment_id": str(assignment.assignment_id),
        "entity_kind": assignment.entity_kind,
        "entity_id": str(assignment.entity_id),
        "taxonomy_name": assignment.taxonomy_name,
        "canonical_value": assignment.canonical_value,
        "assigned_at": assignment.assigned_at.isoformat() if assignment.assigned_at is not None else None,
    }
    return rtnval


@tags_ns.route("/<string:entity_kind>/<string:entity_id>")
@tags_ns.param("entity_kind", "Target entity kind (``project`` at M1)")
@tags_ns.param("entity_id", "Target entity id")
class EntityTagsResource(Resource):
    """
        Resource that exposes POST and GET for tags on an entity.
    """

    @tags_ns.expect(tag_assign_model, validate=True)
    @tags_ns.marshal_with(tag_response_model, code=201)
    def post(self, entity_kind: str, entity_id: str):
        """
            Assign a tag to an entity.
        """
        payload = request.get_json(force=True, silent=False)
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()

        try:
            assignment = tag_service.assign_tag(
                db_session=db_session,
                entity_kind=entity_kind,
                entity_id=entity_id,
                raw_tag=payload.get("tag", ""),
                actor_user_id=actor_user_id,
            )
        except SemanticError as xcpt:
            tags_ns.abort(400, str(xcpt))
        except TaxonomyNotFoundError as xcpt:
            tags_ns.abort(404, str(xcpt))
        except TagValueValidationError as xcpt:
            tags_ns.abort(400, str(xcpt))

        rtnval = _assignment_to_dict(assignment)
        return rtnval, 201

    @tags_ns.marshal_list_with(tag_response_model)
    def get(self, entity_kind: str, entity_id: str):
        """
            List all tags on an entity.
        """
        db_session = _get_request_db_session()
        try:
            rows = tag_service.list_tags(
                db_session=db_session,
                entity_kind=entity_kind,
                entity_id=entity_id,
            )
        except SemanticError as xcpt:
            tags_ns.abort(400, str(xcpt))

        rtnval = [_assignment_to_dict(row) for row in rows]
        return rtnval


@tags_ns.route("/<string:entity_kind>/<string:entity_id>/<path:tag>")
@tags_ns.param("entity_kind", "Target entity kind")
@tags_ns.param("entity_id", "Target entity id")
@tags_ns.param("tag", "Tag in taxonomy:value form")
class EntityTagDetail(Resource):
    """
        Resource that exposes DELETE ``/api/v1/tags/{entity_kind}/{entity_id}/{tag}``.
    """

    def delete(self, entity_kind: str, entity_id: str, tag: str):
        """
            Remove a tag from an entity.
        """
        db_session = _get_request_db_session()
        try:
            tag_service.remove_tag(
                db_session=db_session,
                entity_kind=entity_kind,
                entity_id=entity_id,
                raw_tag=tag,
            )
        except SemanticError as xcpt:
            tags_ns.abort(400, str(xcpt))
        except TaxonomyNotFoundError as xcpt:
            tags_ns.abort(404, str(xcpt))
        except TagValueValidationError as xcpt:
            tags_ns.abort(400, str(xcpt))
        except TagAssignmentNotFoundError as xcpt:
            tags_ns.abort(404, str(xcpt))

        return "", 204


@tags_ns.route("/search")
class TagSearchResource(Resource):
    """
        GET ``/api/v1/tags/search?kind=…&expr=…``.
    """

    def get(self):
        """
            Search entities by boolean tag expression.
        """
        db_session = _get_request_db_session()
        kind = request.args.get("kind", "")
        expr = request.args.get("expr", "")

        try:
            entity_ids = tag_service.search_entities(
                db_session=db_session,
                entity_kind=kind,
                expression=expr,
            )
        except SemanticError as xcpt:
            tags_ns.abort(400, str(xcpt))
        except TagValueValidationError as xcpt:
            tags_ns.abort(400, str(xcpt))

        rtnval = {"entity_kind": kind, "entity_ids": entity_ids}
        return rtnval


@tags_ns.route("/taxonomies")
class TaxonomiesResource(Resource):
    """
        GET ``/api/v1/tags/taxonomies`` — list registered taxonomies.
    """

    def get(self):
        """
            List registered taxonomies.
        """
        from automojo.pychestrate.webservice.tagging.registry import (
            load_registered_taxonomies,
        )
        registry = load_registered_taxonomies()

        rtnval = []
        for name, pack in sorted(registry.items()):
            allowed = getattr(pack, "allowed_values", None)
            rtnval.append({
                "taxonomy_name": name,
                "case_sensitive_value": bool(getattr(pack, "case_sensitive_value", False)),
                "allowed_values": sorted(list(allowed)) if allowed is not None else None,
                "color_hex": getattr(pack, "color_hex", "#888888"),
                "description": getattr(pack, "description", ""),
            })
        return rtnval


def _get_request_db_session():
    """
        Resolve the request-scoped SQLAlchemy session.

        :returns: The SQLAlchemy Session.
    """
    from flask import g
    db_session = getattr(g, "db_session", None)
    if db_session is None:
        tags_ns.abort(503, "Request-scoped db_session not configured")
    return db_session


def _get_request_actor_user_id():
    """
        Resolve the acting principal's user id.

        :returns: The acting user id or None.
    """
    from flask import g
    actor = getattr(g, "actor_user_id", None)
    return actor


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for v1 wiring.

        :param version_prefix: Version prefix (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(tags_ns, version_prefix + TAGS_NAMESPACE_PATH)]
    return rtnval
