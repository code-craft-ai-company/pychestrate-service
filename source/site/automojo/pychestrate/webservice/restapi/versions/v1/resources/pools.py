"""
.. module:: pools
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for resource pool management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for resource pool management:
- POST /pools - create pool
- GET /pools - list pools
- GET /pools/{id} - get pool
- DELETE /pools/{id} - delete pool

Requirements: 2.1, 2.5
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

POOLS_NAMESPACE_PATH = "/pools"

pools_ns = Namespace(
    "Resource Pools v1",
    description="Resource pool management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(pools_ns)

pool_create_model = pools_ns.model('PoolCreate', {
    'name': fields.String(required=True, description='Unique pool name'),
    'description': fields.String(description='Pool description')
})

pool_response_model = pools_ns.model('PoolResponse', {
    'id': fields.Integer(required=True, description='Pool ID'),
    'name': fields.String(required=True, description='Pool name'),
    'description': fields.String(description='Pool description'),
    'is_default': fields.Boolean(required=True, description='Whether this is the default pool'),
    'resource_count': fields.Integer(required=True, description='Number of resources in pool'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'created_by': fields.String(description='User who created the pool')
})

pool_list_model = pools_ns.model('PoolList', {
    'items': fields.List(fields.Nested(pool_response_model), description='List of pools'),
    'total': fields.Integer(required=True, description='Total number of pools'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})


# =============================================================================
# Helper Functions
# =============================================================================

def pool_response_to_dict(pool_response):
    """Convert ResourcePoolResponse dataclass to dict."""
    return {
        'id': pool_response.id,
        'name': pool_response.name,
        'description': pool_response.description,
        'is_default': pool_response.is_default,
        'resource_count': pool_response.resource_count,
        'created_at': pool_response.created_at.isoformat() if pool_response.created_at else None,
        'created_by': pool_response.created_by
    }


# =============================================================================
# Endpoints
# =============================================================================

@pools_ns.route("/")
class PoolCollection(Resource):
    """Pool collection for listing and creating pools."""
    
    @pools_ns.doc('list_pools')
    @pools_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @pools_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @pools_ns.response(200, 'Success', pool_list_model)
    @pools_ns.response(401, 'Unauthorized', error_model)
    @pools_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self):
        """
        List resource pools with pagination.
        
        Requirements: 2.1
        """
        try:
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.resource_manager import ResourceManager
            
            resource_manager = ResourceManager(g.db_session)
            result = resource_manager.list_pools(
                user_id=g.current_user_id,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[pool_response_to_dict(p) for p in result.pools],
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
    
    @pools_ns.doc('create_pool')
    @pools_ns.expect(pool_create_model)
    @pools_ns.response(201, 'Pool created', pool_response_model)
    @pools_ns.response(400, 'Validation error', error_model)
    @pools_ns.response(401, 'Unauthorized', error_model)
    @pools_ns.response(403, 'Forbidden', error_model)
    @pools_ns.response(409, 'Conflict', error_model)
    @require_auth
    @require_permission('resources.create')
    def post(self):
        """
        Create a new resource pool.
        
        Requirements: 2.1
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.resource_manager import (
                ResourceManager,
                ResourcePoolCreateRequest,
                ResourceValidationError,
                DuplicateResourceError
            )
            
            # Build the create request
            create_request = ResourcePoolCreateRequest(
                name=data.get('name', ''),
                description=data.get('description', '')
            )
            
            resource_manager = ResourceManager(g.db_session)
            pool_response = resource_manager.create_pool(
                create_request,
                user_id=g.current_user_id
            )
            
            return pool_response_to_dict(pool_response), 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@pools_ns.route("/<int:pool_id>")
@pools_ns.param('pool_id', 'The pool identifier')
class PoolItem(Resource):
    """Individual pool for get and delete operations."""
    
    @pools_ns.doc('get_pool')
    @pools_ns.response(200, 'Success', pool_response_model)
    @pools_ns.response(401, 'Unauthorized', error_model)
    @pools_ns.response(403, 'Forbidden', error_model)
    @pools_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self, pool_id):
        """
        Get a pool by ID.
        """
        try:
            from automojo.pychestrate.core.managers.resource_manager import ResourceManager
            
            resource_manager = ResourceManager(g.db_session)
            pool_response = resource_manager.get_pool(pool_id)
            
            if pool_response is None:
                return not_found_error('Pool', str(pool_id))
            
            return pool_response_to_dict(pool_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @pools_ns.doc('delete_pool')
    @pools_ns.response(204, 'Pool deleted')
    @pools_ns.response(401, 'Unauthorized', error_model)
    @pools_ns.response(403, 'Forbidden', error_model)
    @pools_ns.response(404, 'Not found', error_model)
    @pools_ns.response(409, 'Conflict - pool has resources', error_model)
    @require_auth
    @require_permission('resources.delete')
    def delete(self, pool_id):
        """
        Delete a pool.
        
        Requirements: 2.5
        """
        try:
            from automojo.pychestrate.core.managers.resource_manager import (
                ResourceManager,
                PoolNotFoundError,
                PoolHasResourcesError
            )
            
            resource_manager = ResourceManager(g.db_session)
            resource_manager.delete_pool(pool_id, user_id=g.current_user_id)
            
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
    Publish the pools namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (pools_ns, "".join([version_prefix, POOLS_NAMESPACE_PATH]))
    ]
    return ns_list
