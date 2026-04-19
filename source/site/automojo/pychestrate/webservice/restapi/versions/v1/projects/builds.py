"""
.. module:: builds
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for project build management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for project build management:
- Build specification CRUD endpoints
- Build execution endpoints
- Build artifact endpoints

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

BUILDS_NAMESPACE_PATH = "/projects"

builds_ns = Namespace(
    "Project Builds v1",
    description="Project build management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(builds_ns)

build_step_model = builds_ns.model('BuildStep', {
    'name': fields.String(required=True, description='Step name'),
    'type': fields.String(required=True, description='Step type (checkout, script, artifact, notification)'),
    'config': fields.Raw(required=True, description='Step configuration'),
    'continue_on_failure': fields.Boolean(description='Continue on failure')
})

build_spec_create_model = builds_ns.model('BuildSpecCreate', {
    'name': fields.String(required=True, description='Specification name'),
    'repository_id': fields.Integer(required=True, description='Repository ID'),
    'branch': fields.String(description='Branch to build (default: main)'),
    'steps': fields.List(fields.Nested(build_step_model), description='Build steps'),
    'environment': fields.Raw(description='Environment variables'),
    'timeout_minutes': fields.Integer(description='Timeout in minutes'),
    'description': fields.String(description='Specification description')
})

build_spec_response_model = builds_ns.model('BuildSpecResponse', {
    'id': fields.Integer(required=True, description='Specification ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'name': fields.String(required=True, description='Specification name'),
    'repository_id': fields.Integer(description='Repository ID'),
    'repository_name': fields.String(description='Repository name'),
    'branch': fields.String(description='Branch'),
    'steps': fields.List(fields.Nested(build_step_model), description='Build steps'),
    'environment': fields.Raw(description='Environment variables'),
    'timeout_minutes': fields.Integer(description='Timeout in minutes'),
    'description': fields.String(description='Description'),
    'version': fields.Integer(description='Specification version'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'updated_at': fields.DateTime(description='Last update timestamp')
})

build_spec_list_model = builds_ns.model('BuildSpecList', {
    'items': fields.List(fields.Nested(build_spec_response_model), description='List of specifications'),
    'total': fields.Integer(required=True, description='Total number of specifications'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})

build_trigger_model = builds_ns.model('BuildTrigger', {
    'spec_id': fields.Integer(required=True, description='Build specification ID'),
    'branch': fields.String(description='Branch override'),
    'commit_sha': fields.String(description='Specific commit SHA'),
    'parameters': fields.Raw(description='Build parameters')
})

build_response_model = builds_ns.model('BuildResponse', {
    'id': fields.Integer(required=True, description='Build ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'spec_id': fields.Integer(required=True, description='Specification ID'),
    'spec_name': fields.String(description='Specification name'),
    'spec_version': fields.Integer(description='Specification version'),
    'repository_name': fields.String(description='Repository name'),
    'branch': fields.String(description='Branch'),
    'commit_sha': fields.String(description='Commit SHA'),
    'commit_message': fields.String(description='Commit message'),
    'status': fields.String(required=True, description='Build status'),
    'trigger_type': fields.String(description='Trigger type'),
    'triggered_by_id': fields.String(description='Triggered by user ID'),
    'triggered_by_username': fields.String(description='Triggered by username'),
    'started_at': fields.DateTime(description='Start timestamp'),
    'completed_at': fields.DateTime(description='Completion timestamp'),
    'duration_seconds': fields.Integer(description='Duration in seconds'),
    'artifact_count': fields.Integer(description='Number of artifacts'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

build_list_model = builds_ns.model('BuildList', {
    'items': fields.List(fields.Nested(build_response_model), description='List of builds'),
    'total': fields.Integer(required=True, description='Total number of builds'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})

build_artifact_model = builds_ns.model('BuildArtifact', {
    'id': fields.Integer(required=True, description='Artifact ID'),
    'build_id': fields.Integer(required=True, description='Build ID'),
    'name': fields.String(required=True, description='Artifact name'),
    'path': fields.String(description='Artifact path'),
    'size_bytes': fields.Integer(description='Size in bytes'),
    'checksum': fields.String(description='Checksum'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

build_artifact_list_model = builds_ns.model('BuildArtifactList', {
    'items': fields.List(fields.Nested(build_artifact_model), description='List of artifacts'),
    'total': fields.Integer(required=True, description='Total number of artifacts'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})


# =============================================================================
# Helper Functions
# =============================================================================

def build_spec_to_dict(spec_response):
    """Convert BuildSpecResponse dataclass to dict."""
    steps = []
    if spec_response.steps:
        for step in spec_response.steps:
            if hasattr(step, '__dict__'):
                steps.append({
                    'name': step.name,
                    'type': step.type,
                    'config': step.config,
                    'continue_on_failure': getattr(step, 'continue_on_failure', False)
                })
            else:
                steps.append(step)
    
    return {
        'id': spec_response.id,
        'project_id': spec_response.project_id,
        'name': spec_response.name,
        'repository_id': spec_response.repository_id,
        'repository_name': spec_response.repository_name,
        'branch': spec_response.branch,
        'steps': steps,
        'environment': spec_response.environment,
        'timeout_minutes': spec_response.timeout_minutes,
        'description': spec_response.description,
        'version': spec_response.version,
        'created_at': spec_response.created_at.isoformat() if spec_response.created_at else None,
        'updated_at': spec_response.updated_at.isoformat() if spec_response.updated_at else None
    }


def build_to_dict(build_response):
    """Convert BuildResponse dataclass to dict."""
    return {
        'id': build_response.id,
        'project_id': build_response.project_id,
        'spec_id': build_response.spec_id,
        'spec_name': build_response.spec_name,
        'spec_version': build_response.spec_version,
        'repository_name': build_response.repository_name,
        'branch': build_response.branch,
        'commit_sha': build_response.commit_sha,
        'commit_message': build_response.commit_message,
        'status': build_response.status.value if hasattr(build_response.status, 'value') else build_response.status,
        'trigger_type': build_response.trigger_type.value if hasattr(build_response.trigger_type, 'value') else build_response.trigger_type,
        'triggered_by_id': str(build_response.triggered_by_id) if build_response.triggered_by_id else None,
        'triggered_by_username': build_response.triggered_by_username,
        'started_at': build_response.started_at.isoformat() if build_response.started_at else None,
        'completed_at': build_response.completed_at.isoformat() if build_response.completed_at else None,
        'duration_seconds': build_response.duration_seconds,
        'artifact_count': build_response.artifact_count,
        'created_at': build_response.created_at.isoformat() if build_response.created_at else None
    }


def artifact_to_dict(artifact_response):
    """Convert BuildArtifactResponse dataclass to dict."""
    return {
        'id': artifact_response.id,
        'build_id': artifact_response.build_id,
        'name': artifact_response.name,
        'path': artifact_response.path,
        'size_bytes': artifact_response.size_bytes,
        'checksum': artifact_response.checksum,
        'created_at': artifact_response.created_at.isoformat() if artifact_response.created_at else None
    }


# =============================================================================
# Build Specification Endpoints
# =============================================================================

@builds_ns.route("/<int:project_id>/build-specs")
@builds_ns.param('project_id', 'The project identifier')
class BuildSpecCollection(Resource):
    """Build specification collection for listing and creating specs."""
    
    @builds_ns.doc('list_build_specs')
    @builds_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @builds_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @builds_ns.response(200, 'Success', build_spec_list_model)
    @builds_ns.response(401, 'Unauthorized', error_model)
    @builds_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def get(self, project_id):
        """List build specifications in the project."""
        try:
            check_project_permission(project_id, 'build.read')
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.build_manager import BuildManager
            
            build_manager = BuildManager(g.db_session)
            result = build_manager.list_specs(project_id=project_id, offset=offset, limit=limit)
            
            return paginated_response(
                items=[build_spec_to_dict(s) for s in result.specs],
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
    
    @builds_ns.doc('create_build_spec')
    @builds_ns.expect(build_spec_create_model)
    @builds_ns.response(201, 'Specification created', build_spec_response_model)
    @builds_ns.response(400, 'Validation error', error_model)
    @builds_ns.response(401, 'Unauthorized', error_model)
    @builds_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def post(self, project_id):
        """Create a build specification."""
        try:
            check_project_permission(project_id, 'build.create')
            data = request.json
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.build_manager import (
                BuildManager, BuildSpecCreateRequest, BuildStepDefinition
            )
            
            steps = []
            for step_data in data.get('steps', []):
                steps.append(BuildStepDefinition(
                    name=step_data.get('name', ''),
                    type=step_data.get('type', ''),
                    config=step_data.get('config', {}),
                    continue_on_failure=step_data.get('continue_on_failure', False)
                ))
            
            create_request = BuildSpecCreateRequest(
                name=data.get('name', ''),
                repository_id=data.get('repository_id'),
                branch=data.get('branch', 'main'),
                steps=steps,
                environment=data.get('environment', {}),
                timeout_minutes=data.get('timeout_minutes', 60),
                description=data.get('description', '')
            )
            
            build_manager = BuildManager(g.db_session)
            spec_response = build_manager.create_spec(project_id, create_request, g.current_user_id)
            
            return build_spec_to_dict(spec_response), 201
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@builds_ns.route("/<int:project_id>/build-specs/<int:spec_id>")
@builds_ns.param('project_id', 'The project identifier')
@builds_ns.param('spec_id', 'The specification identifier')
class BuildSpecItem(Resource):
    """Individual build specification for get, update, and delete."""
    
    @builds_ns.doc('get_build_spec')
    @builds_ns.response(200, 'Success', build_spec_response_model)
    @builds_ns.response(401, 'Unauthorized', error_model)
    @builds_ns.response(403, 'Forbidden', error_model)
    @builds_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, spec_id):
        """Get a build specification by ID."""
        try:
            check_project_permission(project_id, 'build.read')
            from automojo.pychestrate.core.managers.build_manager import BuildManager
            
            build_manager = BuildManager(g.db_session)
            spec_response = build_manager.get_spec(spec_id)
            
            if spec_response is None or spec_response.project_id != project_id:
                return not_found_error('BuildSpec', str(spec_id))
            
            return build_spec_to_dict(spec_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @builds_ns.doc('update_build_spec')
    @builds_ns.expect(build_spec_create_model)
    @builds_ns.response(200, 'Specification updated', build_spec_response_model)
    @builds_ns.response(400, 'Validation error', error_model)
    @builds_ns.response(401, 'Unauthorized', error_model)
    @builds_ns.response(403, 'Forbidden', error_model)
    @builds_ns.response(404, 'Not found', error_model)
    @require_auth
    def put(self, project_id, spec_id):
        """Update a build specification (creates new version)."""
        try:
            check_project_permission(project_id, 'build.create')
            data = request.json
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.build_manager import (
                BuildManager, BuildSpecCreateRequest, BuildStepDefinition
            )
            
            steps = []
            for step_data in data.get('steps', []):
                steps.append(BuildStepDefinition(
                    name=step_data.get('name', ''),
                    type=step_data.get('type', ''),
                    config=step_data.get('config', {}),
                    continue_on_failure=step_data.get('continue_on_failure', False)
                ))
            
            update_request = BuildSpecCreateRequest(
                name=data.get('name', ''),
                repository_id=data.get('repository_id'),
                branch=data.get('branch', 'main'),
                steps=steps,
                environment=data.get('environment', {}),
                timeout_minutes=data.get('timeout_minutes', 60),
                description=data.get('description', '')
            )
            
            build_manager = BuildManager(g.db_session)
            spec_response = build_manager.update_spec(spec_id, update_request, g.current_user_id)
            
            return build_spec_to_dict(spec_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @builds_ns.doc('delete_build_spec')
    @builds_ns.response(204, 'Specification deleted')
    @builds_ns.response(401, 'Unauthorized', error_model)
    @builds_ns.response(403, 'Forbidden', error_model)
    @builds_ns.response(404, 'Not found', error_model)
    @builds_ns.response(409, 'Conflict - has active builds', error_model)
    @require_auth
    def delete(self, project_id, spec_id):
        """Delete a build specification."""
        try:
            check_project_permission(project_id, 'build.create')
            from automojo.pychestrate.core.managers.build_manager import BuildManager
            
            build_manager = BuildManager(g.db_session)
            build_manager.delete_spec(spec_id, g.current_user_id)
            
            return '', 204
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Build Execution Endpoints
# =============================================================================

@builds_ns.route("/<int:project_id>/builds")
@builds_ns.param('project_id', 'The project identifier')
class BuildCollection(Resource):
    """Build collection for listing and triggering builds."""
    
    @builds_ns.doc('list_builds')
    @builds_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @builds_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @builds_ns.param('spec_id', 'Filter by specification ID', type=int)
    @builds_ns.param('status', 'Filter by status', type=str)
    @builds_ns.response(200, 'Success', build_list_model)
    @builds_ns.response(401, 'Unauthorized', error_model)
    @builds_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def get(self, project_id):
        """List builds in the project."""
        try:
            check_project_permission(project_id, 'build.read')
            offset, limit = get_pagination_params()
            spec_id = request.args.get('spec_id', type=int)
            status = request.args.get('status')
            
            from automojo.pychestrate.core.managers.build_manager import BuildManager, JobStatus
            
            status_enum = None
            if status:
                try:
                    status_enum = JobStatus(status.lower())
                except ValueError:
                    pass
            
            build_manager = BuildManager(g.db_session)
            result = build_manager.list_builds(
                project_id=project_id, spec_id=spec_id, status=status_enum,
                offset=offset, limit=limit
            )
            
            return paginated_response(
                items=[build_to_dict(b) for b in result.builds],
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
    
    @builds_ns.doc('trigger_build')
    @builds_ns.expect(build_trigger_model)
    @builds_ns.response(201, 'Build triggered', build_response_model)
    @builds_ns.response(400, 'Validation error', error_model)
    @builds_ns.response(401, 'Unauthorized', error_model)
    @builds_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def post(self, project_id):
        """Trigger a new build."""
        try:
            check_project_permission(project_id, 'build.trigger')
            data = request.json
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.build_manager import (
                BuildManager, BuildTriggerRequest, BuildTriggerType
            )
            
            trigger_request = BuildTriggerRequest(
                spec_id=data.get('spec_id'),
                branch=data.get('branch'),
                commit_sha=data.get('commit_sha'),
                parameters=data.get('parameters', {}),
                trigger_type=BuildTriggerType.API
            )
            
            build_manager = BuildManager(g.db_session)
            build_response = build_manager.trigger_build(trigger_request, g.current_user_id)
            
            return build_to_dict(build_response), 201
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@builds_ns.route("/<int:project_id>/builds/<int:build_id>")
@builds_ns.param('project_id', 'The project identifier')
@builds_ns.param('build_id', 'The build identifier')
class BuildItem(Resource):
    """Individual build for get and cancel operations."""
    
    @builds_ns.doc('get_build')
    @builds_ns.response(200, 'Success', build_response_model)
    @builds_ns.response(401, 'Unauthorized', error_model)
    @builds_ns.response(403, 'Forbidden', error_model)
    @builds_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, build_id):
        """Get a build by ID."""
        try:
            check_project_permission(project_id, 'build.read')
            from automojo.pychestrate.core.managers.build_manager import BuildManager
            
            build_manager = BuildManager(g.db_session)
            build_response = build_manager.get_build(build_id)
            
            if build_response is None or build_response.project_id != project_id:
                return not_found_error('Build', str(build_id))
            
            return build_to_dict(build_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@builds_ns.route("/<int:project_id>/builds/<int:build_id>/cancel")
@builds_ns.param('project_id', 'The project identifier')
@builds_ns.param('build_id', 'The build identifier')
class BuildCancel(Resource):
    """Build cancel endpoint."""
    
    @builds_ns.doc('cancel_build')
    @builds_ns.response(200, 'Build cancelled', build_response_model)
    @builds_ns.response(401, 'Unauthorized', error_model)
    @builds_ns.response(403, 'Forbidden', error_model)
    @builds_ns.response(404, 'Not found', error_model)
    @require_auth
    def post(self, project_id, build_id):
        """Cancel a pending or running build."""
        try:
            check_project_permission(project_id, 'build.cancel')
            from automojo.pychestrate.core.managers.build_manager import BuildManager
            
            build_manager = BuildManager(g.db_session)
            build_response = build_manager.cancel_build(build_id, g.current_user_id)
            
            return build_to_dict(build_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@builds_ns.route("/<int:project_id>/builds/<int:build_id>/logs")
@builds_ns.param('project_id', 'The project identifier')
@builds_ns.param('build_id', 'The build identifier')
class BuildLogs(Resource):
    """Build logs endpoint."""
    
    @builds_ns.doc('get_build_logs')
    @builds_ns.param('step_name', 'Filter by step name', type=str)
    @builds_ns.response(200, 'Success')
    @builds_ns.response(401, 'Unauthorized', error_model)
    @builds_ns.response(403, 'Forbidden', error_model)
    @builds_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, build_id):
        """Get build execution logs."""
        try:
            check_project_permission(project_id, 'build.read')
            step_name = request.args.get('step_name')
            
            from automojo.pychestrate.core.managers.build_manager import BuildManager
            
            build_manager = BuildManager(g.db_session)
            logs = build_manager.get_build_logs(build_id, step_name)
            
            return {'logs': logs}, 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Build Artifact Endpoints
# =============================================================================

@builds_ns.route("/<int:project_id>/builds/<int:build_id>/artifacts")
@builds_ns.param('project_id', 'The project identifier')
@builds_ns.param('build_id', 'The build identifier')
class BuildArtifactCollection(Resource):
    """Build artifact collection."""
    
    @builds_ns.doc('list_build_artifacts')
    @builds_ns.response(200, 'Success', build_artifact_list_model)
    @builds_ns.response(401, 'Unauthorized', error_model)
    @builds_ns.response(403, 'Forbidden', error_model)
    @builds_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, build_id):
        """List artifacts produced by a build."""
        try:
            check_project_permission(project_id, 'build.read')
            from automojo.pychestrate.core.managers.build_manager import BuildManager
            
            build_manager = BuildManager(g.db_session)
            artifacts = build_manager.list_artifacts(build_id)
            
            return paginated_response(
                items=[artifact_to_dict(a) for a in artifacts],
                total=len(artifacts),
                offset=0,
                limit=len(artifacts)
            ), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@builds_ns.route("/<int:project_id>/builds/<int:build_id>/artifacts/<int:artifact_id>")
@builds_ns.param('project_id', 'The project identifier')
@builds_ns.param('build_id', 'The build identifier')
@builds_ns.param('artifact_id', 'The artifact identifier')
class BuildArtifactItem(Resource):
    """Individual build artifact."""
    
    @builds_ns.doc('get_build_artifact')
    @builds_ns.response(200, 'Success', build_artifact_model)
    @builds_ns.response(401, 'Unauthorized', error_model)
    @builds_ns.response(403, 'Forbidden', error_model)
    @builds_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, build_id, artifact_id):
        """Get artifact metadata."""
        try:
            check_project_permission(project_id, 'build.read')
            from automojo.pychestrate.core.managers.build_manager import BuildManager
            
            build_manager = BuildManager(g.db_session)
            artifact = build_manager.get_artifact(artifact_id)
            
            if artifact is None or artifact.build_id != build_id:
                return not_found_error('Artifact', str(artifact_id))
            
            return artifact_to_dict(artifact), 200
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
    Publish the builds namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (builds_ns, "".join([version_prefix, BUILDS_NAMESPACE_PATH]))
    ]
    return ns_list
