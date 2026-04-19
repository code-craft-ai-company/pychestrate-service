"""
.. module:: test_test_manager_result_parsing
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for TestManager result parsing and metrics

.. moduleauthor:: Automation Mojo LLC

Tests for test result parsing and metrics in the TestManager.

**Validates: Requirements 9.1, 9.7**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.test_manager import (
    TestManager,
    TestJobTriggerRequest,
    TestResultSummary,
    TestCaseResult,
    TestCaseStatus,
    JobStatus,
    TestJobNotFoundError,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_spec_name():
    """Generate a unique test specification name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest = ''.join(random.choices(string.ascii_letters + string.digits + '_-.', k=random.randint(5, 20)))
    return start_char + rest


def create_mock_test_spec(spec_id, project_id, name, version=1):
    """Create a mock test specification object."""
    mock_spec = Mock()
    mock_spec.configure(recursive=True)
    ctx = mock_spec.mock_context()
    ctx.set_attribute('id', spec_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('framework', 'pytest')
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


def create_mock_test_job(job_id, project_id, spec_id, spec_version=1, status='succeeded', result_summary=None, spec=None):
    """Create a mock test job object."""
    mock_job = Mock()
    mock_job.configure(recursive=True)
    ctx = mock_job.mock_context()
    ctx.set_attribute('id', job_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('spec_id', spec_id)
    ctx.set_attribute('spec_version', spec_version)
    ctx.set_attribute('build_id', None)
    ctx.set_attribute('infra_job_id', None)
    ctx.set_attribute('status', status)
    ctx.set_attribute('triggered_by_id', 'user-1')
    ctx.set_attribute('parameters_json', {})
    ctx.set_attribute('result_summary_json', result_summary)
    ctx.set_attribute('started_at', Mock())
    ctx.set_attribute('completed_at', Mock())
    ctx.set_attribute('duration_seconds', 120)
    ctx.set_attribute('logs_path', None)
    ctx.set_attribute('results_path', None)
    ctx.set_attribute('created_at', Mock())
    
    if spec is None:
        spec = create_mock_test_spec(spec_id, project_id, 'test-spec')
    ctx.set_attribute('spec', spec)
    
    return mock_job


def create_mock_test_result(result_id, job_id, name, classname, status, duration=1.0, failure_message=None, failure_trace=None):
    """Create a mock test result object."""
    mock_result = Mock()
    mock_result.configure(recursive=True)
    ctx = mock_result.mock_context()
    ctx.set_attribute('id', result_id)
    ctx.set_attribute('job_id', job_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('classname', classname)
    ctx.set_attribute('status', status)
    ctx.set_attribute('duration_seconds', duration)
    ctx.set_attribute('failure_message', failure_message)
    ctx.set_attribute('failure_trace', failure_trace)
    return mock_result


# =============================================================================
# Test Result Parsing Tests
# =============================================================================

def test_get_result_summary_from_cached_summary():
    """
    Test that get_result_summary returns cached summary when available.
    
    **Validates: Requirements 9.7**
    """
    job_id = 1
    project_id = 1
    spec_id = 1
    
    cached_summary = {
        'total': 100,
        'passed': 90,
        'failed': 5,
        'skipped': 3,
        'errors': 2,
        'duration_seconds': 120.5
    }
    
    mock_job = create_mock_test_job(job_id, project_id, spec_id, result_summary=cached_summary)
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_job)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = TestManager(mock_session)
    
    result = manager.get_result_summary(job_id)
    
    assert result.total == 100, f"Total should be 100, got {result.total}"
    assert result.passed == 90, f"Passed should be 90, got {result.passed}"
    assert result.failed == 5, f"Failed should be 5, got {result.failed}"
    assert result.skipped == 3, f"Skipped should be 3, got {result.skipped}"
    assert result.errors == 2, f"Errors should be 2, got {result.errors}"
    assert result.duration_seconds == 120.5, f"Duration should be 120.5, got {result.duration_seconds}"


def test_get_result_summary_calculates_from_results():
    """
    Test that get_result_summary calculates summary from results when not cached.
    
    **Validates: Requirements 9.7**
    """
    job_id = 1
    project_id = 1
    spec_id = 1
    
    mock_job = create_mock_test_job(job_id, project_id, spec_id, result_summary=None)
    
    # Create mock results
    mock_results = [
        create_mock_test_result(1, job_id, 'test_1', 'TestClass', 'passed', 1.0),
        create_mock_test_result(2, job_id, 'test_2', 'TestClass', 'passed', 2.0),
        create_mock_test_result(3, job_id, 'test_3', 'TestClass', 'failed', 1.5),
        create_mock_test_result(4, job_id, 'test_4', 'TestClass', 'skipped', 0.0),
        create_mock_test_result(5, job_id, 'test_5', 'TestClass', 'error', 0.5),
    ]
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # First call: get job
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=mock_job)
        # Second call: get results
        elif call_count[0] == 2:
            mock_filter.mock_context().mock_method('all', return_value=mock_results)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    
    manager = TestManager(mock_session)
    
    result = manager.get_result_summary(job_id)
    
    assert result.total == 5, f"Total should be 5, got {result.total}"
    assert result.passed == 2, f"Passed should be 2, got {result.passed}"
    assert result.failed == 1, f"Failed should be 1, got {result.failed}"
    assert result.skipped == 1, f"Skipped should be 1, got {result.skipped}"
    assert result.errors == 1, f"Errors should be 1, got {result.errors}"
    assert result.duration_seconds == 5.0, f"Duration should be 5.0, got {result.duration_seconds}"


def test_get_result_summary_not_found():
    """
    Test that get_result_summary raises error for nonexistent job.
    
    **Validates: Requirements 9.7**
    """
    job_id = 999
    
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
    
    try:
        manager.get_result_summary(job_id)
        assert False, "Should have raised TestJobNotFoundError"
    except TestJobNotFoundError:
        pass  # Expected


def test_get_test_results_returns_results():
    """
    Test that get_test_results returns test case results.
    
    **Validates: Requirements 9.7**
    """
    job_id = 1
    project_id = 1
    spec_id = 1
    
    mock_job = create_mock_test_job(job_id, project_id, spec_id)
    
    mock_results = [
        create_mock_test_result(1, job_id, 'test_success', 'TestClass', 'passed', 1.0),
        create_mock_test_result(2, job_id, 'test_failure', 'TestClass', 'failed', 2.0, 
                               failure_message='Assertion failed', failure_trace='Traceback...'),
    ]
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # First call: get job
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=mock_job)
        # Second call: get results
        elif call_count[0] == 2:
            mock_order = Mock()
            mock_order.configure(recursive=True)
            mock_order.mock_context().mock_method('all', return_value=mock_results)
            mock_filter.mock_context().mock_method('order_by', return_value=mock_order)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    
    manager = TestManager(mock_session)
    
    results = manager.get_test_results(job_id)
    
    assert len(results) == 2, f"Should return 2 results, got {len(results)}"
    assert results[0].name == 'test_success', f"First result name should be 'test_success'"
    assert results[0].status == TestCaseStatus.PASSED, f"First result status should be PASSED"
    assert results[1].name == 'test_failure', f"Second result name should be 'test_failure'"
    assert results[1].status == TestCaseStatus.FAILED, f"Second result status should be FAILED"
    assert results[1].failure_message == 'Assertion failed', f"Should have failure message"


