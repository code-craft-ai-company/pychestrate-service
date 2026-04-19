"""
.. module:: endpoints
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Web interface endpoints for project management

.. moduleauthor:: Automation Mojo LLC

This module provides web interface endpoints for:
- Project management (list, create, edit, delete)
- Member management (add, remove, update role)
- Repository management (list, create, edit, delete, test, fetch)
- Build specification and execution management
- Infrastructure specification and job management
- Test specification and job management
- Release pipeline and release management
- Calendar event management
- Watch configuration management

All data modifications use postback URLs as per project conventions.

Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from functools import wraps
from datetime import datetime

from flask import (
    render_template, request, redirect, url_for, flash, session, g, Response
)

from . import projects_blueprint
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
    
    Requirements: 13.4, 13.5
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


def project_permission_required(permission):
    """
    Decorator that requires specific project permission.
    
    Must be used after @login_required decorator.
    The route must have a project_id parameter.
    
    Requirements: 13.4
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            project_id = kwargs.get('project_id')
            if not project_id:
                flash('Project not specified.', 'error')
                return redirect(url_for('projects.project_list'))
            
            db_session = g.db_session
            
            from automojo.pychestrate.core.managers.project_manager import ProjectManager
            project_manager = ProjectManager(db_session)
            
            # Check project permission
            if not project_manager.check_permission(project_id, g.current_user_id, permission):
                flash('You do not have permission to perform this action.', 'error')
                return redirect(url_for('projects.project_detail', project_id=project_id))
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def validate_csrf(f):
    """
    Decorator that validates CSRF token for POST requests.
    
    Requirements: 13.2
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            csrf_token = request.form.get('csrf_token')
            if not csrf_token or csrf_token != g.csrf_token:
                flash('Invalid request. Please try again.', 'error')
                return redirect(request.referrer or url_for('projects.project_list'))
        
        return f(*args, **kwargs)
    
    return decorated_function


# =============================================================================
# Error Handling
# =============================================================================

@projects_blueprint.errorhandler(404)
def handle_not_found(error):
    """
    Handle 404 Not Found errors.
    
    Requirements: 13.3
    """
    return render_template('projects/errors/404.html', 
                          csrf_token=session.get('csrf_token', '')), 404


@projects_blueprint.errorhandler(403)
def handle_forbidden(error):
    """
    Handle 403 Forbidden errors.
    
    Requirements: 13.3
    """
    return render_template('projects/errors/403.html', 
                          csrf_token=session.get('csrf_token', '')), 403


@projects_blueprint.errorhandler(500)
def handle_server_error(error):
    """
    Handle 500 Internal Server errors.
    
    Requirements: 13.3
    """
    return render_template('projects/errors/500.html', 
                          csrf_token=session.get('csrf_token', '')), 500


@projects_blueprint.errorhandler(Exception)
def handle_error(error):
    """
    Handle errors and display appropriate error messages.
    
    Requirements: 13.3
    """
    error_message = str(error) if error else "An unexpected error occurred"
    flash(error_message, 'error')
    return redirect(url_for('projects.project_list'))


# =============================================================================
# Dashboard
# =============================================================================

@projects_blueprint.route('/')
@projects_blueprint.route('/dashboard')
@login_required
def dashboard():
    """
    Project management dashboard page.
    
    Requirements: 13.1
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    
    project_manager = ProjectManager(db_session)
    
    # Get projects the user has access to
    projects = project_manager.list_projects(g.current_user_id, limit=10)
    
    # Get recent activity summary
    recent_builds = []
    recent_tests = []
    
    return render_template('projects/dashboard.html',
                          projects=projects,
                          recent_builds=recent_builds,
                          recent_tests=recent_tests,
                          csrf_token=g.csrf_token)


# =============================================================================
# Project Management Endpoints
# =============================================================================

