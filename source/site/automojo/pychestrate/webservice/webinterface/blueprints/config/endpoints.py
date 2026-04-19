"""
.. module:: endpoints
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Web interface endpoints for system configuration management

.. moduleauthor:: Automation Mojo LLC

This module provides web interface endpoints for:
- User management (list, create, edit, deactivate)
- Role management (list, create, edit)
- Global variable management (list, create, edit, history)
- Secret management (scopes, secrets)
- Session management (list, terminate)
- Audit log viewing

All data modifications use postback URLs as per project conventions.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from functools import wraps

from flask import (
    render_template, request, redirect, url_for, flash, session, g
)

from . import config_blueprint
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
    
    Requirements: 10.4, 10.5
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
    
    Requirements: 10.4
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        db_session = g.db_session
        
        from automojo.pychestrate.core.managers.security_manager import SecurityManager
        security_manager = SecurityManager(db_session)
        
        # Check for admin permission
        if not security_manager.check_permission(g.current_user_id, 'users.manage'):
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('config.dashboard'))
        
        return f(*args, **kwargs)
    
    return decorated_function


def validate_csrf(f):
    """
    Decorator that validates CSRF token for POST requests.
    
    Requirements: 10.2
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            csrf_token = request.form.get('csrf_token')
            if not csrf_token or csrf_token != g.csrf_token:
                flash('Invalid request. Please try again.', 'error')
                return redirect(request.referrer or url_for('config.dashboard'))
        
        return f(*args, **kwargs)
    
    return decorated_function



# =============================================================================
# Error Handling
# =============================================================================

@config_blueprint.errorhandler(Exception)
def handle_error(error):
    """
    Handle errors and display appropriate error messages.
    
    Requirements: 10.3
    """
    error_message = str(error) if error else "An unexpected error occurred"
    flash(error_message, 'error')
    return redirect(url_for('config.dashboard'))


# =============================================================================
# Authentication Endpoints
# =============================================================================

@config_blueprint.route('/login', methods=['GET', 'POST'])
def login():
    """
    Login page and authentication handler.
    
    Requirements: 10.2, 10.5
    """
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('config/login.html')
        
        db_session = get_db_session()
        try:
            from automojo.pychestrate.core.managers.security_manager import (
                SecurityManager, AuthRequest
            )
            
            security_manager = SecurityManager(db_session)
            auth_request = AuthRequest(
                username=username,
                password=password,
                client_ip=request.remote_addr or '',
                user_agent=request.user_agent.string or ''
            )
            
            auth_response = security_manager.authenticate(auth_request)
            
            # Store session info
            session['user_id'] = auth_response.user_id
            session['username'] = auth_response.username
            session['session_token'] = auth_response.token
            session['csrf_token'] = auth_response.csrf_token
            
            flash(f'Welcome, {auth_response.username}!', 'success')
            
            next_url = request.args.get('next')
            if next_url:
                return redirect(next_url)
            return redirect(url_for('config.dashboard'))
            
        except Exception as e:
            flash('Invalid username or password.', 'error')
            return render_template('config/login.html')
        finally:
            db_session.close()
    
    return render_template('config/login.html')


@config_blueprint.route('/logout', methods=['POST'])
def logout():
    """
    Logout handler.
    
    Requirements: 10.2
    """
    session_token = session.get('session_token')
    
    if session_token:
        db_session = get_db_session()
        try:
            from automojo.pychestrate.core.managers.security_manager import SecurityManager
            security_manager = SecurityManager(db_session)
            security_manager.logout(session_token)
        except Exception:
            pass
        finally:
            db_session.close()
    
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('config.login'))



# =============================================================================
# Dashboard
# =============================================================================

@config_blueprint.route('/')
@config_blueprint.route('/dashboard')
@login_required
def dashboard():
    """
    Main dashboard page.
    
    Requirements: 10.1
    """
    return render_template('config/dashboard.html',
                          username=g.current_username,
                          csrf_token=g.csrf_token)


# =============================================================================
# User Management Endpoints
# =============================================================================

