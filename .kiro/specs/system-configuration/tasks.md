# Implementation Plan: System Configuration

## Overview

This implementation plan breaks down the System Configuration module into discrete coding tasks. The implementation follows the existing Flask/Flask-RestX patterns in the Pychestrate codebase, using SQLAlchemy for persistence and the testbase framework for testing.

## Existing Implementation Notes

The following components already exist and should be leveraged:

### Local Repository Code
- **User model** (`source/packages/automojo/pychestrate/core/orm.py`): OAuth-based User model with provider, status, roles (as comma-separated string), authtype fields
- **Database connection factory** (`source/packages/automojo/pychestrate/core/dbconnection.py`): PostgreSQL connection via socket or TCP
- **Database IO helpers** (`source/packages/automojo/pychestrate/core/dbio.py`): Database creation, opening, reset functions
- **CSRF token handling** (`source/site/automojo/pychestrate/webservice/security.py`): `csrf_token_generate()` and `csrf_token_validate()` functions
- **Password reset email** (`source/site/automojo/pychestrate/webservice/security.py`): `send_password_reset_email()` function
- **Site metadata** (`source/site/automojo/pychestrate/webservice/metadata.py`): `SITE_SHARED_GLOBALS` with database engine, session factory, SMTP config
- **REST API structure** (`source/site/automojo/pychestrate/webservice/restapi/`): Flask-RestX v1 API with namespace pattern
- **Web interface structure** (`source/site/automojo/pychestrate/webservice/webinterface/`): Blueprint pattern with Vue.js/Bootstrap templates

### Base Framework (`automojo-webservice-flask` package)
The `automojo.webservice.xflask` module provides extensive base infrastructure that should be extended:

- **ORM Models** (`baseorm.py`): User, Credential, CredentialResetToken, Organization, Membership, Role, UserGroup, OAuthToken
- **Security** (`basesecurity.py`): RouteSecurityManager, get_csrf_token(), validate_csrf_token()
- **Authentication** (`baseauthentication.py`): check_authentication_with_roles(), OauthProviderNames
- **Endpoints** (`baseendpoints.py`): OAuth/password login, logout, registration, password reset endpoints
- **Operations** (`baseoperations.py`): User CRUD, credential management, OAuth token management, password reset
- **Blueprint** (`securityblueprint.py`): SecurityBlueprint with @public_route() and @secure_route() decorators
- **State** (`basestate.py`): BASE_SITE_SERVICE_STATE, initialize_service_state(), establish_session()

### What Needs to Be Added
The base framework provides user authentication but lacks:
1. **Permission model** - Fine-grained permissions (the base Role is organization-scoped, not permission-based)
2. **Session tracking** - Database-backed session management with metadata
3. **Password history** - Tracking previous passwords to prevent reuse
4. **Global variables** - System-wide configuration storage
5. **Secrets management** - Encrypted credential storage with scopes
6. **Audit logging** - Security event tracking

## Tasks

- [x] 1. Set up project structure and core models
  - [x] 1.1 Create ORM models for Permission and association tables
    - Add Permission model with id, name, description fields to `source/packages/automojo/pychestrate/core/orm.py`
    - Add SystemRole model (extends base Role with is_system flag and permission associations)
    - Define role_permissions association table
    - Note: Base User, Credential, Role models exist in `automojo.webservice.xflask.baseorm`
    - _Requirements: 1.1, 4.1_
  - [x] 1.2 Create ORM models for Session, PasswordHistory
    - Add Session model with token, user_id, created_at, expires_at, last_activity, client_ip, user_agent, csrf_token
    - Add PasswordHistory model for tracking last 5 passwords
    - Note: CredentialResetToken already exists in base framework
    - _Requirements: 2.1, 3.4, 5.1_
  - [x] 1.3 Create ORM models for GlobalVariable and GlobalVariableHistory
    - Add GlobalVariable model with name, value_json, var_type, description
    - Add GlobalVariableHistory model for audit trail
    - _Requirements: 7.1, 7.6_
  - [x] 1.4 Create ORM models for SecretScope, Secret, SecretVersion
    - Add SecretScope model with name, description, is_system
    - Add Secret model with encrypted_value (LargeBinary), scope relationship
    - Add SecretVersion model for version tracking
    - Add scope_permissions association table for role-based access
    - _Requirements: 11.1, 11.6, 12.1_
  - [x] 1.5 Create ORM model for AuditLog
    - Add AuditLog model with event_type, timestamp, user info, details_json
    - _Requirements: 8.1, 8.2, 8.3_
  - [x] 1.6 Create database migration script
    - Create Alembic migration for new tables (Permission, Session, GlobalVariable, Secret, AuditLog, etc.)
    - Include default roles (Administrator, Operator, Viewer) with is_system=True
    - Include default permissions for each role
    - Include default system scope for secrets
    - _Requirements: 4.5, 12.3_

