"""
.. module:: test_p32w_user_anonymisation_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A deactivated user can be anonymised for a data-protection request (ADM-41).

.. moduleauthor:: Code Craft AI LLC

``specs/1-user-management`` Requirement 5: a data-protection request is met by erasing the person's
data in place, never by deleting the identity row (audit records reference its id). Only a deactivated
account is offered it, the interface asks for the login name to be typed, and afterwards the account has
nothing that names or authenticates a person: its name, email, credentials, sessions, tokens,
memberships and role bindings are gone. It refuses (changing nothing) for an active account, the acting
administrator's own, one already anonymised and one that owns a project. The handlers run here against
the harness's real in-memory database.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import csv
import io
import re
import uuid

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    ensure_seeded_admin,
    ensure_seeded_viewer,
    grant_role_to_user,
    login_as,
)


GOOD_PASSWORD: str = "Correct-Horse-Battery-9"


def _unique(prefix: str) -> str:
    return "{}-{}".format(prefix, uuid.uuid4().hex[:8])


def _make_user(cookies: Dict[str, str], *, prefix: str, display_name: str = "Erase Me") -> Tuple[str, str]:
    username = _unique(prefix)
    response = adm.post_form(
        path="/admin/users/create", cookies=cookies,
        fields={
            "username": username, "email": "{}@example.com".format(username), "password_setup": "password",
            "password": GOOD_PASSWORD, "display_name": display_name, "firstname": "Ada", "lastname": "Lovelace",
        },
    )
    testbase.assert_equal(response.status_code in (302, 303), True, response.text[:200])
    page = adm.get(path="/admin/users", cookies=cookies, query={"search": username}).text
    match = re.search(r'href="/admin/users/([0-9a-f-]{36})"[^>]*>\s*' + re.escape(username), page)
    testbase.assert_true(match is not None, "user not listed")
    return match.group(1), username


def _post(cookies: Dict[str, str], path: str) -> Any:
    """POST a bare form and keep the re-signed session cookie (a flash rides on it)."""
    response = adm.post_form(path=path, cookies=cookies, fields={})
    cookies.update(response.collect_set_cookies())
    return response


def _deactivate(cookies: Dict[str, str], user_id: str) -> None:
    response = _post(cookies, "/admin/users/{}/deactivate".format(user_id))
    testbase.assert_equal(response.status_code in (302, 303), True)
    return


def _seed_session(user_id: str) -> None:
    """A sign-in session (and where it was opened from) for the user. Deactivating a user closes
    their sessions, so a test seeds one *after* deactivating to prove anonymising removes it too."""
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthProviderKind, AuthSession, AuthSessionClient,
    )

    session = adm.open_db_session()
    try:
        session_id = uuid.uuid4()
        session.add(AuthSession(
            session_id=session_id, user_id=uuid.UUID(user_id), provider_kind=AuthProviderKind.LOCAL, provider_name="local",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1), ip_fingerprint="203.0.113.9", user_agent_fingerprint="Firefox",
        ))
        session.flush()
        session.add(AuthSessionClient(session_id=session_id, client_address="203.0.113.9", user_agent="Firefox/140"))
        session.commit()
    finally:
        session.close()
    return


def _seed_personal_data(user_id: str) -> Dict[str, Any]:
    """Give the user a row in every place the design says is erased; return ids of a second user's rows."""
    from ccai.pychestrate.core.orm import ProjectMember, Project  # noqa: E402
    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityEmailVerification, IdentityGroup, IdentityGroupMembership,
    )
    from ccai.pychestrate.webservice.security.auth.api_tokens.models import AuthApiToken  # noqa: E402
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthMfaEnrollment, AuthPasswordToken, PasswordTokenPurpose,
    )

    user_uuid = uuid.UUID(user_id)
    later = datetime.now(timezone.utc) + timedelta(days=1)
    session = adm.open_db_session()
    try:
        session.add(AuthMfaEnrollment(enrollment_id=uuid.uuid4(), user_id=user_uuid, method_name="totp", secret_ref="vault://x"))
        session.add(AuthPasswordToken(
            token_id=uuid.uuid4(), user_id=user_uuid, purpose=PasswordTokenPurpose.RESET, token_hash=uuid.uuid4().hex + uuid.uuid4().hex, expires_at=later,
        ))
        session.add(AuthApiToken(
            token_id=uuid.uuid4(), user_id=user_uuid, name="ci", token_sha256=uuid.uuid4().hex + uuid.uuid4().hex, token_hint="abcd", expires_at=later,
        ))
        session.add(IdentityEmailVerification(
            verification_id=uuid.uuid4(), user_id=user_uuid, new_email="new@example.com", token_hash=b"x" * 32, expires_at=later,
        ))
        group_id = uuid.uuid4()
        session.add(IdentityGroup(group_id=group_id, group_name=_unique("grp"), description=""))
        session.flush()
        session.add(IdentityGroupMembership(group_id=group_id, user_id=user_uuid))
        project = Project(name=_unique("member-of"), owner_id=uuid.UUID(ensure_seeded_admin().user_id), description="")
        session.add(project)
        session.flush()
        session.add(ProjectMember(project_id=project.id, user_id=user_uuid, role="viewer"))
        session.commit()
    finally:
        session.close()
    return {}


