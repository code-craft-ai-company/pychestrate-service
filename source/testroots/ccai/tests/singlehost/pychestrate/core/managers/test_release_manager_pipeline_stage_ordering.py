"""
.. module:: test_release_manager_pipeline_stage_ordering
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ReleaseManager pipeline stage ordering validation

.. moduleauthor:: Code Craft AI LLC

Tests for pipeline stage ordering validation in the ReleaseManager.

**Feature: projects**
**Property 15: Pipeline Stage Ordering**
**Validates: Requirements 17.5**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from ccai.pychestrate.core.managers.release_manager import (
    ReleasePipelineCreateRequest,
    validate_pipeline_stages,
    VALID_STAGE_TYPES,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_pipeline_name():
    """Generate a unique release pipeline name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest = ''.join(random.choices(string.ascii_letters + string.digits + '_-.', k=random.randint(5, 20)))
    return start_char + rest


def generate_unique_stage_name():
    """Generate a unique stage name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest = ''.join(random.choices(string.ascii_letters + string.digits + '_-.', k=random.randint(3, 15)))
    return start_char + rest


def generate_valid_stage(name=None, stage_type=None):
    """
    Generate a valid pipeline stage definition.
    
    :param name: Optional stage name (generated if not provided)
    :param stage_type: Optional stage type (randomly selected if not provided)
    :returns: Dictionary representing a valid stage definition
    """
    if name is None:
        name = generate_unique_stage_name()
    
    if stage_type is None:
        stage_type = random.choice(list(VALID_STAGE_TYPES))
    
    return {
        'name': name,
        'type': stage_type,
        'config': {},
        'requires_approval': random.choice([True, False]),
        'continue_on_failure': random.choice([True, False]),
    }


def generate_valid_stages(count=None):
    """
    Generate a list of valid pipeline stages with unique names.
    
    :param count: Number of stages to generate (random 1-10 if not provided)
    :returns: List of valid stage definitions
    """
    if count is None:
        count = random.randint(1, 10)
    
    stages = []
    used_names = set()
    
    for _ in range(count):
        # Generate unique name
        name = generate_unique_stage_name()
        while name in used_names:
            name = generate_unique_stage_name()
        used_names.add(name)
        
        stages.append(generate_valid_stage(name=name))
    
    return stages


# =============================================================================
# Pipeline Stage Ordering Tests - Property 15
# =============================================================================

def test_valid_stages_pass_validation():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline with valid stages (unique names, valid types), the validation
    should pass with no errors.
    """
    stages = generate_valid_stages(count=5)
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) == 0, f"Valid stages should pass validation, got errors: {errors}"


def test_duplicate_stage_names_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline with duplicate stage names, the validation should fail.
    Duplicate names would create ambiguity in stage ordering and dependencies.
    """
    duplicate_name = generate_unique_stage_name()
    
    stages = [
        generate_valid_stage(name=duplicate_name, stage_type='build'),
        generate_valid_stage(name=duplicate_name, stage_type='test'),
    ]
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) > 0, "Duplicate stage names should be rejected"
    assert any('duplicate' in error.lower() for error in errors), \
        f"Error should mention duplicate, got: {errors}"


def test_empty_stages_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline with no stages, the validation should fail.
    A pipeline must have at least one stage to be valid.
    """
    stages = []
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) > 0, "Empty stages list should be rejected"
    assert any('at least one' in error.lower() for error in errors), \
        f"Error should mention at least one stage required, got: {errors}"


def test_invalid_stage_type_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline with an invalid stage type, the validation should fail.
    """
    stages = [
        {
            'name': generate_unique_stage_name(),
            'type': 'invalid_type_xyz',
            'config': {},
        }
    ]
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) > 0, "Invalid stage type should be rejected"
    assert any('invalid type' in error.lower() for error in errors), \
        f"Error should mention invalid type, got: {errors}"


def test_missing_stage_name_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline stage missing the required 'name' field, validation should fail.
    """
    stages = [
        {
            'type': 'build',
            'config': {},
        }
    ]
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) > 0, "Missing stage name should be rejected"
    assert any('name' in error.lower() for error in errors), \
        f"Error should mention missing name, got: {errors}"


def test_missing_stage_type_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline stage missing the required 'type' field, validation should fail.
    """
    stages = [
        {
            'name': generate_unique_stage_name(),
            'config': {},
        }
    ]
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) > 0, "Missing stage type should be rejected"
    assert any('type' in error.lower() for error in errors), \
        f"Error should mention missing type, got: {errors}"


def test_property_all_valid_stage_types_accepted():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    Property test: For any valid stage type from the allowed set, the stage
    should be accepted by validation.
    """
    for stage_type in VALID_STAGE_TYPES:
        stages = [generate_valid_stage(stage_type=stage_type)]
        
        errors = validate_pipeline_stages(stages)
        
        assert len(errors) == 0, \
            f"Valid stage type '{stage_type}' should be accepted, got errors: {errors}"


