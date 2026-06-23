"""
.. module:: test_test_manager_spec_crud
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for TestManager specification CRUD operations

.. moduleauthor:: Code Craft AI LLC

Tests for test specification CRUD operations in the TestManager.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.test_manager import (
    TestManager,
    TestSpecCreateRequest,
    TestSpecUpdateRequest,
    TestFramework,
    TestResultFormat,
    TestSpecValidationError,
    TestSpecNotFoundError,
    DuplicateTestSpecError,
    TestSpecHasActiveJobsError,
    ProjectNotFoundError,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_spec_name():
    """Generate a unique test specification name for testing."""
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


def create_mock_test_spec(spec_id, project_id, name, version=1, framework='pytest'):
    """Create a mock test specification object matching the ProjectTestSpec ORM model."""
    mock_spec = Mock()
    mock_spec.configure(recursive=True)
    ctx = mock_spec.mock_context()
    ctx.set_attribute('id', spec_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('framework', framework)
    ctx.set_attribute('test_command', 'pytest tests/')
    ctx.set_attribute('test_selection', '')
    ctx.set_attribute('build_ref', None)
    ctx.set_attribute('infra_ref', None)
    ctx.set_attribute('environment_json', {})
    ctx.set_attribute('timeout_minutes', 60)
    ctx.set_attribute('result_format', 'junit_xml')
    ctx.set_attribute('description', '')
    ctx.set_attribute('version', version)
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('updated_at', Mock())
    return mock_spec


def create_mock_session_for_spec_create(project=None, existing_spec=None):
    """
    Create a mock session for create_spec operation.
    
    Query flow for create_spec:
    1. Query Project to verify project exists
    2. Query ProjectTestSpec to check for duplicate name
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    created_spec = [None]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # First call: check project exists
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=project)
        # Second call: check for duplicate name
        elif call_count[0] == 2:
            mock_filter.mock_context().mock_method('first', return_value=existing_spec)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    def add_side_effect(obj):
        created_spec[0] = obj
        obj.id = 1
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add', side_effect=add_side_effect)
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session, created_spec


def create_mock_session_for_spec_update(existing_spec):
    """
    Create a mock session for update_spec operation.
    
    Query flow for update_spec:
    1. Query ProjectTestSpec to find the spec
    2. (Optional) Query ProjectTestSpec to check for duplicate name
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
        
        # First call: find the spec to update
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=existing_spec)
        # Subsequent calls: return None (no duplicate, etc.)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Test Specification CRUD Tests
# =============================================================================

def test_create_spec_with_valid_data():
    """
    Test that creating a test specification with valid data succeeds.
    
    **Validates: Requirements 8.1**
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    
    mock_project = create_mock_project(project_id)
    mock_session, created_spec = create_mock_session_for_spec_create(project=mock_project)
    
    manager = TestManager(mock_session)
    
    request = TestSpecCreateRequest(
        name=spec_name,
        framework=TestFramework.PYTEST,
        test_command='pytest tests/',
        test_selection='',
        environment={},
        timeout_minutes=60,
        result_format=TestResultFormat.JUNIT_XML,
        description='Test specification'
    )
    
    try:
        manager.create_spec(project_id, request, 'user-1')
    except AttributeError:
        # Expected due to mock limitations with ORM relationships
        pass
    
    # Verify spec was created with correct values
    assert created_spec[0] is not None, "Spec should have been created"
    assert created_spec[0].name == spec_name, f"Name should be {spec_name}"
    assert created_spec[0].framework == 'pytest', "Framework should be pytest"
    assert created_spec[0].version == 1, "Initial version should be 1"


def test_create_spec_rejects_invalid_name():
    """
    Test that creating a test specification with invalid name fails.
    
    **Validates: Requirements 8.1**
    """
    project_id = 1
    
    mock_project = create_mock_project(project_id)
    mock_session, _ = create_mock_session_for_spec_create(project=mock_project)
    
    manager = TestManager(mock_session)
    
    # Test with invalid names
    invalid_names = [
        '',  # Empty
        ' ',  # Whitespace only
        '_invalid',  # Starts with underscore
        '-invalid',  # Starts with hyphen
        '.invalid',  # Starts with period
        'a' * 200,  # Too long
    ]
    
    for invalid_name in invalid_names:
        request = TestSpecCreateRequest(
            name=invalid_name,
            framework=TestFramework.PYTEST,
            test_command='pytest tests/',
        )
        
        try:
            manager.create_spec(project_id, request, 'user-1')
            assert False, f"Should have raised TestSpecValidationError for name '{invalid_name}'"
        except TestSpecValidationError as e:
            assert e.field == 'name', f"Error should be for 'name' field, got '{e.field}'"


