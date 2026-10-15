"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_workflow_roles_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Standard roles for the common workflows: Read-only, Tester, Developer, Release manager, Lab manager, Platform operator (ADM-06).

.. moduleauthor:: Code Craft AI LLC

Building a role meant choosing from 73 permission keys, so the first job on a new installation was working out what a tester or a developer needs. The
service now ships six built-in roles for the common workflows. Each is what anyone who works in the product may see plus what the role does, none holds an
administrative key, every one shows complete menu entries, and an administrator who wants a variation copies one. This file pins those properties, that the
Roles page shows the roles with their descriptions (built-in roles used to be listed with a blank one), and that a custom role of the same name is
never replaced.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import csv
import io
import re
import uuid

from typing import Any, Dict, List, Set

from ccai import testbase

from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing
from ccai.pychestrate.webservice.security import rbac
from ccai.pychestrate.webservice.security.rbac.extensions.core_permissions import _CORE_PERMISSION_DESCRIPTIONS
from ccai.pychestrate.webservice.security.rbac.extensions.workflow_roles import (
    DEVELOPER_KEYS,
    LAB_MANAGER_KEYS,
    PLATFORM_OPERATOR_KEYS,
    READ_ONLY_KEYS,
    RELEASE_MANAGER_KEYS,
    TESTER_KEYS,
    WORKFLOW_ROLES,
)
from ccai.pychestrate.webservice.security.rbac.models import PermissionEffect, RbacRole, RbacRolePermission, RoleSource
from ccai.pychestrate.webservice.webinterface.blueprints.config import identity_admin
from ccai.pychestrate.webservice.webinterface.foundation.permission_presentation import menu_preview_data

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session
from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm


NAMES = ["read-only", "tester", "developer", "release-manager", "lab-manager", "platform-operator"]

#: Keys that only ``system-admin`` holds: people, access, secrets, sign-in, audit, the Admin menu, backups to restore, feature flags and more.
ADMIN_ONLY = {
    "system:users.read", "system:users.write", "system:groups.admin", "system:rbac.admin", "system:rbac.read", "system:secrets.admin",
    "system:secrets.read", "system:secrets.write", "system:audit.read", "system:flags.admin", "system:directory.sync", "system:auth.admin",
    "system:auth.read", "system:ui.admin.view", "system:ui.profile.manage", "system:backups.write", "system:projects.write",
    "system:projects.members.manage", "system:rpa.job_types.manage", "system:plugin_api.read", "system:source_integrations.write",
    "system:metrics.write", "system:embed.read", "system:embed.sign",
}


def _keys_by_name() -> Dict[str, Set[str]]:
    return {role.role_name: {grant.permission_key for grant in role.permissions} for role in WORKFLOW_ROLES}


def test_the_six_roles_exist_with_valid_keys_a_description_and_no_repeats():
    """
    **Feature: workflow roles (ADM-06)**
    **Property: the six presets are named read-only, tester, developer, release-manager, lab-manager and platform-operator; each grants only keys
    the catalog knows, only ALLOW, each once; each has a description of a sentence or more; none is called "viewer" (a name the test users and
    the project roles already use).**
    """
    problems: List[str] = []
    for role in WORKFLOW_ROLES:
        keys = [grant.permission_key for grant in role.permissions]
        problems += [role.role_name + ": unknown " + key for key in keys if key not in _CORE_PERMISSION_DESCRIPTIONS]
        problems += [role.role_name + ": repeated" for _ in range(len(keys) - len(set(keys)))]
        problems += [role.role_name + ": not allow" for grant in role.permissions if grant.effect != PermissionEffect.ALLOW]
        if len(role.description) < 40:
            problems.append(role.role_name + ": description too short")

    testbase.assert_equal(([role.role_name for role in WORKFLOW_ROLES], problems, "viewer" in NAMES), (NAMES, [], False))
    return


def test_each_role_is_the_read_only_set_plus_what_it_does_and_developers_do_what_testers_do():
    """
    **Feature: workflow roles (ADM-06)**
    **Property: every role contains all of read-only; tester is a subset of developer; and each role has something of its own beyond read-only.**
    """
    keys = _keys_by_name()
    base = set(READ_ONLY_KEYS)

    testbase.assert_equal(
        (
            all(base <= keys[name] for name in NAMES), keys["read-only"] == base, set(TESTER_KEYS) <= set(DEVELOPER_KEYS),
            keys["tester"] <= keys["developer"], all(len(keys[name] - base) > 0 for name in NAMES if name != "read-only"),
        ),
        (True, True, True, True, True),
    )
    return


