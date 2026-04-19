"""
.. module:: auth
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for authentication

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for authentication:
- POST /auth/login - authenticate
- POST /auth/logout - logout
- POST /auth/password-reset - request reset
- POST /auth/password-reset/confirm - complete reset

Requirements: 2.1, 2.3, 2.5, 2.6
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import request, g
from flask_restx import Namespace, Resource, fields

from .base import (
    require_auth,
    get_db_session,
    error_response,
    validation_error,
    internal_error,
    create_error_model,
    AuthenticationError,
)


# =============================================================================
# Namespace Configuration
# =============================================================================

AUTH_NAMESPACE_PATH = "/config/auth"

auth_ns = Namespace(
    "Auth v1",
    description="Authentication endpoints for system configuration"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(auth_ns)

login_request_model = auth_ns.model('LoginRequest', {
    'username': fields.String(required=True, description='Username'),
    'password': fields.String(required=True, description='Password')
})

login_response_model = auth_ns.model('LoginResponse', {
    'token': fields.String(required=True, description='Authentication token'),
    'expires_at': fields.DateTime(required=True, description='Token expiration time'),
    'user_id': fields.String(required=True, description='User ID'),
    'username': fields.String(required=True, description='Username'),
    'csrf_token': fields.String(required=True, description='CSRF token for the session')
})

password_reset_request_model = auth_ns.model('PasswordResetRequest', {
    'username': fields.String(required=True, description='Username'),
    'email': fields.String(required=True, description='Email address')
})

password_reset_confirm_model = auth_ns.model('PasswordResetConfirm', {
    'username': fields.String(required=True, description='Username'),
    'token': fields.String(required=True, description='Reset token'),
    'new_password': fields.String(required=True, description='New password')
})


# =============================================================================
# Endpoints
# =============================================================================

@auth_ns.route("/login")
class LoginResource(Resource):
    """Login resource for user authentication."""
    
    @auth_ns.doc('login')
    @auth_ns.expect(login_request_model)
    @auth_ns.response(200, 'Login successful', login_response_model)
    @auth_ns.response(400, 'Validation error', error_model)
    @auth_ns.response(401, 'Invalid credentials', error_model)
    def post(self):
        """
        Authenticate user and create session.
        
        Requirements: 2.1
        """
        db_session = None
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            username = data.get('username', '')
            password = data.get('password', '')
            
            if not username:
                return validation_error("Username required", "username")
            
            if not password:
                return validation_error("Password required", "password")
            
            # Get client info
            client_ip = request.remote_addr or ''
            user_agent = request.headers.get('User-Agent', '')
            
            db_session = get_db_session()
            
            from automojo.pychestrate.core.managers.security_manager import (
                SecurityManager,
                AuthRequest,
                AuthenticationError as SecurityAuthError
            )
            
            security_manager = SecurityManager(db_session)
            
            auth_request = AuthRequest(
                username=username,
                password=password,
                client_ip=client_ip,
                user_agent=user_agent
            )
            
            auth_response = security_manager.authenticate(auth_request)
            
            return {
                'token': auth_response.token,
                'expires_at': auth_response.expires_at.isoformat(),
                'user_id': auth_response.user_id,
                'username': auth_response.username,
                'csrf_token': auth_response.csrf_token
            }, 200
            
        except SecurityAuthError:
            # Generic error - don't reveal which credential was wrong
            return error_response('UNAUTHORIZED', 'Invalid credentials', None, 401)
        except Exception as e:
            return internal_error(str(e))
        finally:
            if db_session:
                db_session.close()


@auth_ns.route("/logout")
class LogoutResource(Resource):
    """Logout resource for session termination."""
    
    @auth_ns.doc('logout')
    @auth_ns.response(204, 'Logout successful')
    @auth_ns.response(401, 'Unauthorized', error_model)
    @require_auth
    def post(self):
        """
        Logout and invalidate current session.
        
        Requirements: 2.3
        """
        try:
            from automojo.pychestrate.core.managers.security_manager import SecurityManager
            
            # Get the token from the Authorization header
            auth_header = request.headers.get('Authorization', '')
            token = auth_header[7:] if auth_header.startswith('Bearer ') else ''
            
            security_manager = SecurityManager(g.db_session)
            security_manager.logout(token)
            
            return '', 204
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except Exception as e:
            return internal_error(str(e))


@auth_ns.route("/password-reset")
class PasswordResetRequestResource(Resource):
    """Password reset request resource."""
    
    @auth_ns.doc('request_password_reset')
    @auth_ns.expect(password_reset_request_model)
    @auth_ns.response(200, 'Reset email sent if user exists')
    @auth_ns.response(400, 'Validation error', error_model)
    def post(self):
        """
        Request a password reset.
        
        Always returns success to prevent user enumeration.
        
        Requirements: 2.5
        """
        db_session = None
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            username = data.get('username', '')
            email = data.get('email', '')
            
            if not username:
                return validation_error("Username required", "username")
            
            if not email:
                return validation_error("Email required", "email")
            
            db_session = get_db_session()
            
            from automojo.pychestrate.core.managers.security_manager import (
                SecurityManager,
                PasswordResetRequest
            )
            
            security_manager = SecurityManager(db_session)
            
            reset_request = PasswordResetRequest(
                username=username,
                email=email
            )
            
            try:
                security_manager.request_password_reset(reset_request)
            except Exception:
                # Silently ignore errors to prevent user enumeration
                pass
            
            # Always return success to prevent user enumeration
            return {'message': 'If the user exists, a reset email has been sent'}, 200
            
        except Exception as e:
            return internal_error(str(e))
        finally:
            if db_session:
                db_session.close()


@auth_ns.route("/password-reset/confirm")
class PasswordResetConfirmResource(Resource):
    """Password reset confirmation resource."""
    
    @auth_ns.doc('confirm_password_reset')
    @auth_ns.expect(password_reset_confirm_model)
    @auth_ns.response(200, 'Password reset successful')
    @auth_ns.response(400, 'Validation error or invalid token', error_model)
    def post(self):
        """
        Complete password reset with token.
        
        Requirements: 2.6
        """
        db_session = None
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            username = data.get('username', '')
            token = data.get('token', '')
            new_password = data.get('new_password', '')
            
            if not username:
                return validation_error("Username required", "username")
            
            if not token:
                return validation_error("Token required", "token")
            
            if not new_password:
                return validation_error("New password required", "new_password")
            
            db_session = get_db_session()
            
            from automojo.pychestrate.core.managers.security_manager import (
                SecurityManager,
                PasswordResetTokenError,
                PasswordValidationError,
                PasswordHistoryError
            )
            
            security_manager = SecurityManager(db_session)
            
            security_manager.reset_password(username, token, new_password)
            
            return {'message': 'Password reset successful'}, 200
            
        except PasswordResetTokenError as e:
            return error_response('INVALID_TOKEN', str(e), None, 400)
        except PasswordValidationError as e:
            return validation_error(e.message, 'new_password', {'violations': e.violations})
        except PasswordHistoryError as e:
            return validation_error(str(e), 'new_password')
        except Exception as e:
            return internal_error(str(e))
        finally:
            if db_session:
                db_session.close()


# =============================================================================
# Namespace Publishing
# =============================================================================

def publish_namespaces(version_prefix):
    """
    Publish the auth namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (auth_ns, "".join([version_prefix, AUTH_NAMESPACE_PATH]))
    ]
    return ns_list
