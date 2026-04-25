"""
.. module:: test_p18b_oidc_user_provisioning_m2
    :synopsis: Tests for P18b — 1-authentication M2 OIDC user provisioning.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.webservice.identity.users import user_service
from automojo.pychestrate.webservice.identity.users.models import (
    IdentityUser,
    UserStatus,
)
from automojo.pychestrate.webservice.security.auth.oidc.provisioning import (
    ClaimsMissingError,
    OidcClaimMapping,
    UserDeactivatedError,
    resolve_user_from_claims,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


def _build_claims(
        *,
        sub: str = "idp-user-1",
        email: str = "alice@example.com",
        name: str = "Alice Anderson",
        zoneinfo: str = "America/Los_Angeles"
    ) -> dict:
    rtnval = {
        "sub": sub,
        "email": email,
        "name": name,
        "zoneinfo": zoneinfo,
    }
    return rtnval


# -------------------------------------
# Strategy 3 — provision
# -------------------------------------

def test_resolve_user_from_claims_provisions_when_no_match():
    """
    **Feature: 1-authentication (M2)**
    **Property: a fresh callback for an unknown user
    provisions a new IdentityUser through user_service so
    audit + bus emissions stay unchanged.**
    """
    _engine, session = build_in_memory_session()
    claims = _build_claims()
    result = resolve_user_from_claims(
        db_session=session,
        provider_name="okta",
        claims=claims,
    )
    testbase.assert_equal(result.outcome, "provisioned")
    testbase.assert_equal(result.user.primary_email, "alice@example.com")
    testbase.assert_equal(result.user.provisioning_source, "okta")
    testbase.assert_equal(result.user.external_id, "idp-user-1")
    testbase.assert_equal(result.user.timezone, "America/Los_Angeles")
    testbase.assert_equal(result.user.status, UserStatus.ACTIVE)
    return


def test_provisioning_uses_email_local_part_for_login_name_default():
    """
    **Feature: 1-authentication (M2)**
    **Property: when login_name_claim is None, the helper
    derives the login from the email local part.**
    """
    _engine, session = build_in_memory_session()
    claims = _build_claims(email="bob.smith@corp.example")
    result = resolve_user_from_claims(
        db_session=session,
        provider_name="okta",
        claims=claims,
    )
    testbase.assert_equal(result.user.login_name, "bob.smith")
    return


def test_provisioning_honors_configured_login_name_claim():
    """
    **Feature: 1-authentication (M2)**
    **Property: when login_name_claim is configured, the
    helper picks the matching claim and lowercases it.**
    """
    _engine, session = build_in_memory_session()
    claims = _build_claims()
    claims["preferred_username"] = "Alice.A"
    mapping = OidcClaimMapping(login_name_claim="preferred_username")
    result = resolve_user_from_claims(
        db_session=session,
        provider_name="okta",
        claims=claims,
        mapping=mapping,
    )
    testbase.assert_equal(result.user.login_name, "alice.a")
    return


def test_provisioning_falls_back_to_utc_when_zoneinfo_missing():
    """
    **Feature: 1-authentication (M2)**
    **Property: a missing or empty zoneinfo falls back to
    UTC.**
    """
    _engine, session = build_in_memory_session()
    claims = _build_claims()
    claims.pop("zoneinfo", None)
    result = resolve_user_from_claims(
        db_session=session,
        provider_name="okta",
        claims=claims,
    )
    testbase.assert_equal(result.user.timezone, "UTC")
    return


def test_provisioning_falls_back_to_email_when_name_missing():
    """
    **Feature: 1-authentication (M2)**
    **Property: a missing name claim falls back to the
    primary email so display_name is never empty.**
    """
    _engine, session = build_in_memory_session()
    claims = _build_claims()
    claims.pop("name", None)
    result = resolve_user_from_claims(
        db_session=session,
        provider_name="okta",
        claims=claims,
    )
    testbase.assert_equal(
        result.user.display_name, "alice@example.com",
    )
    return


# -------------------------------------
# Strategy 1 — match by external id
# -------------------------------------

def test_resolve_user_matches_by_external_id_on_repeat():
    """
    **Feature: 1-authentication (M2)**
    **Property: a second callback for the same external_id
    matches the existing row instead of creating a new
    one.**
    """
    _engine, session = build_in_memory_session()
    claims = _build_claims()
    first = resolve_user_from_claims(
        db_session=session,
        provider_name="okta",
        claims=claims,
    )
    second = resolve_user_from_claims(
        db_session=session,
        provider_name="okta",
        claims=claims,
    )
    testbase.assert_equal(second.outcome, "matched_by_external_id")
    testbase.assert_equal(second.user.user_id, first.user.user_id)
    return


def test_match_by_external_id_is_provider_scoped():
    """
    **Feature: 1-authentication (M2)**
    **Property: the same sub claim under a different
    provider doesn't match the prior row — different
    providers are independent identity scopes.**
    """
    _engine, session = build_in_memory_session()
    first = resolve_user_from_claims(
        db_session=session,
        provider_name="okta",
        claims=_build_claims(sub="user-x", email="x@a.com"),
    )
    second = resolve_user_from_claims(
        db_session=session,
        provider_name="auth0",
        claims=_build_claims(sub="user-x", email="x-different@b.com"),
    )
    testbase.assert_equal(first.user.user_id != second.user.user_id, True)
    testbase.assert_equal(second.outcome, "provisioned")
    return


# -------------------------------------
# Strategy 2 — match by email + upgrade
# -------------------------------------

def test_match_by_email_upgrades_provisioning_source():
    """
    **Feature: 1-authentication (M2)**
    **Property: a callback whose email matches an existing
    locally-provisioned user upgrades the row's
    provisioning_source + external_id so subsequent logins
    use the external-id match.**
    """
    _engine, session = build_in_memory_session()
    user_service.create_user(
        db_session=session,
        login_name="alice",
        primary_email="alice@example.com",
        display_name="Alice",
        timezone="UTC",
        provisioning_source="local",
        external_id=None,
        actor_user_id=None,
    )
    claims = _build_claims()
    result = resolve_user_from_claims(
        db_session=session,
        provider_name="okta",
        claims=claims,
    )
    testbase.assert_equal(result.outcome, "matched_by_email_upgraded")
    testbase.assert_equal(result.user.provisioning_source, "okta")
    testbase.assert_equal(result.user.external_id, "idp-user-1")
    second = resolve_user_from_claims(
        db_session=session,
        provider_name="okta",
        claims=claims,
    )
    testbase.assert_equal(second.outcome, "matched_by_external_id")
    return


# -------------------------------------
# Deactivated user gate
# -------------------------------------

def test_deactivated_user_raises_user_deactivated_error():
    """
    **Feature: 1-authentication (M2)**
    **Property: a callback that resolves to a row in
    DEACTIVATED status raises UserDeactivatedError so the
    controller surfaces a 403 and refuses to seat a
    session.**
    """
    _engine, session = build_in_memory_session()
    initial = resolve_user_from_claims(
        db_session=session,
        provider_name="okta",
        claims=_build_claims(),
    )
    user_service.deactivate_user(
        db_session=session,
        user_id=str(initial.user.user_id),
        reason="off-boarded",
    )
    raised = False
    try:
        resolve_user_from_claims(
            db_session=session,
            provider_name="okta",
            claims=_build_claims(),
        )
    except UserDeactivatedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# Required-claim validation
# -------------------------------------

def test_missing_external_id_claim_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: claims without the external_id_claim raise
    ClaimsMissingError so the callback path can surface a
    400 without leaking which claim was wrong.**
    """
    _engine, session = build_in_memory_session()
    claims = _build_claims()
    claims.pop("sub", None)
    raised = False
    try:
        resolve_user_from_claims(
            db_session=session,
            provider_name="okta",
            claims=claims,
        )
    except ClaimsMissingError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_missing_email_claim_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: claims without the email_claim raise
    ClaimsMissingError.**
    """
    _engine, session = build_in_memory_session()
    claims = _build_claims()
    claims.pop("email", None)
    raised = False
    try:
        resolve_user_from_claims(
            db_session=session,
            provider_name="okta",
            claims=claims,
        )
    except ClaimsMissingError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_empty_claim_value_raises_claims_missing():
    """
    **Feature: 1-authentication (M2)**
    **Property: an empty / whitespace-only required claim
    counts as missing.**
    """
    _engine, session = build_in_memory_session()
    claims = _build_claims()
    claims["sub"] = "   "
    raised = False
    try:
        resolve_user_from_claims(
            db_session=session,
            provider_name="okta",
            claims=claims,
        )
    except ClaimsMissingError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_resolve_rejects_empty_provider_name():
    """
    **Feature: 1-authentication (M2)**
    **Property: empty provider_name raises ValueError.**
    """
    _engine, session = build_in_memory_session()
    raised = False
    try:
        resolve_user_from_claims(
            db_session=session,
            provider_name="",
            claims=_build_claims(),
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# Custom mapping
# -------------------------------------

def test_custom_mapping_overrides_canonical_claim_keys():
    """
    **Feature: 1-authentication (M2)**
    **Property: an OidcClaimMapping with non-default keys
    drives the helper to read the matching claims.**
    """
    _engine, session = build_in_memory_session()
    claims = {
        "uid": "ext-9000",
        "mail": "carol@example.com",
        "full_name": "Carol C.",
        "tz": "Europe/London",
    }
    mapping = OidcClaimMapping(
        external_id_claim="uid",
        email_claim="mail",
        display_name_claim="full_name",
        timezone_claim="tz",
    )
    result = resolve_user_from_claims(
        db_session=session,
        provider_name="custom",
        claims=claims,
        mapping=mapping,
    )
    testbase.assert_equal(result.user.external_id, "ext-9000")
    testbase.assert_equal(result.user.primary_email, "carol@example.com")
    testbase.assert_equal(result.user.display_name, "Carol C.")
    testbase.assert_equal(result.user.timezone, "Europe/London")
    return
