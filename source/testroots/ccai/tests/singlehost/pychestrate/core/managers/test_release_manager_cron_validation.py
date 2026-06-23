"""
.. module:: test_release_manager_cron_validation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for ReleaseManager cron expression validation

.. moduleauthor:: Code Craft AI LLC

Property tests for cron expression validation in the ReleaseManager.

**Feature: projects**
**Property 23: Cron Expression Validation**
**Validates: Requirements 21.3**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from ccai.pychestrate.core.managers.release_manager import (
    validate_cron_expression,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_valid_minute():
    """Generate a valid minute field value (0-59)."""
    choices = [
        lambda: '*',
        lambda: str(random.randint(0, 59)),
        lambda: f"{random.randint(0, 30)}-{random.randint(31, 59)}",
        lambda: f"*/{random.randint(1, 30)}",
        lambda: f"{random.randint(0, 29)},{random.randint(30, 59)}",
    ]
    return random.choice(choices)()


def generate_valid_hour():
    """Generate a valid hour field value (0-23)."""
    choices = [
        lambda: '*',
        lambda: str(random.randint(0, 23)),
        lambda: f"{random.randint(0, 11)}-{random.randint(12, 23)}",
        lambda: f"*/{random.randint(1, 12)}",
        lambda: f"{random.randint(0, 11)},{random.randint(12, 23)}",
    ]
    return random.choice(choices)()


def generate_valid_day_of_month():
    """Generate a valid day of month field value (1-31)."""
    choices = [
        lambda: '*',
        lambda: str(random.randint(1, 31)),
        lambda: f"{random.randint(1, 15)}-{random.randint(16, 31)}",
        lambda: f"*/{random.randint(1, 15)}",
        lambda: f"{random.randint(1, 15)},{random.randint(16, 31)}",
    ]
    return random.choice(choices)()


def generate_valid_month():
    """Generate a valid month field value (1-12)."""
    choices = [
        lambda: '*',
        lambda: str(random.randint(1, 12)),
        lambda: f"{random.randint(1, 6)}-{random.randint(7, 12)}",
        lambda: f"*/{random.randint(1, 6)}",
        lambda: f"{random.randint(1, 6)},{random.randint(7, 12)}",
    ]
    return random.choice(choices)()


def generate_valid_day_of_week():
    """Generate a valid day of week field value (0-6)."""
    choices = [
        lambda: '*',
        lambda: str(random.randint(0, 6)),
        lambda: f"{random.randint(0, 3)}-{random.randint(4, 6)}",
        lambda: f"*/{random.randint(1, 3)}",
        lambda: f"{random.randint(0, 3)},{random.randint(4, 6)}",
    ]
    return random.choice(choices)()


def generate_valid_cron_expression():
    """Generate a random valid cron expression."""
    minute = generate_valid_minute()
    hour = generate_valid_hour()
    dom = generate_valid_day_of_month()
    month = generate_valid_month()
    dow = generate_valid_day_of_week()
    return f"{minute} {hour} {dom} {month} {dow}"


def generate_invalid_cron_expression():
    """Generate an invalid cron expression."""
    invalid_patterns = [
        lambda: "",  # Empty string
        lambda: "* * * *",  # Only 4 fields
        lambda: "* * * * * *",  # 6 fields
        lambda: f"{random.randint(60, 100)} * * * *",  # Minute out of range
        lambda: f"* {random.randint(24, 50)} * * *",  # Hour out of range
        lambda: f"* * {random.randint(32, 50)} * *",  # Day of month out of range
        lambda: "* * 0 * *",  # Day of month 0 (invalid)
        lambda: f"* * * {random.randint(13, 20)} *",  # Month out of range
        lambda: "* * * 0 *",  # Month 0 (invalid)
        lambda: f"* * * * {random.randint(7, 15)}",  # Day of week out of range
        lambda: "invalid",  # Not a cron expression
        lambda: "a b c d e",  # Non-numeric fields
        lambda: "*",  # Only 1 field
        lambda: "* *",  # Only 2 fields
        lambda: "* * *",  # Only 3 fields
    ]
    return random.choice(invalid_patterns)()


# =============================================================================
# Cron Expression Validation Tests - Property 23
# =============================================================================

def test_valid_basic_cron_expressions():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Basic cron expressions with wildcards should be valid.
    """
    valid_expressions = [
        "* * * * *",           # Every minute
        "0 * * * *",           # Every hour
        "0 0 * * *",           # Every day at midnight
        "0 0 1 * *",           # First day of every month
        "0 0 * * 0",           # Every Sunday
    ]
    
    for expr in valid_expressions:
        assert validate_cron_expression(expr), \
            f"Cron expression '{expr}' should be valid"


