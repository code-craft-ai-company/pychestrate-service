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


import base64
import logging
import subprocess
import tempfile
import os
import re
import shlex
import shutil

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Iterator, List, Optional
from urllib.parse import urlsplit

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now


_module_logger = logging.getLogger(__name__)


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
    credential_secret_ref: Optional[str] = None
    # Set by fetch_latest: what changed since the previous fetch, and
    # how many watches that fired.
    ref_changes: List[Dict[str, Any]] = field(default_factory=list)
    watches_triggered: int = 0
    # True when this fetch recorded the branches and tags for the first
    # time (nothing is reported as new then).
    refs_first_recorded: bool = False


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


class RepositoryCredentialError(Exception):
    """Exception raised when a repository's credential secret is missing or cannot be read."""

    def __init__(self, message: str, error_code: str = "REPOSITORY_CREDENTIAL_UNAVAILABLE"):
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

# Human names for the authentication types, used in messages.
_AUTH_TYPE_LABELS = {
    'https_token': 'HTTPS access token',
    'ssh_key': 'SSH private key',
    'none': 'no',
}

# GIT_ASKPASS helper for HTTPS token authentication: git runs it once for
# the username and once for the password. Both values come from the
# environment of that one git process, so the token is never written to
# disk or put on a command line.
_ASKPASS_SCRIPT = """#!/bin/sh
case "$1" in
    Username*|username*) printf '%s\\n' "$PYCHESTRATE_GIT_USERNAME" ;;
    *) printf '%s\\n' "$PYCHESTRATE_GIT_TOKEN" ;;
esac
"""

# What to tell the user when git fails, matched against its (lower-cased)
# error output. Anything else gets a generic sentence; the raw output only
# goes to the server log.
_GIT_FAILURE_MESSAGES = (
    (("could not read username", "could not read password", "terminal prompts disabled"),
     "the server asked for credentials. For a private repository, use HTTPS access "
     "token authentication with a credential secret."),
    (("authentication failed", "permission denied (publickey", "invalid username or password",
      "returned error: 401", "returned error: 403"),
     "the server refused the credentials. Check the repository's credential secret."),
    (("repository not found", "not found", "does not appear to be a git repository",
      "returned error: 404"),
     "no repository was found at this URL (or the credentials cannot see it)."),
    (("could not resolve host", "name or service not known", "nodename nor servname"),
     "the host name in the URL could not be resolved."),
    (("host key verification failed",),
     "the SSH host key could not be verified."),
    (("connection refused", "connection timed out", "timed out", "network is unreachable",
      "failed to connect", "could not connect"),
     "the server could not be reached."),
    (("ssl", "certificate"),
     "the server's TLS certificate was not accepted."),
)