- [-] 2. Implement User Manager
  - [x] 2.1 Create UserManager class with validation methods
    - Create `source/packages/automojo/pychestrate/core/managers/user_manager.py`
    - Extend base framework's user operations from `automojo.webservice.xflask.baseoperations`
    - Implement username validation (alphanumeric, underscore, hyphen only)
    - Implement email validation (leverage `automojo.webservice.xflask.basevalidation`)
    - Create dataclasses for requests/responses
    - _Requirements: 1.6, 1.7_
  - [x] 2.2 Write property test for username validation
    - **Property 2: Username Validation**
    - **Validates: Requirements 1.6**
  - [x] 2.3 Write property test for email validation
    - **Property 3: Email Validation**
    - **Validates: Requirements 1.7**
  - [x] 2.4 Implement user CRUD operations
    - Implement create_user with duplicate check
    - Implement get_user, get_user_by_username
    - Implement update_user
    - Implement list_users with pagination
    - _Requirements: 1.1, 1.2, 1.3, 1.5_
  - [x] 2.5 Write property test for user creation uniqueness
    - **Property 1: User Creation Uniqueness**
    - **Validates: Requirements 1.1, 1.2**
  - [x] 2.6 Implement user deactivation with session invalidation
    - Implement deactivate_user
    - Invalidate all sessions for deactivated user
    - _Requirements: 1.4_
  - [x] 2.7 Write property test for deactivation session invalidation
    - **Property 4: User Deactivation Session Invalidation**
    - **Validates: Requirements 1.4**
  - [x] 2.8 Implement role assignment and permission calculation
    - Implement assign_role, remove_role
    - Implement get_effective_permissions
    - _Requirements: 4.2, 4.3_
  - [x] 2.9 Write property test for role permission propagation
    - **Property 13: Role Permission Propagation**
    - **Validates: Requirements 4.2, 4.3**

- [x] 3. Checkpoint - User Manager complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement Security Manager - Authentication
  - [x] 4.1 Create SecurityManager class with password utilities
    - Create `source/packages/automojo/pychestrate/core/managers/security_manager.py`
    - Leverage werkzeug's `generate_password_hash()` and `check_password_hash()` (already used in base framework)
    - Implement validate_password_strength (12+ chars, uppercase, lowercase, digit, special)
    - Leverage existing CSRF functions from `automojo.webservice.xflask.basesecurity`
    - _Requirements: 3.1, 3.2, 3.3_
  - [x] 4.2 Write property test for password strength validation
    - **Property 9: Password Strength Validation**
    - **Validates: Requirements 3.1, 3.2**
  - [x] 4.3 Write property test for password hash storage
    - **Property 10: Password Hash Storage**
    - **Validates: Requirements 3.3**
  - [x] 4.4 Implement authentication flow
    - Implement authenticate method
    - Create session on successful auth
    - Return generic error on failure (no info leakage)
    - _Requirements: 2.1, 2.2_
  - [x] 4.5 Write property test for authentication correctness
    - **Property 5: Authentication Correctness**
    - **Validates: Requirements 2.1, 2.2**
  - [x] 4.6 Implement password history enforcement
    - Track last 5 password hashes
    - Reject reused passwords
    - _Requirements: 3.4_
  - [x] 4.7 Write property test for password history enforcement
    - **Property 11: Password History Enforcement**
    - **Validates: Requirements 3.4**

