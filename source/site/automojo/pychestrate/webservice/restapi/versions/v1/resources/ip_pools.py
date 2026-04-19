"""
.. module:: ip_pools
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for IP pool management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for IP pool management:
- POST /ip-pools - create IP pool
- GET /ip-pools - list IP pools
- GET /ip-pools/{id} - get IP pool with stats
- PUT /ip-pools/{id} - update IP pool
- DELETE /ip-pools/{id} - delete IP pool
- POST /ip-pools/{id}/checkout - checkout IP(s)
- POST /ip-pools/{id}/checkin - checkin IP(s)
- POST /ip-pools/{id}/reserved - mark IP reserved
- DELETE /ip-pools/{id}/reserved/{ip} - unmark reserved

Requirements: 2A.1, 2A.4, 3A.1, 4A.1
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

IP_POOLS_NAMESPACE_PATH = "/ip-pools"

ip_pools_ns = Namespace(
    "IP Pools v1",
    description="IP address pool management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(ip_pools_ns)

ip_pool_create_model = ip_pools_ns.model('IPPoolCreate', {
    'name': fields.String(required=True, description='Unique pool name'),
    'cidr': fields.String(required=True, description='CIDR notation (e.g., 192.168.1.0/24)'),
    'gateway': fields.String(description='Gateway IP address'),
    'dns_servers': fields.List(fields.String, description='List of DNS server IPs'),
    'description': fields.String(description='Pool description'),
    'reserved_ips': fields.List(fields.String, description='List of IPs to reserve')
})

ip_pool_update_model = ip_pools_ns.model('IPPoolUpdate', {
    'description': fields.String(description='Pool description'),
    'gateway': fields.String(description='Gateway IP address'),
    'dns_servers': fields.List(fields.String, description='List of DNS server IPs'),
    'reserved_ips': fields.List(fields.String, description='List of IPs to reserve')
})

ip_pool_response_model = ip_pools_ns.model('IPPoolResponse', {
    'id': fields.Integer(required=True, description='Pool ID'),
    'name': fields.String(required=True, description='Pool name'),
    'cidr': fields.String(required=True, description='CIDR notation'),
    'ip_version': fields.String(required=True, description='IP version (ipv4 or ipv6)'),
    'network_address': fields.String(required=True, description='Network address'),
    'broadcast_address': fields.String(description='Broadcast address'),
    'subnet_mask': fields.String(required=True, description='Subnet mask'),
    'gateway': fields.String(description='Gateway IP'),
    'dns_servers': fields.List(fields.String, description='DNS servers'),
    'description': fields.String(description='Pool description'),
    'total_addresses': fields.Integer(required=True, description='Total usable addresses'),
    'reserved_count': fields.Integer(required=True, description='Reserved addresses'),
    'allocated_count': fields.Integer(required=True, description='Allocated addresses'),
    'available_count': fields.Integer(required=True, description='Available addresses'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'created_by': fields.String(description='User who created the pool')
})

ip_pool_list_model = ip_pools_ns.model('IPPoolList', {
    'items': fields.List(fields.Nested(ip_pool_response_model), description='List of IP pools'),
    'total': fields.Integer(required=True, description='Total number of pools'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})

ip_checkout_request_model = ip_pools_ns.model('IPCheckoutRequest', {
    'count': fields.Integer(description='Number of IPs to allocate (default: 1)'),
    'specific_ip': fields.String(description='Request a specific IP address'),
    'prefer_contiguous': fields.Boolean(description='Prefer contiguous block (default: true)'),
    'job_id': fields.String(description='Job identifier'),
    'timeout_minutes': fields.Integer(description='Allocation timeout in minutes'),
    'reason': fields.String(description='Reason for allocation')
})

ip_allocation_response_model = ip_pools_ns.model('IPAllocationResponse', {
    'id': fields.Integer(required=True, description='Allocation ID'),
    'pool_id': fields.Integer(required=True, description='Pool ID'),
    'pool_name': fields.String(required=True, description='Pool name'),
    'ip_address': fields.String(required=True, description='Allocated IP address'),
    'subnet_mask': fields.String(required=True, description='Subnet mask'),
    'gateway': fields.String(description='Gateway IP'),
    'dns_servers': fields.List(fields.String, description='DNS servers'),
    'user_id': fields.String(required=True, description='User ID'),
    'username': fields.String(description='Username'),
    'job_id': fields.String(description='Job ID'),
    'status': fields.String(required=True, description='Allocation status'),
    'checkout_time': fields.DateTime(description='Checkout timestamp'),
    'expected_checkin': fields.DateTime(description='Expected checkin time')
})

ip_bulk_allocation_response_model = ip_pools_ns.model('IPBulkAllocationResponse', {
    'allocations': fields.List(fields.Nested(ip_allocation_response_model), description='List of allocations'),
    'contiguous': fields.Boolean(required=True, description='Whether IPs are contiguous'),
    'start_ip': fields.String(required=True, description='First IP in range'),
    'end_ip': fields.String(required=True, description='Last IP in range')
})

ip_checkin_request_model = ip_pools_ns.model('IPCheckinRequest', {
    'allocation_ids': fields.List(fields.Integer, description='List of allocation IDs to release'),
    'job_id': fields.String(description='Release all IPs for this job')
})

ip_reserve_request_model = ip_pools_ns.model('IPReserveRequest', {
    'ip_address': fields.String(required=True, description='IP address to reserve'),
    'reason': fields.String(description='Reason for reservation')
})


# =============================================================================
# Helper Functions
# =============================================================================

def ip_pool_response_to_dict(pool_response):
    """Convert IPPoolResponse dataclass to dict."""
    return {
        'id': pool_response.id,
        'name': pool_response.name,
        'cidr': pool_response.cidr,
        'ip_version': pool_response.ip_version,
        'network_address': pool_response.network_address,
        'broadcast_address': pool_response.broadcast_address,
        'subnet_mask': pool_response.subnet_mask,
        'gateway': pool_response.gateway,
        'dns_servers': pool_response.dns_servers,
        'description': pool_response.description,
        'total_addresses': pool_response.total_addresses,
        'reserved_count': pool_response.reserved_count,
        'allocated_count': pool_response.allocated_count,
        'available_count': pool_response.available_count,
        'created_at': pool_response.created_at.isoformat() if pool_response.created_at else None,
        'created_by': pool_response.created_by
    }


def ip_allocation_response_to_dict(alloc_response):
    """Convert IPAllocationResponse dataclass to dict."""
    return {
        'id': alloc_response.id,
        'pool_id': alloc_response.pool_id,
        'pool_name': alloc_response.pool_name,
        'ip_address': alloc_response.ip_address,
        'subnet_mask': alloc_response.subnet_mask,
        'gateway': alloc_response.gateway,
        'dns_servers': alloc_response.dns_servers,
        'user_id': alloc_response.user_id,
        'username': alloc_response.username,
        'job_id': alloc_response.job_id,
        'status': alloc_response.status,
        'checkout_time': alloc_response.checkout_time.isoformat() if alloc_response.checkout_time else None,
        'expected_checkin': alloc_response.expected_checkin.isoformat() if alloc_response.expected_checkin else None
    }


def ip_bulk_allocation_response_to_dict(bulk_response):
    """Convert IPBulkAllocationResponse dataclass to dict."""
    return {
        'allocations': [ip_allocation_response_to_dict(a) for a in bulk_response.allocations],
        'contiguous': bulk_response.contiguous,
        'start_ip': bulk_response.start_ip,
        'end_ip': bulk_response.end_ip
    }


# =============================================================================
# Endpoints
# =============================================================================

@ip_pools_ns.route("/")
class IPPoolCollection(Resource):
    """IP pool collection for listing and creating pools."""
    
    @ip_pools_ns.doc('list_ip_pools')
    @ip_pools_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @ip_pools_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @ip_pools_ns.response(200, 'Success', ip_pool_list_model)
    @ip_pools_ns.response(401, 'Unauthorized', error_model)
    @ip_pools_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self):
        """
        List IP pools with pagination.
        
        Requirements: 2A.1
        """
        try:
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.ip_pool_manager import IPPoolManager
            
            ip_pool_manager = IPPoolManager(g.db_session)
            result = ip_pool_manager.list_pools(
                user_id=g.current_user_id,
                offset=offset,
                limit=limit
            )
            
            return paginated_response(
                items=[ip_pool_response_to_dict(p) for p in result.pools],
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
    
    @ip_pools_ns.doc('create_ip_pool')
    @ip_pools_ns.expect(ip_pool_create_model)
    @ip_pools_ns.response(201, 'IP pool created', ip_pool_response_model)
    @ip_pools_ns.response(400, 'Validation error', error_model)
    @ip_pools_ns.response(401, 'Unauthorized', error_model)
    @ip_pools_ns.response(403, 'Forbidden', error_model)
    @ip_pools_ns.response(409, 'Conflict', error_model)
    @require_auth
    @require_permission('resources.create')
    def post(self):
        """
        Create a new IP pool.
        
        Requirements: 2A.1
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.ip_pool_manager import (
                IPPoolManager,
                IPPoolCreateRequest,
                IPPoolValidationError,
                DuplicateIPPoolError,
                CIDROverlapError
            )
            
            # Build the create request
            create_request = IPPoolCreateRequest(
                name=data.get('name', ''),
                cidr=data.get('cidr', ''),
                gateway=data.get('gateway'),
                dns_servers=data.get('dns_servers', []),
                description=data.get('description', ''),
                reserved_ips=data.get('reserved_ips', [])
            )
            
            ip_pool_manager = IPPoolManager(g.db_session)
            pool_response = ip_pool_manager.create_pool(
                create_request,
                user_id=g.current_user_id
            )
            
            return ip_pool_response_to_dict(pool_response), 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@ip_pools_ns.route("/<int:pool_id>")
