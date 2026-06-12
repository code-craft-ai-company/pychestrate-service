"""
.. module:: test_p10n_mfa_method_extension_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the MFAMethodExtension resource base + TOTP reference.

.. moduleauthor:: Code Craft AI LLC

The slice promotes ``MFAMethodExtension`` from the published-but-
not-yet-implemented list (per ``8-plugin-api`` Requirement 2) into
the catalog. Tests cover the dataclass invariants, the resource-base
contract, the TOTP reference math (against fixed RFC 6238 vectors so
the implementation cannot silently regress), and the catalog walk.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension
from ccai.pychestrate.webservice.plugin_api import build_catalog, is_class_published
from ccai.pychestrate.webservice.plugin_api.catalog_validator import (
    validate_catalog_against_code,
)
from ccai.pychestrate.webservice.security.auth.extensions.mfa_method import (
    MFAEnrollmentChallenge,
    MFAMethodExtension,
    MFAVerificationResult,
)
from ccai.pychestrate.webservice.security.auth.extensions.totp_method import (
    TOTP_DEFAULT_DIGITS,
    TOTP_DEFAULT_PERIOD_SECONDS,
    TotpMfaMethod,
    compute_totp_code,
)


# ---------------------------------------------------------------------------
# Resource base contract
# ---------------------------------------------------------------------------

def test_mfa_method_extension_is_direct_resource_subclass():
    """
    **Feature: 8-plugin-api / 1-authentication MFA**
    **Property: MFAMethodExtension is a direct ResourceExtension
    subclass so the catalog walker enumerates it as a published base.**
    """
    testbase.assert_equal(issubclass(MFAMethodExtension, ResourceExtension), True)
    testbase.assert_equal(ResourceExtension in MFAMethodExtension.__bases__, True)
    return


def test_mfa_method_extension_default_method_name_is_empty():
    """
    **Feature: 1-authentication MFA**
    **Property: The base declares method_name = '' so subclasses must
    override.**
    """
    testbase.assert_equal(MFAMethodExtension.method_name, "")
    return


def test_mfa_method_extension_begin_enrollment_raises_on_base():
    """
    **Feature: 1-authentication MFA**
    **Property: Calling begin_enrollment on the base raises
    NotImplementedError.**
    """
    raised = False
    try:
        MFAMethodExtension.begin_enrollment(user_id="u")
    except NotImplementedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_mfa_method_extension_verify_challenge_raises_on_base():
    """
    **Feature: 1-authentication MFA**
    **Property: Calling verify_challenge on the base raises
    NotImplementedError.**
    """
    raised = False
    try:
        MFAMethodExtension.verify_challenge(
            user_id="u", challenge_id="c", proof={}
        )
    except NotImplementedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

def test_mfa_enrollment_challenge_is_frozen():
    """
    **Feature: 1-authentication MFA**
    **Property: MFAEnrollmentChallenge is a frozen dataclass with
    method_name, challenge_id, payload.**
    """
    challenge = MFAEnrollmentChallenge(
        method_name="totp",
        challenge_id="abc",
        payload={"secret": "x"},
    )
    testbase.assert_equal(challenge.method_name, "totp")
    testbase.assert_equal(challenge.challenge_id, "abc")
    testbase.assert_equal(challenge.payload["secret"], "x")

    raised = False
    try:
        challenge.method_name = "other"
    except Exception:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_mfa_verification_result_is_frozen():
    """
    **Feature: 1-authentication MFA**
    **Property: MFAVerificationResult is a frozen dataclass with
    verified, method_name, failure_reason.**
    """
    result = MFAVerificationResult(
        verified=False, method_name="totp", failure_reason="x"
    )
    testbase.assert_equal(result.verified, False)
    testbase.assert_equal(result.method_name, "totp")
    testbase.assert_equal(result.failure_reason, "x")
    return


# ---------------------------------------------------------------------------
# TOTP reference math (RFC 6238 §B vectors)
# ---------------------------------------------------------------------------

# Per RFC 6238 §B, the test secret is the ASCII string "12345678901234567890"
# encoded as base-32: GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ. The published
# vectors are 8-digit codes, but TOTP codes are also valid at any digit
# length; the math here uses 6-digit truncation to match the M1 default.

_RFC6238_SHARED_SECRET_BASE32 = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

# 6-digit truncated codes for the canonical RFC 6238 timestamps. Computed
# locally with the published reference; pinned here so a future
# implementation regression fails loud.
_RFC6238_VECTORS_6_DIGIT = (
    (59, "287082"),
    (1111111109, "081804"),
    (1111111111, "050471"),
    (1234567890, "005924"),
    (2000000000, "279037"),
)


def test_compute_totp_code_matches_rfc6238_vectors():
    """
    **Feature: 1-authentication MFA (TOTP reference)**
    **Property: compute_totp_code returns the RFC 6238 §B canonical
    6-digit truncations for the published timestamps.**
    """
    for timestamp_seconds, expected_code in _RFC6238_VECTORS_6_DIGIT:
        actual = compute_totp_code(
            secret_base32=_RFC6238_SHARED_SECRET_BASE32,
            timestamp_seconds=timestamp_seconds,
        )
        testbase.assert_equal(actual, expected_code)
    return


def test_compute_totp_code_pads_to_documented_digit_count():
    """
    **Feature: 1-authentication MFA (TOTP reference)**
    **Property: compute_totp_code returns a string of the requested
    digit length, zero-padded if necessary.**
    """
    code = compute_totp_code(
        secret_base32=_RFC6238_SHARED_SECRET_BASE32,
        timestamp_seconds=1234567890,
        digits=8,
    )
    testbase.assert_equal(len(code), 8)
    return


# ---------------------------------------------------------------------------
# TotpMfaMethod surface
# ---------------------------------------------------------------------------

def test_totp_mfa_method_inherits_from_base_only():
    """
    **Feature: 1-authentication MFA**
    **Property: TotpMfaMethod inherits from MFAMethodExtension
    (not directly from ResourceExtension).**
    """
    testbase.assert_equal(
        issubclass(TotpMfaMethod, MFAMethodExtension), True
    )
    testbase.assert_equal(
        MFAMethodExtension in TotpMfaMethod.__bases__, True
    )
    testbase.assert_equal(
        ResourceExtension in TotpMfaMethod.__bases__, False
    )
    return


def test_totp_mfa_method_name_is_totp():
    testbase.assert_equal(TotpMfaMethod.method_name, "totp")
    return


def test_totp_begin_enrollment_returns_secret_with_documented_payload():
    """
    **Feature: 1-authentication MFA (TOTP reference)**
    **Property: begin_enrollment yields a challenge with secret_base32,
    period, digits, and algorithm fields populated.**
    """
    challenge = TotpMfaMethod.begin_enrollment(user_id="user-1")
    testbase.assert_equal(challenge.method_name, "totp")
    testbase.assert_equal(len(challenge.challenge_id) > 0, True)
    testbase.assert_equal("secret_base32" in challenge.payload, True)
    testbase.assert_equal(
        challenge.payload["period_seconds"], TOTP_DEFAULT_PERIOD_SECONDS
    )
    testbase.assert_equal(
        challenge.payload["digits"], TOTP_DEFAULT_DIGITS
    )
    testbase.assert_equal(challenge.payload["algorithm"], "SHA1")
    return


def test_totp_begin_enrollment_returns_distinct_secrets():
    """
    **Feature: 1-authentication MFA (TOTP reference)**
    **Property: Successive enrollments yield distinct secrets and
    challenge ids.**
    """
    a = TotpMfaMethod.begin_enrollment(user_id="user-1")
    b = TotpMfaMethod.begin_enrollment(user_id="user-1")
    testbase.assert_equal(a.payload["secret_base32"] != b.payload["secret_base32"], True)
    testbase.assert_equal(a.challenge_id != b.challenge_id, True)
    return


def test_totp_verify_accepts_correct_code_for_current_step():
    """
    **Feature: 1-authentication MFA (TOTP reference)**
    **Property: verify_challenge returns verified=True when the proof
    code matches the current TOTP step (timestamp injected for
    determinism).**
    """
    fixed_ts = 1234567890
    expected_code = compute_totp_code(
        secret_base32=_RFC6238_SHARED_SECRET_BASE32,
        timestamp_seconds=fixed_ts,
    )
    result = TotpMfaMethod.verify_challenge(
        user_id="u",
        challenge_id="c",
        proof={
            "code": expected_code,
            "secret_base32": _RFC6238_SHARED_SECRET_BASE32,
            "timestamp_seconds": fixed_ts,
        },
    )
    testbase.assert_equal(result.verified, True)
    testbase.assert_equal(result.failure_reason, "")
    return


def test_totp_verify_accepts_one_step_skew():
    """
    **Feature: 1-authentication MFA (TOTP reference)**
    **Property: verify_challenge tolerates a +/- 1 step skew so brief
    clock drift does not lock users out.**
    """
    fixed_ts = 1234567890
    skewed_ts = fixed_ts - TOTP_DEFAULT_PERIOD_SECONDS
    skewed_code = compute_totp_code(
        secret_base32=_RFC6238_SHARED_SECRET_BASE32,
        timestamp_seconds=skewed_ts,
    )
    result = TotpMfaMethod.verify_challenge(
        user_id="u",
        challenge_id="c",
        proof={
            "code": skewed_code,
            "secret_base32": _RFC6238_SHARED_SECRET_BASE32,
            "timestamp_seconds": fixed_ts,
        },
    )
    testbase.assert_equal(result.verified, True)
    return


def test_totp_verify_rejects_wrong_code():
    """
    **Feature: 1-authentication MFA (TOTP reference)**
    **Property: verify_challenge returns verified=False with
    failure_reason='code_mismatch' on a wrong code.**
    """
    fixed_ts = 1234567890
    result = TotpMfaMethod.verify_challenge(
        user_id="u",
        challenge_id="c",
        proof={
            "code": "000000",
            "secret_base32": _RFC6238_SHARED_SECRET_BASE32,
            "timestamp_seconds": fixed_ts,
        },
    )
    testbase.assert_equal(result.verified, False)
    testbase.assert_equal(result.failure_reason, "code_mismatch")
    return


def test_totp_verify_rejects_missing_code():
    """
    **Feature: 1-authentication MFA (TOTP reference)**
    **Property: verify_challenge returns failure_reason='missing_code'
    when the proof omits the code field.**
    """
    result = TotpMfaMethod.verify_challenge(
        user_id="u",
        challenge_id="c",
        proof={"secret_base32": _RFC6238_SHARED_SECRET_BASE32},
    )
    testbase.assert_equal(result.verified, False)
    testbase.assert_equal(result.failure_reason, "missing_code")
    return


def test_totp_verify_rejects_missing_secret():
    """
    **Feature: 1-authentication MFA (TOTP reference)**
    **Property: verify_challenge returns
    failure_reason='missing_secret' when the proof omits the secret.**
    """
    result = TotpMfaMethod.verify_challenge(
        user_id="u",
        challenge_id="c",
        proof={"code": "123456"},
    )
    testbase.assert_equal(result.verified, False)
    testbase.assert_equal(result.failure_reason, "missing_secret")
    return


# ---------------------------------------------------------------------------
# Catalog integration
# ---------------------------------------------------------------------------

def test_mfa_method_extension_is_published():
    rtnval = is_class_published(target_class=MFAMethodExtension)
    testbase.assert_equal(rtnval, True)
    return


def test_catalog_includes_mfa_method_extension_entry():
    catalog = build_catalog()
    matched = None
    for entry in catalog.resource_entries:
        if entry.name == "MFAMethodExtension":
            matched = entry
            break
    testbase.assert_equal(matched is not None, True)
    testbase.assert_equal(
        matched.metadata.reference.endswith(".TotpMfaMethod"), True
    )
    return


def test_catalog_validator_resolves_mfa_method_reference():
    catalog = build_catalog()
    validate_catalog_against_code(catalog=catalog)
    return
