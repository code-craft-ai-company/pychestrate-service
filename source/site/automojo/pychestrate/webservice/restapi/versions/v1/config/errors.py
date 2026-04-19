"""
.. module:: errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Error handling middleware for config REST API

.. moduleauthor:: Automation Mojo LLC

This module provides error handling middleware that:
- Creates consistent error response format
- Maps exceptions to HTTP status codes
- Handles common error scenarios

Requirements: 9.3, 9.6
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import jsonify
from werkzeug.exceptions import HTTPException


# =============================================================================
# Error Response Format
# =============================================================================

def create_error_response(error_code: str, message: str, details: dict = None, status_code: int = 400):
    """
    Create a standardized error response.
    
    The response format is:
    {
        "error_code": "ERROR_CODE",
        "message": "Human-readable error message",
        "details": { ... optional additional details ... }
    }
    
    Requirements: 9.3
    
    :param error_code: Error code identifier (e.g., 'VALIDATION_ERROR', 'NOT_FOUND')
    :param message: Human-readable error message
    :param details: Optional dictionary with additional error details
    :param status_code: HTTP status code
    :returns: Tuple of (response, status_code)
    """
    response = {
        'error_code': error_code,
        'message': message,
        'details': details or {}
    }
    return response, status_code


# =============================================================================
# Exception to HTTP Status Code Mapping
# =============================================================================

# Map of exception types to (error_code, status_code) tuples
EXCEPTION_MAP = {
    # Authentication/Authorization errors
    'AuthenticationError': ('UNAUTHORIZED', 401),
    'AuthorizationError': ('FORBIDDEN', 403),
    'PermissionDeniedError': ('FORBIDDEN', 403),
    
    # Validation errors
    'ValidationError': ('VALIDATION_ERROR', 400),
    'PasswordValidationError': ('VALIDATION_ERROR', 400),
    
    # Not found errors
    'UserNotFoundError': ('NOT_FOUND', 404),
    'RoleNotFoundError': ('NOT_FOUND', 404),
    'VariableNotFoundError': ('NOT_FOUND', 404),
    'SecretNotFoundError': ('NOT_FOUND', 404),
    'ScopeNotFoundError': ('NOT_FOUND', 404),
    'SessionNotFoundError': ('NOT_FOUND', 404),
    
    # Conflict errors
    'DuplicateUserError': ('CONFLICT', 409),
    'DuplicateVariableError': ('CONFLICT', 409),
    'DuplicateSecretError': ('CONFLICT', 409),
    'DuplicateScopeError': ('CONFLICT', 409),
    
    # Business logic errors
    'PasswordHistoryError': ('VALIDATION_ERROR', 400),
    'PasswordResetTokenError': ('INVALID_TOKEN', 400),
    'SessionExpiredError': ('SESSION_EXPIRED', 401),
    'ScopeNotEmptyError': ('SCOPE_NOT_EMPTY', 400),
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
    
    # Default to internal server error
    return ('INTERNAL_ERROR', 500)


def exception_to_response(exception):
    """
    Convert an exception to a standardized error response.
    
    Requirements: 9.3, 9.6
    
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
    
    # Add violations for password validation errors
    if hasattr(exception, 'violations') and exception.violations:
        details['violations'] = exception.violations
    
    # Add permission info for authorization errors
    if hasattr(exception, 'permission') and exception.permission:
        details['required_permission'] = exception.permission
    
    return create_error_response(error_code, message, details, status_code)


# =============================================================================
# Flask Error Handlers
# =============================================================================

def register_error_handlers(app):
    """
    Register error handlers with a Flask application.
    
    This function registers handlers for:
    - HTTP exceptions (4xx, 5xx)
    - Custom application exceptions
    - Unhandled exceptions
    
    Requirements: 9.3, 9.6
    
    :param app: Flask application instance
    """
    
    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        """Handle HTTP exceptions (4xx, 5xx errors)."""
        error_code = 'HTTP_ERROR'
        
        # Map common HTTP status codes to error codes
        status_to_code = {
            400: 'BAD_REQUEST',
            401: 'UNAUTHORIZED',
            403: 'FORBIDDEN',
            404: 'NOT_FOUND',
            405: 'METHOD_NOT_ALLOWED',
            409: 'CONFLICT',
            422: 'UNPROCESSABLE_ENTITY',
            429: 'TOO_MANY_REQUESTS',
            500: 'INTERNAL_ERROR',
            502: 'BAD_GATEWAY',
            503: 'SERVICE_UNAVAILABLE',
        }
        
        error_code = status_to_code.get(e.code, 'HTTP_ERROR')
        
        response = {
            'error_code': error_code,
            'message': e.description or str(e),
            'details': {}
        }
        
        return jsonify(response), e.code
    
    @app.errorhandler(Exception)
    def handle_generic_exception(e):
        """Handle unhandled exceptions."""
        # Check if it's a known application exception
        exception_name = type(e).__name__
        
        if exception_name in EXCEPTION_MAP:
            response, status_code = exception_to_response(e)
            return jsonify(response), status_code
        
        # Log the error for debugging (in production, use proper logging)
        import traceback
        traceback.print_exc()
        
        # Return generic error response
        response = {
            'error_code': 'INTERNAL_ERROR',
            'message': 'An unexpected error occurred',
            'details': {}
        }
        
        return jsonify(response), 500


def register_namespace_error_handlers(namespace):
    """
    Register error handlers with a Flask-RestX namespace.
    
    :param namespace: Flask-RestX Namespace instance
    """
    
    @namespace.errorhandler(Exception)
    def handle_namespace_exception(e):
        """Handle exceptions within the namespace."""
        exception_name = type(e).__name__
        
        if exception_name in EXCEPTION_MAP:
            return exception_to_response(e)
        
        # Return generic error
        return create_error_response(
            'INTERNAL_ERROR',
            'An unexpected error occurred',
            None,
            500
        )
