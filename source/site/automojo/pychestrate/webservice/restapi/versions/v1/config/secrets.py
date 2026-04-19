"""
.. module:: secrets
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for secret management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for secret management:
- POST /scopes - create scope
- GET /scopes - list scopes
- DELETE /scopes/{id} - delete scope
- POST /secrets - create secret
- GET /secrets - list secrets (metadata only)
- GET /secrets/{scope}/{name} - get secret value
- PUT /secrets/{scope}/{name} - update secret
- DELETE /secrets/{scope}/{name} - delete secret

Requirements: 11.1, 11.7, 11.9, 12.1, 12.4
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

SCOPES_NAMESPACE_PATH = "/config/scopes"
SECRETS_NAMESPACE_PATH = "/config/secrets"

secrets_ns = Namespace(
    "Secrets v1",
    description="Secret management endpoints for system configuration"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(secrets_ns)

# Scope models
scope_create_model = secrets_ns.model('ScopeCreate', {
    'name': fields.String(required=True, description='Scope name'),
    'description': fields.String(description='Scope description')
})

scope_response_model = secrets_ns.model('ScopeResponse', {
    'id': fields.Integer(required=True, description='Scope ID'),
    'name': fields.String(required=True, description='Scope name'),
    'description': fields.String(description='Scope description'),
    'secret_count': fields.Integer(required=True, description='Number of secrets in scope'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'created_by': fields.String(description='Creator username')
})

scope_list_model = secrets_ns.model('ScopeList', {
    'items': fields.List(fields.Nested(scope_response_model), description='List of scopes'),
    'total': fields.Integer(required=True, description='Total number of scopes'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})

# Secret models
secret_create_model = secrets_ns.model('SecretCreate', {
    'name': fields.String(required=True, description='Secret name'),
    'value': fields.String(required=True, description='Secret value'),
    'secret_type': fields.String(required=True, description='Secret type (password, api_key, certificate, ssh_key, generic)'),
    'scope_id': fields.Integer(required=True, description='Scope ID'),
    'description': fields.String(description='Secret description')
})

secret_update_model = secrets_ns.model('SecretUpdate', {
    'value': fields.String(description='New secret value'),
    'description': fields.String(description='Secret description')
})

secret_metadata_model = secrets_ns.model('SecretMetadata', {
    'id': fields.Integer(required=True, description='Secret ID'),
    'name': fields.String(required=True, description='Secret name'),
    'secret_type': fields.String(required=True, description='Secret type'),
    'scope_id': fields.Integer(required=True, description='Scope ID'),
    'scope_name': fields.String(required=True, description='Scope name'),
    'description': fields.String(description='Secret description'),
    'version': fields.Integer(required=True, description='Secret version'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'updated_at': fields.DateTime(description='Last update timestamp'),
    'updated_by': fields.String(description='Username of last updater')
})

secret_value_model = secrets_ns.model('SecretValue', {
    'name': fields.String(required=True, description='Secret name'),
    'value': fields.String(required=True, description='Decrypted secret value'),
    'secret_type': fields.String(required=True, description='Secret type')
})

secret_list_model = secrets_ns.model('SecretList', {
    'items': fields.List(fields.Nested(secret_metadata_model), description='List of secrets (metadata only)'),
    'total': fields.Integer(required=True, description='Total number of secrets'),
    'offset': fields.Integer(required=True, description='Current offset'),
    'limit': fields.Integer(required=True, description='Items per page')
})


# =============================================================================
# Helper Functions
# =============================================================================

def scope_response_to_dict(scope_response):
    """Convert SecretScopeResponse dataclass to dict."""
    return {
        'id': scope_response.id,
        'name': scope_response.name,
        'description': scope_response.description or '',
        'secret_count': scope_response.secret_count,
        'created_at': scope_response.created_at.isoformat() if scope_response.created_at else None,
        'created_by': scope_response.created_by or ''
    }


def secret_metadata_to_dict(metadata):
    """Convert SecretMetadataResponse dataclass to dict."""
    return {
        'id': metadata.id,
        'name': metadata.name,
        'secret_type': metadata.secret_type.value if hasattr(metadata.secret_type, 'value') else str(metadata.secret_type),
        'scope_id': metadata.scope_id,
        'scope_name': metadata.scope_name,
        'description': metadata.description or '',
        'version': metadata.version,
        'created_at': metadata.created_at.isoformat() if metadata.created_at else None,
        'updated_at': metadata.updated_at.isoformat() if metadata.updated_at else None,
        'updated_by': metadata.updated_by or ''
    }


def get_secret_manager():
    """Get a SecretManager instance with encryption key from environment."""
    import os
    from automojo.pychestrate.core.managers.secret_manager import SecretManager
    
    # Get encryption key from environment or use a default for development
    encryption_key = os.environ.get('SECRET_ENCRYPTION_KEY', '')
    if not encryption_key:
        # Use a default key for development (32 bytes for AES-256)
        encryption_key = 'development_key_32_bytes_long!!'
    
    # Ensure key is bytes and correct length
    if isinstance(encryption_key, str):
        encryption_key = encryption_key.encode('utf-8')
    
    # Pad or truncate to 32 bytes
    if len(encryption_key) < 32:
        encryption_key = encryption_key + b'\0' * (32 - len(encryption_key))
    elif len(encryption_key) > 32:
        encryption_key = encryption_key[:32]
    
    return SecretManager(g.db_session, encryption_key)


# =============================================================================
# Scope Endpoints
# =============================================================================

@secrets_ns.route("/scopes")
class ScopeCollection(Resource):
    """Scope collection resource for listing and creating scopes."""
    
    @secrets_ns.doc('list_scopes')
    @secrets_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @secrets_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @secrets_ns.response(200, 'Success', scope_list_model)
    @secrets_ns.response(401, 'Unauthorized', error_model)
    @secrets_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('secrets.read')
    def get(self):
        """
        List secret scopes the user has access to.
        
        Requirements: 12.1
        """
        try:
            offset, limit = get_pagination_params()
            
            secret_manager = get_secret_manager()
            scopes = secret_manager.list_scopes(g.current_user_id, offset=offset, limit=limit)
            
            # list_scopes returns a list, not a paginated response
            total = len(scopes)
            
            return paginated_response(
                items=[scope_response_to_dict(s) for s in scopes],
                total=total,
                offset=offset,
                limit=limit
            ), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))
    
    @secrets_ns.doc('create_scope')
    @secrets_ns.expect(scope_create_model)
    @secrets_ns.response(201, 'Scope created', scope_response_model)
    @secrets_ns.response(400, 'Validation error', error_model)
    @secrets_ns.response(401, 'Unauthorized', error_model)
    @secrets_ns.response(403, 'Forbidden', error_model)
    @secrets_ns.response(409, 'Conflict', error_model)
    @require_auth
    @require_permission('secrets.manage')
    def post(self):
        """
        Create a new secret scope.
        
        Requirements: 12.1
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.secret_manager import (
                SecretScopeCreateRequest,
                DuplicateScopeError
            )
            
            name = data.get('name', '').strip()
            description = data.get('description', '')
            
            if not name:
                return validation_error("Scope name required", "name")
            
            create_request = SecretScopeCreateRequest(
                name=name,
                description=description
            )
            
            secret_manager = get_secret_manager()
            scope_response = secret_manager.create_scope(create_request, g.current_user_id)
            
            return scope_response_to_dict(scope_response), 201
            
        except DuplicateScopeError as e:
            return conflict_error(str(e), "name")
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))