@config_blueprint.route('/users')
@login_required
@admin_required
def user_list():
    """
    User list page.
    
    Requirements: 10.1, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.user_manager import UserManager
    
    user_manager = UserManager(db_session)
    
    # Get pagination params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    
    offset = (page - 1) * per_page
    
    result = user_manager.list_users(
        offset=offset,
        limit=per_page,
        search=search if search else None
    )
    
    total_pages = (result.total + per_page - 1) // per_page
    
    return render_template('config/users/list.html',
                          users=result.users,
                          total=result.total,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          search=search,
                          csrf_token=g.csrf_token)


@config_blueprint.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def user_create():
    """
    User creation page and handler.
    
    Requirements: 10.1, 10.2, 10.4
    """
    db_session = g.db_session
    
    if request.method == 'POST':
        from automojo.pychestrate.core.managers.user_manager import (
            UserManager, UserCreateRequest, ValidationError, DuplicateUserError
        )
        from automojo.pychestrate.core.managers.security_manager import SecurityManager
        
        user_manager = UserManager(db_session)
        security_manager = SecurityManager(db_session)
        
        try:
            # Get form data
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            display_name = request.form.get('display_name', '').strip()
            firstname = request.form.get('firstname', '').strip()
            lastname = request.form.get('lastname', '').strip()
            role_ids = request.form.getlist('role_ids', type=int)
            
            # Validate password strength
            violations = security_manager.validate_password_strength(password)
            if violations:
                flash('Password does not meet requirements: ' + ', '.join(violations), 'error')
                return render_template('config/users/create.html',
                                      csrf_token=g.csrf_token,
                                      form_data=request.form)
            
            # Create user
            create_request = UserCreateRequest(
                username=username,
                email=email,
                password=password,
                display_name=display_name,
                firstname=firstname,
                lastname=lastname,
                role_ids=role_ids
            )
            
            user = user_manager.create_user(create_request)
            
            # Add password to history
            password_hash = security_manager.hash_password(password)
            security_manager.add_password_to_history(user.id, password_hash)
            
            flash(f'User "{username}" created successfully.', 'success')
            return redirect(url_for('config.user_list'))
            
        except ValidationError as e:
            flash(f'Validation error: {e.message}', 'error')
        except DuplicateUserError as e:
            flash(f'Duplicate error: {e.message}', 'error')
        except Exception as e:
            flash(f'Error creating user: {str(e)}', 'error')
        
        return render_template('config/users/create.html',
                              csrf_token=g.csrf_token,
                              form_data=request.form)
    
    # GET request - show form with available roles
    from automojo.pychestrate.core.orm import SystemRole
    roles = db_session.query(SystemRole).all()
    
    return render_template('config/users/create.html',
                          csrf_token=g.csrf_token,
                          roles=roles)



@config_blueprint.route('/users/<user_id>')
@login_required
@admin_required
def user_detail(user_id):
    """
    User detail page.
    
    Requirements: 10.1, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.user_manager import UserManager
    
    user_manager = UserManager(db_session)
    user = user_manager.get_user(user_id)
    
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('config.user_list'))
    
    return render_template('config/users/detail.html',
                          user=user,
                          csrf_token=g.csrf_token)


