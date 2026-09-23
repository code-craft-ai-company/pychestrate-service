"""
.. module:: test_p31b_adm_secret_value_not_echoed_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A failed secret create never renders the secret value
               back into the page (audit ADM-31).

.. moduleauthor:: Code Craft AI LLC

Submitting a duplicate secret name re-rendered the create form with
the submitted value in ``value="..."``, so the plaintext secret sat in
the page HTML (and in any proxy or browser cache of it). These tests
drive the real admin routes.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    open_db_session,
    post_form,
    unique_name,
)


def _create_scope(*, cookies) -> int:
    from ccai.pychestrate.core.orm import SecretScope  # noqa: E402

    scope_name = unique_name(prefix="scope")
    response = post_form(
        path="/admin/scopes/create",
        fields={"name": scope_name, "description": "echo test"},
        cookies=cookies,
    )
    testbase.assert_equal(response.status_code, 303)
    db_session = open_db_session()
    try:
        row = (
            db_session.query(SecretScope)
            .filter(SecretScope.name == scope_name)
            .first()
        )
        rtnval = int(row.id)
    finally:
        db_session.close()
    return rtnval


def _duplicate_secret_submit(*, secret_value: str, description: str):
    cookies = admin_cookies()
    scope_id = _create_scope(cookies=cookies)
    secret_name = "dup{}".format(uuid.uuid4().hex[:8])
    first = post_form(
        path="/admin/secrets/create",
        fields={
            "scope_id": scope_id,
            "name": secret_name,
            "secret_type": "generic",
            "value": "first-value-1",
            "description": "",
        },
        cookies=cookies,
    )
    testbase.assert_equal(first.status_code, 303)
    second = post_form(
        path="/admin/secrets/create",
        fields={
            "scope_id": scope_id,
            "name": secret_name,
            "secret_type": "generic",
            "value": secret_value,
            "description": description,
        },
        cookies=cookies,
    )
    return second


def test_failed_secret_create_is_refused_with_the_form():
    """
    **Feature: secret value never echoed (ADM-31)**
    **Property: a duplicate secret name re-renders the create form
    with a 400.**
    """
    response = _duplicate_secret_submit(
        secret_value="canary-{}".format(uuid.uuid4().hex),
        description="",
    )
    testbase.assert_equal(response.status_code, 400)
    return


def test_failed_secret_create_does_not_echo_the_value():
    """
    **Feature: secret value never echoed (ADM-31)**
    **Property: the submitted secret value does not appear anywhere in
    the re-rendered page.**
    """
    canary = "canary-{}".format(uuid.uuid4().hex)
    response = _duplicate_secret_submit(secret_value=canary, description="")
    testbase.assert_equal(canary in response.text, False)
    return


def test_failed_secret_create_asks_to_reenter_the_value():
    """
    **Feature: secret value never echoed (ADM-31)**
    **Property: the re-rendered form tells the user the value was not
    kept and must be entered again.**
    """
    response = _duplicate_secret_submit(
        secret_value="canary-{}".format(uuid.uuid4().hex),
        description="",
    )
    testbase.assert_true(
        "For your security the value was not kept" in response.text,
        response.text[:1500],
    )
    return


def test_failed_secret_create_keeps_the_other_fields():
    """
    **Feature: secret value never echoed (ADM-31)**
    **Property: the non-secret fields the user typed (description)
    survive the re-render.**
    """
    description = "keep-{}".format(uuid.uuid4().hex[:10])
    response = _duplicate_secret_submit(
        secret_value="canary-{}".format(uuid.uuid4().hex),
        description=description,
    )
    testbase.assert_true(description in response.text, "description lost")
    return
