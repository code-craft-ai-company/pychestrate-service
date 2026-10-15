"""
.. module:: test_p40b_ui_profiles_m1
    :synopsis: Tests for 9-ui-profiles M1 -- surface vocabulary, effective
               profile maths, manifest filtering, deployment persistence,
               and the request-scoped jinja global.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import itertools

from typing import List

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.orm import PychestrateModelBase

from ccai.pychestrate.webservice.security.rbac.extensions.core_permissions import (
    CorePermissionExtension,
)
from ccai.pychestrate.webservice.webinterface.site_shell import ui_profile
from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import (
    NAV_ENTRIES,
    NAV_GROUPS,
    build_navigation_manifest,
    governed_entry_counts,
    validate_manifest_surfaces,
)


def _all_manifest_permission_keys() -> List[str]:
    keys = set()
    for group in NAV_GROUPS:
        keys.update(group.required_permissions)
    for entry in NAV_ENTRIES:
        keys.update(entry.required_permissions)
    rtnval = list(keys)
    return rtnval


def _entry_ids(manifest: dict) -> List[str]:
    rtnval: List[str] = []
    for group in manifest["groups"]:
        for entry in group["entries"]:
            rtnval.append(entry["entry_id"])
    return rtnval


def _core_session():
    # The deployment profile is a SYSTEM variable of the modern store (audit ADM-08), so the database needs those tables too.
    from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base
    import ccai.pychestrate.webservice.variables.models  # noqa: F401 -- registers the variable tables

    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    PychestratePhase1Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return session


# ---------------------------------------------------------------------------
# Vocabulary + parsing
# ---------------------------------------------------------------------------


def test_surface_vocabulary_is_fixed_and_described():
    """
    **Feature: 9-ui-profiles (M1)**
    **Property: the four surfaces each carry a display name and a
    description, and the manifest tags only known surfaces.**
    """
    testbase.assert_equal(
        ui_profile.ALL_SURFACE_VALUES, ("build", "testing", "rpa", "infra"),
    )
    for surface in ui_profile.SURFACE_ORDER:
        testbase.assert_true(len(ui_profile.SURFACE_DISPLAY[surface]) > 0)
        testbase.assert_true(len(ui_profile.SURFACE_DESCRIPTIONS[surface]) > 0)
    testbase.assert_equal(validate_manifest_surfaces(), [])
    counts = governed_entry_counts()
    for surface in ("build", "testing", "infra"):
        testbase.assert_true(counts.get(surface, 0) > 0)
    return


def test_parse_surfaces_accepts_lists_json_and_csv():
    """
    **Feature: 9-ui-profiles (M1)**
    **Property: parse_surfaces reads JSON text, Python lists, and
    comma-separated text; unknown names are reported, not swallowed.**
    """
    parsed, issues = ui_profile.parse_surfaces('["build", "rpa"]')
    testbase.assert_equal(parsed, frozenset({ui_profile.UiSurface.BUILD, ui_profile.UiSurface.RPA}))
    testbase.assert_equal(issues, [])

    parsed, issues = ui_profile.parse_surfaces(["testing", "TESTING", "bogus"])
    testbase.assert_equal(parsed, frozenset({ui_profile.UiSurface.TESTING}))
    testbase.assert_equal(len(issues), 1)

    parsed, issues = ui_profile.parse_surfaces("infra, build")
    testbase.assert_equal(parsed, frozenset({ui_profile.UiSurface.INFRA, ui_profile.UiSurface.BUILD}))

    parsed, issues = ui_profile.parse_surfaces("not json [")
    testbase.assert_equal(parsed, frozenset())
    testbase.assert_true(len(issues) > 0)

    parsed, issues = ui_profile.parse_surfaces(None)
    testbase.assert_true(parsed is None)
    return


def test_effective_set_is_well_defined():
    """
    **Feature: 9-ui-profiles (M1)**
    **Property 2: for every deployment set D and override O the
    effective set is O ∩ D when non-empty, else D; it is never empty
    and never leaves D.**
    """
    members = list(ui_profile.SURFACE_ORDER)
    subsets = []
    for size in range(0, len(members) + 1):
        for combo in itertools.combinations(members, size):
            subsets.append(frozenset(combo))
    for deployment in subsets:
        if len(deployment) == 0:
            continue
        for override in subsets + [None]:
            effective, reset = ui_profile.compute_effective(deployment=deployment, override=override)
            testbase.assert_true(len(effective) > 0)
            testbase.assert_true(effective <= deployment)
            if override is None:
                testbase.assert_equal(effective, deployment)
                testbase.assert_equal(reset, False)
            elif len(override & deployment) == 0:
                testbase.assert_equal(effective, deployment)
                testbase.assert_equal(reset, True)
            else:
                testbase.assert_equal(effective, override & deployment)
                testbase.assert_equal(reset, False)
    # An empty deployment set is treated as "everything".
    effective, _reset = ui_profile.compute_effective(deployment=frozenset(), override=None)
    testbase.assert_equal(effective, ui_profile.ALL_SURFACES)
    return


# ---------------------------------------------------------------------------
# Manifest filtering
# ---------------------------------------------------------------------------


def test_manifest_filtering_is_monotonic_and_keeps_core():
    """
    **Feature: 9-ui-profiles (M1)**
    **Property 1: for surface sets A ⊆ B the entries shown under A are a
    subset of those under B; core entries (no surface tag) show under
    every subset; no group ever renders empty.**
    """
    held = _all_manifest_permission_keys()
    members = list(ui_profile.ALL_SURFACE_VALUES)
    core_ids = [e.entry_id for e in NAV_ENTRIES if len(e.surfaces) == 0]
    shown = {}
    for size in range(0, len(members) + 1):
        for combo in itertools.combinations(members, size):
            manifest = build_navigation_manifest(held_permissions=held, enabled_surfaces=combo)
            ids = set(_entry_ids(manifest))
            shown[frozenset(combo)] = ids
            for core_id in core_ids:
                testbase.assert_true(core_id in ids)
            for group in manifest["groups"]:
                testbase.assert_true(len(group["entries"]) > 0)
    for a, ids_a in shown.items():
        for b, ids_b in shown.items():
            if a <= b:
                testbase.assert_true(ids_a <= ids_b)
    everything = build_navigation_manifest(held_permissions=held)
    testbase.assert_equal(set(_entry_ids(everything)), shown[frozenset(members)])
    testbase.assert_equal(len(_entry_ids(everything)), len(NAV_ENTRIES))
    return


def test_rpa_only_profile_hides_build_testing_and_infra_entries():
    """
    **Feature: 9-ui-profiles (M1)**
    **Property: with only the rpa surface enabled the Builds, Test
    Catalog, and Environments entries are hidden while Runs (tagged
    with rpa too) and every admin entry remain.**
    """
    held = _all_manifest_permission_keys()
    manifest = build_navigation_manifest(held_permissions=held, enabled_surfaces=("rpa",))
    ids = set(_entry_ids(manifest))
    for hidden in ("orchestration.builds", "orchestration.test-catalog", "orchestration.environments",
                   "insights.test-metrics"):
        testbase.assert_true(hidden not in ids)
    for kept in ("orchestration.runs", "admin.overview", "admin.ui-profile", "projects.dashboard",
                 "fleet.pods"):
        testbase.assert_true(kept in ids)
    for group in manifest["groups"]:
        for entry in group["entries"]:
            testbase.assert_true(isinstance(entry["surfaces"], list))
    return


def test_ui_profile_permission_is_declared_and_admin_entry_present():
    """
    **Feature: 9-ui-profiles (M1)**
    **Property: the admin UI Profile entry requires a permission the
    core catalog declares, so the entry is reachable for admins.**
    """
    declared = set(CorePermissionExtension.permission_keys)
    testbase.assert_true("system:ui.profile.manage" in declared)
    testbase.assert_true("system:rpa.read" in declared)
    entries = [e for e in NAV_ENTRIES if e.entry_id == "admin.ui-profile"]
    testbase.assert_equal(len(entries), 1)
    testbase.assert_equal(entries[0].route, "/admin/ui-profile")
    return


# ---------------------------------------------------------------------------
# Deployment persistence
# ---------------------------------------------------------------------------


def test_deployment_surfaces_round_trip_through_variable_store():
    """
    **Feature: 9-ui-profiles (M1)**
    **Property 3: saving a valid list persists it as the
    ui.profile.surfaces global variable and reading it back yields the
    same set in canonical order; absent or invalid values fall back to
    every surface.**
    """
    session = _core_session()
    ui_profile.invalidate_deployment_cache()

    testbase.assert_equal(
        ui_profile.resolve_deployment_surfaces(db_session=session, use_cache=False),
        ui_profile.ALL_SURFACES,
    )

    saved = ui_profile.set_deployment_surfaces(
        db_session=session, surfaces=["rpa", "build"], actor_id=None,
    )
    testbase.assert_equal(saved, frozenset({ui_profile.UiSurface.RPA, ui_profile.UiSurface.BUILD}))
    resolved = ui_profile.resolve_deployment_surfaces(db_session=session, use_cache=False)
    testbase.assert_equal(resolved, saved)

    profile = ui_profile.resolve_profile(db_session=session)
    testbase.assert_equal(profile.effective_values, ["build", "rpa"])
    testbase.assert_equal(profile.hidden_values, ["testing", "infra"])
    testbase.assert_true(profile.is_enabled("rpa"))
    testbase.assert_true(profile.is_enabled("build"))
    testbase.assert_true(not profile.is_enabled("testing"))
    testbase.assert_true(profile.is_enabled("unknown-tag"))
    testbase.assert_true(profile.any_enabled(()))
    testbase.assert_true(profile.any_enabled(("testing", "rpa")))
    testbase.assert_true(not profile.any_enabled(("testing", "infra")))

    saved = ui_profile.set_deployment_surfaces(db_session=session, surfaces=["testing"])
    resolved = ui_profile.resolve_deployment_surfaces(db_session=session, use_cache=False)
    testbase.assert_equal(resolved, frozenset({ui_profile.UiSurface.TESTING}))

    raised = False
    try:
        ui_profile.set_deployment_surfaces(db_session=session, surfaces=[])
    except ValueError:
        raised = True
    testbase.assert_true(raised)
    raised = False
    try:
        ui_profile.set_deployment_surfaces(db_session=session, surfaces=["build", "nope"])
    except ValueError:
        raised = True
    testbase.assert_true(raised)

    payload = profile.to_dict()
    testbase.assert_equal(payload["effective_surfaces"], ["build", "rpa"])
    testbase.assert_equal(len(payload["surfaces"]), 4)
    ui_profile.invalidate_deployment_cache()
    session.close()
    return


def test_request_scope_publishes_profile_to_the_jinja_proxy():
    """
    **Feature: 9-ui-profiles (M1)**
    **Property: outside a request the proxy reports every surface;
    inside a scope it reports the published profile and reverts when
    the scope exits.**
    """
    proxy = ui_profile.UiProfileProxy()
    testbase.assert_equal(proxy.effective_values, list(ui_profile.ALL_SURFACE_VALUES))

    narrowed = ui_profile.build_profile(deployment=frozenset({ui_profile.UiSurface.RPA}))
    token = ui_profile.set_current_profile(narrowed)
    try:
        testbase.assert_equal(proxy.effective_values, ["rpa"])
        testbase.assert_true(not proxy.is_enabled("build"))
    finally:
        ui_profile.reset_current_profile(token)
    testbase.assert_true(proxy.is_enabled("build"))

    ui_profile.invalidate_deployment_cache()
    with ui_profile.request_profile_scope() as profile:
        # No session factory is configured in this test process, so
        # the scope resolves the default profile rather than failing.
        testbase.assert_equal(profile.effective_surfaces, ui_profile.ALL_SURFACES)
        testbase.assert_equal(proxy.effective_values, list(ui_profile.ALL_SURFACE_VALUES))
    return


# ---------------------------------------------------------------------------
# REST surface
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, *, db_session, body=b"", path="/api/v1/admin/ui-profile"):
        self.db_session = db_session
        self.auth_principal = object()
        self.body = body
        self.path = path
        return


def test_admin_ui_profile_rest_get_and_put_round_trip():
    """
    **Feature: 9-ui-profiles (M1)**
    **Property: GET returns the deployment surfaces and governed-entry
    counts; PUT persists a valid list and rejects unknown or empty
    lists with 422; a denied principal gets the problem response.**
    """
    import json as _json
    from ccai.pychestrate.webservice.webinterface.site_shell import ui_profile_routes as routes

    session = _core_session()
    ui_profile.invalidate_deployment_cache()
    original_authorize = routes._authorize
    routes._authorize = lambda *, request: None
    try:
        response = routes.handle_get_ui_profile(_FakeRequest(db_session=session))
        testbase.assert_equal(response.status_code, 200)
        body = _json.loads(response._body.decode("utf-8"))
        testbase.assert_equal(body["surfaces"], list(ui_profile.ALL_SURFACE_VALUES))
        testbase.assert_true(body["governed_entries"]["build"] > 0)

        response = routes.handle_put_ui_profile(
            _FakeRequest(db_session=session, body=_json.dumps({"surfaces": ["rpa"]}).encode("utf-8")),
        )
        testbase.assert_equal(response.status_code, 200)
        body = _json.loads(response._body.decode("utf-8"))
        testbase.assert_equal(body["surfaces"], ["rpa"])

        response = routes.handle_put_ui_profile(
            _FakeRequest(db_session=session, body=_json.dumps({"surfaces": []}).encode("utf-8")),
        )
        testbase.assert_equal(response.status_code, 422)
        response = routes.handle_put_ui_profile(
            _FakeRequest(db_session=session, body=_json.dumps({"surfaces": ["nope"]}).encode("utf-8")),
        )
        testbase.assert_equal(response.status_code, 422)
        response = routes.handle_put_ui_profile(_FakeRequest(db_session=session, body=b"not json"))
        testbase.assert_equal(response.status_code, 400)
    finally:
        routes._authorize = original_authorize
        ui_profile.invalidate_deployment_cache()

    anonymous = _FakeRequest(db_session=session)
    anonymous.auth_principal = None
    response = routes.handle_get_ui_profile(anonymous)
    testbase.assert_equal(response.status_code, 401)
    session.close()
    return


# ---------------------------------------------------------------------------
# M2: per-user override + /api/v1/me/preferences/ui.surfaces
# ---------------------------------------------------------------------------


def _dual_session():
    """
        One in-memory engine carrying both the core tables (global
        variables) and the Phase-1 tables (user preferences).
    """
    from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base
    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    PychestratePhase1Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return session


def test_user_override_narrows_within_deployment_and_resets_when_disjoint():
    """
    **Feature: 9-ui-profiles (M2)**
    **Property: a saved override narrows the effective set within the
    deployment; when the deployment later excludes every overridden
    surface the profile falls back and flags override_reset; clearing the
    override returns to the deployment default.**
    """
    session = _dual_session()
    ui_profile.invalidate_deployment_cache()
    user_id = "user-42"

    testbase.assert_true(ui_profile.get_user_override(db_session=session, user_id=user_id) is None)
    saved = ui_profile.set_user_override(db_session=session, user_id=user_id, surfaces=["testing", "rpa"])
    testbase.assert_equal(saved, frozenset({ui_profile.UiSurface.TESTING, ui_profile.UiSurface.RPA}))

    profile = ui_profile.resolve_profile(db_session=session, user_id=user_id)
    testbase.assert_equal(profile.effective_values, ["testing", "rpa"])
    testbase.assert_equal(profile.override_values, ["testing", "rpa"])
    testbase.assert_equal(profile.override_reset, False)

    ui_profile.set_deployment_surfaces(db_session=session, surfaces=["build"])
    ui_profile.invalidate_deployment_cache()
    profile = ui_profile.resolve_profile(db_session=session, user_id=user_id)
    testbase.assert_equal(profile.effective_values, ["build"])
    testbase.assert_equal(profile.override_reset, True)

    ui_profile.set_deployment_surfaces(db_session=session, surfaces=["build", "testing"])
    ui_profile.invalidate_deployment_cache()
    profile = ui_profile.resolve_profile(db_session=session, user_id=user_id)
    testbase.assert_equal(profile.effective_values, ["testing"])

    raised = False
    try:
        ui_profile.set_user_override(db_session=session, user_id=user_id, surfaces=[])
    except ValueError:
        raised = True
    testbase.assert_true(raised)

    testbase.assert_true(ui_profile.clear_user_override(db_session=session, user_id=user_id))
    testbase.assert_true(not ui_profile.clear_user_override(db_session=session, user_id=user_id))
    profile = ui_profile.resolve_profile(db_session=session, user_id=user_id)
    testbase.assert_equal(profile.effective_values, ["build", "testing"])
    testbase.assert_true(profile.override_surfaces is None)

    # Another user is unaffected by the first user's override.
    ui_profile.set_user_override(db_session=session, user_id=user_id, surfaces=["build"])
    other = ui_profile.resolve_profile(db_session=session, user_id="user-43")
    testbase.assert_equal(other.effective_values, ["build", "testing"])
    ui_profile.invalidate_deployment_cache()
    session.close()
    return


class _Principal:
    def __init__(self, user_id):
        self.user_id = user_id
        return


class _MeRequest:
    def __init__(self, *, db_session, user_id="user-42", body=b""):
        self.db_session = db_session
        self.auth_principal = _Principal(user_id) if user_id is not None else None
        self.body = body
        self.path = "/api/v1/me/preferences/ui.surfaces"
        return


def test_me_preferences_rest_round_trip():
    """
    **Feature: 9-ui-profiles (M2)**
    **Property: GET reports no override by default; PUT saves and narrows
    the effective set; DELETE restores the deployment default; invalid
    bodies answer 422 and anonymous callers 401.**
    """
    import json as _json
    from ccai.pychestrate.webservice.security.auth.restapi.v1 import me_routes

    session = _dual_session()
    ui_profile.invalidate_deployment_cache()

    response = me_routes.handle_get_my_ui_surfaces(_MeRequest(db_session=session))
    testbase.assert_equal(response.status_code, 200)
    body = _json.loads(response._body.decode("utf-8"))
    testbase.assert_true(body["surfaces"] is None)
    testbase.assert_equal(body["effective"], list(ui_profile.ALL_SURFACE_VALUES))

    response = me_routes.handle_put_my_ui_surfaces(
        _MeRequest(db_session=session, body=_json.dumps({"surfaces": ["rpa"]}).encode("utf-8")),
    )
    testbase.assert_equal(response.status_code, 200)
    body = _json.loads(response._body.decode("utf-8"))
    testbase.assert_equal(body["surfaces"], ["rpa"])
    testbase.assert_equal(body["effective"], ["rpa"])

    response = me_routes.handle_put_my_ui_surfaces(
        _MeRequest(db_session=session, body=_json.dumps({"surfaces": ["bogus"]}).encode("utf-8")),
    )
    testbase.assert_equal(response.status_code, 422)
    response = me_routes.handle_put_my_ui_surfaces(_MeRequest(db_session=session, body=b"[]"))
    testbase.assert_equal(response.status_code, 422)

    response = me_routes.handle_delete_my_ui_surfaces(_MeRequest(db_session=session))
    testbase.assert_equal(response.status_code, 200)
    body = _json.loads(response._body.decode("utf-8"))
    testbase.assert_true(body["surfaces"] is None)

    response = me_routes.handle_get_my_ui_surfaces(_MeRequest(db_session=session, user_id=None))
    testbase.assert_equal(response.status_code, 401)
    ui_profile.invalidate_deployment_cache()
    session.close()
    return


def test_hidden_routes_lists_surface_hidden_entries_the_caller_could_see():
    """
    **Feature: 9-ui-profiles (M2)**
    **Property: hidden_routes_for returns the routes of permitted entries
    whose surfaces are disabled, and nothing when every surface is on.**
    """
    from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import hidden_routes_for
    held = _all_manifest_permission_keys()
    hidden = hidden_routes_for(held_permissions=held, enabled_surfaces=("rpa",))
    testbase.assert_true("/builds" in hidden)
    testbase.assert_true("/test-catalog" in hidden)
    testbase.assert_true("/runs" not in hidden)
    testbase.assert_equal(hidden_routes_for(held_permissions=held, enabled_surfaces=ui_profile.ALL_SURFACE_VALUES), [])
    testbase.assert_equal(hidden_routes_for(held_permissions=[], enabled_surfaces=("rpa",)), [])
    return
