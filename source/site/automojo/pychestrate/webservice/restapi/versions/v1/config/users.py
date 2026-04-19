"""
.. module:: users
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for user management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for user management:
- POST /users - create user
- GET /users - list users
- GET /users/{id} - get user
- PUT /users/{id} - update user
- DELETE /users/{id} - deactivate user

Requirements: 1.1, 1.3, 1.4, 1.5, 9.4, 9.5
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
    get_db_session,
    get_pagination_params,
    paginated_response,
    error_response,
    validation_error,
    not_found_error,
    conflict_error,
    internal_error,
    create_error_model,
    AuthenticationError,
    AuthorizationError,
)


# =============================================================================
# Namespace Configuration
# =============================================================================

USERS_NAMESPACE_PATH = "/config/users"

users_ns = Namespace(
    "Users v1",
    description="User management endpoints for system configuration"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(users_ns)

user_create_model = users_ns.model('UserCreate', {
    'username': fields.String(required=True, description='Unique username'),
    'email': fields.String(required=True, description='Email address'),
    'password': fields.String(required=True, description='Password (min 12 characters)'),
    'display_name': fields.String(required=True, description='Display name'),
    'firstname': fields.String(description='First name'),
    'lastname': fields.String(description='Last name'),
    'role_ids': fields.List(fields.Integer, description='List of role IDs to assign')
})

user_update_model = users_ns.model('UserUpdate', {
    'email': fields.String(description='Email address'),
    'display_name': fields.String(description='Display name'),
    'firstname': fields.String(description='First name'),
    'lastname': fields.String(description='Last name'),
    'is_active': fields.Boolean(description='Active status'),
    'role_ids': fields.List(fields.Integer, description='List of role IDs')
})

user_response_model = users_ns.model('UserResponse', {
    'id': fields.String(required=True, description='User ID'),
    'username': fields.String(required=True, description='Username'),
    'email': fields.String(required=True, description='Email address'),
    'display_name': fields.String(required=True, description='Display name'),
    'firstname': fields.String(description='First name'),
    'lastname': fields.String(description='Last name'),
    'is_active': fields.Boolean(required=True, description='Active status'),
    'roles': fields.List(fields.String, description='Assigned role names'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'updated_at': fields.DateTime(description='Last update timestamp')
})

user_list_model = users_ns.model('UserList', {
    'items': fields.List(fields.Nested(user_response_model), description='List of users'),
    'total': fields.Integer(required=True, description='Total number of users'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})


# =============================================================================
# Helper Functions
# =============================================================================

def user_response_to_dict(user_response):
    """Convert UserResponse dataclass to dict."""
    return {
        'id': user_response.id,
        'username': user_response.username,
        'email': user_response.email,
        'display_name': user_response.display_name,
        'firstname': user_response.firstname,
        'lastname': user_response.lastname,
        'is_active': user_response.is_active,
        'roles': user_response.roles,
        'created_at': user_response.created_at.isoformat() if user_response.created_at else None,
        'updated_at': user_response.updated_at.isoformat() if user_response.updated_at else None
    }


# =============================================================================
# Endpoints
# =============================================================================

@users_ns.route("/")
class UserCollection(Resource):
    """User collection resource for listing and creating users."""
    
    @users_ns.doc('list_users')
    @users_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @users_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @users_ns.param('search', 'Search string for username, email, or display_name', type=str)
    @users_ns.param('is_active', 'Filter by active status', type=bool)
    @users_ns.response(200, 'Success', user_list_model)
    @users_ns.response(401, 'Unauthorized', error_model)
    @users_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('users.read')
    def get(self):
        """
        List users with pagination and filtering.
        
        Requirements: 1.5, 9.4
        """
        try:
            offset, limit = get_pagination_params()
            search = request.args.get('search')
            is_active_str = request.args.get('is_active')
            
            is_active = None
            if is_active_str is not None:
                is_active = is_active_str.lower() in ('true', '1', 'yes')
            
            from automojo.pychestrate.core.managers.user_manager import UserManager
            
            user_manager = UserManager(g.db_session)
            result = user_manager.list_users(
                offset=offset,
                limit=limit,
                search=search,
                is_active=is_active
            )
            
            return paginated_response(
                items=[user_response_to_dict(u) for u in result.users],
                total=result.total,
                offset=result.offset,
                limit=result.limit
            ), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))
    
    @users_ns.doc('create_user')
    @users_ns.expect(user_create_model)
    @users_ns.response(201, 'User created', user_response_model)
    @users_ns.response(400, 'Validation error', error_model)
    @users_ns.response(401, 'Unauthorized', error_model)
    @users_ns.response(403, 'Forbidden', error_model)
    @users_ns.response(409, 'Conflict', error_model)
    @require_auth
    @require_permission('users.create')
    def post(self):
        """
        Create a new user.
        
        Requirements: 1.1, 9.5
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.user_manager import (
                UserManager,
                UserCreateRequest,
                ValidationError,
                DuplicateUserError
            )
            
            # Build the create request
            create_request = UserCreateRequest(
                username=data.get('username', ''),
                email=data.get('email', ''),
                password=data.get('password', ''),
                display_name=data.get('display_name', ''),
                firstname=data.get('firstname', ''),
                lastname=data.get('lastname', ''),
                role_ids=data.get('role_ids', [])
            )
            
            user_manager = UserManager(g.db_session)
            user_response = user_manager.create_user(create_request)
            
            return user_response_to_dict(user_response), 201
            
        except ValidationError as e:
            return validation_error(e.message, e.field)
        except DuplicateUserError as e:
            return conflict_error(e.message, e.field)
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))


