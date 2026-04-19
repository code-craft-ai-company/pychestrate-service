"""
.. module:: tags
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for resource tag management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for tag management:
- POST /resources/{id}/tags - add tags
- DELETE /resources/{id}/tags - remove tags
- GET /tags - list all tags

Requirements: 7.1
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import request, g
from flask_restx import Namespace, Resource, fields

from .base import (
    require_auth,
    require_permission,
    get_pagination_params,
    paginated_response,
    error_response,
    validation_error,
    not_found_error,
    conflict_error,
    internal_error,
    create_error_model,
    exception_to_response,
    AuthenticationError,
    AuthorizationError,
)


# =============================================================================
# Namespace Configuration
# =============================================================================

TAGS_NAMESPACE_PATH = "/tags"
RESOURCE_TAGS_NAMESPACE_PATH = "/resources"

tags_ns = Namespace(
    "Tags v1",
    description="Tag management endpoints"
)

resource_tags_ns = Namespace(
    "Resource Tags v1",
    description="Resource tag management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(tags_ns)

tags_request_model = tags_ns.model('TagsRequest', {
    'tags': fields.List(fields.String, required=True, description='List of tag names')
})

tag_response_model = tags_ns.model('TagResponse', {
    'id': fields.Integer(required=True, description='Tag ID'),
    'name': fields.String(required=True, description='Tag name'),
    'description': fields.String(description='Tag description'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

tag_list_model = tags_ns.model('TagList', {
    'items': fields.List(fields.Nested(tag_response_model), description='List of tags'),
    'total': fields.Integer(required=True, description='Total number of tags'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})


# =============================================================================
# Helper Functions
# =============================================================================

def tag_response_to_dict(tag_response):
    """Convert TagResponse dataclass to dict."""
    return {
        'id': tag_response.id,
        'name': tag_response.name,
        'description': tag_response.description,
        'created_at': tag_response.created_at.isoformat() if tag_response.created_at else None
    }


# =============================================================================
# Endpoints
# =============================================================================

@tags_ns.route("/")
class TagCollection(Resource):
    """Tag collection for listing all tags."""
    
    @tags_ns.doc('list_tags')
    @tags_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @tags_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @tags_ns.response(200, 'Success', tag_list_model)
    @tags_ns.response(401, 'Unauthorized', error_model)
    @tags_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self):
        """
        List all tags with pagination.
        
        Requirements: 7.1
        """
        try:
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.resource_manager import ResourceManager
            
            resource_manager = ResourceManager(g.db_session)
            result = resource_manager.list_tags(
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[tag_response_to_dict(t) for t in result.tags],
                total=result.total,
                offset=result.offset,
                limit=result.limit
            ), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# Resource tags endpoints
resource_tags_error_model = create_error_model(resource_tags_ns)

resource_tags_request_model = resource_tags_ns.model('ResourceTagsRequest', {
    'tags': fields.List(fields.String, required=True, description='List of tag names')
})


@resource_tags_ns.route("/<int:resource_id>/tags")
@resource_tags_ns.param('resource_id', 'The resource identifier')
class ResourceTags(Resource):
    """Resource tags endpoint for adding and removing tags."""
    
    @resource_tags_ns.doc('add_tags')
    @resource_tags_ns.expect(resource_tags_request_model)
    @resource_tags_ns.response(200, 'Tags added')
    @resource_tags_ns.response(400, 'Validation error', resource_tags_error_model)
    @resource_tags_ns.response(401, 'Unauthorized', resource_tags_error_model)
    @resource_tags_ns.response(403, 'Forbidden', resource_tags_error_model)
    @resource_tags_ns.response(404, 'Not found', resource_tags_error_model)
    @require_auth
    @require_permission('resources.update')
    def post(self, resource_id):
        """
        Add tags to a resource.
        
        Requirements: 7.1
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            tags = data.get('tags', [])
            if not tags:
                return validation_error("tags list required", field='tags')
            
            from automojo.pychestrate.core.managers.resource_manager import (
                ResourceManager,
                ResourceNotFoundError,
                ResourceValidationError
            )
            
            resource_manager = ResourceManager(g.db_session)
            resource_manager.add_tags(
                resource_id,
                tags,
                user_id=g.current_user_id
            )
            
            return {'message': f'Added {len(tags)} tag(s) to resource'}, 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @resource_tags_ns.doc('remove_tags')
    @resource_tags_ns.expect(resource_tags_request_model)
    @resource_tags_ns.response(200, 'Tags removed')
    @resource_tags_ns.response(400, 'Validation error', resource_tags_error_model)
    @resource_tags_ns.response(401, 'Unauthorized', resource_tags_error_model)
    @resource_tags_ns.response(403, 'Forbidden', resource_tags_error_model)
    @resource_tags_ns.response(404, 'Not found', resource_tags_error_model)
    @require_auth
    @require_permission('resources.update')
    def delete(self, resource_id):
        """
        Remove tags from a resource.
        
        Requirements: 7.1
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            tags = data.get('tags', [])
            if not tags:
                return validation_error("tags list required", field='tags')
            
            from automojo.pychestrate.core.managers.resource_manager import (
                ResourceManager,
                ResourceNotFoundError
            )
            
            resource_manager = ResourceManager(g.db_session)
            resource_manager.remove_tags(
                resource_id,
                tags,
                user_id=g.current_user_id
            )
            
            return {'message': f'Removed {len(tags)} tag(s) from resource'}, 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Namespace Publishing
# =============================================================================

def publish_namespaces(version_prefix):
    """
    Publish the tags namespaces.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (tags_ns, "".join([version_prefix, TAGS_NAMESPACE_PATH])),
        (resource_tags_ns, "".join([version_prefix, RESOURCE_TAGS_NAMESPACE_PATH]))
    ]
    return ns_list
