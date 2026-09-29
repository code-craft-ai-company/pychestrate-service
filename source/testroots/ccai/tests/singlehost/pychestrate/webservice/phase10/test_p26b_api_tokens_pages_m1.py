"""
.. module:: test_p26b_api_tokens_pages_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the API-token and service-account pages
               (``/account/api-tokens``, ``/admin/api-tokens``).

.. moduleauthor:: Code Craft AI LLC

Audit finding ORG-F02 asked for a token page under Account and
Admin. These tests drive :mod:`webinterface.blueprints.config.routes_tokens`
against a real in-memory database (the token service is not mocked);
only the sign-in check and the template renderer are stubbed.

Coverage:

* the route matrix and the permission each admin route declares;
* a signed-in user without any admin permission manages their own
  tokens;
* issuing a token renders its secret once in the response and never
  in the flash cookie;
* self-service revocation cannot touch another user's token;
* administrators create service accounts and issue them tokens, and
  cannot issue a token that acts as a person;
* the Admin navigation carries the page, gated like it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.identity.users import user_service
from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from ccai.pychestrate.webservice.security.auth.api_tokens import service as token_service
from ccai.pychestrate.webservice.security.auth.api_tokens.models import AuthApiToken
from ccai.pychestrate.webservice.security.rbac import catalog
from ccai.pychestrate.webservice.webinterface.blueprints.config import (
    routes as config_routes,
    routes_tokens,
)
from ccai.pychestrate.webservice.webinterface.foundation import (
    cookie_session,
    csrf,
    templating,
    url_for as url_for_module,
)
from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import NAV_ENTRIES

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)
from ccai.tests.singlehost.pychestrate.webservice.shared.webworks_test_harness import (
    RenderRecorder,
    make_fake_app,
    make_fake_request,
    make_fake_security_manager,
)


_TEST_UI_COOKIE_SECRET: bytes = b"\x00" * 32
_CSRF_TOKEN: str = "csrf-fresh"


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


class _PageHarness:
    """
        One in-memory database, a signed-in user, a render recorder,
        and the config routes registered against a fake app.
    """

    def __init__(self, *, permission_predicate: Callable[[str, str], bool]) -> None:
        reset_phase1_runtime()
        self.engine, self.session = build_in_memory_session()
        self.user = user_service.create_user(
            db_session=self.session, login_name="dana",
            primary_email="dana@example.test", display_name="Dana",
            timezone="UTC", provisioning_source="local",
            external_id=None, actor_user_id=None,
        )
        self.user_id: str = str(self.user.user_id)
        self.recorder = RenderRecorder()

        url_for_module.reset_registry_for_testing()
        templating.reset_default_environment_for_testing()
        templating.set_default_environment(environment=self.recorder.environment)
        SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = _TEST_UI_COOKIE_SECRET
        session = self.session
        SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = lambda: session

        user_id = self.user_id

        def _builder(*, db_session: Any) -> Any:
            rtnval = make_fake_security_manager(
                db_session=db_session, user_id=user_id, csrf_token=_CSRF_TOKEN,
                permission_predicate=permission_predicate,
            )
            return rtnval

        self._patch = create_module_patch(config_routes, "_build_security_manager")
        mock = self._patch.activate()
        mock.configure(side_effect=_builder)

        self.app = make_fake_app()
        config_routes.register_config_routes(app=self.app)
        return

    def close(self) -> None:
        self._patch.deactivate()
        url_for_module.reset_registry_for_testing()
        templating.reset_default_environment_for_testing()
        SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = None
        SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = None
        self.session.close()
        return

    def cookies(self) -> Dict[str, str]:
        value = cookie_session.sign_session_payload(
            payload={"user_id": self.user_id, "username": "dana", "session_token": "tok-dana"},
            secret=_TEST_UI_COOKIE_SECRET,
        )
        rtnval = {cookie_session.COOKIE_NAME: value}
        return rtnval

    def call(
            self,
            *,
            method: str,
            path: str,
            form: Optional[Dict[str, str]] = None,
            path_params: Optional[Dict[str, str]] = None
        ) -> Any:
        """
            Call the registered handler for ``path`` / ``method`` (the
            path is the route template; ``path_params`` fill it).
        """
        handler = self.app.find_handler(path=path, method=method)
        body_form = None
        if form is not None:
            body_form = dict(form)
            body_form[csrf.FORM_FIELD_NAME] = _CSRF_TOKEN
        request = make_fake_request(
            method=method, path=path, form=body_form,
            cookies=self.cookies(), path_params=path_params or {},
        )
        rtnval = handler(request)
        return rtnval

    def page_context(self, *, template_name: str) -> Dict[str, Any]:
        """
            Context of the most recent render of ``template_name`` (the
            shell wrapper renders its own document afterwards).
        """
        contexts = [
            call.context for call in self.recorder.calls if call.template_name == template_name
        ]
        rtnval = contexts[-1]
        return rtnval


def _allow_everything(user_id: str, permission: str) -> bool:
    return True


def _deny_everything(user_id: str, permission: str) -> bool:
    return False


def _cookie_payload(response: Any) -> Dict[str, Any]:
    """
        Decode the signed session cookie a response sets.
    """
    header_values = [
        value for name, value in response._get_all_headers() if name.lower() == "set-cookie"
    ]
    for header_value in header_values:
        name, _, rest = header_value.partition("=")
        if name == cookie_session.COOKIE_NAME:
            raw = rest.split(";", 1)[0]
            payload = cookie_session.verify_session_payload(
                cookie_value=raw, secret=_TEST_UI_COOKIE_SECRET
            )
            return payload or {}
    return {}


# ===========================================================================
# Registration
# ===========================================================================


def test_token_pages_register_the_documented_routes():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: register_tokens_routes attaches the account and admin
    token routes with the documented methods.**
    """
    url_for_module.reset_registry_for_testing()
    try:
        app = make_fake_app()
        routes_tokens.register_tokens_routes(app=app)
        testbase.assert_equal(
            sorted(app.route_pairs()),
            sorted([
                ("/account/api-tokens", ("GET",)),
                ("/account/api-tokens/create", ("POST",)),
                ("/account/api-tokens/{token_id}/revoke", ("POST",)),
                ("/admin/api-tokens", ("GET",)),
                ("/admin/service-accounts/create", ("POST",)),
                ("/admin/service-accounts/{user_id}/api-tokens/create", ("POST",)),
                ("/admin/api-tokens/{token_id}/revoke", ("POST",)),
            ]),
        )
    finally:
        url_for_module.reset_registry_for_testing()
    return


