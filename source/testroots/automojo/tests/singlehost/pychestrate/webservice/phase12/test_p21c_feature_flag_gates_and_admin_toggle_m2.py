"""
.. module:: test_p21c_feature_flag_gates_and_admin_toggle_m2
    :synopsis: Tests for P21c — feature-flag gates + admin toggle REST.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from flask import Flask, g
from flask_restx import Api
from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.webservice.identity.flags.flag_service import (
    create_flag,
)
from automojo.pychestrate.webservice.identity.flags.models import FlagKind
from automojo.pychestrate.webservice.security.auth import (
    provider_directory,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)
from automojo.pychestrate.webservice.security.auth.oidc.provider_registry import (
    OidcProviderConfig,
    register_oidc_provider,
    reset_for_testing as reset_oidc_registry,
)
from automojo.pychestrate.webservice.security.auth.restapi.v1 import (
    auth_controller,
)
from automojo.pychestrate.webservice.security.auth.saml.provider_registry import (
    SamlProviderConfig,
    register_saml_provider,
    reset_for_testing as reset_saml_registry,
)
from automojo.pychestrate.webservice.security.auth.saml.metadata import (
    SamlMetadataFetchResult,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _stub_oidc_token_fetcher(_request):
    return None


def _stub_oidc_key_resolver(_kid):
    return None


def _register_oidc(*, provider_name: str = "okta") -> None:
    register_oidc_provider(
        config=OidcProviderConfig(
            provider_name=provider_name,
            authorization_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/token",
            expected_issuer="https://idp.example.com",
            client_id="client-pychestrate",
            redirect_uri="https://app.example.com/cb",
            token_fetcher=_stub_oidc_token_fetcher,
            key_resolver=_stub_oidc_key_resolver,
            session_factory=lambda: None,
        ),
    )
    return


def _register_saml(*, provider_name: str = "okta-saml") -> None:
    register_saml_provider(
        config=SamlProviderConfig(
            provider_name=provider_name,
            sp_entity_id="https://app.example.com/sp",
            acs_url="https://app.example.com/saml/acs",
            metadata_url="https://idp.example.com/m.xml",
            metadata_fetcher=lambda _u: SamlMetadataFetchResult(
                document_xml=b"<empty/>", max_age_seconds=3600,
            ),
            session_factory=lambda: None,
        ),
    )
    return


def _seat_kind_flag(
        *, db_session, flag_key: str, default_value: bool
    ) -> None:
    create_flag(
        db_session=db_session,
        flag_key=flag_key,
        flag_kind=FlagKind.BOOLEAN,
        default_value=default_value,
        rules=None,
        actor_user_id=None,
    )
    return


def _setup_directory_with_all_three_kinds() -> None:
    provider_directory.reset_for_testing()
    reset_oidc_registry()
    reset_saml_registry()
    _register_oidc(provider_name="okta")
    _register_saml(provider_name="okta-saml")
    provider_directory.register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="okta",
        display_label="Okta",
    )
    provider_directory.register_credential_mode(
        kind=AuthProviderKind.SAML,
        provider_name="okta-saml",
        display_label="Okta SAML",
    )
    provider_directory.register_credential_mode(
        kind=AuthProviderKind.LOCAL,
        provider_name="local",
        display_label="Local",
    )
    return


# -------------------------------------
# is_enabled_with_flags
# -------------------------------------

def test_is_enabled_with_flags_defaults_true_when_flag_absent():
    """
    **Feature: 1-authentication (M2)**
    **Property: is_enabled_with_flags returns True when
    the kind-level feature flag has not been seeded — the
    default is "the directory's in-memory flag is the
    truth".**
    """
    reset_phase1_runtime()
    _setup_directory_with_all_three_kinds()
    _engine, session = build_in_memory_session()
    testbase.assert_equal(
        provider_directory.is_enabled_with_flags(
            kind=AuthProviderKind.OIDC,
            provider_name="okta",
            db_session=session,
        ),
        True,
    )
    return


def test_is_enabled_with_flags_returns_false_when_kind_flag_disabled():
    """
    **Feature: 1-authentication (M2)**
    **Property: a kind-level flag set to False (e.g.
    auth.oidc_enabled=false) hides every OIDC provider from
    the picker even when the directory has them enabled.**
    """
    reset_phase1_runtime()
    _setup_directory_with_all_three_kinds()
    _engine, session = build_in_memory_session()
    _seat_kind_flag(
        db_session=session,
        flag_key="auth.oidc_enabled",
        default_value=False,
    )
    testbase.assert_equal(
        provider_directory.is_enabled_with_flags(
            kind=AuthProviderKind.OIDC,
            provider_name="okta",
            db_session=session,
        ),
        False,
    )
    # SAML and LOCAL still pass — flags are kind-scoped.
    testbase.assert_equal(
        provider_directory.is_enabled_with_flags(
            kind=AuthProviderKind.SAML,
            provider_name="okta-saml",
            db_session=session,
        ),
        True,
    )
    testbase.assert_equal(
        provider_directory.is_enabled_with_flags(
            kind=AuthProviderKind.LOCAL,
            provider_name="local",
            db_session=session,
        ),
        True,
    )
    return


def test_is_enabled_with_flags_respects_directory_disable_first():
    """
    **Feature: 1-authentication (M2)**
    **Property: a directory entry disabled via
    set_enabled(enabled=False) returns False without ever
    consulting the feature flag (short-circuit on the
    in-memory flag).**
    """
    reset_phase1_runtime()
    _setup_directory_with_all_three_kinds()
    provider_directory.set_enabled(
        kind=AuthProviderKind.OIDC,
        provider_name="okta",
        enabled=False,
    )
    _engine, session = build_in_memory_session()
    # No flag seeded — would default True if reached, but
    # the directory short-circuits.
    testbase.assert_equal(
        provider_directory.is_enabled_with_flags(
            kind=AuthProviderKind.OIDC,
            provider_name="okta",
            db_session=session,
        ),
        False,
    )
    return


def test_local_fallback_enabled_flag_gates_local_kind():
    """
    **Feature: 1-authentication (M2)**
    **Property: auth.local_fallback_enabled set to False
    hides the LOCAL credential mode — this is the spec-
    mandated toggle for shutting off local password
    fallback when SSO is healthy.**
    """
    reset_phase1_runtime()
    _setup_directory_with_all_three_kinds()
    _engine, session = build_in_memory_session()
    _seat_kind_flag(
        db_session=session,
        flag_key="auth.local_fallback_enabled",
        default_value=False,
    )
    testbase.assert_equal(
        provider_directory.is_enabled_with_flags(
            kind=AuthProviderKind.LOCAL,
            provider_name="local",
            db_session=session,
        ),
        False,
    )
    return


# -------------------------------------
# list_enabled_credential_modes_with_flags
# -------------------------------------

def test_list_with_flags_filters_disabled_kind():
    """
    **Feature: 1-authentication (M2)**
    **Property: list_enabled_credential_modes_with_flags
    drops entries whose kind-level flag is False — what
    the picker endpoint returns at request time.**
    """
    reset_phase1_runtime()
    _setup_directory_with_all_three_kinds()
    _engine, session = build_in_memory_session()
    _seat_kind_flag(
        db_session=session,
        flag_key="auth.saml_enabled",
        default_value=False,
    )
    modes = provider_directory.list_enabled_credential_modes_with_flags(
        db_session=session,
    )
    kinds = sorted({m.kind.value for m in modes})
    testbase.assert_equal(kinds, ["LOCAL", "OIDC"])
    return


# -------------------------------------
# REST: GET /api/v1/auth/providers consults flags
# -------------------------------------

def _build_picker_app(*, engine) -> Flask:
    session_factory = sessionmaker(bind=engine)
    app = Flask("p21c-picker")
    app.config["TESTING"] = True

    @app.before_request
    def _attach_session():
        g.db_session = session_factory()
        return None

    @app.teardown_request
    def _close_session(_exc):
        db_session = getattr(g, "db_session", None)
        if db_session is not None:
            db_session.close()
        return None

    api = Api(app)
    for ns, path in auth_controller.publish_namespaces(
        version_prefix="/1",
    ):
        api.add_namespace(ns, path=path)
    return app


def test_get_providers_filters_by_feature_flag_when_db_session_attached():
    """
    **Feature: 1-authentication (M2)**
    **Property: GET /api/v1/auth/providers returns only
    modes whose kind-level feature flag is True when a
    request-scoped g.db_session is attached.**
    """
    reset_phase1_runtime()
    _setup_directory_with_all_three_kinds()
    engine, session = build_in_memory_session()
    _seat_kind_flag(
        db_session=session,
        flag_key="auth.oidc_enabled",
        default_value=False,
    )
    session.close()
    app = _build_picker_app(engine=engine)
    response = app.test_client().get("/1/auth/providers")
    testbase.assert_equal(response.status_code, 200)
    body = response.get_json()
    kinds = sorted({p["kind"] for p in body["providers"]})
    testbase.assert_equal(kinds, ["LOCAL", "SAML"])
    return


# -------------------------------------
# REST: admin enable/disable hot-toggle
# -------------------------------------

def test_admin_disable_then_enable_flips_directory_flag():
    """
    **Feature: 1-authentication (M2)**
    **Property: POST /api/v1/auth/providers/{kind}/{name}/disable
    flips enabled to False; the next picker call drops the
    entry; POST .../enable flips it back True.**
    """
    reset_phase1_runtime()
    _setup_directory_with_all_three_kinds()
    engine, _ = build_in_memory_session()
    app = _build_picker_app(engine=engine)
    client = app.test_client()

    disable_response = client.post(
        "/1/auth/providers/OIDC/okta/disable",
    )
    testbase.assert_equal(disable_response.status_code, 200)
    testbase.assert_equal(
        disable_response.get_json()["enabled"], False,
    )

    picker = client.get("/1/auth/providers").get_json()
    pairs = [
        (p["kind"], p["provider_name"]) for p in picker["providers"]
    ]
    testbase.assert_equal(("OIDC", "okta") in pairs, False)

    enable_response = client.post(
        "/1/auth/providers/OIDC/okta/enable",
    )
    testbase.assert_equal(enable_response.status_code, 200)
    testbase.assert_equal(
        enable_response.get_json()["enabled"], True,
    )

    picker_after = client.get("/1/auth/providers").get_json()
    pairs_after = [
        (p["kind"], p["provider_name"]) for p in picker_after["providers"]
    ]
    testbase.assert_equal(("OIDC", "okta") in pairs_after, True)
    return


def test_admin_disable_unknown_kind_returns_404():
    """
    **Feature: 1-authentication (M2)**
    **Property: an unknown kind segment surfaces 404
    kind_unknown so a typo can't silently no-op.**
    """
    reset_phase1_runtime()
    _setup_directory_with_all_three_kinds()
    engine, _ = build_in_memory_session()
    app = _build_picker_app(engine=engine)
    response = app.test_client().post(
        "/1/auth/providers/MAGIC/okta/disable",
    )
    testbase.assert_equal(response.status_code, 404)
    return


def test_admin_disable_unregistered_provider_returns_404():
    """
    **Feature: 1-authentication (M2)**
    **Property: a known kind but unregistered provider_name
    surfaces 404 credential_mode_not_registered so the admin
    UI can distinguish "kind typo" from "name typo".**
    """
    reset_phase1_runtime()
    _setup_directory_with_all_three_kinds()
    engine, _ = build_in_memory_session()
    app = _build_picker_app(engine=engine)
    response = app.test_client().post(
        "/1/auth/providers/OIDC/never-registered/disable",
    )
    testbase.assert_equal(response.status_code, 404)
    return


def test_admin_enable_kind_segment_is_case_insensitive():
    """
    **Feature: 1-authentication (M2)**
    **Property: lowercase 'oidc' resolves to AuthProviderKind.OIDC
    so REST clients don't have to upper-case the URL segment.**
    """
    reset_phase1_runtime()
    _setup_directory_with_all_three_kinds()
    provider_directory.set_enabled(
        kind=AuthProviderKind.OIDC,
        provider_name="okta",
        enabled=False,
    )
    engine, _ = build_in_memory_session()
    app = _build_picker_app(engine=engine)
    response = app.test_client().post(
        "/1/auth/providers/oidc/okta/enable",
    )
    testbase.assert_equal(response.status_code, 200)
    testbase.assert_equal(
        provider_directory.is_enabled(
            kind=AuthProviderKind.OIDC, provider_name="okta",
        ),
        True,
    )
    return
