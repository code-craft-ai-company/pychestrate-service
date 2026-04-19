"""
.. module:: reservations
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for resource reservation management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for reservation management:
- POST /reservations - create reservation
- GET /reservations - list reservations
- GET /reservations/{id} - get reservation
- PUT /reservations/{id} - modify reservation
- DELETE /reservations/{id} - cancel reservation

Requirements: 5.1, 5.4, 5.5
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

RESERVATIONS_NAMESPACE_PATH = "/reservations"

reservations_ns = Namespace(
    "Reservations v1",
    description="Resource reservation management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(reservations_ns)

reservation_create_model = reservations_ns.model('ReservationCreate', {
    'resource_id': fields.Integer(required=True, description='Resource ID to reserve'),
    'job_id': fields.String(description='Job identifier'),
    'start_time': fields.DateTime(required=True, description='Reservation start time (ISO format)'),
    'end_time': fields.DateTime(required=True, description='Reservation end time (ISO format)'),
    'mode': fields.String(description='Allocation mode (exclusive or shared)', default='exclusive'),
    'reason': fields.String(description='Reason for reservation')
})

reservation_update_model = reservations_ns.model('ReservationUpdate', {
    'start_time': fields.DateTime(description='New start time (ISO format)'),
    'end_time': fields.DateTime(description='New end time (ISO format)')
})

reservation_response_model = reservations_ns.model('ReservationResponse', {
    'id': fields.Integer(required=True, description='Reservation ID'),
    'resource_id': fields.Integer(required=True, description='Resource ID'),
    'resource_name': fields.String(required=True, description='Resource name'),
    'user_id': fields.String(required=True, description='User ID'),
    'username': fields.String(description='Username'),
    'job_id': fields.String(description='Job ID'),
    'start_time': fields.DateTime(required=True, description='Reservation start time'),
    'end_time': fields.DateTime(required=True, description='Reservation end time'),
    'mode': fields.String(required=True, description='Allocation mode'),
    'status': fields.String(required=True, description='Reservation status'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

reservation_list_model = reservations_ns.model('ReservationList', {
    'items': fields.List(fields.Nested(reservation_response_model), description='List of reservations'),
    'total': fields.Integer(required=True, description='Total number of reservations'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})


# =============================================================================
# Helper Functions
# =============================================================================

def reservation_response_to_dict(res_response):
    """Convert ReservationResponse dataclass to dict."""
    return {
        'id': res_response.id,
        'resource_id': res_response.resource_id,
        'resource_name': res_response.resource_name,
        'user_id': res_response.user_id,
        'username': res_response.username,
        'job_id': res_response.job_id,
        'start_time': res_response.start_time.isoformat() if res_response.start_time else None,
        'end_time': res_response.end_time.isoformat() if res_response.end_time else None,
        'mode': res_response.mode,
        'status': res_response.status,
        'created_at': res_response.created_at.isoformat() if res_response.created_at else None
    }


def parse_datetime(date_str):
    """Parse ISO format datetime string."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


# =============================================================================
# Endpoints
# =============================================================================