- [ ] 5. Implement Security Manager - Sessions
  - [x] 5.1 Implement session management
    - Implement validate_token
    - Implement logout (single session)
    - Implement logout_all (all user sessions)
    - Track session metadata (IP, user agent, timestamps)
    - _Requirements: 2.3, 5.1_
  - [x] 5.2 Write property test for session logout invalidation
    - **Property 6: Session Logout Invalidation**
    - **Validates: Requirements 2.3**
  - [x] 5.3 Write property test for session data completeness
    - **Property 16: Session Data Completeness**
    - **Validates: Requirements 5.1**
  - [x] 5.4 Implement session expiry and inactivity timeout
    - Check expiry on token validation
    - Implement cleanup_expired_sessions
    - _Requirements: 2.4, 5.2_
  - [x] 5.5 Write property test for session expiry enforcement
    - **Property 7: Session Expiry Enforcement**
    - **Validates: Requirements 2.4**
  - [x] 5.6 Write property test for session inactivity expiration
    - **Property 17: Session Inactivity Expiration**
    - **Validates: Requirements 5.2**
  - [x] 5.7 Implement concurrent session limit
    - Enforce configurable max sessions per user
    - _Requirements: 5.5_
  - [x] 5.8 Write property test for concurrent session limit
    - **Property 18: Concurrent Session Limit**
    - **Validates: Requirements 5.5**
  - [x] 5.9 Implement password change session invalidation
    - Invalidate other sessions on password change
    - _Requirements: 3.5_
  - [x] 5.10 Write property test for password change session invalidation
    - **Property 12: Password Change Session Invalidation**
    - **Validates: Requirements 3.5**

- [x] 6. Implement Security Manager - Password Reset and CSRF
  - [x] 6.1 Implement password reset flow
    - Extend base framework's `create_credential_reset_token()` and `validate_reset_token_for_user()`
    - Implement reset_password (validate token, update password, check history)
    - Handle expired tokens
    - Leverage existing `send_password_reset_email()` from base framework
    - _Requirements: 2.5, 2.6, 2.7_
  - [x] 6.2 Write property test for password reset token lifecycle
    - **Property 8: Password Reset Token Lifecycle**
    - **Validates: Requirements 2.5, 2.6, 2.7**
  - [x] 6.3 Leverage existing CSRF token management
    - Use `get_csrf_token()` and `validate_csrf_token()` from `automojo.webservice.xflask.basesecurity`
    - These are already session-based and use `secrets.token_urlsafe(32)`
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 6.4 Write property test for CSRF token uniqueness
    - **Property 19: CSRF Token Uniqueness**
    - **Validates: Requirements 6.1**
  - [x] 6.5 Write property test for CSRF token validation
    - **Property 20: CSRF Token Validation**
    - **Validates: Requirements 6.2, 6.3**
  - [x] 6.6 Implement permission checking
    - Implement check_permission
    - _Requirements: 4.4_
  - [x] 6.7 Write property test for permission check enforcement
    - **Property 14: Permission Check Enforcement**
    - **Validates: Requirements 4.4**

- [x] 7. Checkpoint - Security Manager complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement Global Variable Store
  - [x] 8.1 Create GlobalVariableStore class with type handling
    - Create `source/packages/automojo/pychestrate/core/managers/global_variable_store.py`
    - Implement validate_value for each type (string, integer, float, boolean, json)
    - Implement serialize_value (to JSON)
    - Implement deserialize_value (from JSON)
    - _Requirements: 7.5, 7.7, 7.8_
  - [x] 8.2 Write property test for global variable serialization round-trip
    - **Property 22: Global Variable Serialization Round-Trip**
    - **Validates: Requirements 7.7, 7.8**
  - [x] 8.3 Implement variable CRUD operations
    - Implement create_variable with type validation
    - Implement get_variable, get_value (with default)
    - Implement update_variable with type validation
    - Implement delete_variable
    - Implement list_variables with pagination
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x] 8.4 Write property test for global variable type validation
    - **Property 21: Global Variable Type Validation**
    - **Validates: Requirements 7.2, 7.5**
  - [x] 8.5 Write property test for global variable default fallback
    - **Property 23: Global Variable Default Fallback**
    - **Validates: Requirements 7.4**
  - [x] 8.6 Implement variable change history
    - Log changes to GlobalVariableHistory
    - Implement get_change_history
    - _Requirements: 7.6_

