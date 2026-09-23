"""
.. module:: test_p31a_adm_password_policy_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The password rules the forms state are the rules the
               server enforces (audit ADM-17).

.. moduleauthor:: Code Craft AI LLC

The create-user form promised uppercase, lowercase, digit and symbol
while the server accepted "aaaaaaaaaaaa"; the setup wizard checked the
length only. These tests drive the real admin route and the wizard's
validator.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.webservice.webinterface.blueprints.setup.routes import (
    _collect_admin_field_errors,
    _collect_admin_form_errors,
)

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    get,
    open_db_session,
    post_form,
    unique_name,
)


def _create_user_with_password(*, login_name: str, password: str):
    cookies = admin_cookies()
    response = post_form(
        path="/admin/users/create",
        fields={
            "username": login_name,
            "email": "{}@example.com".format(login_name),
            "password": password,
            "display_name": "Policy Probe",
        },
        cookies=cookies,
    )
    return response


def _identity_user_exists(*, login_name: str) -> bool:
    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityUser,
    )
    db_session = open_db_session()
    try:
        row = (
            db_session.query(IdentityUser)
            .filter(IdentityUser.login_name == login_name)
            .first()
        )
        rtnval = row is not None
    finally:
        db_session.close()
    return rtnval


def test_admin_create_refuses_twelve_identical_letters():
    """
    **Feature: password policy (ADM-17)**
    **Property: POST /admin/users/create with "aaaaaaaaaaaa" is
    refused with a 400 and no account is created.**
    """
    login_name = unique_name(prefix="weakpw")
    response = _create_user_with_password(
        login_name=login_name, password="a" * 12
    )
    testbase.assert_equal(response.status_code, 400)
    testbase.assert_equal(_identity_user_exists(login_name=login_name), False)
    return


def test_admin_create_names_the_broken_rules():
    """
    **Feature: password policy (ADM-17)**
    **Property: the re-rendered create form tells the admin which
    rules the password broke.**
    """
    login_name = unique_name(prefix="weakpw")
    response = _create_user_with_password(
        login_name=login_name, password="a" * 12
    )
    testbase.assert_true(
        "Password must contain an uppercase letter." in response.text,
        response.text[:2000],
    )
    return


def test_admin_create_accepts_a_compliant_password():
    """
    **Feature: password policy (ADM-17)**
    **Property: a password meeting every rule still creates the
    account (redirect to the user list).**
    """
    login_name = unique_name(prefix="goodpw")
    response = _create_user_with_password(
        login_name=login_name, password="Granite-Harbor-47!"
    )
    testbase.assert_equal(response.status_code, 303)
    testbase.assert_equal(_identity_user_exists(login_name=login_name), True)
    return


def test_admin_create_form_shows_the_enforced_rules():
    """
    **Feature: password policy (ADM-17)**
    **Property: the create form renders the policy checklist and a
    pattern attribute taken from the same module the server uses.**
    """
    from ccai.pychestrate.webservice.security.auth.password_policy import (  # noqa: E402
        PASSWORD_HTML_PATTERN,
    )
    import html as _html  # noqa: E402

    response = get(path="/admin/users/create", cookies=admin_cookies())
    testbase.assert_equal(response.status_code, 200)
    testbase.assert_true(
        'data-password-rule="symbol"' in response.text, "no rules checklist"
    )
    testbase.assert_true(
        'pattern="{}"'.format(_html.escape(PASSWORD_HTML_PATTERN)) in response.text,
        "pattern attribute missing",
    )
    return


def test_setup_wizard_refuses_a_password_breaking_the_policy():
    """
    **Feature: password policy (ADM-17)**
    **Property: the first-administrator form reports the policy
    problems for "aaaaaaaaaaaa", not just its length, under the
    password field.**
    """
    field_errors = _collect_admin_field_errors(
        login_name="firstadmin",
        email="first@example.com",
        password="a" * 12,
        password_confirm="a" * 12,
        display_name="First Admin",
    )
    testbase.assert_true(
        "Password must contain an uppercase letter." in field_errors.get("password", ""),
        str(field_errors),
    )
    return


def test_setup_wizard_accepts_a_compliant_password():
    """
    **Feature: password policy (ADM-17)**
    **Property: a compliant, matching password yields no wizard
    validation problems.**
    """
    problems = _collect_admin_form_errors(
        login_name="firstadmin",
        email="first@example.com",
        password="Granite-Harbor-47!",
        password_confirm="Granite-Harbor-47!",
        display_name="First Admin",
    )
    testbase.assert_equal(problems, [])
    return
