"""
.. module:: base
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Base utilities for config REST API endpoints

.. moduleauthor:: Automation Mojo LLC

This module provides:
- Authentication decorator for bearer token validation
- Error handling utilities
- Common response models
- Database session management

Requirements: 9.1, 9.2, 9.3, 9.6
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import functools

from flask import request, g
from flask_restx import fields, Namespace

from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS


# =============================================================================
# Error Response Model
# =============================================================================

def create_error_model(ns: Namespace):
    """
    Create a standard error response model for a namespace.
    
    :param ns: The Flask-RestX namespace
    :returns: The error model
    """
    return ns.model('ErrorResponse', {
        'error_code': fields.String(required=True, description='Error code identifier'),
        'message': fields.String(required=True, description='Human-readable error message'),
        'details': fields.Raw(description='Additional error details')
    })


# =============================================================================
# Pagination Model
# =============================================================================

def create_pagination_model(ns: Namespace, item_model, name: str):
    """
    Create a paginated response model for a namespace.
    
    :param ns: The Flask-RestX namespace
    :param item_model: The model for individual items
    :param name: The name for the paginated model
    :returns: The paginated model
    """
    return ns.model(name, {
        'items': fields.List(fields.Nested(item_model), description='List of items'),
        'total': fields.Integer(required=True, description='Total number of items'),
        'offset': fields.Integer(required=True, description='Current offset'),
        'limit': fields.Integer(required=True, description='Items per page')
    })


# =============================================================================
# Database Session Helper
# =============================================================================

def get_db_session():
    """
    Get a database session from the session factory.
    
    :returns: SQLAlchemy database session
    """
    if SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY is None:
        raise RuntimeError("Database session factory not initialized")
    
    return SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY()


# =============================================================================
# Authentication Decorator
# =============================================================================

class AuthenticationError(Exception):
    """Exception raised when authentication fails."""
    
    def __init__(self, message: str = "Authentication required"):
        self.message = message
        super().__init__(self.message)


class AuthorizationError(Exception):
    """Exception raised when authorization fails."""
    
    def __init__(self, message: str = "Permission denied", permission: str = None):
        self.message = message
        self.permission = permission
        super().__init__(self.message)


def require_auth(f):
    """
    Decorator that requires bearer token authentication.
    
    Validates the Authorization header and sets g.current_user and g.session_info
    on successful authentication.
    
    Requirements: 9.2
    
    :param f: The function to wrap
    :returns: The wrapped function
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header:
            raise AuthenticationError("Authorization header required")
        
        if not auth_header.startswith('Bearer '):
            raise AuthenticationError("Invalid authorization format. Use 'Bearer <token>'")
        
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        
        if not token:
            raise AuthenticationError("Token required")
        
        # Validate the token using SecurityManager
        db_session = get_db_session()
        try:
            from automojo.pychestrate.core.managers.security_manager import SecurityManager
            
            security_manager = SecurityManager(db_session)
            session_info = security_manager.validate_token(token)
            
            if session_info is None:
                raise AuthenticationError("Invalid or expired token")
            
            # Store session info in Flask's g object for use in the endpoint
            g.session_info = session_info
            g.current_user_id = session_info.user_id
            g.current_username = session_info.username
            g.db_session = db_session
            
            return f(*args, **kwargs)
        except AuthenticationError:
            db_session.close()
            raise
        except Exception as e:
            db_session.close()
            raise AuthenticationError(f"Authentication failed: {str(e)}")
    
    return decorated


def require_permission(permission: str):
    """
    Decorator that requires a specific permission.
    
    Must be used after @require_auth decorator.
    
    :param permission: The permission name required (e.g., 'users.create')
    :returns: Decorator function
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(g, 'current_user_id'):
                raise AuthenticationError("Authentication required")
            
            db_session = g.db_session
            
            from automojo.pychestrate.core.managers.security_manager import SecurityManager
            
            security_manager = SecurityManager(db_session)
            
            if not security_manager.check_permission(g.current_user_id, permission):
                raise AuthorizationError(f"Permission '{permission}' required", permission)
            
            return f(*args, **kwargs)
        
        return decorated
    
    return decorator


# =============================================================================
# Error Response Helpers
# =============================================================================

def error_response(error_code: str, message: str, details: dict = None, status_code: int = 400):
    """
    Create a standardized error response.
    
    Requirements: 9.3
    
    :param error_code: Error code identifier
    :param message: Human-readable error message
    :param details: Additional error details
    :param status_code: HTTP status code
    :returns: Tuple of (response_dict, status_code)
    """
    response = {
        'error_code': error_code,
        'message': message,
        'details': details or {}
    }
    return response, status_code


def validation_error(message: str, field: str = None, details: dict = None):
    """
    Create a validation error response.
    
    :param message: Error message
    :param field: Field that failed validation
    :param details: Additional details
    :returns: Tuple of (response_dict, 400)
    """
    error_details = details or {}
    if field:
        error_details['field'] = field
    
    return error_response('VALIDATION_ERROR', message, error_details, 400)


def not_found_error(resource: str, identifier: str = None):
    """
    Create a not found error response.
    
    :param resource: Resource type that was not found
    :param identifier: Resource identifier
    :returns: Tuple of (response_dict, 404)
    """
    details = {'resource': resource}
    if identifier:
        details['identifier'] = identifier
    
    return error_response('NOT_FOUND', f"{resource} not found", details, 404)


def unauthorized_error(message: str = "Authentication required"):
    """
    Create an unauthorized error response.
    
    :param message: Error message
    :returns: Tuple of (response_dict, 401)
    """
    return error_response('UNAUTHORIZED', message, None, 401)


def forbidden_error(message: str = "Permission denied", permission: str = None):
    """
    Create a forbidden error response.
    
    :param message: Error message
    :param permission: Permission that was required
    :returns: Tuple of (response_dict, 403)
    """
    details = {}
    if permission:
        details['required_permission'] = permission
    
    return error_response('FORBIDDEN', message, details, 403)


def conflict_error(message: str, field: str = None):
    """
    Create a conflict error response.
    
    :param message: Error message
    :param field: Field that caused the conflict
    :returns: Tuple of (response_dict, 409)
    """
    details = {}
    if field:
        details['field'] = field
    
    return error_response('CONFLICT', message, details, 409)


def internal_error(message: str = "Internal server error"):
    """
    Create an internal server error response.
    
    :param message: Error message
    :returns: Tuple of (response_dict, 500)
    """
    return error_response('INTERNAL_ERROR', message, None, 500)


# =============================================================================
# Pagination Helpers
# =============================================================================

def get_pagination_params():
    """
    Get pagination parameters from request args.
    
    Requirements: 9.4
    
    :returns: Tuple of (offset, limit)
    """
    try:
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 50))
    except ValueError:
        offset = 0
        limit = 50
    
    # Enforce limits
    offset = max(0, offset)
    limit = max(1, min(100, limit))
    
    return offset, limit


def paginated_response(items: list, total: int, offset: int, limit: int):
    """
    Create a paginated response.
    
    :param items: List of items for current page
    :param total: Total number of items
    :param offset: Current offset
    :param limit: Items per page
    :returns: Paginated response dict
    """
    return {
        'items': items,
        'total': total,
        'offset': offset,
        'limit': limit
    }