- [x] 9. Implement Secret Manager
  - [x] 9.1 Create SecretManager class with encryption utilities
    - Create `source/packages/automojo/pychestrate/core/managers/secret_manager.py`
    - Implement AES-256-GCM encryption using cryptography library
    - Implement _encrypt_value, _decrypt_value
    - _Requirements: 11.1, 11.2_
  - [x] 9.2 Write property test for secret encryption round-trip
    - **Property 29: Secret Encryption Round-Trip**
    - **Validates: Requirements 11.1, 11.2**
  - [x] 9.3 Implement scope management
    - Implement create_scope, get_scope, list_scopes, delete_scope
    - Implement grant_scope_permission, revoke_scope_permission
    - _Requirements: 12.1, 12.2, 12.4_
  - [x] 9.4 Write property test for scope deletion constraint ✅ PASSED (5/5 tests)
    - **Property 33: Scope Deletion Constraint**
    - **Validates: Requirements 12.4**
  - [x] 9.5 Implement secret CRUD operations
    - Implement create_secret (encrypt before storage)
    - Implement get_secret_metadata (no value)
    - Implement get_secret_value (decrypt, check permission)
    - Implement update_secret (version increment)
    - Implement delete_secret (soft delete)
    - Implement list_secrets (filtered by permission)
    - _Requirements: 11.1, 11.4, 11.5, 11.7, 11.8, 11.9_
  - [x] 9.6 Write property test for secret value masking ✅ PASSED (4/4 tests)
    - **Property 30: Secret Value Masking**
    - **Validates: Requirements 11.9**
  - [x] 9.7 Write property test for secret scope access control ✅ PASSED (5/5 tests)
    - **Property 31: Secret Scope Access Control**
    - **Validates: Requirements 11.7, 12.2**
  - [x] 9.8 Write property test for secret listing permission filter ✅ PASSED (5/5 tests)
    - **Property 34: Secret Listing Permission Filter**
    - **Validates: Requirements 12.5**
  - [x] 9.9 Implement secret reference resolution
    - Implement resolve_secret_reference for ${scope/name} format
    - _Requirements: 11.10_
  - [x] 9.10 Write property test for secret reference resolution ✅ PASSED (6/6 tests)
    - **Property 32: Secret Reference Resolution**
    - **Validates: Requirements 11.10**

- [x] 10. Checkpoint - Secret Manager complete
  - All 37 tests pass

- [x] 11. Implement Audit Logger
  - [x] 11.1 Create AuditLogger class
    - Create `source/packages/automojo/pychestrate/core/managers/audit_logger.py`
    - Implement log_event for all event types
    - Implement query_logs with filtering and pagination
    - Implement cleanup_old_logs
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  - [x] 11.2 Write property test for audit log completeness
    - **Property 24: Audit Log Completeness**
    - **Validates: Requirements 8.1, 8.2, 8.3**
  - [x] 11.3 Write property test for audit log retention
    - **Property 25: Audit Log Retention**
    - **Validates: Requirements 8.4**
  - [x] 11.4 Integrate audit logging into managers
    - Add audit calls to UserManager operations
    - Add audit calls to SecurityManager operations
    - Add audit calls to GlobalVariableStore operations
    - Add audit calls to SecretManager operations
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 12. Implement REST API endpoints
  - [x] 12.1 Create REST API namespace and base configuration
    - Create `source/site/automojo/pychestrate/webservice/restapi/versions/v1/config/` directory
    - Set up Flask-RestX namespace for /api/v1/config following existing pattern in `restapi/versions/v1/__init__.py`
    - Implement authentication decorator using bearer token validation
    - _Requirements: 9.1, 9.2_
  - [x] 12.2 Write property test for API authentication enforcement
    - **Property 26: API Authentication Enforcement**
    - **Validates: Requirements 9.2**
  - [x] 12.3 Implement error handling middleware
    - Create consistent error response format
    - Map exceptions to HTTP status codes
    - _Requirements: 9.3, 9.6_
  - [x] 12.4 Write property test for API error format consistency ✅ PASSED (8/8 tests)
    - **Property 27: API Error Format Consistency**
    - **Validates: Requirements 9.3**
  - [x] 12.5 Implement user management endpoints
    - POST /users - create user
    - GET /users - list users
    - GET /users/{id} - get user
    - PUT /users/{id} - update user
    - DELETE /users/{id} - deactivate user
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 9.4, 9.5_
  - [x] 12.6 Write property test for API pagination correctness ✅ PASSED (12/12 tests)
    - **Property 28: API Pagination Correctness**
    - **Validates: Requirements 9.4**
  - [x] 12.7 Implement authentication endpoints
    - POST /auth/login - authenticate
    - POST /auth/logout - logout
    - POST /auth/password-reset - request reset
    - POST /auth/password-reset/confirm - complete reset
    - _Requirements: 2.1, 2.3, 2.5, 2.6_
  - [x] 12.8 Implement role management endpoints
    - POST /roles - create role
    - GET /roles - list roles
    - PUT /roles/{id} - update role
    - POST /users/{id}/roles - assign role
    - DELETE /users/{id}/roles/{role_id} - remove role
    - _Requirements: 4.1, 4.2, 4.3_
  - [x] 12.9 Implement session management endpoints
    - GET /sessions - list active sessions
    - DELETE /sessions/{id} - terminate session
    - _Requirements: 5.3, 5.4_
  - [x] 12.10 Implement global variable endpoints
    - POST /variables - create variable
    - GET /variables - list variables
    - GET /variables/{name} - get variable
    - PUT /variables/{name} - update variable
    - DELETE /variables/{name} - delete variable
    - GET /variables/{name}/history - get change history
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x] 12.11 Implement secret management endpoints
    - POST /scopes - create scope
    - GET /scopes - list scopes
    - DELETE /scopes/{id} - delete scope
    - POST /secrets - create secret
    - GET /secrets - list secrets (metadata only)
    - GET /secrets/{scope}/{name} - get secret value
    - PUT /secrets/{scope}/{name} - update secret
    - DELETE /secrets/{scope}/{name} - delete secret
    - _Requirements: 11.1, 11.7, 11.9, 12.1, 12.4_
  - [x] 12.12 Implement audit log endpoints
    - GET /audit-logs - query audit logs
    - _Requirements: 8.5_