@projects_blueprint.route('/list')
@login_required
def project_list():
    """
    Project list page with filtering.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    
    project_manager = ProjectManager(db_session)
    
    # Get pagination and filter params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    
    offset = (page - 1) * per_page
    
    projects = project_manager.list_projects(
        user_id=g.current_user_id,
        offset=offset,
        limit=per_page,
        search=search if search else None
    )
    
    # Calculate total pages (approximate)
    total_pages = 1 if len(projects) < per_page else page + 1
    
    return render_template('projects/projects/list.html',
                          projects=projects,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          search=search,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/create', methods=['GET', 'POST'])
@login_required
@validate_csrf
def project_create():
    """
    Project creation page and handler.
    
    Requirements: 13.1, 13.2
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import (
        ProjectManager, ProjectCreateRequest
    )
    
    project_manager = ProjectManager(db_session)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            # Parse metadata JSON
            metadata_str = request.form.get('metadata', '{}')
            try:
                import json
                metadata = json.loads(metadata_str) if metadata_str else {}
            except json.JSONDecodeError:
                flash('Invalid JSON in metadata field.', 'error')
                return render_template('projects/projects/create.html',
                                      csrf_token=g.csrf_token,
                                      form_data=request.form)
            
            create_request = ProjectCreateRequest(
                name=name,
                description=description,
                metadata=metadata
            )
            
            project = project_manager.create_project(create_request, g.current_user_id)
            
            flash(f'Project "{name}" created successfully.', 'success')
            return redirect(url_for('projects.project_detail', project_id=project.id))
            
        except Exception as e:
            flash(f'Error creating project: {str(e)}', 'error')
            return render_template('projects/projects/create.html',
                                  csrf_token=g.csrf_token,
                                  form_data=request.form)
    
    return render_template('projects/projects/create.html',
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>')
@login_required
def project_detail(project_id):
    """
    Project detail page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.repository_manager import RepositoryManager
    from automojo.pychestrate.core.managers.build_manager import BuildManager
    from automojo.pychestrate.core.managers.test_manager import TestManager
    
    project_manager = ProjectManager(db_session)
    repository_manager = RepositoryManager(db_session)
    build_manager = BuildManager(db_session)
    test_manager = TestManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    # Check access
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    # Get summary data
    repositories = repository_manager.list_repositories(project_id, limit=5)
    recent_builds = build_manager.list_builds(project_id=project_id, limit=5)
    recent_tests = test_manager.list_jobs(project_id=project_id, limit=5)
    members = project_manager.list_members(project_id, limit=10)
    
    return render_template('projects/projects/detail.html',
                          project=project,
                          repositories=repositories,
                          recent_builds=recent_builds,
                          recent_tests=recent_tests,
                          members=members,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
@project_permission_required('admin')
@validate_csrf
def project_edit(project_id):
    """
    Project edit page and handler.
    
    Requirements: 13.1, 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import (
        ProjectManager, ProjectUpdateRequest
    )
    
    project_manager = ProjectManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            # Parse metadata JSON
            metadata_str = request.form.get('metadata', '')
            metadata = None
            if metadata_str:
                try:
                    import json
                    metadata = json.loads(metadata_str)
                except json.JSONDecodeError:
                    flash('Invalid JSON in metadata field.', 'error')
                    return render_template('projects/projects/edit.html',
                                          project=project,
                                          csrf_token=g.csrf_token)
            
            update_request = ProjectUpdateRequest(
                name=name if name else None,
                description=description if description else None,
                metadata=metadata
            )
            
            project_manager.update_project(project_id, update_request, g.current_user_id)
            
            flash('Project updated successfully.', 'success')
            return redirect(url_for('projects.project_detail', project_id=project_id))
            
        except Exception as e:
            flash(f'Error updating project: {str(e)}', 'error')
    
    return render_template('projects/projects/edit.html',
                          project=project,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/delete', methods=['POST'])
@login_required
@project_permission_required('owner')
@validate_csrf
def project_delete(project_id):
    """
    Project deletion handler.
    
    Requirements: 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    
    project_manager = ProjectManager(db_session)
    
    try:
        project_manager.delete_project(project_id, g.current_user_id)
        flash('Project deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting project: {str(e)}', 'error')
    
    return redirect(url_for('projects.project_list'))


# =============================================================================
# Member Management Endpoints
# =============================================================================

@projects_blueprint.route('/<int:project_id>/members')
@login_required
def member_list(project_id):
    """
    Project member list page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    
    project_manager = ProjectManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    # Check access
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    # Get pagination params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    offset = (page - 1) * per_page
    
    members = project_manager.list_members(project_id, offset=offset, limit=per_page)
    
    # Check if user can manage members
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'admin')
    
    total_pages = 1 if len(members) < per_page else page + 1
    
    return render_template('projects/members/list.html',
                          project=project,
                          members=members,
                          can_manage=can_manage,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/members/add', methods=['GET', 'POST'])
@login_required
@project_permission_required('admin')
@validate_csrf
def member_add(project_id):
    """
    Add member to project page and handler.
    
    Requirements: 13.1, 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager, ProjectRole
    from automojo.pychestrate.core.managers.user_manager import UserManager
    
    project_manager = ProjectManager(db_session)
    user_manager = UserManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if request.method == 'POST':
        try:
            user_id = request.form.get('user_id', type=int)
            role_str = request.form.get('role', 'viewer')
            
            role = ProjectRole(role_str)
            
            project_manager.add_member(project_id, user_id, role, g.current_user_id)
            
            flash('Member added successfully.', 'success')
            return redirect(url_for('projects.member_list', project_id=project_id))
            
        except Exception as e:
            flash(f'Error adding member: {str(e)}', 'error')
    
    # Get available users (not already members)
    current_members = project_manager.list_members(project_id, limit=1000)
    member_ids = {m.user_id for m in current_members}
    
    all_users = user_manager.list_users(limit=1000)
    available_users = [u for u in all_users.users if u.id not in member_ids]
    
    roles = [r.value for r in ProjectRole]
    
    return render_template('projects/members/add.html',
                          project=project,
                          available_users=available_users,
                          roles=roles,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/members/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@project_permission_required('admin')
@validate_csrf
def member_edit(project_id, user_id):
    """
    Edit member role page and handler.
    
    Requirements: 13.1, 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager, ProjectRole
    
    project_manager = ProjectManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if request.method == 'POST':
        try:
            role_str = request.form.get('role', 'viewer')
            role = ProjectRole(role_str)
            
            project_manager.update_member_role(project_id, user_id, role, g.current_user_id)
            
            flash('Member role updated successfully.', 'success')
            return redirect(url_for('projects.member_list', project_id=project_id))
            
        except Exception as e:
            flash(f'Error updating member role: {str(e)}', 'error')
    
    # Get current member info
    members = project_manager.list_members(project_id, limit=1000)
    member = next((m for m in members if m.user_id == user_id), None)
    
    if not member:
        flash('Member not found.', 'error')
        return redirect(url_for('projects.member_list', project_id=project_id))
    
    roles = [r.value for r in ProjectRole]
    
    return render_template('projects/members/edit.html',
                          project=project,
                          member=member,
                          roles=roles,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/members/<int:user_id>/remove', methods=['POST'])
@login_required
@project_permission_required('admin')
@validate_csrf
def member_remove(project_id, user_id):
    """
    Remove member from project handler.
    
    Requirements: 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    
    project_manager = ProjectManager(db_session)
    
    try:
        project_manager.remove_member(project_id, user_id, g.current_user_id)
        flash('Member removed successfully.', 'success')
    except Exception as e:
        flash(f'Error removing member: {str(e)}', 'error')
    
    return redirect(url_for('projects.member_list', project_id=project_id))


# =============================================================================
# Repository Management Endpoints
# =============================================================================

@projects_blueprint.route('/<int:project_id>/repositories')
@login_required
def repository_list(project_id):
    """
    Repository list page for a project.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.repository_manager import RepositoryManager
    
    project_manager = ProjectManager(db_session)
    repository_manager = RepositoryManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    # Check access
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    # Get pagination params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    offset = (page - 1) * per_page
    
    repositories = repository_manager.list_repositories(project_id, offset=offset, limit=per_page)
    
    # Check if user can manage repositories
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    total_pages = 1 if len(repositories) < per_page else page + 1
    
    return render_template('projects/repositories/list.html',
                          project=project,
                          repositories=repositories,
                          can_manage=can_manage,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/repositories/create', methods=['GET', 'POST'])
@login_required
@project_permission_required('developer')
@validate_csrf
def repository_create(project_id):
    """
    Repository creation page and handler.
    
    Requirements: 13.1, 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.repository_manager import (
        RepositoryManager, RepositoryCreateRequest, RepositoryAuthType
    )
    
    project_manager = ProjectManager(db_session)
    repository_manager = RepositoryManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            url = request.form.get('url', '').strip()
            auth_type_str = request.form.get('auth_type', 'none')
            credential_secret_ref = request.form.get('credential_secret_ref', '').strip()
            default_branch = request.form.get('default_branch', 'main').strip()
            description = request.form.get('description', '').strip()
            
            auth_type = RepositoryAuthType(auth_type_str)
            
            create_request = RepositoryCreateRequest(
                name=name,
                url=url,
                auth_type=auth_type,
                credential_secret_ref=credential_secret_ref if credential_secret_ref else None,
                default_branch=default_branch,
                description=description
            )
            
            repository = repository_manager.add_repository(project_id, create_request, g.current_user_id)
            
            flash(f'Repository "{name}" added successfully.', 'success')
            return redirect(url_for('projects.repository_detail', 
                                   project_id=project_id, 
                                   repository_id=repository.id))
            
        except Exception as e:
            flash(f'Error adding repository: {str(e)}', 'error')
            return render_template('projects/repositories/create.html',
                                  project=project,
                                  csrf_token=g.csrf_token,
                                  form_data=request.form)
    
    auth_types = [t.value for t in RepositoryAuthType]
    
    return render_template('projects/repositories/create.html',
                          project=project,
                          auth_types=auth_types,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/repositories/<int:repository_id>')
@login_required
def repository_detail(project_id, repository_id):
    """
    Repository detail page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.repository_manager import RepositoryManager
    
    project_manager = ProjectManager(db_session)
    repository_manager = RepositoryManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    # Check access
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    repository = repository_manager.get_repository(repository_id)
    
    if not repository or repository.project_id != project_id:
        flash('Repository not found.', 'error')
        return redirect(url_for('projects.repository_list', project_id=project_id))
    
    # Check if user can manage
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/repositories/detail.html',
                          project=project,
                          repository=repository,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/repositories/<int:repository_id>/edit', methods=['GET', 'POST'])
@login_required
@project_permission_required('developer')
@validate_csrf
def repository_edit(project_id, repository_id):
    """
    Repository edit page and handler.
    
    Requirements: 13.1, 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.repository_manager import (
        RepositoryManager, RepositoryUpdateRequest
    )
    
    project_manager = ProjectManager(db_session)
    repository_manager = RepositoryManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    repository = repository_manager.get_repository(repository_id)
    
    if not repository or repository.project_id != project_id:
        flash('Repository not found.', 'error')
        return redirect(url_for('projects.repository_list', project_id=project_id))
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            credential_secret_ref = request.form.get('credential_secret_ref', '').strip()
            default_branch = request.form.get('default_branch', '').strip()
            description = request.form.get('description', '').strip()
            
            update_request = RepositoryUpdateRequest(
                name=name if name else None,
                credential_secret_ref=credential_secret_ref if credential_secret_ref else None,
                default_branch=default_branch if default_branch else None,
                description=description if description else None
            )
            
            repository_manager.update_repository(repository_id, update_request, g.current_user_id)
            
            flash('Repository updated successfully.', 'success')
            return redirect(url_for('projects.repository_detail', 
                                   project_id=project_id, 
                                   repository_id=repository_id))
            
        except Exception as e:
            flash(f'Error updating repository: {str(e)}', 'error')
    
    return render_template('projects/repositories/edit.html',
                          project=project,
                          repository=repository,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/repositories/<int:repository_id>/delete', methods=['POST'])
@login_required
@project_permission_required('admin')
@validate_csrf
def repository_delete(project_id, repository_id):
    """
    Repository deletion handler.
    
    Requirements: 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.repository_manager import RepositoryManager
    
    repository_manager = RepositoryManager(db_session)
    
    try:
        repository_manager.remove_repository(repository_id, g.current_user_id)
        flash('Repository removed successfully.', 'success')
    except Exception as e:
        flash(f'Error removing repository: {str(e)}', 'error')
    
    return redirect(url_for('projects.repository_list', project_id=project_id))


@projects_blueprint.route('/<int:project_id>/repositories/<int:repository_id>/test', methods=['POST'])
@login_required
@project_permission_required('developer')
@validate_csrf
def repository_test(project_id, repository_id):
    """
    Test repository connectivity handler.
    
    Requirements: 13.2
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.repository_manager import RepositoryManager
    
    repository_manager = RepositoryManager(db_session)
    
    try:
        success = repository_manager.test_connectivity(repository_id)
        if success:
            flash('Repository connectivity test successful.', 'success')
        else:
            flash('Repository connectivity test failed.', 'error')
    except Exception as e:
        flash(f'Error testing repository: {str(e)}', 'error')
    
    return redirect(url_for('projects.repository_detail', 
                           project_id=project_id, 
                           repository_id=repository_id))


@projects_blueprint.route('/<int:project_id>/repositories/<int:repository_id>/fetch', methods=['POST'])
@login_required
@project_permission_required('developer')
@validate_csrf
def repository_fetch(project_id, repository_id):
    """
    Fetch latest repository information handler.
    
    Requirements: 13.2
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.repository_manager import RepositoryManager
    
    repository_manager = RepositoryManager(db_session)
    
    try:
        repository_manager.fetch_latest(repository_id)
        flash('Repository information updated.', 'success')
    except Exception as e:
        flash(f'Error fetching repository: {str(e)}', 'error')
    
    return redirect(url_for('projects.repository_detail', 
                           project_id=project_id, 
                           repository_id=repository_id))


# =============================================================================
# Build Management Endpoints
# =============================================================================

@projects_blueprint.route('/<int:project_id>/builds')
@login_required
def build_list(project_id):
    """
    Build list page for a project.
    
    Requirements: 13.1, 13.4, 13.6
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.build_manager import BuildManager
    
    project_manager = ProjectManager(db_session)
    build_manager = BuildManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    spec_id = request.args.get('spec_id', type=int)
    
    offset = (page - 1) * per_page
    
    builds = build_manager.list_builds(
        project_id=project_id,
        spec_id=spec_id,
        status=status,
        offset=offset,
        limit=per_page
    )
    
    specs = build_manager.list_specs(project_id, limit=100)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    total_pages = 1 if len(builds) < per_page else page + 1
    
    return render_template('projects/builds/list.html',
                          project=project,
                          builds=builds,
                          specs=specs,
                          can_manage=can_manage,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          selected_status=status,
                          selected_spec_id=spec_id,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/builds/specs')
@login_required
def build_spec_list(project_id):
    """
    Build specification list page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.build_manager import BuildManager
    
    project_manager = ProjectManager(db_session)
    build_manager = BuildManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    specs = build_manager.list_specs(project_id, offset=offset, limit=per_page)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    total_pages = 1 if len(specs) < per_page else page + 1
    
    return render_template('projects/builds/spec_list.html',
                          project=project,
                          specs=specs,
                          can_manage=can_manage,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/builds/specs/create', methods=['GET', 'POST'])
@login_required
@project_permission_required('developer')
@validate_csrf
def build_spec_create(project_id):
    """
    Build specification creation page and handler.
    
    Requirements: 13.1, 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.repository_manager import RepositoryManager
    from automojo.pychestrate.core.managers.build_manager import BuildManager, BuildSpecCreateRequest
    import json
    
    project_manager = ProjectManager(db_session)
    repository_manager = RepositoryManager(db_session)
    build_manager = BuildManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            repository_id = request.form.get('repository_id', type=int)
            branch = request.form.get('branch', 'main').strip()
            steps_json = request.form.get('steps', '[]')
            environment_json = request.form.get('environment', '{}')
            timeout_minutes = request.form.get('timeout_minutes', 60, type=int)
            description = request.form.get('description', '').strip()
            
            steps = json.loads(steps_json) if steps_json else []
            environment = json.loads(environment_json) if environment_json else {}
            
            create_request = BuildSpecCreateRequest(
                name=name,
                repository_id=repository_id,
                branch=branch,
                steps=steps,
                environment=environment,
                timeout_minutes=timeout_minutes,
                description=description
            )
            
            spec = build_manager.create_spec(project_id, create_request, g.current_user_id)
            
            flash(f'Build specification "{name}" created successfully.', 'success')
            return redirect(url_for('projects.build_spec_detail', 
                                   project_id=project_id, spec_id=spec.id))
            
        except json.JSONDecodeError:
            flash('Invalid JSON in steps or environment field.', 'error')
        except Exception as e:
            flash(f'Error creating build specification: {str(e)}', 'error')
    
    repositories = repository_manager.list_repositories(project_id, limit=100)
    
    return render_template('projects/builds/spec_create.html',
                          project=project,
                          repositories=repositories,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/builds/specs/<int:spec_id>')
@login_required
def build_spec_detail(project_id, spec_id):
    """
    Build specification detail page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.build_manager import BuildManager
    
    project_manager = ProjectManager(db_session)
    build_manager = BuildManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    spec = build_manager.get_spec(spec_id)
    
    if not spec or spec.project_id != project_id:
        flash('Build specification not found.', 'error')
        return redirect(url_for('projects.build_spec_list', project_id=project_id))
    
    recent_builds = build_manager.list_builds(spec_id=spec_id, limit=10)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/builds/spec_detail.html',
                          project=project,
                          spec=spec,
                          recent_builds=recent_builds,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/builds/<int:build_id>')
@login_required
def build_detail(project_id, build_id):
    """
    Build detail page.
    
    Requirements: 13.1, 13.4, 13.6, 13.7
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.build_manager import BuildManager
    
    project_manager = ProjectManager(db_session)
    build_manager = BuildManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    build = build_manager.get_build(build_id)
    
    if not build or build.project_id != project_id:
        flash('Build not found.', 'error')
        return redirect(url_for('projects.build_list', project_id=project_id))
    
    artifacts = build_manager.list_artifacts(build_id)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/builds/detail.html',
                          project=project,
                          build=build,
                          artifacts=artifacts,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/builds/<int:build_id>/logs')
@login_required
def build_logs(project_id, build_id):
    """
    Build logs page.
    
    Requirements: 13.1, 13.7
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.build_manager import BuildManager
    
    project_manager = ProjectManager(db_session)
    build_manager = BuildManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    build = build_manager.get_build(build_id)
    
    if not build or build.project_id != project_id:
        flash('Build not found.', 'error')
        return redirect(url_for('projects.build_list', project_id=project_id))
    
    step_name = request.args.get('step')
    logs = build_manager.get_build_logs(build_id, step_name=step_name)
    
    return render_template('projects/builds/logs.html',
                          project=project,
                          build=build,
                          logs=logs,
                          selected_step=step_name,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/builds/trigger', methods=['POST'])
@login_required
@project_permission_required('developer')
@validate_csrf
def build_trigger(project_id):
    """
    Trigger a new build handler.
    
    Requirements: 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.build_manager import BuildManager, BuildTriggerRequest
    
    build_manager = BuildManager(db_session)
    
    try:
        spec_id = request.form.get('spec_id', type=int)
        branch = request.form.get('branch', '').strip()
        commit_sha = request.form.get('commit_sha', '').strip()
        
        trigger_request = BuildTriggerRequest(
            spec_id=spec_id,
            branch=branch if branch else None,
            commit_sha=commit_sha if commit_sha else None
        )
        
        build = build_manager.trigger_build(trigger_request, g.current_user_id)
        
        flash(f'Build #{build.id} triggered successfully.', 'success')
        return redirect(url_for('projects.build_detail', project_id=project_id, build_id=build.id))
        
    except Exception as e:
        flash(f'Error triggering build: {str(e)}', 'error')
    
    return redirect(url_for('projects.build_list', project_id=project_id))


@projects_blueprint.route('/<int:project_id>/builds/<int:build_id>/cancel', methods=['POST'])
@login_required
@project_permission_required('developer')
@validate_csrf
def build_cancel(project_id, build_id):
    """
    Cancel a build handler.
    
    Requirements: 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.build_manager import BuildManager
    
    build_manager = BuildManager(db_session)
    
    try:
        build_manager.cancel_build(build_id, g.current_user_id)
        flash('Build cancelled successfully.', 'success')
    except Exception as e:
        flash(f'Error cancelling build: {str(e)}', 'error')
    
    return redirect(url_for('projects.build_detail', project_id=project_id, build_id=build_id))


# =============================================================================
# Infrastructure Management Endpoints
# =============================================================================

@projects_blueprint.route('/<int:project_id>/infrastructure')
@login_required
def infra_job_list(project_id):
    """
    Infrastructure job list page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
    
    project_manager = ProjectManager(db_session)
    infra_manager = InfrastructureManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    spec_id = request.args.get('spec_id', type=int)
    
    offset = (page - 1) * per_page
    
    jobs = infra_manager.list_jobs(
        project_id=project_id,
        spec_id=spec_id,
        status=status,
        offset=offset,
        limit=per_page
    )
    
    specs = infra_manager.list_specs(project_id, limit=100)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    total_pages = 1 if len(jobs) < per_page else page + 1
    
    return render_template('projects/infrastructure/list.html',
                          project=project,
                          jobs=jobs,
                          specs=specs,
                          can_manage=can_manage,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          selected_status=status,
                          selected_spec_id=spec_id,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/infrastructure/specs')
@login_required
def infra_spec_list(project_id):
    """
    Infrastructure specification list page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
    
    project_manager = ProjectManager(db_session)
    infra_manager = InfrastructureManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    specs = infra_manager.list_specs(project_id, offset=offset, limit=per_page)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    total_pages = 1 if len(specs) < per_page else page + 1
    
    return render_template('projects/infrastructure/spec_list.html',
                          project=project,
                          specs=specs,
                          can_manage=can_manage,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/infrastructure/specs/<int:spec_id>')
@login_required
def infra_spec_detail(project_id, spec_id):
    """
    Infrastructure specification detail page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
    
    project_manager = ProjectManager(db_session)
    infra_manager = InfrastructureManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    spec = infra_manager.get_spec(spec_id)
    
    if not spec or spec.project_id != project_id:
        flash('Infrastructure specification not found.', 'error')
        return redirect(url_for('projects.infra_spec_list', project_id=project_id))
    
    recent_jobs = infra_manager.list_jobs(spec_id=spec_id, limit=10)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/infrastructure/spec_detail.html',
                          project=project,
                          spec=spec,
                          recent_jobs=recent_jobs,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/infrastructure/<int:job_id>')
@login_required
def infra_job_detail(project_id, job_id):
    """
    Infrastructure job detail page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
    
    project_manager = ProjectManager(db_session)
    infra_manager = InfrastructureManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    job = infra_manager.get_job(job_id)
    
    if not job or job.project_id != project_id:
        flash('Infrastructure job not found.', 'error')
        return redirect(url_for('projects.infra_job_list', project_id=project_id))
    
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/infrastructure/detail.html',
                          project=project,
                          job=job,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/infrastructure/<int:job_id>/logs')
@login_required
def infra_job_logs(project_id, job_id):
    """
    Infrastructure job logs page.
    
    Requirements: 13.1
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
    
    project_manager = ProjectManager(db_session)
    infra_manager = InfrastructureManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    job = infra_manager.get_job(job_id)
    
    if not job or job.project_id != project_id:
        flash('Infrastructure job not found.', 'error')
        return redirect(url_for('projects.infra_job_list', project_id=project_id))
    
    logs = infra_manager.get_job_logs(job_id)
    
    return render_template('projects/infrastructure/logs.html',
                          project=project,
                          job=job,
                          logs=logs,
                          csrf_token=g.csrf_token)


# =============================================================================
# Test Management Endpoints
# =============================================================================

@projects_blueprint.route('/<int:project_id>/tests')
@login_required
def test_job_list(project_id):
    """
    Test job list page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.test_manager import TestManager
    
    project_manager = ProjectManager(db_session)
    test_manager = TestManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    spec_id = request.args.get('spec_id', type=int)
    
    offset = (page - 1) * per_page
    
    jobs = test_manager.list_jobs(
        project_id=project_id,
        spec_id=spec_id,
        status=status,
        offset=offset,
        limit=per_page
    )
    
    specs = test_manager.list_specs(project_id, limit=100)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    total_pages = 1 if len(jobs) < per_page else page + 1
    
    return render_template('projects/tests/list.html',
                          project=project,
                          jobs=jobs,
                          specs=specs,
                          can_manage=can_manage,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          selected_status=status,
                          selected_spec_id=spec_id,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/tests/specs')
@login_required
def test_spec_list(project_id):
    """
    Test specification list page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.test_manager import TestManager
    
    project_manager = ProjectManager(db_session)
    test_manager = TestManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    specs = test_manager.list_specs(project_id, offset=offset, limit=per_page)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    total_pages = 1 if len(specs) < per_page else page + 1
    
    return render_template('projects/tests/spec_list.html',
                          project=project,
                          specs=specs,
                          can_manage=can_manage,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/tests/specs/<int:spec_id>')
@login_required
def test_spec_detail(project_id, spec_id):
    """
    Test specification detail page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.test_manager import TestManager
    
    project_manager = ProjectManager(db_session)
    test_manager = TestManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    spec = test_manager.get_spec(spec_id)
    
    if not spec or spec.project_id != project_id:
        flash('Test specification not found.', 'error')
        return redirect(url_for('projects.test_spec_list', project_id=project_id))
    
    recent_jobs = test_manager.list_jobs(spec_id=spec_id, limit=10)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/tests/spec_detail.html',
                          project=project,
                          spec=spec,
                          recent_jobs=recent_jobs,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/tests/<int:job_id>')
@login_required
def test_job_detail(project_id, job_id):
    """
    Test job detail page with results.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.test_manager import TestManager
    
    project_manager = ProjectManager(db_session)
    test_manager = TestManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    job = test_manager.get_job(job_id)
    
    if not job or job.project_id != project_id:
        flash('Test job not found.', 'error')
        return redirect(url_for('projects.test_job_list', project_id=project_id))
    
    results = test_manager.get_test_results(job_id)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/tests/detail.html',
                          project=project,
                          job=job,
                          results=results,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/tests/<int:job_id>/logs')
@login_required
def test_job_logs(project_id, job_id):
    """
    Test job logs page.
    
    Requirements: 13.1
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.test_manager import TestManager
    
    project_manager = ProjectManager(db_session)
    test_manager = TestManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    job = test_manager.get_job(job_id)
    
    if not job or job.project_id != project_id:
        flash('Test job not found.', 'error')
        return redirect(url_for('projects.test_job_list', project_id=project_id))
    
    logs = test_manager.get_job_logs(job_id)
    
    return render_template('projects/tests/logs.html',
                          project=project,
                          job=job,
                          logs=logs,
                          csrf_token=g.csrf_token)


# =============================================================================
# Release Management Endpoints
# =============================================================================

@projects_blueprint.route('/<int:project_id>/releases')
@login_required
def release_list(project_id):
    """
    Release list page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.release_manager import ReleaseManager
    
    project_manager = ProjectManager(db_session)
    release_manager = ReleaseManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    channel = request.args.get('channel')
    
    offset = (page - 1) * per_page
    
    releases = release_manager.list_releases(
        project_id=project_id,
        status=status,
        channel=channel,
        offset=offset,
        limit=per_page
    )
    
    channels = release_manager.list_channels(project_id)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    total_pages = 1 if len(releases) < per_page else page + 1
    
    return render_template('projects/releases/list.html',
                          project=project,
                          releases=releases,
                          channels=channels,
                          can_manage=can_manage,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          selected_status=status,
                          selected_channel=channel,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/releases/<int:release_id>')
@login_required
def release_detail(project_id, release_id):
    """
    Release detail page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.release_manager import ReleaseManager
    
    project_manager = ProjectManager(db_session)
    release_manager = ReleaseManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    release = release_manager.get_release(release_id)
    
    if not release or release.project_id != project_id:
        flash('Release not found.', 'error')
        return redirect(url_for('projects.release_list', project_id=project_id))
    
    artifacts = release_manager.list_artifacts(release_id)
    channels = release_manager.list_channels(project_id)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/releases/detail.html',
                          project=project,
                          release=release,
                          artifacts=artifacts,
                          channels=channels,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/releases/pipelines')
@login_required
def pipeline_list(project_id):
    """
    Release pipeline list page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.release_manager import ReleaseManager
    
    project_manager = ProjectManager(db_session)
    release_manager = ReleaseManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    pipelines = release_manager.list_pipelines(project_id, offset=offset, limit=per_page)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    total_pages = 1 if len(pipelines) < per_page else page + 1
    
    return render_template('projects/releases/pipeline_list.html',
                          project=project,
                          pipelines=pipelines,
                          can_manage=can_manage,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/releases/pipelines/<int:pipeline_id>')
@login_required
def pipeline_detail(project_id, pipeline_id):
    """
    Release pipeline detail page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.release_manager import ReleaseManager
    
    project_manager = ProjectManager(db_session)
    release_manager = ReleaseManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    pipeline = release_manager.get_pipeline(pipeline_id)
    
    if not pipeline or pipeline.project_id != project_id:
        flash('Pipeline not found.', 'error')
        return redirect(url_for('projects.pipeline_list', project_id=project_id))
    
    recent_runs = release_manager.list_pipeline_runs(pipeline_id=pipeline_id, limit=10)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/releases/pipeline_detail.html',
                          project=project,
                          pipeline=pipeline,
                          recent_runs=recent_runs,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/releases/channels')
@login_required
def channel_list(project_id):
    """
    Release channel list page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.release_manager import ReleaseManager
    
    project_manager = ProjectManager(db_session)
    release_manager = ReleaseManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    channels = release_manager.list_channels(project_id)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/releases/channel_list.html',
                          project=project,
                          channels=channels,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/releases/schedules')
@login_required
def schedule_list(project_id):
    """
    Release schedule list page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.release_manager import ReleaseManager
    
    project_manager = ProjectManager(db_session)
    release_manager = ReleaseManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    schedules = release_manager.list_schedules(project_id)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/releases/schedule_list.html',
                          project=project,
                          schedules=schedules,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


# =============================================================================
# Calendar Event Endpoints
# =============================================================================

@projects_blueprint.route('/<int:project_id>/calendar')
@login_required
def calendar_view(project_id):
    """
    Calendar view page showing release events.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.release_manager import ReleaseManager
    from datetime import datetime, timedelta
    
    project_manager = ProjectManager(db_session)
    release_manager = ReleaseManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    # Get date range from query params or default to current month
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    if start_date_str:
        start_date = datetime.fromisoformat(start_date_str)
    else:
        today = datetime.now()
        start_date = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    if end_date_str:
        end_date = datetime.fromisoformat(end_date_str)
    else:
        # End of month
        next_month = start_date.replace(day=28) + timedelta(days=4)
        end_date = next_month.replace(day=1) - timedelta(seconds=1)
    
    events = release_manager.get_calendar_events(project_id, start_date, end_date)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/calendar/view.html',
                          project=project,
                          events=events,
                          start_date=start_date,
                          end_date=end_date,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/calendar/events')
@login_required
def release_event_list(project_id):
    """
    Release event list page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.release_manager import ReleaseManager
    
    project_manager = ProjectManager(db_session)
    release_manager = ReleaseManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    events = release_manager.list_release_events(project_id, offset=offset, limit=per_page)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    total_pages = 1 if len(events) < per_page else page + 1
    
    return render_template('projects/calendar/event_list.html',
                          project=project,
                          events=events,
                          can_manage=can_manage,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/calendar/events/<int:event_id>')
@login_required
def release_event_detail(project_id, event_id):
    """
    Release event detail page with phases.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.release_manager import ReleaseManager
    
    project_manager = ProjectManager(db_session)
    release_manager = ReleaseManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    event = release_manager.get_release_event(event_id)
    
    if not event or event.project_id != project_id:
        flash('Release event not found.', 'error')
        return redirect(url_for('projects.release_event_list', project_id=project_id))
    
    phases = release_manager.list_phase_events(event_id)
    branches = release_manager.list_release_branches(event_id)
    merge_events = release_manager.list_merge_events(release_event_id=event_id)
    pull_events = release_manager.list_pull_events(release_event_id=event_id)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/calendar/event_detail.html',
                          project=project,
                          event=event,
                          phases=phases,
                          branches=branches,
                          merge_events=merge_events,
                          pull_events=pull_events,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


# =============================================================================
# Watch Management Endpoints
# =============================================================================

@projects_blueprint.route('/<int:project_id>/watches')
@login_required
def watch_list(project_id):
    """
    Watch list page.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.watch_manager import WatchManager
    
    project_manager = ProjectManager(db_session)
    watch_manager = WatchManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    watches = watch_manager.list_watches(project_id, offset=offset, limit=per_page)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    total_pages = 1 if len(watches) < per_page else page + 1
    
    return render_template('projects/watches/list.html',
                          project=project,
                          watches=watches,
                          can_manage=can_manage,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/watches/create', methods=['GET', 'POST'])
@login_required
@project_permission_required('developer')
@validate_csrf
def watch_create(project_id):
    """
    Watch creation page and handler.
    
    Requirements: 13.1, 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.repository_manager import RepositoryManager
    from automojo.pychestrate.core.managers.watch_manager import WatchManager, WatchCreateRequest
    import json
    
    project_manager = ProjectManager(db_session)
    repository_manager = RepositoryManager(db_session)
    watch_manager = WatchManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            trigger_source = request.form.get('trigger_source', '').strip()
            trigger_conditions_json = request.form.get('trigger_conditions', '{}')
            actions_json = request.form.get('actions', '[]')
            description = request.form.get('description', '').strip()
            
            trigger_conditions = json.loads(trigger_conditions_json) if trigger_conditions_json else {}
            actions = json.loads(actions_json) if actions_json else []
            
            create_request = WatchCreateRequest(
                name=name,
                trigger_source=trigger_source,
                trigger_conditions=trigger_conditions,
                actions=actions,
                description=description
            )
            
            watch = watch_manager.create_watch(project_id, create_request, g.current_user_id)
            
            flash(f'Watch "{name}" created successfully.', 'success')
            return redirect(url_for('projects.watch_detail', project_id=project_id, watch_id=watch.id))
            
        except json.JSONDecodeError:
            flash('Invalid JSON in trigger conditions or actions field.', 'error')
        except Exception as e:
            flash(f'Error creating watch: {str(e)}', 'error')
    
    repositories = repository_manager.list_repositories(project_id, limit=100)
    
    return render_template('projects/watches/create.html',
                          project=project,
                          repositories=repositories,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/watches/<int:watch_id>')
@login_required
def watch_detail(project_id, watch_id):
    """
    Watch detail page with trigger history.
    
    Requirements: 13.1, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.watch_manager import WatchManager
    
    project_manager = ProjectManager(db_session)
    watch_manager = WatchManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    if not project_manager.check_permission(project_id, g.current_user_id, 'view'):
        flash('You do not have permission to view this project.', 'error')
        return redirect(url_for('projects.project_list'))
    
    watch = watch_manager.get_watch(watch_id)
    
    if not watch or watch.project_id != project_id:
        flash('Watch not found.', 'error')
        return redirect(url_for('projects.watch_list', project_id=project_id))
    
    trigger_logs = watch_manager.get_trigger_logs(watch_id, limit=20)
    can_manage = project_manager.check_permission(project_id, g.current_user_id, 'developer')
    
    return render_template('projects/watches/detail.html',
                          project=project,
                          watch=watch,
                          trigger_logs=trigger_logs,
                          can_manage=can_manage,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/watches/<int:watch_id>/edit', methods=['GET', 'POST'])
@login_required
@project_permission_required('developer')
@validate_csrf
def watch_edit(project_id, watch_id):
    """
    Watch edit page and handler.
    
    Requirements: 13.1, 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.project_manager import ProjectManager
    from automojo.pychestrate.core.managers.watch_manager import WatchManager, WatchUpdateRequest
    import json
    
    project_manager = ProjectManager(db_session)
    watch_manager = WatchManager(db_session)
    
    project = project_manager.get_project(project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.project_list'))
    
    watch = watch_manager.get_watch(watch_id)
    
    if not watch or watch.project_id != project_id:
        flash('Watch not found.', 'error')
        return redirect(url_for('projects.watch_list', project_id=project_id))
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            trigger_conditions_json = request.form.get('trigger_conditions', '')
            actions_json = request.form.get('actions', '')
            description = request.form.get('description', '').strip()
            
            trigger_conditions = None
            if trigger_conditions_json:
                trigger_conditions = json.loads(trigger_conditions_json)
            
            actions = None
            if actions_json:
                actions = json.loads(actions_json)
            
            update_request = WatchUpdateRequest(
                name=name if name else None,
                trigger_conditions=trigger_conditions,
                actions=actions,
                description=description if description else None
            )
            
            watch_manager.update_watch(watch_id, update_request, g.current_user_id)
            
            flash('Watch updated successfully.', 'success')
            return redirect(url_for('projects.watch_detail', project_id=project_id, watch_id=watch_id))
            
        except json.JSONDecodeError:
            flash('Invalid JSON in trigger conditions or actions field.', 'error')
        except Exception as e:
            flash(f'Error updating watch: {str(e)}', 'error')
    
    return render_template('projects/watches/edit.html',
                          project=project,
                          watch=watch,
                          csrf_token=g.csrf_token)


@projects_blueprint.route('/<int:project_id>/watches/<int:watch_id>/delete', methods=['POST'])
@login_required
@project_permission_required('admin')
@validate_csrf
def watch_delete(project_id, watch_id):
    """
    Watch deletion handler.
    
    Requirements: 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.watch_manager import WatchManager
    
    watch_manager = WatchManager(db_session)
    
    try:
        watch_manager.delete_watch(watch_id, g.current_user_id)
        flash('Watch deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting watch: {str(e)}', 'error')
    
    return redirect(url_for('projects.watch_list', project_id=project_id))


@projects_blueprint.route('/<int:project_id>/watches/<int:watch_id>/enable', methods=['POST'])
@login_required
@project_permission_required('developer')
@validate_csrf
def watch_enable(project_id, watch_id):
    """
    Enable watch handler.
    
    Requirements: 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.watch_manager import WatchManager
    
    watch_manager = WatchManager(db_session)
    
    try:
        watch_manager.enable_watch(watch_id, g.current_user_id)
        flash('Watch enabled successfully.', 'success')
    except Exception as e:
        flash(f'Error enabling watch: {str(e)}', 'error')
    
    return redirect(url_for('projects.watch_detail', project_id=project_id, watch_id=watch_id))


@projects_blueprint.route('/<int:project_id>/watches/<int:watch_id>/disable', methods=['POST'])
@login_required
@project_permission_required('developer')
@validate_csrf
def watch_disable(project_id, watch_id):
    """
    Disable watch handler.
    
    Requirements: 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.watch_manager import WatchManager
    
    watch_manager = WatchManager(db_session)
    
    try:
        watch_manager.disable_watch(watch_id, g.current_user_id)
        flash('Watch disabled successfully.', 'success')
    except Exception as e:
        flash(f'Error disabling watch: {str(e)}', 'error')
    
    return redirect(url_for('projects.watch_detail', project_id=project_id, watch_id=watch_id))


@projects_blueprint.route('/<int:project_id>/watches/<int:watch_id>/test', methods=['POST'])
@login_required
@project_permission_required('developer')
@validate_csrf
def watch_test(project_id, watch_id):
    """
    Test watch handler.
    
    Requirements: 13.2, 13.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.watch_manager import WatchManager
    
    watch_manager = WatchManager(db_session)
    
    try:
        result = watch_manager.test_watch(watch_id)
        if result:
            flash('Watch test successful.', 'success')
        else:
            flash('Watch test completed with no matches.', 'info')
    except Exception as e:
        flash(f'Error testing watch: {str(e)}', 'error')
    
    return redirect(url_for('projects.watch_detail', project_id=project_id, watch_id=watch_id))
