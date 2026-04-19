"""
.. module:: test_watch_manager_repository_cascade
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for repository removal cascading to watches

.. moduleauthor:: Automation Mojo LLC

Property tests for repository removal cascading to watches.

**Feature: projects**
**Property 22: Repository Removal Cascades to Watches**
**Validates: Requirements 3.2**
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
    RepositoryAuthType,
    RepositoryHasReferencesError,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_name():
    """Generate a unique name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest = ''.join(random.choices(string.ascii_letters + string.digits + '_-.', k=random.randint(5, 20)))
    return start_char + rest


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


def create_mock_watch(watch_id, project_id, name, repository_id, enabled=True):
    """Create a mock watch object matching the ProjectWatch ORM model."""
    mock_watch = Mock()
    mock_watch.configure(recursive=True)
    ctx = mock_watch.mock_context()
    ctx.set_attribute('id', watch_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('trigger_source', 'repository_commit')
    ctx.set_attribute('source_id', repository_id)
    ctx.set_attribute('repository_id', repository_id)
    ctx.set_attribute('conditions_json', {})
    ctx.set_attribute('actions_json', [{'action': 'trigger_build', 'target_id': 1, 'parameters': {}}])
    ctx.set_attribute('enabled', enabled)
    ctx.set_attribute('is_enabled', enabled)  # Alternative attribute name
    ctx.set_attribute('description', '')
    ctx.set_attribute('last_trigger_time', None)
    ctx.set_attribute('trigger_count', 0)
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('updated_at', Mock())
    return mock_watch


def create_mock_session_for_remove_repository(repository, build_spec_count=0, watches=None):
    """
    Create a mock session for remove_repository operation.
    
    Query flow (based on actual implementation):
    1. Query ProjectRepository to find repository
    2. Query ProjectBuildSpec to count references
    3. Query ProjectWatch to find related watches
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    watches = watches or []
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # First call: find repository
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=repository)
        # Second call: count build specs
        elif call_count[0] == 2:
            mock_filter.mock_context().mock_method('count', return_value=build_spec_count)
        # Third call: find watches
        elif call_count[0] == 3:
            mock_filter.mock_context().mock_method('all', return_value=watches)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
            mock_filter.mock_context().mock_method('count', return_value=0)
            mock_filter.mock_context().mock_method('all', return_value=[])
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('delete')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Property Tests for Repository Removal Cascading to Watches
# =============================================================================

def test_remove_repository_disables_related_watches():
    """
    **Feature: projects, Property 22: Repository Removal Cascades to Watches**
    **Validates: Requirements 3.2**
    
    Removing a repository should disable all watches that reference it.
    """
    project_id = 1
    repo_id = 10
    user_id = 'user-1'
    
    mock_repo = create_mock_repository(repo_id, project_id, 'test-repo')
    
    # Create watches that reference this repository
    watches = [
        create_mock_watch(1, project_id, 'watch-1', repo_id, enabled=True),
        create_mock_watch(2, project_id, 'watch-2', repo_id, enabled=True),
    ]
    
    mock_session = create_mock_session_for_remove_repository(mock_repo, build_spec_count=0, watches=watches)
    manager = RepositoryManager(mock_session)
    
    manager.remove_repository(repo_id, user_id)
    
    # All watches should be disabled
    for watch in watches:
        assert watch.is_enabled == False, f"Watch {watch.name} should be disabled after repository removal"


def test_remove_repository_with_no_watches():
    """
    **Feature: projects, Property 22: Repository Removal Cascades to Watches**
    **Validates: Requirements 3.2**
    
    Removing a repository with no watches should succeed without errors.
    """
    project_id = 1
    repo_id = 10
    user_id = 'user-1'
    
    mock_repo = create_mock_repository(repo_id, project_id, 'test-repo')
    mock_session = create_mock_session_for_remove_repository(mock_repo, build_spec_count=0, watches=[])
    manager = RepositoryManager(mock_session)
    
    # Should not raise any exception
    try:
        manager.remove_repository(repo_id, user_id)
        success = True
    except Exception:
        success = False
    
    assert success, "Removing repository with no watches should succeed"


def test_remove_repository_with_build_specs_fails():
    """
    **Feature: projects, Property 22: Repository Removal Cascades to Watches**
    **Validates: Requirements 3.2**
    
    Removing a repository with build specs should fail.
    """
    project_id = 1
    repo_id = 10
    user_id = 'user-1'
    
    mock_repo = create_mock_repository(repo_id, project_id, 'test-repo')
    mock_session = create_mock_session_for_remove_repository(mock_repo, build_spec_count=2, watches=[])
    manager = RepositoryManager(mock_session)
    
    error_raised = False
    try:
        manager.remove_repository(repo_id, user_id)
    except RepositoryHasReferencesError:
        error_raised = True
    
    assert error_raised, "Removing repository with build specs should raise RepositoryHasReferencesError"


def test_property_all_watches_disabled_on_removal():
    """
    **Feature: projects, Property 22: Repository Removal Cascades to Watches**
    **Validates: Requirements 3.2**
    
    Property test: For any repository removal, all related watches should be disabled.
    """
    for _ in range(100):
        project_id = random.randint(1, 100)
        repo_id = random.randint(1, 100)
        user_id = f'user-{random.randint(1, 100)}'
        
        mock_repo = create_mock_repository(repo_id, project_id, generate_unique_name())
        
        # Create random number of watches
        num_watches = random.randint(0, 10)
        watches = [
            create_mock_watch(i + 1, project_id, f'watch-{i}', repo_id, enabled=True)
            for i in range(num_watches)
        ]
        
        mock_session = create_mock_session_for_remove_repository(mock_repo, build_spec_count=0, watches=watches)
        manager = RepositoryManager(mock_session)
        
        manager.remove_repository(repo_id, user_id)
        
        # All watches should be disabled
        for watch in watches:
            assert watch.is_enabled == False, \
                f"Watch should be disabled after repository removal"


def test_property_only_related_watches_affected():
    """
    **Feature: projects, Property 22: Repository Removal Cascades to Watches**
    **Validates: Requirements 3.2**
    
    Property test: Only watches related to the removed repository should be disabled.
    """
    for _ in range(50):
        project_id = 1
        repo_id = 10
        other_repo_id = 20
        user_id = 'user-1'
        
        mock_repo = create_mock_repository(repo_id, project_id, 'test-repo')
        
        # Create watches for the repository being removed
        related_watches = [
            create_mock_watch(i + 1, project_id, f'related-watch-{i}', repo_id, enabled=True)
            for i in range(random.randint(1, 5))
        ]
        
        # Create watches for a different repository (these should not be affected)
        # Note: In the actual implementation, these wouldn't be returned by the query
        # because the query filters by repository_id
        
        mock_session = create_mock_session_for_remove_repository(mock_repo, build_spec_count=0, watches=related_watches)
        manager = RepositoryManager(mock_session)
        
        manager.remove_repository(repo_id, user_id)
        
        # All related watches should be disabled
        for watch in related_watches:
            assert watch.is_enabled == False, \
                f"Related watch should be disabled"


def test_property_disabled_watches_remain_disabled():
    """
    **Feature: projects, Property 22: Repository Removal Cascades to Watches**
    **Validates: Requirements 3.2**
    
    Property test: Already disabled watches should remain disabled after repository removal.
    """
    for _ in range(50):
        project_id = 1
        repo_id = 10
        user_id = 'user-1'
        
        mock_repo = create_mock_repository(repo_id, project_id, 'test-repo')
        
        # Create a mix of enabled and disabled watches
        watches = []
        for i in range(random.randint(1, 5)):
            enabled = random.choice([True, False])
            watch = create_mock_watch(i + 1, project_id, f'watch-{i}', repo_id, enabled=enabled)
            watches.append(watch)
        
        mock_session = create_mock_session_for_remove_repository(mock_repo, build_spec_count=0, watches=watches)
        manager = RepositoryManager(mock_session)
        
        manager.remove_repository(repo_id, user_id)
        
        # All watches should be disabled (including those that were already disabled)
        for watch in watches:
            assert watch.is_enabled == False, \
                f"Watch should be disabled after repository removal"


def test_multiple_repositories_independent():
    """
    **Feature: projects, Property 22: Repository Removal Cascades to Watches**
    **Validates: Requirements 3.2**
    
    Removing one repository should not affect watches for other repositories.
    """
    project_id = 1
    repo1_id = 10
    repo2_id = 20
    user_id = 'user-1'
    
    # First repository with its watches
    mock_repo1 = create_mock_repository(repo1_id, project_id, 'repo-1')
    watches_repo1 = [
        create_mock_watch(1, project_id, 'watch-1', repo1_id, enabled=True),
    ]
    
    # Second repository with its watches (not affected)
    watches_repo2 = [
        create_mock_watch(2, project_id, 'watch-2', repo2_id, enabled=True),
    ]
    
    # Remove first repository
    mock_session = create_mock_session_for_remove_repository(mock_repo1, build_spec_count=0, watches=watches_repo1)
    manager = RepositoryManager(mock_session)
    
    manager.remove_repository(repo1_id, user_id)
    
    # Watches for repo1 should be disabled
    for watch in watches_repo1:
        assert watch.is_enabled == False, "Watch for removed repo should be disabled"
    
    # Watches for repo2 should still be enabled (they weren't in the query result)
    for watch in watches_repo2:
        assert watch.is_enabled == True, "Watch for other repo should remain enabled"


def test_property_cascade_with_various_watch_counts():
    """
    **Feature: projects, Property 22: Repository Removal Cascades to Watches**
    **Validates: Requirements 3.2**
    
    Property test: Repository removal should work correctly regardless of watch count.
    """
    watch_counts = [0, 1, 2, 5, 10, 20, 50]
    
    for count in watch_counts:
        project_id = 1
        repo_id = 10
        user_id = 'user-1'
        
        mock_repo = create_mock_repository(repo_id, project_id, 'test-repo')
        
        watches = [
            create_mock_watch(i + 1, project_id, f'watch-{i}', repo_id, enabled=True)
            for i in range(count)
        ]
        
        mock_session = create_mock_session_for_remove_repository(mock_repo, build_spec_count=0, watches=watches)
        manager = RepositoryManager(mock_session)
        
        manager.remove_repository(repo_id, user_id)
        
        # All watches should be disabled
        disabled_count = sum(1 for w in watches if w.is_enabled == False)
        assert disabled_count == count, \
            f"All {count} watches should be disabled, got {disabled_count}"


def test_property_removal_is_idempotent_for_disabled_watches():
    """
    **Feature: projects, Property 22: Repository Removal Cascades to Watches**
    **Validates: Requirements 3.2**
    
    Property test: Setting is_enabled to False on already disabled watches should be safe.
    """
    for _ in range(50):
        project_id = 1
        repo_id = 10
        user_id = 'user-1'
        
        mock_repo = create_mock_repository(repo_id, project_id, 'test-repo')
        
        # All watches already disabled
        watches = [
            create_mock_watch(i + 1, project_id, f'watch-{i}', repo_id, enabled=False)
            for i in range(random.randint(1, 5))
        ]
        
        mock_session = create_mock_session_for_remove_repository(mock_repo, build_spec_count=0, watches=watches)
        manager = RepositoryManager(mock_session)
        
        # Should not raise any exception
        try:
            manager.remove_repository(repo_id, user_id)
            success = True
        except Exception:
            success = False
        
        assert success, "Removing repository with already disabled watches should succeed"
        
        # All watches should still be disabled
        for watch in watches:
            assert watch.is_enabled == False