@secrets_ns.route("/scopes/<int:scope_id>")
@secrets_ns.param('scope_id', 'The scope identifier')
class ScopeResource(Resource):
    """Individual scope resource for deletion."""
    
    @secrets_ns.doc('delete_scope')
    @secrets_ns.response(204, 'Scope deleted')
    @secrets_ns.response(400, 'Cannot delete scope with secrets', error_model)
    @secrets_ns.response(401, 'Unauthorized', error_model)
    @secrets_ns.response(403, 'Forbidden', error_model)
    @secrets_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('secrets.manage')
    def delete(self, scope_id):
        """
        Delete a secret scope.
        
        Fails if secrets still exist in the scope.
        
        Requirements: 12.4
        """
        try:
            from automojo.pychestrate.core.managers.secret_manager import (
                ScopeNotFoundError,
                ScopeNotEmptyError
            )
            
            secret_manager = get_secret_manager()
            secret_manager.delete_scope(scope_id, g.current_user_id)
            
            return '', 204
            
        except ScopeNotFoundError:
            return not_found_error('Scope', str(scope_id))
        except ScopeNotEmptyError as e:
            return error_response('SCOPE_NOT_EMPTY', str(e), None, 400)
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))


# =============================================================================
# Secret Endpoints
# =============================================================================

