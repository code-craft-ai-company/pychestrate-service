"""
.. module:: variables
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for global variable management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for global variable management:
- POST /variables - create variable
- GET /variables - list variables
- GET /variables/{name} - get variable
- PUT /variables/{name} - update variable
- DELETE /variables/{name} - delete variable
- GET /variables/{name}/history - get change history

Requirements: 7.1, 7.2, 7.3, 7.4
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
    AuthenticationError,
    AuthorizationError,
)


# =============================================================================
# Namespace Configuration
# =============================================================================

VARIABLES_NAMESPACE_PATH = "/config/variables"

variables_ns = Namespace(
    "Variables v1",
    description="Global variable management endpoints for system configuration"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(variables_ns)

variable_create_model = variables_ns.model('VariableCreate', {
    'name': fields.String(required=True, description='Variable name'),
    'value': fields.Raw(required=True, description='Variable value'),
    'var_type': fields.String(required=True, description='Variable type (string, integer, float, boolean, json)'),
    'description': fields.String(description='Variable description'),
    'default_value': fields.Raw(description='Default value')
})

variable_update_model = variables_ns.model('VariableUpdate', {
    'value': fields.Raw(required=True, description='New variable value'),
    'description': fields.String(description='Variable description')
})

variable_response_model = variables_ns.model('VariableResponse', {
    'id': fields.Integer(required=True, description='Variable ID'),
    'name': fields.String(required=True, description='Variable name'),
    'value': fields.Raw(required=True, description='Variable value'),
    'var_type': fields.String(required=True, description='Variable type'),
    'description': fields.String(description='Variable description'),
    'default_value': fields.Raw(description='Default value'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'updated_at': fields.DateTime(description='Last update timestamp'),
    'updated_by': fields.String(description='Username of last updater')
})

variable_list_model = variables_ns.model('VariableList', {
    'items': fields.List(fields.Nested(variable_response_model), description='List of variables'),
    'total': fields.Integer(required=True, description='Total number of variables'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})

variable_history_model = variables_ns.model('VariableHistory', {
    'id': fields.Integer(required=True, description='History entry ID'),
    'variable_name': fields.String(required=True, description='Variable name'),
    'old_value': fields.Raw(description='Previous value'),
    'new_value': fields.Raw(description='New value'),
    'changed_by': fields.String(description='Username of changer'),
    'changed_at': fields.DateTime(description='Change timestamp')
})

variable_history_list_model = variables_ns.model('VariableHistoryList', {
    'items': fields.List(fields.Nested(variable_history_model), description='List of history entries'),
    'total': fields.Integer(required=True, description='Total number of entries'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})


# =============================================================================
# Helper Functions
# =============================================================================

def variable_response_to_dict(var_response):
    """Convert GlobalVariableResponse dataclass to dict."""
    return {
        'id': var_response.id,
        'name': var_response.name,
        'value': var_response.value,
        'var_type': var_response.var_type.value if hasattr(var_response.var_type, 'value') else str(var_response.var_type),
        'description': var_response.description or '',
        'default_value': var_response.default_value,
        'created_at': var_response.created_at.isoformat() if var_response.created_at else None,
        'updated_at': var_response.updated_at.isoformat() if var_response.updated_at else None,
        'updated_by': var_response.updated_by or ''
    }


def history_entry_to_dict(entry):
    """Convert VariableChangeLog dataclass to dict."""
    return {
        'id': entry.id,
        'variable_name': entry.variable_name,
        'old_value': entry.old_value,
        'new_value': entry.new_value,
        'changed_by': entry.changed_by or '',
        'changed_at': entry.changed_at.isoformat() if entry.changed_at else None
    }


# =============================================================================
# Endpoints
# =============================================================================

@variables_ns.route("/")
class VariableCollection(Resource):
    """Variable collection resource for listing and creating variables."""
    
    @variables_ns.doc('list_variables')
    @variables_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @variables_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @variables_ns.param('search', 'Search string for variable name', type=str)
    @variables_ns.response(200, 'Success', variable_list_model)
    @variables_ns.response(401, 'Unauthorized', error_model)
    @variables_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('variables.read')
    def get(self):
        """
        List global variables with pagination.
        
        Requirements: 7.4
        """
        try:
            offset, limit = get_pagination_params()
            search = request.args.get('search')
            
            from automojo.pychestrate.core.managers.global_variable_store import GlobalVariableStore
            
            store = GlobalVariableStore(g.db_session)
            result = store.list_variables(offset=offset, limit=limit, search=search)
            
            return paginated_response(
                items=[variable_response_to_dict(v) for v in result.variables],
                total=result.total,
                offset=result.offset,
                limit=result.limit
            ), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))
    
    @variables_ns.doc('create_variable')
    @variables_ns.expect(variable_create_model)
    @variables_ns.response(201, 'Variable created', variable_response_model)
    @variables_ns.response(400, 'Validation error', error_model)
    @variables_ns.response(401, 'Unauthorized', error_model)
    @variables_ns.response(403, 'Forbidden', error_model)
    @variables_ns.response(409, 'Conflict', error_model)
    @require_auth
    @require_permission('variables.create')
    def post(self):
        """
        Create a new global variable.
        
        Requirements: 7.1
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.global_variable_store import (
                GlobalVariableStore,
                GlobalVariableCreateRequest,
                VariableType,
                ValidationError,
                DuplicateVariableError
            )
            
            name = data.get('name', '').strip()
            value = data.get('value')
            var_type_str = data.get('var_type', '').lower()
            description = data.get('description', '')
            default_value = data.get('default_value')
            
            if not name:
                return validation_error("Variable name required", "name")
            
            if value is None:
                return validation_error("Variable value required", "value")
            
            # Convert var_type string to enum
            try:
                var_type = VariableType(var_type_str)
            except ValueError:
                return validation_error(
                    f"Invalid variable type. Must be one of: string, integer, float, boolean, json",
                    "var_type"
                )
            
            create_request = GlobalVariableCreateRequest(
                name=name,
                value=value,
                var_type=var_type,
                description=description,
                default_value=default_value
            )
            
            store = GlobalVariableStore(g.db_session)
            var_response = store.create_variable(create_request, g.current_user_id)
            
            return variable_response_to_dict(var_response), 201
            
        except ValidationError as e:
            return validation_error(e.message, e.field)
        except DuplicateVariableError as e:
            return conflict_error(e.message, "name")
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))


