"""
.. module:: watches
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for project watch management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for project watch management:
- Watch CRUD endpoints
- Watch trigger log endpoints

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

WATCHES_NAMESPACE_PATH = "/projects"

watches_ns = Namespace(
    "Project Watches v1",
    description="Project watch management endpoints"
)


# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(watches_ns)

watch_create_model = watches_ns.model('WatchCreate', {
    'name': fields.String(required=True, description='Watch name'),
    'watch_type': fields.String(required=True, description='Watch type (repository, schedule, webhook)'),
    'repository_id': fields.Integer(description='Repository ID for repository watches'),
    'branch_pattern': fields.String(description='Branch pattern to watch'),
    'path_pattern': fields.String(description='Path pattern to watch'),
    'schedule': fields.String(description='Cron schedule for schedule watches'),
    'webhook_secret': fields.String(description='Webhook secret for webhook watches'),
    'trigger_action': fields.String(required=True, description='Action to trigger (build, test, deploy)'),
    'trigger_spec_id': fields.Integer(description='Spec ID to trigger'),
    'enabled': fields.Boolean(description='Whether watch is enabled', default=True),
    'description': fields.String(description='Watch description')
})

watch_update_model = watches_ns.model('WatchUpdate', {
    'name': fields.String(description='Watch name'),
    'branch_pattern': fields.String(description='Branch pattern to watch'),
    'path_pattern': fields.String(description='Path pattern to watch'),
    'schedule': fields.String(description='Cron schedule for schedule watches'),
    'trigger_action': fields.String(description='Action to trigger'),
    'trigger_spec_id': fields.Integer(description='Spec ID to trigger'),
    'enabled': fields.Boolean(description='Whether watch is enabled'),
    'description': fields.String(description='Watch description')
})

watch_response_model = watches_ns.model('WatchResponse', {
    'id': fields.Integer(required=True, description='Watch ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'name': fields.String(required=True, description='Watch name'),
    'watch_type': fields.String(required=True, description='Watch type'),
    'repository_id': fields.Integer(description='Repository ID'),
    'repository_name': fields.String(description='Repository name'),
    'branch_pattern': fields.String(description='Branch pattern'),
    'path_pattern': fields.String(description='Path pattern'),
    'schedule': fields.String(description='Cron schedule'),
    'trigger_action': fields.String(description='Trigger action'),
    'trigger_spec_id': fields.Integer(description='Trigger spec ID'),
    'enabled': fields.Boolean(description='Whether watch is enabled'),
    'description': fields.String(description='Watch description'),
    'last_triggered': fields.DateTime(description='Last trigger timestamp'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'updated_at': fields.DateTime(description='Last update timestamp')
})


trigger_log_response_model = watches_ns.model('TriggerLogResponse', {
    'id': fields.Integer(required=True, description='Trigger log ID'),
    'watch_id': fields.Integer(required=True, description='Watch ID'),
    'triggered_at': fields.DateTime(required=True, description='Trigger timestamp'),
    'trigger_source': fields.String(description='Trigger source (commit, schedule, webhook)'),
    'trigger_data': fields.Raw(description='Trigger data'),
    'result_status': fields.String(description='Result status'),
    'result_job_id': fields.Integer(description='Result job ID'),
    'error_message': fields.String(description='Error message if failed')
})


# =============================================================================
# Helper Functions
# =============================================================================

def watch_to_dict(watch_response):
    """Convert WatchResponse dataclass to dict."""
    return {
        'id': watch_response.id,
        'project_id': watch_response.project_id,
        'name': watch_response.name,
        'watch_type': watch_response.watch_type.value if hasattr(watch_response.watch_type, 'value') else watch_response.watch_type,
        'repository_id': watch_response.repository_id if hasattr(watch_response, 'repository_id') else None,
        'repository_name': watch_response.repository_name if hasattr(watch_response, 'repository_name') else '',
        'branch_pattern': watch_response.branch_pattern if hasattr(watch_response, 'branch_pattern') else None,
        'path_pattern': watch_response.path_pattern if hasattr(watch_response, 'path_pattern') else None,
        'schedule': watch_response.schedule if hasattr(watch_response, 'schedule') else None,
        'trigger_action': watch_response.trigger_action if hasattr(watch_response, 'trigger_action') else None,
        'trigger_spec_id': watch_response.trigger_spec_id if hasattr(watch_response, 'trigger_spec_id') else None,
        'enabled': watch_response.enabled if hasattr(watch_response, 'enabled') else True,
        'description': watch_response.description if hasattr(watch_response, 'description') else '',
        'last_triggered': watch_response.last_triggered.isoformat() if hasattr(watch_response, 'last_triggered') and watch_response.last_triggered else None,
        'created_at': watch_response.created_at.isoformat() if watch_response.created_at else None,
        'updated_at': watch_response.updated_at.isoformat() if hasattr(watch_response, 'updated_at') and watch_response.updated_at else None
    }


def trigger_log_to_dict(log_response):
    """Convert TriggerLogResponse dataclass to dict."""
    return {
        'id': log_response.id,
        'watch_id': log_response.watch_id,
        'triggered_at': log_response.triggered_at.isoformat() if log_response.triggered_at else None,
        'trigger_source': log_response.trigger_source if hasattr(log_response, 'trigger_source') else None,
        'trigger_data': log_response.trigger_data if hasattr(log_response, 'trigger_data') else {},
        'result_status': log_response.result_status.value if hasattr(log_response.result_status, 'value') else log_response.result_status,
        'result_job_id': log_response.result_job_id if hasattr(log_response, 'result_job_id') else None,
        'error_message': log_response.error_message if hasattr(log_response, 'error_message') else None
    }


# =============================================================================
# Watch Endpoints
# =============================================================================

@watches_ns.route("/<int:project_id>/watches")
@watches_ns.param('project_id', 'The project identifier')
class WatchCollection(Resource):
    """Collection endpoint for watches."""
    
    @watches_ns.doc('list_watches')
    @watches_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @watches_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @watches_ns.param('watch_type', 'Filter by watch type', type=str)
    @watches_ns.param('enabled', 'Filter by enabled status', type=bool)
    @watches_ns.response(200, 'Success')
    @watches_ns.response(401, 'Unauthorized', error_model)
    @watches_ns.response(403, 'Forbidden', error_model)
    @watches_ns.response(404, 'Project not found', error_model)
    @require_auth
    def get(self, project_id):
        """List watches for a project."""
        try:
            check_project_permission(project_id, 'read')
            offset, limit = get_pagination_params()
            watch_type = request.args.get('watch_type')
            enabled_str = request.args.get('enabled')
            enabled = None
            if enabled_str is not None:
                enabled = enabled_str.lower() in ('true', '1', 'yes')
            
            from automojo.pychestrate.core.managers.watch_manager import WatchManager
            
            watch_manager = WatchManager(g.db_session)
            result = watch_manager.list_watches(
                project_id=project_id,
                watch_type=watch_type,
                enabled=enabled,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[watch_to_dict(w) for w in result.watches],
                total=result.total,
                offset=result.offset,
                limit=result.limit
            ), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @watches_ns.doc('create_watch')
    @watches_ns.expect(watch_create_model)
    @watches_ns.response(201, 'Watch created', watch_response_model)
    @watches_ns.response(400, 'Validation error', error_model)
    @watches_ns.response(401, 'Unauthorized', error_model)
    @watches_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def post(self, project_id):
        """Create a new watch."""
        try:
            check_project_permission(project_id, 'write')
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.watch_manager import (
                WatchManager,
                WatchCreateRequest
            )
            
            create_request = WatchCreateRequest(
                project_id=project_id,
                name=data.get('name', ''),
                watch_type=data.get('watch_type', ''),
                repository_id=data.get('repository_id'),
                branch_pattern=data.get('branch_pattern'),
                path_pattern=data.get('path_pattern'),
                schedule=data.get('schedule'),
                webhook_secret=data.get('webhook_secret'),
                trigger_action=data.get('trigger_action', ''),
                trigger_spec_id=data.get('trigger_spec_id'),
                enabled=data.get('enabled', True),
                description=data.get('description', '')
            )
            
            watch_manager = WatchManager(g.db_session)
            watch = watch_manager.create_watch(
                create_request,
                user_id=g.current_user_id
            )
            
            return watch_to_dict(watch), 201
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


@watches_ns.route("/<int:project_id>/watches/<int:watch_id>")
@watches_ns.param('project_id', 'The project identifier')
@watches_ns.param('watch_id', 'The watch identifier')
class WatchItem(Resource):
    """Individual watch endpoint."""
    
    @watches_ns.doc('get_watch')
    @watches_ns.response(200, 'Success', watch_response_model)
    @watches_ns.response(401, 'Unauthorized', error_model)
    @watches_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, watch_id):
        """Get a watch by ID."""
        try:
            check_project_permission(project_id, 'read')
            
            from automojo.pychestrate.core.managers.watch_manager import WatchManager
            
            watch_manager = WatchManager(g.db_session)
            watch = watch_manager.get_watch(watch_id)
            
            if watch is None:
                return not_found_error('Watch', str(watch_id))
            
            return watch_to_dict(watch), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @watches_ns.doc('update_watch')
    @watches_ns.expect(watch_update_model)
    @watches_ns.response(200, 'Watch updated', watch_response_model)
    @watches_ns.response(400, 'Validation error', error_model)
    @watches_ns.response(401, 'Unauthorized', error_model)
    @watches_ns.response(404, 'Not found', error_model)
    @require_auth
    def put(self, project_id, watch_id):
        """Update a watch."""
        try:
            check_project_permission(project_id, 'write')
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.watch_manager import (
                WatchManager,
                WatchUpdateRequest
            )
            
            update_request = WatchUpdateRequest(
                name=data.get('name'),
                branch_pattern=data.get('branch_pattern'),
                path_pattern=data.get('path_pattern'),
                schedule=data.get('schedule'),
                trigger_action=data.get('trigger_action'),
                trigger_spec_id=data.get('trigger_spec_id'),
                enabled=data.get('enabled'),
                description=data.get('description')
            )
            
            watch_manager = WatchManager(g.db_session)
            watch = watch_manager.update_watch(
                watch_id,
                update_request,
                user_id=g.current_user_id
            )
            
            return watch_to_dict(watch), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)
    
    @watches_ns.doc('delete_watch')
    @watches_ns.response(204, 'Watch deleted')
    @watches_ns.response(401, 'Unauthorized', error_model)
    @watches_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, watch_id):
        """Delete a watch."""
        try:
            check_project_permission(project_id, 'admin')
            
            from automojo.pychestrate.core.managers.watch_manager import WatchManager
            
            watch_manager = WatchManager(g.db_session)
            watch_manager.delete_watch(watch_id, user_id=g.current_user_id)
            
            return '', 204
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Watch Trigger Log Endpoints
# =============================================================================

@watches_ns.route("/<int:project_id>/watches/<int:watch_id>/triggers")
@watches_ns.param('project_id', 'The project identifier')
@watches_ns.param('watch_id', 'The watch identifier')
class WatchTriggerLogCollection(Resource):
    """Collection endpoint for watch trigger logs."""
    
    @watches_ns.doc('list_trigger_logs')
    @watches_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @watches_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @watches_ns.param('status', 'Filter by result status', type=str)
    @watches_ns.response(200, 'Success')
    @watches_ns.response(401, 'Unauthorized', error_model)
    @watches_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, watch_id):
        """List trigger logs for a watch."""
        try:
            check_project_permission(project_id, 'read')
            offset, limit = get_pagination_params()
            status = request.args.get('status')
            
            from automojo.pychestrate.core.managers.watch_manager import WatchManager
            
            watch_manager = WatchManager(g.db_session)
            result = watch_manager.list_trigger_logs(
                watch_id=watch_id,
                status=status,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[trigger_log_to_dict(log) for log in result.logs],
                total=result.total,
                offset=result.offset,
                limit=result.limit
            ), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


@watches_ns.route("/<int:project_id>/watches/<int:watch_id>/triggers/<int:log_id>")
@watches_ns.param('project_id', 'The project identifier')
@watches_ns.param('watch_id', 'The watch identifier')
@watches_ns.param('log_id', 'The trigger log identifier')
class WatchTriggerLogItem(Resource):
    """Individual trigger log endpoint."""
    
    @watches_ns.doc('get_trigger_log')
    @watches_ns.response(200, 'Success', trigger_log_response_model)
    @watches_ns.response(401, 'Unauthorized', error_model)
    @watches_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, watch_id, log_id):
        """Get a trigger log by ID."""
        try:
            check_project_permission(project_id, 'read')
            
            from automojo.pychestrate.core.managers.watch_manager import WatchManager
            
            watch_manager = WatchManager(g.db_session)
            log = watch_manager.get_trigger_log(log_id)
            
            if log is None:
                return not_found_error('TriggerLog', str(log_id))
            
            return trigger_log_to_dict(log), 200
            
        except (AuthenticationError, AuthorizationError) as e:
            return exception_to_response(e)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Namespace Publishing
# =============================================================================

def publish_namespaces(version_prefix):
    """
    Publish the watches namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (watches_ns, "".join([version_prefix, WATCHES_NAMESPACE_PATH]))
    ]
    return ns_list