def test_admin_token_routes_declare_catalogued_permissions():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: the admin routes require system:auth.read to view,
    system:users.write to create service accounts, system:auth.admin
    to issue service-account tokens and revoke tokens -- all keys the
    RBAC catalog knows.**
    """
    reset_phase1_runtime()
    known = set(catalog.load_catalog_from_registry().permissions)
    declared = dict(routes_tokens._ROUTE_PERMISSIONS)
    testbase.assert_equal(
        (declared, all(key in known for key in declared.values())),
        ({
            "config.admin_api_tokens": "system:auth.read",
            "config.service_account_create": "system:users.write",
            "config.service_account_token_create": "system:auth.admin",
            "config.admin_api_token_revoke": "system:auth.admin",
        }, True),
    )
    return


def test_admin_navigation_lists_the_token_page_behind_auth_read():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: the Admin navigation carries /admin/api-tokens gated
    by the same key the page enforces.**
    """
    entries = [entry for entry in NAV_ENTRIES if entry.route == "/admin/api-tokens"]
    testbase.assert_equal(
        [(entry.group_id, entry.required_permissions) for entry in entries],
        [("admin", ["system:auth.read"])],
    )
    return


# ===========================================================================
# Account pages
# ===========================================================================


def test_user_without_admin_permissions_sees_their_token_page():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: a signed-in user holding no permission at all gets
    /account/api-tokens (a user manages their own tokens).**
    """
    harness = _PageHarness(permission_predicate=_deny_everything)
    try:
        response = harness.call(method="GET", path="/account/api-tokens")
        testbase.assert_equal(
            (response.status_code, "config/tokens/account.html" in harness.recorder.template_names()),
            (200, True),
        )
    finally:
        harness.close()
    return


def test_account_page_lists_only_the_users_own_tokens():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: /account/api-tokens lists the signed-in user's tokens
    and nobody else's.**
    """
    harness = _PageHarness(permission_predicate=_deny_everything)
    try:
        other = user_service.create_user(
            db_session=harness.session, login_name="erin", primary_email="erin@example.test",
            display_name="Erin", timezone="UTC", provisioning_source="local",
            external_id=None, actor_user_id=None,
        )
        for user_id, name in ((harness.user_id, "mine"), (str(other.user_id), "theirs")):
            token_service.create_api_token(
                db_session=harness.session, user_id=user_id, name=name,
                lifetime_days=None, scope=None, actor_user_id=user_id,
            )
        harness.call(method="GET", path="/account/api-tokens")
        names = [token.name for token in harness.page_context(template_name="config/tokens/account.html")["tokens"]]
        testbase.assert_equal(names, ["mine"])
    finally:
        harness.close()
    return