def _username_from_url(*, url: str) -> Optional[str]:
    """
    The user name embedded in an HTTPS repository URL
    (``https://user@host/repo.git``), if any.

    :param url: Repository URL
    :returns: The user name, or None
    """
    try:
        parts = urlsplit(url or "")
    except ValueError:
        return None
    rtnval = parts.username if parts.username else None
    return rtnval


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
    
    def __init__(
        self,
        db_session: DbSession,
        audit_logger=None,
        secret_manager=None,
        credential_resolver: Optional[Callable[[str], str]] = None,
        event_sink: Optional[Callable[..., List[Any]]] = None
    ):
        """
        Initialize the RepositoryManager with a database session.

        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        :param secret_manager: Optional legacy SecretManager for ``scope/name``
                               credential references
        :param credential_resolver: Optional callable ``(secret_ref) -> str``
                                    that reads a repository's credential
                                    secret (it raises
                                    :class:`RepositoryCredentialError` when
                                    the secret cannot be read). Preferred
                                    over ``secret_manager``.
        :param event_sink: Optional callable
                           ``(*, trigger_source, source_id, event_data)``
                           returning the watch trigger logs, called for
                           each change a fetch finds. Defaults to the
                           project's watches with the core action
                           managers (see
                           :func:`watch_manager.dispatch_watch_event`).
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
        self._secret_manager = secret_manager
        self._credential_resolver = credential_resolver
        self._event_sink = event_sink if event_sink is not None else self._dispatch_to_watches

    def _dispatch_to_watches(
        self,
        *,
        trigger_source: Any,
        source_id: int,
        event_data: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> List[Any]:
        """
        The default event sink: process the event with the project's
        watches (their actions run as ``user_id`` or the project owner).

        :returns: The watch trigger logs
        """
        from ccai.pychestrate.core.managers.watch_manager import dispatch_watch_event

        rtnval = dispatch_watch_event(
            db_session=self._db_session, trigger_source=trigger_source,
            source_id=source_id, event_data=event_data, user_id=user_id,
        )
        return rtnval
    
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
                "Choose the credential secret for {} authentication, or choose "
                "Public (no authentication) for a public repository.".format(
                    _AUTH_TYPE_LABELS.get(request.auth_type.value, request.auth_type.value)
                ),
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
            created_at=repository.created_at,
            credential_secret_ref=repository.credential_secret_ref
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

        # Forget the branches and tags recorded by fetches.
        from ccai.pychestrate.core.orm import ProjectRepositoryRef
        self._db_session.query(ProjectRepositoryRef).filter(
            ProjectRepositoryRef.repository_id == repository_id
        ).delete(synchronize_session=False)

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
        Resolve the credential a repository authenticates with.

        Repositories with ``auth_type == none`` need none. Otherwise the
        repository's ``credential_secret_ref`` is resolved through the
        ``credential_resolver`` the caller supplied (the web UI reads the
        secrets vault with the acting user's permissions) or, failing
        that, the legacy ``secret_manager`` (``scope/name`` references).
        A credential that cannot be resolved is an error: it used to be
        swallowed, git ran without credentials and every private
        repository failed.

        :param repository: The ProjectRepository ORM object
        :returns: The credential value, or None for ``auth_type == none``
        :raises RepositoryCredentialError: If the credential is missing or
                                           cannot be read
        """
        if repository.auth_type == RepositoryAuthType.NONE.value:
            return None

        secret_ref = (repository.credential_secret_ref or "").strip()
        if len(secret_ref) == 0:
            raise RepositoryCredentialError(
                "This repository uses {} authentication but has no credential "
                "secret. Edit the repository and choose one.".format(
                    _AUTH_TYPE_LABELS.get(repository.auth_type, repository.auth_type)
                )
            )

        if self._credential_resolver is not None:
            credential = self._credential_resolver(secret_ref)
        elif self._secret_manager is not None:
            try:
                credential = self._secret_manager.resolve_secret_reference(
                    "${" + secret_ref + "}"
                )
            except Exception:
                raise RepositoryCredentialError(
                    "The credential secret {} could not be read.".format(secret_ref)
                ) from None
        else:
            raise RepositoryCredentialError(
                "No secrets service is available to read the credential secret {}.".format(
                    secret_ref
                )
            )

        if credential is None or len(str(credential).strip()) == 0:
            raise RepositoryCredentialError(
                "The credential secret {} is empty.".format(secret_ref)
            )
        return str(credential)

    @contextmanager
    def _git_access(self, *, repository) -> Iterator[Dict[str, Any]]:
        """
        Prepare the environment git runs in to reach ``repository`` and
        clean up afterwards.

        * No prompts ever (``GIT_TERMINAL_PROMPT=0``, SSH ``BatchMode``).
        * ``https_token``: a private ``GIT_ASKPASS`` script answers the
          username prompt with the URL's user (or ``x-access-token``) and
          the password prompt with the token, both passed through the
          environment -- the token never appears on a command line or in
          a URL, and configured credential helpers are switched off.
        * ``ssh_key``: the key is written to a private temporary file and
          used through ``ssh -i ... -o IdentitiesOnly=yes``.

        :param repository: The ProjectRepository ORM object
        :yields: ``{"env": ..., "args": [...], "secrets": [...]}`` -- the
                 environment, the git options to put before the command,
                 and the values to scrub from anything git prints
        :raises RepositoryCredentialError: If the credential cannot be
                                           resolved
        """
        credential = self._get_credential_for_repository(repository)

        env = os.environ.copy()
        env['GIT_TERMINAL_PROMPT'] = '0'
        env['GIT_SSH_COMMAND'] = 'ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new'
        # Inherited prompt helpers must not answer for us, and git's trace
        # output would print the Authorization header.
        for inherited in list(env.keys()):
            if (
                inherited in ('GIT_ASKPASS', 'SSH_ASKPASS', 'GIT_PASSWORD', 'GIT_CURL_VERBOSE')
                or inherited.startswith('GIT_TRACE')
            ):
                env.pop(inherited, None)
        git_args: List[str] = []
        secrets: List[str] = []
        workdir = None

        try:
            if credential is not None:
                workdir = tempfile.mkdtemp(prefix="pyc-git-")
                if repository.auth_type == RepositoryAuthType.SSH_KEY.value:
                    # OpenSSH wants LF line endings and a final newline.
                    key_text = credential.replace("\r\n", "\n").strip() + "\n"
                    secrets.append(credential.strip())
                    key_path = os.path.join(workdir, "id_key")
                    key_fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(key_fd, "w") as key_file:
                        key_file.write(key_text)
                    env['GIT_SSH_COMMAND'] = (
                        "ssh -i {} -o IdentitiesOnly=yes -o BatchMode=yes "
                        "-o StrictHostKeyChecking=accept-new".format(shlex.quote(key_path))
                    )
                else:
                    token = credential.strip()
                    username = _username_from_url(url=repository.url) or "x-access-token"
                    secrets.append(token)
                    secrets.append(
                        base64.b64encode(
                            "{}:{}".format(username, token).encode("utf-8")
                        ).decode("ascii")
                    )
                    askpass_path = os.path.join(workdir, "askpass.sh")
                    askpass_fd = os.open(askpass_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
                    with os.fdopen(askpass_fd, "w") as askpass_file:
                        askpass_file.write(_ASKPASS_SCRIPT)
                    env['GIT_ASKPASS'] = askpass_path
                    env['PYCHESTRATE_GIT_USERNAME'] = username
                    env['PYCHESTRATE_GIT_TOKEN'] = token
                    git_args = ['-c', 'credential.helper=']
            yield {"env": env, "args": git_args, "secrets": secrets}
        finally:
            if workdir is not None:
                shutil.rmtree(workdir, ignore_errors=True)

    def _describe_git_failure(
        self,
        *,
        repository,
        action: str,
        stderr: Optional[str],
        secrets: List[str]
    ) -> str:
        """
        Turn a failed git command into a message for the user and log the
        details (with any credential scrubbed) for an administrator.

        :param repository: The ProjectRepository ORM object
        :param action: What was attempted, e.g. ``"connect to"``
        :param stderr: What git printed
        :param secrets: Values that must never be logged or shown
        :returns: A user-facing sentence
        """
        text = stderr or ""
        for secret in secrets:
            if secret:
                text = text.replace(secret, "********")
        lowered = text.lower()
        _module_logger.warning(
            "pychestrate.repository.git_failed repository_id=%s action=%s stderr=%s",
            getattr(repository, 'id', None), action, text.strip()[:2000],
        )
        explanation = (
            "git reported an error. Check the URL and credentials; an "
            "administrator can find the details in the server log."
        )
        for needles, message in _GIT_FAILURE_MESSAGES:
            if any(needle in lowered for needle in needles):
                explanation = message
                break
        rtnval = "Could not {} the repository: {}".format(action, explanation)
        return rtnval

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
                f"The repository did not answer within {timeout} seconds."
            )
        except Exception:
            _module_logger.exception("pychestrate.repository.git_unavailable")
            raise RepositoryConnectivityError(
                "Git could not be started on the server. An administrator can "
                "find the details in the server log."
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

        with self._git_access(repository=repository) as access:
            # Use git ls-remote to test connectivity without cloning
            result = self._run_git_command(
                access['args'] + ['ls-remote', '--heads', repository.url],
                env=access['env'],
                timeout=30
            )

            if result.returncode != 0:
                raise RepositoryConnectivityError(
                    self._describe_git_failure(
                        repository=repository, action="connect to", stderr=result.stderr,
                        secrets=access["secrets"],
                    )
                )

        return True
    
    def fetch_latest(self, repository_id: int) -> RepositoryResponse:
        """
        Fetch the repository's branches and tags, record the default
        branch's latest commit, and fire the project's repository watches
        for what changed since the previous fetch:

        * a branch that moved -- ``repository_commit``;
        * a new branch -- ``repository_branch`` and ``repository_commit``;
        * a new tag -- ``repository_tag``.

        The first fetch of a repository only records its branches and
        tags (announcing every existing ref would start a build for each).

        :param repository_id: The repository's unique identifier
        :returns: RepositoryResponse with updated commit information; its
                  ``ref_changes`` lists what changed and
                  ``watches_triggered`` how many watches fired
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

        with self._git_access(repository=repository) as access:
            remote_refs = self._list_remote_refs(repository=repository, access=access)

        now = utc_now()
        repository.last_fetch_time = now
        commit_sha = remote_refs['branch'].get(repository.default_branch)
        if commit_sha and commit_sha != repository.last_commit_sha:
            repository.last_commit_sha = commit_sha
            # The details of the previous commit no longer apply.
            repository.last_commit_message = None
            repository.last_commit_author = None
            repository.last_commit_time = None
            commit_info = self._get_commit_details(repository, commit_sha)
            if commit_info:
                repository.last_commit_message = commit_info.get('message', '')[:512]
                repository.last_commit_author = commit_info.get('author', '')[:128]
                if commit_info.get('time'):
                    repository.last_commit_time = commit_info['time']

        ref_changes, first_recorded = self._record_refs(
            repository=repository, remote_refs=remote_refs, now=now
        )
        self._db_session.commit()

        watches_triggered = self._dispatch_ref_changes(repository=repository, ref_changes=ref_changes)

        rtnval = self._repository_to_response(repository)
        rtnval.ref_changes = ref_changes
        rtnval.watches_triggered = watches_triggered
        rtnval.refs_first_recorded = first_recorded
        return rtnval

    def _list_remote_refs(self, *, repository, access: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        """
        List the remote's branches and tags with ``git ls-remote``.

        :param repository: The ProjectRepository ORM object
        :param access: What :meth:`_git_access` yielded
        :returns: ``{"branch": {name: sha}, "tag": {name: sha}}``; an
                  annotated tag maps to the commit it points at
        :raises RepositoryConnectivityError: If git fails
        """
        result = self._run_git_command(
            access['args'] + ['ls-remote', '--heads', '--tags', repository.url],
            env=access['env'],
            timeout=60
        )
        if result.returncode != 0:
            raise RepositoryConnectivityError(
                self._describe_git_failure(
                    repository=repository, action="fetch from", stderr=result.stderr,
                    secrets=access["secrets"],
                )
            )

        branches: Dict[str, str] = {}
        tags: Dict[str, str] = {}
        peeled: Dict[str, str] = {}
        for line in (result.stdout or "").splitlines():
            parts = line.strip().split("\t")
            if len(parts) != 2:
                continue
            sha, ref = parts[0].strip(), parts[1].strip()
            if ref.startswith("refs/heads/"):
                branches[ref[len("refs/heads/"):]] = sha
            elif ref.startswith("refs/tags/"):
                name = ref[len("refs/tags/"):]
                if name.endswith("^{}"):
                    peeled[name[:-len("^{}")]] = sha
                else:
                    tags[name] = sha
        tags.update(peeled)
        rtnval = {"branch": branches, "tag": tags}
        return rtnval

    def _record_refs(
        self,
        *,
        repository,
        remote_refs: Dict[str, Dict[str, str]],
        now: datetime
    ) -> Any:
        """
        Bring the stored refs in line with the remote and report what
        changed. Nothing is reported while no refs are stored yet (the
        first fetch sets the baseline). A tag that moved is recorded but
        not reported; refs deleted on the remote are forgotten.

        :param repository: The ProjectRepository ORM object
        :param remote_refs: What :meth:`_list_remote_refs` returned
        :param now: Timestamp of this fetch
        :returns: ``(changes, first_recorded)``: the changes, each
                  ``{"change": "commit" | "branch_created" |
                  "tag_created", "name", "commit_sha", "previous_sha"}``,
                  and whether this fetch set the baseline
        """
        from ccai.pychestrate.core.orm import ProjectRepositoryRef

        stored = self._db_session.query(ProjectRepositoryRef).filter(
            ProjectRepositoryRef.repository_id == repository.id
        ).all()
        known = {(row.kind, row.name): row for row in stored}
        baseline = len(stored) == 0

        changes: List[Dict[str, Any]] = []
        for kind in ("branch", "tag"):
            for name, sha in sorted(remote_refs.get(kind, {}).items()):
                row = known.pop((kind, name), None)
                if row is None:
                    self._db_session.add(ProjectRepositoryRef(
                        repository_id=repository.id, kind=kind, name=name[:255],
                        commit_sha=sha, first_seen_at=now, updated_at=now,
                    ))
                    if baseline is False:
                        changes.append({
                            "change": "branch_created" if kind == "branch" else "tag_created",
                            "name": name, "commit_sha": sha, "previous_sha": None,
                        })
                elif row.commit_sha != sha:
                    previous_sha = row.commit_sha
                    row.commit_sha = sha
                    row.updated_at = now
                    if kind == "branch" and baseline is False:
                        changes.append({
                            "change": "commit", "name": name, "commit_sha": sha,
                            "previous_sha": previous_sha,
                        })
        for row in known.values():
            self._db_session.delete(row)

        # An empty remote records nothing, so its first push is the baseline.
        first_recorded = baseline and len(remote_refs.get("branch", {})) + len(remote_refs.get("tag", {})) > 0
        rtnval = (changes, first_recorded)
        return rtnval

    def _dispatch_ref_changes(self, *, repository, ref_changes: List[Dict[str, Any]]) -> int:
        """
        Fire the repository watches for each change found by a fetch.
        A failing watch never fails the fetch: the error is logged.

        :param repository: The ProjectRepository ORM object
        :param ref_changes: What :meth:`_record_refs` returned
        :returns: How many watches fired
        """
        from ccai.pychestrate.core.managers.watch_manager import WatchTriggerSource

        events = []
        for change in ref_changes:
            base = {
                "repository_id": repository.id,
                "repository_name": repository.name,
                "commit_sha": change["commit_sha"],
            }
            if change["change"] == "tag_created":
                events.append((WatchTriggerSource.REPOSITORY_TAG, dict(base, tag=change["name"])))
                continue
            commit_event = dict(base, branch=change["name"], previous_sha=change["previous_sha"])
            if change["change"] == "branch_created":
                events.append((WatchTriggerSource.REPOSITORY_BRANCH, dict(base, branch=change["name"])))
                commit_event["created"] = True
            events.append((WatchTriggerSource.REPOSITORY_COMMIT, commit_event))

        fired = 0
        for trigger_source, event_data in events:
            try:
                trigger_logs = self._event_sink(
                    trigger_source=trigger_source, source_id=repository.id, event_data=event_data,
                )
                fired = fired + len(trigger_logs or [])
            except Exception:
                _module_logger.exception(
                    "pychestrate.repository.watch_dispatch_failed repository_id=%s trigger=%s",
                    repository.id, trigger_source.value,
                )
                try:
                    self._db_session.rollback()
                except Exception:
                    pass
        rtnval = fired
        return rtnval
    
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
        
        with self._git_access(repository=repository) as access:
            # Get all branches using ls-remote
            result = self._run_git_command(
                access['args'] + ['ls-remote', '--heads', repository.url],
                env=access['env'],
                timeout=30
            )

            if result.returncode != 0:
                raise RepositoryConnectivityError(
                    self._describe_git_failure(
                        repository=repository, action="list the branches of", stderr=result.stderr,
                        secrets=access["secrets"],
                    )
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
        
        commit_sha = None
        ref_type = 'branch'

        with self._git_access(repository=repository) as access:
            # Try to resolve the ref
            # First try as a branch
            result = self._run_git_command(
                access['args'] + ['ls-remote', repository.url, f'refs/heads/{ref}'],
                env=access['env'],
                timeout=30
            )

            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split()
                if parts:
                    commit_sha = parts[0]
            else:
                # Try as a tag
                result = self._run_git_command(
                    access['args'] + ['ls-remote', repository.url, f'refs/tags/{ref}'],
                    env=access['env'],
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
