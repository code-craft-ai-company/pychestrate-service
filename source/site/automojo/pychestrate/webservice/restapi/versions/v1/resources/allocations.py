"""
.. module:: allocations
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for resource allocation management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for allocation management:
- POST /resources/{id}/checkout - checkout resource
- POST /allocations/{id}/checkin - checkin resource
- GET /allocations - list allocations
- GET /allocations/{id} - get allocation
- DELETE /allocations/{id} - force checkin (admin)
- GET /allocations/history - get allocation history
- GET /metrics - get utilization metrics
- GET /allocations/export - export allocation data

Requirements: 3.1, 4.1, 4.4, 9.1, 9.3, 9.5
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

ALLOCATIONS_NAMESPACE_PATH = "/allocations"
RESOURCES_CHECKOUT_NAMESPACE_PATH = "/resources"
METRICS_NAMESPACE_PATH = "/metrics"

allocations_ns = Namespace(
    "Allocations v1",
    description="Resource allocation management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(allocations_ns)

checkout_request_model = allocations_ns.model('CheckoutRequest', {
    'resource_id': fields.Integer(description='Resource ID to checkout'),
    'resource_name': fields.String(description='Resource name to checkout'),
    'pool_id': fields.Integer(description='Pool ID for tag-based checkout'),
    'tags': fields.List(fields.String, description='Tags for resource selection'),
    'job_id': fields.String(description='Job identifier'),
    'mode': fields.String(description='Allocation mode (exclusive or shared)', default='exclusive'),
    'timeout_minutes': fields.Integer(description='Allocation timeout in minutes'),
    'reason': fields.String(description='Reason for checkout')
})

allocation_response_model = allocations_ns.model('AllocationResponse', {
    'id': fields.Integer(required=True, description='Allocation ID'),
    'resource_id': fields.Integer(required=True, description='Resource ID'),
    'resource_name': fields.String(required=True, description='Resource name'),
    'resource_type': fields.String(required=True, description='Resource type'),
    'user_id': fields.String(required=True, description='User ID'),
    'username': fields.String(description='Username'),
    'job_id': fields.String(description='Job ID'),
    'mode': fields.String(required=True, description='Allocation mode'),
    'status': fields.String(required=True, description='Allocation status'),
    'checkout_time': fields.DateTime(description='Checkout timestamp'),
    'expected_checkin': fields.DateTime(description='Expected checkin time'),
    'actual_checkin': fields.DateTime(description='Actual checkin time'),
    'duration_minutes': fields.Integer(description='Allocation duration in minutes'),
    'metadata': fields.Raw(description='Resource metadata at checkout time')
})

allocation_list_model = allocations_ns.model('AllocationList', {
    'items': fields.List(fields.Nested(allocation_response_model), description='List of allocations'),
    'total': fields.Integer(required=True, description='Total number of allocations'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})

force_checkin_request_model = allocations_ns.model('ForceCheckinRequest', {
    'reason': fields.String(required=True, description='Reason for force checkin')
})

metrics_response_model = allocations_ns.model('MetricsResponse', {
    'total_allocation_time_minutes': fields.Integer(description='Total allocation time in minutes'),
    'average_duration_minutes': fields.Float(description='Average allocation duration'),
    'peak_concurrent_usage': fields.Integer(description='Peak concurrent allocations'),
    'total_allocations': fields.Integer(description='Total number of allocations'),
    'active_allocations': fields.Integer(description='Currently active allocations'),
    'resource_utilization': fields.Raw(description='Per-resource utilization data')
})


# =============================================================================
# Helper Functions
# =============================================================================

def allocation_response_to_dict(alloc_response):
    """Convert AllocationResponse dataclass to dict."""
    return {
        'id': alloc_response.id,
        'resource_id': alloc_response.resource_id,
        'resource_name': alloc_response.resource_name,
        'resource_type': alloc_response.resource_type,
        'user_id': alloc_response.user_id,
        'username': alloc_response.username,
        'job_id': alloc_response.job_id,
        'mode': alloc_response.mode,
        'status': alloc_response.status,
        'checkout_time': alloc_response.checkout_time.isoformat() if alloc_response.checkout_time else None,
        'expected_checkin': alloc_response.expected_checkin.isoformat() if alloc_response.expected_checkin else None,
        'actual_checkin': alloc_response.actual_checkin.isoformat() if alloc_response.actual_checkin else None,
        'duration_minutes': alloc_response.duration_minutes,
        'metadata': alloc_response.metadata
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

@allocations_ns.route("/")
class AllocationCollection(Resource):
    """Allocation collection for listing allocations."""
    
    @allocations_ns.doc('list_allocations')
    @allocations_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @allocations_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @allocations_ns.param('resource_id', 'Filter by resource ID', type=int)
    @allocations_ns.param('user_id', 'Filter by user ID', type=str)
    @allocations_ns.param('job_id', 'Filter by job ID', type=str)
    @allocations_ns.param('status', 'Filter by status (active, released, expired, forced)', type=str)
    @allocations_ns.response(200, 'Success', allocation_list_model)
    @allocations_ns.response(401, 'Unauthorized', error_model)
    @allocations_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self):
        """
        List allocations with pagination and filtering.
        
        Requirements: 9.1
        """
        try:
            offset, limit = get_pagination_params()
            resource_id = request.args.get('resource_id', type=int)
            user_id = request.args.get('user_id')
            job_id = request.args.get('job_id')
            status = request.args.get('status')
            
            from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
            
            allocation_manager = AllocationManager(g.db_session)
            result = allocation_manager.list_allocations(
                resource_id=resource_id,
                user_id=user_id,
                job_id=job_id,
                status=status,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[allocation_response_to_dict(a) for a in result.allocations],
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


@allocations_ns.route("/<int:allocation_id>")
@allocations_ns.param('allocation_id', 'The allocation identifier')
class AllocationItem(Resource):
    """Individual allocation for get and force checkin operations."""
    
    @allocations_ns.doc('get_allocation')
    @allocations_ns.response(200, 'Success', allocation_response_model)
    @allocations_ns.response(401, 'Unauthorized', error_model)
    @allocations_ns.response(403, 'Forbidden', error_model)
    @allocations_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self, allocation_id):
        """
        Get an allocation by ID.
        """
        try:
            from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
            
            allocation_manager = AllocationManager(g.db_session)
            alloc_response = allocation_manager.get_allocation(allocation_id)
            
            if alloc_response is None:
                return not_found_error('Allocation', str(allocation_id))
            
            return allocation_response_to_dict(alloc_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @allocations_ns.doc('force_checkin')
    @allocations_ns.expect(force_checkin_request_model)
    @allocations_ns.response(200, 'Allocation force checked in', allocation_response_model)
    @allocations_ns.response(401, 'Unauthorized', error_model)
    @allocations_ns.response(403, 'Forbidden', error_model)
    @allocations_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.admin')
    def delete(self, allocation_id):
        """
        Force checkin an allocation (admin only).
        
        Requirements: 4.4
        """
        try:
            data = request.json or {}
            reason = data.get('reason', 'Administrative force checkin')
            
            from automojo.pychestrate.core.managers.allocation_manager import (
                AllocationManager,
                AllocationNotFoundError
            )
            
            allocation_manager = AllocationManager(g.db_session)
            alloc_response = allocation_manager.force_checkin(
                allocation_id,
                admin_user_id=g.current_user_id,
                reason=reason
            )
            
            return allocation_response_to_dict(alloc_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@allocations_ns.route("/<int:allocation_id>/checkin")
@allocations_ns.param('allocation_id', 'The allocation identifier')
class AllocationCheckin(Resource):
    """Allocation checkin endpoint."""
    
    @allocations_ns.doc('checkin_allocation')
    @allocations_ns.response(200, 'Allocation checked in', allocation_response_model)
    @allocations_ns.response(401, 'Unauthorized', error_model)
    @allocations_ns.response(403, 'Forbidden - not allocation owner', error_model)
    @allocations_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.checkin')
    def post(self, allocation_id):
        """
        Checkin a resource allocation.
        
        Requirements: 4.1
        """
        try:
            from automojo.pychestrate.core.managers.allocation_manager import (
                AllocationManager,
                AllocationNotFoundError,
                NotAllocationOwnerError
            )
            
            allocation_manager = AllocationManager(g.db_session)
            alloc_response = allocation_manager.checkin(
                allocation_id,
                user_id=g.current_user_id
            )
            
            return allocation_response_to_dict(alloc_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@allocations_ns.route("/history")
class AllocationHistory(Resource):
    """Allocation history endpoint."""
    
    @allocations_ns.doc('get_allocation_history')
    @allocations_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @allocations_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @allocations_ns.param('resource_id', 'Filter by resource ID', type=int)
    @allocations_ns.param('user_id', 'Filter by user ID', type=str)
    @allocations_ns.param('start_date', 'Filter by start date (ISO format)', type=str)
    @allocations_ns.param('end_date', 'Filter by end date (ISO format)', type=str)
    @allocations_ns.response(200, 'Success', allocation_list_model)
    @allocations_ns.response(401, 'Unauthorized', error_model)
    @allocations_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self):
        """
        Get allocation history with filtering.
        
        Requirements: 9.1
        """
        try:
            offset, limit = get_pagination_params()
            resource_id = request.args.get('resource_id', type=int)
            user_id = request.args.get('user_id')
            start_date = parse_datetime(request.args.get('start_date'))
            end_date = parse_datetime(request.args.get('end_date'))
            
            from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
            
            allocation_manager = AllocationManager(g.db_session)
            result = allocation_manager.get_allocation_history(
                resource_id=resource_id,
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[allocation_response_to_dict(a) for a in result.allocations],
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


@allocations_ns.route("/export")
class AllocationExport(Resource):
    """Allocation data export endpoint."""
    
    @allocations_ns.doc('export_allocation_data')
    @allocations_ns.param('resource_id', 'Filter by resource ID', type=int)
    @allocations_ns.param('start_date', 'Filter by start date (ISO format)', type=str)
    @allocations_ns.param('end_date', 'Filter by end date (ISO format)', type=str)
    @allocations_ns.param('format', 'Export format (json or csv)', type=str, default='json')
    @allocations_ns.response(200, 'Success')
    @allocations_ns.response(401, 'Unauthorized', error_model)
    @allocations_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self):
        """
        Export allocation data.
        
        Requirements: 9.5
        """
        try:
            resource_id = request.args.get('resource_id', type=int)
            start_date = parse_datetime(request.args.get('start_date'))
            end_date = parse_datetime(request.args.get('end_date'))
            export_format = request.args.get('format', 'json')
            
            if export_format not in ('json', 'csv'):
                return validation_error("Format must be 'json' or 'csv'", field='format')
            
            from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
            from flask import Response
            
            allocation_manager = AllocationManager(g.db_session)
            data = allocation_manager.export_allocation_data(
                resource_id=resource_id,
                start_date=start_date,
                end_date=end_date,
                format=export_format
            )
            
            if export_format == 'csv':
                return Response(
                    data,
                    mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=allocations.csv'}
                )
            else:
                return Response(
                    data,
                    mimetype='application/json',
                    headers={'Content-Disposition': 'attachment; filename=allocations.json'}
                )
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# Separate namespace for resource checkout
resources_checkout_ns = Namespace(
    "Resource Checkout v1",
    description="Resource checkout endpoint"
)


@resources_checkout_ns.route("/<int:resource_id>/checkout")
@resources_checkout_ns.param('resource_id', 'The resource identifier')
class ResourceCheckout(Resource):
    """Resource checkout endpoint."""
    
    @resources_checkout_ns.doc('checkout_resource')
    @resources_checkout_ns.expect(checkout_request_model)
    @resources_checkout_ns.response(201, 'Resource checked out', allocation_response_model)
    @resources_checkout_ns.response(400, 'Validation error', error_model)
    @resources_checkout_ns.response(401, 'Unauthorized', error_model)
    @resources_checkout_ns.response(403, 'Forbidden', error_model)
    @resources_checkout_ns.response(404, 'Not found', error_model)
    @resources_checkout_ns.response(409, 'Resource unavailable', error_model)
    @require_auth
    @require_permission('resources.checkout')
    def post(self, resource_id):
        """
        Checkout a resource.
        
        Requirements: 3.1
        """
        try:
            data = request.json or {}
            
            from automojo.pychestrate.core.managers.allocation_manager import (
                AllocationManager,
                CheckoutRequest,
                ResourceNotFoundError,
                ResourceUnavailableError,
                ResourceOfflineError,
                CapacityExceededError
            )
            
            # Build the checkout request
            checkout_request = CheckoutRequest(
                resource_id=resource_id,
                job_id=data.get('job_id'),
                mode=data.get('mode', 'exclusive'),
                timeout_minutes=data.get('timeout_minutes'),
                reason=data.get('reason', '')
            )
            
            allocation_manager = AllocationManager(g.db_session)
            alloc_response = allocation_manager.checkout(
                checkout_request,
                user_id=g.current_user_id
            )
            
            return allocation_response_to_dict(alloc_response), 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# Separate namespace for metrics
metrics_ns = Namespace(
    "Metrics v1",
    description="Resource utilization metrics endpoint"
)


@metrics_ns.route("/")
class Metrics(Resource):
    """Utilization metrics endpoint."""
    
    @metrics_ns.doc('get_metrics')
    @metrics_ns.param('resource_id', 'Filter by resource ID', type=int)
    @metrics_ns.param('pool_id', 'Filter by pool ID', type=int)
    @metrics_ns.param('start_date', 'Filter by start date (ISO format)', type=str)
    @metrics_ns.param('end_date', 'Filter by end date (ISO format)', type=str)
    @metrics_ns.response(200, 'Success', metrics_response_model)
    @metrics_ns.response(401, 'Unauthorized', error_model)
    @metrics_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self):
        """
        Get utilization metrics.
        
        Requirements: 9.3
        """
        try:
            resource_id = request.args.get('resource_id', type=int)
            pool_id = request.args.get('pool_id', type=int)
            start_date = parse_datetime(request.args.get('start_date'))
            end_date = parse_datetime(request.args.get('end_date'))
            
            from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
            
            allocation_manager = AllocationManager(g.db_session)
            metrics = allocation_manager.get_utilization_metrics(
                resource_id=resource_id,
                pool_id=pool_id,
                start_date=start_date,
                end_date=end_date
            )
            
            return metrics, 200
            
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
    Publish the allocations namespaces.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (allocations_ns, "".join([version_prefix, ALLOCATIONS_NAMESPACE_PATH])),
        (resources_checkout_ns, "".join([version_prefix, RESOURCES_CHECKOUT_NAMESPACE_PATH])),
        (metrics_ns, "".join([version_prefix, METRICS_NAMESPACE_PATH]))
    ]
    return ns_list
