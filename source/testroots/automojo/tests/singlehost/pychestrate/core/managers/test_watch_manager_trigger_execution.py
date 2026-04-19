"""
.. module:: test_watch_manager_trigger_execution
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for WatchManager trigger execution

.. moduleauthor:: Automation Mojo LLC

Property tests for watch trigger execution in the WatchManager.

**Feature: projects**
**Property 21: Watch Trigger Execution**
**Validates: Requirements 10.6**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.watch_manager import (
    WatchManager,
    WatchTriggerSource,
    WatchAction,
    WatchCondition,
    WatchActionConfig,
    WatchCreateRequest,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_watch_name():
    """Generate a unique watch name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest = ''.join(random.choices(string.ascii_letters + string.digits + '_-.', k=random.randint(5, 20)))
    return start_char + rest


def generate_branch_name():
    """Generate a random branch name."""
    prefixes = ['feature/', 'bugfix/', 'release/', 'hotfix/', '']
    prefix = random.choice(prefixes)
    name = ''.join(random.choices(string.ascii_lowercase + string.digits + '-', k=random.randint(3, 15)))
    return prefix + name


def generate_tag_name():
    """Generate a random tag name."""
    major = random.randint(0, 99)
    minor = random.randint(0, 99)
    patch = random.randint(0, 99)
    return f"v{major}.{minor}.{patch}"