def test_create_spec_rejects_empty_test_command():
    """
    Test that creating a test specification with empty test command fails.
    
    **Validates: Requirements 8.1**
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    
    mock_project = create_mock_project(project_id)
    mock_session, _ = create_mock_session_for_spec_create(project=mock_project)
    
    manager = TestManager(mock_session)
    
    request = TestSpecCreateRequest(
        name=spec_name,
        framework=TestFramework.PYTEST,
        test_command='',  # Empty command
    )
    
    try:
        manager.create_spec(project_id, request, 'user-1')
        assert False, "Should have raised TestSpecValidationError for empty test_command"
    except TestSpecValidationError as e:
        assert e.field == 'test_command', f"Error should be for 'test_command' field, got '{e.field}'"


def test_create_spec_rejects_invalid_framework():
    """
    Test that creating a test specification with invalid framework fails.
    
    **Validates: Requirements 8.4**
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    
    mock_project = create_mock_project(project_id)
    mock_session, _ = create_mock_session_for_spec_create(project=mock_project)
    
    manager = TestManager(mock_session)
    
    request = TestSpecCreateRequest(
        name=spec_name,
        framework='invalid_framework',  # Invalid framework
        test_command='pytest tests/',
    )
    
    try:
        manager.create_spec(project_id, request, 'user-1')
        assert False, "Should have raised TestSpecValidationError for invalid framework"
    except TestSpecValidationError as e:
        assert e.field == 'framework', f"Error should be for 'framework' field, got '{e.field}'"


def test_create_spec_rejects_duplicate_name():
    """
    Test that creating a test specification with duplicate name fails.
    
    **Validates: Requirements 8.1**
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    
    mock_project = create_mock_project(project_id)
    existing_spec = create_mock_test_spec(1, project_id, spec_name)
    mock_session, _ = create_mock_session_for_spec_create(project=mock_project, existing_spec=existing_spec)
    
    manager = TestManager(mock_session)
    
    request = TestSpecCreateRequest(
        name=spec_name,
        framework=TestFramework.PYTEST,
        test_command='pytest tests/',
    )
    
    try:
        manager.create_spec(project_id, request, 'user-1')
        assert False, "Should have raised DuplicateTestSpecError"
    except DuplicateTestSpecError as e:
        assert e.field == 'name', f"Error should be for 'name' field, got '{e.field}'"


def test_create_spec_rejects_nonexistent_project():
    """
    Test that creating a test specification for nonexistent project fails.
    
    **Validates: Requirements 8.1**
    """
    spec_name = generate_unique_spec_name()
    project_id = 999
    
    mock_session, _ = create_mock_session_for_spec_create(project=None)
    
    manager = TestManager(mock_session)
    
    request = TestSpecCreateRequest(
        name=spec_name,
        framework=TestFramework.PYTEST,
        test_command='pytest tests/',
    )
    
    try:
        manager.create_spec(project_id, request, 'user-1')
        assert False, "Should have raised ProjectNotFoundError"
    except ProjectNotFoundError:
        pass  # Expected


def test_update_spec_increments_version():
    """
    Test that updating a test specification increments the version.
    
    **Validates: Requirements 8.2**
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    initial_version = 1
    
    existing_spec = create_mock_test_spec(spec_id, project_id, spec_name, version=initial_version)
    mock_session = create_mock_session_for_spec_update(existing_spec)
    
    manager = TestManager(mock_session)
    
    request = TestSpecUpdateRequest(
        description='Updated description'
    )
    
    result = manager.update_spec(spec_id, request, 'user-1')
    
    assert result.version == initial_version + 1, \
        f"Version should be {initial_version + 1}, got {result.version}"


