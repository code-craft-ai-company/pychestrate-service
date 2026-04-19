"""
.. module:: roles
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for role management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for role management:
- POST /roles - create role
- GET /roles - list roles
- PUT /roles/{id} - update role
- POST /users/{id}/roles - assign role
- DELETE /users/{id}/roles/{role_id} - remove role

Requirements: 4.1, 4.2, 4.3
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
    AuthenticationError,
    AuthorizationError,
)


# =============================================================================
# Namespace Configuration
# =============================================================================

ROLES_NAMESPACE_PATH = "/config/roles"
USER_ROLES_NAMESPACE_PATH = "/config/users"

roles_ns = Namespace(
    "Roles v1",
    description="Role management endpoints for system configuration"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(roles_ns)

role_create_model = roles_ns.model('RoleCreate', {
    'name': fields.String(required=True, description='Role name'),
    'description': fields.String(description='Role description'),
    'permission_ids': fields.List(fields.Integer, description='List of permission IDs')
})

role_update_model = roles_ns.model('RoleUpdate', {
    'name': fields.String(description='Role name'),
    'description': fields.String(description='Role description'),
    'permission_ids': fields.List(fields.Integer, description='List of permission IDs')
})

permission_model = roles_ns.model('Permission', {
    'id': fields.Integer(required=True, description='Permission ID'),
    'name': fields.String(required=True, description='Permission name'),
    'description': fields.String(description='Permission description')
})

role_response_model = roles_ns.model('RoleResponse', {
    'id': fields.Integer(required=True, description='Role ID'),
    'name': fields.String(required=True, description='Role name'),
    'description': fields.String(description='Role description'),
    'is_system': fields.Boolean(required=True, description='Whether this is a system role'),
    'permissions': fields.List(fields.Nested(permission_model), description='Assigned permissions'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

role_list_model = roles_ns.model('RoleList', {
    'items': fields.List(fields.Nested(role_response_model), description='List of roles'),
    'total': fields.Integer(required=True, description='Total number of roles'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})

role_assign_model = roles_ns.model('RoleAssign', {
    'role_id': fields.Integer(required=True, description='Role ID to assign')
})


# =============================================================================
# Helper Functions
# =============================================================================

def role_to_dict(role):
    """Convert SystemRole ORM object to dict."""
    permissions = []
    for perm in role.permissions:
        permissions.append({
            'id': perm.id,
            'name': perm.name,
            'description': perm.description or ''
        })
    
    return {
        'id': role.id,
        'name': role.name,
        'description': role.description or '',
        'is_system': role.is_system,
        'permissions': permissions,
        'created_at': role.created_at.isoformat() if role.created_at else None
    }


# =============================================================================
# Role Endpoints
# =============================================================================

@roles_ns.route("/")
class RoleCollection(Resource):
    """Role collection resource for listing and creating roles."""
    
    @roles_ns.doc('list_roles')
    @roles_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @roles_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @roles_ns.response(200, 'Success', role_list_model)
    @roles_ns.response(401, 'Unauthorized', error_model)
    @roles_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('roles.read')
    def get(self):
        """
        List all roles with pagination.
        
        Requirements: 4.1
        """
        try:
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.orm import SystemRole
            
            query = g.db_session.query(SystemRole)
            total = query.count()
            roles = query.offset(offset).limit(limit).all()
            
            return paginated_response(
                items=[role_to_dict(r) for r in roles],
                total=total,
                offset=offset,
                limit=limit
            ), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))
    
    @roles_ns.doc('create_role')
    @roles_ns.expect(role_create_model)
    @roles_ns.response(201, 'Role created', role_response_model)
    @roles_ns.response(400, 'Validation error', error_model)
    @roles_ns.response(401, 'Unauthorized', error_model)
    @roles_ns.response(403, 'Forbidden', error_model)
    @roles_ns.response(409, 'Conflict', error_model)
    @require_auth
    @require_permission('roles.create')
    def post(self):
        """
        Create a new role.
        
        Requirements: 4.1
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            name = data.get('name', '').strip()
            description = data.get('description', '')
            permission_ids = data.get('permission_ids', [])
            
            if not name:
                return validation_error("Role name required", "name")
            
            from automojo.pychestrate.core.orm import SystemRole, Permission
            from automojo.pychestrate.core.defaults import utc_now
            
            # Check for duplicate name
            existing = g.db_session.query(SystemRole).filter(
                SystemRole.name == name
            ).first()
            
            if existing:
                return conflict_error(f"Role '{name}' already exists", "name")
            
            # Create the role
            role = SystemRole(
                name=name,
                description=description,
                is_system=False,
                created_at=utc_now()
            )
            
            # Assign permissions
            if permission_ids:
                permissions = g.db_session.query(Permission).filter(
                    Permission.id.in_(permission_ids)
                ).all()
                role.permissions = permissions
            
            g.db_session.add(role)
            g.db_session.commit()
            
            return role_to_dict(role), 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))