def test_property_random_valid_pipelines_pass_validation():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    Property test: For any randomly generated valid pipeline (unique stage names,
    valid types), the validation should pass.
    """
    for _ in range(100):
        num_stages = random.randint(1, 10)
        stages = generate_valid_stages(count=num_stages)
        
        errors = validate_pipeline_stages(stages)
        
        assert len(errors) == 0, \
            f"Valid pipeline with {num_stages} stages should pass validation, got errors: {errors}"


def test_property_duplicate_names_always_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    Property test: For any pipeline with duplicate stage names, regardless of
    other properties, the validation should fail.
    """
    for _ in range(100):
        # Generate a random duplicate name
        duplicate_name = generate_unique_stage_name()
        
        # Generate random number of stages (at least 2 for duplicates)
        num_stages = random.randint(2, 10)
        
        stages = []
        used_names = set()
        
        # Add first stage with the duplicate name
        stages.append(generate_valid_stage(name=duplicate_name))
        
        # Add some unique stages
        for _ in range(num_stages - 2):
            name = generate_unique_stage_name()
            while name in used_names or name == duplicate_name:
                name = generate_unique_stage_name()
            used_names.add(name)
            stages.append(generate_valid_stage(name=name))
        
        # Add second stage with the duplicate name
        stages.append(generate_valid_stage(name=duplicate_name))
        
        # Shuffle to randomize position of duplicates
        random.shuffle(stages)
        
        errors = validate_pipeline_stages(stages)
        
        assert len(errors) > 0, \
            f"Pipeline with duplicate name '{duplicate_name}' should be rejected"


def test_property_stage_order_preserved():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    Property test: For any valid pipeline, the stage order as defined should be
    preserved (stages are processed in the order they appear in the list).
    This ensures dependencies can be satisfied by earlier stages.
    """
    for _ in range(100):
        # Generate stages with specific order
        stages = generate_valid_stages(count=random.randint(2, 8))
        
        # Record the original order
        original_order = [stage['name'] for stage in stages]
        
        # Validate - should pass
        errors = validate_pipeline_stages(stages)
        
        assert len(errors) == 0, \
            f"Valid pipeline should pass validation, got errors: {errors}"
        
        # Verify order is preserved (stages list is not modified)
        current_order = [stage['name'] for stage in stages]
        assert original_order == current_order, \
            f"Stage order should be preserved. Original: {original_order}, Current: {current_order}"


def test_property_invalid_stage_types_always_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    Property test: For any stage with an invalid type (not in VALID_STAGE_TYPES),
    the validation should fail.
    """
    invalid_types = [
        'invalid',
        'unknown',
        'deploy',  # Not in valid types
        'compile',
        'release',
        '',
        '123',
        'BUILD',  # Case sensitive
        'Test',
    ]
    
    for invalid_type in invalid_types:
        stages = [
            {
                'name': generate_unique_stage_name(),
                'type': invalid_type,
                'config': {},
            }
        ]
        
        errors = validate_pipeline_stages(stages)
        
        assert len(errors) > 0, \
            f"Invalid stage type '{invalid_type}' should be rejected"


def test_property_mixed_valid_invalid_stages():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    Property test: For any pipeline with a mix of valid and invalid stages,
    the validation should fail and report errors for the invalid stages.
    """
    for _ in range(50):
        # Generate some valid stages
        valid_stages = generate_valid_stages(count=random.randint(1, 5))
        
        # Add an invalid stage
        invalid_stage = {
            'name': generate_unique_stage_name(),
            'type': 'invalid_type',
            'config': {},
        }
        
        # Mix them together
        all_stages = valid_stages + [invalid_stage]
        random.shuffle(all_stages)
        
        errors = validate_pipeline_stages(all_stages)
        
        assert len(errors) > 0, \
            "Pipeline with invalid stage should be rejected"


def test_non_dict_stage_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline with a non-dictionary stage, validation should fail.
    """
    stages = [
        "not a dict",
        generate_valid_stage(),
    ]
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) > 0, "Non-dict stage should be rejected"
    assert any('dictionary' in error.lower() for error in errors), \
        f"Error should mention dictionary, got: {errors}"


def test_non_list_stages_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline where stages is not a list, validation should fail.
    """
    # Test with dict instead of list
    stages = {'stage1': generate_valid_stage()}
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) > 0, "Non-list stages should be rejected"
    assert any('list' in error.lower() for error in errors), \
        f"Error should mention list, got: {errors}"


def test_empty_stage_name_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline stage with an empty name, validation should fail.
    """
    stages = [
        {
            'name': '',
            'type': 'build',
            'config': {},
        }
    ]
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) > 0, "Empty stage name should be rejected"


def test_whitespace_only_stage_name_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline stage with a whitespace-only name, validation should fail.
    """
    stages = [
        {
            'name': '   ',
            'type': 'build',
            'config': {},
        }
    ]
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) > 0, "Whitespace-only stage name should be rejected"


def test_invalid_config_type_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline stage with a non-dict config, validation should fail.
    """
    stages = [
        {
            'name': generate_unique_stage_name(),
            'type': 'build',
            'config': 'not a dict',
        }
    ]
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) > 0, "Non-dict config should be rejected"


def test_invalid_requires_approval_type_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline stage with a non-boolean requires_approval, validation should fail.
    """
    stages = [
        {
            'name': generate_unique_stage_name(),
            'type': 'build',
            'config': {},
            'requires_approval': 'yes',  # Should be boolean
        }
    ]
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) > 0, "Non-boolean requires_approval should be rejected"


def test_invalid_continue_on_failure_type_rejected():
    """
    **Feature: projects, Property 15: Pipeline Stage Ordering**
    **Validates: Requirements 17.5**
    
    For any pipeline stage with a non-boolean continue_on_failure, validation should fail.
    """
    stages = [
        {
            'name': generate_unique_stage_name(),
            'type': 'build',
            'config': {},
            'continue_on_failure': 1,  # Should be boolean
        }
    ]
    
    errors = validate_pipeline_stages(stages)
    
    assert len(errors) > 0, "Non-boolean continue_on_failure should be rejected"