def test_update_spec_not_found():
    """
    Test that updating a nonexistent test specification fails.
    
    **Validates: Requirements 8.2**
    """
    spec_id = 999
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=None)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = TestManager(mock_session)
    
    request = TestSpecUpdateRequest(
        description='Updated description'
    )
    
    try:
        manager.update_spec(spec_id, request, 'user-1')
        assert False, "Should have raised TestSpecNotFoundError"
    except TestSpecNotFoundError:
        pass  # Expected


def test_get_spec_returns_spec():
    """
    Test that getting a test specification returns the spec.
    
    **Validates: Requirements 8.1**
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    version = 5
    
    existing_spec = create_mock_test_spec(spec_id, project_id, spec_name, version=version)
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=existing_spec)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = TestManager(mock_session)
    
    result = manager.get_spec(spec_id)
    
    assert result is not None, "Should return spec"
    assert result.id == spec_id, f"ID should be {spec_id}"
    assert result.name == spec_name, f"Name should be {spec_name}"
    assert result.version == version, f"Version should be {version}"


def test_get_spec_returns_none_for_nonexistent():
    """
    Test that getting a nonexistent test specification returns None.
    
    **Validates: Requirements 8.1**
    """
    spec_id = 999
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=None)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = TestManager(mock_session)
    
    result = manager.get_spec(spec_id)
    
    assert result is None, "Should return None for nonexistent spec"


def test_validate_spec_returns_errors_for_invalid_spec():
    """
    Test that validate_spec returns errors for invalid specification.
    
    **Validates: Requirements 8.5**
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    manager = TestManager(mock_session)
    
    # Create invalid spec
    request = TestSpecCreateRequest(
        name='',  # Invalid name
        framework='invalid',  # Invalid framework
        test_command='',  # Invalid command
        timeout_minutes=-1,  # Invalid timeout
    )
    
    errors = manager.validate_spec(request)
    
    assert len(errors) > 0, "Should return errors for invalid spec"
    assert any('name' in e.lower() for e in errors), "Should have name error"
    assert any('framework' in e.lower() for e in errors), "Should have framework error"
    assert any('command' in e.lower() for e in errors), "Should have command error"
    assert any('timeout' in e.lower() for e in errors), "Should have timeout error"


def test_validate_spec_returns_empty_for_valid_spec():
    """
    Test that validate_spec returns empty list for valid specification.
    
    **Validates: Requirements 8.5**
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    manager = TestManager(mock_session)
    
    # Create valid spec
    request = TestSpecCreateRequest(
        name=generate_unique_spec_name(),
        framework=TestFramework.PYTEST,
        test_command='pytest tests/',
        timeout_minutes=60,
    )
    
    errors = manager.validate_spec(request)
    
    assert len(errors) == 0, f"Should return no errors for valid spec, got: {errors}"


def test_supported_frameworks():
    """
    Test that all supported frameworks are accepted.
    
    **Validates: Requirements 8.4**
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    manager = TestManager(mock_session)
    
    supported_frameworks = [
        TestFramework.PYTEST,
        TestFramework.UNITTEST,
        TestFramework.TESTBASE,
        TestFramework.CUSTOM,
    ]
    
    for framework in supported_frameworks:
        request = TestSpecCreateRequest(
            name=generate_unique_spec_name(),
            framework=framework,
            test_command='test command',
        )
        
        errors = manager.validate_spec(request)
        
        framework_errors = [e for e in errors if 'framework' in e.lower()]
        assert len(framework_errors) == 0, \
            f"Framework {framework} should be valid, got errors: {framework_errors}"


def test_supported_result_formats():
    """
    Test that all supported result formats are accepted.
    
    **Validates: Requirements 9.5**
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    manager = TestManager(mock_session)
    
    supported_formats = [
        TestResultFormat.JUNIT_XML,
        TestResultFormat.TAP,
        TestResultFormat.JSON,
    ]
    
    for result_format in supported_formats:
        request = TestSpecCreateRequest(
            name=generate_unique_spec_name(),
            framework=TestFramework.PYTEST,
            test_command='test command',
            result_format=result_format,
        )
        
        errors = manager.validate_spec(request)
        
        format_errors = [e for e in errors if 'result' in e.lower() and 'format' in e.lower()]
        assert len(format_errors) == 0, \
            f"Result format {result_format} should be valid, got errors: {format_errors}"
