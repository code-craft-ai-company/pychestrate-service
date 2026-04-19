"""
.. module:: errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Error handling middleware for resource REST API

.. moduleauthor:: Automation Mojo LLC

This module provides error handling middleware that:
- Creates consistent error response format
- Maps exceptions to HTTP status codes
- Handles common error scenarios

Requirements: 10.3, 10.6
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import jsonify
from werkzeug.exceptions import HTTPException

from .base import EXCEPTION_MAP, exception_to_response, error_response


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
    
    Requirements: 10.3, 10.6
    
    :param app: Flask application instance
    """
    
    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        """Handle HTTP exceptions (4xx, 5xx errors)."""
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
        
        # Check if exception has error_code attribute
        if hasattr(e, 'error_code'):
            return exception_to_response(e)
        
        # Return generic error
        return error_response(
            'INTERNAL_ERROR',
            'An unexpected error occurred',
            None,
            500
        )