@secrets_ns.route("/")
class SecretCollection(Resource):
    """Secret collection resource for listing and creating secrets."""
    
    @secrets_ns.doc('list_secrets')
    @secrets_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @secrets_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @secrets_ns.param('scope_id', 'Filter by scope ID', type=int)
    @secrets_ns.response(200, 'Success', secret_list_model)
    @secrets_ns.response(401, 'Unauthorized', error_model)
    @secrets_ns.response(403, 'Forbidden', error_model)
    @require_auth
    @require_permission('secrets.read')
    def get(self):
        """
        List secrets (metadata only) filtered by user permissions.
        
        Requirements: 11.9, 12.5
        """
        try:
            offset, limit = get_pagination_params()
            scope_id = request.args.get('scope_id', type=int)
            
            secret_manager = get_secret_manager()
            secrets = secret_manager.list_secrets(
                scope_id=scope_id,
                user_id=g.current_user_id,
                offset=offset,
                limit=limit
            )
            
            # list_secrets returns a list
            total = len(secrets)
            
            return paginated_response(
                items=[secret_metadata_to_dict(s) for s in secrets],
                total=total,
                offset=offset,
                limit=limit
            ), 200
            
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))
    
    @secrets_ns.doc('create_secret')
    @secrets_ns.expect(secret_create_model)
    @secrets_ns.response(201, 'Secret created', secret_metadata_model)
    @secrets_ns.response(400, 'Validation error', error_model)
    @secrets_ns.response(401, 'Unauthorized', error_model)
    @secrets_ns.response(403, 'Forbidden', error_model)
    @secrets_ns.response(409, 'Conflict', error_model)
    @require_auth
    @require_permission('secrets.create')
    def post(self):
        """
        Create a new secret with encrypted value.
        
        Requirements: 11.1
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.secret_manager import (
                SecretCreateRequest,
                SecretType,
                DuplicateSecretError,
                ScopeNotFoundError,
                PermissionDeniedError
            )
            
            name = data.get('name', '').strip()
            value = data.get('value', '')
            secret_type_str = data.get('secret_type', '').lower()
            scope_id = data.get('scope_id')
            description = data.get('description', '')
            
            if not name:
                return validation_error("Secret name required", "name")
            
            if not value:
                return validation_error("Secret value required", "value")
            
            if scope_id is None:
                return validation_error("Scope ID required", "scope_id")
            
            # Convert secret_type string to enum
            try:
                secret_type = SecretType(secret_type_str)
            except ValueError:
                return validation_error(
                    "Invalid secret type. Must be one of: password, api_key, certificate, ssh_key, generic",
                    "secret_type"
                )
            
            create_request = SecretCreateRequest(
                name=name,
                value=value,
                secret_type=secret_type,
                scope_id=scope_id,
                description=description
            )
            
            secret_manager = get_secret_manager()
            metadata = secret_manager.create_secret(create_request, g.current_user_id)
            
            return secret_metadata_to_dict(metadata), 201
            
        except DuplicateSecretError as e:
            return conflict_error(str(e), "name")
        except ScopeNotFoundError:
            return not_found_error('Scope', str(scope_id))
        except PermissionDeniedError as e:
            return error_response('FORBIDDEN', str(e), None, 403)
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))


@secrets_ns.route("/<string:scope_name>/<string:secret_name>")
@secrets_ns.param('scope_name', 'The scope name')
@secrets_ns.param('secret_name', 'The secret name')
class SecretResource(Resource):
    """Individual secret resource for get, update, and delete operations."""
    
    @secrets_ns.doc('get_secret_value')
    @secrets_ns.response(200, 'Success', secret_value_model)
    @secrets_ns.response(401, 'Unauthorized', error_model)
    @secrets_ns.response(403, 'Forbidden', error_model)
    @secrets_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('secrets.read')
    def get(self, scope_name, secret_name):
        """
        Get decrypted secret value.
        
        Requires read permission on the scope.
        
        Requirements: 11.7
        """
        try:
            from automojo.pychestrate.core.managers.secret_manager import (
                SecretNotFoundError,
                ScopeNotFoundError,
                PermissionDeniedError
            )
            
            secret_manager = get_secret_manager()
            
            # Get scope by name
            scope = secret_manager.get_scope_by_name(scope_name)
            if scope is None:
                return not_found_error('Scope', scope_name)
            
            secret_value = secret_manager.get_secret_value(
                secret_name,
                scope.id,
                g.current_user_id
            )
            
            return {
                'name': secret_value.name,
                'value': secret_value.value,
                'secret_type': secret_value.secret_type.value if hasattr(secret_value.secret_type, 'value') else str(secret_value.secret_type)
            }, 200
            
        except SecretNotFoundError:
            return not_found_error('Secret', f"{scope_name}/{secret_name}")
        except ScopeNotFoundError:
            return not_found_error('Scope', scope_name)
        except PermissionDeniedError as e:
            return error_response('FORBIDDEN', str(e), None, 403)
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))
    
    @secrets_ns.doc('update_secret')
    @secrets_ns.expect(secret_update_model)
    @secrets_ns.response(200, 'Secret updated', secret_metadata_model)
    @secrets_ns.response(400, 'Validation error', error_model)
    @secrets_ns.response(401, 'Unauthorized', error_model)
    @secrets_ns.response(403, 'Forbidden', error_model)
    @secrets_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('secrets.update')
    def put(self, scope_name, secret_name):
        """
        Update a secret value or metadata.
        
        Increments the version number.
        
        Requirements: 11.4
        """
        try:
            data = request.json
            
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.secret_manager import (
                SecretUpdateRequest,
                SecretNotFoundError,
                ScopeNotFoundError,
                PermissionDeniedError
            )
            
            value = data.get('value')
            description = data.get('description')
            
            update_request = SecretUpdateRequest(
                value=value,
                description=description
            )
            
            secret_manager = get_secret_manager()
            
            # Get scope by name
            scope = secret_manager.get_scope_by_name(scope_name)
            if scope is None:
                return not_found_error('Scope', scope_name)
            
            metadata = secret_manager.update_secret(
                secret_name,
                scope.id,
                update_request,
                g.current_user_id
            )
            
            return secret_metadata_to_dict(metadata), 200
            
        except SecretNotFoundError:
            return not_found_error('Secret', f"{scope_name}/{secret_name}")
        except ScopeNotFoundError:
            return not_found_error('Scope', scope_name)
        except PermissionDeniedError as e:
            return error_response('FORBIDDEN', str(e), None, 403)
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return internal_error(str(e))
    
    @secrets_ns.doc('delete_secret')
    @secrets_ns.response(204, 'Secret deleted')
    @secrets_ns.response(401, 'Unauthorized', error_model)
    @secrets_ns.response(403, 'Forbidden', error_model)
    @secrets_ns.response(404, 'Not found', error_model)
    @require_auth
    @require_permission('secrets.delete')
    def delete(self, scope_name, secret_name):
        """
        Mark a secret as deleted.
        
        Requirements: 11.5
        """
        try:
            from automojo.pychestrate.core.managers.secret_manager import (
                SecretNotFoundError,
                ScopeNotFoundError,
                PermissionDeniedError
            )
            
            secret_manager = get_secret_manager()
            
            # Get scope by name
            scope = secret_manager.get_scope_by_name(scope_name)
            if scope is None:
                return not_found_error('Scope', scope_name)
            
            secret_manager.delete_secret(secret_name, scope.id, g.current_user_id)
            
            return '', 204
            
        except SecretNotFoundError:
            return not_found_error('Secret', f"{scope_name}/{secret_name}")
        except ScopeNotFoundError:
            return not_found_error('Scope', scope_name)
        except PermissionDeniedError as e:
            return error_response('FORBIDDEN', str(e), None, 403)
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
    Publish the secrets namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (secrets_ns, "".join([version_prefix, SECRETS_NAMESPACE_PATH]))
    ]
    return ns_list
