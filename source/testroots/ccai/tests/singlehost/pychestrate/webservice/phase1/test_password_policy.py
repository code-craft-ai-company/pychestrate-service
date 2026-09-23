"""
.. module:: test_password_policy
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the shared local-password policy
               (security.auth.password_policy).

.. moduleauthor:: Code Craft AI LLC

The admin create-user form stated "Minimum 12 characters with
uppercase, lowercase, digit, and special character" while the server
only checked the length, so ``aaaaaaaaaaaa`` was accepted (audit
ADM-17). Each test pins one rule of the policy every password-setting
path now shares.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.webservice.security.auth.password_policy import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PASSWORD_HTML_PATTERN,
    PasswordPolicyError,
    check_password_against_policy,
    enforce_password_policy,
    password_policy_template_context,
)


_GOOD_PASSWORD: str = "CorrectHorse9!Battery"


def test_twelve_identical_letters_are_refused():
    """
    **Feature: password policy (ADM-17)**
    **Property: the audit's example "aaaaaaaaaaaa" breaks the policy
    even though it meets the minimum length.**
    """
    problems = check_password_against_policy(password="a" * 12)
    testbase.assert_true(len(problems) > 0, "aaaaaaaaaaaa was accepted")
    return


def test_a_password_meeting_every_rule_is_accepted():
    """
    **Feature: password policy (ADM-17)**
    **Property: a long mixed-class password with no username and no
    common stem yields no problems.**
    """
    problems = check_password_against_policy(
        password=_GOOD_PASSWORD, login_name="worker", email="worker@example.com"
    )
    testbase.assert_equal(problems, [])
    return


def test_a_short_password_is_refused():
    """
    **Feature: password policy (ADM-17)**
    **Property: a password one character shorter than the minimum is
    refused with a length message.**
    """
    candidate = "Aa1!" + "x" * (MIN_PASSWORD_LENGTH - 5)
    problems = check_password_against_policy(password=candidate)
    testbase.assert_true(
        any("at least {}".format(MIN_PASSWORD_LENGTH) in p for p in problems),
        str(problems),
    )
    return


def test_an_overlong_password_is_refused():
    """
    **Feature: password policy (ADM-17)**
    **Property: a password longer than the maximum is refused with a
    length message.**
    """
    candidate = "Aa1!" + "q" * MAX_PASSWORD_LENGTH
    problems = check_password_against_policy(password=candidate)
    testbase.assert_true(
        any("at most {}".format(MAX_PASSWORD_LENGTH) in p for p in problems),
        str(problems),
    )
    return


def test_a_password_without_an_uppercase_letter_is_refused():
    """
    **Feature: password policy (ADM-17)**
    **Property: the uppercase rule is enforced on its own.**
    """
    problems = check_password_against_policy(password=_GOOD_PASSWORD.lower())
    testbase.assert_equal(
        problems, ["Password must contain an uppercase letter."]
    )
    return


def test_a_password_without_a_lowercase_letter_is_refused():
    """
    **Feature: password policy (ADM-17)**
    **Property: the lowercase rule is enforced on its own.**
    """
    problems = check_password_against_policy(password=_GOOD_PASSWORD.upper())
    testbase.assert_equal(
        problems, ["Password must contain a lowercase letter."]
    )
    return


def test_a_password_without_a_digit_is_refused():
    """
    **Feature: password policy (ADM-17)**
    **Property: the digit rule is enforced on its own.**
    """
    problems = check_password_against_policy(password="CorrectHorse!Battery")
    testbase.assert_equal(problems, ["Password must contain a digit."])
    return


def test_a_password_without_a_symbol_is_refused():
    """
    **Feature: password policy (ADM-17)**
    **Property: the symbol rule is enforced on its own.**
    """
    problems = check_password_against_policy(password="CorrectHorse9Battery")
    testbase.assert_equal(
        problems, ["Password must contain a symbol, such as ! # or -."]
    )
    return


def test_a_password_containing_the_username_is_refused():
    """
    **Feature: password policy (ADM-17)**
    **Property: a password that contains the login name
    (case-insensitively) is refused.**
    """
    problems = check_password_against_policy(
        password="Deploy-Bot-2026!x", login_name="deploy-bot"
    )
    testbase.assert_equal(problems, ["Password must not contain the username."])
    return


def test_a_password_containing_the_email_local_part_is_refused():
    """
    **Feature: password policy (ADM-17)**
    **Property: a password that contains the part of the email
    address before the @ is refused.**
    """
    problems = check_password_against_policy(
        password="Jdoe#Secure-2026", email="jdoe@example.com"
    )
    testbase.assert_equal(
        problems, ["Password must not contain the email address."]
    )
    return


def test_a_padded_common_password_is_refused():
    """
    **Feature: password policy (ADM-17)**
    **Property: "Password123!" meets every character rule but is
    refused as too common.**
    """
    problems = check_password_against_policy(password="Password123!")
    testbase.assert_equal(
        problems,
        ["Password is too common. Choose something less predictable."],
    )
    return


def test_a_substituted_common_password_is_refused():
    """
    **Feature: password policy (ADM-17)**
    **Property: letter substitutions ("P@ssw0rd!2024") do not get a
    common password past the check.**
    """
    problems = check_password_against_policy(password="P@ssw0rd!2024")
    testbase.assert_equal(
        problems,
        ["Password is too common. Choose something less predictable."],
    )
    return


def test_enforce_raises_with_every_problem():
    """
    **Feature: password policy (ADM-17)**
    **Property: enforce_password_policy raises PasswordPolicyError
    whose problems list names each broken rule.**
    """
    raised = None
    try:
        enforce_password_policy(password="a" * 12)
    except PasswordPolicyError as xcpt:
        raised = xcpt
    testbase.assert_true(raised is not None, "no error raised")
    testbase.assert_equal(len(raised.problems), 3)
    return


def test_the_template_context_carries_the_same_minimum_length():
    """
    **Feature: password policy (ADM-17)**
    **Property: the values forms render their hint from carry the
    server's minimum length, in the rule text and in the pattern.**
    """
    context = password_policy_template_context()
    testbase.assert_equal(context["password_min_length"], MIN_PASSWORD_LENGTH)
    testbase.assert_true(
        "{" + str(MIN_PASSWORD_LENGTH) + "," in PASSWORD_HTML_PATTERN,
        PASSWORD_HTML_PATTERN,
    )
    return


def test_the_html_pattern_is_valid_under_the_v_flag():
    """
    **Feature: password policy (ADM-17)**
    **Property: the password inputs' pattern passes the RegExp v-flag
    model the form-pattern checks use, so browsers do not ignore it.**
    """
    from ccai.tests.singlehost.pychestrate.webservice.phase14.test_p40j_form_patterns_m1 import (  # noqa: E402
        v_flag_class_problem,
    )
    testbase.assert_equal(v_flag_class_problem(PASSWORD_HTML_PATTERN), None)
    return
