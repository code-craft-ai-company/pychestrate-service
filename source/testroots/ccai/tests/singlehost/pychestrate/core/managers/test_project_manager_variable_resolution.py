"""
.. module:: test_project_manager_variable_resolution
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ProjectManager variable resolution order

.. moduleauthor:: Code Craft AI LLC

Tests for variable resolution order in the ProjectManager.

**Feature: projects**
**Property 8: Variable Resolution Order**
**Validates: Requirements 4.6, 17.6**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import random
import string

from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.project_manager import ProjectManager
from ccai.pychestrate.webservice.variables.models import VariableValueType


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_name():
    """Generate a unique variable name for testing."""
    return 'var_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def create_mock_project_variable(var_id, name, value, var_type='string'):
    """Create a mock project variable object."""
    mock_var = Mock()
    mock_var.configure(recursive=True)
    ctx = mock_var.mock_context()
    ctx.set_attribute('id', var_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('value_json', json.dumps(value))
    ctx.set_attribute('var_type', var_type)
    ctx.set_attribute('is_sensitive', False)
    return mock_var


def create_mock_global_variable(var_id, name, value, var_type='string'):
    """Create a mock SYSTEM-scope variable binding (the modern store's row; string values only)."""
    mock_var = Mock()
    mock_var.configure(recursive=True)
    ctx = mock_var.mock_context()
    ctx.set_attribute('id', var_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('value_type', VariableValueType.STRING)
    ctx.set_attribute('value_text', value)
    return mock_var


def create_mock_session_for_variable_resolution(project_var=None, global_var=None):
    """
    Create a mock session that simulates variable resolution.
    
    Query flow for resolve_variable:
    1. Query ProjectVariable to check project scope
    2. Query the SYSTEM-scope variable bindings (only if project var not found)
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
        
        # First call: project variable lookup
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=project_var)
        # Second call: global variable lookup (only if project var was None)
        elif call_count[0] == 2:
            mock_filter.mock_context().mock_method('first', return_value=global_var)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    
    return mock_session


# =============================================================================
# Variable Resolution Order Tests - Property 8
# =============================================================================

def test_project_variable_takes_precedence_over_global():
    """
    **Feature: projects, Property 8: Variable Resolution Order**
    **Validates: Requirements 4.6, 17.6**
    
    For any variable reference, the resolution order is: project variables first,
    then global variables. If found in project scope, global scope is not checked.
    """
    project_id = 1
    var_name = 'MY_VAR'
    project_value = 'project_value'
    global_value = 'global_value'
    
    # Create both project and global variables with same name
    project_var = create_mock_project_variable(1, var_name, project_value)
    global_var = create_mock_global_variable(1, var_name, global_value)
    
    # Create mock session - project var exists, so global should not be checked
    mock_session = create_mock_session_for_variable_resolution(project_var, global_var)
    
    manager = ProjectManager(mock_session)
    
    # Resolve the variable
    result = manager.resolve_variable(project_id, var_name)
    
    # Should return project value, not global value
    assert result == project_value, \
        f"Project variable should take precedence. Expected '{project_value}', got '{result}'"


def test_global_variable_used_when_project_variable_not_found():
    """
    **Feature: projects, Property 8: Variable Resolution Order**
    **Validates: Requirements 4.6, 17.6**
    
    If a variable is not found in project scope, it should be resolved from global scope.
    """
    project_id = 1
    var_name = 'GLOBAL_ONLY_VAR'
    global_value = 'global_value'
    
    # Create only global variable
    global_var = create_mock_global_variable(1, var_name, global_value)
    
    # Create mock session - no project var, but global var exists
    mock_session = create_mock_session_for_variable_resolution(None, global_var)
    
    manager = ProjectManager(mock_session)
    
    # Resolve the variable
    result = manager.resolve_variable(project_id, var_name)
    
    # Should return global value
    assert result == global_value, \
        f"Global variable should be used when project var not found. Expected '{global_value}', got '{result}'"


def test_none_returned_when_variable_not_found_in_any_scope():
    """
    **Feature: projects, Property 8: Variable Resolution Order**
    **Validates: Requirements 4.6, 17.6**
    
    If a variable is not found in either project or global scope, None should be returned.
    """
    project_id = 1
    var_name = 'NONEXISTENT_VAR'
    
    # Create mock session - no variables exist
    mock_session = create_mock_session_for_variable_resolution(None, None)
    
    manager = ProjectManager(mock_session)
    
    # Resolve the variable
    result = manager.resolve_variable(project_id, var_name)
    
    # Should return None
    assert result is None, f"Should return None when variable not found. Got '{result}'"


def test_property_project_scope_always_checked_first():
    """
    **Feature: projects, Property 8: Variable Resolution Order**
    **Validates: Requirements 4.6, 17.6**
    
    Property test: For any variable name, project scope is always checked first.
    """
    for _ in range(100):
        project_id = random.randint(1, 1000)
        var_name = generate_unique_name()
        project_value = f'project_{random.randint(1, 1000)}'
        global_value = f'global_{random.randint(1, 1000)}'
        
        # Create both variables
        project_var = create_mock_project_variable(1, var_name, project_value)
        global_var = create_mock_global_variable(1, var_name, global_value)
        
        # Create mock session with both variables
        mock_session = create_mock_session_for_variable_resolution(project_var, global_var)
        
        manager = ProjectManager(mock_session)
        
        # Resolve the variable
        result = manager.resolve_variable(project_id, var_name)
        
        # Should always return project value when both exist
        assert result == project_value, \
            f"Project scope should always be checked first for '{var_name}'"


def test_property_global_scope_only_checked_when_project_scope_empty():
    """
    **Feature: projects, Property 8: Variable Resolution Order**
    **Validates: Requirements 4.6, 17.6**
    
    Property test: Global scope is only checked when project scope doesn't have the variable.
    """
    for _ in range(100):
        project_id = random.randint(1, 1000)
        var_name = generate_unique_name()
        global_value = f'global_{random.randint(1, 1000)}'
        
        # Create only global variable
        global_var = create_mock_global_variable(1, var_name, global_value)
        
        # Create mock session with only global variable
        mock_session = create_mock_session_for_variable_resolution(None, global_var)
        
        manager = ProjectManager(mock_session)
        
        # Resolve the variable
        result = manager.resolve_variable(project_id, var_name)
        
        # Should return global value when project var doesn't exist
        assert result == global_value, \
            f"Global scope should be checked when project scope is empty for '{var_name}'"


def test_variable_resolution_with_different_types():
    """
    **Feature: projects, Property 8: Variable Resolution Order**
    **Validates: Requirements 4.6, 17.6**
    
    Variable resolution should work correctly for all supported types.
    """
    project_id = 1
    
    test_cases = [
        ('string_var', 'hello world', 'string'),
        ('int_var', 42, 'integer'),
        ('float_var', 3.14, 'float'),
        ('bool_var', True, 'boolean'),
        ('json_var', {'key': 'value'}, 'json'),
    ]
    
    for var_name, value, var_type in test_cases:
        project_var = create_mock_project_variable(1, var_name, value, var_type)
        mock_session = create_mock_session_for_variable_resolution(project_var, None)
        
        manager = ProjectManager(mock_session)
        result = manager.resolve_variable(project_id, var_name)
        
        assert result == value, \
            f"Variable resolution failed for type '{var_type}'. Expected {value}, got {result}"


def test_variable_resolution_is_deterministic():
    """
    **Feature: projects, Property 8: Variable Resolution Order**
    **Validates: Requirements 4.6, 17.6**
    
    Property: For any variable, calling resolve_variable multiple times
    should always return the same result.
    """
    project_id = 1
    var_name = 'DETERMINISTIC_VAR'
    project_value = 'consistent_value'
    
    project_var = create_mock_project_variable(1, var_name, project_value)
    
    results = []
    for _ in range(10):
        mock_session = create_mock_session_for_variable_resolution(project_var, None)
        manager = ProjectManager(mock_session)
        results.append(manager.resolve_variable(project_id, var_name))
    
    assert all(r == results[0] for r in results), \
        "Variable resolution should be deterministic"