def test_none_of_them_holds_an_administrative_key_and_read_only_changes_nothing():
    """
    **Feature: workflow roles (ADM-06)**
    **Property: no workflow role grants a key that only system-admin should hold (people, roles, secret values, sign-in, audit, the Admin menu,
    restoring backups, feature flags, creating projects); read-only holds only ``.read`` keys.**
    """
    keys = _keys_by_name()
    admin_keys = {name: sorted(held & ADMIN_ONLY) for name, held in keys.items() if held & ADMIN_ONLY}
    writes = sorted(key for key in keys["read-only"] if not key.endswith(".read"))

    testbase.assert_equal((admin_keys, writes), ({}, []))
    return


def test_each_role_does_what_its_name_says_and_not_what_belongs_to_the_next():
    """
    **Feature: workflow roles (ADM-06)**
    **Property: a tester can run tests and keep the catalog but not start builds; a developer can start builds and pipelines but not publish to a
    channel or manage devices; a release manager publishes to channels but does not edit pipelines; a lab manager manages devices and pools but
    does not start tests; a platform operator manages environments, provisioning and pods but not restore backups; nobody but system-admin
    can restore a backup.**
    """
    keys = _keys_by_name()

    testbase.assert_equal(
        (
            {"system:test_runs.create", "system:test_catalog.write"} <= keys["tester"], "system:builds.create" in keys["tester"],
            {"system:builds.create", "system:pipelines.run", "system:pipelines.write"} <= keys["developer"],
            "system:release_channels.write" in keys["developer"], "system:resources.manage" in keys["developer"],
            {"system:release_channels.write", "system:release_templates.write", "system:builds.create"} <= keys["release-manager"],
            "system:pipelines.write" in keys["release-manager"],
            {"system:resources.write", "system:resources.manage", "system:resource_pools.write"} <= keys["lab-manager"],
            "system:test_runs.create" in keys["lab-manager"],
            {"system:environments.write", "system:provisioning.create", "system:pods.write"} <= keys["platform-operator"],
            [name for name in NAMES if "system:backups.write" in keys[name]],
        ),
        (True, False, True, False, False, True, False, True, False, True, []),
    )
    return


def test_every_role_shows_whole_menu_entries_and_the_workflow_ones_show_the_pages_they_use():
    """
    **Feature: workflow roles (ADM-06)**
    **Property: outside the Admin menu (which needs ``system:ui.admin.view``, held only by system-admin) no role holds only part of what a menu
    entry needs, so no entry is half-shown; read-only shows Runs, Builds, Dashboards and Resources and Pools; every other role shows at least as many
    entries as read-only.**
    """
    data = menu_preview_data()
    keys = _keys_by_name()
    half_shown: List[str] = []
    shown: Dict[str, Set[str]] = {}
    for name in NAMES:
        shown[name] = set()
        for entry in data["entries"]:
            if entry["label"].startswith("Admin ›") or entry["label"].startswith("Projects ›"):
                continue
            missing = [key for key in entry["needs"] if key not in keys[name]]
            if len(missing) == 0:
                shown[name].add(entry["label"])
            elif len(missing) < len(entry["needs"]):
                half_shown.append("{}: {}".format(name, entry["label"]))

    testbase.assert_equal(
        (
            half_shown, {"Orchestration › Runs", "Orchestration › Builds", "Insights › Dashboards", "Fleet › Resources and Pools"} <= shown["read-only"],
            all(shown["read-only"] <= shown[name] for name in NAMES),
        ),
        ([], True, True),
    )
    return


def _session() -> Any:
    reset_registry_for_testing()
    rbac.register_builtin_extensions()
    _engine, session = build_in_memory_session()
    return session


