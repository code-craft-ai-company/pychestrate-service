"""
.. module:: security.auth.metrics_emitter
    :synopsis: Auth metric definitions + recorder helpers (M3 T3.1).

The 1-authentication M3 hardening pass mandates that every
auth flow emits the metrics named in NFR-3 of the
``1-authentication`` requirements document. This module ships:

* :func:`register_auth_metrics` — bootstrap helper that
  registers every auth-side definition with the timeseries
  facade. Called once at app startup.
* Per-flow recorder helpers
  (:func:`record_login`, :func:`record_local_login_failure`,
  :func:`record_mfa_failure`,
  :func:`record_oidc_discovery_refresh_failure`,
  :func:`record_saml_metadata_refresh_failure`,
  :func:`record_token_refresh`,
  :func:`set_session_active_count`) that the OIDC / SAML /
  local / MFA paths call so the recording happens through
  one well-typed seam instead of a scatter of
  ``write_counter`` calls.

Histograms land when the timeseries M2 ships the
bucket-aware write path; until then
:data:`pychestrate_auth_login_duration_seconds` is declared
as a histogram definition for forward-compat but the
emitter helpers don't try to write samples through the M1
counter/gauge path.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Mapping, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.metrics.timeseries import service as metrics_service
from automojo.pychestrate.webservice.metrics.timeseries.facade import (
    MetricDefinition,
    MetricKind,
    get_metric_registry,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)


# Stable metric names — these are what NFR-3 mandates. Keep
# the full set as module-level constants so callers can read
# them back without re-declaring.
METRIC_LOGIN_TOTAL: str = "pychestrate_auth_login_total"
METRIC_LOGIN_DURATION_SECONDS: str = (
    "pychestrate_auth_login_duration_seconds"
)
METRIC_LOCAL_LOGIN_FAILURES_TOTAL: str = (
    "pychestrate_auth_local_login_failures_total"
)
METRIC_MFA_FAILURES_TOTAL: str = (
    "pychestrate_auth_mfa_failures_total"
)
METRIC_SESSION_ACTIVE: str = "pychestrate_auth_session_active"
METRIC_SAML_METADATA_REFRESH_FAILURES_TOTAL: str = (
    "pychestrate_auth_saml_metadata_refresh_failures_total"
)
METRIC_OIDC_DISCOVERY_REFRESH_FAILURES_TOTAL: str = (
    "pychestrate_auth_oidc_discovery_refresh_failures_total"
)
METRIC_TOKEN_REFRESH_TOTAL: str = (
    "pychestrate_auth_token_refresh_total"
)


# Stable outcome / reason tokens — also surfaced here so the
# recorder helpers can validate inputs without an
# import-cycle to each flow module.
LOGIN_OUTCOME_SUCCEEDED: str = "succeeded"
LOGIN_OUTCOME_REJECTED: str = "rejected"
LOGIN_OUTCOME_MFA_REQUIRED: str = "mfa_required"

TOKEN_REFRESH_OUTCOME_REFRESHED: str = "refreshed"
TOKEN_REFRESH_OUTCOME_SKIPPED_FRESH: str = "skipped_fresh"
TOKEN_REFRESH_OUTCOME_FAILED: str = "failed"


_AUTH_METRIC_DEFINITIONS: Tuple[MetricDefinition, ...] = (
    MetricDefinition(
        name=METRIC_LOGIN_TOTAL,
        kind=MetricKind.COUNTER,
        label_names=("provider_kind", "provider_name", "outcome"),
        help_text=(
            "Count of completed login attempts per "
            "provider and outcome."
        ),
    ),
    MetricDefinition(
        name=METRIC_LOGIN_DURATION_SECONDS,
        kind=MetricKind.HISTOGRAM,
        label_names=("provider_kind", "provider_name", "outcome"),
        help_text=(
            "End-to-end login duration in seconds. "
            "Histogram emission lands when timeseries M2 ships."
        ),
        buckets=(
            0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
        ),
    ),
    MetricDefinition(
        name=METRIC_LOCAL_LOGIN_FAILURES_TOTAL,
        kind=MetricKind.COUNTER,
        label_names=("reason",),
        help_text=(
            "Count of local credential login failures, "
            "labeled by failure reason."
        ),
    ),
    MetricDefinition(
        name=METRIC_MFA_FAILURES_TOTAL,
        kind=MetricKind.COUNTER,
        label_names=("method",),
        help_text=(
            "Count of MFA verify failures per method "
            "(totp / webauthn / push)."
        ),
    ),
    MetricDefinition(
        name=METRIC_SESSION_ACTIVE,
        kind=MetricKind.GAUGE,
        label_names=(),
        help_text=(
            "Current count of un-expired auth_sessions rows."
        ),
    ),
    MetricDefinition(
        name=METRIC_SAML_METADATA_REFRESH_FAILURES_TOTAL,
        kind=MetricKind.COUNTER,
        label_names=("provider_name",),
        help_text=(
            "Count of failed SAML metadata refresh attempts "
            "per IdP."
        ),
    ),
    MetricDefinition(
        name=METRIC_OIDC_DISCOVERY_REFRESH_FAILURES_TOTAL,
        kind=MetricKind.COUNTER,
        label_names=("issuer",),
        help_text=(
            "Count of failed OIDC discovery refresh "
            "attempts per issuer."
        ),
    ),
    MetricDefinition(
        name=METRIC_TOKEN_REFRESH_TOTAL,
        kind=MetricKind.COUNTER,
        label_names=("outcome",),
        help_text=(
            "Count of OIDC token refresh attempts by "
            "outcome (refreshed / skipped_fresh / failed)."
        ),
    ),
)


def list_auth_metric_definitions() -> Tuple[MetricDefinition, ...]:
    """
        Return the canonical tuple of auth metric definitions
        that :func:`register_auth_metrics` would seed.
        Exposed so test fixtures can iterate the set without
        re-declaring it.
    """
    rtnval = _AUTH_METRIC_DEFINITIONS
    return rtnval


def register_auth_metrics(*, db_session: DbSession) -> None:
    """
        Register every auth metric definition with the
        timeseries facade. Idempotent: a re-register
        overwrites the prior definition with the same
        instance, which is fine because the definitions are
        frozen dataclasses.

        :param db_session: Active SQLAlchemy session — the
                           timeseries service emits a
                           ``definition.registered`` event
                           on each register call.
    """
    for definition in _AUTH_METRIC_DEFINITIONS:
        metrics_service.register_definition(
            db_session=db_session, definition=definition,
        )
    return


def _safe_write_counter(
        *,
        db_session: DbSession,
        name: str,
        labels: Mapping[str, Any]
    ) -> None:
    """
        Internal helper: write a counter delta of 1.0 only
        when the metric definition is in the registry. The
        auth flows call the recorder helpers
        unconditionally; deployments / tests that haven't
        bootstrapped the timeseries driver simply skip
        emission instead of crashing the user-facing flow.
    """
    registry = get_metric_registry()
    if registry.find(name=name) is None:
        return
    try:
        metrics_service.write_counter(
            db_session=db_session,
            name=name,
            delta=1.0,
            labels=dict(labels),
        )
    except Exception:
        # Metrics emission is best-effort — never break a
        # login / refresh on a metric-side failure.
        return
    return


def _safe_write_gauge(
        *,
        db_session: DbSession,
        name: str,
        value: float,
        labels: Mapping[str, Any]
    ) -> None:
    registry = get_metric_registry()
    if registry.find(name=name) is None:
        return
    try:
        metrics_service.write_gauge(
            db_session=db_session,
            name=name,
            value=float(value),
            labels=dict(labels),
        )
    except Exception:
        return
    return


def record_login(
        *,
        db_session: DbSession,
        provider_kind: AuthProviderKind,
        provider_name: str,
        outcome: str
    ) -> None:
    """
        Increment :data:`METRIC_LOGIN_TOTAL` by 1 for
        ``(provider_kind, provider_name, outcome)``.
    """
    _safe_write_counter(
        db_session=db_session,
        name=METRIC_LOGIN_TOTAL,
        labels={
            "provider_kind": provider_kind.value,
            "provider_name": provider_name,
            "outcome": outcome,
        },
    )
    return


def record_local_login_failure(
        *,
        db_session: DbSession,
        reason: str
    ) -> None:
    """
        Increment :data:`METRIC_LOCAL_LOGIN_FAILURES_TOTAL`
        for the failure ``reason`` (``bad_password`` /
        ``user_not_found`` / ``mfa_required`` /
        ``backoff_active`` / etc.).
    """
    _safe_write_counter(
        db_session=db_session,
        name=METRIC_LOCAL_LOGIN_FAILURES_TOTAL,
        labels={"reason": reason},
    )
    return


def record_mfa_failure(
        *,
        db_session: DbSession,
        method_name: str
    ) -> None:
    """
        Increment :data:`METRIC_MFA_FAILURES_TOTAL` for the
        named MFA method when its
        :meth:`MFAMethodExtension.verify_response` rejects
        the user-supplied response.
    """
    _safe_write_counter(
        db_session=db_session,
        name=METRIC_MFA_FAILURES_TOTAL,
        labels={"method": method_name},
    )
    return


def record_oidc_discovery_refresh_failure(
        *,
        db_session: DbSession,
        issuer: str
    ) -> None:
    """
        Increment :data:`METRIC_OIDC_DISCOVERY_REFRESH_FAILURES_TOTAL`
        for the named issuer.
    """
    _safe_write_counter(
        db_session=db_session,
        name=METRIC_OIDC_DISCOVERY_REFRESH_FAILURES_TOTAL,
        labels={"issuer": issuer},
    )
    return


def record_saml_metadata_refresh_failure(
        *,
        db_session: DbSession,
        provider_name: str
    ) -> None:
    """
        Increment :data:`METRIC_SAML_METADATA_REFRESH_FAILURES_TOTAL`
        for the named SAML IdP.
    """
    _safe_write_counter(
        db_session=db_session,
        name=METRIC_SAML_METADATA_REFRESH_FAILURES_TOTAL,
        labels={"provider_name": provider_name},
    )
    return


def record_token_refresh(
        *,
        db_session: DbSession,
        outcome: str
    ) -> None:
    """
        Increment :data:`METRIC_TOKEN_REFRESH_TOTAL` for
        the supplied outcome (``refreshed`` /
        ``skipped_fresh`` / ``failed``).
    """
    _safe_write_counter(
        db_session=db_session,
        name=METRIC_TOKEN_REFRESH_TOTAL,
        labels={"outcome": outcome},
    )
    return


def set_session_active_count(
        *,
        db_session: DbSession,
        count: int
    ) -> None:
    """
        Record the current count of un-expired ``auth_sessions``
        rows on :data:`METRIC_SESSION_ACTIVE`. Production
        deployments call this from a periodic job; tests can
        call it inline.
    """
    _safe_write_gauge(
        db_session=db_session,
        name=METRIC_SESSION_ACTIVE,
        value=float(count),
        labels={},
    )
    return
