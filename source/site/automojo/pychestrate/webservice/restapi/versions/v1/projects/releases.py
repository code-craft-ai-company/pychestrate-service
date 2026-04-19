"""
.. module:: releases
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for project release management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for project release management:
- Release pipeline CRUD endpoints
- Pipeline run endpoints
- Release CRUD endpoints
- Artifact endpoints
- Channel endpoints
- Schedule endpoints

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

RELEASES_NAMESPACE_PATH = "/projects"

releases_ns = Namespace(
    "Project Releases v1",
    description="Project release management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(releases_ns)

pipeline_stage_model = releases_ns.model('PipelineStage', {
    'name': fields.String(required=True, description='Stage name'),
    'type': fields.String(required=True, description='Stage type'),
    'config': fields.Raw(description='Stage configuration'),
    'requires_approval': fields.Boolean(description='Requires approval'),
    'continue_on_failure': fields.Boolean(description='Continue on failure')
})

pipeline_create_model = releases_ns.model('PipelineCreate', {
    'name': fields.String(required=True, description='Pipeline name'),
    'stages': fields.List(fields.Nested(pipeline_stage_model), description='Pipeline stages'),
    'triggers': fields.List(fields.String, description='Trigger types'),
    'variables': fields.Raw(description='Variables'),
    'description': fields.String(description='Description')
})

pipeline_response_model = releases_ns.model('PipelineResponse', {
    'id': fields.Integer(required=True, description='Pipeline ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'name': fields.String(required=True, description='Pipeline name'),
    'stages': fields.List(fields.Nested(pipeline_stage_model), description='Pipeline stages'),
    'triggers': fields.List(fields.String, description='Trigger types'),
    'variables': fields.Raw(description='Variables'),
    'description': fields.String(description='Description'),
    'version': fields.Integer(description='Version'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'updated_at': fields.DateTime(description='Last update timestamp')
})

pipeline_list_model = releases_ns.model('PipelineList', {
    'items': fields.List(fields.Nested(pipeline_response_model), description='List of pipelines'),
    'total': fields.Integer(required=True, description='Total'),
    'offset': fields.Integer(required=True, description='Offset'),
    'limit': fields.Integer(required=True, description='Limit')
})

release_create_model = releases_ns.model('ReleaseCreate', {
    'version': fields.String(required=True, description='Release version'),
    'name': fields.String(description='Release name'),
    'description': fields.String(description='Description'),
    'metadata': fields.Raw(description='Metadata')
})

release_response_model = releases_ns.model('ReleaseResponse', {
    'id': fields.Integer(required=True, description='Release ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'version': fields.String(required=True, description='Version'),
    'name': fields.String(description='Name'),
    'description': fields.String(description='Description'),
    'status': fields.String(description='Status'),
    'metadata': fields.Raw(description='Metadata'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'published_at': fields.DateTime(description='Publish timestamp'),
    'published_by_id': fields.String(description='Published by user ID')
})

release_list_model = releases_ns.model('ReleaseList', {
    'items': fields.List(fields.Nested(release_response_model), description='List of releases'),
    'total': fields.Integer(required=True, description='Total'),
    'offset': fields.Integer(required=True, description='Offset'),
    'limit': fields.Integer(required=True, description='Limit')
})

channel_create_model = releases_ns.model('ChannelCreate', {
    'name': fields.String(required=True, description='Channel name'),
    'description': fields.String(description='Description')
})

channel_response_model = releases_ns.model('ChannelResponse', {
    'id': fields.Integer(required=True, description='Channel ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'name': fields.String(required=True, description='Channel name'),
    'description': fields.String(description='Description'),
    'current_release_id': fields.Integer(description='Current release ID'),
    'current_release_version': fields.String(description='Current release version'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

schedule_create_model = releases_ns.model('ScheduleCreate', {
    'name': fields.String(required=True, description='Schedule name'),
    'cron_expression': fields.String(required=True, description='Cron expression'),
    'pipeline_id': fields.Integer(required=True, description='Pipeline ID'),
    'variables': fields.Raw(description='Variables override')
})

schedule_response_model = releases_ns.model('ScheduleResponse', {
    'id': fields.Integer(required=True, description='Schedule ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'name': fields.String(required=True, description='Schedule name'),
    'cron_expression': fields.String(description='Cron expression'),
    'pipeline_id': fields.Integer(description='Pipeline ID'),
    'variables': fields.Raw(description='Variables'),
    'enabled': fields.Boolean(description='Enabled'),
    'last_run_time': fields.DateTime(description='Last run time'),
    'next_run_time': fields.DateTime(description='Next run time'),
    'created_at': fields.DateTime(description='Creation timestamp')
})


# =============================================================================
# Helper Functions
# =============================================================================

def pipeline_to_dict(pipeline_response):
    """Convert ReleasePipelineResponse dataclass to dict."""
    stages = []
    if pipeline_response.stages:
        for stage in pipeline_response.stages:
            if hasattr(stage, '__dict__'):
                stages.append({
                    'name': stage.name,
                    'type': stage.type.value if hasattr(stage.type, 'value') else stage.type,
                    'config': stage.config,
                    'requires_approval': getattr(stage, 'requires_approval', False),
                    'continue_on_failure': getattr(stage, 'continue_on_failure', False)
                })
            else:
                stages.append(stage)
    
    triggers = []
    if pipeline_response.triggers:
        for t in pipeline_response.triggers:
            triggers.append(t.value if hasattr(t, 'value') else t)
    
    return {
        'id': pipeline_response.id,
        'project_id': pipeline_response.project_id,
        'name': pipeline_response.name,
        'stages': stages,
        'triggers': triggers,
        'variables': pipeline_response.variables,
        'description': pipeline_response.description,
        'version': pipeline_response.version,
        'created_at': pipeline_response.created_at.isoformat() if pipeline_response.created_at else None,
        'updated_at': pipeline_response.updated_at.isoformat() if pipeline_response.updated_at else None
    }


def release_to_dict(release_response):
    """Convert ReleaseResponse dataclass to dict."""
    return {
        'id': release_response.id,
        'project_id': release_response.project_id,
        'version': release_response.version,
        'name': release_response.name,
        'description': release_response.description,
        'status': release_response.status.value if hasattr(release_response.status, 'value') else release_response.status,
        'metadata': release_response.metadata if hasattr(release_response, 'metadata') else {},
        'created_at': release_response.created_at.isoformat() if release_response.created_at else None,
        'published_at': release_response.published_at.isoformat() if hasattr(release_response, 'published_at') and release_response.published_at else None,
        'published_by_id': str(release_response.published_by_id) if hasattr(release_response, 'published_by_id') and release_response.published_by_id else None
    }


def channel_to_dict(channel_response):
    """Convert ReleaseChannelResponse dataclass to dict."""
    return {
        'id': channel_response.id,
        'project_id': channel_response.project_id,
        'name': channel_response.name,
        'description': channel_response.description,
        'current_release_id': channel_response.current_release_id if hasattr(channel_response, 'current_release_id') else None,
        'current_release_version': channel_response.current_release_version if hasattr(channel_response, 'current_release_version') else None,
        'created_at': channel_response.created_at.isoformat() if channel_response.created_at else None
    }


def schedule_to_dict(schedule_response):
    """Convert ReleaseScheduleResponse dataclass to dict."""
    return {
        'id': schedule_response.id,
        'project_id': schedule_response.project_id,
        'name': schedule_response.name,
        'cron_expression': schedule_response.cron_expression,
        'pipeline_id': schedule_response.pipeline_id,
        'variables': schedule_response.variables if hasattr(schedule_response, 'variables') else {},
        'enabled': schedule_response.enabled,
        'last_run_time': schedule_response.last_run_time.isoformat() if hasattr(schedule_response, 'last_run_time') and schedule_response.last_run_time else None,
        'next_run_time': schedule_response.next_run_time.isoformat() if hasattr(schedule_response, 'next_run_time') and schedule_response.next_run_time else None,
        'created_at': schedule_response.created_at.isoformat() if schedule_response.created_at else None
    }


# =============================================================================
# Release Pipeline Endpoints
# =============================================================================

@releases_ns.route("/<int:project_id>/pipelines")
@releases_ns.param('project_id', 'The project identifier')
class PipelineCollection(Resource):
    """Release pipeline collection."""
    
    @releases_ns.doc('list_pipelines')
    @releases_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @releases_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @releases_ns.response(200, 'Success', pipeline_list_model)
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def get(self, project_id):
        """List release pipelines."""
        try:
            check_project_permission(project_id, 'release.read')
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager
            
            release_manager = ReleaseManager(g.db_session)
            result = release_manager.list_pipelines(project_id=project_id, offset=offset, limit=limit)
            
            return paginated_response(
                items=[pipeline_to_dict(p) for p in result.pipelines],
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
    
    @releases_ns.doc('create_pipeline')
    @releases_ns.expect(pipeline_create_model)
    @releases_ns.response(201, 'Pipeline created', pipeline_response_model)
    @releases_ns.response(400, 'Validation error', error_model)
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def post(self, project_id):
        """Create a release pipeline."""
        try:
            check_project_permission(project_id, 'release.create')
            data = request.json
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.release_manager import (
                ReleaseManager, ReleasePipelineCreateRequest, PipelineStageDefinition, PipelineStageType, PipelineTriggerType
            )
            
            stages = []
            for stage_data in data.get('stages', []):
                stage_type_str = stage_data.get('type', 'build').lower()
                try:
                    stage_type = PipelineStageType(stage_type_str)
                except ValueError:
                    stage_type = PipelineStageType.BUILD
                
                stages.append(PipelineStageDefinition(
                    name=stage_data.get('name', ''),
                    type=stage_type,
                    config=stage_data.get('config', {}),
                    requires_approval=stage_data.get('requires_approval', False),
                    continue_on_failure=stage_data.get('continue_on_failure', False)
                ))
            
            triggers = []
            for trigger_str in data.get('triggers', []):
                try:
                    triggers.append(PipelineTriggerType(trigger_str.lower()))
                except ValueError:
                    pass
            
            create_request = ReleasePipelineCreateRequest(
                name=data.get('name', ''),
                stages=stages,
                triggers=triggers,
                variables=data.get('variables', {}),
                description=data.get('description', '')
            )
            
            release_manager = ReleaseManager(g.db_session)
            pipeline_response = release_manager.create_pipeline(project_id, create_request, g.current_user_id)
            
            return pipeline_to_dict(pipeline_response), 201
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@releases_ns.route("/<int:project_id>/pipelines/<int:pipeline_id>")
@releases_ns.param('project_id', 'The project identifier')
@releases_ns.param('pipeline_id', 'The pipeline identifier')
class PipelineItem(Resource):
    """Individual release pipeline."""
    
    @releases_ns.doc('get_pipeline')
    @releases_ns.response(200, 'Success', pipeline_response_model)
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @releases_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, pipeline_id):
        """Get a release pipeline."""
        try:
            check_project_permission(project_id, 'release.read')
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager
            
            release_manager = ReleaseManager(g.db_session)
            pipeline_response = release_manager.get_pipeline(pipeline_id)
            
            if pipeline_response is None or pipeline_response.project_id != project_id:
                return not_found_error('Pipeline', str(pipeline_id))
            
            return pipeline_to_dict(pipeline_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @releases_ns.doc('delete_pipeline')
    @releases_ns.response(204, 'Pipeline deleted')
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @releases_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, pipeline_id):
        """Delete a release pipeline."""
        try:
            check_project_permission(project_id, 'release.create')
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager
            
            release_manager = ReleaseManager(g.db_session)
            release_manager.delete_pipeline(pipeline_id, g.current_user_id)
            
            return '', 204
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Release Endpoints
# =============================================================================

@releases_ns.route("/<int:project_id>/releases")
@releases_ns.param('project_id', 'The project identifier')
class ReleaseCollection(Resource):
    """Release collection."""
    
    @releases_ns.doc('list_releases')
    @releases_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @releases_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @releases_ns.param('status', 'Filter by status', type=str)
    @releases_ns.response(200, 'Success', release_list_model)
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def get(self, project_id):
        """List releases."""
        try:
            check_project_permission(project_id, 'release.read')
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager
            
            release_manager = ReleaseManager(g.db_session)
            result = release_manager.list_releases(project_id=project_id, offset=offset, limit=limit)
            
            return paginated_response(
                items=[release_to_dict(r) for r in result.releases],
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
    
    @releases_ns.doc('create_release')
    @releases_ns.expect(release_create_model)
    @releases_ns.response(201, 'Release created', release_response_model)
    @releases_ns.response(400, 'Validation error', error_model)
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @releases_ns.response(409, 'Conflict', error_model)
    @require_auth
    def post(self, project_id):
        """Create a release."""
        try:
            check_project_permission(project_id, 'release.create')
            data = request.json
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager, ReleaseCreateRequest
            
            create_request = ReleaseCreateRequest(
                version=data.get('version', ''),
                name=data.get('name', ''),
                description=data.get('description', ''),
                metadata=data.get('metadata', {})
            )
            
            release_manager = ReleaseManager(g.db_session)
            release_response = release_manager.create_release(project_id, create_request, g.current_user_id)
            
            return release_to_dict(release_response), 201
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@releases_ns.route("/<int:project_id>/releases/<int:release_id>")
@releases_ns.param('project_id', 'The project identifier')
@releases_ns.param('release_id', 'The release identifier')
class ReleaseItem(Resource):
    """Individual release."""
    
    @releases_ns.doc('get_release')
    @releases_ns.response(200, 'Success', release_response_model)
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @releases_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, release_id):
        """Get a release."""
        try:
            check_project_permission(project_id, 'release.read')
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager
            
            release_manager = ReleaseManager(g.db_session)
            release_response = release_manager.get_release(release_id)
            
            if release_response is None or release_response.project_id != project_id:
                return not_found_error('Release', str(release_id))
            
            return release_to_dict(release_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @releases_ns.doc('delete_release')
    @releases_ns.response(204, 'Release deleted')
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @releases_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, release_id):
        """Delete a release."""
        try:
            check_project_permission(project_id, 'release.create')
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager
            
            release_manager = ReleaseManager(g.db_session)
            release_manager.delete_release(release_id, g.current_user_id)
            
            return '', 204
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Channel Endpoints
# =============================================================================

@releases_ns.route("/<int:project_id>/channels")
@releases_ns.param('project_id', 'The project identifier')
class ChannelCollection(Resource):
    """Release channel collection."""
    
    @releases_ns.doc('list_channels')
    @releases_ns.response(200, 'Success')
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def get(self, project_id):
        """List release channels."""
        try:
            check_project_permission(project_id, 'release.read')
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager
            
            release_manager = ReleaseManager(g.db_session)
            channels = release_manager.list_channels(project_id)
            
            return {'items': [channel_to_dict(c) for c in channels]}, 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @releases_ns.doc('create_channel')
    @releases_ns.expect(channel_create_model)
    @releases_ns.response(201, 'Channel created', channel_response_model)
    @releases_ns.response(400, 'Validation error', error_model)
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def post(self, project_id):
        """Create a release channel."""
        try:
            check_project_permission(project_id, 'release.create')
            data = request.json
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager, ReleaseChannelCreateRequest
            
            create_request = ReleaseChannelCreateRequest(
                name=data.get('name', ''),
                description=data.get('description', '')
            )
            
            release_manager = ReleaseManager(g.db_session)
            channel_response = release_manager.create_channel(project_id, create_request, g.current_user_id)
            
            return channel_to_dict(channel_response), 201
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@releases_ns.route("/<int:project_id>/channels/<int:channel_id>/publish")
@releases_ns.param('project_id', 'The project identifier')
@releases_ns.param('channel_id', 'The channel identifier')
class ChannelPublish(Resource):
    """Channel publish endpoint."""
    
    @releases_ns.doc('publish_to_channel')
    @releases_ns.response(200, 'Published', channel_response_model)
    @releases_ns.response(400, 'Validation error', error_model)
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def post(self, project_id, channel_id):
        """Publish a release to a channel."""
        try:
            check_project_permission(project_id, 'release.publish')
            data = request.json or {}
            release_id = data.get('release_id')
            
            if not release_id:
                return validation_error("release_id is required", field="release_id")
            
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager
            
            release_manager = ReleaseManager(g.db_session)
            channel_response = release_manager.publish_to_channel(channel_id, release_id, g.current_user_id)
            
            return channel_to_dict(channel_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Schedule Endpoints
# =============================================================================

@releases_ns.route("/<int:project_id>/schedules")
@releases_ns.param('project_id', 'The project identifier')
class ScheduleCollection(Resource):
    """Release schedule collection."""
    
    @releases_ns.doc('list_schedules')
    @releases_ns.response(200, 'Success')
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def get(self, project_id):
        """List release schedules."""
        try:
            check_project_permission(project_id, 'release.read')
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager
            
            release_manager = ReleaseManager(g.db_session)
            schedules = release_manager.list_schedules(project_id)
            
            return {'items': [schedule_to_dict(s) for s in schedules]}, 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @releases_ns.doc('create_schedule')
    @releases_ns.expect(schedule_create_model)
    @releases_ns.response(201, 'Schedule created', schedule_response_model)
    @releases_ns.response(400, 'Validation error', error_model)
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def post(self, project_id):
        """Create a release schedule."""
        try:
            check_project_permission(project_id, 'release.create')
            data = request.json
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager, ReleaseScheduleCreateRequest
            
            create_request = ReleaseScheduleCreateRequest(
                name=data.get('name', ''),
                cron_expression=data.get('cron_expression', ''),
                pipeline_id=data.get('pipeline_id'),
                variables=data.get('variables', {})
            )
            
            release_manager = ReleaseManager(g.db_session)
            schedule_response = release_manager.create_schedule(project_id, create_request, g.current_user_id)
            
            return schedule_to_dict(schedule_response), 201
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@releases_ns.route("/<int:project_id>/schedules/<int:schedule_id>")
@releases_ns.param('project_id', 'The project identifier')
@releases_ns.param('schedule_id', 'The schedule identifier')
class ScheduleItem(Resource):
    """Individual release schedule."""
    
    @releases_ns.doc('delete_schedule')
    @releases_ns.response(204, 'Schedule deleted')
    @releases_ns.response(401, 'Unauthorized', error_model)
    @releases_ns.response(403, 'Forbidden', error_model)
    @releases_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, schedule_id):
        """Delete a release schedule."""
        try:
            check_project_permission(project_id, 'release.create')
            from automojo.pychestrate.core.managers.release_manager import ReleaseManager
            
            release_manager = ReleaseManager(g.db_session)
            release_manager.delete_schedule(schedule_id, g.current_user_id)
            
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
    Publish the releases namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (releases_ns, "".join([version_prefix, RELEASES_NAMESPACE_PATH]))
    ]
    return ns_list