def _counts(user_id: str) -> Dict[str, int]:
    """How many rows of each kind still belong to the user."""
    from sqlalchemy import func  # noqa: E402

    from ccai.pychestrate.core.orm import ProjectMember  # noqa: E402
    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityEmailVerification, IdentityGroupMembership,
    )
    from ccai.pychestrate.webservice.security.auth.api_tokens.models import AuthApiToken  # noqa: E402
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthLocalCredentials, AuthMfaEnrollment, AuthPasswordToken, AuthSession, AuthSessionClient,
    )
    from ccai.pychestrate.webservice.security.rbac.models import PrincipalKind, RbacRoleBinding  # noqa: E402

    user_uuid = uuid.UUID(user_id)
    session = adm.open_db_session()
    try:
        rtnval = {
            "credentials": session.query(func.count()).select_from(AuthLocalCredentials).filter(AuthLocalCredentials.user_id == user_uuid).scalar(),
            "sessions": session.query(func.count()).select_from(AuthSession).filter(AuthSession.user_id == user_uuid).scalar(),
            "session_clients": session.query(func.count()).select_from(AuthSessionClient).join(
                AuthSession, AuthSession.session_id == AuthSessionClient.session_id).filter(AuthSession.user_id == user_uuid).scalar(),
            "mfa": session.query(func.count()).select_from(AuthMfaEnrollment).filter(AuthMfaEnrollment.user_id == user_uuid).scalar(),
            "password_tokens": session.query(func.count()).select_from(AuthPasswordToken).filter(AuthPasswordToken.user_id == user_uuid).scalar(),
            "api_tokens": session.query(func.count()).select_from(AuthApiToken).filter(AuthApiToken.user_id == user_uuid).scalar(),
            "email_verifications": session.query(func.count()).select_from(IdentityEmailVerification).filter(IdentityEmailVerification.user_id == user_uuid).scalar(),
            "groups": session.query(func.count()).select_from(IdentityGroupMembership).filter(IdentityGroupMembership.user_id == user_uuid).scalar(),
            "bindings": session.query(func.count()).select_from(RbacRoleBinding).filter(
                RbacRoleBinding.principal_kind == PrincipalKind.USER, RbacRoleBinding.principal_id == user_uuid).scalar(),
            "projects": session.query(func.count()).select_from(ProjectMember).filter(ProjectMember.user_id == user_uuid).scalar(),
        }
    finally:
        session.close()
    return rtnval


def _client_rows() -> int:
    """Every session-client row in the database (an orphan left by a deleted session would show here)."""
    from sqlalchemy import func  # noqa: E402

    from ccai.pychestrate.webservice.security.auth.models import AuthSessionClient  # noqa: E402

    session = adm.open_db_session()
    try:
        return int(session.query(func.count()).select_from(AuthSessionClient).scalar())
    finally:
        session.close()


def _identity_row(user_id: str) -> Dict[str, Any]:
    from ccai.pychestrate.core.orm import User as LegacyUser  # noqa: E402
    from ccai.pychestrate.webservice.identity.users.models import IdentityUser, UserStatus  # noqa: E402

    session = adm.open_db_session()
    try:
        row = session.query(IdentityUser).filter(IdentityUser.user_id == uuid.UUID(user_id)).one()
        legacy = session.query(LegacyUser).filter(LegacyUser.id == uuid.UUID(user_id)).first()
        rtnval = {
            "login": row.login_name, "email": row.primary_email, "display": row.display_name, "external": row.external_id,
            "deactivated": row.status == UserStatus.DEACTIVATED, "anonymised": row.anonymised_at is not None,
            "legacy": None if legacy is None else (legacy.login, legacy.email, legacy.display_name, legacy.first_name, legacy.last_name, legacy.roles),
        }
    finally:
        session.close()
    return rtnval


