"""
.. module:: test_p10t_embed_signing_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ``8-embeddable-views`` M1 signing primitives.

.. moduleauthor:: Automation Mojo LLC

Covers:

* the fixed view-kind catalog (5 entries, names + component tags +
  read-scopes + supports_anonymous flag)
* :func:`issue_signed_url` produces the documented URL + canonical
  payload shapes
* :func:`verify_signed_url` returns the documented
  :class:`VerificationOutcome` for every documented branch — tamper,
  TTL, unknown key, malformed payload, and the success path

The signing module is framework-free; M1 leaves DB-backed key store
+ vault integration to follow-ups, so tests inject a callable
``key_resolver`` and a fixed ``now_unix`` for deterministic output.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from urllib.parse import parse_qs, urlparse

from automojo import testbase

from automojo.errors.exceptions import ConfigurationError, SemanticError

from automojo.pychestrate.webservice.embed import (
    EMBED_NAMESPACE_PREFIX,
    EmbedSigningKey,
    EmbedViewKind,
    SignedEmbedUrl,
    VIEW_KIND_ARTIFACT_PREVIEW,
    VIEW_KIND_PIPELINE_DAG,
    VIEW_KIND_PROJECT_DASHBOARD_TILE,
    VIEW_KIND_RUN_DETAIL,
    VIEW_KIND_RUN_LOG_STREAM,
    VerificationOutcome,
    get_view_kind,
    issue_signed_url,
    list_view_kinds,
    verify_signed_url,
)
from automojo.pychestrate.webservice.embed.signing import (
    AUDIENCE_QUERY_KEY,
    EXPIRES_QUERY_KEY,
    KEY_ID_QUERY_KEY,
    SIGNATURE_QUERY_KEY,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXED_NOW_UNIX: int = 1_700_000_000
_DEFAULT_TTL_SECONDS: int = 300
_TEST_KEY: EmbedSigningKey = EmbedSigningKey(
    key_id="key-alpha",
    key_bytes=b"test-key-bytes-do-not-reuse-in-prod",
)
_OTHER_KEY: EmbedSigningKey = EmbedSigningKey(
    key_id="key-beta",
    key_bytes=b"different-key-bytes",
)


def _resolver_for(*, key: EmbedSigningKey):
    """Build a key_resolver that returns ``key`` for its id."""

    def _resolve(key_id: str):
        if key_id == key.key_id:
            rtnval = key
            return rtnval
        rtnval = None
        return rtnval

    rtnval = _resolve
    return rtnval


def _multi_key_resolver(*keys: EmbedSigningKey):
    """Build a key_resolver covering several keys by id."""
    by_id = {k.key_id: k for k in keys}

    def _resolve(key_id: str):
        rtnval = by_id.get(key_id, None)
        return rtnval

    rtnval = _resolve
    return rtnval


def _issue_default(*, view_kind: str = VIEW_KIND_RUN_DETAIL,
                   resource_id: str = "run-001",
                   audience: str = "partner.example.com",
                   ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> SignedEmbedUrl:
    rtnval = issue_signed_url(
        view_kind=view_kind,
        resource_id=resource_id,
        audience=audience,
        ttl_seconds=ttl_seconds,
        signing_key=_TEST_KEY,
        now_unix=_FIXED_NOW_UNIX,
    )
    return rtnval


def _verify_default(*, signed: SignedEmbedUrl, now_unix: int = None,
                    key_resolver=None,
                    view_kind_override: str = None,
                    resource_id_override: str = None,
                    audience_override: str = None,
                    expires_override: int = None,
                    key_id_override: str = None,
                    signature_override: str = None) -> VerificationOutcome:
    parsed = urlparse(signed.url)
    qs = parse_qs(parsed.query)
    path_parts = parsed.path[len(EMBED_NAMESPACE_PREFIX):].split("/", 1)
    extracted_view_kind, extracted_resource_id = path_parts[0], path_parts[1]

    rtnval = verify_signed_url(
        view_kind=(
            view_kind_override if view_kind_override is not None else extracted_view_kind
        ),
        resource_id=(
            resource_id_override if resource_id_override is not None
            else extracted_resource_id
        ),
        audience=(
            audience_override if audience_override is not None
            else qs[AUDIENCE_QUERY_KEY][0]
        ),
        expires_unix=(
            expires_override if expires_override is not None
            else int(qs[EXPIRES_QUERY_KEY][0])
        ),
        key_id=(
            key_id_override if key_id_override is not None
            else qs[KEY_ID_QUERY_KEY][0]
        ),
        signature_hex=(
            signature_override if signature_override is not None
            else qs[SIGNATURE_QUERY_KEY][0]
        ),
        now_unix=(
            now_unix if now_unix is not None else _FIXED_NOW_UNIX + 60
        ),
        key_resolver=(
            key_resolver if key_resolver is not None
            else _resolver_for(key=_TEST_KEY)
        ),
    )
    return rtnval


# ---------------------------------------------------------------------------
# View-kind catalog (T1.3)
# ---------------------------------------------------------------------------

def test_catalog_lists_five_documented_view_kinds():
    """
    **Feature: 8-embeddable-views T1.3**
    **Property: list_view_kinds returns exactly the five fixed
    catalog entries documented in the spec.**
    """
    names = [vk.view_kind_name for vk in list_view_kinds()]
    expected = [
        VIEW_KIND_RUN_DETAIL,
        VIEW_KIND_RUN_LOG_STREAM,
        VIEW_KIND_ARTIFACT_PREVIEW,
        VIEW_KIND_PIPELINE_DAG,
        VIEW_KIND_PROJECT_DASHBOARD_TILE,
    ]
    testbase.assert_equal(names, expected)
    return


def test_catalog_run_detail_carries_documented_component_tag():
    """
    **Feature: 8-embeddable-views T1.3**
    **Property: run_detail maps to the pyc-run-detail component
    tag (Layer 9 contract).**
    """
    entry = get_view_kind(view_kind_name=VIEW_KIND_RUN_DETAIL)
    testbase.assert_equal(entry.component_tag, "pyc-run-detail")
    return


def test_catalog_log_stream_maps_to_log_stream_component():
    entry = get_view_kind(view_kind_name=VIEW_KIND_RUN_LOG_STREAM)
    testbase.assert_equal(entry.component_tag, "pyc-log-stream")
    return


def test_catalog_dashboard_tile_supports_anonymous_access():
    """
    **Feature: 8-embeddable-views T1.3**
    **Property: project_dashboard_tile is the only kind that
    supports_anonymous (kiosk / public-portal use case).**
    """
    for entry in list_view_kinds():
        if entry.view_kind_name == VIEW_KIND_PROJECT_DASHBOARD_TILE:
            testbase.assert_equal(entry.supports_anonymous, True)
        else:
            testbase.assert_equal(entry.supports_anonymous, False)
    return


def test_catalog_view_kind_dataclass_is_frozen():
    """
    **Feature: 8-embeddable-views T1.3**
    **Property: EmbedViewKind is a frozen dataclass.**
    """
    entry = get_view_kind(view_kind_name=VIEW_KIND_RUN_DETAIL)
    raised = False
    try:
        entry.component_tag = "different"
    except Exception:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_catalog_unknown_view_kind_raises_configuration_error():
    """
    **Feature: 8-embeddable-views T1.3**
    **Property: get_view_kind on a non-catalog name raises
    ConfigurationError naming the unknown name.**
    """
    raised = False
    error_text = ""
    try:
        get_view_kind(view_kind_name="does-not-exist")
    except ConfigurationError as xcpt:
        raised = True
        error_text = str(xcpt)
    testbase.assert_equal(raised, True)
    testbase.assert_equal("does-not-exist" in error_text, True)
    return


# ---------------------------------------------------------------------------
# issue_signed_url (T1.4)
# ---------------------------------------------------------------------------

def test_issue_emits_documented_url_shape():
    """
    **Feature: 8-embeddable-views T1.4**
    **Property: issued URL matches /embed/<view>/<rid>?a=&e=&k=&s=.**
    """
    signed = _issue_default()
    parsed = urlparse(signed.url)
    testbase.assert_equal(
        parsed.path, "/embed/run_detail/run-001"
    )
    qs = parse_qs(parsed.query)
    for key in (AUDIENCE_QUERY_KEY, EXPIRES_QUERY_KEY, KEY_ID_QUERY_KEY, SIGNATURE_QUERY_KEY):
        testbase.assert_equal(key in qs, True)
    return


def test_issue_canonical_payload_matches_spec_layout():
    """
    **Feature: 8-embeddable-views T1.4**
    **Property: canonical_payload is the documented
    "<view_kind>|<resource_id>|<audience>|<expires_unix>|<key_id>".**
    """
    signed = _issue_default()
    expected = "run_detail|run-001|partner.example.com|{}|key-alpha".format(
        signed.expires_unix
    )
    testbase.assert_equal(signed.canonical_payload, expected)
    return


def test_issue_expires_unix_equals_now_plus_ttl():
    """
    **Feature: 8-embeddable-views T1.4**
    **Property: expires_unix = now_unix + ttl_seconds.**
    """
    signed = _issue_default(ttl_seconds=600)
    testbase.assert_equal(signed.expires_unix, _FIXED_NOW_UNIX + 600)
    return


def test_issue_is_deterministic_for_same_inputs():
    """
    **Feature: 8-embeddable-views T1.4**
    **Property: Calling issue_signed_url twice with identical inputs
    yields identical URLs (HMAC is deterministic).**
    """
    signed_a = _issue_default()
    signed_b = _issue_default()
    testbase.assert_equal(signed_a.url, signed_b.url)
    return


def test_issue_signature_changes_when_resource_id_changes():
    """
    **Feature: 8-embeddable-views T1.4**
    **Property: Different resource_id yields a different signature
    (binding holds).**
    """
    signed_a = _issue_default(resource_id="run-001")
    signed_b = _issue_default(resource_id="run-002")
    qs_a = parse_qs(urlparse(signed_a.url).query)
    qs_b = parse_qs(urlparse(signed_b.url).query)
    testbase.assert_equal(
        qs_a[SIGNATURE_QUERY_KEY][0] != qs_b[SIGNATURE_QUERY_KEY][0], True
    )
    return


def test_issue_signature_changes_when_audience_changes():
    signed_a = _issue_default(audience="portal-a.example.com")
    signed_b = _issue_default(audience="portal-b.example.com")
    qs_a = parse_qs(urlparse(signed_a.url).query)
    qs_b = parse_qs(urlparse(signed_b.url).query)
    testbase.assert_equal(
        qs_a[SIGNATURE_QUERY_KEY][0] != qs_b[SIGNATURE_QUERY_KEY][0], True
    )
    return


def test_issue_rejects_unknown_view_kind_with_configuration_error():
    raised = False
    try:
        issue_signed_url(
            view_kind="bogus", resource_id="x", audience="y",
            ttl_seconds=60, signing_key=_TEST_KEY, now_unix=_FIXED_NOW_UNIX,
        )
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_issue_rejects_empty_resource_id_with_semantic_error():
    raised = False
    try:
        issue_signed_url(
            view_kind=VIEW_KIND_RUN_DETAIL, resource_id="", audience="y",
            ttl_seconds=60, signing_key=_TEST_KEY, now_unix=_FIXED_NOW_UNIX,
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_issue_rejects_empty_audience_with_semantic_error():
    raised = False
    try:
        issue_signed_url(
            view_kind=VIEW_KIND_RUN_DETAIL, resource_id="x", audience="",
            ttl_seconds=60, signing_key=_TEST_KEY, now_unix=_FIXED_NOW_UNIX,
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_issue_rejects_non_positive_ttl_with_semantic_error():
    raised = False
    try:
        issue_signed_url(
            view_kind=VIEW_KIND_RUN_DETAIL, resource_id="x", audience="y",
            ttl_seconds=0, signing_key=_TEST_KEY, now_unix=_FIXED_NOW_UNIX,
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_issue_rejects_separator_in_resource_id():
    """
    **Feature: 8-embeddable-views T1.4**
    **Property: A resource_id containing the canonical separator
    ``|`` is rejected — otherwise the parsed canonical payload would
    be ambiguous.**
    """
    raised = False
    try:
        issue_signed_url(
            view_kind=VIEW_KIND_RUN_DETAIL,
            resource_id="run|injected", audience="y",
            ttl_seconds=60, signing_key=_TEST_KEY, now_unix=_FIXED_NOW_UNIX,
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# verify_signed_url (T1.5)
# ---------------------------------------------------------------------------

def test_verify_returns_verified_for_fresh_signed_url():
    """
    **Feature: 8-embeddable-views T1.5**
    **Property: A fresh URL within its TTL signed by a known key
    verifies clean.**
    """
    signed = _issue_default()
    outcome = _verify_default(signed=signed)
    testbase.assert_equal(outcome, VerificationOutcome.VERIFIED)
    return


def test_verify_rejects_tampered_resource_id_as_signature_mismatch():
    """
    **Feature: 8-embeddable-views T1.5**
    **Property: Mutating the resource_id after signing invalidates
    the signature (constant-time mismatch).**
    """
    signed = _issue_default(resource_id="run-001")
    outcome = _verify_default(
        signed=signed, resource_id_override="run-002"
    )
    testbase.assert_equal(outcome, VerificationOutcome.SIGNATURE_MISMATCH)
    return


def test_verify_rejects_tampered_audience_as_signature_mismatch():
    signed = _issue_default()
    outcome = _verify_default(
        signed=signed, audience_override="malicious-portal.example.com"
    )
    testbase.assert_equal(outcome, VerificationOutcome.SIGNATURE_MISMATCH)
    return


def test_verify_rejects_tampered_expires_as_signature_mismatch():
    """
    **Feature: 8-embeddable-views T1.5**
    **Property: Replacing the embedded expiry with a later
    timestamp invalidates the signature — TTL extension via wire
    tampering is impossible.**
    """
    signed = _issue_default()
    outcome = _verify_default(
        signed=signed, expires_override=signed.expires_unix + 86400
    )
    testbase.assert_equal(outcome, VerificationOutcome.SIGNATURE_MISMATCH)
    return


def test_verify_rejects_signature_replaced_with_other_keys_signature():
    """
    **Feature: 8-embeddable-views T1.5**
    **Property: A URL signed by ``key-beta`` but presented as if
    signed by ``key-alpha`` is rejected (the resolver returns the
    alpha bytes; constant-time compare fails).**
    """
    signed_under_beta = issue_signed_url(
        view_kind=VIEW_KIND_RUN_DETAIL, resource_id="run-001",
        audience="x.example.com", ttl_seconds=300,
        signing_key=_OTHER_KEY, now_unix=_FIXED_NOW_UNIX,
    )
    qs = parse_qs(urlparse(signed_under_beta.url).query)
    rogue_signature = qs[SIGNATURE_QUERY_KEY][0]

    legitimate_signed = _issue_default()
    outcome = _verify_default(
        signed=legitimate_signed,
        signature_override=rogue_signature,
    )
    testbase.assert_equal(outcome, VerificationOutcome.SIGNATURE_MISMATCH)
    return


def test_verify_returns_expired_when_now_at_or_past_expires():
    signed = _issue_default(ttl_seconds=60)
    outcome = _verify_default(
        signed=signed, now_unix=signed.expires_unix
    )
    testbase.assert_equal(outcome, VerificationOutcome.EXPIRED)
    return


def test_verify_returns_expired_when_now_well_past_expires():
    signed = _issue_default(ttl_seconds=60)
    outcome = _verify_default(
        signed=signed, now_unix=signed.expires_unix + 3600
    )
    testbase.assert_equal(outcome, VerificationOutcome.EXPIRED)
    return


def test_verify_returns_signing_key_unknown_when_resolver_returns_none():
    """
    **Feature: 8-embeddable-views T1.5**
    **Property: When the resolver returns None for the requested
    key id (rotated-out / revoked / never-existed) the outcome is
    SIGNING_KEY_UNKNOWN, not SIGNATURE_MISMATCH.**
    """
    signed = _issue_default()
    outcome = _verify_default(
        signed=signed,
        key_resolver=lambda kid: None,
    )
    testbase.assert_equal(outcome, VerificationOutcome.SIGNING_KEY_UNKNOWN)
    return


def test_verify_returns_signing_key_unknown_when_resolver_raises():
    """
    **Feature: 8-embeddable-views T1.5**
    **Property: A resolver that raises (e.g. DB outage) is
    reclassified as SIGNING_KEY_UNKNOWN — verification never lets a
    transient backend error become a successful verification.**
    """

    def _raising_resolver(key_id: str):
        raise RuntimeError("simulated DB outage")

    signed = _issue_default()
    outcome = _verify_default(signed=signed, key_resolver=_raising_resolver)
    testbase.assert_equal(outcome, VerificationOutcome.SIGNING_KEY_UNKNOWN)
    return


def test_verify_returns_malformed_for_empty_resource_id():
    signed = _issue_default()
    outcome = _verify_default(signed=signed, resource_id_override="")
    testbase.assert_equal(outcome, VerificationOutcome.MALFORMED_PAYLOAD)
    return


def test_verify_returns_malformed_for_empty_signature():
    signed = _issue_default()
    outcome = _verify_default(signed=signed, signature_override="")
    testbase.assert_equal(outcome, VerificationOutcome.MALFORMED_PAYLOAD)
    return


def test_verify_returns_malformed_for_unknown_view_kind():
    """
    **Feature: 8-embeddable-views T1.5**
    **Property: An off-catalog view_kind is treated as malformed
    payload (catalog drift) rather than signature_mismatch.**
    """
    signed = _issue_default()
    outcome = _verify_default(signed=signed, view_kind_override="bogus")
    testbase.assert_equal(outcome, VerificationOutcome.MALFORMED_PAYLOAD)
    return


def test_verify_round_trips_across_all_five_view_kinds():
    """
    **Feature: 8-embeddable-views T1.5**
    **Property: Issue + verify works for every documented view kind.**
    """
    for view_kind_name in (
        VIEW_KIND_RUN_DETAIL,
        VIEW_KIND_RUN_LOG_STREAM,
        VIEW_KIND_ARTIFACT_PREVIEW,
        VIEW_KIND_PIPELINE_DAG,
        VIEW_KIND_PROJECT_DASHBOARD_TILE,
    ):
        signed = _issue_default(view_kind=view_kind_name)
        outcome = _verify_default(signed=signed)
        testbase.assert_equal(outcome, VerificationOutcome.VERIFIED)
    return


def test_verify_resolves_correct_key_when_multiple_keys_exist():
    """
    **Feature: 8-embeddable-views T1.5**
    **Property: A multi-key resolver picks by ``key_id``; URLs
    signed under different keys verify against their own key only.**
    """
    signed_alpha = _issue_default()  # signed under _TEST_KEY (alpha)
    signed_beta = issue_signed_url(
        view_kind=VIEW_KIND_RUN_DETAIL, resource_id="run-002",
        audience="portal.example.com", ttl_seconds=300,
        signing_key=_OTHER_KEY, now_unix=_FIXED_NOW_UNIX,
    )

    multi_resolver = _multi_key_resolver(_TEST_KEY, _OTHER_KEY)

    outcome_a = _verify_default(signed=signed_alpha, key_resolver=multi_resolver)
    outcome_b = _verify_default(signed=signed_beta, key_resolver=multi_resolver)
    testbase.assert_equal(outcome_a, VerificationOutcome.VERIFIED)
    testbase.assert_equal(outcome_b, VerificationOutcome.VERIFIED)
    return


# ---------------------------------------------------------------------------
# Sanity checks on dataclass shapes
# ---------------------------------------------------------------------------

def test_signed_embed_url_is_frozen():
    signed = _issue_default()
    raised = False
    try:
        signed.url = "different"
    except Exception:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_signing_key_is_frozen():
    raised = False
    try:
        _TEST_KEY.key_id = "different"
    except Exception:
        raised = True
    testbase.assert_equal(raised, True)
    return
