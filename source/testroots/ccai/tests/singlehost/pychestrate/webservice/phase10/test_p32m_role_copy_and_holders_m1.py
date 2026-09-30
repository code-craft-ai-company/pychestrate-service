"""
.. module:: test_p32m_role_copy_and_holders_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A role can be copied, and its page says who has it (ADM-06).

.. moduleauthor:: Code Craft AI LLC

Building a role meant ticking permissions from an empty form, and the role
page showed only "3 users". The create form now starts from any role
(``?copy_from=<role id>``, chosen on the form or with Copy Role on a role's page)
with its permissions ticked and a free name suggested, and the role page lists
who has the role and where it applies. Naming the people needs permission to view
users; the change buttons need permission to administer roles.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import uuid

from typing import Any, Dict, List, Optional, Tuple

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.blueprints.config import identity_admin
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_roles import suggest_copy_name

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    ensure_seeded_user,
    grant_role_to_user,
    login_as,
)


def _role_links(page: str) -> Dict[str, str]:
    """Role name -> role id for every role the list page links to."""
    rtnval: Dict[str, str] = {}
    for role_id, name in re.findall(r'href="/admin/roles/([0-9a-f-]{36})"[^>]*>\s*([^<]+?)\s*</a>', page):
        rtnval[name] = role_id
    return rtnval


def _role_id(cookies: Dict[str, str], name: str) -> str:
    page = adm.get(path="/admin/roles", cookies=cookies).text
    links = _role_links(page)
    testbase.assert_true(name in links, "role {} not listed: {}".format(name, sorted(links)))
    return links[name]


def _ticked(page: str) -> List[str]:
    """The permission keys ticked on a role form."""
    ticked: List[str] = []
    for tag in re.findall(r'<input[^>]*name="permission_keys"[^>]*>', page):
        if " checked" in tag:
            match = re.search(r'value="([^"]+)"', tag)
            if match is not None:
                ticked.append(match.group(1))
    return sorted(ticked)


def _field_value(page: str, field_id: str) -> str:
    match = re.search(r'<input[^>]*\bid="' + field_id + r'"[^>]*\bvalue="([^"]*)"', page)
    return match.group(1) if match is not None else ""


def _unique(prefix: str) -> str:
    return "{}-{}".format(prefix, uuid.uuid4().hex[:8])


def test_a_copy_is_named_after_the_original_with_a_free_number_and_stays_within_the_limit():
    """
    **Feature: role copy (ADM-06)**
    **Property: the suggested name is "<name> copy", then "<name> copy 2", "copy 3" when
    those are taken (case does not matter), and a very long original is shortened so the
    copy's name is still no more than 128 characters.**
    """
    long_name = "x" * 128
    testbase.assert_equal(
        (
            suggest_copy_name(name="Auditor", existing_names=["Auditor"]),
            suggest_copy_name(name="Auditor", existing_names=["Auditor", "auditor COPY"]),
            suggest_copy_name(name="Auditor", existing_names=["Auditor", "Auditor copy", "Auditor copy 2"]),
            len(suggest_copy_name(name=long_name, existing_names=[long_name])),
            suggest_copy_name(name=long_name, existing_names=[long_name]).endswith(" copy"),
        ),
        ("Auditor copy", "Auditor copy 2", "Auditor copy 3", 128, True),
    )
    return


def test_the_create_form_started_from_a_role_has_its_permissions_ticked_and_a_name_to_change():
    """
    **Feature: role copy (ADM-06)**
    **Property: opening the create form with ``copy_from`` a built-in role gives a suggested
    name, the role's description, exactly the role's permissions ticked, a note saying what it
    is a copy of, and the chooser set to that role; without ``copy_from`` nothing is ticked.**
    """
    cookies = adm.admin_cookies()
    auditor_id = _role_id(cookies, "auditor")
    detail = adm.get(path="/admin/roles/" + auditor_id, cookies=cookies).text
    expected = int(re.search(r"Permissions \((\d+)\)", detail).group(1))

    copy = adm.get(path="/admin/roles/create", query={"copy_from": auditor_id}, cookies=cookies)
    blank = adm.get(path="/admin/roles/create", cookies=cookies)
    selected = re.search(r'<option value="' + auditor_id + r'" selected>', copy.text) is not None

    testbase.assert_equal(
        (
            copy.status_code, _field_value(copy.text, "name"), len(_ticked(copy.text)) == expected and expected > 0,
            'data-role="copy-note"' in copy.text and "Copy of auditor" in copy.text, selected,
            blank.status_code, _ticked(blank.text), 'data-role="copy-note"' in blank.text, 'data-role="start-from"' in blank.text,
        ),
        (200, "auditor copy", True, True, True, 200, [], False, True),
    )
    return


def test_submitting_the_copy_makes_a_custom_role_with_the_same_permissions_and_a_second_copy_gets_the_next_name():
    """
    **Feature: role copy (ADM-06)**
    **Property: creating from the pre-filled form yields a custom role that grants what the
    original does; copying the original again offers the next free name; the original is
    unchanged.**
    """
    cookies = adm.admin_cookies()
    source_name = _unique("copy-source")
    keys = ["system:rbac.read", "system:users.read", "system:builds.read"]
    created = adm.post_form(
        path="/admin/roles/create", cookies=cookies,
        fields=[("name", source_name), ("description", "Reads things"), *[("permission_keys", key) for key in keys]],
    )
    source_id = _role_id(cookies, source_name)

    form = adm.get(path="/admin/roles/create", query={"copy_from": source_id}, cookies=cookies).text
    copy_name = _field_value(form, "name")
    submitted = adm.post_form(
        path="/admin/roles/create", cookies=cookies,
        fields=[("name", copy_name), ("description", "Reads things"), *[("permission_keys", key) for key in _ticked(form)]],
    )
    copy_id = _role_id(cookies, copy_name)
    copy_detail = adm.get(path="/admin/roles/" + copy_id, cookies=cookies).text
    source_detail = adm.get(path="/admin/roles/" + source_id, cookies=cookies).text
    second = _field_value(adm.get(path="/admin/roles/create", query={"copy_from": source_id}, cookies=cookies).text, "name")

    testbase.assert_equal(
        (
            created.status_code, _ticked(form), copy_name, submitted.status_code,
            "Custom Role" in copy_detail, "Permissions (3)" in copy_detail, "Permissions (3)" in source_detail, second,
        ),
        (303, sorted(keys), source_name + " copy", 303, True, True, True, source_name + " copy 2"),
    )
    return


def test_a_role_to_copy_that_does_not_exist_gives_an_empty_form_and_says_so():
    """
    **Feature: role copy (ADM-06)**
    **Property: ``copy_from`` naming no role (or not an id) opens the ordinary empty form with a
    warning, not an error page.**
    """
    cookies = adm.admin_cookies()
    missing = adm.get(path="/admin/roles/create", query={"copy_from": str(uuid.uuid4())}, cookies=cookies)
    garbage = adm.get(path="/admin/roles/create", query={"copy_from": "not-an-id"}, cookies=cookies)

    testbase.assert_equal(
        (
            missing.status_code, "The role to copy was not found" in missing.text, _field_value(missing.text, "name"), _ticked(missing.text),
            garbage.status_code, "The role to copy was not found" in garbage.text,
        ),
        (200, True, "", [], 200, True),
    )
    return


def test_every_role_offers_copy_and_a_built_in_one_says_that_copying_is_how_to_change_it():
    """
    **Feature: role copy (ADM-06)**
    **Property: the roles list has a Copy link on every row and the role page has a Copy Role
    button pointing at ``copy_from=<its id>``; a built-in role's page says to copy it to get a
    version that can be changed and offers neither Edit nor Delete.**
    """
    cookies = adm.admin_cookies()
    auditor_id = _role_id(cookies, "auditor")
    listing = adm.get(path="/admin/roles", cookies=cookies).text
    detail = adm.get(path="/admin/roles/" + auditor_id, cookies=cookies).text

    testbase.assert_equal(
        (
            listing.count('data-role="copy-role"') >= len(_role_links(listing)),
            'href="/admin/roles/create?copy_from={}"'.format(auditor_id) in detail,
            "Copy it to make a version you can change" in detail,
            "Edit Role" in detail, "Delete Role" in detail,
        ),
        (True, True, True, False, False),
    )
    return


def _bind(*, user_id: str, role_id: str, scope: str, scope_id: Optional[str] = None) -> None:
    from ccai.pychestrate.webservice.security.rbac.models import (  # noqa: E402
        BindingScope, PrincipalKind, RbacRoleBinding,
    )
    session = adm.open_db_session()
    try:
        session.add(RbacRoleBinding(
            binding_id=uuid.uuid4(), role_id=uuid.UUID(role_id), principal_kind=PrincipalKind.USER,
            principal_id=uuid.UUID(user_id), scope_kind=BindingScope[scope],
            scope_id=uuid.UUID(scope_id) if scope_id is not None else None, inherits_into_project=False,
        ))
        session.commit()
    finally:
        session.close()
    return


def test_the_role_page_lists_who_has_the_role_by_name_and_where_it_applies():
    """
    **Feature: role holders (ADM-06)**
    **Property: a role held by a user everywhere, by a user in a project, and by a deactivated
    user is listed with each person's name linked to their page, the project's name (or that
    it no longer exists) and a Deactivated mark; the heading counts them all; a role nobody has
    says so and how to give it.**
    """
    from ccai.pychestrate.webservice.identity.users.models import IdentityUser, UserStatus  # noqa: E402
    from ccai.pychestrate.webservice.projects.models import Project  # noqa: E402

    cookies = adm.admin_cookies()
    role_name = _unique("holders-role")
    adm.post_form(path="/admin/roles/create", cookies=cookies, fields=[("name", role_name), ("permission_keys", "system:rbac.read")])
    role_id = _role_id(cookies, role_name)
    empty = adm.get(path="/admin/roles/" + role_id, cookies=cookies).text

    everywhere = ensure_seeded_user(login=_unique("holder-a"))
    in_project = ensure_seeded_user(login=_unique("holder-b"))
    gone = ensure_seeded_user(login=_unique("holder-c"))
    project_id = str(uuid.uuid4())
    session = adm.open_db_session()
    try:
        session.add(Project(project_id=uuid.UUID(project_id), slug=_unique("holders-proj"), display_name="Holders Project"))
        session.query(IdentityUser).filter(IdentityUser.user_id == uuid.UUID(gone.user_id)).update({"status": UserStatus.DEACTIVATED})
        session.commit()
    finally:
        session.close()
    _bind(user_id=everywhere.user_id, role_id=role_id, scope="SYSTEM")
    _bind(user_id=in_project.user_id, role_id=role_id, scope="PROJECT", scope_id=project_id)
    _bind(user_id=gone.user_id, role_id=role_id, scope="PROJECT", scope_id=str(uuid.uuid4()))

    page = adm.get(path="/admin/roles/" + role_id, cookies=cookies).text
    card = page[page.index('data-role="role-holders"'):]
    rows = re.findall(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>", card, re.S)
    by_login = {re.sub(r"<[^>]+>", "", login).strip(): (re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", name)).strip(), where.strip(), name) for name, login, where in rows}

    testbase.assert_equal(
        (
            "Who has this role (0)" in empty and "Nobody has this role yet" in empty,
            "Who has this role (3)" in page,
            sorted(by_login),
            by_login[everywhere.login][1], by_login[in_project.login][1], by_login[gone.login][1],
            'href="/admin/users/{}"'.format(everywhere.user_id) in by_login[everywhere.login][2],
            "Deactivated" in by_login[gone.login][0], "Deactivated" in by_login[everywhere.login][0],
        ),
        (
            True, True, sorted([everywhere.login, in_project.login, gone.login]),
            "Everywhere", "Holders Project", "A project that no longer exists", True, True, False,
        ),
    )
    return


def test_a_person_who_may_read_roles_but_not_users_sees_only_the_count_and_no_change_buttons():
    """
    **Feature: role holders (ADM-06)**
    **Property: someone allowed to open the admin console and read roles, but not to view users
    or administer roles, sees the count on a role page but not who has it, and is not offered
    Copy, Edit, Delete or Create; the create page itself still refuses them.**
    """
    cookies = adm.admin_cookies()
    limited_role = _unique("read-roles-only")
    adm.post_form(
        path="/admin/roles/create", cookies=cookies,
        fields=[("name", limited_role), ("permission_keys", "system:rbac.read"), ("permission_keys", identity_admin.ADMIN_UI_PERMISSION_KEY)],
    )
    watched_role = _unique("watched-role")
    adm.post_form(path="/admin/roles/create", cookies=cookies, fields=[("name", watched_role), ("permission_keys", "system:rbac.read")])
    watched_id = _role_id(cookies, watched_role)
    holder = ensure_seeded_user(login=_unique("watched-holder"))
    _bind(user_id=holder.user_id, role_id=watched_id, scope="SYSTEM")

    limited = ensure_seeded_user(login=_unique("limited"))
    grant_role_to_user(user_id=limited.user_id, role_name=limited_role)
    limited_cookies = login_as(wsgi_app=ensure_app().wsgi_app, user=limited)

    detail = adm.get(path="/admin/roles/" + watched_id, cookies=limited_cookies)
    listing = adm.get(path="/admin/roles", cookies=limited_cookies)
    create = adm.get(path="/admin/roles/create", cookies=limited_cookies)

    testbase.assert_equal(
        (
            detail.status_code, "Who has this role (1)" in detail.text, holder.login in detail.text,
            "Naming the people who have a role needs permission to view users" in detail.text,
            "Copy Role" in detail.text or "Edit Role" in detail.text or "Delete Role" in detail.text,
            listing.status_code, 'data-role="copy-role"' in listing.text, "Create Role" in listing.text,
            create.status_code,
        ),
        (200, True, False, True, False, 200, False, False, 403),
    )
    return


def test_the_holders_query_is_capped_and_ordered_by_name():
    """
    **Feature: role holders (ADM-06)**
    **Property: ``list_role_holders`` returns holders ordered by name, returns nothing for an
    id that is not a role id, and never returns more than the limit it is given.**
    """
    cookies = adm.admin_cookies()
    role_name = _unique("capped-role")
    adm.post_form(path="/admin/roles/create", cookies=cookies, fields=[("name", role_name), ("permission_keys", "system:rbac.read")])
    role_id = _role_id(cookies, role_name)
    logins = [_unique("capped-" + letter) for letter in ("c", "a", "b")]
    for login in logins:
        _bind(user_id=ensure_seeded_user(login=login).user_id, role_id=role_id, scope="SYSTEM")

    session = adm.open_db_session()
    try:
        everyone = identity_admin.list_role_holders(db_session=session, role_id=role_id)
        capped = identity_admin.list_role_holders(db_session=session, role_id=role_id, limit=2)
        nothing = identity_admin.list_role_holders(db_session=session, role_id="not-a-uuid")
    finally:
        session.close()

    labels = [entry.label for entry in everyone]
    testbase.assert_equal(
        (len(everyone), labels == sorted(labels, key=str.lower), len(capped), nothing),
        (3, True, 2, []),
    )
    return
