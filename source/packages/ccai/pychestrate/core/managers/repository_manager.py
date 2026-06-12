"""
.. module:: repository_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the RepositoryManager class for repository CRUD operations and connectivity

.. moduleauthor:: Code Craft AI LLC

This module provides the RepositoryManager class which handles:
- Repository CRUD operations (Requirements 3.1, 3.2, 3.6, 3.7)
- Repository connectivity testing (Requirements 3.3, 3.4)
- Branch listing and commit information retrieval
- Support for HTTPS and SSH authentication
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import subprocess
import tempfile
import os
import re

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now


# =============================================================================
# Enums
# =============================================================================

class RepositoryAuthType(str, Enum):
    """
        Enum-like class to represent the authentication types for repositories.
    """
    HTTPS_TOKEN = 'https_token'
    SSH_KEY = 'ssh_key'
    NONE = 'none'


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class RepositoryCreateRequest:
    """Request dataclass for creating a new repository."""
    name: str
    url: str
    auth_type: RepositoryAuthType
    credential_secret_ref: Optional[str] = None
    default_branch: str = "main"
    description: str = ""


@dataclass
class RepositoryUpdateRequest:
    """Request dataclass for updating an existing repository."""
    name: Optional[str] = None
    credential_secret_ref: Optional[str] = None
    default_branch: Optional[str] = None
    description: Optional[str] = None


@dataclass
class RepositoryResponse:
    """Response dataclass for repository data."""
    id: int
    project_id: int
    name: str
    url: str
    auth_type: RepositoryAuthType
    default_branch: str
    description: str
    last_commit_sha: Optional[str]
    last_commit_message: Optional[str]
    last_commit_author: Optional[str]
    last_commit_time: Optional[datetime]
    last_fetch_time: Optional[datetime]
    created_at: datetime


@dataclass
class RepositoryListResponse:
    """Response dataclass for paginated repository list."""
    repositories: List[RepositoryResponse]
    total: int
    offset: int
    limit: int


@dataclass
class BranchResponse:
    """Response dataclass for branch data."""
    name: str
    commit_sha: str
    commit_message: str
    commit_author: str
    commit_time: datetime


# =============================================================================
# Exceptions
# =============================================================================

class RepositoryValidationError(Exception):
    """Exception raised when repository validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = None):
        self.message = message
        self.field = field
        self.error_code = error_code or "VALIDATION_ERROR"
        super().__init__(self.message)