def _flash_after(cookies: Dict[str, str], path: str) -> str:
    """The text of the page the person is sent to (where the flash is shown)."""
    response = adm.get(path=path, cookies=cookies)
    cookies.update(response.collect_set_cookies())
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", response.text))


def test_anonymising_a_deactivated_user_erases_everything_that_names_or_authenticates_them():
    """
    **Feature: user anonymisation (ADM-41)**
    **Property: after a deactivated user with a session, MFA enrolment, password link, API token, email
    verification, group membership, project membership and a role is anonymised, none of those rows is left;
    the identity row stays, deactivated, with a login, email and display name derived from its id and no
    external id; the legacy mirror is scrubbed the same way; another user's rows are untouched.**
    """
    cookies = adm.admin_cookies()
    user_id, username = _make_user(cookies, prefix="erase")
    bystander_id, _bystander = _make_user(cookies, prefix="bystander")
    grant_role_to_user(user_id=user_id, role_name="auditor")
    _seed_personal_data(user_id)
    _seed_session(bystander_id)
    _deactivate(cookies, user_id)
    _seed_session(user_id)
    before = _counts(user_id)
    bystander_before = _counts(bystander_id)
    clients_before = _client_rows()

    response = _post(cookies, "/admin/users/{}/anonymise".format(user_id))
    after = _counts(user_id)
    row = _identity_row(user_id)
    hex_id = uuid.UUID(user_id).hex

    testbase.assert_equal(
        (
            response.status_code in (302, 303), all(count >= 1 for count in before.values()),
            after, row["login"], row["email"], row["display"], row["external"], row["deactivated"], row["anonymised"], row["legacy"],
            _counts(bystander_id) == bystander_before, _client_rows() == clients_before - 1,
        ),
        (
            True, True,
            {"credentials": 0, "sessions": 0, "session_clients": 0, "mfa": 0, "password_tokens": 0, "api_tokens": 0,
             "email_verifications": 0, "groups": 0, "bindings": 0, "projects": 0},
            "anonymised-" + hex_id, "{}@anonymised.invalid".format(uuid.UUID(user_id)), "Anonymised user", None, True, True,
            ("anonymised-" + hex_id, "{}@anonymised.invalid".format(uuid.UUID(user_id)), "Anonymised user", "", "", ""),
            True, True,
        ),
    )
    return


def test_an_anonymised_account_shows_as_anonymised_and_offers_no_way_back():
    """
    **Feature: user anonymisation (ADM-41)**
    **Property: the user's page and the list say "Anonymised"; neither offers Edit, Reset password,
    Reactivate or Anonymise; Edit redirects to the page with a message; Reactivate is refused and the
    account stays anonymised; the CSV export says "anonymised" with no roles.**
    """
    cookies = adm.admin_cookies()
    user_id, username = _make_user(cookies, prefix="gone")
    _deactivate(cookies, user_id)
    _post(cookies, "/admin/users/{}/anonymise".format(user_id))
    anonymised = "anonymised-" + uuid.UUID(user_id).hex

    detail = adm.get(path="/admin/users/" + user_id, cookies=cookies).text
    listing = adm.get(path="/admin/users", cookies=cookies, query={"search": anonymised}).text
    edit = adm.get(path="/admin/users/{}/edit".format(user_id), cookies=cookies)
    reactivate = _post(cookies, "/admin/users/{}/reactivate".format(user_id))
    after = _flash_after(cookies, "/admin/users/" + user_id)
    exported = list(csv.DictReader(io.StringIO(adm.get(path="/admin/users", cookies=cookies, query={"format": "csv", "search": anonymised}).text)))

    testbase.assert_equal(
        (
            "Anonymised" in detail, username in detail,
            any(text in detail for text in ("Edit User", "Reset password", "Reactivate", 'data-role="anonymise-form"')),
            "Anonymised" in listing and "Erased" in listing, edit.status_code in (302, 303), reactivate.status_code in (302, 303),
            "cannot be reactivated" in after, _identity_row(user_id)["anonymised"],
            [(row["status"], row["system_roles"]) for row in exported],
        ),
        (True, False, False, True, True, True, True, True, [("anonymised", "")]),
    )
    return


