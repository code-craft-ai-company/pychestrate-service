"""
.. module:: resources
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for resource management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for resource management:
- POST /resources - create resource
- GET /resources - list resources
- GET /resources/{id} - get resource
- PUT /resources/{id} - update resource
- DELETE /resources/{id} - delete resource

Requirements: 1.1, 1.3, 1.4, 1.5, 10.4, 10.5
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

RESOURCES_NAMESPACE_PATH = "/resources"

resources_ns = Namespace(
    "Resources v1",
    description="Resource management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(resources_ns)

resource_create_model = resources_ns.model('ResourceCreate', {
    'name': fields.String(required=True, description='Unique resource name within pool'),
    'resource_type': fields.String(required=True, description='Resource type (device, ip_address, port, credential, generic)'),
    'pool_id': fields.Integer(description='Pool ID to assign resource to'),
    'description': fields.String(description='Resource description'),
    'metadata': fields.Raw(description='Resource metadata as key-value pairs'),
    'tags': fields.List(fields.String, description='List of tags to assign'),
    'capacity': fields.Integer(description='Capacity for shared resources (default: 1)'),
    'sensitive_fields': fields.List(fields.String, description='List of metadata fields to mask')
})

resource_update_model = resources_ns.model('ResourceUpdate', {
    'description': fields.String(description='Resource description'),
    'metadata': fields.Raw(description='Resource metadata as key-value pairs'),
    'tags': fields.List(fields.String, description='List of tags'),
    'capacity': fields.Integer(description='Capacity for shared resources'),
    'health_status': fields.String(description='Health status (online, offline, degraded, maintenance)'),
    'sensitive_fields': fields.List(fields.String, description='List of metadata fields to mask')
})

resource_response_model = resources_ns.model('ResourceResponse', {
    'id': fields.Integer(required=True, description='Resource ID'),
    'name': fields.String(required=True, description='Resource name'),
    'resource_type': fields.String(required=True, description='Resource type'),
    'pool_id': fields.Integer(description='Pool ID'),
    'pool_name': fields.String(description='Pool name'),
    'description': fields.String(description='Resource description'),
    'metadata': fields.Raw(description='Resource metadata'),
    'tags': fields.List(fields.String, description='Assigned tags'),
    'capacity': fields.Integer(required=True, description='Resource capacity'),
    'current_allocations': fields.Integer(required=True, description='Current active allocations'),
    'health_status': fields.String(required=True, description='Health status'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'updated_at': fields.DateTime(description='Last update timestamp')
})

resource_list_model = resources_ns.model('ResourceList', {
    'items': fields.List(fields.Nested(resource_response_model), description='List of resources'),
    'total': fields.Integer(required=True, description='Total number of resources'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})


# =============================================================================
# Helper Functions
# =============================================================================

def resource_response_to_dict(resource_response):
    """Convert ResourceResponse dataclass to dict."""
    return {
        'id': resource_response.id,
        'name': resource_response.name,
        'resource_type': resource_response.resource_type,
        'pool_id': resource_response.pool_id,
        'pool_name': resource_response.pool_name,
        'description': resource_response.description,
        'metadata': resource_response.metadata,
        'tags': resource_response.tags,
        'capacity': resource_response.capacity,
        'current_allocations': resource_response.current_allocations,
        'health_status': resource_response.health_status,
        'created_at': resource_response.created_at.isoformat() if resource_response.created_at else None,
        'updated_at': resource_response.updated_at.isoformat() if resource_response.updated_at else None
    }


# =============================================================================
# Endpoints
# =============================================================================

@resources_ns.route("/")
class ResourceCollection(Resource):
    """Resource collection for listing and creating resources."""
    
    @resources_ns.doc('list_resources')
    @resources_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @resources_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @resources_ns.param('pool_id', 'Filter by pool ID', type=int)
    @resources_ns.param('resource_type', 'Filter by resource type', type=str)
    @resources_ns.param('tags', 'Filter by tags (comma-separated)', type=str)
    @resources_ns.param('health_status', 'Filter by health status', type=str)
    @resources_ns.param('available_only', 'Only return available resources', type=bool)
    @resources_ns.response(200, 'Success', resource_list_model)
    @resources_ns.response(401, 'Unauthorized', error_model)
    @resources_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self):
        """
        List resources with pagination and filtering.
        
        Requirements: 1.5, 10.4
        """
        try:
            offset, limit = get_pagination_params()
            pool_id = request.args.get('pool_id', type=int)
            resource_type = request.args.get('resource_type')
            tags_str = request.args.get('tags')
            health_status = request.args.get('health_status')
            available_only = request.args.get('available_only', 'false').lower() in ('true', '1', 'yes')
            
            # Parse tags
            tags = None
            if tags_str:
                tags = [t.strip() for t in tags_str.split(',') if t.strip()]
            
            from automojo.pychestrate.core.managers.resource_manager import ResourceManager
            
            resource_manager = ResourceManager(g.db_session)
            result = resource_manager.list_resources(
                pool_id=pool_id,
                resource_type=resource_type,
                tags=tags,
                health_status=health_status,
                available_only=available_only,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[resource_response_to_dict(r) for r in result.resources],
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
    
    @resources_ns.doc('create_resource')
    @resources_ns.expect(resource_create_model)
    @resources_ns.response(201, 'Resource created', resource_response_model)
    @resources_ns.response(400, 'Validation error', error_model)
    @resources_ns.response(401, 'Unauthorized', error_model)
    @resources_ns.response(403, 'Forbidden', error_model)
    @resources_ns.response(409, 'Conflict', error_model)
    @require_auth
    @require_permission('resources.create')
    def post(self):
        """
        Create a new resource.
        
        Requirements: 1.1, 10.5
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.resource_manager import (
                ResourceManager,
                ResourceCreateRequest,
                ResourceValidationError,
                DuplicateResourceError,
                PoolNotFoundError
            )
            
            # Build the create request
            create_request = ResourceCreateRequest(
                name=data.get('name', ''),
                resource_type=data.get('resource_type', ''),
                pool_id=data.get('pool_id'),
                description=data.get('description', ''),
                metadata=data.get('metadata', {}),
                tags=data.get('tags', []),
                capacity=data.get('capacity', 1),
                sensitive_fields=data.get('sensitive_fields', [])
            )
            
            resource_manager = ResourceManager(g.db_session)
            resource_response = resource_manager.create_resource(
                create_request,
                user_id=g.current_user_id
            )
            
            return resource_response_to_dict(resource_response), 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@resources_ns.route("/<int:resource_id>")