def test_valid_specific_time_cron_expressions():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Cron expressions with specific times should be valid.
    """
    valid_expressions = [
        "30 4 * * *",          # 4:30 AM every day
        "0 9 * * 1-5",         # 9 AM weekdays
        "0 12 1 * *",          # Noon on first of month
        "15 14 1 * *",         # 2:15 PM on first of month
        "0 0 1 1 *",           # Midnight on Jan 1
    ]
    
    for expr in valid_expressions:
        assert validate_cron_expression(expr), \
            f"Cron expression '{expr}' should be valid"


def test_valid_range_cron_expressions():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Cron expressions with ranges should be valid.
    """
    valid_expressions = [
        "0-30 * * * *",        # First 30 minutes of each hour
        "0 9-17 * * *",        # Every hour 9 AM to 5 PM
        "0 0 1-15 * *",        # First 15 days of month
        "0 0 * 1-6 *",         # First 6 months
        "0 0 * * 1-5",         # Monday to Friday
    ]
    
    for expr in valid_expressions:
        assert validate_cron_expression(expr), \
            f"Cron expression '{expr}' should be valid"


def test_valid_step_cron_expressions():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Cron expressions with step values should be valid.
    """
    valid_expressions = [
        "*/5 * * * *",         # Every 5 minutes
        "0 */2 * * *",         # Every 2 hours
        "0 0 */3 * *",         # Every 3 days
        "0 0 1 */2 *",         # Every 2 months
        "0 0 * * */2",         # Every other day of week
    ]
    
    for expr in valid_expressions:
        assert validate_cron_expression(expr), \
            f"Cron expression '{expr}' should be valid"


def test_valid_comma_separated_cron_expressions():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Cron expressions with comma-separated values should be valid.
    """
    valid_expressions = [
        "0,30 * * * *",        # At 0 and 30 minutes
        "0 9,12,18 * * *",     # At 9 AM, noon, and 6 PM
        "0 0 1,15 * *",        # 1st and 15th of month
        "0 0 * 1,4,7,10 *",    # Quarterly
        "0 0 * * 0,6",         # Weekends
    ]
    
    for expr in valid_expressions:
        assert validate_cron_expression(expr), \
            f"Cron expression '{expr}' should be valid"


def test_invalid_cron_expressions():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Invalid cron expressions should be rejected.
    """
    invalid_expressions = [
        "",                    # Empty string
        "* * * *",             # Only 4 fields
        "* * * * * *",         # 6 fields
        "60 * * * *",          # Minute out of range
        "* 24 * * *",          # Hour out of range
        "* * 32 * *",          # Day of month out of range
        "* * 0 * *",           # Day of month 0 (invalid)
        "* * * 13 *",          # Month out of range
        "* * * 0 *",           # Month 0 (invalid)
        "* * * * 7",           # Day of week out of range
        "invalid",             # Not a cron expression
        "a b c d e",           # Non-numeric fields
    ]
    
    for expr in invalid_expressions:
        assert not validate_cron_expression(expr), \
            f"Cron expression '{expr}' should be invalid"


def test_empty_cron_expression_invalid():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Empty cron expression should be invalid.
    """
    assert not validate_cron_expression(""), "Empty string should be invalid"
    assert not validate_cron_expression(None), "None should be invalid"