@variables_ns.route("/<string:name>")
@variables_ns.param('name', 'The variable name')
class VariableResource(Resource):
    """Individual variable resource for get, update, and delete operations."""
    
    @variables_ns.doc('get_variable')
    @variables_ns.response(200, 'Success', variable_response_model)
    @variables_ns.response(401, 'Unauthorized', error_model)
    @variables_ns.response(403, 'Forbidden', error_model)
    @variables_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('variables.read')
    def get(self, name):
        """
        Get a variable by name.
        
        Requirements: 7.4
        """
        try:
            from automojo.pychestrate.core.managers.global_variable_store import GlobalVariableStore
            
            store = GlobalVariableStore(g.db_session)
            var_response = store.get_variable(name)
            
            if var_response is None:
                return not_found_error('Variable', name)
            
            return variable_response_to_dict(var_response), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))
    
    @variables_ns.doc('update_variable')
    @variables_ns.expect(variable_update_model)
    @variables_ns.response(200, 'Variable updated', variable_response_model)
    @variables_ns.response(400, 'Validation error', error_model)
    @variables_ns.response(401, 'Unauthorized', error_model)
    @variables_ns.response(403, 'Forbidden', error_model)
    @variables_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('variables.update')
    def put(self, name):
        """
        Update a variable's value.
        
        Requirements: 7.2
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.global_variable_store import (
                GlobalVariableStore,
                GlobalVariableUpdateRequest,
                ValidationError,
                VariableNotFoundError
            )
            
            value = data.get('value')
            description = data.get('description')
            
            if value is None:
                return validation_error("Variable value required", "value")
            
            update_request = GlobalVariableUpdateRequest(
                value=value,
                description=description
            )
            
            store = GlobalVariableStore(g.db_session)
            var_response = store.update_variable(name, update_request, g.current_user_id)
            
            return variable_response_to_dict(var_response), 200
            
        except VariableNotFoundError:
            return not_found_error('Variable', name)
        except ValidationError as e:
            return validation_error(e.message, e.field)
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))
    
    @variables_ns.doc('delete_variable')
    @variables_ns.response(204, 'Variable deleted')
    @variables_ns.response(401, 'Unauthorized', error_model)
    @variables_ns.response(403, 'Forbidden', error_model)
    @variables_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('variables.delete')
    def delete(self, name):
        """
        Delete a variable.
        
        Requirements: 7.3
        """
        try:
            from automojo.pychestrate.core.managers.global_variable_store import (
                GlobalVariableStore,
                VariableNotFoundError
            )
            
            store = GlobalVariableStore(g.db_session)
            store.delete_variable(name, g.current_user_id)
            
            return '', 204
            
        except VariableNotFoundError:
            return not_found_error('Variable', name)
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))


@variables_ns.route("/<string:name>/history")
@variables_ns.param('name', 'The variable name')
class VariableHistoryResource(Resource):
    """Variable history resource for viewing change history."""
    
    @variables_ns.doc('get_variable_history')
    @variables_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @variables_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @variables_ns.response(200, 'Success', variable_history_list_model)
    @variables_ns.response(401, 'Unauthorized', error_model)
    @variables_ns.response(403, 'Forbidden', error_model)
    @variables_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('variables.read')
    def get(self, name):
        """
        Get change history for a variable.
        
        Requirements: 7.6
        """
        try:
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.global_variable_store import GlobalVariableStore
            
            store = GlobalVariableStore(g.db_session)
            
            # Check if variable exists
            var = store.get_variable(name)
            if var is None:
                return not_found_error('Variable', name)
            
            # get_change_history returns a List[VariableChangeLog]
            history = store.get_change_history(name, offset=offset, limit=limit)
            
            # Since we don't have total count, use len of returned items
            # This is a limitation - for proper pagination we'd need to modify the store
            return paginated_response(
                items=[history_entry_to_dict(h) for h in history],
                total=len(history),
                offset=offset,
                limit=limit
            ), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))


# =============================================================================
# Namespace Publishing
# =============================================================================

def publish_namespaces(version_prefix):
    """
    Publish the variables namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (variables_ns, "".join([version_prefix, VARIABLES_NAMESPACE_PATH]))
    ]
    return ns_list
