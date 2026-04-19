"""
.. module:: health
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for resource health monitoring

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for health monitoring:
- PUT /resources/{id}/health - update health status
- GET /resources/{id}/health/history - get health history
- PUT /resources/{id}/health/config - configure health check
- POST /resources/{id}/health/check - run health check

Requirements: 6.1, 6.2, 6.5
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

HEALTH_NAMESPACE_PATH = "/resources"

health_ns = Namespace(
    "Health v1",
    description="Resource health monitoring endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(health_ns)

health_status_update_model = health_ns.model('HealthStatusUpdate', {
    'status': fields.String(required=True, description='Health status (online, offline, degraded, maintenance)'),
    'reason': fields.String(description='Reason for status change')
})

health_config_model = health_ns.model('HealthCheckConfig', {
    'probe_url': fields.String(description='URL to probe for health check'),
    'probe_command': fields.String(description='Command to run for health check'),
    'interval_seconds': fields.Integer(description='Check interval in seconds', default=60),
    'timeout_seconds': fields.Integer(description='Check timeout in seconds', default=10),
    'failure_threshold': fields.Integer(description='Failures before marking unhealthy', default=3),
    'success_threshold': fields.Integer(description='Successes before marking healthy', default=1),
    'enabled': fields.Boolean(description='Whether health check is enabled', default=True)
})

health_config_response_model = health_ns.model('HealthCheckConfigResponse', {
    'id': fields.Integer(required=True, description='Config ID'),
    'resource_id': fields.Integer(required=True, description='Resource ID'),
    'resource_name': fields.String(required=True, description='Resource name'),
    'probe_url': fields.String(description='Probe URL'),
    'probe_command': fields.String(description='Probe command'),
    'interval_seconds': fields.Integer(required=True, description='Check interval'),
    'timeout_seconds': fields.Integer(required=True, description='Check timeout'),
    'failure_threshold': fields.Integer(required=True, description='Failure threshold'),
    'success_threshold': fields.Integer(required=True, description='Success threshold'),
    'consecutive_failures': fields.Integer(required=True, description='Current consecutive failures'),
    'consecutive_successes': fields.Integer(required=True, description='Current consecutive successes'),
    'last_check_time': fields.DateTime(description='Last check timestamp'),
    'last_check_result': fields.Boolean(description='Last check result'),
    'enabled': fields.Boolean(required=True, description='Whether enabled')
})

health_transition_model = health_ns.model('HealthTransition', {
    'id': fields.Integer(required=True, description='Transition ID'),
    'resource_id': fields.Integer(required=True, description='Resource ID'),
    'resource_name': fields.String(required=True, description='Resource name'),
    'old_status': fields.String(required=True, description='Previous status'),
    'new_status': fields.String(required=True, description='New status'),
    'reason': fields.String(description='Reason for change'),
    'triggered_by': fields.String(required=True, description='What triggered the change'),
    'user_id': fields.String(description='User who made the change'),
    'timestamp': fields.DateTime(required=True, description='Transition timestamp')
})

health_history_model = health_ns.model('HealthHistory', {
    'items': fields.List(fields.Nested(health_transition_model), description='List of transitions'),
    'total': fields.Integer(required=True, description='Total number of transitions'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})

health_check_result_model = health_ns.model('HealthCheckResult', {
    'resource_id': fields.Integer(required=True, description='Resource ID'),
    'resource_name': fields.String(required=True, description='Resource name'),
    'healthy': fields.Boolean(required=True, description='Whether check passed'),
    'old_status': fields.String(required=True, description='Status before check'),
    'new_status': fields.String(required=True, description='Status after check'),
    'status_changed': fields.Boolean(required=True, description='Whether status changed'),
    'error_message': fields.String(description='Error message if check failed')
})


# =============================================================================
# Helper Functions
# =============================================================================

def health_config_response_to_dict(config_response):
    """Convert HealthCheckConfigResponse dataclass to dict."""
    return {
        'id': config_response.id,
        'resource_id': config_response.resource_id,
        'resource_name': config_response.resource_name,
        'probe_url': config_response.probe_url,
        'probe_command': config_response.probe_command,
        'interval_seconds': config_response.interval_seconds,
        'timeout_seconds': config_response.timeout_seconds,
        'failure_threshold': config_response.failure_threshold,
        'success_threshold': config_response.success_threshold,
        'consecutive_failures': config_response.consecutive_failures,
        'consecutive_successes': config_response.consecutive_successes,
        'last_check_time': config_response.last_check_time.isoformat() if config_response.last_check_time else None,
        'last_check_result': config_response.last_check_result,
        'enabled': config_response.enabled
    }


def health_transition_to_dict(transition):
    """Convert HealthTransitionResponse dataclass to dict."""
    return {
        'id': transition.id,
        'resource_id': transition.resource_id,
        'resource_name': transition.resource_name,
        'old_status': transition.old_status,
        'new_status': transition.new_status,
        'reason': transition.reason,
        'triggered_by': transition.triggered_by,
        'user_id': transition.user_id,
        'timestamp': transition.timestamp.isoformat() if transition.timestamp else None
    }


def health_check_result_to_dict(result):
    """Convert HealthCheckResult dataclass to dict."""
    return {
        'resource_id': result.resource_id,
        'resource_name': result.resource_name,
        'healthy': result.healthy,
        'old_status': result.old_status,
        'new_status': result.new_status,
        'status_changed': result.status_changed,
        'error_message': result.error_message
    }


# =============================================================================
# Endpoints
# =============================================================================

@health_ns.route("/<int:resource_id>/health")
@health_ns.param('resource_id', 'The resource identifier')
class ResourceHealth(Resource):
    """Resource health status endpoint."""
    
    @health_ns.doc('update_health_status')
    @health_ns.expect(health_status_update_model)
    @health_ns.response(200, 'Health status updated')
    @health_ns.response(400, 'Validation error', error_model)
    @health_ns.response(401, 'Unauthorized', error_model)
    @health_ns.response(403, 'Forbidden', error_model)
    @health_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.update')
    def put(self, resource_id):
        """
        Update resource health status.
        
        Requirements: 6.1
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            status = data.get('status')
            if not status:
                return validation_error("status required", field='status')
            
            from automojo.pychestrate.core.managers.health_monitor import (
                HealthMonitor,
                ResourceNotFoundError,
                InvalidHealthStatusError
            )
            
            health_monitor = HealthMonitor(g.db_session)
            health_monitor.update_health_status(
                resource_id,
                status,
                reason=data.get('reason', ''),
                user_id=g.current_user_id
            )
            
            return {'message': f'Health status updated to {status}'}, 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@health_ns.route("/<int:resource_id>/health/history")
