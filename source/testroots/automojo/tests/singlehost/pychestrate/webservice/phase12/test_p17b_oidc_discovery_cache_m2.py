"""
.. module:: test_p17b_oidc_discovery_cache_m2
    :synopsis: Tests for P17b — 1-authentication M2 OIDC discovery cache.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import Optional

from automojo import testbase

from automojo.pychestrate.webservice.security.auth.oidc import discovery
from automojo.pychestrate.webservice.security.auth.oidc.discovery import (
    DEFAULT_DISCOVERY_TTL,
    DiscoveryDocument,
    DiscoveryFetchResult,
    MAX_DISCOVERY_TTL,
    MIN_DISCOVERY_TTL,
    cached_document,
    clamp_ttl,
    invalidate,
    load_and_cache,
    parse_discovery_document,
    reset_for_testing,
)


def _prepare_runtime() -> None:
    reset_for_testing()
    return


def _build_payload(
        *,
        issuer: str = "https://idp.example.com",
        extra: Optional[dict] = None
    ) -> dict:
    payload = {
        "issuer": issuer,
        "authorization_endpoint": issuer + "/authorize",
        "token_endpoint": issuer + "/token",
        "jwks_uri": issuer + "/jwks",
    }
    if extra is not None:
        payload.update(extra)
    return payload


def _build_fetch_result(
        *,
        issuer: str = "https://idp.example.com",
        max_age_seconds: Optional[int] = None
    ) -> DiscoveryFetchResult:
    document = parse_discovery_document(payload=_build_payload(issuer=issuer))
    rtnval = DiscoveryFetchResult(
        document=document, max_age_seconds=max_age_seconds,
    )
    return rtnval


# -------------------------------------
# parse_discovery_document
# -------------------------------------

def test_parse_discovery_document_validates_required_fields():
    """
    **Feature: 1-authentication (M2)**
    **Property: parse_discovery_document raises ValueError
    when any required field is missing.**
    """
    raised_count = 0
    for missing_key in (
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "jwks_uri",
    ):
        payload = _build_payload()
        del payload[missing_key]
        try:
            parse_discovery_document(payload=payload)
        except ValueError:
            raised_count = raised_count + 1
    testbase.assert_equal(raised_count, 4)
    return


def test_parse_discovery_document_rejects_non_string_field():
    """
    **Feature: 1-authentication (M2)**
    **Property: a non-string required field surfaces as
    ValueError.**
    """
    payload = _build_payload()
    payload["jwks_uri"] = 42
    raised = False
    try:
        parse_discovery_document(payload=payload)
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_parse_discovery_document_preserves_raw_payload():
    """
    **Feature: 1-authentication (M2)**
    **Property: the parsed DiscoveryDocument carries the
    full raw payload so callers can read non-canonical
    fields.**
    """
    payload = _build_payload(extra={"end_session_endpoint": "/logout"})
    document = parse_discovery_document(payload=payload)
    testbase.assert_equal(
        document.raw.get("end_session_endpoint"), "/logout",
    )
    testbase.assert_equal(
        document.issuer, "https://idp.example.com",
    )
    return


# -------------------------------------
# clamp_ttl
# -------------------------------------

def test_clamp_ttl_none_falls_back_to_default():
    """
    **Feature: 1-authentication (M2)**
    **Property: clamp_ttl(None) returns DEFAULT_DISCOVERY_TTL.**
    """
    testbase.assert_equal(
        clamp_ttl(max_age_seconds=None), DEFAULT_DISCOVERY_TTL,
    )
    return


def test_clamp_ttl_below_minimum_clamps_up():
    """
    **Feature: 1-authentication (M2)**
    **Property: a max-age below MIN_DISCOVERY_TTL clamps up
    so a hostile IdP can't force rapid re-fetching.**
    """
    testbase.assert_equal(
        clamp_ttl(max_age_seconds=10), MIN_DISCOVERY_TTL,
    )
    testbase.assert_equal(
        clamp_ttl(max_age_seconds=0), MIN_DISCOVERY_TTL,
    )
    return


def test_clamp_ttl_above_maximum_clamps_down():
    """
    **Feature: 1-authentication (M2)**
    **Property: a max-age above MAX_DISCOVERY_TTL clamps
    down so an arbitrarily-stale doc can't pin in cache.**
    """
    rtnval = clamp_ttl(max_age_seconds=10 * 24 * 3600)
    testbase.assert_equal(rtnval, MAX_DISCOVERY_TTL)
    return


def test_clamp_ttl_in_range_passes_through():
    """
    **Feature: 1-authentication (M2)**
    **Property: a max-age in the [min, max] window
    round-trips without modification.**
    """
    expected = timedelta(minutes=30)
    rtnval = clamp_ttl(max_age_seconds=int(expected.total_seconds()))
    testbase.assert_equal(rtnval, expected)
    return


# -------------------------------------
# load_and_cache
# -------------------------------------

def test_load_and_cache_caches_first_fetch():
    """
    **Feature: 1-authentication (M2)**
    **Property: the first load_and_cache call hits the
    fetcher; the second call within the TTL serves from
    cache and skips the fetcher.**
    """
    _prepare_runtime()
    fetch_count = {"n": 0}

    def _fetcher(issuer):
        fetch_count["n"] = fetch_count["n"] + 1
        return _build_fetch_result(issuer=issuer, max_age_seconds=600)

    document_a = load_and_cache(
        issuer="https://idp.example.com",
        fetcher=_fetcher,
    )
    document_b = load_and_cache(
        issuer="https://idp.example.com",
        fetcher=_fetcher,
    )
    testbase.assert_equal(
        document_a.issuer, "https://idp.example.com",
    )
    testbase.assert_equal(document_a, document_b)
    testbase.assert_equal(fetch_count["n"], 1)
    return


def test_load_and_cache_refetches_after_ttl_expiry():
    """
    **Feature: 1-authentication (M2)**
    **Property: a load_and_cache call past the entry's
    deadline refetches.**
    """
    _prepare_runtime()
    fetch_count = {"n": 0}

    def _fetcher(issuer):
        fetch_count["n"] = fetch_count["n"] + 1
        return _build_fetch_result(issuer=issuer, max_age_seconds=600)

    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    load_and_cache(
        issuer="https://idp.example.com",
        fetcher=_fetcher,
        now=anchor,
    )
    load_and_cache(
        issuer="https://idp.example.com",
        fetcher=_fetcher,
        now=anchor + timedelta(hours=2),
    )
    testbase.assert_equal(fetch_count["n"], 2)
    return


def test_load_and_cache_force_refresh_bypasses_cache():
    """
    **Feature: 1-authentication (M2)**
    **Property: force_refresh=True calls the fetcher even
    when the cache is warm.**
    """
    _prepare_runtime()
    fetch_count = {"n": 0}

    def _fetcher(issuer):
        fetch_count["n"] = fetch_count["n"] + 1
        return _build_fetch_result(issuer=issuer, max_age_seconds=600)

    load_and_cache(
        issuer="https://idp.example.com", fetcher=_fetcher,
    )
    load_and_cache(
        issuer="https://idp.example.com",
        fetcher=_fetcher,
        force_refresh=True,
    )
    testbase.assert_equal(fetch_count["n"], 2)
    return


def test_load_and_cache_clamps_low_max_age():
    """
    **Feature: 1-authentication (M2)**
    **Property: a fetcher returning max_age_seconds=10 is
    clamped to MIN_DISCOVERY_TTL — the next load 1 hour
    later still hits the cache.**
    """
    _prepare_runtime()
    fetch_count = {"n": 0}

    def _fetcher(issuer):
        fetch_count["n"] = fetch_count["n"] + 1
        return _build_fetch_result(issuer=issuer, max_age_seconds=10)

    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    load_and_cache(
        issuer="https://idp.example.com", fetcher=_fetcher, now=anchor,
    )
    # 60 seconds later — well below the 5-minute clamped
    # floor so the cache is still warm.
    load_and_cache(
        issuer="https://idp.example.com",
        fetcher=_fetcher,
        now=anchor + timedelta(seconds=60),
    )
    testbase.assert_equal(fetch_count["n"], 1)
    return


def test_load_and_cache_rejects_empty_issuer():
    """
    **Feature: 1-authentication (M2)**
    **Property: an empty issuer raises ValueError.**
    """
    _prepare_runtime()
    raised = False
    try:
        load_and_cache(issuer="", fetcher=lambda i: None)
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_load_and_cache_raises_when_fetcher_returns_none():
    """
    **Feature: 1-authentication (M2)**
    **Property: a fetcher returning None surfaces as
    RuntimeError so the caller can fall back to a stale
    document or surface a 503.**
    """
    _prepare_runtime()
    raised = False
    try:
        load_and_cache(
            issuer="https://idp.example.com",
            fetcher=lambda i: None,
        )
    except RuntimeError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# cached_document + invalidate
# -------------------------------------

def test_cached_document_returns_none_when_not_loaded():
    """
    **Feature: 1-authentication (M2)**
    **Property: cached_document returns None for an issuer
    that hasn't been loaded.**
    """
    _prepare_runtime()
    testbase.assert_equal(
        cached_document(issuer="https://idp.example.com"),
        None,
    )
    return


def test_cached_document_returns_loaded_entry():
    """
    **Feature: 1-authentication (M2)**
    **Property: cached_document returns the document loaded
    by a prior load_and_cache call within the TTL.**
    """
    _prepare_runtime()

    def _fetcher(issuer):
        return _build_fetch_result(issuer=issuer, max_age_seconds=3600)

    load_and_cache(
        issuer="https://idp.example.com", fetcher=_fetcher,
    )
    document = cached_document(issuer="https://idp.example.com")
    testbase.assert_equal(document is not None, True)
    testbase.assert_equal(document.issuer, "https://idp.example.com")
    return


def test_cached_document_returns_none_after_expiry():
    """
    **Feature: 1-authentication (M2)**
    **Property: cached_document past the entry's TTL
    returns None and removes the row.**
    """
    _prepare_runtime()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)

    def _fetcher(issuer):
        return _build_fetch_result(issuer=issuer, max_age_seconds=600)

    load_and_cache(
        issuer="https://idp.example.com",
        fetcher=_fetcher,
        now=anchor,
    )
    rtnval = cached_document(
        issuer="https://idp.example.com",
        now=anchor + timedelta(hours=2),
    )
    testbase.assert_equal(rtnval, None)
    return


def test_invalidate_drops_cached_entry():
    """
    **Feature: 1-authentication (M2)**
    **Property: invalidate(issuer) drops the cached row;
    returns True on success, False on miss.**
    """
    _prepare_runtime()

    def _fetcher(issuer):
        return _build_fetch_result(issuer=issuer, max_age_seconds=3600)

    load_and_cache(
        issuer="https://idp.example.com", fetcher=_fetcher,
    )
    first = invalidate(issuer="https://idp.example.com")
    second = invalidate(issuer="https://idp.example.com")
    testbase.assert_equal(first, True)
    testbase.assert_equal(second, False)
    testbase.assert_equal(
        cached_document(issuer="https://idp.example.com"),
        None,
    )
    return