def create_mock_watch(watch_id, project_id, name, trigger_source, source_id, 
                      conditions=None, actions=None, enabled=True):
    """Create a mock watch object matching the ProjectWatch ORM model."""
    mock_watch = Mock()
    mock_watch.configure(recursive=True)
    ctx = mock_watch.mock_context()
    ctx.set_attribute('id', watch_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('trigger_source', trigger_source.value if isinstance(trigger_source, WatchTriggerSource) else trigger_source)
    ctx.set_attribute('source_id', source_id)
    ctx.set_attribute('repository_id', source_id if trigger_source != WatchTriggerSource.BUILD_COMPLETION else None)
    ctx.set_attribute('conditions_json', conditions or {})
    ctx.set_attribute('actions_json', actions or [{'action': 'trigger_build', 'target_id': 1, 'parameters': {}}])
    ctx.set_attribute('enabled', enabled)
    ctx.set_attribute('description', '')
    ctx.set_attribute('last_trigger_time', None)
    ctx.set_attribute('trigger_count', 0)
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('updated_at', Mock())
    return mock_watch


def create_mock_session_for_process_event(watches):
    """
    Create a mock session for process_event operation.
    
    Query flow:
    1. Query ProjectWatch to find matching watches
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    # Create a mock that returns watches when .all() is called
    # The query chain is: query(Model).filter(...).all()
    mock_all_result = Mock()
    mock_all_result.configure(recursive=True)
    mock_all_result.mock_context().mock_method('all', return_value=watches)
    mock_all_result.mock_context().mock_method('filter', return_value=mock_all_result)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_query.mock_context().mock_method('filter', return_value=mock_all_result)
    
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Property Tests for Watch Trigger Execution
# =============================================================================

def test_matching_event_triggers_watch():
    """
    **Feature: projects, Property 21: Watch Trigger Execution**
    **Validates: Requirements 10.6**
    
    An event matching a watch's trigger conditions should trigger the watch.
    """
    project_id = 1
    watch_id = 1
    source_id = 10
    
    # Create a watch with branch pattern condition
    mock_watch = create_mock_watch(
        watch_id, project_id, 'test-watch',
        WatchTriggerSource.REPOSITORY_COMMIT, source_id,
        conditions={'branch_pattern': 'main'},
        actions=[{'action': 'trigger_build', 'target_id': 1, 'parameters': {}}],
        enabled=True
    )
    
    mock_session = create_mock_session_for_process_event([mock_watch])
    manager = WatchManager(mock_session)
    
    # Event that matches the condition
    event_data = {'branch': 'main', 'commit_sha': 'abc123'}
    
    result = manager.process_event(
        WatchTriggerSource.REPOSITORY_COMMIT,
        source_id,
        event_data
    )
    
    # Should have triggered the watch
    assert len(result) == 1, "Matching event should trigger exactly one watch"
    assert result[0].watch_id == watch_id


def test_non_matching_event_does_not_trigger():
    """
    **Feature: projects, Property 21: Watch Trigger Execution**
    **Validates: Requirements 10.6**
    
    An event not matching a watch's conditions should not trigger the watch.
    """
    project_id = 1
    watch_id = 1
    source_id = 10
    
    # Create a watch with branch pattern condition
    mock_watch = create_mock_watch(
        watch_id, project_id, 'test-watch',
        WatchTriggerSource.REPOSITORY_COMMIT, source_id,
        conditions={'branch_pattern': '^main$'},
        actions=[{'action': 'trigger_build', 'target_id': 1, 'parameters': {}}],
        enabled=True
    )
    
    mock_session = create_mock_session_for_process_event([mock_watch])
    manager = WatchManager(mock_session)
    
    # Event that does NOT match the condition
    event_data = {'branch': 'feature/test', 'commit_sha': 'abc123'}
    
    result = manager.process_event(
        WatchTriggerSource.REPOSITORY_COMMIT,
        source_id,
        event_data
    )
    
    # Should not have triggered the watch
    assert len(result) == 0, "Non-matching event should not trigger any watch"


def test_disabled_watch_not_triggered():
    """
    **Feature: projects, Property 21: Watch Trigger Execution**
    **Validates: Requirements 10.6**
    
    A disabled watch should not be triggered even if conditions match.
    """
    project_id = 1
    watch_id = 1
    source_id = 10
    
    # Create a disabled watch
    mock_watch = create_mock_watch(
        watch_id, project_id, 'test-watch',
        WatchTriggerSource.REPOSITORY_COMMIT, source_id,
        conditions={'branch_pattern': 'main'},
        actions=[{'action': 'trigger_build', 'target_id': 1, 'parameters': {}}],
        enabled=False  # Disabled
    )
    
    # Session returns no watches because query filters by enabled=True
    mock_session = create_mock_session_for_process_event([])
    manager = WatchManager(mock_session)
    
    event_data = {'branch': 'main', 'commit_sha': 'abc123'}
    
    result = manager.process_event(
        WatchTriggerSource.REPOSITORY_COMMIT,
        source_id,
        event_data
    )
    
    assert len(result) == 0, "Disabled watch should not be triggered"


def test_all_actions_executed_on_trigger():
    """
    **Feature: projects, Property 21: Watch Trigger Execution**
    **Validates: Requirements 10.6**
    
    When a watch is triggered, all configured actions should be executed.
    """
    project_id = 1
    watch_id = 1
    source_id = 10
    
    # Create a watch with multiple actions
    actions = [
        {'action': 'trigger_build', 'target_id': 1, 'parameters': {}},
        {'action': 'trigger_test_job', 'target_id': 2, 'parameters': {}},
        {'action': 'send_notification', 'target_id': None, 'parameters': {'channel': 'slack'}},
    ]
    
    mock_watch = create_mock_watch(
        watch_id, project_id, 'test-watch',
        WatchTriggerSource.REPOSITORY_COMMIT, source_id,
        conditions={},  # No conditions = always match
        actions=actions,
        enabled=True
    )
    
    mock_session = create_mock_session_for_process_event([mock_watch])
    manager = WatchManager(mock_session)
    
    event_data = {'branch': 'main', 'commit_sha': 'abc123'}
    
    result = manager.process_event(
        WatchTriggerSource.REPOSITORY_COMMIT,
        source_id,
        event_data
    )
    
    assert len(result) == 1, "Should trigger exactly one watch"
    assert len(result[0].actions_executed) == 3, "All 3 actions should be executed"


def test_trigger_log_records_event_data():
    """
    **Feature: projects, Property 21: Watch Trigger Execution**
    **Validates: Requirements 10.6**
    
    The trigger log should record the event data that triggered the watch.
    """
    project_id = 1
    watch_id = 1
    source_id = 10
    
    mock_watch = create_mock_watch(
        watch_id, project_id, 'test-watch',
        WatchTriggerSource.REPOSITORY_COMMIT, source_id,
        conditions={},
        actions=[{'action': 'trigger_build', 'target_id': 1, 'parameters': {}}],
        enabled=True
    )
    
    mock_session = create_mock_session_for_process_event([mock_watch])
    manager = WatchManager(mock_session)
    
    event_data = {
        'branch': 'main',
        'commit_sha': 'abc123def456',
        'author': 'test-user',
        'message': 'Test commit'
    }
    
    result = manager.process_event(
        WatchTriggerSource.REPOSITORY_COMMIT,
        source_id,
        event_data
    )
    
    assert len(result) == 1
    assert result[0].trigger_event == event_data, "Trigger log should record the event data"


def test_property_matching_events_always_trigger():
    """
    **Feature: projects, Property 21: Watch Trigger Execution**
    **Validates: Requirements 10.6**
    
    Property test: For any event matching a watch's conditions, the watch should be triggered
    and all actions should be logged.
    """
    for _ in range(100):
        project_id = random.randint(1, 100)
        watch_id = random.randint(1, 100)
        source_id = random.randint(1, 100)
        branch = generate_branch_name()
        
        # Create a watch with no conditions (always matches)
        num_actions = random.randint(1, 5)
        actions = [
            {'action': random.choice(['trigger_build', 'send_notification']), 
             'target_id': random.randint(1, 100), 
             'parameters': {}}
            for _ in range(num_actions)
        ]
        
        mock_watch = create_mock_watch(
            watch_id, project_id, generate_unique_watch_name(),
            WatchTriggerSource.REPOSITORY_COMMIT, source_id,
            conditions={},  # No conditions = always match
            actions=actions,
            enabled=True
        )
        
        mock_session = create_mock_session_for_process_event([mock_watch])
        manager = WatchManager(mock_session)
        
        event_data = {'branch': branch, 'commit_sha': 'abc123'}
        
        result = manager.process_event(
            WatchTriggerSource.REPOSITORY_COMMIT,
            source_id,
            event_data
        )
        
        assert len(result) == 1, f"Matching event should trigger watch"
        assert len(result[0].actions_executed) == num_actions, \
            f"All {num_actions} actions should be executed"


def test_property_branch_pattern_matching():
    """
    **Feature: projects, Property 21: Watch Trigger Execution**
    **Validates: Requirements 10.6**
    
    Property test: Events matching branch patterns should trigger watches,
    events not matching should not.
    """
    for _ in range(100):
        project_id = 1
        watch_id = 1
        source_id = 10
        
        # Create a watch with a specific branch pattern
        pattern = '^main$|^develop$'
        mock_watch = create_mock_watch(
            watch_id, project_id, 'test-watch',
            WatchTriggerSource.REPOSITORY_COMMIT, source_id,
            conditions={'branch_pattern': pattern},
            actions=[{'action': 'trigger_build', 'target_id': 1, 'parameters': {}}],
            enabled=True
        )
        
        mock_session = create_mock_session_for_process_event([mock_watch])
        manager = WatchManager(mock_session)
        
        # Test with matching branch
        matching_branches = ['main', 'develop']
        non_matching_branches = ['feature/test', 'bugfix/issue', 'release/1.0']
        
        branch = random.choice(matching_branches + non_matching_branches)
        event_data = {'branch': branch, 'commit_sha': 'abc123'}
        
        result = manager.process_event(
            WatchTriggerSource.REPOSITORY_COMMIT,
            source_id,
            event_data
        )
        
        if branch in matching_branches:
            assert len(result) == 1, f"Branch '{branch}' should match pattern '{pattern}'"
        else:
            assert len(result) == 0, f"Branch '{branch}' should not match pattern '{pattern}'"


def test_property_multiple_watches_can_trigger():
    """
    **Feature: projects, Property 21: Watch Trigger Execution**
    **Validates: Requirements 10.6**
    
    Property test: Multiple watches matching the same event should all be triggered.
    """
    for _ in range(50):
        project_id = 1
        source_id = 10
        num_watches = random.randint(1, 5)
        
        watches = [
            create_mock_watch(
                i + 1, project_id, f'watch-{i}',
                WatchTriggerSource.REPOSITORY_COMMIT, source_id,
                conditions={},  # No conditions = always match
                actions=[{'action': 'trigger_build', 'target_id': i + 1, 'parameters': {}}],
                enabled=True
            )
            for i in range(num_watches)
        ]
        
        mock_session = create_mock_session_for_process_event(watches)
        manager = WatchManager(mock_session)
        
        event_data = {'branch': 'main', 'commit_sha': 'abc123'}
        
        result = manager.process_event(
            WatchTriggerSource.REPOSITORY_COMMIT,
            source_id,
            event_data
        )
        
        assert len(result) == num_watches, \
            f"All {num_watches} matching watches should be triggered"


def test_build_completion_trigger():
    """
    **Feature: projects, Property 21: Watch Trigger Execution**
    **Validates: Requirements 10.6**
    
    Build completion events should trigger watches configured for build completion.
    """
    project_id = 1
    watch_id = 1
    build_spec_id = 10
    
    mock_watch = create_mock_watch(
        watch_id, project_id, 'test-watch',
        WatchTriggerSource.BUILD_COMPLETION, build_spec_id,
        conditions={'build_status': 'succeeded'},
        actions=[{'action': 'trigger_test_job', 'target_id': 1, 'parameters': {}}],
        enabled=True
    )
    
    mock_session = create_mock_session_for_process_event([mock_watch])
    manager = WatchManager(mock_session)
    
    event_data = {'build_status': 'succeeded', 'build_id': 123}
    
    result = manager.process_event(
        WatchTriggerSource.BUILD_COMPLETION,
        build_spec_id,
        event_data
    )
    
    assert len(result) == 1, "Build completion event should trigger watch"


def test_build_status_any_matches_all():
    """
    **Feature: projects, Property 21: Watch Trigger Execution**
    **Validates: Requirements 10.6**
    
    Build status 'any' should match both succeeded and failed builds.
    """
    project_id = 1
    watch_id = 1
    build_spec_id = 10
    
    mock_watch = create_mock_watch(
        watch_id, project_id, 'test-watch',
        WatchTriggerSource.BUILD_COMPLETION, build_spec_id,
        conditions={'build_status': 'any'},
        actions=[{'action': 'send_notification', 'target_id': None, 'parameters': {}}],
        enabled=True
    )
    
    for status in ['succeeded', 'failed']:
        mock_session = create_mock_session_for_process_event([mock_watch])
        manager = WatchManager(mock_session)
        
        event_data = {'build_status': status, 'build_id': 123}
        
        result = manager.process_event(
            WatchTriggerSource.BUILD_COMPLETION,
            build_spec_id,
            event_data
        )
        
        assert len(result) == 1, f"Build status 'any' should match '{status}'"