- [x] 13. Checkpoint - REST API complete
  - All 262 tests pass (28 REST API tests + 234 other tests)

- [x] 14. Implement Web Interface
  - [x] 14.1 Create web interface blueprints structure
    - Create `source/site/automojo/pychestrate/webservice/webinterface/blueprints/config/` directory
    - Use `SecurityBlueprint` from `automojo.webservice.xflask.securityblueprint` for route security integration
    - Use Vue.js/Bootstrap pattern from existing `home.html` template
    - _Requirements: 10.1_
  - [x] 14.2 Leverage existing authentication pages from base framework
    - Base framework provides login, logout, registration, password reset endpoints
    - Customize templates if needed for Pychestrate branding
    - Implement postback handlers using `@public_route()` decorator
    - _Requirements: 10.2, 10.5_
  - [x] 14.3 Implement user management pages
    - Create user list page using `@secure_route(roles=['admin'])`
    - Create user detail/edit page
    - Create user create page
    - Implement postback handlers
    - _Requirements: 10.1, 10.2, 10.4_
  - [x] 14.4 Implement role management pages
    - Create role list page using `@secure_route(roles=['admin'])`
    - Create role detail/edit page
    - Implement postback handlers
    - _Requirements: 10.1, 10.2, 10.4_
  - [x] 14.5 Implement global variable management pages
    - Create variable list page
    - Create variable detail/edit page
    - Create variable history page
    - Implement postback handlers
    - _Requirements: 10.1, 10.2, 10.4_
  - [x] 14.6 Implement secret management pages
    - Create scope list page
    - Create secret list page (metadata only)
    - Create secret create/edit page
    - Implement postback handlers
    - _Requirements: 10.1, 10.2, 10.4_
  - [x] 14.7 Implement session management pages
    - Create active sessions list page
    - Implement session termination postback
    - _Requirements: 10.1, 10.2, 10.4_
  - [x] 14.8 Implement audit log viewer page
    - Create audit log list page with filtering
    - _Requirements: 10.1, 10.4_
  - [x] 14.9 Leverage existing authentication middleware from base framework
    - Use `check_authentication_with_roles()` from `automojo.webservice.xflask.baseauthentication`
    - Use `RouteSecurityManager` for endpoint protection
    - Redirect to login handled automatically by base framework
    - _Requirements: 10.4, 10.5_
  - [x] 14.10 Implement error display
    - Create error message templates
    - Integrate error display into all pages
    - _Requirements: 10.3_

- [x] 15. Final checkpoint - All components complete
  - Ensure all tests pass, ask the user if questions arise.
  - Verify all requirements are covered
  - Run full test suite including property tests

## Notes

- All tasks are required for comprehensive correctness guarantees
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- All database operations go through the dbio pattern per project conventions
- Web interface uses postback URLs for data modifications per project conventions