@resources_ns.param('resource_id', 'The resource identifier')
class ResourceItem(Resource):
    """Individual resource for get, update, and delete operations."""
    
    @resources_ns.doc('get_resource')
    @resources_ns.response(200, 'Success', resource_response_model)
    @resources_ns.response(401, 'Unauthorized', error_model)
    @resources_ns.response(403, 'Forbidden', error_model)
    @resources_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self, resource_id):
        """
        Get a resource by ID.
        
        Requirements: 1.5
        """
        try:
            from automojo.pychestrate.core.managers.resource_manager import ResourceManager
            
            resource_manager = ResourceManager(g.db_session)
            resource_response = resource_manager.get_resource(resource_id)
            
            if resource_response is None:
                return not_found_error('Resource', str(resource_id))
            
            return resource_response_to_dict(resource_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @resources_ns.doc('update_resource')
    @resources_ns.expect(resource_update_model)
    @resources_ns.response(200, 'Resource updated', resource_response_model)
    @resources_ns.response(400, 'Validation error', error_model)
    @resources_ns.response(401, 'Unauthorized', error_model)
    @resources_ns.response(403, 'Forbidden', error_model)
    @resources_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.update')
    def put(self, resource_id):
        """
        Update a resource.
        
        Requirements: 1.3, 10.5
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.resource_manager import (
                ResourceManager,
                ResourceUpdateRequest,
                ResourceValidationError,
                ResourceNotFoundError
            )
            
            # Build the update request
            update_request = ResourceUpdateRequest(
                description=data.get('description'),
                metadata=data.get('metadata'),
                tags=data.get('tags'),
                capacity=data.get('capacity'),
                health_status=data.get('health_status'),
                sensitive_fields=data.get('sensitive_fields')
            )
            
            resource_manager = ResourceManager(g.db_session)
            resource_response = resource_manager.update_resource(
                resource_id,
                update_request,
                user_id=g.current_user_id
            )
            
            return resource_response_to_dict(resource_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @resources_ns.doc('delete_resource')
    @resources_ns.response(204, 'Resource deleted')
    @resources_ns.response(401, 'Unauthorized', error_model)
    @resources_ns.response(403, 'Forbidden', error_model)
    @resources_ns.response(404, 'Not found', error_model)
    @resources_ns.response(409, 'Conflict - resource has active allocations', error_model)
    @require_auth
    @require_permission('resources.delete')
    def delete(self, resource_id):
        """
        Delete a resource.
        
        Requirements: 1.4
        """
        try:
            from automojo.pychestrate.core.managers.resource_manager import (
                ResourceManager,
                ResourceNotFoundError,
                ResourceHasAllocationsError
            )
            
            resource_manager = ResourceManager(g.db_session)
            resource_manager.delete_resource(resource_id, user_id=g.current_user_id)
            
            return '', 204
            
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
    Publish the resources namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (resources_ns, "".join([version_prefix, RESOURCES_NAMESPACE_PATH]))
    ]
    return ns_list