def test_wrong_field_count_invalid():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Cron expressions with wrong number of fields should be invalid.
    """
    invalid_expressions = [
        "*",                   # 1 field
        "* *",                 # 2 fields
        "* * *",               # 3 fields
        "* * * *",             # 4 fields
        "* * * * * *",         # 6 fields
        "* * * * * * *",       # 7 fields
    ]
    
    for expr in invalid_expressions:
        assert not validate_cron_expression(expr), \
            f"Cron expression '{expr}' with wrong field count should be invalid"


def test_property_valid_cron_fields_produce_valid_expression():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: Combining valid field values should produce valid expressions.
    """
    for _ in range(100):
        minute = generate_valid_minute()
        hour = generate_valid_hour()
        dom = generate_valid_day_of_month()
        month = generate_valid_month()
        dow = generate_valid_day_of_week()
        expr = f"{minute} {hour} {dom} {month} {dow}"
        
        assert validate_cron_expression(expr), \
            f"Cron expression '{expr}' should be valid"


def test_property_all_valid_minutes():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: All minute values 0-59 should be valid.
    """
    for minute in range(60):
        expr = f"{minute} * * * *"
        assert validate_cron_expression(expr), \
            f"Minute value {minute} should be valid"


def test_property_all_valid_hours():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: All hour values 0-23 should be valid.
    """
    for hour in range(24):
        expr = f"0 {hour} * * *"
        assert validate_cron_expression(expr), \
            f"Hour value {hour} should be valid"


def test_property_all_valid_days_of_month():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: All day of month values 1-31 should be valid.
    """
    for dom in range(1, 32):
        expr = f"0 0 {dom} * *"
        assert validate_cron_expression(expr), \
            f"Day of month value {dom} should be valid"


def test_property_all_valid_months():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: All month values 1-12 should be valid.
    """
    for month in range(1, 13):
        expr = f"0 0 1 {month} *"
        assert validate_cron_expression(expr), \
            f"Month value {month} should be valid"


def test_property_all_valid_days_of_week():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: All day of week values 0-6 should be valid.
    """
    for dow in range(7):
        expr = f"0 0 * * {dow}"
        assert validate_cron_expression(expr), \
            f"Day of week value {dow} should be valid"


def test_property_invalid_minutes_rejected():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: Minute values >= 60 should be invalid.
    """
    for minute in range(60, 100):
        expr = f"{minute} * * * *"
        assert not validate_cron_expression(expr), \
            f"Minute value {minute} should be invalid"


def test_property_invalid_hours_rejected():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: Hour values >= 24 should be invalid.
    """
    for hour in range(24, 50):
        expr = f"0 {hour} * * *"
        assert not validate_cron_expression(expr), \
            f"Hour value {hour} should be invalid"


def test_property_invalid_days_of_month_rejected():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: Day of month values > 31 or 0 should be invalid.
    """
    # Test values > 31
    for dom in range(32, 50):
        expr = f"0 0 {dom} * *"
        assert not validate_cron_expression(expr), \
            f"Day of month value {dom} should be invalid"
    
    # Test value 0
    expr = "0 0 0 * *"
    assert not validate_cron_expression(expr), \
        "Day of month value 0 should be invalid"


def test_property_invalid_months_rejected():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: Month values > 12 or 0 should be invalid.
    """
    # Test values > 12
    for month in range(13, 20):
        expr = f"0 0 1 {month} *"
        assert not validate_cron_expression(expr), \
            f"Month value {month} should be invalid"
    
    # Test value 0
    expr = "0 0 1 0 *"
    assert not validate_cron_expression(expr), \
        "Month value 0 should be invalid"


def test_property_invalid_days_of_week_rejected():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: Day of week values > 6 should be invalid.
    """
    for dow in range(7, 15):
        expr = f"0 0 * * {dow}"
        assert not validate_cron_expression(expr), \
            f"Day of week value {dow} should be invalid"