@health_ns.param('resource_id', 'The resource identifier')
class ResourceHealthHistory(Resource):
    """Resource health history endpoint."""
    
    @health_ns.doc('get_health_history')
    @health_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @health_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @health_ns.response(200, 'Success', health_history_model)
    @health_ns.response(401, 'Unauthorized', error_model)
    @health_ns.response(403, 'Forbidden', error_model)
    @health_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self, resource_id):
        """
        Get health status transition history.
        
        Requirements: 6.2
        """
        try:
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.health_monitor import (
                HealthMonitor,
                ResourceNotFoundError
            )
            
            health_monitor = HealthMonitor(g.db_session)
            result = health_monitor.get_health_history(
                resource_id,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[health_transition_to_dict(t) for t in result.transitions],
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


@health_ns.route("/<int:resource_id>/health/config")
@health_ns.param('resource_id', 'The resource identifier')
class ResourceHealthConfig(Resource):
    """Resource health check configuration endpoint."""
    
    @health_ns.doc('get_health_config')
    @health_ns.response(200, 'Success', health_config_response_model)
    @health_ns.response(401, 'Unauthorized', error_model)
    @health_ns.response(403, 'Forbidden', error_model)
    @health_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self, resource_id):
        """
        Get health check configuration.
        
        Requirements: 6.5
        """
        try:
            from automojo.pychestrate.core.managers.health_monitor import (
                HealthMonitor,
                ResourceNotFoundError,
                HealthCheckConfigNotFoundError
            )
            
            health_monitor = HealthMonitor(g.db_session)
            config = health_monitor.get_health_check_config(resource_id)
            
            if config is None:
                return not_found_error('Health check config', str(resource_id))
            
            return health_config_response_to_dict(config), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @health_ns.doc('configure_health_check')
    @health_ns.expect(health_config_model)
    @health_ns.response(200, 'Health check configured', health_config_response_model)
    @health_ns.response(400, 'Validation error', error_model)
    @health_ns.response(401, 'Unauthorized', error_model)
    @health_ns.response(403, 'Forbidden', error_model)
    @health_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.update')
    def put(self, resource_id):
        """
        Configure health check for a resource.
        
        Requirements: 6.5
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.health_monitor import (
                HealthMonitor,
                HealthCheckConfigRequest,
                ResourceNotFoundError,
                InvalidHealthCheckConfigError
            )
            
            # Build the config request
            config_request = HealthCheckConfigRequest(
                resource_id=resource_id,
                probe_url=data.get('probe_url'),
                probe_command=data.get('probe_command'),
                interval_seconds=data.get('interval_seconds', 60),
                timeout_seconds=data.get('timeout_seconds', 10),
                failure_threshold=data.get('failure_threshold', 3),
                success_threshold=data.get('success_threshold', 1),
                enabled=data.get('enabled', True)
            )
            
            health_monitor = HealthMonitor(g.db_session)
            config = health_monitor.configure_health_check(
                config_request,
                user_id=g.current_user_id
            )
            
            return health_config_response_to_dict(config), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@health_ns.route("/<int:resource_id>/health/check")
@health_ns.param('resource_id', 'The resource identifier')
class ResourceHealthCheck(Resource):
    """Resource health check execution endpoint."""
    
    @health_ns.doc('run_health_check')
    @health_ns.response(200, 'Health check executed', health_check_result_model)
    @health_ns.response(401, 'Unauthorized', error_model)
    @health_ns.response(403, 'Forbidden', error_model)
    @health_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.update')
    def post(self, resource_id):
        """
        Run health check for a resource.
        
        Requirements: 6.5
        """
        try:
            from automojo.pychestrate.core.managers.health_monitor import (
                HealthMonitor,
                ResourceNotFoundError,
                HealthCheckConfigNotFoundError
            )
            
            health_monitor = HealthMonitor(g.db_session)
            result = health_monitor.run_health_check(resource_id)
            
            return health_check_result_to_dict(result), 200
            
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
    Publish the health namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (health_ns, "".join([version_prefix, HEALTH_NAMESPACE_PATH]))
    ]
    return ns_list
