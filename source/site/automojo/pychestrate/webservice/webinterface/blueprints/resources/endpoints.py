"""
.. module:: endpoints
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Web interface endpoints for resource management

.. moduleauthor:: Automation Mojo LLC

This module provides web interface endpoints for:
- Resource management (list, create, edit, delete)
- Pool management (list, create, delete)
- IP pool management (list, create, edit, checkout, checkin)
- Allocation viewing (active, history, force checkin)
- Reservation management (list, create, edit, cancel)
- Health monitoring (dashboard, configuration, history)

All data modifications use postback URLs as per project conventions.

Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from functools import wraps
from datetime import datetime

from flask import (
    render_template, request, redirect, url_for, flash, session, g
)

from . import resources_blueprint
from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS


# =============================================================================
# Authentication Helpers
# =============================================================================

def get_db_session():
    """Get a database session from the session factory."""
    if SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY is None:
        raise RuntimeError("Database session factory not initialized")
    return SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY()


def login_required(f):
    """
    Decorator that requires user authentication.
    
    Redirects to login page if not authenticated.
    
    Requirements: 11.4, 11.5
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('config.login', next=request.url))
        
        # Validate session token
        session_token = session.get('session_token')
        if not session_token:
            flash('Session expired. Please log in again.', 'warning')
            return redirect(url_for('config.login', next=request.url))
        
        db_session = get_db_session()
        try:
            from automojo.pychestrate.core.managers.security_manager import SecurityManager
            security_manager = SecurityManager(db_session)
            session_info = security_manager.validate_token(session_token)
            
            if session_info is None:
                session.clear()
                flash('Session expired. Please log in again.', 'warning')
                return redirect(url_for('config.login', next=request.url))
            
            g.current_user_id = session_info.user_id
            g.current_username = session_info.username
            g.csrf_token = session_info.csrf_token
            g.db_session = db_session
            
            return f(*args, **kwargs)
        except Exception:
            db_session.close()
            session.clear()
            flash('Authentication error. Please log in again.', 'error')
            return redirect(url_for('config.login'))
    
    return decorated_function


def admin_required(f):
    """
    Decorator that requires admin role.
    
    Must be used after @login_required decorator.
    
    Requirements: 11.4
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        db_session = g.db_session
        
        from automojo.pychestrate.core.managers.security_manager import SecurityManager
        security_manager = SecurityManager(db_session)
        
        # Check for admin permission
        if not security_manager.check_permission(g.current_user_id, 'resources.manage'):
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('resources.dashboard'))
        
        return f(*args, **kwargs)
    
    return decorated_function


def validate_csrf(f):
    """
    Decorator that validates CSRF token for POST requests.
    
    Requirements: 11.2
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            csrf_token = request.form.get('csrf_token')
            if not csrf_token or csrf_token != g.csrf_token:
                flash('Invalid request. Please try again.', 'error')
                return redirect(request.referrer or url_for('resources.dashboard'))
        
        return f(*args, **kwargs)
    
    return decorated_function


# =============================================================================
# Error Handling
# =============================================================================

@resources_blueprint.errorhandler(404)
def handle_not_found(error):
    """
    Handle 404 Not Found errors.
    
    Requirements: 11.3
    """
    return render_template('resources/errors/404.html', csrf_token=session.get('csrf_token', '')), 404


@resources_blueprint.errorhandler(403)
def handle_forbidden(error):
    """
    Handle 403 Forbidden errors.
    
    Requirements: 11.3
    """
    return render_template('resources/errors/403.html', csrf_token=session.get('csrf_token', '')), 403


@resources_blueprint.errorhandler(500)
def handle_server_error(error):
    """
    Handle 500 Internal Server errors.
    
    Requirements: 11.3
    """
    return render_template('resources/errors/500.html', csrf_token=session.get('csrf_token', '')), 500


@resources_blueprint.errorhandler(Exception)
def handle_error(error):
    """
    Handle errors and display appropriate error messages.
    
    Requirements: 11.3
    """
    error_message = str(error) if error else "An unexpected error occurred"
    flash(error_message, 'error')
    return redirect(url_for('resources.dashboard'))


# =============================================================================
# Dashboard
# =============================================================================

