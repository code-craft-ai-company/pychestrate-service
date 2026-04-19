"""
.. module:: repositories
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for project repository management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for project repository management:
- GET /projects/{id}/repositories - list repositories
- POST /projects/{id}/repositories - add repository
- GET /projects/{id}/repositories/{repo_id} - get repository
- PUT /projects/{id}/repositories/{repo_id} - update repository
- DELETE /projects/{id}/repositories/{repo_id} - remove repository
- POST /projects/{id}/repositories/{repo_id}/test - test connectivity
- POST /projects/{id}/repositories/{repo_id}/fetch - fetch latest

Requirements: 12.1
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import request, g
from flask_restx import Namespace, Resource, fields

from ..resources.base import (
    require_auth,
    get_pagination_params,
    paginated_response,
    error_response,
    validation_error,
    not_found_error,
    create_error_model,
    exception_to_response,
    AuthenticationError,
    AuthorizationError,
)

from .projects import check_project_permission


# =============================================================================
# Namespace Configuration
# =============================================================================

REPOSITORIES_NAMESPACE_PATH = "/projects"

repositories_ns = Namespace(
    "Project Repositories v1",
    description="Project repository management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(repositories_ns)

repository_create_model = repositories_ns.model('RepositoryCreate', {
    'name': fields.String(required=True, description='Repository name'),
    'url': fields.String(required=True, description='Repository URL'),
    'auth_type': fields.String(required=True, description='Authentication type (https_token, ssh_key, none)'),
    'credential_secret_ref': fields.String(description='Secret reference for credentials'),
    'default_branch': fields.String(description='Default branch (default: main)'),
    'description': fields.String(description='Repository description')
})

repository_update_model = repositories_ns.model('RepositoryUpdate', {
    'name': fields.String(description='Repository name'),
    'credential_secret_ref': fields.String(description='Secret reference for credentials'),
    'default_branch': fields.String(description='Default branch'),
    'description': fields.String(description='Repository description')
})

repository_response_model = repositories_ns.model('RepositoryResponse', {
    'id': fields.Integer(required=True, description='Repository ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'name': fields.String(required=True, description='Repository name'),
    'url': fields.String(required=True, description='Repository URL'),
    'auth_type': fields.String(required=True, description='Authentication type'),
    'default_branch': fields.String(description='Default branch'),
    'description': fields.String(description='Repository description'),
    'last_commit_sha': fields.String(description='Last commit SHA'),
    'last_commit_message': fields.String(description='Last commit message'),
    'last_commit_author': fields.String(description='Last commit author'),
    'last_commit_time': fields.DateTime(description='Last commit time'),
    'last_fetch_time': fields.DateTime(description='Last fetch time'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

repository_list_model = repositories_ns.model('RepositoryList', {
    'items': fields.List(fields.Nested(repository_response_model), description='List of repositories'),
    'total': fields.Integer(required=True, description='Total number of repositories'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})

connectivity_result_model = repositories_ns.model('ConnectivityResult', {
    'success': fields.Boolean(required=True, description='Whether connectivity test succeeded'),
    'message': fields.String(description='Result message')
})

branch_response_model = repositories_ns.model('BranchResponse', {
    'name': fields.String(required=True, description='Branch name'),
    'commit_sha': fields.String(description='Commit SHA'),
    'commit_message': fields.String(description='Commit message'),
    'commit_author': fields.String(description='Commit author'),
    'commit_time': fields.DateTime(description='Commit time')
})


# =============================================================================
# Helper Functions
# =============================================================================

def repository_response_to_dict(repo_response):
    """Convert RepositoryResponse dataclass to dict."""
    return {
        'id': repo_response.id,
        'project_id': repo_response.project_id,
        'name': repo_response.name,
        'url': repo_response.url,
        'auth_type': repo_response.auth_type.value if hasattr(repo_response.auth_type, 'value') else repo_response.auth_type,
        'default_branch': repo_response.default_branch,
        'description': repo_response.description,
        'last_commit_sha': repo_response.last_commit_sha,
        'last_commit_message': repo_response.last_commit_message,
        'last_commit_author': repo_response.last_commit_author,
        'last_commit_time': repo_response.last_commit_time.isoformat() if repo_response.last_commit_time else None,
        'last_fetch_time': repo_response.last_fetch_time.isoformat() if repo_response.last_fetch_time else None,
        'created_at': repo_response.created_at.isoformat() if repo_response.created_at else None
    }


# =============================================================================
# Repository Endpoints
# =============================================================================

@repositories_ns.route("/<int:project_id>/repositories")
@repositories_ns.param('project_id', 'The project identifier')
class RepositoryCollection(Resource):
    """Repository collection for listing and adding repositories."""
    
    @repositories_ns.doc('list_repositories')
    @repositories_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @repositories_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @repositories_ns.response(200, 'Success', repository_list_model)
    @repositories_ns.response(401, 'Unauthorized', error_model)
    @repositories_ns.response(403, 'Forbidden', error_model)
    @repositories_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id):
        """
        List repositories in the project.
        
        Requirements: 12.1, 12.4
        """
        try:
            check_project_permission(project_id, 'repository.read')
            
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.repository_manager import RepositoryManager
            
            repository_manager = RepositoryManager(g.db_session)
            result = repository_manager.list_repositories(
                project_id=project_id,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[repository_response_to_dict(r) for r in result.repositories],
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
    
    @repositories_ns.doc('add_repository')
    @repositories_ns.expect(repository_create_model)
    @repositories_ns.response(201, 'Repository added', repository_response_model)
    @repositories_ns.response(400, 'Validation error', error_model)
    @repositories_ns.response(401, 'Unauthorized', error_model)
    @repositories_ns.response(403, 'Forbidden', error_model)
    @repositories_ns.response(404, 'Not found', error_model)
    @repositories_ns.response(409, 'Conflict', error_model)
    @require_auth
    def post(self, project_id):
        """
        Add a repository to the project.
        
        Requirements: 12.1, 12.5, 12.6
        """
        try:
            check_project_permission(project_id, 'repository.add')
            
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.repository_manager import (
                RepositoryManager,
                RepositoryCreateRequest,
                RepositoryAuthType,
                RepositoryValidationError,
                DuplicateRepositoryError,
                ProjectNotFoundError
            )
            
            auth_type_str = data.get('auth_type', 'none').lower()
            try:
                auth_type = RepositoryAuthType(auth_type_str)
            except ValueError:
                return validation_error(
                    f"Invalid auth_type: {auth_type_str}. Must be one of: https_token, ssh_key, none",
                    field="auth_type"
                )
            
            create_request = RepositoryCreateRequest(
                name=data.get('name', ''),
                url=data.get('url', ''),
                auth_type=auth_type,
                credential_secret_ref=data.get('credential_secret_ref'),
                default_branch=data.get('default_branch', 'main'),
                description=data.get('description', '')
            )
            
            repository_manager = RepositoryManager(g.db_session)
            repo_response = repository_manager.add_repository(
                project_id=project_id,
                request=create_request,
                user_id=g.current_user_id
            )
            
            return repository_response_to_dict(repo_response), 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@repositories_ns.route("/<int:project_id>/repositories/<int:repository_id>")
@repositories_ns.param('project_id', 'The project identifier')
@repositories_ns.param('repository_id', 'The repository identifier')
class RepositoryItem(Resource):
    """Individual repository for get, update, and delete operations."""
    
    @repositories_ns.doc('get_repository')
    @repositories_ns.response(200, 'Success', repository_response_model)
    @repositories_ns.response(401, 'Unauthorized', error_model)
    @repositories_ns.response(403, 'Forbidden', error_model)
    @repositories_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, repository_id):
        """
        Get a repository by ID.
        
        Requirements: 12.1
        """
        try:
            check_project_permission(project_id, 'repository.read')
            
            from automojo.pychestrate.core.managers.repository_manager import RepositoryManager
            
            repository_manager = RepositoryManager(g.db_session)
            repo_response = repository_manager.get_repository(repository_id)
            
            if repo_response is None:
                return not_found_error('Repository', str(repository_id))
            
            # Verify repository belongs to project
            if repo_response.project_id != project_id:
                return not_found_error('Repository', str(repository_id))
            
            return repository_response_to_dict(repo_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @repositories_ns.doc('update_repository')
    @repositories_ns.expect(repository_update_model)
    @repositories_ns.response(200, 'Repository updated', repository_response_model)
    @repositories_ns.response(400, 'Validation error', error_model)
    @repositories_ns.response(401, 'Unauthorized', error_model)
    @repositories_ns.response(403, 'Forbidden', error_model)
    @repositories_ns.response(404, 'Not found', error_model)
    @require_auth
    def put(self, project_id, repository_id):
        """
        Update a repository.
        
        Requirements: 12.1, 12.5
        """
        try:
            check_project_permission(project_id, 'repository.update')
            
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.repository_manager import (
                RepositoryManager,
                RepositoryUpdateRequest,
                RepositoryValidationError,
                RepositoryNotFoundError
            )
            
            update_request = RepositoryUpdateRequest(
                name=data.get('name'),
                credential_secret_ref=data.get('credential_secret_ref'),
                default_branch=data.get('default_branch'),
                description=data.get('description')
            )
            
            repository_manager = RepositoryManager(g.db_session)
            repo_response = repository_manager.update_repository(
                repository_id=repository_id,
                request=update_request,
                user_id=g.current_user_id
            )
            
            return repository_response_to_dict(repo_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @repositories_ns.doc('remove_repository')
    @repositories_ns.response(204, 'Repository removed')
    @repositories_ns.response(401, 'Unauthorized', error_model)
    @repositories_ns.response(403, 'Forbidden', error_model)
    @repositories_ns.response(404, 'Not found', error_model)
    @repositories_ns.response(409, 'Conflict - repository has references', error_model)
    @require_auth
    def delete(self, project_id, repository_id):
        """
        Remove a repository from the project.
        
        Requirements: 12.1, 12.6
        """
        try:
            check_project_permission(project_id, 'repository.remove')
            
            from automojo.pychestrate.core.managers.repository_manager import (
                RepositoryManager,
                RepositoryNotFoundError,
                RepositoryHasReferencesError
            )
            
            repository_manager = RepositoryManager(g.db_session)
            repository_manager.remove_repository(
                repository_id=repository_id,
                user_id=g.current_user_id
            )
            
            return '', 204
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@repositories_ns.route("/<int:project_id>/repositories/<int:repository_id>/test")
@repositories_ns.param('project_id', 'The project identifier')
@repositories_ns.param('repository_id', 'The repository identifier')
class RepositoryConnectivityTest(Resource):
    """Repository connectivity test endpoint."""
    
    @repositories_ns.doc('test_connectivity')
    @repositories_ns.response(200, 'Success', connectivity_result_model)
    @repositories_ns.response(401, 'Unauthorized', error_model)
    @repositories_ns.response(403, 'Forbidden', error_model)
    @repositories_ns.response(404, 'Not found', error_model)
    @require_auth
    def post(self, project_id, repository_id):
        """
        Test repository connectivity.
        
        Requirements: 12.1
        """
        try:
            check_project_permission(project_id, 'repository.read')
            
            from automojo.pychestrate.core.managers.repository_manager import (
                RepositoryManager,
                RepositoryNotFoundError,
                RepositoryConnectivityError
            )
            
            repository_manager = RepositoryManager(g.db_session)
            
            try:
                success = repository_manager.test_connectivity(repository_id)
                return {
                    'success': success,
                    'message': 'Connectivity test passed' if success else 'Connectivity test failed'
                }, 200
            except RepositoryConnectivityError as e:
                return {
                    'success': False,
                    'message': str(e)
                }, 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@repositories_ns.route("/<int:project_id>/repositories/<int:repository_id>/fetch")
@repositories_ns.param('project_id', 'The project identifier')
@repositories_ns.param('repository_id', 'The repository identifier')
class RepositoryFetch(Resource):
    """Repository fetch endpoint."""
    
    @repositories_ns.doc('fetch_latest')
    @repositories_ns.response(200, 'Success', repository_response_model)
    @repositories_ns.response(401, 'Unauthorized', error_model)
    @repositories_ns.response(403, 'Forbidden', error_model)
    @repositories_ns.response(404, 'Not found', error_model)
    @require_auth
    def post(self, project_id, repository_id):
        """
        Fetch latest commit information from repository.
        
        Requirements: 12.1
        """
        try:
            check_project_permission(project_id, 'repository.read')
            
            from automojo.pychestrate.core.managers.repository_manager import (
                RepositoryManager,
                RepositoryNotFoundError,
                RepositoryConnectivityError
            )
            
            repository_manager = RepositoryManager(g.db_session)
            repo_response = repository_manager.fetch_latest(repository_id)
            
            return repository_response_to_dict(repo_response), 200
            
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
    Publish the repositories namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (repositories_ns, "".join([version_prefix, REPOSITORIES_NAMESPACE_PATH]))
    ]
    return ns_list
