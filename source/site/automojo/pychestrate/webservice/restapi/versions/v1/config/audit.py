"""
.. module:: audit
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for audit log management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for audit log management:
- GET /audit-logs - query audit logs

Requirements: 8.5
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from flask import request, g
from flask_restx import Namespace, Resource, fields

from .base import (
    require_auth,
    require_permission,
    get_pagination_params,
    paginated_response,
    error_response,
    validation_error,
    internal_error,
    create_error_model,
    AuthenticationError,
    AuthorizationError,
)


# =============================================================================
# Namespace Configuration
# =============================================================================

AUDIT_NAMESPACE_PATH = "/config/audit-logs"

audit_ns = Namespace(
    "Audit v1",
    description="Audit log endpoints for system configuration"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(audit_ns)

audit_log_model = audit_ns.model('AuditLogEntry', {
    'id': fields.Integer(required=True, description='Log entry ID'),
    'event_type': fields.String(required=True, description='Event type'),
    'timestamp': fields.DateTime(required=True, description='Event timestamp'),
    'user_id': fields.String(description='User ID who performed the action'),
    'username': fields.String(description='Username who performed the action'),
    'target_user_id': fields.String(description='Target user ID (if applicable)'),
    'target_username': fields.String(description='Target username (if applicable)'),
    'client_ip': fields.String(description='Client IP address'),
    'details': fields.Raw(description='Additional event details')
})

audit_log_list_model = audit_ns.model('AuditLogList', {
    'items': fields.List(fields.Nested(audit_log_model), description='List of audit log entries'),
    'total': fields.Integer(required=True, description='Total number of entries'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})


# =============================================================================
# Helper Functions
# =============================================================================

def audit_entry_to_dict(entry):
    """Convert AuditLogEntry dataclass to dict."""
    return {
        'id': entry.id,
        'event_type': entry.event_type.value if hasattr(entry.event_type, 'value') else str(entry.event_type),
        'timestamp': entry.timestamp.isoformat() if entry.timestamp else None,
        'user_id': entry.user_id,
        'username': entry.username or '',
        'target_user_id': entry.target_user_id,
        'target_username': entry.target_username or '',
        'client_ip': entry.client_ip or '',
        'details': entry.details or {}
    }


# =============================================================================
# Endpoints
# =============================================================================

@audit_ns.route("/")
class AuditLogCollection(Resource):
    """Audit log collection resource for querying logs."""
    
    @audit_ns.doc('query_audit_logs')
    @audit_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @audit_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @audit_ns.param('event_type', 'Filter by event type (comma-separated for multiple)', type=str)
    @audit_ns.param('user_id', 'Filter by user ID who performed the action', type=str)
    @audit_ns.param('target_user_id', 'Filter by target user ID', type=str)
    @audit_ns.param('start_date', 'Filter by start date (ISO format)', type=str)
    @audit_ns.param('end_date', 'Filter by end date (ISO format)', type=str)
    @audit_ns.response(200, 'Success', audit_log_list_model)
    @audit_ns.response(400, 'Validation error', error_model)
    @audit_ns.response(401, 'Unauthorized', error_model)
    @audit_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('audit.read')
    def get(self):
        """
        Query audit logs with filtering and pagination.
        
        Requirements: 8.5
        """
        try:
            offset, limit = get_pagination_params()
            
            # Parse filter parameters
            event_type_str = request.args.get('event_type')
            user_id = request.args.get('user_id')
            target_user_id = request.args.get('target_user_id')
            start_date_str = request.args.get('start_date')
            end_date_str = request.args.get('end_date')
            
            # Parse event types
            event_types = None
            if event_type_str:
                from automojo.pychestrate.core.managers.audit_logger import AuditEventType
                
                event_type_names = [e.strip() for e in event_type_str.split(',')]
                event_types = []
                for name in event_type_names:
                    try:
                        event_types.append(AuditEventType(name))
                    except ValueError:
                        return validation_error(
                            f"Invalid event type: {name}",
                            "event_type"
                        )
            
            # Parse dates
            start_date = None
            end_date = None
            
            if start_date_str:
                try:
                    start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                except ValueError:
                    return validation_error(
                        "Invalid start_date format. Use ISO format (e.g., 2024-01-01T00:00:00)",
                        "start_date"
                    )
            
            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                except ValueError:
                    return validation_error(
                        "Invalid end_date format. Use ISO format (e.g., 2024-01-01T00:00:00)",
                        "end_date"
                    )
            
            from automojo.pychestrate.core.managers.audit_logger import (
                AuditLogger,
                AuditLogQuery
            )
            
            audit_logger = AuditLogger(g.db_session)
            
            query = AuditLogQuery(
                event_types=event_types,
                user_id=user_id,
                target_user_id=target_user_id,
                start_date=start_date,
                end_date=end_date,
                offset=offset,
                limit=limit
            )
            
            result = audit_logger.query_logs(query)
            
            return paginated_response(
                items=[audit_entry_to_dict(e) for e in result.entries],
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


# =============================================================================
# Namespace Publishing
# =============================================================================

def publish_namespaces(version_prefix):
    """
    Publish the audit namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (audit_ns, "".join([version_prefix, AUDIT_NAMESPACE_PATH]))
    ]
    return ns_list