@users_ns.route("/<string:user_id>")
@users_ns.param('user_id', 'The user identifier')
class UserResource(Resource):
    """Individual user resource for get, update, and delete operations."""
    
    @users_ns.doc('get_user')
    @users_ns.response(200, 'Success', user_response_model)
    @users_ns.response(401, 'Unauthorized', error_model)
    @users_ns.response(403, 'Forbidden', error_model)
    @users_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('users.read')
    def get(self, user_id):
        """
        Get a user by ID.
        
        Requirements: 1.5
        """
        try:
            from automojo.pychestrate.core.managers.user_manager import UserManager
            
            user_manager = UserManager(g.db_session)
            user_response = user_manager.get_user(user_id)
            
            if user_response is None:
                return not_found_error('User', user_id)
            
            return user_response_to_dict(user_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))
    
    @users_ns.doc('update_user')
    @users_ns.expect(user_update_model)
    @users_ns.response(200, 'User updated', user_response_model)
    @users_ns.response(400, 'Validation error', error_model)
    @users_ns.response(401, 'Unauthorized', error_model)
    @users_ns.response(403, 'Forbidden', error_model)
    @users_ns.response(404, 'Not found', error_model)
    @users_ns.response(409, 'Conflict', error_model)
    @require_auth
    @require_permission('users.update')
    def put(self, user_id):
        """
        Update a user.
        
        Requirements: 1.3, 9.5
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.user_manager import (
                UserManager,
                UserUpdateRequest,
                ValidationError,
                DuplicateUserError,
                UserNotFoundError
            )
            
            # Build the update request
            update_request = UserUpdateRequest(
                email=data.get('email'),
                display_name=data.get('display_name'),
                firstname=data.get('firstname'),
                lastname=data.get('lastname'),
                is_active=data.get('is_active'),
                role_ids=data.get('role_ids')
            )
            
            user_manager = UserManager(g.db_session)
            user_response = user_manager.update_user(user_id, update_request)
            
            return user_response_to_dict(user_response), 200
            
        except UserNotFoundError:
            return not_found_error('User', user_id)
        except ValidationError as e:
            return validation_error(e.message, e.field)
        except DuplicateUserError as e:
            return conflict_error(e.message, e.field)
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))
    
    @users_ns.doc('deactivate_user')
    @users_ns.response(204, 'User deactivated')
    @users_ns.response(401, 'Unauthorized', error_model)
    @users_ns.response(403, 'Forbidden', error_model)
    @users_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('users.delete')
    def delete(self, user_id):
        """
        Deactivate a user account.
        
        Requirements: 1.4
        """
        try:
            from automojo.pychestrate.core.managers.user_manager import (
                UserManager,
                UserNotFoundError
            )
            
            user_manager = UserManager(g.db_session)
            user_manager.deactivate_user(user_id)
            
            return '', 204
            
        except UserNotFoundError:
            return not_found_error('User', user_id)
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))


# =============================================================================
# Namespace Publishing
# =============================================================================

def publish_namespaces(version_prefix):
    """
    Publish the users namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (users_ns, "".join([version_prefix, USERS_NAMESPACE_PATH]))
    ]
    return ns_list
