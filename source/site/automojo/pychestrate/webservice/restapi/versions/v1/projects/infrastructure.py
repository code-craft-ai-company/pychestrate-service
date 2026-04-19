"""
.. module:: infrastructure
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for project infrastructure management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for project infrastructure management:
- Infrastructure specification CRUD endpoints
- Infrastructure job endpoints

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

INFRASTRUCTURE_NAMESPACE_PATH = "/projects"

infrastructure_ns = Namespace(
    "Project Infrastructure v1",
    description="Project infrastructure management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(infrastructure_ns)

infra_resource_model = infrastructure_ns.model('InfraResource', {
    'name': fields.String(required=True, description='Resource name'),
    'type': fields.String(required=True, description='Resource type'),
    'provider_config': fields.Raw(required=True, description='Provider configuration')
})

infra_spec_create_model = infrastructure_ns.model('InfraSpecCreate', {
    'name': fields.String(required=True, description='Specification name'),
    'provider': fields.String(required=True, description='Provider (local, docker, kubernetes, aws, azure, gcp)'),
    'resources': fields.List(fields.Nested(infra_resource_model), description='Resource definitions'),
    'variables': fields.Raw(description='Variables'),
    'timeout_minutes': fields.Integer(description='Timeout in minutes'),
    'description': fields.String(description='Description')
})

infra_spec_response_model = infrastructure_ns.model('InfraSpecResponse', {
    'id': fields.Integer(required=True, description='Specification ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'name': fields.String(required=True, description='Specification name'),
    'provider': fields.String(required=True, description='Provider'),
    'resources': fields.List(fields.Nested(infra_resource_model), description='Resource definitions'),
    'variables': fields.Raw(description='Variables'),
    'timeout_minutes': fields.Integer(description='Timeout in minutes'),
    'description': fields.String(description='Description'),
    'version': fields.Integer(description='Specification version'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'updated_at': fields.DateTime(description='Last update timestamp')
})

infra_spec_list_model = infrastructure_ns.model('InfraSpecList', {
    'items': fields.List(fields.Nested(infra_spec_response_model), description='List of specifications'),
    'total': fields.Integer(required=True, description='Total'),
    'offset': fields.Integer(required=True, description='Offset'),
    'limit': fields.Integer(required=True, description='Limit')
})

infra_job_trigger_model = infrastructure_ns.model('InfraJobTrigger', {
    'spec_id': fields.Integer(required=True, description='Specification ID'),
    'action': fields.String(required=True, description='Action (provision, update, destroy)'),
    'variables': fields.Raw(description='Variables override')
})

infra_job_response_model = infrastructure_ns.model('InfraJobResponse', {
    'id': fields.Integer(required=True, description='Job ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'spec_id': fields.Integer(required=True, description='Specification ID'),
    'spec_name': fields.String(description='Specification name'),
    'spec_version': fields.Integer(description='Specification version'),
    'action': fields.String(description='Action'),
    'state': fields.String(description='Infrastructure state'),
    'status': fields.String(required=True, description='Job status'),
    'triggered_by_id': fields.String(description='Triggered by user ID'),
    'triggered_by_username': fields.String(description='Triggered by username'),
    'provisioned_resources': fields.List(fields.Raw, description='Provisioned resources'),
    'connection_details': fields.Raw(description='Connection details'),
    'started_at': fields.DateTime(description='Start timestamp'),
    'completed_at': fields.DateTime(description='Completion timestamp'),
    'duration_seconds': fields.Integer(description='Duration in seconds'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

infra_job_list_model = infrastructure_ns.model('InfraJobList', {
    'items': fields.List(fields.Nested(infra_job_response_model), description='List of jobs'),
    'total': fields.Integer(required=True, description='Total'),
    'offset': fields.Integer(required=True, description='Offset'),
    'limit': fields.Integer(required=True, description='Limit')
})


# =============================================================================
# Helper Functions
# =============================================================================

def infra_spec_to_dict(spec_response):
    """Convert InfraSpecResponse dataclass to dict."""
    resources = []
    if spec_response.resources:
        for res in spec_response.resources:
            if hasattr(res, '__dict__'):
                resources.append({
                    'name': res.name,
                    'type': res.type,
                    'provider_config': res.provider_config
                })
            else:
                resources.append(res)
    
    return {
        'id': spec_response.id,
        'project_id': spec_response.project_id,
        'name': spec_response.name,
        'provider': spec_response.provider.value if hasattr(spec_response.provider, 'value') else spec_response.provider,
        'resources': resources,
        'variables': spec_response.variables,
        'timeout_minutes': spec_response.timeout_minutes,
        'description': spec_response.description,
        'version': spec_response.version,
        'created_at': spec_response.created_at.isoformat() if spec_response.created_at else None,
        'updated_at': spec_response.updated_at.isoformat() if spec_response.updated_at else None
    }


def infra_job_to_dict(job_response):
    """Convert InfraJobResponse dataclass to dict."""
    return {
        'id': job_response.id,
        'project_id': job_response.project_id,
        'spec_id': job_response.spec_id,
        'spec_name': job_response.spec_name,
        'spec_version': job_response.spec_version,
        'action': job_response.action.value if hasattr(job_response.action, 'value') else job_response.action,
        'state': job_response.state.value if hasattr(job_response.state, 'value') else job_response.state,
        'status': job_response.status.value if hasattr(job_response.status, 'value') else job_response.status,
        'triggered_by_id': str(job_response.triggered_by_id) if job_response.triggered_by_id else None,
        'triggered_by_username': job_response.triggered_by_username,
        'provisioned_resources': job_response.provisioned_resources,
        'connection_details': job_response.connection_details,
        'started_at': job_response.started_at.isoformat() if job_response.started_at else None,
        'completed_at': job_response.completed_at.isoformat() if job_response.completed_at else None,
        'duration_seconds': job_response.duration_seconds,
        'created_at': job_response.created_at.isoformat() if job_response.created_at else None
    }


# =============================================================================
# Infrastructure Specification Endpoints
# =============================================================================

@infrastructure_ns.route("/<int:project_id>/infra-specs")
@infrastructure_ns.param('project_id', 'The project identifier')
class InfraSpecCollection(Resource):
    """Infrastructure specification collection."""
    
    @infrastructure_ns.doc('list_infra_specs')
    @infrastructure_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @infrastructure_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @infrastructure_ns.response(200, 'Success', infra_spec_list_model)
    @infrastructure_ns.response(401, 'Unauthorized', error_model)
    @infrastructure_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def get(self, project_id):
        """List infrastructure specifications."""
        try:
            check_project_permission(project_id, 'infra.read')
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
            
            infra_manager = InfrastructureManager(g.db_session)
            result = infra_manager.list_specs(project_id=project_id, offset=offset, limit=limit)
            
            return paginated_response(
                items=[infra_spec_to_dict(s) for s in result.specs],
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
    
    @infrastructure_ns.doc('create_infra_spec')
    @infrastructure_ns.expect(infra_spec_create_model)
    @infrastructure_ns.response(201, 'Specification created', infra_spec_response_model)
    @infrastructure_ns.response(400, 'Validation error', error_model)
    @infrastructure_ns.response(401, 'Unauthorized', error_model)
    @infrastructure_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def post(self, project_id):
        """Create an infrastructure specification."""
        try:
            check_project_permission(project_id, 'infra.create')
            data = request.json
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.infrastructure_manager import (
                InfrastructureManager, InfraSpecCreateRequest, InfraResourceDefinition, InfraProvider
            )
            
            provider_str = data.get('provider', 'local').lower()
            try:
                provider = InfraProvider(provider_str)
            except ValueError:
                return validation_error(f"Invalid provider: {provider_str}", field="provider")
            
            resources = []
            for res_data in data.get('resources', []):
                resources.append(InfraResourceDefinition(
                    name=res_data.get('name', ''),
                    type=res_data.get('type', ''),
                    provider_config=res_data.get('provider_config', {})
                ))
            
            create_request = InfraSpecCreateRequest(
                name=data.get('name', ''),
                provider=provider,
                resources=resources,
                variables=data.get('variables', {}),
                timeout_minutes=data.get('timeout_minutes', 30),
                description=data.get('description', '')
            )
            
            infra_manager = InfrastructureManager(g.db_session)
            spec_response = infra_manager.create_spec(project_id, create_request, g.current_user_id)
            
            return infra_spec_to_dict(spec_response), 201
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@infrastructure_ns.route("/<int:project_id>/infra-specs/<int:spec_id>")
@infrastructure_ns.param('project_id', 'The project identifier')
@infrastructure_ns.param('spec_id', 'The specification identifier')
class InfraSpecItem(Resource):
    """Individual infrastructure specification."""
    
    @infrastructure_ns.doc('get_infra_spec')
    @infrastructure_ns.response(200, 'Success', infra_spec_response_model)
    @infrastructure_ns.response(401, 'Unauthorized', error_model)
    @infrastructure_ns.response(403, 'Forbidden', error_model)
    @infrastructure_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, spec_id):
        """Get an infrastructure specification."""
        try:
            check_project_permission(project_id, 'infra.read')
            from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
            
            infra_manager = InfrastructureManager(g.db_session)
            spec_response = infra_manager.get_spec(spec_id)
            
            if spec_response is None or spec_response.project_id != project_id:
                return not_found_error('InfraSpec', str(spec_id))
            
            return infra_spec_to_dict(spec_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @infrastructure_ns.doc('delete_infra_spec')
    @infrastructure_ns.response(204, 'Specification deleted')
    @infrastructure_ns.response(401, 'Unauthorized', error_model)
    @infrastructure_ns.response(403, 'Forbidden', error_model)
    @infrastructure_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, spec_id):
        """Delete an infrastructure specification."""
        try:
            check_project_permission(project_id, 'infra.create')
            from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
            
            infra_manager = InfrastructureManager(g.db_session)
            infra_manager.delete_spec(spec_id, g.current_user_id)
            
            return '', 204
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Infrastructure Job Endpoints
# =============================================================================

@infrastructure_ns.route("/<int:project_id>/infra-jobs")
@infrastructure_ns.param('project_id', 'The project identifier')
class InfraJobCollection(Resource):
    """Infrastructure job collection."""
    
    @infrastructure_ns.doc('list_infra_jobs')
    @infrastructure_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @infrastructure_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @infrastructure_ns.param('spec_id', 'Filter by specification ID', type=int)
    @infrastructure_ns.param('status', 'Filter by status', type=str)
    @infrastructure_ns.response(200, 'Success', infra_job_list_model)
    @infrastructure_ns.response(401, 'Unauthorized', error_model)
    @infrastructure_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def get(self, project_id):
        """List infrastructure jobs."""
        try:
            check_project_permission(project_id, 'infra.read')
            offset, limit = get_pagination_params()
            spec_id = request.args.get('spec_id', type=int)
            
            from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
            
            infra_manager = InfrastructureManager(g.db_session)
            result = infra_manager.list_jobs(project_id=project_id, spec_id=spec_id, offset=offset, limit=limit)
            
            return paginated_response(
                items=[infra_job_to_dict(j) for j in result.jobs],
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
    
    @infrastructure_ns.doc('trigger_infra_job')
    @infrastructure_ns.expect(infra_job_trigger_model)
    @infrastructure_ns.response(201, 'Job triggered', infra_job_response_model)
    @infrastructure_ns.response(400, 'Validation error', error_model)
    @infrastructure_ns.response(401, 'Unauthorized', error_model)
    @infrastructure_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def post(self, project_id):
        """Trigger an infrastructure job."""
        try:
            check_project_permission(project_id, 'infra.trigger')
            data = request.json
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.infrastructure_manager import (
                InfrastructureManager, InfraJobTriggerRequest, InfraAction
            )
            
            action_str = data.get('action', 'provision').lower()
            try:
                action = InfraAction(action_str)
            except ValueError:
                return validation_error(f"Invalid action: {action_str}", field="action")
            
            trigger_request = InfraJobTriggerRequest(
                spec_id=data.get('spec_id'),
                action=action,
                variables=data.get('variables', {})
            )
            
            infra_manager = InfrastructureManager(g.db_session)
            job_response = infra_manager.trigger_job(trigger_request, g.current_user_id)
            
            return infra_job_to_dict(job_response), 201
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@infrastructure_ns.route("/<int:project_id>/infra-jobs/<int:job_id>")
@infrastructure_ns.param('project_id', 'The project identifier')
@infrastructure_ns.param('job_id', 'The job identifier')
class InfraJobItem(Resource):
    """Individual infrastructure job."""
    
    @infrastructure_ns.doc('get_infra_job')
    @infrastructure_ns.response(200, 'Success', infra_job_response_model)
    @infrastructure_ns.response(401, 'Unauthorized', error_model)
    @infrastructure_ns.response(403, 'Forbidden', error_model)
    @infrastructure_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, job_id):
        """Get an infrastructure job."""
        try:
            check_project_permission(project_id, 'infra.read')
            from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
            
            infra_manager = InfrastructureManager(g.db_session)
            job_response = infra_manager.get_job(job_id)
            
            if job_response is None or job_response.project_id != project_id:
                return not_found_error('InfraJob', str(job_id))
            
            return infra_job_to_dict(job_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@infrastructure_ns.route("/<int:project_id>/infra-jobs/<int:job_id>/cancel")
@infrastructure_ns.param('project_id', 'The project identifier')
@infrastructure_ns.param('job_id', 'The job identifier')
class InfraJobCancel(Resource):
    """Infrastructure job cancel endpoint."""
    
    @infrastructure_ns.doc('cancel_infra_job')
    @infrastructure_ns.response(200, 'Job cancelled', infra_job_response_model)
    @infrastructure_ns.response(401, 'Unauthorized', error_model)
    @infrastructure_ns.response(403, 'Forbidden', error_model)
    @infrastructure_ns.response(404, 'Not found', error_model)
    @require_auth
    def post(self, project_id, job_id):
        """Cancel an infrastructure job."""
        try:
            check_project_permission(project_id, 'infra.cancel')
            from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
            
            infra_manager = InfrastructureManager(g.db_session)
            job_response = infra_manager.cancel_job(job_id, g.current_user_id)
            
            return infra_job_to_dict(job_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@infrastructure_ns.route("/<int:project_id>/infra-jobs/<int:job_id>/logs")
@infrastructure_ns.param('project_id', 'The project identifier')
@infrastructure_ns.param('job_id', 'The job identifier')
class InfraJobLogs(Resource):
    """Infrastructure job logs endpoint."""
    
    @infrastructure_ns.doc('get_infra_job_logs')
    @infrastructure_ns.response(200, 'Success')
    @infrastructure_ns.response(401, 'Unauthorized', error_model)
    @infrastructure_ns.response(403, 'Forbidden', error_model)
    @infrastructure_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, job_id):
        """Get infrastructure job logs."""
        try:
            check_project_permission(project_id, 'infra.read')
            from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
            
            infra_manager = InfrastructureManager(g.db_session)
            logs = infra_manager.get_job_logs(job_id)
            
            return {'logs': logs}, 200
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
    Publish the infrastructure namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (infrastructure_ns, "".join([version_prefix, INFRASTRUCTURE_NAMESPACE_PATH]))
    ]
    return ns_list