def test_issuing_a_token_shows_the_secret_once_in_the_response():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: POST /account/api-tokens/create renders the page with
    the new token's secret in the one-time panel and a pyc login
    command, and the secret is not written into the session cookie.**
    """
    harness = _PageHarness(permission_predicate=_deny_everything)
    try:
        response = harness.call(
            method="POST", path="/account/api-tokens/create",
            form={"name": "laptop", "expires_in_days": "30", "scope": "read-only"},
        )
        minted = harness.page_context(template_name="config/tokens/account.html")["minted"]
        cookie_text = str(_cookie_payload(response))
        testbase.assert_equal(
            (response.status_code, minted["token"][:4], minted["scope"],
             minted["login_command"].startswith("pyc login --server-url "),
             minted["token"] in cookie_text),
            (200, "pyc_", "read-only", True, False),
        )
    finally:
        harness.close()
    return


def test_issued_token_acts_as_the_signed_in_user():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: the token issued on the account page authenticates as
    the user who issued it.**
    """
    harness = _PageHarness(permission_predicate=_deny_everything)
    try:
        harness.call(
            method="POST", path="/account/api-tokens/create", form={"name": "laptop"},
        )
        token = harness.page_context(template_name="config/tokens/account.html")["minted"]["token"]
        from datetime import datetime, timezone  # noqa: E402
        principal = token_service.authenticate_api_token(
            db_session=harness.session, token=token, now=datetime.now(timezone.utc),
            request_method="GET", request_path="/api/v1/me",
        )
        testbase.assert_equal(principal.user_id, harness.user_id)
    finally:
        harness.close()
    return


def test_invalid_token_form_shows_the_validation_message_next_to_the_name():
    """
    **Feature: API token pages (ORG-F02, ADM-11)**
    **Property: a token form with no name answers 400 and renders the
    page with the validation message as the name field's error (no
    banner) and issues nothing.**
    """
    harness = _PageHarness(permission_predicate=_deny_everything)
    try:
        response = harness.call(
            method="POST", path="/account/api-tokens/create", form={"name": ""},
        )
        context = harness.page_context(template_name="config/tokens/account.html")
        testbase.assert_equal(
            (response.status_code, context["errors"], context["flashes"],
             harness.session.query(AuthApiToken).count()),
            (400, {"name": "A token name is required."}, [], 0),
        )
    finally:
        harness.close()
    return


def test_self_service_revoke_cannot_touch_another_users_token():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: POST /account/api-tokens/{id}/revoke naming another
    user's token reports it as not found (a 404 page) and leaves it
    active.**
    """
    harness = _PageHarness(permission_predicate=_deny_everything)
    try:
        other = user_service.create_user(
            db_session=harness.session, login_name="erin", primary_email="erin@example.test",
            display_name="Erin", timezone="UTC", provisioning_source="local",
            external_id=None, actor_user_id=None,
        )
        issued = token_service.create_api_token(
            db_session=harness.session, user_id=str(other.user_id), name="theirs",
            lifetime_days=None, scope=None, actor_user_id=str(other.user_id),
        )
        response = harness.call(
            method="POST", path="/account/api-tokens/{token_id}/revoke", form={},
            path_params={"token_id": issued.view.token_id},
        )
        view = token_service.read_api_token(db_session=harness.session, token_id=issued.view.token_id)
        testbase.assert_equal(
            (response.status_code, harness.page_context(template_name="site_shell/error_page.html")["title"], view.status),
            (404, "Token not found", "active"),
        )
    finally:
        harness.close()
    return


def test_user_revokes_their_own_token_from_the_account_page():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: POST /account/api-tokens/{id}/revoke on the user's own
    token revokes it.**
    """
    harness = _PageHarness(permission_predicate=_deny_everything)
    try:
        issued = token_service.create_api_token(
            db_session=harness.session, user_id=harness.user_id, name="mine",
            lifetime_days=None, scope=None, actor_user_id=harness.user_id,
        )
        harness.call(
            method="POST", path="/account/api-tokens/{token_id}/revoke", form={},
            path_params={"token_id": issued.view.token_id},
        )
        view = token_service.read_api_token(db_session=harness.session, token_id=issued.view.token_id)
        testbase.assert_equal(view.status, "revoked")
    finally:
        harness.close()
    return


