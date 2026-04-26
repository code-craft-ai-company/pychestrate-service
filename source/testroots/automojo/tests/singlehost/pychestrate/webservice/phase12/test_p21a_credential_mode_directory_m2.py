"""
.. module:: test_p21a_credential_mode_directory_m2
    :synopsis: Tests for P21a — 1-authentication M2 unified credential-mode directory.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from automojo import testbase

from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)
from automojo.pychestrate.webservice.security.auth.oidc.provider_registry import (
    OidcProviderConfig,
    register_oidc_provider,
    reset_for_testing as reset_oidc_registry,
)
from automojo.pychestrate.webservice.security.auth.provider_directory import (
    CredentialModeView,
    is_enabled,
    list_credential_modes,
    list_enabled_credential_modes,
    register_credential_mode,
    reset_for_testing as reset_directory,
    set_enabled,
    unregister_credential_mode,
)
from automojo.pychestrate.webservice.security.auth.saml.provider_registry import (
    SamlProviderConfig,
    register_saml_provider,
    reset_for_testing as reset_saml_registry,
)
from automojo.pychestrate.webservice.security.auth.saml.metadata import (
    SamlMetadataFetchResult,
)


def _stub_oidc_token_fetcher(_request):
    return None


def _stub_oidc_key_resolver(_kid):
    return None


def _stub_saml_metadata_fetcher(_url):
    return SamlMetadataFetchResult(
        document_xml=b"<empty/>", max_age_seconds=3600,
    )


def _stub_session_factory():
    return None


def _register_backing_oidc(*, provider_name: str = "okta") -> None:
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
            session_factory=_stub_session_factory,
        ),
    )
    return


def _register_backing_saml(
        *, provider_name: str = "okta-saml"
    ) -> None:
    register_saml_provider(
        config=SamlProviderConfig(
            provider_name=provider_name,
            sp_entity_id="https://app.example.com/sp",
            acs_url="https://app.example.com/saml/acs",
            metadata_url="https://idp.example.com/m.xml",
            metadata_fetcher=_stub_saml_metadata_fetcher,
            session_factory=_stub_session_factory,
        ),
    )
    return


def _setup_clean() -> None:
    reset_directory()
    reset_oidc_registry()
    reset_saml_registry()
    return


# -------------------------------------
# register / list / unregister
# -------------------------------------

def test_register_returns_view_with_default_login_paths_per_kind():
    """
    **Feature: 1-authentication (M2)**
    **Property: register_credential_mode emits the canonical
    /auth/{kind}/{provider_name}/login path for OIDC and SAML
    and /api/v1/auth/local/login for LOCAL when login_path is
    omitted.**
    """
    _setup_clean()
    _register_backing_oidc(provider_name="okta")
    _register_backing_saml(provider_name="okta-saml")
    oidc_view = register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="okta",
        display_label="Sign in with Okta (OIDC)",
    )
    saml_view = register_credential_mode(
        kind=AuthProviderKind.SAML,
        provider_name="okta-saml",
        display_label="Sign in with Okta (SAML)",
    )
    local_view = register_credential_mode(
        kind=AuthProviderKind.LOCAL,
        provider_name="local",
        display_label="Local password",
    )
    testbase.assert_equal(
        oidc_view.login_path, "/auth/oidc/okta/login",
    )
    testbase.assert_equal(
        saml_view.login_path, "/auth/saml/okta-saml/login",
    )
    testbase.assert_equal(
        local_view.login_path, "/api/v1/auth/local/login",
    )
    return


def test_register_honors_explicit_login_path():
    """
    **Feature: 1-authentication (M2)**
    **Property: register_credential_mode honors a
    caller-supplied login_path (overrides the default).**
    """
    _setup_clean()
    _register_backing_oidc()
    view = register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="okta",
        display_label="Custom Okta",
        login_path="/auth/custom/okta-login",
    )
    testbase.assert_equal(view.login_path, "/auth/custom/okta-login")
    return


def test_register_rejects_duplicate_kind_provider_name_pair():
    """
    **Feature: 1-authentication (M2)**
    **Property: a second register_credential_mode with the
    same (kind, provider_name) raises ValueError so a config
    typo can't silently override an existing entry.**
    """
    _setup_clean()
    _register_backing_oidc()
    register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="okta",
        display_label="Sign in with Okta",
    )
    raised = False
    try:
        register_credential_mode(
            kind=AuthProviderKind.OIDC,
            provider_name="okta",
            display_label="Other label",
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_register_rejects_empty_provider_name_or_label():
    """
    **Feature: 1-authentication (M2)**
    **Property: empty provider_name / display_label raise
    ValueError before the entry lands.**
    """
    _setup_clean()
    raised_pn = False
    raised_lbl = False
    try:
        register_credential_mode(
            kind=AuthProviderKind.LOCAL,
            provider_name="",
            display_label="x",
        )
    except ValueError:
        raised_pn = True
    try:
        register_credential_mode(
            kind=AuthProviderKind.LOCAL,
            provider_name="local",
            display_label="",
        )
    except ValueError:
        raised_lbl = True
    testbase.assert_equal(raised_pn, True)
    testbase.assert_equal(raised_lbl, True)
    return


def test_unregister_drops_entry_and_is_idempotent():
    """
    **Feature: 1-authentication (M2)**
    **Property: unregister_credential_mode returns True the
    first time and False on a second call against the same
    entry.**
    """
    _setup_clean()
    _register_backing_oidc()
    register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="okta",
        display_label="Okta",
    )
    testbase.assert_equal(
        unregister_credential_mode(
            kind=AuthProviderKind.OIDC, provider_name="okta",
        ),
        True,
    )
    testbase.assert_equal(
        unregister_credential_mode(
            kind=AuthProviderKind.OIDC, provider_name="okta",
        ),
        False,
    )
    return


# -------------------------------------
# Backing-config cross-reference
# -------------------------------------

def test_list_filters_modes_with_no_backing_config():
    """
    **Feature: 1-authentication (M2)**
    **Property: an OIDC directory entry whose backing
    OidcProviderConfig has been unregistered is filtered
    out of list_credential_modes — the picker can never
    advertise a half-shaped provider.**
    """
    _setup_clean()
    _register_backing_oidc(provider_name="okta")
    register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="okta",
        display_label="Okta",
    )
    register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="auth0",  # no backing config
        display_label="Auth0",
    )
    modes = list_credential_modes()
    names = [m.provider_name for m in modes]
    testbase.assert_equal(names, ["okta"])
    return


def test_local_does_not_require_backing_config():
    """
    **Feature: 1-authentication (M2)**
    **Property: a LOCAL entry has no backing
    OidcProviderConfig / SamlProviderConfig and is always
    listed as long as it's registered.**
    """
    _setup_clean()
    register_credential_mode(
        kind=AuthProviderKind.LOCAL,
        provider_name="local",
        display_label="Local",
    )
    modes = list_credential_modes()
    testbase.assert_equal(len(modes), 1)
    testbase.assert_equal(modes[0].kind, AuthProviderKind.LOCAL)
    return


def test_list_returns_modes_sorted_by_kind_then_provider_name():
    """
    **Feature: 1-authentication (M2)**
    **Property: list_credential_modes returns entries
    sorted by (kind, provider_name) so the picker rendering
    is deterministic.**
    """
    _setup_clean()
    _register_backing_oidc(provider_name="okta")
    _register_backing_oidc(provider_name="auth0")
    _register_backing_saml(provider_name="okta-saml")
    register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="okta", display_label="Okta",
    )
    register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="auth0", display_label="Auth0",
    )
    register_credential_mode(
        kind=AuthProviderKind.SAML,
        provider_name="okta-saml", display_label="Okta SAML",
    )
    register_credential_mode(
        kind=AuthProviderKind.LOCAL,
        provider_name="local", display_label="Local",
    )
    rendered = [
        (m.kind.value, m.provider_name) for m in list_credential_modes()
    ]
    testbase.assert_equal(
        rendered,
        [
            ("LOCAL", "local"),
            ("OIDC", "auth0"),
            ("OIDC", "okta"),
            ("SAML", "okta-saml"),
        ],
    )
    return


# -------------------------------------
# enabled toggle + is_enabled
# -------------------------------------

def test_set_enabled_flips_flag_without_re_registering():
    """
    **Feature: 1-authentication (M2)**
    **Property: set_enabled toggles the enabled flag in
    place; the entry stays in list_credential_modes but
    drops out of list_enabled_credential_modes.**
    """
    _setup_clean()
    _register_backing_oidc(provider_name="okta")
    register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="okta",
        display_label="Okta",
    )
    set_enabled(
        kind=AuthProviderKind.OIDC,
        provider_name="okta",
        enabled=False,
    )
    listed = list_credential_modes()
    enabled = list_enabled_credential_modes()
    testbase.assert_equal(len(listed), 1)
    testbase.assert_equal(listed[0].enabled, False)
    testbase.assert_equal(enabled, [])
    return


def test_set_enabled_unknown_mode_raises_key_error():
    """
    **Feature: 1-authentication (M2)**
    **Property: set_enabled against a (kind, provider_name)
    that was never registered raises KeyError.**
    """
    _setup_clean()
    raised = False
    try:
        set_enabled(
            kind=AuthProviderKind.OIDC,
            provider_name="never",
            enabled=False,
        )
    except KeyError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_is_enabled_returns_false_for_unregistered_or_disabled_or_unbacked():
    """
    **Feature: 1-authentication (M2)**
    **Property: is_enabled requires the entry to be
    registered AND enabled AND backed by a provider config
    (LOCAL needs no backing config).**
    """
    _setup_clean()
    _register_backing_oidc(provider_name="okta")
    register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="okta", display_label="Okta",
    )
    register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="auth0", display_label="Auth0",
    )
    register_credential_mode(
        kind=AuthProviderKind.LOCAL,
        provider_name="local", display_label="Local",
        enabled=False,
    )
    testbase.assert_equal(
        is_enabled(
            kind=AuthProviderKind.OIDC, provider_name="okta",
        ),
        True,
    )
    # auth0 has no backing config — false even though enabled.
    testbase.assert_equal(
        is_enabled(
            kind=AuthProviderKind.OIDC, provider_name="auth0",
        ),
        False,
    )
    # local was registered disabled.
    testbase.assert_equal(
        is_enabled(
            kind=AuthProviderKind.LOCAL, provider_name="local",
        ),
        False,
    )
    # never registered.
    testbase.assert_equal(
        is_enabled(
            kind=AuthProviderKind.OIDC, provider_name="never",
        ),
        False,
    )
    return


def test_register_with_enabled_false_lands_disabled():
    """
    **Feature: 1-authentication (M2)**
    **Property: registering with enabled=False lets an
    operator pre-stage a provider that won't show up on the
    picker until set_enabled flips it on.**
    """
    _setup_clean()
    _register_backing_oidc(provider_name="staged")
    view = register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="staged",
        display_label="Staged",
        enabled=False,
    )
    testbase.assert_equal(view.enabled, False)
    enabled = list_enabled_credential_modes()
    testbase.assert_equal(enabled, [])
    return


def test_reset_for_testing_clears_directory():
    """
    **Feature: 1-authentication (M2)**
    **Property: reset_for_testing drops every directory
    entry so cross-test state can't leak.**
    """
    _setup_clean()
    _register_backing_oidc()
    register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="okta", display_label="Okta",
    )
    reset_directory()
    testbase.assert_equal(list_credential_modes(), [])
    return
