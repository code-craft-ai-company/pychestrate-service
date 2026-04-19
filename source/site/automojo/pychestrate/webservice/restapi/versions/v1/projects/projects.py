"""
.. module:: projects
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for project management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for project management:
- POST /projects - create project
- GET /projects - list projects
- GET /projects/{id} - get project
- PUT /projects/{id} - update project
- DELETE /projects/{id} - delete project
- GET /projects/{id}/members - list members
- POST /projects/{id}/members - add member
- PUT /projects/{id}/members/{user_id} - update member role
- DELETE /projects/{id}/members/{user_id} - remove member
- GET /projects/{id}/resources - list assigned resources
- POST /projects/{id}/resources - assign resource
- DELETE /projects/{id}/resources/{resource_id} - unassign resource
- GET /projects/{id}/variables - list variables
- POST /projects/{id}/variables - create variable
- PUT /projects/{id}/variables/{var_id} - update variable
- DELETE /projects/{id}/variables/{var_id} - delete variable

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import request, g
from flask_restx import Namespace, Resource, fields

from ..resources.base import (
    require_auth,
    require_permission,
    get_pagination_params,
    paginated_response,
    error_response,
    validation_error,
    not_found_error,
    conflict_error,
    forbidden_error,
    internal_error,
    create_error_model,
    exception_to_response,
    AuthenticationError,
    AuthorizationError,
)


# =============================================================================
# Namespace Configuration
# =============================================================================

PROJECTS_NAMESPACE_PATH = "/projects"

projects_ns = Namespace(
    "Projects v1",
    description="Project management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(projects_ns)

project_create_model = projects_ns.model('ProjectCreate', {
    'name': fields.String(required=True, description='Unique project name'),
    'description': fields.String(description='Project description'),
    'metadata': fields.Raw(description='Project metadata as key-value pairs')
})

project_update_model = projects_ns.model('ProjectUpdate', {
    'name': fields.String(description='Project name'),
    'description': fields.String(description='Project description'),
    'metadata': fields.Raw(description='Project metadata as key-value pairs')
})

project_response_model = projects_ns.model('ProjectResponse', {
    'id': fields.Integer(required=True, description='Project ID'),
    'name': fields.String(required=True, description='Project name'),
    'description': fields.String(description='Project description'),
    'owner_id': fields.String(required=True, description='Owner user ID'),
    'owner_username': fields.String(required=True, description='Owner username'),
    'metadata': fields.Raw(description='Project metadata'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'updated_at': fields.DateTime(description='Last update timestamp'),
    'last_activity_at': fields.DateTime(description='Last activity timestamp'),
    'member_count': fields.Integer(description='Number of members'),
    'repository_count': fields.Integer(description='Number of repositories'),
    'active_jobs': fields.Integer(description='Number of active jobs')
})

project_list_model = projects_ns.model('ProjectList', {
    'items': fields.List(fields.Nested(project_response_model), description='List of projects'),
    'total': fields.Integer(required=True, description='Total number of projects'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})

# Member models
member_add_model = projects_ns.model('MemberAdd', {
    'user_id': fields.String(required=True, description='User ID to add'),
    'role': fields.String(required=True, description='Role (owner, administrator, developer, viewer)')
})

member_update_model = projects_ns.model('MemberUpdate', {
    'role': fields.String(required=True, description='New role (owner, administrator, developer, viewer)')
})

member_response_model = projects_ns.model('MemberResponse', {
    'user_id': fields.String(required=True, description='User ID'),
    'username': fields.String(required=True, description='Username'),
    'display_name': fields.String(description='Display name'),
    'role': fields.String(required=True, description='Role'),
    'joined_at': fields.DateTime(description='Join timestamp')
})

member_list_model = projects_ns.model('MemberList', {
    'items': fields.List(fields.Nested(member_response_model), description='List of members'),
    'total': fields.Integer(required=True, description='Total number of members'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})

# Resource assignment models
resource_assign_model = projects_ns.model('ResourceAssign', {
    'resource_id': fields.Integer(required=True, description='Resource ID to assign')
})

assigned_resource_model = projects_ns.model('AssignedResource', {
    'resource_id': fields.Integer(required=True, description='Resource ID'),
    'resource_name': fields.String(required=True, description='Resource name'),
    'resource_type': fields.String(required=True, description='Resource type'),
    'pool_id': fields.Integer(description='Pool ID'),
    'pool_name': fields.String(description='Pool name'),
    'health_status': fields.String(description='Health status'),
    'current_allocations': fields.Integer(description='Current allocations'),
    'capacity': fields.Integer(description='Capacity'),
    'assigned_at': fields.DateTime(description='Assignment timestamp')
})

assigned_resource_list_model = projects_ns.model('AssignedResourceList', {
    'items': fields.List(fields.Nested(assigned_resource_model), description='List of assigned resources'),
    'total': fields.Integer(required=True, description='Total number of resources'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})

# Variable models
variable_create_model = projects_ns.model('VariableCreate', {
    'name': fields.String(required=True, description='Variable name'),
    'value': fields.Raw(required=True, description='Variable value'),
    'var_type': fields.String(required=True, description='Variable type (string, integer, float, boolean, json)'),
    'is_sensitive': fields.Boolean(description='Whether value is sensitive'),
    'description': fields.String(description='Variable description')
})

variable_update_model = projects_ns.model('VariableUpdate', {
    'value': fields.Raw(required=True, description='New variable value'),
    'description': fields.String(description='Variable description')
})

variable_response_model = projects_ns.model('VariableResponse', {
    'id': fields.Integer(required=True, description='Variable ID'),
    'name': fields.String(required=True, description='Variable name'),
    'value': fields.Raw(description='Variable value (masked if sensitive)'),
    'var_type': fields.String(required=True, description='Variable type'),
    'is_sensitive': fields.Boolean(required=True, description='Whether value is sensitive'),
    'description': fields.String(description='Variable description'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'updated_at': fields.DateTime(description='Last update timestamp')
})

variable_list_model = projects_ns.model('VariableList', {
    'items': fields.List(fields.Nested(variable_response_model), description='List of variables'),
    'total': fields.Integer(required=True, description='Total number of variables'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})


# =============================================================================
# Helper Functions
# =============================================================================

def project_response_to_dict(project_response):
    """Convert ProjectResponse dataclass to dict."""
    return {
        'id': project_response.id,
        'name': project_response.name,
        'description': project_response.description,
        'owner_id': project_response.owner_id,
        'owner_username': project_response.owner_username,
        'metadata': project_response.metadata,
        'created_at': project_response.created_at.isoformat() if project_response.created_at else None,
        'updated_at': project_response.updated_at.isoformat() if project_response.updated_at else None,
        'last_activity_at': project_response.last_activity_at.isoformat() if project_response.last_activity_at else None,
        'member_count': project_response.member_count,
        'repository_count': project_response.repository_count,
        'active_jobs': project_response.active_jobs
    }


def member_response_to_dict(member_response):
    """Convert ProjectMemberResponse dataclass to dict."""
    return {
        'user_id': member_response.user_id,
        'username': member_response.username,
        'display_name': member_response.display_name,
        'role': member_response.role.value if hasattr(member_response.role, 'value') else member_response.role,
        'joined_at': member_response.joined_at.isoformat() if member_response.joined_at else None
    }


def assigned_resource_to_dict(resource_response):
    """Convert AssignedResourceResponse dataclass to dict."""
    return {
        'resource_id': resource_response.resource_id,
        'resource_name': resource_response.resource_name,
        'resource_type': resource_response.resource_type,
        'pool_id': resource_response.pool_id,
        'pool_name': resource_response.pool_name,
        'health_status': resource_response.health_status,
        'current_allocations': resource_response.current_allocations,
        'capacity': resource_response.capacity,
        'assigned_at': resource_response.assigned_at.isoformat() if resource_response.assigned_at else None
    }


def variable_response_to_dict(variable_response):
    """Convert ProjectVariableResponse dataclass to dict."""
    return {
        'id': variable_response.id,
        'name': variable_response.name,
        'value': variable_response.value,
        'var_type': variable_response.var_type,
        'is_sensitive': variable_response.is_sensitive,
        'description': variable_response.description,
        'created_at': variable_response.created_at.isoformat() if variable_response.created_at else None,
        'updated_at': variable_response.updated_at.isoformat() if variable_response.updated_at else None
    }


def check_project_permission(project_id: int, permission: str):
    """
    Check if current user has permission on project.
    
    :param project_id: The project ID
    :param permission: The permission to check
    :raises AuthorizationError: If permission denied
    """
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    
    project_manager = ProjectManager(g.db_session)
    
    if not project_manager.check_permission(project_id, g.current_user_id, permission):
        raise AuthorizationError(f"Permission '{permission}' required for this project", permission)


# =============================================================================
# Project Collection Endpoints
# =============================================================================

@projects_ns.route("/")
class ProjectCollection(Resource):
    """Project collection for listing and creating projects."""
    
    @projects_ns.doc('list_projects')
    @projects_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @projects_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @projects_ns.param('search', 'Search string for project name or description', type=str)
    @projects_ns.response(200, 'Success', project_list_model)
    @projects_ns.response(401, 'Unauthorized', error_model)
    @require_auth
    def get(self):
        """
        List projects the user has access to.
        
        Requirements: 12.1, 12.4, 12.7
        """
        try:
            offset, limit = get_pagination_params()
            search = request.args.get('search')
            
            from automojo.pychestrate.core.managers.project_manager import ProjectManager
            
            project_manager = ProjectManager(g.db_session)
            result = project_manager.list_projects(
                user_id=g.current_user_id,
                offset=offset,
                limit=limit,
                search=search
            )
            
            return paginated_response(
                items=[project_response_to_dict(p) for p in result.projects],
                total=result.total,
                offset=result.offset,
                limit=result.limit
            ), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except Exception as e:
            return exception_to_response(e)
    
    @projects_ns.doc('create_project')
    @projects_ns.expect(project_create_model)
    @projects_ns.response(201, 'Project created', project_response_model)
    @projects_ns.response(400, 'Validation error', error_model)
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(409, 'Conflict', error_model)
    @require_auth
    @require_permission('projects.create')
    def post(self):
        """
        Create a new project.
        
        Requirements: 12.1, 12.5, 12.6
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.project_manager import (
                ProjectManager,
                ProjectCreateRequest,
                ProjectValidationError,
                DuplicateProjectError
            )
            
            create_request = ProjectCreateRequest(
                name=data.get('name', ''),
                description=data.get('description', ''),
                metadata=data.get('metadata', {})
            )
            
            project_manager = ProjectManager(g.db_session)
            project_response = project_manager.create_project(
                create_request,
                user_id=g.current_user_id
            )
            
            return project_response_to_dict(project_response), 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@projects_ns.route("/<int:project_id>")
