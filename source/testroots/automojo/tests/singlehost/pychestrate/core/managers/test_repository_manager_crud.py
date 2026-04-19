"""
.. module:: test_repository_manager_crud
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for RepositoryManager CRUD operations

.. moduleauthor:: Automation Mojo LLC

Tests for repository CRUD operations in the RepositoryManager.

**Feature: projects**
**Validates: Requirements 3.1, 3.2, 3.6, 3.7**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.repository_manager import (
    RepositoryManager,
    RepositoryCreateRequest,
    RepositoryUpdateRequest,
    RepositoryAuthType,
    RepositoryNotFoundError,
    DuplicateRepositoryError,
    ProjectNotFoundError,
    RepositoryHasReferencesError,
    validate_repository_name,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_repository_name():
    """Generate a unique repository name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest = ''.join(random.choices(string.ascii_letters + string.digits + '_-.', k=random.randint(5, 20)))
    return start_char + rest


def create_mock_project(project_id, name='test-project'):
    """Create a mock project object matching the Project ORM model."""
    mock_project = Mock()
    mock_project.configure(recursive=True)
    ctx = mock_project.mock_context()
    ctx.set_attribute('id', project_id)
    ctx.set_attribute('name', name)
    return mock_project


def create_mock_repository(repo_id, project_id, name, url='https://github.com/test/repo.git'):
    """Create a mock repository object matching the ProjectRepository ORM model."""
    mock_repo = Mock()
    mock_repo.configure(recursive=True)
    ctx = mock_repo.mock_context()
    ctx.set_attribute('id', repo_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('url', url)
    ctx.set_attribute('auth_type', RepositoryAuthType.NONE.value)
    ctx.set_attribute('credential_secret_ref', None)
    ctx.set_attribute('default_branch', 'main')
    ctx.set_attribute('description', '')
    ctx.set_attribute('last_commit_sha', None)
    ctx.set_attribute('last_commit_message', None)
    ctx.set_attribute('last_commit_author', None)
    ctx.set_attribute('last_commit_time', None)
    ctx.set_attribute('last_fetch_time', None)
    ctx.set_attribute('created_at', Mock())
    return mock_repo


def create_mock_session_for_add_repository(project=None, existing_repo=None):
    """
    Create a mock session for add_repository operation.
    
    Query flow:
    1. Query Project to verify project exists
    2. Query ProjectRepository to check for duplicate name
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # First call: project lookup
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=project)
        # Second call: duplicate repository check
        elif call_count[0] == 2:
            mock_filter.mock_context().mock_method('first', return_value=existing_repo)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


def create_mock_session_for_get_repository(repository=None):
    """Create a mock session for get_repository operation."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=repository)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    return mock_session


def create_mock_session_for_list_repositories(repositories, total=None):
    """Create a mock session for list_repositories operation."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    
    # Count returns total
    mock_filter.mock_context().mock_method('count', return_value=total or len(repositories))
    
    # Order by returns mock that supports offset/limit
    mock_order = Mock()
    mock_order.configure(recursive=True)
    mock_offset = Mock()
    mock_offset.configure(recursive=True)
    mock_offset.mock_context().mock_method('limit', return_value=Mock())
    mock_offset.mock_context().mock_method('all', return_value=repositories)
    
    # Chain: order_by -> offset -> limit -> all
    mock_limit = Mock()
    mock_limit.configure(recursive=True)
    mock_limit.mock_context().mock_method('all', return_value=repositories)
    mock_offset.mock_context().mock_method('limit', return_value=mock_limit)
    mock_order.mock_context().mock_method('offset', return_value=mock_offset)
    mock_filter.mock_context().mock_method('order_by', return_value=mock_order)
    
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    return mock_session


# =============================================================================
# Repository Name Validation Tests
# =============================================================================

def test_valid_repository_names_pass_validation():
    """
    **Validates: Requirements 3.1**
    
    Valid repository names with alphanumeric start and allowed characters should pass.
    """
    valid_names = [
        "repo123",
        "test_repo",
        "my-repo",
        "Repo_Name-123",
        "a",
        "ABC",
        "repo_with_underscore",
        "repo-with-hyphen",
        "repo.with.period",
        "MixedCase123",
        "x" * 128,  # Max length
    ]
    
    for name in valid_names:
        result = validate_repository_name(name)
        assert result is True, f"Valid repository name '{name}' should pass validation"


def test_invalid_repository_names_fail_validation():
    """
    **Validates: Requirements 3.1**
    
    Invalid repository names should fail validation.
    """
    invalid_names = [
        "",
        None,
        "_startswithunderscore",
        "-startswithhyphen",
        ".startswithperiod",
        "has space",
        "has@special",
        "x" * 129,  # Too long
    ]
    
    for name in invalid_names:
        result = validate_repository_name(name)
        assert result is False, f"Invalid repository name '{name}' should fail validation"


# =============================================================================
# Repository CRUD Tests
# =============================================================================

def test_add_repository_success():
    """
    **Validates: Requirements 3.1**
    
    Adding a repository to a project should succeed with valid data.
    """
    project_id = 1
    user_id = 'user-1'
    repo_name = generate_unique_repository_name()
    
    mock_project = create_mock_project(project_id)
    mock_session = create_mock_session_for_add_repository(project=mock_project, existing_repo=None)
    
    manager = RepositoryManager(mock_session)
    
    request = RepositoryCreateRequest(
        name=repo_name,
        url='https://github.com/test/repo.git',
        auth_type=RepositoryAuthType.NONE,
        description='Test repository'
    )
    
    # Should not raise any exception
    try:
        manager.add_repository(project_id, request, user_id)
        success = True
    except Exception as e:
        success = False
    
    assert success, "Adding a valid repository should succeed"


def test_add_repository_project_not_found():
    """
    **Validates: Requirements 3.1**
    
    Adding a repository to a non-existent project should raise ProjectNotFoundError.
    """
    project_id = 999
    user_id = 'user-1'
    
    mock_session = create_mock_session_for_add_repository(project=None, existing_repo=None)
    
    manager = RepositoryManager(mock_session)
    
    request = RepositoryCreateRequest(
        name='test-repo',
        url='https://github.com/test/repo.git',
        auth_type=RepositoryAuthType.NONE
    )
    
    error_raised = False
    try:
        manager.add_repository(project_id, request, user_id)
    except ProjectNotFoundError:
        error_raised = True
    
    assert error_raised, "Adding repository to non-existent project should raise ProjectNotFoundError"


def test_add_repository_duplicate_name():
    """
    **Validates: Requirements 3.1**
    
    Adding a repository with a duplicate name in the same project should raise DuplicateRepositoryError.
    """
    project_id = 1
    user_id = 'user-1'
    repo_name = 'existing-repo'
    
    mock_project = create_mock_project(project_id)
    mock_existing_repo = create_mock_repository(1, project_id, repo_name)
    mock_session = create_mock_session_for_add_repository(project=mock_project, existing_repo=mock_existing_repo)
    
    manager = RepositoryManager(mock_session)
    
    request = RepositoryCreateRequest(
        name=repo_name,
        url='https://github.com/test/repo.git',
        auth_type=RepositoryAuthType.NONE
    )
    
    error_raised = False
    try:
        manager.add_repository(project_id, request, user_id)
    except DuplicateRepositoryError:
        error_raised = True
    
    assert error_raised, "Adding repository with duplicate name should raise DuplicateRepositoryError"


def test_get_repository_found():
    """
    **Validates: Requirements 3.6**
    
    Getting an existing repository should return the repository data.
    """
    repo_id = 1
    project_id = 1
    repo_name = 'test-repo'
    
    mock_repo = create_mock_repository(repo_id, project_id, repo_name)
    mock_session = create_mock_session_for_get_repository(repository=mock_repo)
    
    manager = RepositoryManager(mock_session)
    
    result = manager.get_repository(repo_id)
    
    assert result is not None, "Getting existing repository should return data"
    assert result.id == repo_id
    assert result.name == repo_name


def test_get_repository_not_found():
    """
    **Validates: Requirements 3.6**
    
    Getting a non-existent repository should return None.
    """
    repo_id = 999
    
    mock_session = create_mock_session_for_get_repository(repository=None)
    
    manager = RepositoryManager(mock_session)
    
    result = manager.get_repository(repo_id)
    
    assert result is None, "Getting non-existent repository should return None"


def test_list_repositories_returns_paginated_results():
    """
    **Validates: Requirements 3.6**
    
    Listing repositories should return paginated results with repository details.
    """
    project_id = 1
    
    mock_repos = [
        create_mock_repository(1, project_id, 'repo-1'),
        create_mock_repository(2, project_id, 'repo-2'),
        create_mock_repository(3, project_id, 'repo-3'),
    ]
    
    mock_session = create_mock_session_for_list_repositories(mock_repos, total=3)
    
    manager = RepositoryManager(mock_session)
    
    result = manager.list_repositories(project_id, offset=0, limit=10)
    
    assert result.total == 3
    assert len(result.repositories) == 3
    assert result.offset == 0
    assert result.limit == 10


# =============================================================================
# Authentication Type Tests
# =============================================================================

def test_add_repository_https_token_requires_credential():
    """
    **Validates: Requirements 3.3**
    
    Adding a repository with HTTPS_TOKEN auth type requires credential_secret_ref.
    """
    project_id = 1
    user_id = 'user-1'
    
    mock_project = create_mock_project(project_id)
    mock_session = create_mock_session_for_add_repository(project=mock_project, existing_repo=None)
    
    manager = RepositoryManager(mock_session)
    
    request = RepositoryCreateRequest(
        name='test-repo',
        url='https://github.com/test/repo.git',
        auth_type=RepositoryAuthType.HTTPS_TOKEN,
        credential_secret_ref=None  # Missing credential
    )
    
    error_raised = False
    try:
        manager.add_repository(project_id, request, user_id)
    except Exception as e:
        if 'credential' in str(e).lower():
            error_raised = True
    
    assert error_raised, "HTTPS_TOKEN auth type should require credential_secret_ref"


def test_add_repository_ssh_key_requires_credential():
    """
    **Validates: Requirements 3.3**
    
    Adding a repository with SSH_KEY auth type requires credential_secret_ref.
    """
    project_id = 1
    user_id = 'user-1'
    
    mock_project = create_mock_project(project_id)
    mock_session = create_mock_session_for_add_repository(project=mock_project, existing_repo=None)
    
    manager = RepositoryManager(mock_session)
    
    request = RepositoryCreateRequest(
        name='test-repo',
        url='git@github.com:test/repo.git',
        auth_type=RepositoryAuthType.SSH_KEY,
        credential_secret_ref=None  # Missing credential
    )
    
    error_raised = False
    try:
        manager.add_repository(project_id, request, user_id)
    except Exception as e:
        if 'credential' in str(e).lower():
            error_raised = True
    
    assert error_raised, "SSH_KEY auth type should require credential_secret_ref"


def test_add_repository_none_auth_no_credential_required():
    """
    **Validates: Requirements 3.3**
    
    Adding a repository with NONE auth type does not require credential_secret_ref.
    """
    project_id = 1
    user_id = 'user-1'
    
    mock_project = create_mock_project(project_id)
    mock_session = create_mock_session_for_add_repository(project=mock_project, existing_repo=None)
    
    manager = RepositoryManager(mock_session)
    
    request = RepositoryCreateRequest(
        name='test-repo',
        url='https://github.com/test/repo.git',
        auth_type=RepositoryAuthType.NONE,
        credential_secret_ref=None
    )
    
    # Should not raise any exception
    try:
        manager.add_repository(project_id, request, user_id)
        success = True
    except Exception:
        success = False
    
    assert success, "NONE auth type should not require credential_secret_ref"
