"""
.. module:: secret_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the SecretManager class for secure storage and retrieval of sensitive credentials

.. moduleauthor:: Code Craft AI LLC

This module provides the SecretManager class which handles:
- AES-256-GCM encryption for secret storage (Requirements 11.1, 11.2)
- Secret scope management (Requirements 12.1, 12.2, 12.4)
- Secret CRUD operations (Requirements 11.1, 11.4, 11.5, 11.7, 11.8, 11.9)
- Secret reference resolution (Requirement 11.10)

The implementation uses the cryptography library for AES-256-GCM encryption.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SecretType


# =============================================================================
# Constants
# =============================================================================

# AES-256 key size in bytes (256 bits = 32 bytes)
AES_KEY_SIZE = 32

# GCM nonce size in bytes (96 bits = 12 bytes is recommended)
GCM_NONCE_SIZE = 12

# Secret reference pattern: ${scope/secret_name}
SECRET_REFERENCE_PATTERN = re.compile(r'\$\{([^/]+)/([^}]+)\}')

# Scope and secret names: what the create forms' pattern allows, and what
# a ${scope/secret_name} reference can carry (no '/', '}' or spaces).
SECRET_NAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,127}\Z')
SECRET_NAME_RULE = (
    "letters, digits, underscores and hyphens, starting with a letter"
    " (at most 128 characters)"
)


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class SecretScopeCreateRequest:
    """Request dataclass for creating a new secret scope."""
    name: str
    description: str = ""



@dataclass
class SecretScopeResponse:
    """Response dataclass for secret scope data."""
    id: int
    name: str
    description: str
    is_system: bool
    secret_count: int
    created_at: datetime
    created_by: Optional[str]


@dataclass
class SecretScopeListResponse:
    """Response dataclass for paginated secret scope list."""
    scopes: List['SecretScopeResponse']
    total: int
    offset: int
    limit: int


@dataclass
class SecretCreateRequest:
    """Request dataclass for creating a new secret."""
    name: str
    value: str
    secret_type: SecretType
    scope_id: int
    description: str = ""


@dataclass
class SecretUpdateRequest:
    """Request dataclass for updating an existing secret."""
    value: Optional[str] = None
    description: Optional[str] = None


@dataclass
class SecretMetadataResponse:
    """Response dataclass for secret metadata (never includes the actual value)."""
    id: int
    name: str
    secret_type: SecretType
    scope_id: int
    scope_name: str
    description: str
    version: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str]


@dataclass
class SecretValueResponse:
    """Response dataclass with decrypted value - only for authorized access."""
    name: str
    value: str
    secret_type: SecretType
    scope_name: str


@dataclass
class SecretListResponse:
    """Response dataclass for paginated secret list."""
    secrets: List[SecretMetadataResponse]
    total: int
    offset: int
    limit: int


# =============================================================================
# Exceptions
# =============================================================================

class SecretManagerError(Exception):
    """
    Base exception for secret manager errors.

    ``field`` names the input the error is about (for example ``name`` or
    ``value``), so a form can show the message next to it; it is None when
    the error is about no single input.
    """

    def __init__(self, message: str, field: Optional[str] = None):
        self.message = message
        self.field = field
        super().__init__(self.message)


class ScopeNotFoundError(SecretManagerError):
    """Exception raised when a scope is not found."""
    pass


class ScopeNotEmptyError(SecretManagerError):
    """Exception raised when attempting to delete a scope that contains secrets."""
    pass


class DuplicateScopeError(SecretManagerError):
    """Exception raised when attempting to create a scope with duplicate name."""
    pass


class SecretNotFoundError(SecretManagerError):
    """Exception raised when a secret is not found."""
    pass


class DuplicateSecretError(SecretManagerError):
    """Exception raised when attempting to create a secret with duplicate name in scope."""
    pass


class ScopeAccessDeniedError(SecretManagerError):
    """Exception raised when user lacks permission to access a scope."""
    pass


class EncryptionError(SecretManagerError):
    """Exception raised when encryption or decryption fails."""
    pass


class InvalidSecretReferenceError(SecretManagerError):
    """Exception raised when a secret reference is invalid."""
    pass


# =============================================================================
# Encryption Functions
# =============================================================================

def encrypt_value(plaintext: str, key: bytes) -> bytes:
    """
    Encrypt a secret value using AES-256-GCM.
    
    The encrypted format is: nonce (12 bytes) + ciphertext + tag (16 bytes)
    
    :param plaintext: The plaintext value to encrypt
    :param key: The 32-byte AES-256 encryption key
    :returns: The encrypted bytes (nonce + ciphertext + tag)
    :raises EncryptionError: If encryption fails
    
    Validates: Requirements 11.1, 11.2
    """
    if len(key) != AES_KEY_SIZE:
        raise EncryptionError(f"Invalid key size: expected {AES_KEY_SIZE} bytes, got {len(key)}")
    
    try:
        # Generate a random nonce
        nonce = os.urandom(GCM_NONCE_SIZE)
        
        # Create AESGCM cipher
        aesgcm = AESGCM(key)
        
        # Encrypt the plaintext
        plaintext_bytes = plaintext.encode('utf-8')
        ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)
        
        # Return nonce + ciphertext (ciphertext includes the tag)
        return nonce + ciphertext
    except Exception as e:
        raise EncryptionError(f"Encryption failed: {str(e)}")


def decrypt_value(encrypted_data: bytes, key: bytes) -> str:
    """
    Decrypt a secret value using AES-256-GCM.
    
    :param encrypted_data: The encrypted bytes (nonce + ciphertext + tag)
    :param key: The 32-byte AES-256 encryption key
    :returns: The decrypted plaintext value
    :raises EncryptionError: If decryption fails
    
    Validates: Requirements 11.1, 11.2
    """
    if len(key) != AES_KEY_SIZE:
        raise EncryptionError(f"Invalid key size: expected {AES_KEY_SIZE} bytes, got {len(key)}")
    
    if len(encrypted_data) < GCM_NONCE_SIZE + 16:  # nonce + minimum tag size
        raise EncryptionError("Invalid encrypted data: too short")
    
    try:
        # Extract nonce and ciphertext
        nonce = encrypted_data[:GCM_NONCE_SIZE]
        ciphertext = encrypted_data[GCM_NONCE_SIZE:]
        
        # Create AESGCM cipher
        aesgcm = AESGCM(key)
        
        # Decrypt the ciphertext
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        
        return plaintext_bytes.decode('utf-8')
    except Exception as e:
        raise EncryptionError(f"Decryption failed: {str(e)}")


def generate_encryption_key() -> bytes:
    """
    Generate a new random AES-256 encryption key.
    
    :returns: A 32-byte random key
    """
    return os.urandom(AES_KEY_SIZE)



# =============================================================================
# SecretManager Class
# =============================================================================

class SecretManager:
    """
    Manager class for secure storage and retrieval of sensitive credentials.
    
    This class handles:
    - AES-256-GCM encryption for secret storage (Requirements 11.1, 11.2)
    - Secret scope management (Requirements 12.1, 12.2, 12.4)
    - Secret CRUD operations (Requirements 11.1, 11.4, 11.5, 11.7, 11.8, 11.9)
    - Secret reference resolution (Requirement 11.10)
    
    The implementation uses the cryptography library for AES-256-GCM encryption.
    """
    
    def __init__(self, db_session: DbSession, encryption_key: bytes, audit_logger=None):
        """
        Initialize the SecretManager with a database session and encryption key.
        
        :param db_session: SQLAlchemy database session
        :param encryption_key: 32-byte AES-256 encryption key
        :param audit_logger: Optional AuditLogger instance for audit logging
        :raises EncryptionError: If key size is invalid
        """
        if len(encryption_key) != AES_KEY_SIZE:
            raise EncryptionError(
                f"Invalid encryption key size: expected {AES_KEY_SIZE} bytes, got {len(encryption_key)}"
            )
        
        self._db_session = db_session
        self._encryption_key = encryption_key
        self._audit_logger = audit_logger
    
    # =========================================================================
    # Encryption Methods
    # =========================================================================
    
    def _encrypt_value(self, plaintext: str) -> bytes:
        """
        Encrypt a secret value using AES-256-GCM.
        
        :param plaintext: The plaintext value to encrypt
        :returns: The encrypted bytes
        
        Validates: Requirements 11.1, 11.2
        """
        return encrypt_value(plaintext, self._encryption_key)
    
    def _decrypt_value(self, encrypted_data: bytes) -> str:
        """
        Decrypt a secret value using AES-256-GCM.
        
        :param encrypted_data: The encrypted bytes
        :returns: The decrypted plaintext value
        
        Validates: Requirements 11.1, 11.2
        """
        return decrypt_value(encrypted_data, self._encryption_key)
    
    # =========================================================================
    # Scope Management Methods
    # =========================================================================
    
    def create_scope(
        self,
        request: SecretScopeCreateRequest,
        user_id: str = None
    ) -> SecretScopeResponse:
        """
        Create a new secret scope.
        
        :param request: The scope creation request
        :param user_id: The ID of the user creating the scope
        :returns: SecretScopeResponse with the created scope data
        :raises DuplicateScopeError: If scope name already exists
        
        Validates: Requirements 12.1
        """
        from ccai.pychestrate.core.orm import SecretScope
        
        # Validate name
        if not request.name or len(request.name.strip()) == 0:
            raise SecretManagerError("Scope name is required", field="name")
        
        if len(request.name) > 128:
            raise SecretManagerError("Scope name must be 128 characters or less", field="name")

        if SECRET_NAME_PATTERN.match(request.name) is None:
            raise SecretManagerError("Scope names use " + SECRET_NAME_RULE + ".", field="name")
        
        # Check for duplicate name
        existing = self._db_session.query(SecretScope).filter(
            SecretScope.name == request.name
        ).first()
        
        if existing:
            raise DuplicateScopeError(f"Scope '{request.name}' already exists")
        
        # Create the scope
        now = utc_now()
        
        scope = SecretScope(
            name=request.name,
            description=request.description or "",
            is_system=False,
            created_at=now,
            created_by_id=user_id
        )
        
        self._db_session.add(scope)
        self._db_session.commit()
        
        # Log the scope creation event
        if self._audit_logger and user_id:
            from ccai.pychestrate.core.orm import User
            user = self._db_session.query(User).filter(User.id == user_id).first()
            username = user.login if user else ""
            self._audit_logger.log_scope_created(
                user_id=str(user_id),
                username=username,
                scope_name=request.name
            )
        
        return self._scope_to_response(scope)
    
    def get_scope(self, scope_id: int) -> Optional[SecretScopeResponse]:
        """
        Get a scope by ID.
        
        :param scope_id: The scope ID
        :returns: SecretScopeResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import SecretScope
        
        scope = self._db_session.query(SecretScope).filter(
            SecretScope.id == scope_id
        ).first()
        
        if not scope:
            return None
        
        return self._scope_to_response(scope)
    
    def get_scope_by_name(self, name: str) -> Optional[SecretScopeResponse]:
        """
        Get a scope by name.
        
        :param name: The scope name
        :returns: SecretScopeResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import SecretScope
        
        scope = self._db_session.query(SecretScope).filter(
            SecretScope.name == name
        ).first()
        
        if not scope:
            return None
        
        return self._scope_to_response(scope)
    
    def list_scopes(
        self,
        user_id: str = None,
        offset: int = 0,
        limit: int = 50
    ) -> SecretScopeListResponse:
        """
        List scopes the user has access to.
        
        :param user_id: Optional user ID to filter by permissions
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: SecretScopeListResponse with paginated scope list
        
        Validates: Requirements 12.5
        """
        from ccai.pychestrate.core.orm import SecretScope
        
        query = self._db_session.query(SecretScope)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        scopes = query.order_by(SecretScope.name).offset(offset).limit(limit).all()
        
        return SecretScopeListResponse(
            scopes=[self._scope_to_response(scope) for scope in scopes],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def delete_scope(self, scope_id: int, user_id: str = None) -> None:
        """
        Delete a scope. Fails if secrets still exist in the scope.
        
        :param scope_id: The scope ID to delete
        :param user_id: The ID of the user deleting the scope
        :raises ScopeNotFoundError: If scope is not found
        :raises ScopeNotEmptyError: If scope contains secrets
        
        Validates: Requirements 12.4
        """
        from ccai.pychestrate.core.orm import SecretScope, Secret
        
        scope = self._db_session.query(SecretScope).filter(
            SecretScope.id == scope_id
        ).first()
        
        if not scope:
            raise ScopeNotFoundError(f"Scope with ID {scope_id} not found")
        
        # Check if scope contains secrets (including soft-deleted ones)
        secret_count = self._db_session.query(Secret).filter(
            Secret.scope_id == scope_id
        ).count()
        
        if secret_count > 0:
            raise ScopeNotEmptyError(
                f"Cannot delete scope '{scope.name}': contains {secret_count} secret(s)"
            )
        
        # Store scope name before deletion for audit logging
        scope_name = scope.name
        
        # Delete the scope
        self._db_session.delete(scope)
        self._db_session.commit()
        
        # Log the scope deletion event
        if self._audit_logger and user_id:
            from ccai.pychestrate.core.orm import User
            user = self._db_session.query(User).filter(User.id == user_id).first()
            username = user.login if user else ""
            self._audit_logger.log_scope_deleted(
                user_id=str(user_id),
                username=username,
                scope_name=scope_name
            )
    
    def grant_scope_permission(
        self,
        scope_id: int,
        role_id: int,
        can_read: bool,
        can_manage: bool
    ) -> None:
        """
        Grant role permissions on a scope.
        
        :param scope_id: The scope ID
        :param role_id: The role ID
        :param can_read: Whether the role can read secrets in this scope
        :param can_manage: Whether the role can manage secrets in this scope
        
        Validates: Requirements 12.2
        """
        from ccai.pychestrate.core.orm import SecretScope, SystemRole, scope_permissions
        
        # Verify scope exists
        scope = self._db_session.query(SecretScope).filter(
            SecretScope.id == scope_id
        ).first()
        
        if not scope:
            raise ScopeNotFoundError(f"Scope with ID {scope_id} not found")
        
        # Verify role exists
        role = self._db_session.query(SystemRole).filter(
            SystemRole.id == role_id
        ).first()
        
        if not role:
            raise SecretManagerError(f"Role with ID {role_id} not found")
        
        # Check if permission already exists
        existing = self._db_session.execute(
            scope_permissions.select().where(
                scope_permissions.c.scope_id == scope_id,
                scope_permissions.c.role_id == role_id
            )
        ).first()
        
        if existing:
            # Update existing permission
            self._db_session.execute(
                scope_permissions.update().where(
                    scope_permissions.c.scope_id == scope_id,
                    scope_permissions.c.role_id == role_id
                ).values(can_read=can_read, can_manage=can_manage)
            )
        else:
            # Insert new permission
            self._db_session.execute(
                scope_permissions.insert().values(
                    scope_id=scope_id,
                    role_id=role_id,
                    can_read=can_read,
                    can_manage=can_manage
                )
            )
        
        self._db_session.commit()
    
    def revoke_scope_permission(self, scope_id: int, role_id: int) -> None:
        """
        Revoke role permissions on a scope.
        
        :param scope_id: The scope ID
        :param role_id: The role ID
        
        Validates: Requirements 12.2
        """
        from ccai.pychestrate.core.orm import scope_permissions
        
        self._db_session.execute(
            scope_permissions.delete().where(
                scope_permissions.c.scope_id == scope_id,
                scope_permissions.c.role_id == role_id
            )
        )
        
        self._db_session.commit()
    
    # =========================================================================
    # Secret CRUD Methods
    # =========================================================================
    
    def create_secret(
        self,
        request: SecretCreateRequest,
        user_id: str = None
    ) -> SecretMetadataResponse:
        """
        Create a new secret with encrypted value.
        
        :param request: The secret creation request
        :param user_id: The ID of the user creating the secret
        :returns: SecretMetadataResponse with the created secret metadata
        :raises ScopeNotFoundError: If scope is not found
        :raises DuplicateSecretError: If secret name already exists in scope
        
        Validates: Requirements 11.1
        """
        from ccai.pychestrate.core.orm import SecretScope, Secret, SecretVersion
        
        # Validate name
        if not request.name or len(request.name.strip()) == 0:
            raise SecretManagerError("Secret name is required", field="name")
        
        if len(request.name) > 128:
            raise SecretManagerError("Secret name must be 128 characters or less", field="name")

        if SECRET_NAME_PATTERN.match(request.name) is None:
            raise SecretManagerError("Secret names use " + SECRET_NAME_RULE + ".", field="name")
        
        # Validate value
        if not request.value:
            raise SecretManagerError("Secret value is required", field="value")
        
        # Verify scope exists
        scope = self._db_session.query(SecretScope).filter(
            SecretScope.id == request.scope_id
        ).first()
        
        if not scope:
            raise ScopeNotFoundError(f"Scope with ID {request.scope_id} not found")
        
        # Check for duplicate name in scope
        existing = self._db_session.query(Secret).filter(
            Secret.scope_id == request.scope_id,
            Secret.name == request.name,
            Secret.is_deleted == False
        ).first()
        
        if existing:
            raise DuplicateSecretError(
                f"Secret '{request.name}' already exists in scope '{scope.name}'"
            )
        
        # Encrypt the value
        encrypted_value = self._encrypt_value(request.value)
        
        # Create the secret
        now = utc_now()
        
        secret = Secret(
            name=request.name,
            scope_id=request.scope_id,
            encrypted_value=encrypted_value,
            secret_type=request.secret_type.value,
            description=request.description or "",
            version=1,
            is_deleted=False,
            created_at=now,
            updated_at=now,
            updated_by_id=user_id
        )
        
        self._db_session.add(secret)
        self._db_session.flush()  # Get the secret ID
        
        # Create initial version record
        version = SecretVersion(
            secret_id=secret.id,
            version=1,
            changed_at=now,
            changed_by_id=user_id
        )
        
        self._db_session.add(version)
        self._db_session.commit()
        
        # Log the secret creation event
        if self._audit_logger and user_id:
            from ccai.pychestrate.core.orm import User
            user = self._db_session.query(User).filter(User.id == user_id).first()
            username = user.login if user else ""
            self._audit_logger.log_secret_created(
                user_id=str(user_id),
                username=username,
                secret_name=request.name,
                scope_name=scope.name
            )
        
        return self._secret_to_metadata_response(secret)
    
    def get_secret_metadata(
        self,
        name: str,
        scope_id: int
    ) -> Optional[SecretMetadataResponse]:
        """
        Get secret metadata without the value.
        
        :param name: The secret name
        :param scope_id: The scope ID
        :returns: SecretMetadataResponse if found, None otherwise
        
        Validates: Requirements 11.9
        """
        from ccai.pychestrate.core.orm import Secret
        
        secret = self._db_session.query(Secret).filter(
            Secret.scope_id == scope_id,
            Secret.name == name,
            Secret.is_deleted == False
        ).first()
        
        if not secret:
            return None
        
        return self._secret_to_metadata_response(secret)
    
    def get_secret_value(
        self,
        name: str,
        scope_id: int,
        user_id: str = None
    ) -> SecretValueResponse:
        """
        Get decrypted secret value. Requires read permission.
        
        :param name: The secret name
        :param scope_id: The scope ID
        :param user_id: The ID of the user requesting the secret
        :returns: SecretValueResponse with decrypted value
        :raises SecretNotFoundError: If secret is not found
        :raises ScopeAccessDeniedError: If user lacks read permission
        
        Validates: Requirements 11.2, 11.7
        """
        from ccai.pychestrate.core.orm import Secret, SecretScope
        
        secret = self._db_session.query(Secret).filter(
            Secret.scope_id == scope_id,
            Secret.name == name,
            Secret.is_deleted == False
        ).first()
        
        if not secret:
            raise SecretNotFoundError(f"Secret '{name}' not found in scope")
        
        # Check permission if user_id provided
        if user_id and not self.check_scope_permission(user_id, scope_id, 'read'):
            raise ScopeAccessDeniedError(
                f"User lacks read permission for scope"
            )
        
        # Decrypt the value
        decrypted_value = self._decrypt_value(secret.encrypted_value)
        
        # Get scope name
        scope = self._db_session.query(SecretScope).filter(
            SecretScope.id == scope_id
        ).first()
        
        # Log the secret access event
        if self._audit_logger and user_id:
            from ccai.pychestrate.core.orm import User
            user = self._db_session.query(User).filter(User.id == user_id).first()
            username = user.login if user else ""
            self._audit_logger.log_secret_accessed(
                user_id=str(user_id),
                username=username,
                secret_name=name,
                scope_name=scope.name if scope else ""
            )
        
        return SecretValueResponse(
            name=secret.name,
            value=decrypted_value,
            secret_type=SecretType(secret.secret_type),
            scope_name=scope.name if scope else ""
        )
    
    def update_secret(
        self,
        name: str,
        scope_id: int,
        request: SecretUpdateRequest,
        user_id: str = None
    ) -> SecretMetadataResponse:
        """
        Update secret value or metadata. Increments version.
        
        :param name: The secret name
        :param scope_id: The scope ID
        :param request: The update request
        :param user_id: The ID of the user making the update
        :returns: SecretMetadataResponse with updated secret metadata
        :raises SecretNotFoundError: If secret is not found
        
        Validates: Requirements 11.4
        """
        from ccai.pychestrate.core.orm import Secret, SecretVersion
        
        secret = self._db_session.query(Secret).filter(
            Secret.scope_id == scope_id,
            Secret.name == name,
            Secret.is_deleted == False
        ).first()
        
        if not secret:
            raise SecretNotFoundError(f"Secret '{name}' not found in scope")
        
        now = utc_now()
        
        # Update value if provided
        if request.value is not None:
            secret.encrypted_value = self._encrypt_value(request.value)
            secret.version += 1
            
            # Create version record
            version = SecretVersion(
                secret_id=secret.id,
                version=secret.version,
                changed_at=now,
                changed_by_id=user_id
            )
            self._db_session.add(version)
        
        # Update description if provided
        if request.description is not None:
            secret.description = request.description
        
        secret.updated_at = now
        secret.updated_by_id = user_id
        
        self._db_session.commit()
        
        # Log the secret update event
        if self._audit_logger and user_id:
            from ccai.pychestrate.core.orm import User, SecretScope
            user = self._db_session.query(User).filter(User.id == user_id).first()
            username = user.login if user else ""
            scope = self._db_session.query(SecretScope).filter(
                SecretScope.id == scope_id
            ).first()
            self._audit_logger.log_secret_updated(
                user_id=str(user_id),
                username=username,
                secret_name=name,
                scope_name=scope.name if scope else ""
            )
        
        return self._secret_to_metadata_response(secret)
    
    def delete_secret(
        self,
        name: str,
        scope_id: int,
        user_id: str = None
    ) -> None:
        """
        Mark secret as deleted (soft delete).
        
        :param name: The secret name
        :param scope_id: The scope ID
        :param user_id: The ID of the user deleting the secret
        :raises SecretNotFoundError: If secret is not found
        
        Validates: Requirements 11.5
        """
        from ccai.pychestrate.core.orm import Secret
        
        secret = self._db_session.query(Secret).filter(
            Secret.scope_id == scope_id,
            Secret.name == name,
            Secret.is_deleted == False
        ).first()
        
        if not secret:
            raise SecretNotFoundError(f"Secret '{name}' not found in scope")
        
        # Store scope info before soft delete for audit logging
        scope_id_for_audit = secret.scope_id
        
        # Soft delete
        secret.is_deleted = True
        secret.updated_at = utc_now()
        secret.updated_by_id = user_id
        
        self._db_session.commit()
        
        # Log the secret deletion event
        if self._audit_logger and user_id:
            from ccai.pychestrate.core.orm import User, SecretScope
            user = self._db_session.query(User).filter(User.id == user_id).first()
            username = user.login if user else ""
            scope = self._db_session.query(SecretScope).filter(
                SecretScope.id == scope_id_for_audit
            ).first()
            self._audit_logger.log_secret_deleted(
                user_id=str(user_id),
                username=username,
                secret_name=name,
                scope_name=scope.name if scope else ""
            )
    
    def list_secrets(
        self,
        scope_id: int = None,
        user_id: str = None,
        offset: int = 0,
        limit: int = 50,
        include_deleted: bool = False
    ) -> SecretListResponse:
        """
        List secrets (metadata only) filtered by scope and user permissions.
        
        :param scope_id: Optional scope ID to filter by
        :param user_id: Optional user ID to filter by permissions
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :param include_deleted: Whether to include soft-deleted secrets
        :returns: SecretListResponse with paginated secret list
        
        Validates: Requirements 11.9, 12.5
        """
        from ccai.pychestrate.core.orm import Secret
        
        query = self._db_session.query(Secret)
        
        # Filter by scope if provided
        if scope_id is not None:
            query = query.filter(Secret.scope_id == scope_id)
        
        # Filter out deleted secrets unless requested
        if not include_deleted:
            query = query.filter(Secret.is_deleted == False)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        secrets = query.order_by(Secret.name).offset(offset).limit(limit).all()
        
        return SecretListResponse(
            secrets=[self._secret_to_metadata_response(secret) for secret in secrets],
            total=total,
            offset=offset,
            limit=limit
        )
    
    # =========================================================================
    # Permission Checking Methods
    # =========================================================================
    
    def check_scope_permission(
        self,
        user_id: str,
        scope_id: int,
        permission: str
    ) -> bool:
        """
        Check if user has permission (read/manage) on scope.
        
        :param user_id: The user's unique identifier
        :param scope_id: The scope ID
        :param permission: The permission to check ('read' or 'manage')
        :returns: True if user has the permission, False otherwise
        
        Validates: Requirements 11.7, 12.2
        """
        from ccai.pychestrate.core.orm import User, SystemRole, SecretScope, scope_permissions
        
        # Get user
        user = self._db_session.query(User).filter(User.id == user_id).first()
        
        if not user:
            return False
        
        # Check if user is active
        if user.status != "active":
            return False
        
        # Get scope
        scope = self._db_session.query(SecretScope).filter(
            SecretScope.id == scope_id
        ).first()
        
        if not scope:
            return False
        
        # Get role names from user
        role_names = user.roles.split(",") if user.roles else []
        role_names = [r.strip() for r in role_names if r.strip()]
        
        if not role_names:
            return False
        
        # Get role IDs
        roles = self._db_session.query(SystemRole).filter(
            SystemRole.name.in_(role_names)
        ).all()
        
        role_ids = [role.id for role in roles]
        
        if not role_ids:
            return False
        
        # Check scope permissions for these roles
        for role_id in role_ids:
            perm = self._db_session.execute(
                scope_permissions.select().where(
                    scope_permissions.c.scope_id == scope_id,
                    scope_permissions.c.role_id == role_id
                )
            ).first()
            
            if perm:
                if permission == 'read' and perm.can_read:
                    return True
                if permission == 'manage' and perm.can_manage:
                    return True
        
        return False
    
    # =========================================================================
    # Secret Reference Resolution
    # =========================================================================
    
    def resolve_secret_reference(
        self,
        reference: str,
        user_id: str = None
    ) -> str:
        """
        Resolve a secret reference (e.g., '${scope/secret_name}') to its value.
        
        :param reference: The secret reference string
        :param user_id: The ID of the user requesting the secret
        :returns: The decrypted secret value
        :raises InvalidSecretReferenceError: If reference format is invalid
        :raises SecretNotFoundError: If secret is not found
        :raises ScopeAccessDeniedError: If user lacks read permission
        
        Validates: Requirements 11.10
        """
        # Parse the reference
        match = SECRET_REFERENCE_PATTERN.match(reference)
        
        if not match:
            raise InvalidSecretReferenceError(
                f"Invalid secret reference format: '{reference}'. "
                f"Expected format: ${{scope/secret_name}}"
            )
        
        scope_name = match.group(1)
        secret_name = match.group(2)
        
        # Get scope by name
        scope = self.get_scope_by_name(scope_name)
        
        if not scope:
            raise ScopeNotFoundError(f"Scope '{scope_name}' not found")
        
        # Get secret value
        return self.get_secret_value(secret_name, scope.id, user_id).value
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _scope_to_response(self, scope) -> SecretScopeResponse:
        """
        Convert a SecretScope ORM object to a SecretScopeResponse dataclass.
        
        :param scope: The SecretScope ORM object
        :returns: SecretScopeResponse dataclass
        """
        from ccai.pychestrate.core.orm import User, Secret
        
        # Get username if created_by_id is set
        created_by = None
        if scope.created_by_id:
            user = self._db_session.query(User).filter(
                User.id == scope.created_by_id
            ).first()
            if user:
                created_by = user.login
        
        # Count non-deleted secrets in scope
        secret_count = self._db_session.query(Secret).filter(
            Secret.scope_id == scope.id,
            Secret.is_deleted == False
        ).count()
        
        return SecretScopeResponse(
            id=scope.id,
            name=scope.name,
            description=scope.description or "",
            is_system=scope.is_system,
            secret_count=secret_count,
            created_at=scope.created_at,
            created_by=created_by
        )
    
    def _secret_to_metadata_response(self, secret) -> SecretMetadataResponse:
        """
        Convert a Secret ORM object to a SecretMetadataResponse dataclass.
        
        Note: This method NEVER includes the actual secret value.
        
        :param secret: The Secret ORM object
        :returns: SecretMetadataResponse dataclass
        
        Validates: Requirements 11.9
        """
        from ccai.pychestrate.core.orm import User, SecretScope
        
        # Get username if updated_by_id is set
        updated_by = None
        if secret.updated_by_id:
            user = self._db_session.query(User).filter(
                User.id == secret.updated_by_id
            ).first()
            if user:
                updated_by = user.login
        
        # Get scope name
        scope = self._db_session.query(SecretScope).filter(
            SecretScope.id == secret.scope_id
        ).first()
        scope_name = scope.name if scope else ""
        
        return SecretMetadataResponse(
            id=secret.id,
            name=secret.name,
            secret_type=SecretType(secret.secret_type),
            scope_id=secret.scope_id,
            scope_name=scope_name,
            description=secret.description or "",
            version=secret.version,
            is_deleted=secret.is_deleted,
            created_at=secret.created_at,
            updated_at=secret.updated_at,
            updated_by=updated_by
        )