def test_common_cron_patterns():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Test common cron patterns used in real-world scenarios.
    """
    common_patterns = [
        ("0 0 * * *", "Daily at midnight"),
        ("0 0 * * 0", "Weekly on Sunday"),
        ("0 0 1 * *", "Monthly on the 1st"),
        ("0 0 1 1 *", "Yearly on Jan 1"),
        ("*/15 * * * *", "Every 15 minutes"),
        ("0 */4 * * *", "Every 4 hours"),
        ("0 9-17 * * 1-5", "Business hours weekdays"),
        ("0 0 1,15 * *", "1st and 15th of month"),
    ]
    
    for expr, description in common_patterns:
        assert validate_cron_expression(expr), \
            f"Common pattern '{description}' ({expr}) should be valid"


def test_range_with_step_valid():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Ranges with step values should be valid.
    """
    valid_expressions = [
        "0-30/5 * * * *",      # Every 5 minutes in first half hour
        "0 9-17/2 * * *",      # Every 2 hours during business hours
        "0 0 1-15/3 * *",      # Every 3 days in first half of month
    ]
    
    for expr in valid_expressions:
        assert validate_cron_expression(expr), \
            f"Cron expression '{expr}' should be valid"


def test_property_generated_valid_expressions():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: Generated valid cron expressions should be accepted.
    """
    for _ in range(100):
        expr = generate_valid_cron_expression()
        assert validate_cron_expression(expr), \
            f"Generated cron expression '{expr}' should be valid"


def test_property_validation_is_deterministic():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: For any cron expression, calling validate_cron_expression
    multiple times should always return the same result.
    """
    test_expressions = [
        "* * * * *",
        "0 0 * * *",
        "*/5 * * * *",
        "invalid",
        "",
        "60 * * * *",
    ]
    
    for expr in test_expressions:
        results = [validate_cron_expression(expr) for _ in range(10)]
        assert all(r == results[0] for r in results), \
            f"Validation for '{expr}' should be deterministic"


def test_property_valid_accepted_invalid_rejected():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Property test: For any cron expression string, the validation function
    accepts it if and only if it conforms to standard 5-field cron syntax.
    """
    # Test valid expressions are accepted
    for _ in range(50):
        valid_expr = generate_valid_cron_expression()
        assert validate_cron_expression(valid_expr), \
            f"Valid expression '{valid_expr}' should be accepted"
    
    # Test invalid expressions are rejected
    for _ in range(50):
        invalid_expr = generate_invalid_cron_expression()
        # Skip empty strings as they're handled separately
        if invalid_expr == "":
            continue
        assert not validate_cron_expression(invalid_expr), \
            f"Invalid expression '{invalid_expr}' should be rejected"


def test_cron_edge_cases():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Test edge cases for cron expression validation.
    """
    # Boundary values
    assert validate_cron_expression("0 0 1 1 0"), \
        "Minimum boundary values should be valid"
    assert validate_cron_expression("59 23 31 12 6"), \
        "Maximum boundary values should be valid"
    
    # Multiple comma-separated values
    assert validate_cron_expression("0,15,30,45 * * * *"), \
        "Multiple comma-separated values should be valid"
    
    # Complex expression
    assert validate_cron_expression("0-30/5 9-17/2 1,15 1-6 1-5"), \
        "Complex expression should be valid"


def test_whitespace_handling():
    """
    **Feature: projects, Property 23: Cron Expression Validation**
    **Validates: Requirements 21.3**
    
    Test whitespace handling in cron expressions.
    """
    # Leading/trailing whitespace should be handled by strip()
    assert validate_cron_expression("  * * * * *  "), \
        "Expression with leading/trailing whitespace should be valid"
    
    # Multiple spaces between fields - Python's split() handles this by
    # splitting on any whitespace and removing empty strings, so this is valid
    expr_with_extra_spaces = "*  *  *  *  *"
    assert validate_cron_expression(expr_with_extra_spaces), \
        "Expression with multiple spaces between fields should be valid (split handles it)"
