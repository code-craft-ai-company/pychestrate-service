"""
.. module:: calendar
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for project calendar event management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for project calendar event management:
- Release event endpoints
- Phase event endpoints
- Release branch endpoints
- Merge event endpoints
- Pull event endpoints
- Calendar view endpoint

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

CALENDAR_NAMESPACE_PATH = "/projects"

calendar_ns = Namespace(
    "Project Calendar v1",
    description="Project calendar event management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(calendar_ns)

release_event_create_model = calendar_ns.model('ReleaseEventCreate', {
    'name': fields.String(required=True, description='Event name'),
    'start_time': fields.DateTime(required=True, description='Start time'),
    'end_time': fields.DateTime(required=True, description='End time'),
    'release_id': fields.Integer(description='Release ID'),
    'description': fields.String(description='Description')
})

release_event_response_model = calendar_ns.model('ReleaseEventResponse', {
    'id': fields.Integer(required=True, description='Event ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'name': fields.String(required=True, description='Event name'),
    'start_time': fields.DateTime(description='Start time'),
    'end_time': fields.DateTime(description='End time'),
    'release_id': fields.Integer(description='Release ID'),
    'description': fields.String(description='Description'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

phase_event_create_model = calendar_ns.model('PhaseEventCreate', {
    'name': fields.String(required=True, description='Phase name'),
    'release_event_id': fields.Integer(required=True, description='Release event ID'),
    'start_time': fields.DateTime(required=True, description='Start time'),
    'end_time': fields.DateTime(required=True, description='End time'),
    'order': fields.Integer(description='Phase order'),
    'description': fields.String(description='Description')
})

phase_event_response_model = calendar_ns.model('PhaseEventResponse', {
    'id': fields.Integer(required=True, description='Phase ID'),
    'release_event_id': fields.Integer(required=True, description='Release event ID'),
    'name': fields.String(required=True, description='Phase name'),
    'start_time': fields.DateTime(description='Start time'),
    'end_time': fields.DateTime(description='End time'),
    'order': fields.Integer(description='Phase order'),
    'status': fields.String(description='Phase status'),
    'description': fields.String(description='Description'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

release_branch_create_model = calendar_ns.model('ReleaseBranchCreate', {
    'release_event_id': fields.Integer(required=True, description='Release event ID'),
    'repository_id': fields.Integer(required=True, description='Repository ID'),
    'branch_name': fields.String(required=True, description='Branch name')
})

release_branch_response_model = calendar_ns.model('ReleaseBranchResponse', {
    'id': fields.Integer(required=True, description='Branch association ID'),
    'release_event_id': fields.Integer(required=True, description='Release event ID'),
    'repository_id': fields.Integer(required=True, description='Repository ID'),
    'repository_name': fields.String(description='Repository name'),
    'branch_name': fields.String(required=True, description='Branch name'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

merge_event_create_model = calendar_ns.model('MergeEventCreate', {
    'release_event_id': fields.Integer(required=True, description='Release event ID'),
    'repository_id': fields.Integer(required=True, description='Repository ID'),
    'source_branch': fields.String(required=True, description='Source branch'),
    'target_branch': fields.String(required=True, description='Target branch'),
    'scheduled_time': fields.DateTime(required=True, description='Scheduled time')
})

merge_event_response_model = calendar_ns.model('MergeEventResponse', {
    'id': fields.Integer(required=True, description='Merge event ID'),
    'release_event_id': fields.Integer(required=True, description='Release event ID'),
    'repository_id': fields.Integer(required=True, description='Repository ID'),
    'source_branch': fields.String(description='Source branch'),
    'target_branch': fields.String(description='Target branch'),
    'scheduled_time': fields.DateTime(description='Scheduled time'),
    'status': fields.String(description='Status'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

pull_event_create_model = calendar_ns.model('PullEventCreate', {
    'release_event_id': fields.Integer(required=True, description='Release event ID'),
    'repository_id': fields.Integer(required=True, description='Repository ID'),
    'source_branch': fields.String(required=True, description='Source branch'),
    'target_branch': fields.String(required=True, description='Target branch'),
    'scheduled_time': fields.DateTime(required=True, description='Scheduled time')
})

pull_event_response_model = calendar_ns.model('PullEventResponse', {
    'id': fields.Integer(required=True, description='Pull event ID'),
    'release_event_id': fields.Integer(required=True, description='Release event ID'),
    'repository_id': fields.Integer(required=True, description='Repository ID'),
    'source_branch': fields.String(description='Source branch'),
    'target_branch': fields.String(description='Target branch'),
    'scheduled_time': fields.DateTime(description='Scheduled time'),
    'status': fields.String(description='Status'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

calendar_event_model = calendar_ns.model('CalendarEvent', {
    'id': fields.Integer(required=True, description='Event ID'),
    'type': fields.String(required=True, description='Event type'),
    'name': fields.String(description='Event name'),
    'start_time': fields.DateTime(description='Start time'),
    'end_time': fields.DateTime(description='End time'),
    'status': fields.String(description='Status'),
    'metadata': fields.Raw(description='Additional metadata')
})


# =============================================================================
# Helper Functions
# =============================================================================

def release_event_to_dict(event_response):
    """Convert ReleaseEventResponse dataclass to dict."""
    return {
        'id': event_response.id,
        'project_id': event_response.project_id,
        'name': event_response.name,
        'start_time': event_response.start_time.isoformat() if event_response.start_time else None,
        'end_time': event_response.end_time.isoformat() if event_response.end_time else None,
        'release_id': event_response.release_id if hasattr(event_response, 'release_id') else None,
        'description': event_response.description if hasattr(event_response, 'description') else '',
        'created_at': event_response.created_at.isoformat() if event_response.created_at else None
    }


def phase_event_to_dict(phase_response):
    """Convert PhaseEventResponse dataclass to dict."""
    return {
        'id': phase_response.id,
        'release_event_id': phase_response.release_event_id,
        'name': phase_response.name,
        'start_time': phase_response.start_time.isoformat() if phase_response.start_time else None,
        'end_time': phase_response.end_time.isoformat() if phase_response.end_time else None,
        'order': phase_response.order if hasattr(phase_response, 'order') else 0,
        'status': phase_response.status.value if hasattr(phase_response.status, 'value') else phase_response.status,
        'description': phase_response.description if hasattr(phase_response, 'description') else '',
        'created_at': phase_response.created_at.isoformat() if phase_response.created_at else None
    }


def release_branch_to_dict(branch_response):
    """Convert ReleaseBranchResponse dataclass to dict."""
    return {
        'id': branch_response.id,
        'release_event_id': branch_response.release_event_id,
        'repository_id': branch_response.repository_id,
        'repository_name': branch_response.repository_name if hasattr(branch_response, 'repository_name') else '',
        'branch_name': branch_response.branch_name,
        'created_at': branch_response.created_at.isoformat() if branch_response.created_at else None
    }


def merge_event_to_dict(merge_response):
    """Convert MergeEventResponse dataclass to dict."""
    return {
        'id': merge_response.id,
        'release_event_id': merge_response.release_event_id,
        'repository_id': merge_response.repository_id,
        'source_branch': merge_response.source_branch,
        'target_branch': merge_response.target_branch,
        'scheduled_time': merge_response.scheduled_time.isoformat() if merge_response.scheduled_time else None,
        'status': merge_response.status.value if hasattr(merge_response.status, 'value') else merge_response.status,
        'created_at': merge_response.created_at.isoformat() if merge_response.created_at else None
    }


def pull_event_to_dict(pull_response):
    """Convert PullEventResponse dataclass to dict."""
    return {
        'id': pull_response.id,
        'release_event_id': pull_response.release_event_id,
        'repository_id': pull_response.repository_id,
        'source_branch': pull_response.source_branch,
        'target_branch': pull_response.target_branch,
        'scheduled_time': pull_response.scheduled_time.isoformat() if pull_response.scheduled_time else None,
        'status': pull_response.status.value if hasattr(pull_response.status, 'value') else pull_response.status,
        'created_at': pull_response.created_at.isoformat() if pull_response.created_at else None
    }


# =============================================================================
# Release Event Endpoints
# =============================================================================

@calendar_ns.route("/<int:project_id>/calendar/release-events")
@calendar_ns.param('project_id', 'The project identifier')
class ReleaseEventCollection(Resource):
    """Collection endpoint for release events."""
    
    @calendar_ns.doc('list_release_events')
    @calendar_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @calendar_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @calendar_ns.response(200, 'Success')
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(403, 'Forbidden', error_model)
    @calendar_ns.response(404, 'Project not found', error_model)
    @require_auth
    def get(self, project_id):
        """List release events for a project."""
        try:
            check_project_permission(project_id, 'read')
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            result = calendar_manager.list_release_events(
                project_id=project_id,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[release_event_to_dict(e) for e in result.events],
                total=result.total,
                offset=result.offset,
                limit=result.limit
            ), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('create_release_event')
    @calendar_ns.expect(release_event_create_model)
    @calendar_ns.response(201, 'Release event created', release_event_response_model)
    @calendar_ns.response(400, 'Validation error', error_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def post(self, project_id):
        """Create a new release event."""
        try:
            check_project_permission(project_id, 'write')
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.calendar_manager import (
                CalendarManager,
                ReleaseEventCreateRequest
            )
            
            create_request = ReleaseEventCreateRequest(
                project_id=project_id,
                name=data.get('name', ''),
                start_time=data.get('start_time'),
                end_time=data.get('end_time'),
                release_id=data.get('release_id'),
                description=data.get('description', '')
            )
            
            calendar_manager = CalendarManager(g.db_session)
            event = calendar_manager.create_release_event(
                create_request,
                user_id=g.current_user_id
            )
            
            return release_event_to_dict(event), 201
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


@calendar_ns.route("/<int:project_id>/calendar/release-events/<int:event_id>")
@calendar_ns.param('project_id', 'The project identifier')
@calendar_ns.param('event_id', 'The release event identifier')
class ReleaseEventItem(Resource):
    """Individual release event endpoint."""
    
    @calendar_ns.doc('get_release_event')
    @calendar_ns.response(200, 'Success', release_event_response_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, event_id):
        """Get a release event by ID."""
        try:
            check_project_permission(project_id, 'read')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            event = calendar_manager.get_release_event(event_id)
            
            if event is None:
                return not_found_error('ReleaseEvent', str(event_id))
            
            return release_event_to_dict(event), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('update_release_event')
    @calendar_ns.expect(release_event_create_model)
    @calendar_ns.response(200, 'Release event updated', release_event_response_model)
    @calendar_ns.response(400, 'Validation error', error_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def put(self, project_id, event_id):
        """Update a release event."""
        try:
            check_project_permission(project_id, 'write')
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.calendar_manager import (
                CalendarManager,
                ReleaseEventUpdateRequest
            )
            
            update_request = ReleaseEventUpdateRequest(
                name=data.get('name'),
                start_time=data.get('start_time'),
                end_time=data.get('end_time'),
                release_id=data.get('release_id'),
                description=data.get('description')
            )
            
            calendar_manager = CalendarManager(g.db_session)
            event = calendar_manager.update_release_event(
                event_id,
                update_request,
                user_id=g.current_user_id
            )
            
            return release_event_to_dict(event), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('delete_release_event')
    @calendar_ns.response(204, 'Release event deleted')
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, event_id):
        """Delete a release event."""
        try:
            check_project_permission(project_id, 'admin')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            calendar_manager.delete_release_event(event_id, user_id=g.current_user_id)
            
            return '', 204
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Phase Event Endpoints
# =============================================================================

@calendar_ns.route("/<int:project_id>/calendar/release-events/<int:event_id>/phases")
@calendar_ns.param('project_id', 'The project identifier')
@calendar_ns.param('event_id', 'The release event identifier')
class PhaseEventCollection(Resource):
    """Collection endpoint for phase events."""
    
    @calendar_ns.doc('list_phase_events')
    @calendar_ns.response(200, 'Success')
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, event_id):
        """List phase events for a release event."""
        try:
            check_project_permission(project_id, 'read')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            phases = calendar_manager.list_phase_events(event_id)
            
            return {'items': [phase_event_to_dict(p) for p in phases]}, 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('create_phase_event')
    @calendar_ns.expect(phase_event_create_model)
    @calendar_ns.response(201, 'Phase event created', phase_event_response_model)
    @calendar_ns.response(400, 'Validation error', error_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @require_auth
    def post(self, project_id, event_id):
        """Create a new phase event."""
        try:
            check_project_permission(project_id, 'write')
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.calendar_manager import (
                CalendarManager,
                PhaseEventCreateRequest
            )
            
            create_request = PhaseEventCreateRequest(
                release_event_id=event_id,
                name=data.get('name', ''),
                start_time=data.get('start_time'),
                end_time=data.get('end_time'),
                order=data.get('order', 0),
                description=data.get('description', '')
            )
            
            calendar_manager = CalendarManager(g.db_session)
            phase = calendar_manager.create_phase_event(
                create_request,
                user_id=g.current_user_id
            )
            
            return phase_event_to_dict(phase), 201
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


@calendar_ns.route("/<int:project_id>/calendar/phases/<int:phase_id>")
@calendar_ns.param('project_id', 'The project identifier')
@calendar_ns.param('phase_id', 'The phase event identifier')
class PhaseEventItem(Resource):
    """Individual phase event endpoint."""
    
    @calendar_ns.doc('get_phase_event')
    @calendar_ns.response(200, 'Success', phase_event_response_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, phase_id):
        """Get a phase event by ID."""
        try:
            check_project_permission(project_id, 'read')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            phase = calendar_manager.get_phase_event(phase_id)
            
            if phase is None:
                return not_found_error('PhaseEvent', str(phase_id))
            
            return phase_event_to_dict(phase), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('update_phase_event')
    @calendar_ns.expect(phase_event_create_model)
    @calendar_ns.response(200, 'Phase event updated', phase_event_response_model)
    @calendar_ns.response(400, 'Validation error', error_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @require_auth
    def put(self, project_id, phase_id):
        """Update a phase event."""
        try:
            check_project_permission(project_id, 'write')
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.calendar_manager import (
                CalendarManager,
                PhaseEventUpdateRequest
            )
            
            update_request = PhaseEventUpdateRequest(
                name=data.get('name'),
                start_time=data.get('start_time'),
                end_time=data.get('end_time'),
                order=data.get('order'),
                status=data.get('status'),
                description=data.get('description')
            )
            
            calendar_manager = CalendarManager(g.db_session)
            phase = calendar_manager.update_phase_event(
                phase_id,
                update_request,
                user_id=g.current_user_id
            )
            
            return phase_event_to_dict(phase), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('delete_phase_event')
    @calendar_ns.response(204, 'Phase event deleted')
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, phase_id):
        """Delete a phase event."""
        try:
            check_project_permission(project_id, 'admin')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            calendar_manager.delete_phase_event(phase_id, user_id=g.current_user_id)
            
            return '', 204
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Release Branch Endpoints
# =============================================================================

@calendar_ns.route("/<int:project_id>/calendar/release-events/<int:event_id>/branches")
@calendar_ns.param('project_id', 'The project identifier')
@calendar_ns.param('event_id', 'The release event identifier')
class ReleaseBranchCollection(Resource):
    """Collection endpoint for release branches."""
    
    @calendar_ns.doc('list_release_branches')
    @calendar_ns.response(200, 'Success')
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, event_id):
        """List release branches for a release event."""
        try:
            check_project_permission(project_id, 'read')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            branches = calendar_manager.list_release_branches(event_id)
            
            return {'items': [release_branch_to_dict(b) for b in branches]}, 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('create_release_branch')
    @calendar_ns.expect(release_branch_create_model)
    @calendar_ns.response(201, 'Release branch created', release_branch_response_model)
    @calendar_ns.response(400, 'Validation error', error_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @require_auth
    def post(self, project_id, event_id):
        """Create a new release branch association."""
        try:
            check_project_permission(project_id, 'write')
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.calendar_manager import (
                CalendarManager,
                ReleaseBranchCreateRequest
            )
            
            create_request = ReleaseBranchCreateRequest(
                release_event_id=event_id,
                repository_id=data.get('repository_id'),
                branch_name=data.get('branch_name', '')
            )
            
            calendar_manager = CalendarManager(g.db_session)
            branch = calendar_manager.create_release_branch(
                create_request,
                user_id=g.current_user_id
            )
            
            return release_branch_to_dict(branch), 201
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


@calendar_ns.route("/<int:project_id>/calendar/branches/<int:branch_id>")
@calendar_ns.param('project_id', 'The project identifier')
@calendar_ns.param('branch_id', 'The release branch identifier')
class ReleaseBranchItem(Resource):
    """Individual release branch endpoint."""
    
    @calendar_ns.doc('get_release_branch')
    @calendar_ns.response(200, 'Success', release_branch_response_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, branch_id):
        """Get a release branch by ID."""
        try:
            check_project_permission(project_id, 'read')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            branch = calendar_manager.get_release_branch(branch_id)
            
            if branch is None:
                return not_found_error('ReleaseBranch', str(branch_id))
            
            return release_branch_to_dict(branch), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('delete_release_branch')
    @calendar_ns.response(204, 'Release branch deleted')
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, branch_id):
        """Delete a release branch association."""
        try:
            check_project_permission(project_id, 'write')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            calendar_manager.delete_release_branch(branch_id, user_id=g.current_user_id)
            
            return '', 204
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Merge Event Endpoints
# =============================================================================

@calendar_ns.route("/<int:project_id>/calendar/release-events/<int:event_id>/merges")
@calendar_ns.param('project_id', 'The project identifier')
@calendar_ns.param('event_id', 'The release event identifier')
class MergeEventCollection(Resource):
    """Collection endpoint for merge events."""
    
    @calendar_ns.doc('list_merge_events')
    @calendar_ns.response(200, 'Success')
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, event_id):
        """List merge events for a release event."""
        try:
            check_project_permission(project_id, 'read')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            merges = calendar_manager.list_merge_events(event_id)
            
            return {'items': [merge_event_to_dict(m) for m in merges]}, 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('create_merge_event')
    @calendar_ns.expect(merge_event_create_model)
    @calendar_ns.response(201, 'Merge event created', merge_event_response_model)
    @calendar_ns.response(400, 'Validation error', error_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @require_auth
    def post(self, project_id, event_id):
        """Create a new merge event."""
        try:
            check_project_permission(project_id, 'write')
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.calendar_manager import (
                CalendarManager,
                MergeEventCreateRequest
            )
            
            create_request = MergeEventCreateRequest(
                release_event_id=event_id,
                repository_id=data.get('repository_id'),
                source_branch=data.get('source_branch', ''),
                target_branch=data.get('target_branch', ''),
                scheduled_time=data.get('scheduled_time')
            )
            
            calendar_manager = CalendarManager(g.db_session)
            merge = calendar_manager.create_merge_event(
                create_request,
                user_id=g.current_user_id
            )
            
            return merge_event_to_dict(merge), 201
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


@calendar_ns.route("/<int:project_id>/calendar/merges/<int:merge_id>")
@calendar_ns.param('project_id', 'The project identifier')
@calendar_ns.param('merge_id', 'The merge event identifier')
class MergeEventItem(Resource):
    """Individual merge event endpoint."""
    
    @calendar_ns.doc('get_merge_event')
    @calendar_ns.response(200, 'Success', merge_event_response_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, merge_id):
        """Get a merge event by ID."""
        try:
            check_project_permission(project_id, 'read')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            merge = calendar_manager.get_merge_event(merge_id)
            
            if merge is None:
                return not_found_error('MergeEvent', str(merge_id))
            
            return merge_event_to_dict(merge), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('update_merge_event')
    @calendar_ns.expect(merge_event_create_model)
    @calendar_ns.response(200, 'Merge event updated', merge_event_response_model)
    @calendar_ns.response(400, 'Validation error', error_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @require_auth
    def put(self, project_id, merge_id):
        """Update a merge event."""
        try:
            check_project_permission(project_id, 'write')
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.calendar_manager import (
                CalendarManager,
                MergeEventUpdateRequest
            )
            
            update_request = MergeEventUpdateRequest(
                source_branch=data.get('source_branch'),
                target_branch=data.get('target_branch'),
                scheduled_time=data.get('scheduled_time'),
                status=data.get('status')
            )
            
            calendar_manager = CalendarManager(g.db_session)
            merge = calendar_manager.update_merge_event(
                merge_id,
                update_request,
                user_id=g.current_user_id
            )
            
            return merge_event_to_dict(merge), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('delete_merge_event')
    @calendar_ns.response(204, 'Merge event deleted')
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, merge_id):
        """Delete a merge event."""
        try:
            check_project_permission(project_id, 'admin')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            calendar_manager.delete_merge_event(merge_id, user_id=g.current_user_id)
            
            return '', 204
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Pull Event Endpoints
# =============================================================================

@calendar_ns.route("/<int:project_id>/calendar/release-events/<int:event_id>/pulls")
@calendar_ns.param('project_id', 'The project identifier')
@calendar_ns.param('event_id', 'The release event identifier')
class PullEventCollection(Resource):
    """Collection endpoint for pull events."""
    
    @calendar_ns.doc('list_pull_events')
    @calendar_ns.response(200, 'Success')
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, event_id):
        """List pull events for a release event."""
        try:
            check_project_permission(project_id, 'read')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            pulls = calendar_manager.list_pull_events(event_id)
            
            return {'items': [pull_event_to_dict(p) for p in pulls]}, 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('create_pull_event')
    @calendar_ns.expect(pull_event_create_model)
    @calendar_ns.response(201, 'Pull event created', pull_event_response_model)
    @calendar_ns.response(400, 'Validation error', error_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @require_auth
    def post(self, project_id, event_id):
        """Create a new pull event."""
        try:
            check_project_permission(project_id, 'write')
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.calendar_manager import (
                CalendarManager,
                PullEventCreateRequest
            )
            
            create_request = PullEventCreateRequest(
                release_event_id=event_id,
                repository_id=data.get('repository_id'),
                source_branch=data.get('source_branch', ''),
                target_branch=data.get('target_branch', ''),
                scheduled_time=data.get('scheduled_time')
            )
            
            calendar_manager = CalendarManager(g.db_session)
            pull = calendar_manager.create_pull_event(
                create_request,
                user_id=g.current_user_id
            )
            
            return pull_event_to_dict(pull), 201
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


@calendar_ns.route("/<int:project_id>/calendar/pulls/<int:pull_id>")
@calendar_ns.param('project_id', 'The project identifier')
@calendar_ns.param('pull_id', 'The pull event identifier')
class PullEventItem(Resource):
    """Individual pull event endpoint."""
    
    @calendar_ns.doc('get_pull_event')
    @calendar_ns.response(200, 'Success', pull_event_response_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, pull_id):
        """Get a pull event by ID."""
        try:
            check_project_permission(project_id, 'read')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            pull = calendar_manager.get_pull_event(pull_id)
            
            if pull is None:
                return not_found_error('PullEvent', str(pull_id))
            
            return pull_event_to_dict(pull), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('update_pull_event')
    @calendar_ns.expect(pull_event_create_model)
    @calendar_ns.response(200, 'Pull event updated', pull_event_response_model)
    @calendar_ns.response(400, 'Validation error', error_model)
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @require_auth
    def put(self, project_id, pull_id):
        """Update a pull event."""
        try:
            check_project_permission(project_id, 'write')
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.calendar_manager import (
                CalendarManager,
                PullEventUpdateRequest
            )
            
            update_request = PullEventUpdateRequest(
                source_branch=data.get('source_branch'),
                target_branch=data.get('target_branch'),
                scheduled_time=data.get('scheduled_time'),
                status=data.get('status')
            )
            
            calendar_manager = CalendarManager(g.db_session)
            pull = calendar_manager.update_pull_event(
                pull_id,
                update_request,
                user_id=g.current_user_id
            )
            
            return pull_event_to_dict(pull), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @calendar_ns.doc('delete_pull_event')
    @calendar_ns.response(204, 'Pull event deleted')
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, pull_id):
        """Delete a pull event."""
        try:
            check_project_permission(project_id, 'admin')
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            calendar_manager.delete_pull_event(pull_id, user_id=g.current_user_id)
            
            return '', 204
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Calendar View Endpoint
# =============================================================================

@calendar_ns.route("/<int:project_id>/calendar")
@calendar_ns.param('project_id', 'The project identifier')
class CalendarView(Resource):
    """Calendar view endpoint for aggregated calendar events."""
    
    @calendar_ns.doc('get_calendar_view')
    @calendar_ns.param('start_date', 'Start date for calendar view (ISO format)', type=str)
    @calendar_ns.param('end_date', 'End date for calendar view (ISO format)', type=str)
    @calendar_ns.param('event_types', 'Event types to include (comma-separated)', type=str)
    @calendar_ns.response(200, 'Success')
    @calendar_ns.response(401, 'Unauthorized', error_model)
    @calendar_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id):
        """Get aggregated calendar view for a project."""
        try:
            check_project_permission(project_id, 'read')
            
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            event_types_str = request.args.get('event_types')
            
            event_types = None
            if event_types_str:
                event_types = [t.strip() for t in event_types_str.split(',') if t.strip()]
            
            from automojo.pychestrate.core.managers.calendar_manager import CalendarManager
            
            calendar_manager = CalendarManager(g.db_session)
            events = calendar_manager.get_calendar_view(
                project_id=project_id,
                start_date=start_date,
                end_date=end_date,
                event_types=event_types
            )
            
            # Convert events to dict format
            items = []
            for event in events:
                items.append({
                    'id': event.id,
                    'type': event.type,
                    'name': event.name,
                    'start_time': event.start_time.isoformat() if event.start_time else None,
                    'end_time': event.end_time.isoformat() if event.end_time else None,
                    'status': event.status.value if hasattr(event.status, 'value') else event.status,
                    'metadata': event.metadata if hasattr(event, 'metadata') else {}
                })
            
            return {'items': items}, 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Namespace Publishing
# =============================================================================

def publish_namespaces(version_prefix):
    """
    Publish the calendar namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (calendar_ns, "".join([version_prefix, CALENDAR_NAMESPACE_PATH]))
    ]
    return ns_list