# ===========================================================================
# Admin pages
# ===========================================================================


def test_admin_page_is_refused_without_auth_read():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: /admin/api-tokens answers 403 to a signed-in user
    without system:auth.read.**
    """
    harness = _PageHarness(permission_predicate=_deny_everything)
    try:
        response = harness.call(method="GET", path="/admin/api-tokens")
        testbase.assert_equal(response.status_code, 403)
    finally:
        harness.close()
    return


def test_admin_creates_a_service_account_from_the_page():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: POST /admin/service-accounts/create creates a service
    account the admin page then lists.**
    """
    harness = _PageHarness(permission_predicate=_allow_everything)
    try:
        harness.call(
            method="POST", path="/admin/service-accounts/create",
            form={"login_name": "ci-nightly", "display_name": "Nightly CI"},
        )
        harness.call(method="GET", path="/admin/api-tokens")
        accounts = [account.login_name for account in harness.page_context(template_name="config/tokens/admin.html")["service_accounts"]]
        testbase.assert_equal(accounts, ["ci-nightly"])
    finally:
        harness.close()
    return


def test_admin_issues_a_service_account_token_shown_once():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: issuing a service-account token renders its secret in
    the one-time panel, labelled with the service account.**
    """
    harness = _PageHarness(permission_predicate=_allow_everything)
    try:
        account = token_service.create_service_account(
            db_session=harness.session, login_name="ci", display_name="CI", actor_user_id=None,
        )
        account_id = str(account.user_id)
        response = harness.call(
            method="POST", path="/admin/service-accounts/{user_id}/api-tokens/create",
            form={"name": "nightly", "expires_in_days": "30"},
            path_params={"user_id": account_id},
        )
        minted = harness.page_context(template_name="config/tokens/admin.html")["minted"]
        testbase.assert_equal(
            (response.status_code, minted["owner_label"], minted["token"][:4]),
            (200, "ci", "pyc_"),
        )
    finally:
        harness.close()
    return


def test_admin_cannot_issue_a_token_that_acts_as_a_person():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: the service-account token form refuses a person's
    user id (a 404 "Service account not found"), so no administrator
    can mint a token that impersonates a user.**
    """
    harness = _PageHarness(permission_predicate=_allow_everything)
    try:
        response = harness.call(
            method="POST", path="/admin/service-accounts/{user_id}/api-tokens/create",
            form={"name": "impersonate"},
            path_params={"user_id": harness.user_id},
        )
        testbase.assert_equal(
            (response.status_code, harness.page_context(template_name="site_shell/error_page.html")["title"],
             harness.session.query(AuthApiToken).count()),
            (404, "Service account not found", 0),
        )
    finally:
        harness.close()
    return


def test_admin_revokes_any_token():
    """
    **Feature: API token pages (ORG-F02)**
    **Property: POST /admin/api-tokens/{id}/revoke revokes another
    user's token.**
    """
    harness = _PageHarness(permission_predicate=_allow_everything)
    try:
        other = user_service.create_user(
            db_session=harness.session, login_name="erin", primary_email="erin@example.test",
            display_name="Erin", timezone="UTC", provisioning_source="local",
            external_id=None, actor_user_id=None,
        )
        issued = token_service.create_api_token(
            db_session=harness.session, user_id=str(other.user_id), name="theirs",
            lifetime_days=None, scope=None, actor_user_id=str(other.user_id),
        )
        harness.call(
            method="POST", path="/admin/api-tokens/{token_id}/revoke", form={},
            path_params={"token_id": issued.view.token_id},
        )
        view = token_service.read_api_token(db_session=harness.session, token_id=issued.view.token_id)
        testbase.assert_equal(view.status, "revoked")
    finally:
        harness.close()
    return