def test_persisting_the_catalog_keeps_the_descriptions_and_never_touches_a_custom_role_of_the_same_name():
    """
    **Feature: workflow roles (ADM-06)**
    **Property: persisting the catalog creates a row for each role with the catalog's description; a built-in row that was stored with a blank
    description (as every one was before) gets it; a custom role called "tester", made before, stays custom with its own description and its one
    permission and is not duplicated.**
    """
    session = _session()
    session.add(RbacRole(role_id=uuid.uuid4(), role_name="auditor", source=RoleSource.BUILTIN, source_name="auditor", description=""))
    mine = RbacRole(role_id=uuid.uuid4(), role_name="tester", source=RoleSource.CUSTOM, source_name=None, description="my own testers")
    session.add(mine)
    session.add(RbacRolePermission(role_id=mine.role_id, permission_key="system:runs.read", effect=PermissionEffect.ALLOW))
    session.commit()

    identity_admin.ensure_catalog_roles_persisted(db_session=session)
    identity_admin.ensure_catalog_roles_persisted(db_session=session)

    rows = {row.role_name: row for row in session.query(RbacRole).all()}
    permissions = [row.permission_key for row in session.query(RbacRolePermission).filter(RbacRolePermission.role_id == mine.role_id).all()]
    testers = session.query(RbacRole).filter(RbacRole.role_name == "tester").count()

    testbase.assert_equal(
        (
            all(name in rows for name in NAMES), rows["auditor"].description, rows["developer"].description.startswith("Everything a Tester can do"),
            rows["tester"].source, rows["tester"].description, permissions, testers,
        ),
        (True, "Read-only access to audit records and RBAC catalog.", True, RoleSource.CUSTOM, "my own testers", ["system:runs.read"], 1),
    )
    return


def _rows(body: str) -> List[Dict[str, str]]:
    return list(csv.DictReader(io.StringIO(body)))


def test_the_roles_page_lists_them_as_built_in_with_their_descriptions_and_copy_ticks_their_permissions():
    """
    **Feature: workflow roles (ADM-06)**
    **Property: the Roles page's CSV lists the six as built-in with their descriptions and the right permission counts; the page links each; Copy Role
    on tester opens the create form with exactly the tester's permission keys ticked; opening a built-in role's edit address goes to its page with a
    message pointing at Copy Role (not a form that would be refused), while a custom role's edit form still opens.**
    """
    cookies = adm.admin_cookies()
    export = adm.get(path="/admin/roles", cookies=cookies, query={"format": "csv"})
    rows = {row["name"]: row for row in _rows(export.text)}
    page = adm.get(path="/admin/roles", cookies=cookies).text
    links = {name: role_id for role_id, name in re.findall(r'href="/admin/roles/([0-9a-f-]{36})"[^>]*>\s*([^<]+?)\s*</a>', page)}
    copy = adm.get(path="/admin/roles/create", cookies=cookies, query={"copy_from": links["tester"]}).text
    ticked = sorted(
        match.group(1) for tag in re.findall(r'<input[^>]*name="permission_keys"[^>]*>', copy) if " checked" in tag
        for match in [re.search(r'value="([^"]+)"', tag)] if match is not None
    )
    editing = adm.get(path="/admin/roles/{}/edit".format(links["tester"]), cookies=cookies)
    landed = adm.get(path=editing.header("Location") or "/admin/roles", cookies=adm.merge_cookies(cookies=cookies, response=editing))
    custom = "custom-" + uuid.uuid4().hex[:8]
    adm.post_form(path="/admin/roles/create", cookies=cookies, fields=[("name", custom), ("description", "d"), ("permission_keys", "system:runs.read")])
    custom_id = {name: rid for rid, name in re.findall(r'href="/admin/roles/([0-9a-f-]{36})"[^>]*>\s*([^<]+?)\s*</a>', adm.get(path="/admin/roles", cookies=cookies).text)}[custom]
    custom_edit = adm.get(path="/admin/roles/{}/edit".format(custom_id), cookies=cookies)

    testbase.assert_equal(
        (
            [rows[name]["type"] for name in NAMES], [int(rows[name]["permissions"]) for name in NAMES], rows["tester"]["description"].startswith("Everything Read-only"),
            all(name in links for name in NAMES), ticked == sorted(TESTER_KEYS),
            editing.status_code in (302, 303), (editing.header("Location") or "").endswith("/admin/roles/" + links["tester"]),
            "Copy Role" in landed.text and "cannot be changed" in landed.text, custom_edit.status_code, 'name="permission_keys"' in custom_edit.text,
        ),
        (
            ["built-in"] * 6, [len(READ_ONLY_KEYS), len(TESTER_KEYS), len(DEVELOPER_KEYS), len(RELEASE_MANAGER_KEYS), len(LAB_MANAGER_KEYS), len(PLATFORM_OPERATOR_KEYS)],
            True, True, True, True, True, True, 200, True,
        ),
    )
    return