@config_blueprint.route('/users/<user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def user_edit(user_id):
    """
    User edit page and handler.
    
    Requirements: 10.1, 10.2, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.user_manager import (
        UserManager, UserUpdateRequest, ValidationError, DuplicateUserError
    )
    
    user_manager = UserManager(db_session)
    
    if request.method == 'POST':
        try:
            # Get form data
            email = request.form.get('email', '').strip()
            display_name = request.form.get('display_name', '').strip()
            firstname = request.form.get('firstname', '').strip()
            lastname = request.form.get('lastname', '').strip()
            is_active = request.form.get('is_active') == 'on'
            role_ids = request.form.getlist('role_ids', type=int)
            
            update_request = UserUpdateRequest(
                email=email if email else None,
                display_name=display_name if display_name else None,
                firstname=firstname,
                lastname=lastname,
                is_active=is_active,
                role_ids=role_ids
            )
            
            user_manager.update_user(user_id, update_request)
            
            flash('User updated successfully.', 'success')
            return redirect(url_for('config.user_detail', user_id=user_id))
            
        except ValidationError as e:
            flash(f'Validation error: {e.message}', 'error')
        except DuplicateUserError as e:
            flash(f'Duplicate error: {e.message}', 'error')
        except Exception as e:
            flash(f'Error updating user: {str(e)}', 'error')
    
    # GET request or error - show form
    user = user_manager.get_user(user_id)
    
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('config.user_list'))
    
    from automojo.pychestrate.core.orm import SystemRole
    roles = db_session.query(SystemRole).all()
    
    return render_template('config/users/edit.html',
                          user=user,
                          roles=roles,
                          csrf_token=g.csrf_token)


@config_blueprint.route('/users/<user_id>/deactivate', methods=['POST'])
@login_required
@admin_required
@validate_csrf
def user_deactivate(user_id):
    """
    User deactivation handler.
    
    Requirements: 10.2, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.user_manager import UserManager, UserNotFoundError
    
    user_manager = UserManager(db_session)
    
    try:
        user_manager.deactivate_user(user_id)
        flash('User deactivated successfully.', 'success')
    except UserNotFoundError:
        flash('User not found.', 'error')
    except Exception as e:
        flash(f'Error deactivating user: {str(e)}', 'error')
    
    return redirect(url_for('config.user_list'))



# =============================================================================
# Role Management Endpoints
# =============================================================================

@config_blueprint.route('/roles')
@login_required
@admin_required
def role_list():
    """
    Role list page.
    
    Requirements: 10.1, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.orm import SystemRole
    
    roles = db_session.query(SystemRole).all()
    
    return render_template('config/roles/list.html',
                          roles=roles,
                          csrf_token=g.csrf_token)


@config_blueprint.route('/roles/create', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def role_create():
    """
    Role creation page and handler.
    
    Requirements: 10.1, 10.2, 10.4
    """
    db_session = g.db_session
    
    if request.method == 'POST':
        from automojo.pychestrate.core.orm import SystemRole, Permission
        
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            permission_ids = request.form.getlist('permission_ids', type=int)
            
            if not name:
                flash('Role name is required.', 'error')
                return render_template('config/roles/create.html',
                                      csrf_token=g.csrf_token,
                                      form_data=request.form)
            
            # Check for duplicate
            existing = db_session.query(SystemRole).filter(
                SystemRole.name == name
            ).first()
            
            if existing:
                flash(f'Role "{name}" already exists.', 'error')
                return render_template('config/roles/create.html',
                                      csrf_token=g.csrf_token,
                                      form_data=request.form)
            
            # Create role
            role = SystemRole(
                name=name,
                description=description,
                is_system=False
            )
            
            # Add permissions
            if permission_ids:
                permissions = db_session.query(Permission).filter(
                    Permission.id.in_(permission_ids)
                ).all()
                role.permissions = permissions
            
            db_session.add(role)
            db_session.commit()
            
            flash(f'Role "{name}" created successfully.', 'success')
            return redirect(url_for('config.role_list'))
            
        except Exception as e:
            db_session.rollback()
            flash(f'Error creating role: {str(e)}', 'error')
            return render_template('config/roles/create.html',
                                  csrf_token=g.csrf_token,
                                  form_data=request.form)
    
    # GET request - show form with available permissions
    from automojo.pychestrate.core.orm import Permission
    permissions = db_session.query(Permission).all()
    
    return render_template('config/roles/create.html',
                          csrf_token=g.csrf_token,
                          permissions=permissions)


@config_blueprint.route('/roles/<int:role_id>')
@login_required
@admin_required
def role_detail(role_id):
    """
    Role detail page.
    
    Requirements: 10.1, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.orm import SystemRole
    
    role = db_session.query(SystemRole).filter(SystemRole.id == role_id).first()
    
    if not role:
        flash('Role not found.', 'error')
        return redirect(url_for('config.role_list'))
    
    return render_template('config/roles/detail.html',
                          role=role,
                          csrf_token=g.csrf_token)


@config_blueprint.route('/roles/<int:role_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def role_edit(role_id):
    """
    Role edit page and handler.
    
    Requirements: 10.1, 10.2, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.orm import SystemRole, Permission
    
    role = db_session.query(SystemRole).filter(SystemRole.id == role_id).first()
    
    if not role:
        flash('Role not found.', 'error')
        return redirect(url_for('config.role_list'))
    
    if request.method == 'POST':
        try:
            # System roles cannot be modified
            if role.is_system:
                flash('System roles cannot be modified.', 'error')
                return redirect(url_for('config.role_detail', role_id=role_id))
            
            description = request.form.get('description', '').strip()
            permission_ids = request.form.getlist('permission_ids', type=int)
            
            role.description = description
            
            # Update permissions
            if permission_ids:
                permissions = db_session.query(Permission).filter(
                    Permission.id.in_(permission_ids)
                ).all()
                role.permissions = permissions
            else:
                role.permissions = []
            
            db_session.commit()
            
            flash('Role updated successfully.', 'success')
            return redirect(url_for('config.role_detail', role_id=role_id))
            
        except Exception as e:
            db_session.rollback()
            flash(f'Error updating role: {str(e)}', 'error')
    
    # GET request - show form
    permissions = db_session.query(Permission).all()
    current_permission_ids = [p.id for p in role.permissions]
    
    return render_template('config/roles/edit.html',
                          role=role,
                          permissions=permissions,
                          current_permission_ids=current_permission_ids,
                          csrf_token=g.csrf_token)



# =============================================================================
# Global Variable Management Endpoints
# =============================================================================

@config_blueprint.route('/variables')
@login_required
@admin_required
def variable_list():
    """
    Global variable list page.
    
    Requirements: 10.1, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.global_variable_store import GlobalVariableStore
    
    variable_store = GlobalVariableStore(db_session)
    
    # Get pagination params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    
    offset = (page - 1) * per_page
    
    result = variable_store.list_variables(
        offset=offset,
        limit=per_page,
        search=search if search else None
    )
    
    total_pages = (result.total + per_page - 1) // per_page
    
    return render_template('config/variables/list.html',
                          variables=result.variables,
                          total=result.total,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          search=search,
                          csrf_token=g.csrf_token)


@config_blueprint.route('/variables/create', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def variable_create():
    """
    Global variable creation page and handler.
    
    Requirements: 10.1, 10.2, 10.4
    """
    db_session = g.db_session
    
    if request.method == 'POST':
        from automojo.pychestrate.core.managers.global_variable_store import (
            GlobalVariableStore, GlobalVariableCreateRequest, VariableType
        )
        
        variable_store = GlobalVariableStore(db_session)
        
        try:
            name = request.form.get('name', '').strip()
            value = request.form.get('value', '')
            var_type_str = request.form.get('var_type', 'string')
            description = request.form.get('description', '').strip()
            default_value = request.form.get('default_value', '')
            
            var_type = VariableType(var_type_str)
            
            # Parse value based on type
            parsed_value = variable_store.parse_value_from_string(value, var_type)
            parsed_default = None
            if default_value:
                parsed_default = variable_store.parse_value_from_string(default_value, var_type)
            
            create_request = GlobalVariableCreateRequest(
                name=name,
                value=parsed_value,
                var_type=var_type,
                description=description,
                default_value=parsed_default
            )
            
            variable_store.create_variable(create_request, g.current_user_id)
            
            flash(f'Variable "{name}" created successfully.', 'success')
            return redirect(url_for('config.variable_list'))
            
        except ValueError as e:
            flash(f'Invalid value: {str(e)}', 'error')
        except Exception as e:
            flash(f'Error creating variable: {str(e)}', 'error')
        
        return render_template('config/variables/create.html',
                              csrf_token=g.csrf_token,
                              form_data=request.form)
    
    return render_template('config/variables/create.html',
                          csrf_token=g.csrf_token)


@config_blueprint.route('/variables/<name>')
@login_required
@admin_required
def variable_detail(name):
    """
    Global variable detail page.
    
    Requirements: 10.1, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.global_variable_store import GlobalVariableStore
    
    variable_store = GlobalVariableStore(db_session)
    variable = variable_store.get_variable(name)
    
    if not variable:
        flash('Variable not found.', 'error')
        return redirect(url_for('config.variable_list'))
    
    return render_template('config/variables/detail.html',
                          variable=variable,
                          csrf_token=g.csrf_token)


@config_blueprint.route('/variables/<name>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def variable_edit(name):
    """
    Global variable edit page and handler.
    
    Requirements: 10.1, 10.2, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.global_variable_store import (
        GlobalVariableStore, GlobalVariableUpdateRequest
    )
    
    variable_store = GlobalVariableStore(db_session)
    
    if request.method == 'POST':
        try:
            value = request.form.get('value', '')
            description = request.form.get('description', '').strip()
            
            # Get current variable to know its type
            variable = variable_store.get_variable(name)
            if not variable:
                flash('Variable not found.', 'error')
                return redirect(url_for('config.variable_list'))
            
            # Parse value based on type
            parsed_value = variable_store.parse_value_from_string(value, variable.var_type)
            
            update_request = GlobalVariableUpdateRequest(
                value=parsed_value,
                description=description if description else None
            )
            
            variable_store.update_variable(name, update_request, g.current_user_id)
            
            flash('Variable updated successfully.', 'success')
            return redirect(url_for('config.variable_detail', name=name))
            
        except ValueError as e:
            flash(f'Invalid value: {str(e)}', 'error')
        except Exception as e:
            flash(f'Error updating variable: {str(e)}', 'error')
    
    # GET request - show form
    variable = variable_store.get_variable(name)
    
    if not variable:
        flash('Variable not found.', 'error')
        return redirect(url_for('config.variable_list'))
    
    return render_template('config/variables/edit.html',
                          variable=variable,
                          csrf_token=g.csrf_token)


@config_blueprint.route('/variables/<name>/delete', methods=['POST'])
@login_required
@admin_required
@validate_csrf
def variable_delete(name):
    """
    Global variable deletion handler.
    
    Requirements: 10.2, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.global_variable_store import GlobalVariableStore
    
    variable_store = GlobalVariableStore(db_session)
    
    try:
        variable_store.delete_variable(name, g.current_user_id)
        flash(f'Variable "{name}" deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting variable: {str(e)}', 'error')
    
    return redirect(url_for('config.variable_list'))


@config_blueprint.route('/variables/<name>/history')
@login_required
@admin_required
def variable_history(name):
    """
    Global variable change history page.
    
    Requirements: 10.1, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.global_variable_store import GlobalVariableStore
    
    variable_store = GlobalVariableStore(db_session)
    
    # Get pagination params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    offset = (page - 1) * per_page
    
    variable = variable_store.get_variable(name)
    history = variable_store.get_change_history(name, offset=offset, limit=per_page)
    
    if not variable:
        flash('Variable not found.', 'error')
        return redirect(url_for('config.variable_list'))
    
    return render_template('config/variables/history.html',
                          variable=variable,
                          history=history,
                          page=page,
                          per_page=per_page,
                          csrf_token=g.csrf_token)



# =============================================================================
# Secret Management Endpoints
# =============================================================================

@config_blueprint.route('/scopes')
@login_required
@admin_required
def scope_list():
    """
    Secret scope list page.
    
    Requirements: 10.1, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.secret_manager import SecretManager
    import os
    
    encryption_key = os.environ.get('SECRET_ENCRYPTION_KEY', 'default-key-for-dev').encode()
    secret_manager = SecretManager(db_session, encryption_key)
    
    # Get pagination params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    offset = (page - 1) * per_page
    
    scopes = secret_manager.list_scopes(g.current_user_id, offset=offset, limit=per_page)
    
    return render_template('config/secrets/scope_list.html',
                          scopes=scopes,
                          page=page,
                          per_page=per_page,
                          csrf_token=g.csrf_token)


@config_blueprint.route('/scopes/create', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def scope_create():
    """
    Secret scope creation page and handler.
    
    Requirements: 10.1, 10.2, 10.4
    """
    db_session = g.db_session
    
    if request.method == 'POST':
        from automojo.pychestrate.core.managers.secret_manager import (
            SecretManager, SecretScopeCreateRequest
        )
        import os
        
        encryption_key = os.environ.get('SECRET_ENCRYPTION_KEY', 'default-key-for-dev').encode()
        secret_manager = SecretManager(db_session, encryption_key)
        
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            create_request = SecretScopeCreateRequest(
                name=name,
                description=description
            )
            
            secret_manager.create_scope(create_request, g.current_user_id)
            
            flash(f'Scope "{name}" created successfully.', 'success')
            return redirect(url_for('config.scope_list'))
            
        except Exception as e:
            flash(f'Error creating scope: {str(e)}', 'error')
        
        return render_template('config/secrets/scope_create.html',
                              csrf_token=g.csrf_token,
                              form_data=request.form)
    
    return render_template('config/secrets/scope_create.html',
                          csrf_token=g.csrf_token)


@config_blueprint.route('/scopes/<int:scope_id>/delete', methods=['POST'])
@login_required
@admin_required
@validate_csrf
def scope_delete(scope_id):
    """
    Secret scope deletion handler.
    
    Requirements: 10.2, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.secret_manager import SecretManager
    import os
    
    encryption_key = os.environ.get('SECRET_ENCRYPTION_KEY', 'default-key-for-dev').encode()
    secret_manager = SecretManager(db_session, encryption_key)
    
    try:
        secret_manager.delete_scope(scope_id, g.current_user_id)
        flash('Scope deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting scope: {str(e)}', 'error')
    
    return redirect(url_for('config.scope_list'))


@config_blueprint.route('/secrets')
@login_required
@admin_required
def secret_list():
    """
    Secret list page (metadata only).
    
    Requirements: 10.1, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.secret_manager import SecretManager
    import os
    
    encryption_key = os.environ.get('SECRET_ENCRYPTION_KEY', 'default-key-for-dev').encode()
    secret_manager = SecretManager(db_session, encryption_key)
    
    # Get pagination and filter params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    scope_id = request.args.get('scope_id', type=int)
    
    offset = (page - 1) * per_page
    
    secrets = secret_manager.list_secrets(
        scope_id=scope_id,
        user_id=g.current_user_id,
        offset=offset,
        limit=per_page
    )
    
    # Get scopes for filter dropdown
    scopes = secret_manager.list_scopes(g.current_user_id)
    
    return render_template('config/secrets/list.html',
                          secrets=secrets,
                          scopes=scopes,
                          selected_scope_id=scope_id,
                          page=page,
                          per_page=per_page,
                          csrf_token=g.csrf_token)


@config_blueprint.route('/secrets/create', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def secret_create():
    """
    Secret creation page and handler.
    
    Requirements: 10.1, 10.2, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.secret_manager import (
        SecretManager, SecretCreateRequest, SecretType
    )
    import os
    
    encryption_key = os.environ.get('SECRET_ENCRYPTION_KEY', 'default-key-for-dev').encode()
    secret_manager = SecretManager(db_session, encryption_key)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            value = request.form.get('value', '')
            secret_type_str = request.form.get('secret_type', 'generic')
            scope_id = request.form.get('scope_id', type=int)
            description = request.form.get('description', '').strip()
            
            secret_type = SecretType(secret_type_str)
            
            create_request = SecretCreateRequest(
                name=name,
                value=value,
                secret_type=secret_type,
                scope_id=scope_id,
                description=description
            )
            
            secret_manager.create_secret(create_request, g.current_user_id)
            
            flash(f'Secret "{name}" created successfully.', 'success')
            return redirect(url_for('config.secret_list'))
            
        except Exception as e:
            flash(f'Error creating secret: {str(e)}', 'error')
        
        scopes = secret_manager.list_scopes(g.current_user_id)
        return render_template('config/secrets/create.html',
                              csrf_token=g.csrf_token,
                              scopes=scopes,
                              form_data=request.form)
    
    # GET request - show form
    scopes = secret_manager.list_scopes(g.current_user_id)
    
    return render_template('config/secrets/create.html',
                          csrf_token=g.csrf_token,
                          scopes=scopes)


@config_blueprint.route('/secrets/<int:scope_id>/<name>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@validate_csrf
def secret_edit(scope_id, name):
    """
    Secret edit page and handler.
    
    Requirements: 10.1, 10.2, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.secret_manager import (
        SecretManager, SecretUpdateRequest
    )
    import os
    
    encryption_key = os.environ.get('SECRET_ENCRYPTION_KEY', 'default-key-for-dev').encode()
    secret_manager = SecretManager(db_session, encryption_key)
    
    if request.method == 'POST':
        try:
            value = request.form.get('value', '')
            description = request.form.get('description', '').strip()
            
            update_request = SecretUpdateRequest(
                value=value if value else None,
                description=description if description else None
            )
            
            secret_manager.update_secret(name, scope_id, update_request, g.current_user_id)
            
            flash('Secret updated successfully.', 'success')
            return redirect(url_for('config.secret_list'))
            
        except Exception as e:
            flash(f'Error updating secret: {str(e)}', 'error')
    
    # GET request - show form
    secret = secret_manager.get_secret_metadata(name, scope_id)
    
    if not secret:
        flash('Secret not found.', 'error')
        return redirect(url_for('config.secret_list'))
    
    return render_template('config/secrets/edit.html',
                          secret=secret,
                          csrf_token=g.csrf_token)


@config_blueprint.route('/secrets/<int:scope_id>/<name>/delete', methods=['POST'])
@login_required
@admin_required
@validate_csrf
def secret_delete(scope_id, name):
    """
    Secret deletion handler.
    
    Requirements: 10.2, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.secret_manager import SecretManager
    import os
    
    encryption_key = os.environ.get('SECRET_ENCRYPTION_KEY', 'default-key-for-dev').encode()
    secret_manager = SecretManager(db_session, encryption_key)
    
    try:
        secret_manager.delete_secret(name, scope_id, g.current_user_id)
        flash(f'Secret "{name}" deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting secret: {str(e)}', 'error')
    
    return redirect(url_for('config.secret_list'))



# =============================================================================
# Session Management Endpoints
# =============================================================================

@config_blueprint.route('/sessions')
@login_required
@admin_required
def session_list():
    """
    Active sessions list page.
    
    Requirements: 10.1, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.security_manager import SecurityManager
    
    security_manager = SecurityManager(db_session)
    
    # Get filter params
    user_id = request.args.get('user_id')
    
    sessions = security_manager.list_active_sessions(user_id=user_id)
    
    return render_template('config/sessions/list.html',
                          sessions=sessions,
                          filter_user_id=user_id,
                          csrf_token=g.csrf_token)


@config_blueprint.route('/sessions/<int:session_id>/terminate', methods=['POST'])
@login_required
@admin_required
@validate_csrf
def session_terminate(session_id):
    """
    Session termination handler.
    
    Requirements: 10.2, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.security_manager import SecurityManager
    
    security_manager = SecurityManager(db_session)
    
    try:
        security_manager.terminate_session(session_id)
        flash('Session terminated successfully.', 'success')
    except Exception as e:
        flash(f'Error terminating session: {str(e)}', 'error')
    
    return redirect(url_for('config.session_list'))


# =============================================================================
# Audit Log Endpoints
# =============================================================================

@config_blueprint.route('/audit-logs')
@login_required
@admin_required
def audit_log_list():
    """
    Audit log viewer page with filtering.
    
    Requirements: 10.1, 10.4
    """
    db_session = g.db_session
    
    from automojo.pychestrate.core.managers.audit_logger import (
        AuditLogger, AuditLogQuery, AuditEventType
    )
    from datetime import datetime
    
    audit_logger = AuditLogger(db_session)
    
    # Get pagination and filter params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    event_type = request.args.get('event_type')
    user_id = request.args.get('user_id')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
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
    
    # Parse event types
    event_types = None
    if event_type:
        try:
            event_types = [AuditEventType(event_type)]
        except ValueError:
            pass
    
    query = AuditLogQuery(
        event_types=event_types,
        user_id=int(user_id) if user_id else None,
        start_date=start_date,
        end_date=end_date,
        offset=offset,
        limit=per_page
    )
    
    logs = audit_logger.query_logs(query)
    
    # Get all event types for filter dropdown
    all_event_types = [e.value for e in AuditEventType]
    
    return render_template('config/audit/list.html',
                          logs=logs,
                          all_event_types=all_event_types,
                          selected_event_type=event_type,
                          filter_user_id=user_id,
                          start_date=start_date_str,
                          end_date=end_date_str,
                          page=page,
                          per_page=per_page,
                          csrf_token=g.csrf_token)