@projects_ns.param('project_id', 'The project identifier')
class ProjectItem(Resource):
    """Individual project for get, update, and delete operations."""
    
    @projects_ns.doc('get_project')
    @projects_ns.response(200, 'Success', project_response_model)
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id):
        """
        Get a project by ID.
        
        Requirements: 12.1
        """
        try:
            check_project_permission(project_id, 'project.read')
            
            from automojo.pychestrate.core.managers.project_manager import ProjectManager
            
            project_manager = ProjectManager(g.db_session)
            project_response = project_manager.get_project(project_id)
            
            if project_response is None:
                return not_found_error('Project', str(project_id))
            
            return project_response_to_dict(project_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @projects_ns.doc('update_project')
    @projects_ns.expect(project_update_model)
    @projects_ns.response(200, 'Project updated', project_response_model)
    @projects_ns.response(400, 'Validation error', error_model)
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @projects_ns.response(409, 'Conflict', error_model)
    @require_auth
    def put(self, project_id):
        """
        Update a project.
        
        Requirements: 12.1, 12.5, 12.6
        """
        try:
            check_project_permission(project_id, 'project.update')
            
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.project_manager import (
                ProjectManager,
                ProjectUpdateRequest,
                ProjectValidationError,
                ProjectNotFoundError,
                DuplicateProjectError
            )
            
            update_request = ProjectUpdateRequest(
                name=data.get('name'),
                description=data.get('description'),
                metadata=data.get('metadata')
            )
            
            project_manager = ProjectManager(g.db_session)
            project_response = project_manager.update_project(
                project_id,
                update_request,
                user_id=g.current_user_id
            )
            
            return project_response_to_dict(project_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @projects_ns.doc('delete_project')
    @projects_ns.response(204, 'Project deleted')
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @projects_ns.response(409, 'Conflict - project has active jobs', error_model)
    @require_auth
    def delete(self, project_id):
        """
        Delete a project.
        
        Requirements: 12.1, 12.6
        """
        try:
            check_project_permission(project_id, 'project.delete')
            
            from automojo.pychestrate.core.managers.project_manager import (
                ProjectManager,
                ProjectNotFoundError,
                ProjectHasActiveJobsError
            )
            
            project_manager = ProjectManager(g.db_session)
            project_manager.delete_project(project_id, user_id=g.current_user_id)
            
            return '', 204
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Member Endpoints
# =============================================================================

@projects_ns.route("/<int:project_id>/members")
@projects_ns.param('project_id', 'The project identifier')
class ProjectMemberCollection(Resource):
    """Project member collection for listing and adding members."""
    
    @projects_ns.doc('list_members')
    @projects_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @projects_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @projects_ns.response(200, 'Success', member_list_model)
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id):
        """
        List project members.
        
        Requirements: 12.1, 12.4
        """
        try:
            check_project_permission(project_id, 'member.read')
            
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.project_manager import ProjectManager
            
            project_manager = ProjectManager(g.db_session)
            result = project_manager.list_members(
                project_id=project_id,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[member_response_to_dict(m) for m in result.members],
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
    
    @projects_ns.doc('add_member')
    @projects_ns.expect(member_add_model)
    @projects_ns.response(201, 'Member added', member_response_model)
    @projects_ns.response(400, 'Validation error', error_model)
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @projects_ns.response(409, 'Conflict', error_model)
    @require_auth
    def post(self, project_id):
        """
        Add a member to the project.
        
        Requirements: 12.1, 12.5, 12.6
        """
        try:
            check_project_permission(project_id, 'member.add')
            
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.project_manager import (
                ProjectManager,
                ProjectRole,
                ProjectNotFoundError,
                DuplicateMemberError,
                ProjectValidationError
            )
            
            user_id = data.get('user_id')
            role_str = data.get('role', '').lower()
            
            if not user_id:
                return validation_error("user_id is required", field="user_id")
            
            try:
                role = ProjectRole(role_str)
            except ValueError:
                return validation_error(
                    f"Invalid role: {role_str}. Must be one of: owner, administrator, developer, viewer",
                    field="role"
                )
            
            project_manager = ProjectManager(g.db_session)
            member_response = project_manager.add_member(
                project_id=project_id,
                user_id=user_id,
                role=role,
                added_by=g.current_user_id
            )
            
            return member_response_to_dict(member_response), 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@projects_ns.route("/<int:project_id>/members/<string:user_id>")
@projects_ns.param('project_id', 'The project identifier')
@projects_ns.param('user_id', 'The user identifier')
class ProjectMemberItem(Resource):
    """Individual project member for update and delete operations."""
    
    @projects_ns.doc('update_member_role')
    @projects_ns.expect(member_update_model)
    @projects_ns.response(200, 'Member updated', member_response_model)
    @projects_ns.response(400, 'Validation error', error_model)
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @require_auth
    def put(self, project_id, user_id):
        """
        Update a member's role.
        
        Requirements: 12.1, 12.5
        """
        try:
            check_project_permission(project_id, 'member.update')
            
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.project_manager import (
                ProjectManager,
                ProjectRole,
                ProjectNotFoundError,
                MemberNotFoundError,
                ProjectValidationError
            )
            
            role_str = data.get('role', '').lower()
            
            try:
                role = ProjectRole(role_str)
            except ValueError:
                return validation_error(
                    f"Invalid role: {role_str}. Must be one of: owner, administrator, developer, viewer",
                    field="role"
                )
            
            project_manager = ProjectManager(g.db_session)
            member_response = project_manager.update_member_role(
                project_id=project_id,
                user_id=user_id,
                role=role,
                updated_by=g.current_user_id
            )
            
            return member_response_to_dict(member_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @projects_ns.doc('remove_member')
    @projects_ns.response(204, 'Member removed')
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, user_id):
        """
        Remove a member from the project.
        
        Requirements: 12.1, 12.6
        """
        try:
            check_project_permission(project_id, 'member.remove')
            
            from automojo.pychestrate.core.managers.project_manager import (
                ProjectManager,
                ProjectNotFoundError,
                MemberNotFoundError,
                ProjectValidationError
            )
            
            project_manager = ProjectManager(g.db_session)
            project_manager.remove_member(
                project_id=project_id,
                user_id=user_id,
                removed_by=g.current_user_id
            )
            
            return '', 204
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Resource Assignment Endpoints
# =============================================================================

@projects_ns.route("/<int:project_id>/resources")
@projects_ns.param('project_id', 'The project identifier')
class ProjectResourceCollection(Resource):
    """Project resource collection for listing and assigning resources."""
    
    @projects_ns.doc('list_assigned_resources')
    @projects_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @projects_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @projects_ns.response(200, 'Success', assigned_resource_list_model)
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id):
        """
        List resources assigned to the project.
        
        Requirements: 12.1, 12.4
        """
        try:
            check_project_permission(project_id, 'resource.read')
            
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.project_manager import ProjectManager
            
            project_manager = ProjectManager(g.db_session)
            result = project_manager.list_assigned_resources(
                project_id=project_id,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[assigned_resource_to_dict(r) for r in result.resources],
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
    
    @projects_ns.doc('assign_resource')
    @projects_ns.expect(resource_assign_model)
    @projects_ns.response(201, 'Resource assigned')
    @projects_ns.response(400, 'Validation error', error_model)
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @projects_ns.response(409, 'Conflict', error_model)
    @require_auth
    def post(self, project_id):
        """
        Assign a resource to the project.
        
        Requirements: 12.1, 12.5, 12.6
        """
        try:
            check_project_permission(project_id, 'resource.assign')
            
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.project_manager import (
                ProjectManager,
                ProjectNotFoundError,
                ResourceNotFoundError,
                ResourceAlreadyAssignedError
            )
            
            resource_id = data.get('resource_id')
            
            if not resource_id:
                return validation_error("resource_id is required", field="resource_id")
            
            project_manager = ProjectManager(g.db_session)
            project_manager.assign_resource(
                project_id=project_id,
                resource_id=resource_id,
                user_id=g.current_user_id
            )
            
            return {'message': 'Resource assigned successfully'}, 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@projects_ns.route("/<int:project_id>/resources/<int:resource_id>")
@projects_ns.param('project_id', 'The project identifier')
@projects_ns.param('resource_id', 'The resource identifier')
class ProjectResourceItem(Resource):
    """Individual project resource for unassignment."""
    
    @projects_ns.doc('unassign_resource')
    @projects_ns.response(204, 'Resource unassigned')
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, resource_id):
        """
        Unassign a resource from the project.
        
        Requirements: 12.1, 12.6
        """
        try:
            check_project_permission(project_id, 'resource.unassign')
            
            from automojo.pychestrate.core.managers.project_manager import (
                ProjectManager,
                ProjectNotFoundError,
                ResourceNotAssignedError
            )
            
            project_manager = ProjectManager(g.db_session)
            project_manager.unassign_resource(
                project_id=project_id,
                resource_id=resource_id,
                user_id=g.current_user_id
            )
            
            return '', 204
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Variable Endpoints
# =============================================================================

@projects_ns.route("/<int:project_id>/variables")
@projects_ns.param('project_id', 'The project identifier')
class ProjectVariableCollection(Resource):
    """Project variable collection for listing and creating variables."""
    
    @projects_ns.doc('list_variables')
    @projects_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @projects_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @projects_ns.response(200, 'Success', variable_list_model)
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id):
        """
        List project variables.
        
        Requirements: 12.1, 12.4
        """
        try:
            check_project_permission(project_id, 'variable.read')
            
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.project_manager import ProjectManager
            
            project_manager = ProjectManager(g.db_session)
            result = project_manager.list_variables(
                project_id=project_id,
                include_sensitive=False,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[variable_response_to_dict(v) for v in result.variables],
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
    
    @projects_ns.doc('create_variable')
    @projects_ns.expect(variable_create_model)
    @projects_ns.response(201, 'Variable created', variable_response_model)
    @projects_ns.response(400, 'Validation error', error_model)
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @projects_ns.response(409, 'Conflict', error_model)
    @require_auth
    def post(self, project_id):
        """
        Create a project variable.
        
        Requirements: 12.1, 12.5, 12.6
        """
        try:
            check_project_permission(project_id, 'variable.create')
            
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.project_manager import (
                ProjectManager,
                ProjectVariableCreateRequest,
                ProjectNotFoundError,
                DuplicateVariableError,
                ProjectValidationError,
                TypeValidationError
            )
            
            create_request = ProjectVariableCreateRequest(
                name=data.get('name', ''),
                value=data.get('value'),
                var_type=data.get('var_type', 'string'),
                is_sensitive=data.get('is_sensitive', False),
                description=data.get('description', '')
            )
            
            project_manager = ProjectManager(g.db_session)
            variable_response = project_manager.create_variable(
                project_id=project_id,
                request=create_request,
                user_id=g.current_user_id
            )
            
            return variable_response_to_dict(variable_response), 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@projects_ns.route("/<int:project_id>/variables/<int:variable_id>")
@projects_ns.param('project_id', 'The project identifier')
@projects_ns.param('variable_id', 'The variable identifier')
class ProjectVariableItem(Resource):
    """Individual project variable for update and delete operations."""
    
    @projects_ns.doc('update_variable')
    @projects_ns.expect(variable_update_model)
    @projects_ns.response(200, 'Variable updated', variable_response_model)
    @projects_ns.response(400, 'Validation error', error_model)
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @require_auth
    def put(self, project_id, variable_id):
        """
        Update a project variable.
        
        Requirements: 12.1, 12.5
        """
        try:
            check_project_permission(project_id, 'variable.update')
            
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.project_manager import (
                ProjectManager,
                ProjectVariableUpdateRequest,
                ProjectNotFoundError,
                VariableNotFoundError,
                TypeValidationError
            )
            
            update_request = ProjectVariableUpdateRequest(
                value=data.get('value'),
                description=data.get('description')
            )
            
            project_manager = ProjectManager(g.db_session)
            variable_response = project_manager.update_variable(
                project_id=project_id,
                variable_id=variable_id,
                request=update_request,
                user_id=g.current_user_id
            )
            
            return variable_response_to_dict(variable_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @projects_ns.doc('delete_variable')
    @projects_ns.response(204, 'Variable deleted')
    @projects_ns.response(401, 'Unauthorized', error_model)
    @projects_ns.response(403, 'Forbidden', error_model)
    @projects_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, variable_id):
        """
        Delete a project variable.
        
        Requirements: 12.1, 12.6
        """
        try:
            check_project_permission(project_id, 'variable.delete')
            
            from automojo.pychestrate.core.managers.project_manager import (
                ProjectManager,
                ProjectNotFoundError,
                VariableNotFoundError
            )
            
            project_manager = ProjectManager(g.db_session)
            project_manager.delete_variable(
                project_id=project_id,
                variable_id=variable_id,
                user_id=g.current_user_id
            )
            
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
    Publish the projects namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (projects_ns, "".join([version_prefix, PROJECTS_NAMESPACE_PATH]))
    ]
    return ns_list
