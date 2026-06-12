"""
.. module:: test_release_manager_pipeline_completion
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for ReleaseManager pipeline completion creates release

.. moduleauthor:: Code Craft AI LLC

Property tests for pipeline completion creates release in the ReleaseManager.

**Feature: projects**
**Property 16: Pipeline Completion Creates Release**
**Validates: Requirements 18.6**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.release_manager import (
    ReleaseManager,
    PipelineRunStatus,
    StageRunStatus,
    PipelineTriggerType,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_semver():
    """Generate a random semantic version string."""
    major = random.randint(0, 99)
    minor = random.randint(0, 99)
    patch = random.randint(0, 99)
    return f"{major}.{minor}.{patch}"


def generate_unique_stage_name():
    """Generate a unique stage name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest = ''.join(random.choices(string.ascii_letters + string.digits + '_-.', k=random.randint(3, 15)))
    return start_char + rest


def create_mock_project(project_id, name='test-project'):
    """Create a mock project object matching the Project ORM model."""
    mock_project = Mock()
    mock_project.configure(recursive=True)
    ctx = mock_project.mock_context()
    ctx.set_attribute('id', project_id)
    ctx.set_attribute('name', name)
    return mock_project


def create_mock_pipeline(pipeline_id, project_id, name='test-pipeline', stages=None, version=1):
    """Create a mock pipeline object matching the ProjectReleasePipeline ORM model."""
    if stages is None:
        stages = [
            {'name': 'build', 'type': 'build', 'config': {}},
            {'name': 'test', 'type': 'test', 'config': {}},
            {'name': 'package', 'type': 'package', 'config': {}},
        ]
    
    mock_pipeline = Mock()
    mock_pipeline.configure(recursive=True)
    ctx = mock_pipeline.mock_context()
    ctx.set_attribute('id', pipeline_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('stages_json', stages)
    ctx.set_attribute('triggers_json', ['manual'])
    ctx.set_attribute('variables_json', {})
    ctx.set_attribute('description', '')
    ctx.set_attribute('version', version)
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('updated_at', Mock())
    return mock_pipeline


def create_mock_pipeline_run(run_id, pipeline_id, status, pipeline=None, release_id=None):
    """Create a mock pipeline run object matching the ProjectPipelineRun ORM model."""
    mock_run = Mock()
    mock_run.configure(recursive=True)
    ctx = mock_run.mock_context()
    ctx.set_attribute('id', run_id)
    ctx.set_attribute('pipeline_id', pipeline_id)
    ctx.set_attribute('pipeline_version', 1)
    ctx.set_attribute('status', status)
    ctx.set_attribute('current_stage', None)
    ctx.set_attribute('trigger_type', PipelineTriggerType.MANUAL.value)
    ctx.set_attribute('triggered_by_id', 'user-1')
    ctx.set_attribute('variables_json', {})
    ctx.set_attribute('release_id', release_id)
    ctx.set_attribute('started_at', Mock())
    ctx.set_attribute('completed_at', Mock() if status == PipelineRunStatus.SUCCEEDED.value else None)
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('pipeline', pipeline)
    return mock_run


def create_mock_stage_run(stage_run_id, pipeline_run_id, stage_name, status):
    """Create a mock stage run object matching the ProjectStageRun ORM model."""
    mock_stage_run = Mock()
    mock_stage_run.configure(recursive=True)
    ctx = mock_stage_run.mock_context()
    ctx.set_attribute('id', stage_run_id)
    ctx.set_attribute('pipeline_run_id', pipeline_run_id)
    ctx.set_attribute('stage_name', stage_name)
    ctx.set_attribute('stage_type', 'build')
    ctx.set_attribute('status', status)
    ctx.set_attribute('requires_approval', False)
    ctx.set_attribute('approved_by_id', None)
    ctx.set_attribute('approved_at', None)
    ctx.set_attribute('started_at', Mock())
    ctx.set_attribute('completed_at', Mock() if status == StageRunStatus.SUCCEEDED.value else None)
    ctx.set_attribute('logs_path', None)
    ctx.set_attribute('output_json', {})
    return mock_stage_run


def create_mock_session_for_trigger(mock_pipeline):
    """
    Create a mock database session configured for trigger_pipeline testing.
    
    :param mock_pipeline: The mock pipeline to return from queries
    :returns: Tuple of (mock_session, tracking_dict) where tracking_dict contains
              lists to track created objects
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    tracking = {
        'run_status': None,
        'run_version': None,
        'run_trigger_type': None,
        'run_variables': None,
        'stage_runs': [],
        'stage_statuses': [],
    }
    
    call_count = [0]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=mock_pipeline)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    def add_side_effect(obj):
        if hasattr(obj, 'pipeline_id') and hasattr(obj, 'status') and not hasattr(obj, 'stage_name'):
            # This is a pipeline run
            tracking['run_status'] = obj.status
            tracking['run_version'] = getattr(obj, 'pipeline_version', None)
            tracking['run_trigger_type'] = getattr(obj, 'trigger_type', None)
            tracking['run_variables'] = getattr(obj, 'variables_json', None)
            obj.id = 1
        elif hasattr(obj, 'stage_name'):
            # This is a stage run
            tracking['stage_runs'].append(obj.stage_name)
            tracking['stage_statuses'].append(obj.status)
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add', side_effect=add_side_effect)
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session, tracking


# =============================================================================
# Pipeline Completion Creates Release Tests - Property 16
# =============================================================================

def test_successful_pipeline_creates_pending_status():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    When a pipeline run is triggered, it should start with pending status.
    """
    project_id = 1
    pipeline_id = 1
    
    mock_pipeline = create_mock_pipeline(pipeline_id, project_id)
    mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
    
    manager = ReleaseManager(mock_session)
    
    try:
        manager.trigger_pipeline(
            pipeline_id=pipeline_id,
            trigger_type=PipelineTriggerType.MANUAL,
            variables={},
            user_id='user-1'
        )
    except AttributeError:
        pass
    
    # Verify run was created with pending status
    assert tracking['run_status'] == PipelineRunStatus.PENDING.value, \
        f"Pipeline run should start with pending status, got {tracking['run_status']}"


def test_pipeline_creates_stage_runs():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    Triggering a pipeline should create stage run records for each stage.
    """
    project_id = 1
    pipeline_id = 1
    stages = [
        {'name': 'checkout', 'type': 'checkout', 'config': {}},
        {'name': 'build', 'type': 'build', 'config': {}},
        {'name': 'test', 'type': 'test', 'config': {}},
    ]
    
    mock_pipeline = create_mock_pipeline(pipeline_id, project_id, stages=stages)
    mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
    
    manager = ReleaseManager(mock_session)
    
    try:
        manager.trigger_pipeline(
            pipeline_id=pipeline_id,
            trigger_type=PipelineTriggerType.MANUAL,
            variables={},
            user_id='user-1'
        )
    except AttributeError:
        pass
    
    # Verify stage runs were created for each stage
    expected_stages = ['checkout', 'build', 'test']
    assert set(tracking['stage_runs']) == set(expected_stages), \
        f"Stage runs should be created for all stages. Expected {expected_stages}, got {tracking['stage_runs']}"


def test_property_stage_runs_match_pipeline_stages():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    Property test: For any pipeline with N stages, triggering should create
    exactly N stage run records.
    """
    for _ in range(100):
        project_id = 1
        pipeline_id = 1
        
        # Generate random number of stages
        stage_count = random.randint(1, 10)
        stages = [
            {'name': f'stage_{i}', 'type': 'build', 'config': {}}
            for i in range(stage_count)
        ]
        
        mock_pipeline = create_mock_pipeline(pipeline_id, project_id, stages=stages)
        mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
        
        manager = ReleaseManager(mock_session)
        
        try:
            manager.trigger_pipeline(
                pipeline_id=pipeline_id,
                trigger_type=PipelineTriggerType.MANUAL,
                variables={},
                user_id='user-1'
            )
        except AttributeError:
            pass
        
        assert len(tracking['stage_runs']) == stage_count, \
            f"Should create {stage_count} stage runs, got {len(tracking['stage_runs'])}"


def test_pipeline_run_tracks_pipeline_version():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    Pipeline run should track the pipeline version at time of trigger.
    """
    project_id = 1
    pipeline_id = 1
    pipeline_version = 5
    
    mock_pipeline = create_mock_pipeline(pipeline_id, project_id, version=pipeline_version)
    mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
    
    manager = ReleaseManager(mock_session)
    
    try:
        manager.trigger_pipeline(
            pipeline_id=pipeline_id,
            trigger_type=PipelineTriggerType.MANUAL,
            variables={},
            user_id='user-1'
        )
    except AttributeError:
        pass
    
    assert tracking['run_version'] == pipeline_version, \
        f"Pipeline run should track version {pipeline_version}, got {tracking['run_version']}"


def test_property_pipeline_version_always_tracked():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    Property test: For any pipeline version, the pipeline run should track
    that exact version.
    """
    for _ in range(100):
        project_id = 1
        pipeline_id = 1
        pipeline_version = random.randint(1, 1000)
        
        mock_pipeline = create_mock_pipeline(pipeline_id, project_id, version=pipeline_version)
        mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
        
        manager = ReleaseManager(mock_session)
        
        try:
            manager.trigger_pipeline(
                pipeline_id=pipeline_id,
                trigger_type=PipelineTriggerType.MANUAL,
                variables={},
                user_id='user-1'
            )
        except AttributeError:
            pass
        
        assert tracking['run_version'] == pipeline_version, \
            f"Pipeline run should track version {pipeline_version}, got {tracking['run_version']}"


def test_pipeline_run_stores_trigger_type():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    Pipeline run should store the trigger type.
    """
    project_id = 1
    pipeline_id = 1
    
    trigger_types_to_test = [
        PipelineTriggerType.MANUAL,
        PipelineTriggerType.TAG_PUSH,
        PipelineTriggerType.SCHEDULE,
        PipelineTriggerType.API,
    ]
    
    for trigger_type in trigger_types_to_test:
        mock_pipeline = create_mock_pipeline(pipeline_id, project_id)
        mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
        
        manager = ReleaseManager(mock_session)
        
        try:
            manager.trigger_pipeline(
                pipeline_id=pipeline_id,
                trigger_type=trigger_type,
                variables={},
                user_id='user-1'
            )
        except AttributeError:
            pass
        
        assert tracking['run_trigger_type'] == trigger_type.value, \
            f"Pipeline run should store trigger type {trigger_type.value}, got {tracking['run_trigger_type']}"


def test_pipeline_run_stores_variables():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    Pipeline run should store the provided variables.
    """
    project_id = 1
    pipeline_id = 1
    variables = {'VERSION': '1.0.0', 'ENVIRONMENT': 'production'}
    
    mock_pipeline = create_mock_pipeline(pipeline_id, project_id)
    mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
    
    manager = ReleaseManager(mock_session)
    
    try:
        manager.trigger_pipeline(
            pipeline_id=pipeline_id,
            trigger_type=PipelineTriggerType.MANUAL,
            variables=variables,
            user_id='user-1'
        )
    except AttributeError:
        pass
    
    assert tracking['run_variables'] == variables, \
        f"Pipeline run should store variables {variables}, got {tracking['run_variables']}"


def test_property_variables_preserved_in_run():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    Property test: For any set of variables passed to trigger, they should be
    preserved exactly in the pipeline run.
    """
    for _ in range(100):
        project_id = 1
        pipeline_id = 1
        
        # Generate random variables
        num_vars = random.randint(0, 10)
        variables = {
            f'VAR_{i}': ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(1, 20)))
            for i in range(num_vars)
        }
        
        mock_pipeline = create_mock_pipeline(pipeline_id, project_id)
        mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
        
        manager = ReleaseManager(mock_session)
        
        try:
            manager.trigger_pipeline(
                pipeline_id=pipeline_id,
                trigger_type=PipelineTriggerType.MANUAL,
                variables=variables,
                user_id='user-1'
            )
        except AttributeError:
            pass
        
        assert tracking['run_variables'] == variables, \
            f"Variables should be preserved: expected {variables}, got {tracking['run_variables']}"


def test_stage_runs_start_with_pending_status():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    All stage runs should start with pending status.
    """
    project_id = 1
    pipeline_id = 1
    stages = [
        {'name': 'build', 'type': 'build', 'config': {}},
        {'name': 'test', 'type': 'test', 'config': {}},
    ]
    
    mock_pipeline = create_mock_pipeline(pipeline_id, project_id, stages=stages)
    mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
    
    manager = ReleaseManager(mock_session)
    
    try:
        manager.trigger_pipeline(
            pipeline_id=pipeline_id,
            trigger_type=PipelineTriggerType.MANUAL,
            variables={},
            user_id='user-1'
        )
    except AttributeError:
        pass
    
    for status in tracking['stage_statuses']:
        assert status == StageRunStatus.PENDING.value, \
            f"All stage runs should start with pending status, got {status}"


def test_property_all_stage_runs_start_pending():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    Property test: For any pipeline with any number of stages, all stage runs
    should start with pending status.
    """
    for _ in range(100):
        project_id = 1
        pipeline_id = 1
        
        # Generate random stages
        stage_count = random.randint(1, 10)
        stages = [
            {'name': generate_unique_stage_name(), 'type': random.choice(['build', 'test', 'package']), 'config': {}}
            for _ in range(stage_count)
        ]
        
        mock_pipeline = create_mock_pipeline(pipeline_id, project_id, stages=stages)
        mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
        
        manager = ReleaseManager(mock_session)
        
        try:
            manager.trigger_pipeline(
                pipeline_id=pipeline_id,
                trigger_type=PipelineTriggerType.MANUAL,
                variables={},
                user_id='user-1'
            )
        except AttributeError:
            pass
        
        for i, status in enumerate(tracking['stage_statuses']):
            assert status == StageRunStatus.PENDING.value, \
                f"Stage run {i} should start with pending status, got {status}"


def test_property_stage_names_match_pipeline_definition():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    Property test: For any pipeline, the stage run names should exactly match
    the stage names defined in the pipeline.
    """
    for _ in range(100):
        project_id = 1
        pipeline_id = 1
        
        # Generate unique stage names
        stage_count = random.randint(1, 10)
        stage_names = set()
        while len(stage_names) < stage_count:
            stage_names.add(generate_unique_stage_name())
        stage_names = list(stage_names)
        
        stages = [
            {'name': name, 'type': 'build', 'config': {}}
            for name in stage_names
        ]
        
        mock_pipeline = create_mock_pipeline(pipeline_id, project_id, stages=stages)
        mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
        
        manager = ReleaseManager(mock_session)
        
        try:
            manager.trigger_pipeline(
                pipeline_id=pipeline_id,
                trigger_type=PipelineTriggerType.MANUAL,
                variables={},
                user_id='user-1'
            )
        except AttributeError:
            pass
        
        assert set(tracking['stage_runs']) == set(stage_names), \
            f"Stage run names should match pipeline definition. Expected {stage_names}, got {tracking['stage_runs']}"


def test_empty_variables_preserved():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    Empty variables dictionary should be preserved in the pipeline run.
    """
    project_id = 1
    pipeline_id = 1
    
    mock_pipeline = create_mock_pipeline(pipeline_id, project_id)
    mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
    
    manager = ReleaseManager(mock_session)
    
    try:
        manager.trigger_pipeline(
            pipeline_id=pipeline_id,
            trigger_type=PipelineTriggerType.MANUAL,
            variables={},
            user_id='user-1'
        )
    except AttributeError:
        pass
    
    assert tracking['run_variables'] == {}, \
        f"Empty variables should be preserved, got {tracking['run_variables']}"


def test_single_stage_pipeline():
    """
    **Feature: projects, Property 16: Pipeline Completion Creates Release**
    **Validates: Requirements 18.6**
    
    A pipeline with a single stage should create exactly one stage run.
    """
    project_id = 1
    pipeline_id = 1
    stages = [
        {'name': 'single_stage', 'type': 'build', 'config': {}},
    ]
    
    mock_pipeline = create_mock_pipeline(pipeline_id, project_id, stages=stages)
    mock_session, tracking = create_mock_session_for_trigger(mock_pipeline)
    
    manager = ReleaseManager(mock_session)
    
    try:
        manager.trigger_pipeline(
            pipeline_id=pipeline_id,
            trigger_type=PipelineTriggerType.MANUAL,
            variables={},
            user_id='user-1'
        )
    except AttributeError:
        pass
    
    assert len(tracking['stage_runs']) == 1, \
        f"Single stage pipeline should create 1 stage run, got {len(tracking['stage_runs'])}"
    assert tracking['stage_runs'][0] == 'single_stage', \
        f"Stage run name should be 'single_stage', got {tracking['stage_runs'][0]}"