@ip_pools_ns.param('pool_id', 'The IP pool identifier')
class IPPoolItem(Resource):
    """Individual IP pool for get, update, and delete operations."""
    
    @ip_pools_ns.doc('get_ip_pool')
    @ip_pools_ns.response(200, 'Success', ip_pool_response_model)
    @ip_pools_ns.response(401, 'Unauthorized', error_model)
    @ip_pools_ns.response(403, 'Forbidden', error_model)
    @ip_pools_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.read')
    def get(self, pool_id):
        """
        Get an IP pool by ID with stats.
        
        Requirements: 2A.5
        """
        try:
            from automojo.pychestrate.core.managers.ip_pool_manager import IPPoolManager
            
            ip_pool_manager = IPPoolManager(g.db_session)
            pool_response = ip_pool_manager.get_pool(pool_id)
            
            if pool_response is None:
                return not_found_error('IP Pool', str(pool_id))
            
            return ip_pool_response_to_dict(pool_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @ip_pools_ns.doc('update_ip_pool')
    @ip_pools_ns.expect(ip_pool_update_model)
    @ip_pools_ns.response(200, 'IP pool updated', ip_pool_response_model)
    @ip_pools_ns.response(400, 'Validation error', error_model)
    @ip_pools_ns.response(401, 'Unauthorized', error_model)
    @ip_pools_ns.response(403, 'Forbidden', error_model)
    @ip_pools_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.update')
    def put(self, pool_id):
        """
        Update an IP pool.
        
        Requirements: 2A.4
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.ip_pool_manager import (
                IPPoolManager,
                IPPoolUpdateRequest,
                IPPoolNotFoundError
            )
            
            # Build the update request
            update_request = IPPoolUpdateRequest(
                description=data.get('description'),
                gateway=data.get('gateway'),
                dns_servers=data.get('dns_servers'),
                reserved_ips=data.get('reserved_ips')
            )
            
            ip_pool_manager = IPPoolManager(g.db_session)
            pool_response = ip_pool_manager.update_pool(
                pool_id,
                update_request,
                user_id=g.current_user_id
            )
            
            return ip_pool_response_to_dict(pool_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @ip_pools_ns.doc('delete_ip_pool')
    @ip_pools_ns.response(204, 'IP pool deleted')
    @ip_pools_ns.response(401, 'Unauthorized', error_model)
    @ip_pools_ns.response(403, 'Forbidden', error_model)
    @ip_pools_ns.response(404, 'Not found', error_model)
    @ip_pools_ns.response(409, 'Conflict - pool has allocations', error_model)
    @require_auth
    @require_permission('resources.delete')
    def delete(self, pool_id):
        """
        Delete an IP pool.
        """
        try:
            from automojo.pychestrate.core.managers.ip_pool_manager import (
                IPPoolManager,
                IPPoolNotFoundError,
                IPPoolHasAllocationsError
            )
            
            ip_pool_manager = IPPoolManager(g.db_session)
            ip_pool_manager.delete_pool(pool_id, user_id=g.current_user_id)
            
            return '', 204
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@ip_pools_ns.route("/<int:pool_id>/checkout")
@ip_pools_ns.param('pool_id', 'The IP pool identifier')
class IPPoolCheckout(Resource):
    """IP checkout endpoint."""
    
    @ip_pools_ns.doc('checkout_ip')
    @ip_pools_ns.expect(ip_checkout_request_model)
    @ip_pools_ns.response(201, 'IP(s) allocated', ip_bulk_allocation_response_model)
    @ip_pools_ns.response(400, 'Validation error', error_model)
    @ip_pools_ns.response(401, 'Unauthorized', error_model)
    @ip_pools_ns.response(403, 'Forbidden', error_model)
    @ip_pools_ns.response(404, 'Not found', error_model)
    @ip_pools_ns.response(409, 'Pool exhausted or IP unavailable', error_model)
    @require_auth
    @require_permission('resources.checkout')
    def post(self, pool_id):
        """
        Checkout IP address(es) from pool.
        
        Requirements: 3A.1
        """
        try:
            data = request.json or {}
            
            from automojo.pychestrate.core.managers.ip_pool_manager import (
                IPPoolManager,
                IPAllocationRequest,
                IPPoolNotFoundError,
                IPPoolExhaustedError,
                IPNotAvailableError
            )
            
            # Build the allocation request
            alloc_request = IPAllocationRequest(
                pool_id=pool_id,
                count=data.get('count', 1),
                specific_ip=data.get('specific_ip'),
                prefer_contiguous=data.get('prefer_contiguous', True),
                job_id=data.get('job_id'),
                timeout_minutes=data.get('timeout_minutes'),
                reason=data.get('reason', '')
            )
            
            ip_pool_manager = IPPoolManager(g.db_session)
            
            if alloc_request.count == 1 and not alloc_request.specific_ip:
                # Single IP checkout
                alloc_response = ip_pool_manager.checkout_ip(
                    alloc_request,
                    user_id=g.current_user_id
                )
                # Wrap in bulk response format
                result = {
                    'allocations': [ip_allocation_response_to_dict(alloc_response)],
                    'contiguous': True,
                    'start_ip': alloc_response.ip_address,
                    'end_ip': alloc_response.ip_address
                }
            else:
                # Bulk or specific IP checkout
                bulk_response = ip_pool_manager.checkout_ips(
                    alloc_request,
                    user_id=g.current_user_id
                )
                result = ip_bulk_allocation_response_to_dict(bulk_response)
            
            return result, 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@ip_pools_ns.route("/<int:pool_id>/checkin")
@ip_pools_ns.param('pool_id', 'The IP pool identifier')
class IPPoolCheckin(Resource):
    """IP checkin endpoint."""
    
    @ip_pools_ns.doc('checkin_ip')
    @ip_pools_ns.expect(ip_checkin_request_model)
    @ip_pools_ns.response(200, 'IP(s) released')
    @ip_pools_ns.response(400, 'Validation error', error_model)
    @ip_pools_ns.response(401, 'Unauthorized', error_model)
    @ip_pools_ns.response(403, 'Forbidden', error_model)
    @ip_pools_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.checkin')
    def post(self, pool_id):
        """
        Checkin IP address(es) to pool.
        
        Requirements: 4A.1
        """
        try:
            data = request.json or {}
            
            from automojo.pychestrate.core.managers.ip_pool_manager import (
                IPPoolManager,
                IPPoolNotFoundError,
                IPAllocationNotFoundError,
                NotIPAllocationOwnerError
            )
            
            ip_pool_manager = IPPoolManager(g.db_session)
            
            allocation_ids = data.get('allocation_ids', [])
            job_id = data.get('job_id')
            
            if job_id:
                # Release all IPs for a job
                count = ip_pool_manager.checkin_job_ips(
                    job_id,
                    user_id=g.current_user_id
                )
                return {'released_count': count}, 200
            elif allocation_ids:
                # Release specific allocations
                count = ip_pool_manager.checkin_ips(
                    allocation_ids,
                    user_id=g.current_user_id
                )
                return {'released_count': count}, 200
            else:
                return validation_error("Either allocation_ids or job_id required")
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@ip_pools_ns.route("/<int:pool_id>/reserved")
@ip_pools_ns.param('pool_id', 'The IP pool identifier')
class IPPoolReserved(Resource):
    """IP reservation endpoint."""
    
    @ip_pools_ns.doc('mark_ip_reserved')
    @ip_pools_ns.expect(ip_reserve_request_model)
    @ip_pools_ns.response(201, 'IP marked as reserved')
    @ip_pools_ns.response(400, 'Validation error', error_model)
    @ip_pools_ns.response(401, 'Unauthorized', error_model)
    @ip_pools_ns.response(403, 'Forbidden', error_model)
    @ip_pools_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.update')
    def post(self, pool_id):
        """
        Mark an IP address as reserved.
        
        Requirements: 2A.4
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            ip_address = data.get('ip_address')
            if not ip_address:
                return validation_error("ip_address required", field='ip_address')
            
            from automojo.pychestrate.core.managers.ip_pool_manager import (
                IPPoolManager,
                IPPoolNotFoundError,
                IPNotInPoolError
            )
            
            ip_pool_manager = IPPoolManager(g.db_session)
            ip_pool_manager.mark_ip_reserved(
                pool_id,
                ip_address,
                reason=data.get('reason', ''),
                user_id=g.current_user_id
            )
            
            return {'message': f'IP {ip_address} marked as reserved'}, 201
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@ip_pools_ns.route("/<int:pool_id>/reserved/<string:ip_address>")
@ip_pools_ns.param('pool_id', 'The IP pool identifier')
@ip_pools_ns.param('ip_address', 'The IP address to unreserve')
class IPPoolReservedItem(Resource):
    """Individual reserved IP endpoint."""
    
    @ip_pools_ns.doc('unmark_ip_reserved')
    @ip_pools_ns.response(204, 'IP reservation removed')
    @ip_pools_ns.response(401, 'Unauthorized', error_model)
    @ip_pools_ns.response(403, 'Forbidden', error_model)
    @ip_pools_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('resources.update')
    def delete(self, pool_id, ip_address):
        """
        Remove reserved status from an IP address.
        
        Requirements: 2A.4
        """
        try:
            from automojo.pychestrate.core.managers.ip_pool_manager import (
                IPPoolManager,
                IPPoolNotFoundError
            )
            
            ip_pool_manager = IPPoolManager(g.db_session)
            ip_pool_manager.unmark_ip_reserved(
                pool_id,
                ip_address,
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
    Publish the IP pools namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (ip_pools_ns, "".join([version_prefix, IP_POOLS_NAMESPACE_PATH]))
    ]
    return ns_list