@roles_ns.route("/<int:role_id>")
@roles_ns.param('role_id', 'The role identifier')
class RoleResource(Resource):
    """Individual role resource for get and update operations."""
    
    @roles_ns.doc('get_role')
    @roles_ns.response(200, 'Success', role_response_model)
    @roles_ns.response(401, 'Unauthorized', error_model)
    @roles_ns.response(403, 'Forbidden', error_model)
    @roles_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('roles.read')
    def get(self, role_id):
        """
        Get a role by ID.
        """
        try:
            from automojo.pychestrate.core.orm import SystemRole
            
            role = g.db_session.query(SystemRole).filter(
                SystemRole.id == role_id
            ).first()
            
            if role is None:
                return not_found_error('Role', str(role_id))
            
            return role_to_dict(role), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))
    
    @roles_ns.doc('update_role')
    @roles_ns.expect(role_update_model)
    @roles_ns.response(200, 'Role updated', role_response_model)
    @roles_ns.response(400, 'Validation error', error_model)
    @roles_ns.response(401, 'Unauthorized', error_model)
    @roles_ns.response(403, 'Forbidden', error_model)
    @roles_ns.response(404, 'Not found', error_model)
    @roles_ns.response(409, 'Conflict', error_model)
    @require_auth
    @require_permission('roles.update')
    def put(self, role_id):
        """
        Update a role.
        
        Requirements: 4.1
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.orm import SystemRole, Permission
            
            role = g.db_session.query(SystemRole).filter(
                SystemRole.id == role_id
            ).first()
            
            if role is None:
                return not_found_error('Role', str(role_id))
            
            # Update name if provided
            if 'name' in data:
                name = data['name'].strip()
                if not name:
                    return validation_error("Role name cannot be empty", "name")
                
                # Check for duplicate name (excluding current role)
                existing = g.db_session.query(SystemRole).filter(
                    SystemRole.name == name,
                    SystemRole.id != role_id
                ).first()
                
                if existing:
                    return conflict_error(f"Role '{name}' already exists", "name")
                
                role.name = name
            
            # Update description if provided
            if 'description' in data:
                role.description = data['description']
            
            # Update permissions if provided
            if 'permission_ids' in data:
                permission_ids = data['permission_ids']
                permissions = g.db_session.query(Permission).filter(
                    Permission.id.in_(permission_ids)
                ).all()
                role.permissions = permissions
            
            g.db_session.commit()
            
            return role_to_dict(role), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))


# =============================================================================
# User Role Assignment Endpoints
# =============================================================================

@roles_ns.route("/users/<string:user_id>/roles")
@roles_ns.param('user_id', 'The user identifier')
class UserRoleCollection(Resource):
    """User role assignment resource."""
    
    @roles_ns.doc('assign_role_to_user')
    @roles_ns.expect(role_assign_model)
    @roles_ns.response(200, 'Role assigned')
    @roles_ns.response(400, 'Validation error', error_model)
    @roles_ns.response(401, 'Unauthorized', error_model)
    @roles_ns.response(403, 'Forbidden', error_model)
    @roles_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('users.update')
    def post(self, user_id):
        """
        Assign a role to a user.
        
        Requirements: 4.2
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            role_id = data.get('role_id')
            
            if role_id is None:
                return validation_error("Role ID required", "role_id")
            
            from automojo.pychestrate.core.managers.user_manager import (
                UserManager,
                UserNotFoundError,
                RoleNotFoundError
            )
            
            user_manager = UserManager(g.db_session)
            user_manager.assign_role(user_id, role_id)
            
            return {'message': 'Role assigned successfully'}, 200
            
        except UserNotFoundError:
            return not_found_error('User', user_id)
        except RoleNotFoundError:
            return not_found_error('Role', str(role_id))
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))


@roles_ns.route("/users/<string:user_id>/roles/<int:role_id>")
@roles_ns.param('user_id', 'The user identifier')
@roles_ns.param('role_id', 'The role identifier')
class UserRoleResource(Resource):
    """Individual user role resource for removal."""
    
    @roles_ns.doc('remove_role_from_user')
    @roles_ns.response(204, 'Role removed')
    @roles_ns.response(401, 'Unauthorized', error_model)
    @roles_ns.response(403, 'Forbidden', error_model)
    @roles_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('users.update')
    def delete(self, user_id, role_id):
        """
        Remove a role from a user.
        
        Requirements: 4.3
        """
        try:
            from automojo.pychestrate.core.managers.user_manager import (
                UserManager,
                UserNotFoundError,
                RoleNotFoundError
            )
            
            user_manager = UserManager(g.db_session)
            user_manager.remove_role(user_id, role_id)
            
            return '', 204
            
        except UserNotFoundError:
            return not_found_error('User', user_id)
        except RoleNotFoundError:
            return not_found_error('Role', str(role_id))
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
    Publish the roles namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (roles_ns, "".join([version_prefix, ROLES_NAMESPACE_PATH]))
    ]
    return ns_list