def test_it_refuses_and_changes_nothing_for_an_active_account_the_administrators_own_and_a_project_owner():
    """
    **Feature: user anonymisation (ADM-41)**
    **Property: an active user, the acting administrator, an account already anonymised and a user who
    owns a project are each refused with a message saying what to do first, and the account's name, email
    and rows are exactly as before.**
    """
    from ccai.pychestrate.core.orm import Project  # noqa: E402

    cookies = adm.admin_cookies()
    active_id, _active = _make_user(cookies, prefix="active")
    owner_id, owner_name = _make_user(cookies, prefix="owner")
    _seed_personal_data(owner_id)
    _deactivate(cookies, owner_id)
    session = adm.open_db_session()
    try:
        session.add(Project(name=_unique("owned"), owner_id=uuid.UUID(owner_id), description=""))
        session.commit()
    finally:
        session.close()
    done_id, _done = _make_user(cookies, prefix="done")
    _deactivate(cookies, done_id)
    _post(cookies, "/admin/users/{}/anonymise".format(done_id))
    admin_id = ensure_seeded_admin().user_id

    outcomes: Dict[str, Tuple[bool, str]] = {}
    for label, target in (("active", active_id), ("self", admin_id), ("done", done_id), ("owner", owner_id)):
        before = (_identity_row(target), _counts(target))
        response = _post(cookies, "/admin/users/{}/anonymise".format(target))
        message = _flash_after(cookies, "/admin/users/" + target)
        outcomes[label] = (response.status_code in (302, 303) and before == (_identity_row(target), _counts(target)), message)

    testbase.assert_equal(
        (
            {label: unchanged for label, (unchanged, _message) in outcomes.items()},
            "not deactivated" in outcomes["active"][1] and "Deactivate the account first" in outcomes["active"][1],
            "cannot anonymise your own account" in outcomes["self"][1],
            "already anonymised" in outcomes["done"][1],
            "owns the project" in outcomes["owner"][1] and "Transfer or delete it first" in outcomes["owner"][1],
        ),
        ({"active": True, "self": True, "done": True, "owner": True}, True, True, True, True),
    )
    return


def test_the_button_asks_for_the_login_name_and_is_only_on_a_deactivated_account_and_needs_the_permission():
    """
    **Feature: user anonymisation (ADM-41)**
    **Property: a deactivated user's page carries an Anonymise form whose confirmation asks for the
    login name to be typed; an active user's page has none; a signed-in user without the users permission
    is refused (403) and nothing changes; the anonymisation is written to the audit log with no name or
    email in it.**
    """
    adm.ensure_audit_wiring()
    cookies = adm.admin_cookies()
    user_id, username = _make_user(cookies, prefix="button", display_name="Grace Hopper")
    active_page = adm.get(path="/admin/users/" + user_id, cookies=cookies).text
    _deactivate(cookies, user_id)
    inactive_page = adm.get(path="/admin/users/" + user_id, cookies=cookies).text
    form = re.search(r'<form[^>]*data-role="anonymise-form"[^>]*>', inactive_page)

    viewer = login_as(wsgi_app=ensure_app().wsgi_app, user=ensure_seeded_viewer())
    refused = adm.post_form(path="/admin/users/{}/anonymise".format(user_id), cookies=viewer, fields={})
    still_there = _identity_row(user_id)["login"]

    mark = adm.latest_audit_sequence()
    _post(cookies, "/admin/users/{}/anonymise".format(user_id))
    records = adm.audit_records_for(kind="audit.user.anonymised", since_sequence=mark)
    recorded = " ".join(str(record.payload_json) for record in records)

    testbase.assert_equal(
        (
            'data-role="anonymise-form"' in active_page, form is not None and 'data-confirm-type="{}"'.format(username) in form.group(0),
            refused.status_code, still_there == username, len(records),
            user_id in recorded, username in recorded, "Grace Hopper" in recorded, "@example.com" in recorded,
        ),
        (False, True, 403, True, 1, True, False, False, False),
    )
    return