@reservations_ns.route("/")
class ReservationCollection(Resource):
    """Reservation collection for listing and creating reservations."""
    
    @reservations_ns.doc('list_reservations')
    @reservations_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @reservations_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @reservations_ns.param('resource_id', 'Filter by resource ID', type=int)
    @reservations_ns.param('user_id', 'Filter by user ID', type=str)
    @reservations_ns.param('start_after', 'Filter reservations starting after (ISO format)', type=str)
    @reservations_ns.param('end_before', 'Filter reservations ending before (ISO format)', type=str)
    @reservations_ns.response(200, 'Success', reservation_list_model)
    @reservations_ns.response(401, 'Unauthorized', error_model)
    @reservations_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self):
        """
        List reservations with pagination and filtering.
        """
        try:
            offset, limit = get_pagination_params()
            resource_id = request.args.get('resource_id', type=int)
            user_id = request.args.get('user_id')
            start_after = parse_datetime(request.args.get('start_after'))
            end_before = parse_datetime(request.args.get('end_before'))
            
            from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
            
            allocation_manager = AllocationManager(g.db_session)
            result = allocation_manager.list_reservations(
                resource_id=resource_id,
                user_id=user_id,
                start_after=start_after,
                end_before=end_before,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[reservation_response_to_dict(r) for r in result.reservations],
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
    
    @reservations_ns.doc('create_reservation')
    @reservations_ns.expect(reservation_create_model)
    @reservations_ns.response(201, 'Reservation created', reservation_response_model)
    @reservations_ns.response(400, 'Validation error', error_model)
    @reservations_ns.response(401, 'Unauthorized', error_model)
    @reservations_ns.response(403, 'Forbidden', error_model)
    @reservations_ns.response(409, 'Conflict - reservation conflicts with existing', error_model)
    @require_auth
    @require_permission('resources.reserve')
    def post(self):
        """
        Create a new reservation.
        
        Requirements: 5.1
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.allocation_manager import (
                AllocationManager,
                ReservationRequest,
                ReservationConflictError,
                InvalidTimeWindowError,
                ResourceNotFoundError
            )
            
            # Parse datetime fields
            start_time = parse_datetime(data.get('start_time'))
            end_time = parse_datetime(data.get('end_time'))
            
            if not start_time:
                return validation_error("Valid start_time required (ISO format)", field='start_time')
            if not end_time:
                return validation_error("Valid end_time required (ISO format)", field='end_time')
            
            # Build the reservation request
            reservation_request = ReservationRequest(
                resource_id=data.get('resource_id'),
                job_id=data.get('job_id'),
                start_time=start_time,
                end_time=end_time,
                mode=data.get('mode', 'exclusive'),
                reason=data.get('reason', '')
            )
            
            allocation_manager = AllocationManager(g.db_session)
            res_response = allocation_manager.create_reservation(
                reservation_request,
                user_id=g.current_user_id
            )
            
            return reservation_response_to_dict(res_response), 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@reservations_ns.route("/<int:reservation_id>")
@reservations_ns.param('reservation_id', 'The reservation identifier')
class ReservationItem(Resource):
    """Individual reservation for get, update, and cancel operations."""
    
    @reservations_ns.doc('get_reservation')
    @reservations_ns.response(200, 'Success', reservation_response_model)
    @reservations_ns.response(401, 'Unauthorized', error_model)
    @reservations_ns.response(403, 'Forbidden', error_model)
    @reservations_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self, reservation_id):
        """
        Get a reservation by ID.
        """
        try:
            from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
            
            allocation_manager = AllocationManager(g.db_session)
            res_response = allocation_manager.get_reservation(reservation_id)
            
            if res_response is None:
                return not_found_error('Reservation', str(reservation_id))
            
            return reservation_response_to_dict(res_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @reservations_ns.doc('modify_reservation')
    @reservations_ns.expect(reservation_update_model)
    @reservations_ns.response(200, 'Reservation modified', reservation_response_model)
    @reservations_ns.response(400, 'Validation error', error_model)
    @reservations_ns.response(401, 'Unauthorized', error_model)
    @reservations_ns.response(403, 'Forbidden', error_model)
    @reservations_ns.response(404, 'Not found', error_model)
    @reservations_ns.response(409, 'Conflict - new time conflicts with existing', error_model)
    @require_auth
    @require_permission('resources.reserve')
    def put(self, reservation_id):
        """
        Modify a reservation time window.
        
        Requirements: 5.5
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.allocation_manager import (
                AllocationManager,
                ReservationNotFoundError,
                ReservationConflictError,
                InvalidTimeWindowError
            )
            
            # Parse datetime fields
            start_time = parse_datetime(data.get('start_time'))
            end_time = parse_datetime(data.get('end_time'))
            
            allocation_manager = AllocationManager(g.db_session)
            res_response = allocation_manager.modify_reservation(
                reservation_id,
                start_time=start_time,
                end_time=end_time,
                user_id=g.current_user_id
            )
            
            return reservation_response_to_dict(res_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @reservations_ns.doc('cancel_reservation')
    @reservations_ns.response(204, 'Reservation cancelled')
    @reservations_ns.response(401, 'Unauthorized', error_model)
    @reservations_ns.response(403, 'Forbidden', error_model)
    @reservations_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.reserve')
    def delete(self, reservation_id):
        """
        Cancel a reservation.
        
        Requirements: 5.4
        """
        try:
            from automojo.pychestrate.core.managers.allocation_manager import (
                AllocationManager,
                ReservationNotFoundError
            )
            
            allocation_manager = AllocationManager(g.db_session)
            allocation_manager.cancel_reservation(
                reservation_id,
                user_id=g.current_user_id
            )
            
            return '', 204
            
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
    Publish the reservations namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (reservations_ns, "".join([version_prefix, RESERVATIONS_NAMESPACE_PATH]))
    ]
    return ns_list
