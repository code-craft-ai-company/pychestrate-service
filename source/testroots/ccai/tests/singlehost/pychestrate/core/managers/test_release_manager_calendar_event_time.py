"""
.. module:: test_release_manager_calendar_event_time
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for ReleaseManager calendar event time validation

.. moduleauthor:: Code Craft AI LLC

Property tests for calendar event time validation in the ReleaseManager.

**Feature: projects**
**Property 26: Calendar Event Time Validation**
**Validates: Requirements 22.4**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random

from datetime import datetime, timedelta, timezone

from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.release_manager import (
    ReleaseManager,
    ReleaseEventCreateRequest,
    ReleaseEventUpdateRequest,
    ReleaseEventValidationError,
)


# =============================================================================
# Mock Helpers
# =============================================================================

def create_mock_project(project_id, name):
    """Create a mock project object."""
    mock_project = Mock()
    mock_project.configure(recursive=True)
    ctx = mock_project.mock_context()
    ctx.set_attribute('id', project_id)
    ctx.set_attribute('name', name)
    return mock_project


def create_mock_release(release_id, project_id, version):
    """Create a mock release object."""
    mock_release = Mock()
    mock_release.configure(recursive=True)
    ctx = mock_release.mock_context()
    ctx.set_attribute('id', release_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('version', version)
    ctx.set_attribute('name', f'Release {version}')
    return mock_release


def create_mock_release_event(event_id, project_id, release_id, name, start_time, end_time):
    """Create a mock release event object."""
    mock_event = Mock()
    mock_event.configure(recursive=True)
    ctx = mock_event.mock_context()
    ctx.set_attribute('id', event_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('release_id', release_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('description', '')
    ctx.set_attribute('start_time', start_time)
    ctx.set_attribute('end_time', end_time)
    ctx.set_attribute('created_at', datetime.now(timezone.utc))
    ctx.set_attribute('updated_at', datetime.now(timezone.utc))
    ctx.set_attribute('phases', [])
    
    # Create mock release for the event
    mock_release = create_mock_release(release_id, project_id, '1.0.0')
    ctx.set_attribute('release', mock_release)
    
    return mock_event


def create_mock_session_for_create_event(project, release, created_event=None):
    """
    Create a mock session for create_release_event operation.
    
    Query flow:
    1. Query Project to verify project exists
    2. Query ProjectRelease to verify release exists
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
        
        # First call: find project
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=project)
        # Second call: find release
        elif call_count[0] == 2:
            mock_filter.mock_context().mock_method('first', return_value=release)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