@resources_blueprint.route('/')
@resources_blueprint.route('/dashboard')
@login_required
def dashboard():
    """
    Resource management dashboard page.
    
    Requirements: 11.1, 11.6
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
    from automojo.pychestrate.core.managers.ip_pool_manager import IPPoolManager
    
    resource_manager = ResourceManager(db_session)
    allocation_manager = AllocationManager(db_session)
    ip_pool_manager = IPPoolManager(db_session)
    
    # Get summary statistics
    resources = resource_manager.list_resources(limit=1000)
    pools = resource_manager.list_pools(g.current_user_id)
    ip_pools = ip_pool_manager.list_pools(g.current_user_id)
    active_allocations = allocation_manager.list_allocations(status='active')
    
    # Count by health status
    health_counts = {'online': 0, 'offline': 0, 'degraded': 0, 'maintenance': 0}
    for resource in resources:
        status = resource.health_status.value if hasattr(resource.health_status, 'value') else resource.health_status
        if status in health_counts:
            health_counts[status] += 1
    
    return render_template('resources/dashboard.html',
                          resource_count=len(resources),
                          pool_count=len(pools),
                          ip_pool_count=len(ip_pools),
                          active_allocation_count=len(active_allocations),
                          health_counts=health_counts,
                          csrf_token=g.csrf_token)



# =============================================================================
# Resource Management Endpoints
# =============================================================================

@resources_blueprint.route('/list')
@login_required
def resource_list():
    """
    Resource list page with filtering.
    
    Requirements: 11.1, 11.4, 11.6
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    
    resource_manager = ResourceManager(db_session)
    
    # Get pagination and filter params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    pool_id = request.args.get('pool_id', type=int)
    resource_type = request.args.get('resource_type')
    health_status = request.args.get('health_status')
    search = request.args.get('search', '')
    tags = request.args.getlist('tags')
    
    offset = (page - 1) * per_page
    
    # Build filter kwargs
    filter_kwargs = {
        'offset': offset,
        'limit': per_page
    }
    if pool_id:
        filter_kwargs['pool_id'] = pool_id
    if resource_type:
        from automojo.pychestrate.core.managers.resource_manager import ResourceType
        try:
            filter_kwargs['resource_type'] = ResourceType(resource_type)
        except ValueError:
            pass
    if health_status:
        from automojo.pychestrate.core.managers.resource_manager import HealthStatus
        try:
            filter_kwargs['health_status'] = HealthStatus(health_status)
        except ValueError:
            pass
    if tags:
        filter_kwargs['tags'] = tags
    
    resources = resource_manager.list_resources(**filter_kwargs)
    
    # Get pools for filter dropdown
    pools = resource_manager.list_pools(g.current_user_id)
    
    # Get all tags for filter dropdown
    all_tags = resource_manager.list_tags()
    
    # Calculate total pages (approximate since we don't have total count)
    total_pages = 1 if len(resources) < per_page else page + 1
    
    return render_template('resources/resources/list.html',
                          resources=resources,
                          pools=pools,
                          all_tags=all_tags,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          selected_pool_id=pool_id,
                          selected_resource_type=resource_type,
                          selected_health_status=health_status,
                          selected_tags=tags,
                          search=search,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/create', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def resource_create():
    """
    Resource creation page and handler.
    
    Requirements: 11.1, 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import (
        ResourceManager, ResourceCreateRequest, ResourceType
    )
    
    resource_manager = ResourceManager(db_session)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            resource_type_str = request.form.get('resource_type', 'generic')
            pool_id = request.form.get('pool_id', type=int)
            description = request.form.get('description', '').strip()
            capacity = request.form.get('capacity', 1, type=int)
            tags = request.form.getlist('tags')
            
            # Parse metadata JSON
            metadata_str = request.form.get('metadata', '{}')
            try:
                import json
                metadata = json.loads(metadata_str) if metadata_str else {}
            except json.JSONDecodeError:
                flash('Invalid JSON in metadata field.', 'error')
                pools = resource_manager.list_pools(g.current_user_id)
                all_tags = resource_manager.list_tags()
                return render_template('resources/resources/create.html',
                                      csrf_token=g.csrf_token,
                                      pools=pools,
                                      all_tags=all_tags,
                                      form_data=request.form)
            
            resource_type = ResourceType(resource_type_str)
            
            create_request = ResourceCreateRequest(
                name=name,
                resource_type=resource_type,
                pool_id=pool_id,
                description=description,
                metadata=metadata,
                tags=tags,
                capacity=capacity
            )
            
            resource = resource_manager.create_resource(create_request, g.current_user_id)
            
            flash(f'Resource "{name}" created successfully.', 'success')
            return redirect(url_for('resources.resource_detail', resource_id=resource.id))
            
        except Exception as e:
            flash(f'Error creating resource: {str(e)}', 'error')
            pools = resource_manager.list_pools(g.current_user_id)
            all_tags = resource_manager.list_tags()
            return render_template('resources/resources/create.html',
                                  csrf_token=g.csrf_token,
                                  pools=pools,
                                  all_tags=all_tags,
                                  form_data=request.form)
    
    # GET request - show form
    pools = resource_manager.list_pools(g.current_user_id)
    all_tags = resource_manager.list_tags()
    
    return render_template('resources/resources/create.html',
                          csrf_token=g.csrf_token,
                          pools=pools,
                          all_tags=all_tags)


@resources_blueprint.route('/<int:resource_id>')
@login_required
def resource_detail(resource_id):
    """
    Resource detail page.
    
    Requirements: 11.1, 11.4, 11.6
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
    
    resource_manager = ResourceManager(db_session)
    allocation_manager = AllocationManager(db_session)
    
    resource = resource_manager.get_resource(resource_id)
    
    if not resource:
        flash('Resource not found.', 'error')
        return redirect(url_for('resources.resource_list'))
    
    # Get active allocations for this resource
    active_allocations = allocation_manager.get_active_allocations(resource_id)
    
    return render_template('resources/resources/detail.html',
                          resource=resource,
                          active_allocations=active_allocations,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/<int:resource_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def resource_edit(resource_id):
    """
    Resource edit page and handler.
    
    Requirements: 11.1, 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import (
        ResourceManager, ResourceUpdateRequest, HealthStatus
    )
    
    resource_manager = ResourceManager(db_session)
    
    resource = resource_manager.get_resource(resource_id)
    
    if not resource:
        flash('Resource not found.', 'error')
        return redirect(url_for('resources.resource_list'))
    
    if request.method == 'POST':
        try:
            description = request.form.get('description', '').strip()
            capacity = request.form.get('capacity', type=int)
            health_status_str = request.form.get('health_status')
            tags = request.form.getlist('tags')
            
            # Parse metadata JSON
            metadata_str = request.form.get('metadata', '')
            metadata = None
            if metadata_str:
                try:
                    import json
                    metadata = json.loads(metadata_str)
                except json.JSONDecodeError:
                    flash('Invalid JSON in metadata field.', 'error')
                    pools = resource_manager.list_pools(g.current_user_id)
                    all_tags = resource_manager.list_tags()
                    return render_template('resources/resources/edit.html',
                                          resource=resource,
                                          pools=pools,
                                          all_tags=all_tags,
                                          csrf_token=g.csrf_token)
            
            health_status = None
            if health_status_str:
                health_status = HealthStatus(health_status_str)
            
            update_request = ResourceUpdateRequest(
                description=description if description else None,
                metadata=metadata,
                tags=tags if tags else None,
                capacity=capacity,
                health_status=health_status
            )
            
            resource_manager.update_resource(resource_id, update_request, g.current_user_id)
            
            flash('Resource updated successfully.', 'success')
            return redirect(url_for('resources.resource_detail', resource_id=resource_id))
            
        except Exception as e:
            flash(f'Error updating resource: {str(e)}', 'error')
    
    # GET request - show form
    pools = resource_manager.list_pools(g.current_user_id)
    all_tags = resource_manager.list_tags()
    
    return render_template('resources/resources/edit.html',
                          resource=resource,
                          pools=pools,
                          all_tags=all_tags,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/<int:resource_id>/delete', methods=['POST'])
@login_required
@admin_required
@validate_csrf
def resource_delete(resource_id):
    """
    Resource deletion handler.
    
    Requirements: 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    
    resource_manager = ResourceManager(db_session)
    
    try:
        resource_manager.delete_resource(resource_id, g.current_user_id)
        flash('Resource deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting resource: {str(e)}', 'error')
    
    return redirect(url_for('resources.resource_list'))


@resources_blueprint.route('/<int:resource_id>/checkout', methods=['POST'])
@login_required
@validate_csrf
def resource_checkout(resource_id):
    """
    Resource checkout handler.
    
    Requirements: 11.2
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.allocation_manager import (
        AllocationManager, CheckoutRequest, AllocationMode
    )
    
    allocation_manager = AllocationManager(db_session)
    
    try:
        job_id = request.form.get('job_id', '').strip()
        mode_str = request.form.get('mode', 'exclusive')
        timeout_minutes = request.form.get('timeout_minutes', type=int)
        reason = request.form.get('reason', '').strip()
        
        mode = AllocationMode(mode_str)
        
        checkout_request = CheckoutRequest(
            resource_id=resource_id,
            job_id=job_id if job_id else None,
            mode=mode,
            timeout_minutes=timeout_minutes,
            reason=reason
        )
        
        allocation = allocation_manager.checkout(checkout_request, g.current_user_id)
        
        flash(f'Resource checked out successfully. Allocation ID: {allocation.id}', 'success')
    except Exception as e:
        flash(f'Error checking out resource: {str(e)}', 'error')
    
    return redirect(url_for('resources.resource_detail', resource_id=resource_id))



# =============================================================================
# Pool Management Endpoints
# =============================================================================

@resources_blueprint.route('/pools')
@login_required
def pool_list():
    """
    Resource pool list page.
    
    Requirements: 11.1, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    
    resource_manager = ResourceManager(db_session)
    
    pools = resource_manager.list_pools(g.current_user_id)
    
    return render_template('resources/pools/list.html',
                          pools=pools,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/pools/create', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def pool_create():
    """
    Resource pool creation page and handler.
    
    Requirements: 11.1, 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import (
        ResourceManager, ResourcePoolCreateRequest
    )
    
    resource_manager = ResourceManager(db_session)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            create_request = ResourcePoolCreateRequest(
                name=name,
                description=description
            )
            
            pool = resource_manager.create_pool(create_request, g.current_user_id)
            
            flash(f'Pool "{name}" created successfully.', 'success')
            return redirect(url_for('resources.pool_detail', pool_id=pool.id))
            
        except Exception as e:
            flash(f'Error creating pool: {str(e)}', 'error')
            return render_template('resources/pools/create.html',
                                  csrf_token=g.csrf_token,
                                  form_data=request.form)
    
    return render_template('resources/pools/create.html',
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/pools/<int:pool_id>')
@login_required
def pool_detail(pool_id):
    """
    Resource pool detail page with resources.
    
    Requirements: 11.1, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    
    resource_manager = ResourceManager(db_session)
    
    pool = resource_manager.get_pool(pool_id)
    
    if not pool:
        flash('Pool not found.', 'error')
        return redirect(url_for('resources.pool_list'))
    
    # Get resources in this pool
    resources = resource_manager.list_resources(pool_id=pool_id, limit=100)
    
    return render_template('resources/pools/detail.html',
                          pool=pool,
                          resources=resources,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/pools/<int:pool_id>/delete', methods=['POST'])
@login_required
@admin_required
@validate_csrf
def pool_delete(pool_id):
    """
    Resource pool deletion handler.
    
    Requirements: 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    
    resource_manager = ResourceManager(db_session)
    
    try:
        resource_manager.delete_pool(pool_id, g.current_user_id)
        flash('Pool deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting pool: {str(e)}', 'error')
    
    return redirect(url_for('resources.pool_list'))



# =============================================================================
# IP Pool Management Endpoints
# =============================================================================

@resources_blueprint.route('/ip-pools')
@login_required
def ip_pool_list():
    """
    IP pool list page with stats.
    
    Requirements: 11.1, 11.4, 11.6
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.ip_pool_manager import IPPoolManager
    
    ip_pool_manager = IPPoolManager(db_session)
    
    pools = ip_pool_manager.list_pools(g.current_user_id)
    
    return render_template('resources/ip_pools/list.html',
                          pools=pools,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/ip-pools/create', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def ip_pool_create():
    """
    IP pool creation page and handler.
    
    Requirements: 11.1, 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.ip_pool_manager import (
        IPPoolManager, IPPoolCreateRequest
    )
    
    ip_pool_manager = IPPoolManager(db_session)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            cidr = request.form.get('cidr', '').strip()
            gateway = request.form.get('gateway', '').strip()
            dns_servers_str = request.form.get('dns_servers', '').strip()
            description = request.form.get('description', '').strip()
            reserved_ips_str = request.form.get('reserved_ips', '').strip()
            
            # Parse DNS servers (comma-separated)
            dns_servers = []
            if dns_servers_str:
                dns_servers = [s.strip() for s in dns_servers_str.split(',') if s.strip()]
            
            # Parse reserved IPs (comma-separated)
            reserved_ips = []
            if reserved_ips_str:
                reserved_ips = [s.strip() for s in reserved_ips_str.split(',') if s.strip()]
            
            create_request = IPPoolCreateRequest(
                name=name,
                cidr=cidr,
                gateway=gateway if gateway else None,
                dns_servers=dns_servers,
                description=description,
                reserved_ips=reserved_ips
            )
            
            pool = ip_pool_manager.create_pool(create_request, g.current_user_id)
            
            flash(f'IP Pool "{name}" created successfully.', 'success')
            return redirect(url_for('resources.ip_pool_detail', pool_id=pool.id))
            
        except Exception as e:
            flash(f'Error creating IP pool: {str(e)}', 'error')
            return render_template('resources/ip_pools/create.html',
                                  csrf_token=g.csrf_token,
                                  form_data=request.form)
    
    return render_template('resources/ip_pools/create.html',
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/ip-pools/<int:pool_id>')
@login_required
def ip_pool_detail(pool_id):
    """
    IP pool detail page showing allocations.
    
    Requirements: 11.1, 11.4, 11.6
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.ip_pool_manager import IPPoolManager
    
    ip_pool_manager = IPPoolManager(db_session)
    
    pool = ip_pool_manager.get_pool(pool_id)
    
    if not pool:
        flash('IP Pool not found.', 'error')
        return redirect(url_for('resources.ip_pool_list'))
    
    # Get allocations for this pool
    allocations = ip_pool_manager.list_allocations(pool_id=pool_id, status='active')
    
    # Get available IPs preview
    available_ips = ip_pool_manager.get_available_ips(pool_id, count=10)
    
    return render_template('resources/ip_pools/detail.html',
                          pool=pool,
                          allocations=allocations,
                          available_ips=available_ips,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/ip-pools/<int:pool_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def ip_pool_edit(pool_id):
    """
    IP pool edit page and handler.
    
    Requirements: 11.1, 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.ip_pool_manager import (
        IPPoolManager, IPPoolUpdateRequest
    )
    
    ip_pool_manager = IPPoolManager(db_session)
    
    pool = ip_pool_manager.get_pool(pool_id)
    
    if not pool:
        flash('IP Pool not found.', 'error')
        return redirect(url_for('resources.ip_pool_list'))
    
    if request.method == 'POST':
        try:
            gateway = request.form.get('gateway', '').strip()
            dns_servers_str = request.form.get('dns_servers', '').strip()
            description = request.form.get('description', '').strip()
            reserved_ips_str = request.form.get('reserved_ips', '').strip()
            
            # Parse DNS servers
            dns_servers = None
            if dns_servers_str:
                dns_servers = [s.strip() for s in dns_servers_str.split(',') if s.strip()]
            
            # Parse reserved IPs
            reserved_ips = None
            if reserved_ips_str:
                reserved_ips = [s.strip() for s in reserved_ips_str.split(',') if s.strip()]
            
            update_request = IPPoolUpdateRequest(
                description=description if description else None,
                gateway=gateway if gateway else None,
                dns_servers=dns_servers,
                reserved_ips=reserved_ips
            )
            
            ip_pool_manager.update_pool(pool_id, update_request, g.current_user_id)
            
            flash('IP Pool updated successfully.', 'success')
            return redirect(url_for('resources.ip_pool_detail', pool_id=pool_id))
            
        except Exception as e:
            flash(f'Error updating IP pool: {str(e)}', 'error')
    
    return render_template('resources/ip_pools/edit.html',
                          pool=pool,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/ip-pools/<int:pool_id>/delete', methods=['POST'])
@login_required
@admin_required
@validate_csrf
def ip_pool_delete(pool_id):
    """
    IP pool deletion handler.
    
    Requirements: 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.ip_pool_manager import IPPoolManager
    
    ip_pool_manager = IPPoolManager(db_session)
    
    try:
        ip_pool_manager.delete_pool(pool_id, g.current_user_id)
        flash('IP Pool deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting IP pool: {str(e)}', 'error')
    
    return redirect(url_for('resources.ip_pool_list'))


@resources_blueprint.route('/ip-pools/<int:pool_id>/checkout', methods=['POST'])
@login_required
@validate_csrf
def ip_pool_checkout(pool_id):
    """
    IP checkout handler.
    
    Requirements: 11.2
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.ip_pool_manager import (
        IPPoolManager, IPAllocationRequest
    )
    
    ip_pool_manager = IPPoolManager(db_session)
    
    try:
        count = request.form.get('count', 1, type=int)
        specific_ip = request.form.get('specific_ip', '').strip()
        job_id = request.form.get('job_id', '').strip()
        timeout_minutes = request.form.get('timeout_minutes', type=int)
        reason = request.form.get('reason', '').strip()
        
        alloc_request = IPAllocationRequest(
            pool_id=pool_id,
            count=count,
            specific_ip=specific_ip if specific_ip else None,
            job_id=job_id if job_id else None,
            timeout_minutes=timeout_minutes,
            reason=reason
        )
        
        if count == 1:
            allocation = ip_pool_manager.checkout_ip(alloc_request, g.current_user_id)
            flash(f'IP {allocation.ip_address} checked out successfully.', 'success')
        else:
            result = ip_pool_manager.checkout_ips(alloc_request, g.current_user_id)
            flash(f'{len(result.allocations)} IPs checked out successfully.', 'success')
            
    except Exception as e:
        flash(f'Error checking out IP: {str(e)}', 'error')
    
    return redirect(url_for('resources.ip_pool_detail', pool_id=pool_id))


@resources_blueprint.route('/ip-pools/<int:pool_id>/checkin', methods=['POST'])
@login_required
@validate_csrf
def ip_pool_checkin(pool_id):
    """
    IP checkin handler.
    
    Requirements: 11.2
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.ip_pool_manager import IPPoolManager
    
    ip_pool_manager = IPPoolManager(db_session)
    
    try:
        allocation_id = request.form.get('allocation_id', type=int)
        job_id = request.form.get('job_id', '').strip()
        
        if allocation_id:
            ip_pool_manager.checkin_ip(allocation_id, g.current_user_id)
            flash('IP checked in successfully.', 'success')
        elif job_id:
            count = ip_pool_manager.checkin_job_ips(job_id, g.current_user_id)
            flash(f'{count} IPs checked in for job {job_id}.', 'success')
        else:
            flash('No allocation ID or job ID provided.', 'error')
            
    except Exception as e:
        flash(f'Error checking in IP: {str(e)}', 'error')
    
    return redirect(url_for('resources.ip_pool_detail', pool_id=pool_id))



# =============================================================================
# Allocation Viewing Endpoints
# =============================================================================

@resources_blueprint.route('/allocations')
@login_required
def allocation_list():
    """
    Active allocations list page.
    
    Requirements: 11.1, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    
    allocation_manager = AllocationManager(db_session)
    resource_manager = ResourceManager(db_session)
    
    # Get filter params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    resource_id = request.args.get('resource_id', type=int)
    user_id = request.args.get('user_id', type=int)
    job_id = request.args.get('job_id', '')
    
    offset = (page - 1) * per_page
    
    # Build filter kwargs
    filter_kwargs = {
        'status': 'active',
        'offset': offset,
        'limit': per_page
    }
    if resource_id:
        filter_kwargs['resource_id'] = resource_id
    if user_id:
        filter_kwargs['user_id'] = user_id
    if job_id:
        filter_kwargs['job_id'] = job_id
    
    allocations = allocation_manager.list_allocations(**filter_kwargs)
    
    # Get resources for filter dropdown
    resources = resource_manager.list_resources(limit=100)
    
    total_pages = 1 if len(allocations) < per_page else page + 1
    
    return render_template('resources/allocations/list.html',
                          allocations=allocations,
                          resources=resources,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          selected_resource_id=resource_id,
                          selected_user_id=user_id,
                          selected_job_id=job_id,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/allocations/history')
@login_required
def allocation_history():
    """
    Allocation history page with filtering.
    
    Requirements: 11.1, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    
    allocation_manager = AllocationManager(db_session)
    resource_manager = ResourceManager(db_session)
    
    # Get filter params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    resource_id = request.args.get('resource_id', type=int)
    user_id = request.args.get('user_id', type=int)
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    
    offset = (page - 1) * per_page
    
    # Parse dates
    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.fromisoformat(start_date_str)
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.fromisoformat(end_date_str)
        except ValueError:
            pass
    
    allocations = allocation_manager.get_allocation_history(
        resource_id=resource_id,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        offset=offset,
        limit=per_page
    )
    
    # Get resources for filter dropdown
    resources = resource_manager.list_resources(limit=100)
    
    total_pages = 1 if len(allocations) < per_page else page + 1
    
    return render_template('resources/allocations/history.html',
                          allocations=allocations,
                          resources=resources,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          selected_resource_id=resource_id,
                          selected_user_id=user_id,
                          start_date=start_date_str,
                          end_date=end_date_str,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/allocations/<int:allocation_id>')
@login_required
def allocation_detail(allocation_id):
    """
    Allocation detail page.
    
    Requirements: 11.1, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
    
    allocation_manager = AllocationManager(db_session)
    
    allocation = allocation_manager.get_allocation(allocation_id)
    
    if not allocation:
        flash('Allocation not found.', 'error')
        return redirect(url_for('resources.allocation_list'))
    
    return render_template('resources/allocations/detail.html',
                          allocation=allocation,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/allocations/<int:allocation_id>/checkin', methods=['POST'])
@login_required
@validate_csrf
def allocation_checkin(allocation_id):
    """
    Allocation checkin handler.
    
    Requirements: 11.2
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
    
    allocation_manager = AllocationManager(db_session)
    
    try:
        allocation_manager.checkin(allocation_id, g.current_user_id)
        flash('Resource checked in successfully.', 'success')
    except Exception as e:
        flash(f'Error checking in resource: {str(e)}', 'error')
    
    return redirect(url_for('resources.allocation_list'))


@resources_blueprint.route('/allocations/<int:allocation_id>/force-checkin', methods=['POST'])
@login_required
@admin_required
@validate_csrf
def allocation_force_checkin(allocation_id):
    """
    Force checkin handler for administrators.
    
    Requirements: 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
    
    allocation_manager = AllocationManager(db_session)
    
    try:
        reason = request.form.get('reason', 'Administrative force checkin')
        allocation_manager.force_checkin(allocation_id, g.current_user_id, reason)
        flash('Resource force checked in successfully.', 'success')
    except Exception as e:
        flash(f'Error force checking in resource: {str(e)}', 'error')
    
    return redirect(url_for('resources.allocation_list'))



# =============================================================================
# Reservation Management Endpoints
# =============================================================================

@resources_blueprint.route('/reservations')
@login_required
def reservation_list():
    """
    Reservation list page.
    
    Requirements: 11.1, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    
    allocation_manager = AllocationManager(db_session)
    resource_manager = ResourceManager(db_session)
    
    # Get filter params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    resource_id = request.args.get('resource_id', type=int)
    start_after_str = request.args.get('start_after', '')
    end_before_str = request.args.get('end_before', '')
    
    offset = (page - 1) * per_page
    
    # Parse dates
    start_after = None
    end_before = None
    if start_after_str:
        try:
            start_after = datetime.fromisoformat(start_after_str)
        except ValueError:
            pass
    if end_before_str:
        try:
            end_before = datetime.fromisoformat(end_before_str)
        except ValueError:
            pass
    
    reservations = allocation_manager.list_reservations(
        resource_id=resource_id,
        start_after=start_after,
        end_before=end_before,
        offset=offset,
        limit=per_page
    )
    
    # Get resources for filter dropdown
    resources = resource_manager.list_resources(limit=100)
    
    total_pages = 1 if len(reservations) < per_page else page + 1
    
    return render_template('resources/reservations/list.html',
                          reservations=reservations,
                          resources=resources,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          selected_resource_id=resource_id,
                          start_after=start_after_str,
                          end_before=end_before_str,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/reservations/create', methods=['GET', 'POST'])
@login_required
@validate_csrf
def reservation_create():
    """
    Reservation creation page and handler.
    
    Requirements: 11.1, 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.allocation_manager import (
        AllocationManager, ReservationRequest, AllocationMode
    )
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    
    allocation_manager = AllocationManager(db_session)
    resource_manager = ResourceManager(db_session)
    
    if request.method == 'POST':
        try:
            resource_id = request.form.get('resource_id', type=int)
            job_id = request.form.get('job_id', '').strip()
            start_time_str = request.form.get('start_time', '')
            end_time_str = request.form.get('end_time', '')
            mode_str = request.form.get('mode', 'exclusive')
            reason = request.form.get('reason', '').strip()
            
            # Parse times
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else None
            end_time = datetime.fromisoformat(end_time_str) if end_time_str else None
            
            if not start_time or not end_time:
                flash('Start time and end time are required.', 'error')
                resources = resource_manager.list_resources(limit=100)
                return render_template('resources/reservations/create.html',
                                      csrf_token=g.csrf_token,
                                      resources=resources,
                                      form_data=request.form)
            
            mode = AllocationMode(mode_str)
            
            reservation_request = ReservationRequest(
                resource_id=resource_id,
                job_id=job_id if job_id else None,
                start_time=start_time,
                end_time=end_time,
                mode=mode,
                reason=reason
            )
            
            reservation = allocation_manager.create_reservation(reservation_request, g.current_user_id)
            
            flash(f'Reservation created successfully. ID: {reservation.id}', 'success')
            return redirect(url_for('resources.reservation_list'))
            
        except Exception as e:
            flash(f'Error creating reservation: {str(e)}', 'error')
            resources = resource_manager.list_resources(limit=100)
            return render_template('resources/reservations/create.html',
                                  csrf_token=g.csrf_token,
                                  resources=resources,
                                  form_data=request.form)
    
    # GET request - show form
    resources = resource_manager.list_resources(limit=100)
    
    return render_template('resources/reservations/create.html',
                          csrf_token=g.csrf_token,
                          resources=resources)


@resources_blueprint.route('/reservations/<int:reservation_id>')
@login_required
def reservation_detail(reservation_id):
    """
    Reservation detail page.
    
    Requirements: 11.1, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
    
    allocation_manager = AllocationManager(db_session)
    
    reservations = allocation_manager.list_reservations(limit=1000)
    reservation = None
    for r in reservations:
        if r.id == reservation_id:
            reservation = r
            break
    
    if not reservation:
        flash('Reservation not found.', 'error')
        return redirect(url_for('resources.reservation_list'))
    
    return render_template('resources/reservations/detail.html',
                          reservation=reservation,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/reservations/<int:reservation_id>/edit', methods=['GET', 'POST'])
@login_required
@validate_csrf
def reservation_edit(reservation_id):
    """
    Reservation edit page and handler.
    
    Requirements: 11.1, 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
    
    allocation_manager = AllocationManager(db_session)
    
    # Get current reservation
    reservations = allocation_manager.list_reservations(limit=1000)
    reservation = None
    for r in reservations:
        if r.id == reservation_id:
            reservation = r
            break
    
    if not reservation:
        flash('Reservation not found.', 'error')
        return redirect(url_for('resources.reservation_list'))
    
    if request.method == 'POST':
        try:
            start_time_str = request.form.get('start_time', '')
            end_time_str = request.form.get('end_time', '')
            
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else None
            end_time = datetime.fromisoformat(end_time_str) if end_time_str else None
            
            allocation_manager.modify_reservation(
                reservation_id,
                start_time=start_time,
                end_time=end_time,
                user_id=g.current_user_id
            )
            
            flash('Reservation updated successfully.', 'success')
            return redirect(url_for('resources.reservation_detail', reservation_id=reservation_id))
            
        except Exception as e:
            flash(f'Error updating reservation: {str(e)}', 'error')
    
    return render_template('resources/reservations/edit.html',
                          reservation=reservation,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/reservations/<int:reservation_id>/cancel', methods=['POST'])
@login_required
@validate_csrf
def reservation_cancel(reservation_id):
    """
    Reservation cancellation handler.
    
    Requirements: 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
    
    allocation_manager = AllocationManager(db_session)
    
    try:
        allocation_manager.cancel_reservation(reservation_id, g.current_user_id)
        flash('Reservation cancelled successfully.', 'success')
    except Exception as e:
        flash(f'Error cancelling reservation: {str(e)}', 'error')
    
    return redirect(url_for('resources.reservation_list'))



# =============================================================================
# Health Monitoring Endpoints
# =============================================================================

@resources_blueprint.route('/health')
@login_required
def health_dashboard():
    """
    Health status dashboard.
    
    Requirements: 11.1, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    from automojo.pychestrate.core.managers.health_monitor import HealthMonitor
    
    resource_manager = ResourceManager(db_session)
    health_monitor = HealthMonitor(db_session)
    
    # Get all resources
    resources = resource_manager.list_resources(limit=1000)
    
    # Group by health status
    health_groups = {
        'online': [],
        'degraded': [],
        'maintenance': [],
        'offline': []
    }
    
    for resource in resources:
        status = resource.health_status.value if hasattr(resource.health_status, 'value') else resource.health_status
        if status in health_groups:
            health_groups[status].append(resource)
    
    return render_template('resources/health/dashboard.html',
                          health_groups=health_groups,
                          total_count=len(resources),
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/health/<int:resource_id>')
@login_required
def health_detail(resource_id):
    """
    Resource health detail page with history.
    
    Requirements: 11.1, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    from automojo.pychestrate.core.managers.health_monitor import HealthMonitor
    
    resource_manager = ResourceManager(db_session)
    health_monitor = HealthMonitor(db_session)
    
    resource = resource_manager.get_resource(resource_id)
    
    if not resource:
        flash('Resource not found.', 'error')
        return redirect(url_for('resources.health_dashboard'))
    
    # Get health history
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    history = health_monitor.get_health_history(resource_id, offset=offset, limit=per_page)
    
    # Get health check config
    config = health_monitor.get_health_check_config(resource_id)
    
    total_pages = 1 if len(history) < per_page else page + 1
    
    return render_template('resources/health/detail.html',
                          resource=resource,
                          history=history,
                          config=config,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/health/<int:resource_id>/config', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def health_config(resource_id):
    """
    Health check configuration page.
    
    Requirements: 11.1, 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    from automojo.pychestrate.core.managers.health_monitor import HealthMonitor, HealthCheckConfig
    
    resource_manager = ResourceManager(db_session)
    health_monitor = HealthMonitor(db_session)
    
    resource = resource_manager.get_resource(resource_id)
    
    if not resource:
        flash('Resource not found.', 'error')
        return redirect(url_for('resources.health_dashboard'))
    
    if request.method == 'POST':
        try:
            probe_url = request.form.get('probe_url', '').strip()
            probe_command = request.form.get('probe_command', '').strip()
            interval_seconds = request.form.get('interval_seconds', 60, type=int)
            timeout_seconds = request.form.get('timeout_seconds', 10, type=int)
            failure_threshold = request.form.get('failure_threshold', 3, type=int)
            success_threshold = request.form.get('success_threshold', 1, type=int)
            enabled = request.form.get('enabled') == 'on'
            
            config = HealthCheckConfig(
                resource_id=resource_id,
                probe_url=probe_url if probe_url else None,
                probe_command=probe_command if probe_command else None,
                interval_seconds=interval_seconds,
                timeout_seconds=timeout_seconds,
                failure_threshold=failure_threshold,
                success_threshold=success_threshold,
                enabled=enabled
            )
            
            health_monitor.configure_health_check(config, g.current_user_id)
            
            flash('Health check configuration saved.', 'success')
            return redirect(url_for('resources.health_detail', resource_id=resource_id))
            
        except Exception as e:
            flash(f'Error saving configuration: {str(e)}', 'error')
    
    # Get current config
    config = health_monitor.get_health_check_config(resource_id)
    
    return render_template('resources/health/config.html',
                          resource=resource,
                          config=config,
                          csrf_token=g.csrf_token)


@resources_blueprint.route('/health/<int:resource_id>/update', methods=['POST'])
@login_required
@admin_required
@validate_csrf
def health_update(resource_id):
    """
    Update resource health status.
    
    Requirements: 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.health_monitor import HealthMonitor
    from automojo.pychestrate.core.managers.resource_manager import HealthStatus
    
    health_monitor = HealthMonitor(db_session)
    
    try:
        status_str = request.form.get('status', '')
        reason = request.form.get('reason', '').strip()
        
        status = HealthStatus(status_str)
        
        health_monitor.update_health_status(resource_id, status, reason, g.current_user_id)
        
        flash(f'Health status updated to {status_str}.', 'success')
    except Exception as e:
        flash(f'Error updating health status: {str(e)}', 'error')
    
    return redirect(url_for('resources.health_detail', resource_id=resource_id))


@resources_blueprint.route('/health/<int:resource_id>/check', methods=['POST'])
@login_required
@admin_required
@validate_csrf
def health_run_check(resource_id):
    """
    Run health check for a resource.
    
    Requirements: 11.2, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.health_monitor import HealthMonitor
    
    health_monitor = HealthMonitor(db_session)
    
    try:
        result = health_monitor.run_health_check(resource_id)
        
        if result:
            flash('Health check passed.', 'success')
        else:
            flash('Health check failed.', 'warning')
    except Exception as e:
        flash(f'Error running health check: {str(e)}', 'error')
    
    return redirect(url_for('resources.health_detail', resource_id=resource_id))


# =============================================================================
# Tag Management Endpoints
# =============================================================================

@resources_blueprint.route('/tags')
@login_required
def tag_list():
    """
    Tag list page.
    
    Requirements: 11.1, 11.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.resource_manager import ResourceManager
    
    resource_manager = ResourceManager(db_session)
    
    tags = resource_manager.list_tags()
    
    return render_template('resources/tags/list.html',
                          tags=tags,
                          csrf_token=g.csrf_token)
