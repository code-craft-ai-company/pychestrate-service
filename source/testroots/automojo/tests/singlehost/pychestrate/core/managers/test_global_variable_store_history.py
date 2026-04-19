"""
.. module:: test_global_variable_store_history
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for GlobalVariableStore change history

.. moduleauthor:: Automation Mojo LLC

Tests for global variable change history tracking.

**Feature: system-configuration**
**Validates: Requirements 7.6**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.core.managers.global_variable_store import (
    GlobalVariableStore,
    VariableChangeLog,
)

from automojo.testbase.mocking import Mock


# =============================================================================
# Mock Database Session Factory
# =============================================================================

def create_mock_session():
    """Create a basic mock database session."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    return mock_session


def create_mock_history_entry(entry_id, var_name, old_val, new_val, changed_by, changed_at):
    """Create a mock GlobalVariableHistory entry."""
    mock_entry = Mock()
    mock_entry.configure(recursive=True)
    
    ctx = mock_entry.mock_context()
    ctx.set_attribute('id', entry_id)
    ctx.set_attribute('variable_name', var_name)
    ctx.set_attribute('old_value_json', old_val)
    ctx.set_attribute('new_value_json', new_val)
    ctx.set_attribute('changed_by_id', changed_by)
    ctx.set_attribute('changed_at', changed_at)
    
    return mock_entry


def create_mock_session_with_history_entries(entries):
    """Create a mock session that returns history entries."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    
    mock_order_by = Mock()
    mock_order_by.configure(recursive=True)
    
    mock_offset = Mock()
    mock_offset.configure(recursive=True)
    
    mock_limit = Mock()
    mock_limit.configure(recursive=True)
    mock_limit.mock_context().mock_method('all', return_value=entries)
    
    mock_offset.mock_context().mock_method('limit', return_value=mock_limit)
    mock_order_by.mock_context().mock_method('offset', return_value=mock_offset)
    mock_filter.mock_context().mock_method('order_by', return_value=mock_order_by)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    return mock_session


# =============================================================================
# Tests for Change History
# =============================================================================

def test_variable_change_log_dataclass():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.6**
    
    VariableChangeLog dataclass should store all required fields.
    """
    from datetime import datetime
    
    now = datetime.now()
    log = VariableChangeLog(
        id=1,
        variable_name="test_var",
        old_value="old",
        new_value="new",
        changed_by="admin",
        changed_at=now
    )
    
    assert log.id == 1
    assert log.variable_name == "test_var"
    assert log.old_value == "old"
    assert log.new_value == "new"
    assert log.changed_by == "admin"
    assert log.changed_at == now


def test_variable_change_log_with_none_values():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.6**
    
    VariableChangeLog should handle None values for old_value and changed_by.
    """
    from datetime import datetime
    
    now = datetime.now()
    log = VariableChangeLog(
        id=1,
        variable_name="test_var",
        old_value=None,
        new_value="new",
        changed_by=None,
        changed_at=now
    )
    
    assert log.old_value is None
    assert log.changed_by is None


def test_get_change_history_returns_empty_list_for_no_history():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.6**
    
    get_change_history should return empty list when no history exists.
    """
    mock_session = create_mock_session_with_history_entries([])
    store = GlobalVariableStore(mock_session)
    
    result = store.get_change_history("nonexistent_var")
    
    assert result == []


def test_global_variable_store_has_get_change_history_method():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.6**
    
    GlobalVariableStore should have get_change_history method.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    assert hasattr(store, 'get_change_history')
    assert callable(store.get_change_history)


def test_get_change_history_accepts_pagination_params():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.6**
    
    get_change_history should accept offset and limit parameters.
    """
    mock_session = create_mock_session_with_history_entries([])
    store = GlobalVariableStore(mock_session)
    
    # Should not raise any errors
    result = store.get_change_history("test_var", offset=0, limit=10)
    assert isinstance(result, list)
    
    result = store.get_change_history("test_var", offset=10, limit=50)
    assert isinstance(result, list)


def test_change_history_tracks_variable_name():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.6**
    
    Change history should track the variable name for each change.
    """
    from datetime import datetime
    
    log = VariableChangeLog(
        id=1,
        variable_name="my_config_var",
        old_value="old_value",
        new_value="new_value",
        changed_by="admin",
        changed_at=datetime.now()
    )
    
    assert log.variable_name == "my_config_var"


def test_change_history_tracks_old_and_new_values():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.6**
    
    Change history should track both old and new values.
    """
    from datetime import datetime
    
    log = VariableChangeLog(
        id=1,
        variable_name="test_var",
        old_value={"key": "old"},
        new_value={"key": "new"},
        changed_by="admin",
        changed_at=datetime.now()
    )
    
    assert log.old_value == {"key": "old"}
    assert log.new_value == {"key": "new"}


def test_change_history_tracks_timestamp():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.6**
    
    Change history should track the timestamp of each change.
    """
    from datetime import datetime
    
    timestamp = datetime(2025, 1, 15, 10, 30, 0)
    log = VariableChangeLog(
        id=1,
        variable_name="test_var",
        old_value="old",
        new_value="new",
        changed_by="admin",
        changed_at=timestamp
    )
    
    assert log.changed_at == timestamp


def test_change_history_tracks_user():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.6**
    
    Change history should track the user who made the change.
    """
    from datetime import datetime
    
    log = VariableChangeLog(
        id=1,
        variable_name="test_var",
        old_value="old",
        new_value="new",
        changed_by="admin_user",
        changed_at=datetime.now()
    )
    
    assert log.changed_by == "admin_user"
