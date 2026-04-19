"""
.. module:: base
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Base utilities for resource REST API endpoints

.. moduleauthor:: Automation Mojo LLC

This module provides:
- Authentication decorator for bearer token validation
- Error handling utilities
- Common response models
- Database session management

Requirements: 10.1, 10.2, 10.3, 10.6
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
    
    Requirements: 10.2
    
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
    
    :param permission: The permission name required (e.g., 'resources.create')
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
    
    Requirements: 10.3
    
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
    
    Requirements: 10.4
    
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


# =============================================================================
# Exception to HTTP Status Code Mapping
# =============================================================================

# Map of exception types to (error_code, status_code) tuples
EXCEPTION_MAP = {
    # Authentication/Authorization errors
    'AuthenticationError': ('UNAUTHORIZED', 401),
    'AuthorizationError': ('FORBIDDEN', 403),
    
    # Resource Manager errors
    'ResourceValidationError': ('VALIDATION_ERROR', 400),
    'ResourceNotFoundError': ('NOT_FOUND', 404),
    'DuplicateResourceError': ('CONFLICT', 409),
    'ResourceHasAllocationsError': ('CONFLICT', 409),
    'PoolNotFoundError': ('NOT_FOUND', 404),
    'PoolHasResourcesError': ('CONFLICT', 409),
    'TagNotFoundError': ('NOT_FOUND', 404),
    
    # Allocation Manager errors
    'AllocationError': ('ALLOCATION_ERROR', 400),
    'ResourceUnavailableError': ('RESOURCE_UNAVAILABLE', 409),
    'ResourceOfflineError': ('RESOURCE_OFFLINE', 409),
    'CapacityExceededError': ('CAPACITY_EXCEEDED', 409),
    'AllocationNotFoundError': ('NOT_FOUND', 404),
    'NotAllocationOwnerError': ('FORBIDDEN', 403),
    'ReservationConflictError': ('CONFLICT', 409),
    'ReservationNotFoundError': ('NOT_FOUND', 404),
    'InvalidTimeWindowError': ('VALIDATION_ERROR', 400),
    'CheckoutPermissionDeniedError': ('FORBIDDEN', 403),
    'LockTimeoutError': ('SERVICE_UNAVAILABLE', 503),
    'ConcurrentModificationError': ('CONFLICT', 409),
    'NoMatchingResourceError': ('NOT_FOUND', 404),
    
    # IP Pool Manager errors
    'IPPoolValidationError': ('VALIDATION_ERROR', 400),
    'IPPoolNotFoundError': ('NOT_FOUND', 404),
    'DuplicateIPPoolError': ('CONFLICT', 409),
    'CIDROverlapError': ('CONFLICT', 409),
    'IPPoolHasAllocationsError': ('CONFLICT', 409),
    'IPPoolExhaustedError': ('RESOURCE_EXHAUSTED', 409),
    'IPNotAvailableError': ('RESOURCE_UNAVAILABLE', 409),
    'IPNotInPoolError': ('VALIDATION_ERROR', 400),
    'IPAllocationNotFoundError': ('NOT_FOUND', 404),
    'NotIPAllocationOwnerError': ('FORBIDDEN', 403),
    
    # Health Monitor errors
    'HealthMonitorError': ('HEALTH_MONITOR_ERROR', 400),
    'InvalidHealthStatusError': ('VALIDATION_ERROR', 400),
    'HealthCheckConfigNotFoundError': ('NOT_FOUND', 404),
    'InvalidHealthCheckConfigError': ('VALIDATION_ERROR', 400),
}


def get_error_info_for_exception(exception):
    """
    Get error code and status code for an exception.
    
    :param exception: The exception instance
    :returns: Tuple of (error_code, status_code)
    """
    exception_name = type(exception).__name__
    
    if exception_name in EXCEPTION_MAP:
        return EXCEPTION_MAP[exception_name]
    
    # Check if exception has error_code attribute
    if hasattr(exception, 'error_code'):
        error_code = exception.error_code
        # Determine status code based on error code pattern
        if 'NOT_FOUND' in error_code:
            return (error_code, 404)
        elif 'CONFLICT' in error_code or 'EXISTS' in error_code:
            return (error_code, 409)
        elif 'FORBIDDEN' in error_code or 'PERMISSION' in error_code:
            return (error_code, 403)
        elif 'UNAUTHORIZED' in error_code:
            return (error_code, 401)
        elif 'VALIDATION' in error_code or 'INVALID' in error_code:
            return (error_code, 400)
        else:
            return (error_code, 400)
    
    # Default to internal server error
    return ('INTERNAL_ERROR', 500)


def exception_to_response(exception):
    """
    Convert an exception to a standardized error response.
    
    Requirements: 10.3, 10.6
    
    :param exception: The exception instance
    :returns: Tuple of (response_dict, status_code)
    """
    error_code, status_code = get_error_info_for_exception(exception)
    
    # Get message from exception
    message = str(exception)
    if hasattr(exception, 'message'):
        message = exception.message
    
    # Build details
    details = {}
    
    # Add field info for validation errors
    if hasattr(exception, 'field') and exception.field:
        details['field'] = exception.field
    
    # Add permission info for authorization errors
    if hasattr(exception, 'permission') and exception.permission:
        details['required_permission'] = exception.permission
    
    # Add current allocation info for unavailable errors
    if hasattr(exception, 'current_allocation') and exception.current_allocation:
        details['current_allocation'] = {
            'id': exception.current_allocation.id,
            'user_id': exception.current_allocation.user_id,
            'job_id': exception.current_allocation.job_id
        }
    
    # Add capacity info for capacity exceeded errors
    if hasattr(exception, 'capacity') and exception.capacity is not None:
        details['capacity'] = exception.capacity
    if hasattr(exception, 'current_allocations') and exception.current_allocations is not None:
        details['current_allocations'] = exception.current_allocations
    
    # Add health status info
    if hasattr(exception, 'health_status') and exception.health_status:
        details['health_status'] = exception.health_status
    
    # Add conflicting reservations info
    if hasattr(exception, 'conflicting_reservations') and exception.conflicting_reservations:
        details['conflicting_reservations'] = [
            {'id': r.id, 'start_time': r.start_time.isoformat(), 'end_time': r.end_time.isoformat()}
            for r in exception.conflicting_reservations
        ]
    
    # Add overlapping pools info
    if hasattr(exception, 'overlapping_pools') and exception.overlapping_pools:
        details['overlapping_pools'] = exception.overlapping_pools
    
    return error_response(error_code, message, details, status_code)


# =============================================================================
# Namespace Publishing (empty - base module has no endpoints)
# =============================================================================

def publish_namespaces(version_prefix):
    """
    Publish base namespaces (none - this is a utility module).
    
    :param version_prefix: The version prefix for the API path
    :returns: Empty list
    """
    return []