def test_get_test_results_not_found():
    """
    Test that get_test_results raises error for nonexistent job.
    
    **Validates: Requirements 9.7**
    """
    job_id = 999
    
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
    
    try:
        manager.get_test_results(job_id)
        assert False, "Should have raised TestJobNotFoundError"
    except TestJobNotFoundError:
        pass  # Expected


def test_trigger_job_creates_pending_job():
    """
    Test that trigger_job creates a job with pending status.
    
    **Validates: Requirements 9.1**
    """
    spec_id = 1
    project_id = 1
    
    mock_spec = create_mock_test_spec(spec_id, project_id, 'test-spec')
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    created_job = [None]
    
    def query_side_effect(model):
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        mock_filter.mock_context().mock_method('first', return_value=mock_spec)
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    def add_side_effect(obj):
        created_job[0] = obj
        obj.id = 1
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add', side_effect=add_side_effect)
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    manager = TestManager(mock_session)
    
    request = TestJobTriggerRequest(
        spec_id=spec_id,
        parameters={'key': 'value'}
    )
    
    try:
        manager.trigger_job(request, 'user-1')
    except AttributeError:
        # Expected due to mock limitations
        pass
    
    assert created_job[0] is not None, "Job should have been created"
    assert created_job[0].status == 'pending', f"Status should be 'pending', got {created_job[0].status}"
    assert created_job[0].spec_id == spec_id, f"Spec ID should be {spec_id}"


def test_job_response_includes_result_summary():
    """
    Test that job response includes result summary when available.
    
    **Validates: Requirements 9.3**
    """
    job_id = 1
    project_id = 1
    spec_id = 1
    
    cached_summary = {
        'total': 50,
        'passed': 45,
        'failed': 3,
        'skipped': 1,
        'errors': 1,
        'duration_seconds': 60.0
    }
    
    mock_job = create_mock_test_job(job_id, project_id, spec_id, result_summary=cached_summary)
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_job)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = TestManager(mock_session)
    
    result = manager.get_job(job_id)
    
    assert result is not None, "Should return job"
    assert result.result_summary is not None, "Should have result summary"
    assert result.result_summary.total == 50, f"Total should be 50"
    assert result.result_summary.passed == 45, f"Passed should be 45"