class RepositoryNotFoundError(Exception):
    """Exception raised when a repository is not found."""
    
    def __init__(self, message: str, error_code: str = "REPOSITORY_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateRepositoryError(Exception):
    """Exception raised when attempting to create a repository with duplicate name."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "REPOSITORY_NAME_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class ProjectNotFoundError(Exception):
    """Exception raised when a project is not found."""
    
    def __init__(self, message: str, error_code: str = "PROJECT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class RepositoryConnectivityError(Exception):
    """Exception raised when repository connectivity test fails."""
    
    def __init__(self, message: str, error_code: str = "CONNECTIVITY_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class RepositoryHasReferencesError(Exception):
    """Exception raised when attempting to delete a repository with references."""
    
    def __init__(self, message: str, error_code: str = "REPOSITORY_HAS_REFERENCES"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


# =============================================================================
# Validation Constants
# =============================================================================

# Repository name validation: alphanumeric, underscore, hyphen, period
# Must start with alphanumeric, 1-128 characters
REPOSITORY_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}\Z')

# Git URL patterns
GIT_HTTPS_PATTERN = re.compile(r'^https?://[^\s]+\.git$|^https?://[^\s]+$')
GIT_SSH_PATTERN = re.compile(r'^git@[^\s:]+:[^\s]+\.git$|^ssh://[^\s]+$')


# =============================================================================
# Validation Functions
# =============================================================================

def validate_repository_name(name: str) -> bool:
    """
    Validate that a repository name contains only alphanumeric characters, underscores, hyphens, and periods.
    
    :param name: The repository name to validate
    :returns: True if valid, False otherwise
    """
    if not name:
        return False
    
    if not REPOSITORY_NAME_PATTERN.match(name):
        return False
    
    return True


def validate_repository_url(url: str, auth_type: RepositoryAuthType) -> bool:
    """
    Validate that a repository URL is valid for the given authentication type.
    
    :param url: The repository URL to validate
    :param auth_type: The authentication type
    :returns: True if valid, False otherwise
    """
    if not url:
        return False
    
    if auth_type == RepositoryAuthType.SSH_KEY:
        return bool(GIT_SSH_PATTERN.match(url))
    else:
        # HTTPS_TOKEN or NONE
        return bool(GIT_HTTPS_PATTERN.match(url)) or bool(GIT_SSH_PATTERN.match(url))




# =============================================================================
# RepositoryManager Class
# =============================================================================

class RepositoryManager:
    """
    Manager class for repository CRUD operations and connectivity.
    
    This class handles all repository-related operations including:
    - Repository creation with validation
    - Repository retrieval by ID
    - Repository updates
    - Repository deletion with reference check
    - Repository connectivity testing
    - Branch listing and commit information retrieval
    
    Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
    """
    
    def __init__(self, db_session: DbSession, audit_logger=None, secret_manager=None):
        """
        Initialize the RepositoryManager with a database session.
        
        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        :param secret_manager: Optional SecretManager instance for credential resolution
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
        self._secret_manager = secret_manager
    
    # =========================================================================
    # Validation Methods
    # =========================================================================
    
    def _validate_repository_create_request(self, request: RepositoryCreateRequest) -> None:
        """
        Validate a repository creation request.
        
        :param request: The repository creation request to validate
        :raises RepositoryValidationError: If validation fails
        """
        if not validate_repository_name(request.name):
            raise RepositoryValidationError(
                "Repository name must be 1-128 characters, start with alphanumeric, "
                "and contain only alphanumeric characters, underscores, hyphens, and periods",
                field="name",
                error_code="INVALID_REPOSITORY_NAME"
            )
        
        if not request.url:
            raise RepositoryValidationError(
                "Repository URL is required",
                field="url",
                error_code="MISSING_URL"
            )
        
        # Validate auth_type is a valid enum value
        if not isinstance(request.auth_type, RepositoryAuthType):
            try:
                request.auth_type = RepositoryAuthType(request.auth_type)
            except ValueError:
                raise RepositoryValidationError(
                    f"Invalid authentication type: {request.auth_type}. "
                    f"Must be one of: {', '.join([e.value for e in RepositoryAuthType])}",
                    field="auth_type",
                    error_code="INVALID_AUTH_TYPE"
                )
        
        # Validate credential_secret_ref is provided for authenticated types
        if request.auth_type != RepositoryAuthType.NONE and not request.credential_secret_ref:
            raise RepositoryValidationError(
                f"Credential secret reference is required for authentication type '{request.auth_type.value}'",
                field="credential_secret_ref",
                error_code="MISSING_CREDENTIAL_REF"
            )
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _repository_to_response(self, repository) -> RepositoryResponse:
        """
        Convert a ProjectRepository ORM object to a RepositoryResponse.
        
        :param repository: The ProjectRepository ORM object
        :returns: RepositoryResponse dataclass
        """
        return RepositoryResponse(
            id=repository.id,
            project_id=repository.project_id,
            name=repository.name,
            url=repository.url,
            auth_type=RepositoryAuthType(repository.auth_type),
            default_branch=repository.default_branch,
            description=repository.description or "",
            last_commit_sha=repository.last_commit_sha,
            last_commit_message=repository.last_commit_message,
            last_commit_author=repository.last_commit_author,
            last_commit_time=repository.last_commit_time,
            last_fetch_time=repository.last_fetch_time,
            created_at=repository.created_at
        )
    
    # =========================================================================
    # Repository CRUD Operations
    # =========================================================================
    
    def add_repository(
        self,
        project_id: int,
        request: RepositoryCreateRequest,
        user_id: str
    ) -> RepositoryResponse:
        """
        Add a repository to a project.
        
        :param project_id: The project's unique identifier
        :param request: The repository creation request containing repository data
        :param user_id: The ID of the user adding the repository
        :returns: RepositoryResponse with the created repository data
        :raises ProjectNotFoundError: If project is not found
        :raises RepositoryValidationError: If validation fails
        :raises DuplicateRepositoryError: If repository name already exists in project
        
        Validates: Requirements 3.1, 3.5
        """
        from ccai.pychestrate.core.orm import Project, ProjectRepository
        
        # Validate the request
        self._validate_repository_create_request(request)
        
        # Verify project exists
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Check for duplicate name within project
        existing_repo = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.project_id == project_id,
            ProjectRepository.name == request.name
        ).first()
        
        if existing_repo:
            raise DuplicateRepositoryError(
                f"Repository with name '{request.name}' already exists in project '{project.name}'",
                field="name"
            )
        
        # Create the repository
        now = utc_now()
        
        repository = ProjectRepository(
            project_id=project_id,
            name=request.name,
            url=request.url,
            auth_type=request.auth_type.value,
            credential_secret_ref=request.credential_secret_ref,
            default_branch=request.default_branch,
            description=request.description or "",
            created_at=now
        )
        
        self._db_session.add(repository)
        self._db_session.commit()
        
        # Log the repository creation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='repository_added',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "repository_id": repository.id,
                    "repository_name": repository.name,
                    "repository_url": repository.url
                }
            )
        
        return self._repository_to_response(repository)
    
    def get_repository(self, repository_id: int) -> Optional[RepositoryResponse]:
        """
        Get repository by ID.
        
        :param repository_id: The repository's unique identifier
        :returns: RepositoryResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import ProjectRepository
        
        repository = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.id == repository_id
        ).first()
        
        if not repository:
            return None
        
        return self._repository_to_response(repository)
    
    def update_repository(
        self,
        repository_id: int,
        request: RepositoryUpdateRequest,
        user_id: str
    ) -> RepositoryResponse:
        """
        Update repository configuration.
        
        :param repository_id: The repository's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: RepositoryResponse with the updated repository data
        :raises RepositoryNotFoundError: If repository is not found
        :raises RepositoryValidationError: If validation fails
        :raises DuplicateRepositoryError: If new name already exists in project
        """
        from ccai.pychestrate.core.orm import ProjectRepository
        
        repository = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.id == repository_id
        ).first()
        
        if not repository:
            raise RepositoryNotFoundError(f"Repository with ID '{repository_id}' not found")
        
        # Update name if provided
        if request.name is not None:
            if not validate_repository_name(request.name):
                raise RepositoryValidationError(
                    "Repository name must be 1-128 characters, start with alphanumeric, "
                    "and contain only alphanumeric characters, underscores, hyphens, and periods",
                    field="name",
                    error_code="INVALID_REPOSITORY_NAME"
                )
            
            # Check for duplicate name (excluding current repository)
            existing_repo = self._db_session.query(ProjectRepository).filter(
                ProjectRepository.project_id == repository.project_id,
                ProjectRepository.name == request.name,
                ProjectRepository.id != repository_id
            ).first()
            
            if existing_repo:
                raise DuplicateRepositoryError(
                    f"Repository with name '{request.name}' already exists in this project",
                    field="name"
                )
            
            repository.name = request.name
        
        # Update credential_secret_ref if provided
        if request.credential_secret_ref is not None:
            repository.credential_secret_ref = request.credential_secret_ref
        
        # Update default_branch if provided
        if request.default_branch is not None:
            repository.default_branch = request.default_branch
        
        # Update description if provided
        if request.description is not None:
            repository.description = request.description
        
        self._db_session.commit()
        
        # Log the repository update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='repository_updated',
                user_id=str(user_id),
                details={
                    "repository_id": repository.id,
                    "repository_name": repository.name,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._repository_to_response(repository)
    
    def remove_repository(self, repository_id: int, user_id: str) -> None:
        """
        Remove repository from project.
        
        This also disables related watches as per Requirements 3.2.
        
        :param repository_id: The repository's unique identifier
        :param user_id: The ID of the user removing the repository
        :raises RepositoryNotFoundError: If repository is not found
        :raises RepositoryHasReferencesError: If repository has active build specs
        
        Validates: Requirements 3.2
        """
        from ccai.pychestrate.core.orm import ProjectRepository, ProjectBuildSpec, ProjectWatch
        
        repository = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.id == repository_id
        ).first()
        
        if not repository:
            raise RepositoryNotFoundError(f"Repository with ID '{repository_id}' not found")
        
        # Check for build specs referencing this repository
        build_spec_count = self._db_session.query(ProjectBuildSpec).filter(
            ProjectBuildSpec.repository_id == repository_id
        ).count()
        
        if build_spec_count > 0:
            raise RepositoryHasReferencesError(
                f"Cannot remove repository '{repository.name}' with {build_spec_count} build specification(s) referencing it"
            )
        
        repository_name = repository.name
        project_id = repository.project_id
        
        # Disable related watches (Requirements 3.2)
        watches = self._db_session.query(ProjectWatch).filter(
            ProjectWatch.repository_id == repository_id
        ).all()
        
        for watch in watches:
            watch.is_enabled = False
        
        # Delete the repository
        self._db_session.delete(repository)
        self._db_session.commit()
        
        # Log the repository removal event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='repository_removed',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "repository_id": repository_id,
                    "repository_name": repository_name,
                    "watches_disabled": len(watches)
                }
            )
    
    def list_repositories(
        self,
        project_id: int,
        offset: int = 0,
        limit: int = 50
    ) -> RepositoryListResponse:
        """
        List repositories in a project.
        
        :param project_id: The project's unique identifier
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: RepositoryListResponse with paginated repository list
        
        Validates: Requirements 3.6
        """
        from ccai.pychestrate.core.orm import ProjectRepository
        
        query = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.project_id == project_id
        )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        repositories = query.order_by(ProjectRepository.name).offset(offset).limit(limit).all()
        
        return RepositoryListResponse(
            repositories=[self._repository_to_response(repo) for repo in repositories],
            total=total,
            offset=offset,
            limit=limit
        )


    # =========================================================================
    # Repository Connectivity Operations
    # =========================================================================
    
    def _get_credential_for_repository(self, repository) -> Optional[str]:
        """
        Get the credential value for a repository from the secret manager.
        
        :param repository: The ProjectRepository ORM object
        :returns: The credential value or None if not available
        """
        if not repository.credential_secret_ref or not self._secret_manager:
            return None
        
        try:
            # Parse the secret reference (format: scope/secret_name)
            parts = repository.credential_secret_ref.split('/')
            if len(parts) == 2:
                scope_name, secret_name = parts
                secret_response = self._secret_manager.get_secret_value(
                    scope_name=scope_name,
                    secret_name=secret_name
                )
                if secret_response:
                    return secret_response.value
        except Exception:
            # If we can't get the credential, return None
            pass
        
        return None
    
    def _build_git_env(self, repository, credential: Optional[str] = None) -> Dict[str, str]:
        """
        Build environment variables for git commands.
        
        :param repository: The ProjectRepository ORM object
        :param credential: Optional credential value
        :returns: Dictionary of environment variables
        """
        env = os.environ.copy()
        
        # Disable interactive prompts
        env['GIT_TERMINAL_PROMPT'] = '0'
        env['GIT_SSH_COMMAND'] = 'ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new'
        
        if credential and repository.auth_type == RepositoryAuthType.HTTPS_TOKEN.value:
            # For HTTPS with token, we'll use the credential helper
            env['GIT_ASKPASS'] = 'echo'
            env['GIT_PASSWORD'] = credential
        
        return env
    
    def _run_git_command(
        self,
        args: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: int = 30
    ) -> subprocess.CompletedProcess:
        """
        Run a git command with the given arguments.
        
        :param args: List of git command arguments
        :param cwd: Working directory for the command
        :param env: Environment variables
        :param timeout: Timeout in seconds
        :returns: CompletedProcess result
        :raises RepositoryConnectivityError: If the command fails
        """
        cmd = ['git'] + args
        
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result
        except subprocess.TimeoutExpired:
            raise RepositoryConnectivityError(
                f"Git command timed out after {timeout} seconds"
            )
        except Exception as e:
            raise RepositoryConnectivityError(
                f"Failed to execute git command: {str(e)}"
            )
    
    def test_connectivity(self, repository_id: int) -> bool:
        """
        Test repository connectivity by performing a test fetch.
        
        :param repository_id: The repository's unique identifier
        :returns: True if connectivity test passes
        :raises RepositoryNotFoundError: If repository is not found
        :raises RepositoryConnectivityError: If connectivity test fails
        
        Validates: Requirements 3.3, 3.4
        """
        from ccai.pychestrate.core.orm import ProjectRepository
        
        repository = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.id == repository_id
        ).first()
        
        if not repository:
            raise RepositoryNotFoundError(f"Repository with ID '{repository_id}' not found")
        
        # Get credential if available
        credential = self._get_credential_for_repository(repository)
        
        # Build environment
        env = self._build_git_env(repository, credential)
        
        # Use git ls-remote to test connectivity without cloning
        result = self._run_git_command(
            ['ls-remote', '--heads', repository.url],
            env=env,
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            raise RepositoryConnectivityError(
                f"Failed to connect to repository: {error_msg}"
            )
        
        return True
    
    def fetch_latest(self, repository_id: int) -> RepositoryResponse:
        """
        Fetch latest commit information from the repository.
        
        :param repository_id: The repository's unique identifier
        :returns: RepositoryResponse with updated commit information
        :raises RepositoryNotFoundError: If repository is not found
        :raises RepositoryConnectivityError: If fetch fails
        
        Validates: Requirements 3.4
        """
        from ccai.pychestrate.core.orm import ProjectRepository
        
        repository = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.id == repository_id
        ).first()
        
        if not repository:
            raise RepositoryNotFoundError(f"Repository with ID '{repository_id}' not found")
        
        # Get credential if available
        credential = self._get_credential_for_repository(repository)
        
        # Build environment
        env = self._build_git_env(repository, credential)
        
        # Get the latest commit SHA for the default branch
        result = self._run_git_command(
            ['ls-remote', repository.url, f'refs/heads/{repository.default_branch}'],
            env=env,
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            raise RepositoryConnectivityError(
                f"Failed to fetch from repository: {error_msg}"
            )
        
        # Parse the output to get the commit SHA
        output = result.stdout.strip()
        if output:
            parts = output.split()
            if parts:
                commit_sha = parts[0]
                
                # Update the repository with the latest commit info
                now = utc_now()
                repository.last_commit_sha = commit_sha
                repository.last_fetch_time = now
                
                # Try to get more commit details using git log
                # This requires a clone, so we'll do it in a temp directory
                commit_info = self._get_commit_details(repository, commit_sha, credential)
                if commit_info:
                    repository.last_commit_message = commit_info.get('message', '')[:512]
                    repository.last_commit_author = commit_info.get('author', '')[:128]
                    if commit_info.get('time'):
                        repository.last_commit_time = commit_info['time']
                
                self._db_session.commit()
        
        return self._repository_to_response(repository)
    
    def _get_commit_details(
        self,
        repository,
        commit_sha: str,
        credential: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed commit information.
        
        This is a best-effort operation that may fail if the repository
        cannot be cloned or accessed.
        
        :param repository: The ProjectRepository ORM object
        :param commit_sha: The commit SHA to get details for
        :param credential: Optional credential value
        :returns: Dictionary with commit details or None
        """
        # For now, we'll return minimal info since full clone is expensive
        # In a production system, this would use a shallow clone or API
        return None
    
    def list_branches(self, repository_id: int) -> List[BranchResponse]:
        """
        List branches in repository.
        
        :param repository_id: The repository's unique identifier
        :returns: List of BranchResponse objects
        :raises RepositoryNotFoundError: If repository is not found
        :raises RepositoryConnectivityError: If listing fails
        
        Validates: Requirements 3.7
        """
        from ccai.pychestrate.core.orm import ProjectRepository
        
        repository = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.id == repository_id
        ).first()
        
        if not repository:
            raise RepositoryNotFoundError(f"Repository with ID '{repository_id}' not found")
        
        # Get credential if available
        credential = self._get_credential_for_repository(repository)
        
        # Build environment
        env = self._build_git_env(repository, credential)
        
        # Get all branches using ls-remote
        result = self._run_git_command(
            ['ls-remote', '--heads', repository.url],
            env=env,
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            raise RepositoryConnectivityError(
                f"Failed to list branches: {error_msg}"
            )
        
        branches = []
        now = utc_now()
        
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            
            parts = line.split('\t')
            if len(parts) >= 2:
                commit_sha = parts[0]
                ref = parts[1]
                
                # Extract branch name from ref (refs/heads/branch_name)
                if ref.startswith('refs/heads/'):
                    branch_name = ref[len('refs/heads/'):]
                    
                    branches.append(BranchResponse(
                        name=branch_name,
                        commit_sha=commit_sha,
                        commit_message="",  # Would require additional fetch
                        commit_author="",   # Would require additional fetch
                        commit_time=now     # Placeholder
                    ))
        
        return branches
    
    def get_commit_info(self, repository_id: int, ref: str) -> Dict[str, Any]:
        """
        Get commit information for a ref (branch, tag, sha).
        
        :param repository_id: The repository's unique identifier
        :param ref: The reference to get info for (branch name, tag, or SHA)
        :returns: Dictionary with commit information
        :raises RepositoryNotFoundError: If repository is not found
        :raises RepositoryConnectivityError: If fetch fails
        """
        from ccai.pychestrate.core.orm import ProjectRepository
        
        repository = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.id == repository_id
        ).first()
        
        if not repository:
            raise RepositoryNotFoundError(f"Repository with ID '{repository_id}' not found")
        
        # Get credential if available
        credential = self._get_credential_for_repository(repository)
        
        # Build environment
        env = self._build_git_env(repository, credential)
        
        # Try to resolve the ref
        # First try as a branch
        result = self._run_git_command(
            ['ls-remote', repository.url, f'refs/heads/{ref}'],
            env=env,
            timeout=30
        )
        
        commit_sha = None
        ref_type = 'branch'
        
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split()
            if parts:
                commit_sha = parts[0]
        else:
            # Try as a tag
            result = self._run_git_command(
                ['ls-remote', repository.url, f'refs/tags/{ref}'],
                env=env,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split()
                if parts:
                    commit_sha = parts[0]
                    ref_type = 'tag'
            else:
                # Assume it's a SHA and try to verify
                # For now, just return the ref as the SHA
                commit_sha = ref
                ref_type = 'sha'
        
        return {
            'ref': ref,
            'ref_type': ref_type,
            'commit_sha': commit_sha,
            'repository_id': repository_id,
            'repository_name': repository.name
        }
