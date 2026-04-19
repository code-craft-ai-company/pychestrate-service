"""
.. module:: sessions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for session management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for session management:
- GET /sessions - list active sessions
- DELETE /sessions/{id} - terminate session

Requirements: 5.3, 5.4
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
    not_found_error,
    internal_error,
    create_error_model,
    AuthenticationError,
    AuthorizationError,
)


# =============================================================================
# Namespace Configuration
# =============================================================================

SESSIONS_NAMESPACE_PATH = "/config/sessions"

sessions_ns = Namespace(
    "Sessions v1",
    description="Session management endpoints for system configuration"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(sessions_ns)

session_response_model = sessions_ns.model('SessionResponse', {
    'session_id': fields.Integer(required=True, description='Session ID'),
    'user_id': fields.String(required=True, description='User ID'),
    'username': fields.String(required=True, description='Username'),
    'created_at': fields.DateTime(required=True, description='Session creation time'),
    'last_activity': fields.DateTime(required=True, description='Last activity time'),
    'expires_at': fields.DateTime(required=True, description='Session expiration time'),
    'client_ip': fields.String(description='Client IP address'),
    'user_agent': fields.String(description='Client user agent')
})

session_list_model = sessions_ns.model('SessionList', {
    'items': fields.List(fields.Nested(session_response_model), description='List of sessions'),
    'total': fields.Integer(required=True, description='Total number of sessions'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})


# =============================================================================
# Helper Functions
# =============================================================================

def session_info_to_dict(session_info):
    """Convert SessionInfo dataclass to dict."""
    return {
        'session_id': session_info.session_id,
        'user_id': session_info.user_id,
        'username': session_info.username,
        'created_at': session_info.created_at.isoformat() if session_info.created_at else None,
        'last_activity': session_info.last_activity.isoformat() if session_info.last_activity else None,
        'expires_at': session_info.expires_at.isoformat() if session_info.expires_at else None,
        'client_ip': session_info.client_ip or '',
        'user_agent': session_info.user_agent or ''
    }


# =============================================================================
# Endpoints
# =============================================================================

@sessions_ns.route("/")
class SessionCollection(Resource):
    """Session collection resource for listing active sessions."""
    
    @sessions_ns.doc('list_sessions')
    @sessions_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @sessions_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @sessions_ns.param('user_id', 'Filter by user ID', type=str)
    @sessions_ns.response(200, 'Success', session_list_model)
    @sessions_ns.response(401, 'Unauthorized', error_model)
    @sessions_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('sessions.read')
    def get(self):
        """
        List active sessions with optional user filter.
        
        Requirements: 5.3
        """
        try:
            offset, limit = get_pagination_params()
            user_id = request.args.get('user_id')
            
            from automojo.pychestrate.core.managers.security_manager import SecurityManager
            
            security_manager = SecurityManager(g.db_session)
            sessions = security_manager.list_active_sessions(user_id=user_id)
            
            # Apply pagination manually since list_active_sessions returns all
            total = len(sessions)
            paginated_sessions = sessions[offset:offset + limit]
            
            return paginated_response(
                items=[session_info_to_dict(s) for s in paginated_sessions],
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


@sessions_ns.route("/<int:session_id>")
@sessions_ns.param('session_id', 'The session identifier')
class SessionResource(Resource):
    """Individual session resource for termination."""
    
    @sessions_ns.doc('terminate_session')
    @sessions_ns.response(204, 'Session terminated')
    @sessions_ns.response(401, 'Unauthorized', error_model)
    @sessions_ns.response(403, 'Forbidden', error_model)
    @sessions_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('sessions.delete')
    def delete(self, session_id):
        """
        Terminate a specific session.
        
        Requirements: 5.4
        """
        try:
            from automojo.pychestrate.core.managers.security_manager import SecurityManager
            from automojo.pychestrate.core.orm import Session as SessionModel
            
            # Check if session exists
            session = g.db_session.query(SessionModel).filter(
                SessionModel.id == session_id
            ).first()
            
            if session is None:
                return not_found_error('Session', str(session_id))
            
            security_manager = SecurityManager(g.db_session)
            security_manager.terminate_session(session_id)
            
            return '', 204
            
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
    Publish the sessions namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (sessions_ns, "".join([version_prefix, SESSIONS_NAMESPACE_PATH]))
    ]
    return ns_list