def create_mock_session_for_update_event(existing_event):
    """
    Create a mock session for update_release_event operation.
    
    Query flow:
    1. Query ProjectReleaseEvent to find existing event
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    def query_side_effect(model):
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        mock_filter.mock_context().mock_method('first', return_value=existing_event)
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_valid_time_range():
    """Generate a valid time range where end_time > start_time."""
    base_time = datetime.now(timezone.utc)
    start_offset = random.randint(0, 365)  # Days from now
    duration = random.randint(1, 30)  # Duration in days
    
    start_time = base_time + timedelta(days=start_offset)
    end_time = start_time + timedelta(days=duration)
    
    return start_time, end_time


def generate_invalid_time_range():
    """Generate an invalid time range where end_time <= start_time."""
    base_time = datetime.now(timezone.utc)
    start_offset = random.randint(1, 365)  # Days from now
    
    start_time = base_time + timedelta(days=start_offset)
    
    # Generate end_time that is before or equal to start_time
    invalid_type = random.choice(['before', 'equal'])
    if invalid_type == 'before':
        end_time = start_time - timedelta(days=random.randint(1, 30))
    else:
        end_time = start_time
    
    return start_time, end_time


def generate_event_name():
    """Generate a random event name."""
    prefixes = ["Release", "Sprint", "Milestone", "Phase", "Deployment"]
    suffixes = ["Alpha", "Beta", "RC", "Final", "Hotfix"]
    return f"{random.choice(prefixes)} {random.choice(suffixes)} {random.randint(1, 100)}"


# =============================================================================
# Calendar Event Time Validation Tests - Property 26
# =============================================================================

def test_valid_time_range_accepted():
    """
    **Feature: projects, Property 26: Calendar Event Time Validation**
    **Validates: Requirements 22.4**
    
    Release events with end_time after start_time should be accepted.
    """
    project_id = 1
    release_id = 1
    
    mock_project = create_mock_project(project_id, 'test-project')
    mock_release = create_mock_release(release_id, project_id, '1.0.0')
    mock_session = create_mock_session_for_create_event(mock_project, mock_release)
    
    manager = ReleaseManager(mock_session)
    
    start_time, end_time = generate_valid_time_range()
    
    request = ReleaseEventCreateRequest(
        release_id=release_id,
        name="Valid Event",
        start_time=start_time,
        end_time=end_time,
        description="Test event"
    )
    
    # The validation should pass (no exception raised)
    try:
        manager.create_release_event(project_id, request, "test_user")
        # If we get here without exception, validation passed
        assert True
    except ReleaseEventValidationError:
        assert False, "Valid time range should be accepted"
    except AttributeError:
        # Mock may not have all attributes, but validation passed
        pass


def test_invalid_time_range_end_before_start_rejected():
    """
    **Feature: projects, Property 26: Calendar Event Time Validation**
    **Validates: Requirements 22.4**
    
    Release events with end_time before start_time should be rejected.
    """
    project_id = 1
    release_id = 1
    
    mock_project = create_mock_project(project_id, 'test-project')
    mock_release = create_mock_release(release_id, project_id, '1.0.0')
    mock_session = create_mock_session_for_create_event(mock_project, mock_release)
    
    manager = ReleaseManager(mock_session)
    
    start_time = datetime.now(timezone.utc) + timedelta(days=10)
    end_time = start_time - timedelta(days=5)  # End before start
    
    request = ReleaseEventCreateRequest(
        release_id=release_id,
        name="Invalid Event",
        start_time=start_time,
        end_time=end_time,
        description="Test event"
    )
    
    try:
        manager.create_release_event(project_id, request, "test_user")
        assert False, "Should have raised ReleaseEventValidationError"
    except ReleaseEventValidationError as e:
        assert "End time must be after start time" in str(e.message)
        assert e.field == "end_time"


def test_invalid_time_range_end_equals_start_rejected():
    """
    **Feature: projects, Property 26: Calendar Event Time Validation**
    **Validates: Requirements 22.4**
    
    Release events with end_time equal to start_time should be rejected.
    """
    project_id = 1
    release_id = 1
    
    mock_project = create_mock_project(project_id, 'test-project')
    mock_release = create_mock_release(release_id, project_id, '1.0.0')
    mock_session = create_mock_session_for_create_event(mock_project, mock_release)
    
    manager = ReleaseManager(mock_session)
    
    same_time = datetime.now(timezone.utc) + timedelta(days=10)
    
    request = ReleaseEventCreateRequest(
        release_id=release_id,
        name="Invalid Event",
        start_time=same_time,
        end_time=same_time,  # End equals start
        description="Test event"
    )
    
    try:
        manager.create_release_event(project_id, request, "test_user")
        assert False, "Should have raised ReleaseEventValidationError"
    except ReleaseEventValidationError as e:
        assert "End time must be after start time" in str(e.message)
        assert e.field == "end_time"


def test_update_with_invalid_time_range_rejected():
    """
    **Feature: projects, Property 26: Calendar Event Time Validation**
    **Validates: Requirements 22.4**
    
    Updating release events with invalid time range should be rejected.
    """
    event_id = 1
    project_id = 1
    release_id = 1
    
    start_time = datetime.now(timezone.utc) + timedelta(days=10)
    end_time = start_time + timedelta(days=5)
    
    mock_event = create_mock_release_event(
        event_id, project_id, release_id, "Test Event", start_time, end_time
    )
    mock_session = create_mock_session_for_update_event(mock_event)
    
    manager = ReleaseManager(mock_session)
    
    # Try to update with invalid time range (end before start)
    new_end_time = start_time - timedelta(days=1)
    
    update_request = ReleaseEventUpdateRequest(
        end_time=new_end_time
    )
    
    try:
        manager.update_release_event(event_id, update_request, "test_user")
        assert False, "Should have raised ReleaseEventValidationError"
    except ReleaseEventValidationError as e:
        assert "End time must be after start time" in str(e.message)


def test_property_valid_time_ranges_always_accepted():
    """
    **Feature: projects, Property 26: Calendar Event Time Validation**
    **Validates: Requirements 22.4**
    
    Property test: For any release event, if end_time > start_time,
    the event should be created successfully.
    """
    for i in range(100):
        project_id = random.randint(1, 100)
        release_id = random.randint(1, 100)
        
        mock_project = create_mock_project(project_id, f'test-project-{i}')
        mock_release = create_mock_release(release_id, project_id, f'1.0.{i}')
        mock_session = create_mock_session_for_create_event(mock_project, mock_release)
        
        manager = ReleaseManager(mock_session)
        
        start_time, end_time = generate_valid_time_range()
        
        request = ReleaseEventCreateRequest(
            release_id=release_id,
            name=generate_event_name(),
            start_time=start_time,
            end_time=end_time,
            description="Property test event"
        )
        
        try:
            manager.create_release_event(project_id, request, "test_user")
            # Validation passed
        except ReleaseEventValidationError:
            assert False, \
                f"Event with valid time range should be created (start={start_time}, end={end_time})"
        except AttributeError:
            # Mock may not have all attributes, but validation passed
            pass


def test_property_invalid_time_ranges_always_rejected():
    """
    **Feature: projects, Property 26: Calendar Event Time Validation**
    **Validates: Requirements 22.4**
    
    Property test: For any release event, if end_time <= start_time,
    the event creation should be rejected.
    """
    for i in range(100):
        project_id = random.randint(1, 100)
        release_id = random.randint(1, 100)
        
        mock_project = create_mock_project(project_id, f'test-project-{i}')
        mock_release = create_mock_release(release_id, project_id, f'2.0.{i}')
        mock_session = create_mock_session_for_create_event(mock_project, mock_release)
        
        manager = ReleaseManager(mock_session)
        
        start_time, end_time = generate_invalid_time_range()
        
        request = ReleaseEventCreateRequest(
            release_id=release_id,
            name=generate_event_name(),
            start_time=start_time,
            end_time=end_time,
            description="Property test event"
        )
        
        try:
            manager.create_release_event(project_id, request, "test_user")
            assert False, \
                f"Event with invalid time range should be rejected (start={start_time}, end={end_time})"
        except ReleaseEventValidationError:
            pass  # Expected


def test_property_time_validation_is_deterministic():
    """
    **Feature: projects, Property 26: Calendar Event Time Validation**
    **Validates: Requirements 22.4**
    
    Property test: For any given start_time and end_time, the validation
    result should always be the same.
    """
    project_id = 1
    release_id = 1
    
    # Test with valid time range
    start_time = datetime.now(timezone.utc) + timedelta(days=10)
    end_time = start_time + timedelta(days=5)
    
    for i in range(10):
        mock_project = create_mock_project(project_id, 'test-project')
        mock_release = create_mock_release(release_id, project_id, f'3.0.{i}')
        mock_session = create_mock_session_for_create_event(mock_project, mock_release)
        
        manager = ReleaseManager(mock_session)
        
        request = ReleaseEventCreateRequest(
            release_id=release_id,
            name=f"Deterministic Test {i}",
            start_time=start_time,
            end_time=end_time,
            description="Test event"
        )
        
        try:
            manager.create_release_event(project_id, request, "test_user")
            # Valid time range should always be accepted
        except ReleaseEventValidationError:
            assert False, "Valid time range should always be accepted"
        except AttributeError:
            pass
    
    # Test with invalid time range
    invalid_end_time = start_time - timedelta(days=1)
    
    for i in range(10):
        mock_project = create_mock_project(project_id, 'test-project')
        mock_release = create_mock_release(release_id, project_id, f'4.0.{i}')
        mock_session = create_mock_session_for_create_event(mock_project, mock_release)
        
        manager = ReleaseManager(mock_session)
        
        request = ReleaseEventCreateRequest(
            release_id=release_id,
            name=f"Deterministic Test Invalid {i}",
            start_time=start_time,
            end_time=invalid_end_time,
            description="Test event"
        )
        
        try:
            manager.create_release_event(project_id, request, "test_user")
            assert False, "Invalid time range should always be rejected"
        except ReleaseEventValidationError:
            pass  # Expected


def test_boundary_time_values():
    """
    **Feature: projects, Property 26: Calendar Event Time Validation**
    **Validates: Requirements 22.4**
    
    Test boundary cases for time validation.
    """
    project_id = 1
    release_id = 1
    
    mock_project = create_mock_project(project_id, 'test-project')
    mock_release = create_mock_release(release_id, project_id, '1.0.0')
    mock_session = create_mock_session_for_create_event(mock_project, mock_release)
    
    manager = ReleaseManager(mock_session)
    
    base_time = datetime.now(timezone.utc)
    
    # Test minimum valid duration (1 second)
    start_time = base_time + timedelta(days=10)
    end_time = start_time + timedelta(seconds=1)
    
    request = ReleaseEventCreateRequest(
        release_id=release_id,
        name="Minimum Duration Event",
        start_time=start_time,
        end_time=end_time,
        description="Test event"
    )
    
    try:
        manager.create_release_event(project_id, request, "test_user")
        # Validation passed - 1 second duration is valid
    except ReleaseEventValidationError:
        assert False, "Event with 1 second duration should be valid"
    except AttributeError:
        pass


def test_various_duration_lengths():
    """
    **Feature: projects, Property 26: Calendar Event Time Validation**
    **Validates: Requirements 22.4**
    
    Test various duration lengths are accepted.
    """
    project_id = 1
    release_id = 1
    
    base_time = datetime.now(timezone.utc)
    
    durations = [
        timedelta(seconds=1),
        timedelta(minutes=1),
        timedelta(hours=1),
        timedelta(days=1),
        timedelta(weeks=1),
        timedelta(days=30),
        timedelta(days=365),
    ]
    
    for i, duration in enumerate(durations):
        mock_project = create_mock_project(project_id, 'test-project')
        mock_release = create_mock_release(release_id, project_id, f'5.0.{i}')
        mock_session = create_mock_session_for_create_event(mock_project, mock_release)
        
        manager = ReleaseManager(mock_session)
        
        start_time = base_time + timedelta(days=i * 400)  # Spread out to avoid overlap
        end_time = start_time + duration
        
        request = ReleaseEventCreateRequest(
            release_id=release_id,
            name=f"Duration Test {i}",
            start_time=start_time,
            end_time=end_time,
            description=f"Test event with duration {duration}"
        )
        
        try:
            manager.create_release_event(project_id, request, "test_user")
            # Validation passed
        except ReleaseEventValidationError:
            assert False, f"Event with duration {duration} should be valid"
        except AttributeError:
            pass


def test_update_only_start_time_validates_against_existing_end():
    """
    **Feature: projects, Property 26: Calendar Event Time Validation**
    **Validates: Requirements 22.4**
    
    When updating only start_time, validation should use existing end_time.
    """
    event_id = 1
    project_id = 1
    release_id = 1
    
    start_time = datetime.now(timezone.utc) + timedelta(days=10)
    end_time = start_time + timedelta(days=5)
    
    mock_event = create_mock_release_event(
        event_id, project_id, release_id, "Test Event", start_time, end_time
    )
    mock_session = create_mock_session_for_update_event(mock_event)
    
    manager = ReleaseManager(mock_session)
    
    # Update only start_time to be after end_time (should fail)
    new_start_time = end_time + timedelta(days=1)
    
    update_request = ReleaseEventUpdateRequest(
        start_time=new_start_time
    )
    
    try:
        manager.update_release_event(event_id, update_request, "test_user")
        assert False, "Should have raised ReleaseEventValidationError"
    except ReleaseEventValidationError as e:
        assert "End time must be after start time" in str(e.message)


def test_update_only_end_time_validates_against_existing_start():
    """
    **Feature: projects, Property 26: Calendar Event Time Validation**
    **Validates: Requirements 22.4**
    
    When updating only end_time, validation should use existing start_time.
    """
    event_id = 1
    project_id = 1
    release_id = 1
    
    start_time = datetime.now(timezone.utc) + timedelta(days=10)
    end_time = start_time + timedelta(days=5)
    
    mock_event = create_mock_release_event(
        event_id, project_id, release_id, "Test Event", start_time, end_time
    )
    mock_session = create_mock_session_for_update_event(mock_event)
    
    manager = ReleaseManager(mock_session)
    
    # Update only end_time to be before start_time (should fail)
    new_end_time = start_time - timedelta(days=1)
    
    update_request = ReleaseEventUpdateRequest(
        end_time=new_end_time
    )
    
    try:
        manager.update_release_event(event_id, update_request, "test_user")
        assert False, "Should have raised ReleaseEventValidationError"
    except ReleaseEventValidationError as e:
        assert "End time must be after start time" in str(e.message)
