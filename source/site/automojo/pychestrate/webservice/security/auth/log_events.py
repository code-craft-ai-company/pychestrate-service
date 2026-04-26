"""
.. module:: security.auth.log_events
    :synopsis: Structured auth log events with SECRET-field redaction (M3 T3.2).

The 1-authentication M3 hardening pass mandates structured
log events for every login outcome and session lifecycle
edge, with token-bearing fields tagged so an upstream log
scrubber drops them before write. This module exposes:

* Stable log-event name constants
  (``AUTH_LOGIN_SUCCEEDED`` / ``AUTH_LOGIN_REJECTED`` /
  ``AUTH_SESSION_OPENED`` / ``AUTH_SESSION_CLOSED`` /
  ``AUTH_SESSION_REFRESHED`` / ``AUTH_OIDC_DISCOVERY_REFRESHED`` /
  ``AUTH_SAML_METADATA_REFRESHED`` /
  ``AUTH_MFA_CHALLENGE_ISSUED`` /
  ``AUTH_MFA_CHALLENGE_VERIFIED``).
* :func:`emit_log_event` — single emission seam that
  scrubs declared SECRET keys before passing the payload
  to stdlib :mod:`logging`.
* :func:`redact_secrets` — pure helper that returns a
  copy of the payload with secret keys swapped for the
  :data:`SECRET_REDACTED_MARKER` so the payload is safe to
  log even when an upstream scrubber isn't installed.

The default :data:`SECRET_FIELD_NAMES` set covers the
canonical token-bearing field names used across the OIDC /
SAML / local flows: id_token, access_token, refresh_token,
authorization_code, password, mfa_code, secret_payload,
pkce_verifier, saml_response_xml, raw_assertion_xml.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Any, Iterable, Mapping, Optional


LOGGER_NAME: str = "pychestrate.auth"

SECRET_REDACTED_MARKER: str = "<redacted>"


# Default set of payload keys that carry secret material.
# Callers can pass an extended set to :func:`emit_log_event`
# when a flow surfaces a non-canonical secret name.
SECRET_FIELD_NAMES: frozenset = frozenset({
    "id_token",
    "access_token",
    "refresh_token",
    "access_token_payload",
    "refresh_token_payload",
    "access_token_enc",
    "refresh_token_enc",
    "authorization_code",
    "code",
    "password",
    "password_hash",
    "mfa_code",
    "secret_payload",
    "secret_ref",
    "pkce_verifier",
    "pkce_verifier_enc",
    "saml_response_xml",
    "raw_assertion_xml",
    "client_secret",
    "signature_value",
})


# Stable event-name tokens.
AUTH_LOGIN_SUCCEEDED: str = "auth.login.succeeded"
AUTH_LOGIN_REJECTED: str = "auth.login.rejected"
AUTH_SESSION_OPENED: str = "auth.session.opened"
AUTH_SESSION_CLOSED: str = "auth.session.closed"
AUTH_SESSION_REFRESHED: str = "auth.session.refreshed"
AUTH_OIDC_DISCOVERY_REFRESHED: str = "auth.oidc.discovery.refreshed"
AUTH_OIDC_DISCOVERY_REFRESH_FAILED: str = (
    "auth.oidc.discovery.refresh_failed"
)
AUTH_SAML_METADATA_REFRESHED: str = "auth.saml.metadata.refreshed"
AUTH_SAML_METADATA_REFRESH_FAILED: str = (
    "auth.saml.metadata.refresh_failed"
)
AUTH_MFA_CHALLENGE_ISSUED: str = "auth.mfa.challenge.issued"
AUTH_MFA_CHALLENGE_VERIFIED: str = "auth.mfa.challenge.verified"
AUTH_MFA_CHALLENGE_REJECTED: str = "auth.mfa.challenge.rejected"


def redact_secrets(
        *,
        payload: Mapping[str, Any],
        extra_secret_keys: Optional[Iterable[str]] = None
    ) -> dict:
    """
        Return a shallow copy of ``payload`` with every key
        in :data:`SECRET_FIELD_NAMES` (plus any caller-supplied
        ``extra_secret_keys``) replaced by
        :data:`SECRET_REDACTED_MARKER`. Nested mappings are
        scrubbed recursively; lists / tuples of mappings are
        scrubbed element-wise. Non-mapping containers are
        passed through unchanged.

        :param payload: Source mapping.
        :param extra_secret_keys: Optional iterable of
                                  additional secret key
                                  names to redact.

        :returns: New ``dict`` with secrets replaced.
    """
    if payload is None:
        rtnval: dict = {}
        return rtnval
    secret_keys = set(SECRET_FIELD_NAMES)
    if extra_secret_keys is not None:
        for key in extra_secret_keys:
            secret_keys.add(key)
    rtnval = _redact_recursive(node=payload, secret_keys=secret_keys)
    return rtnval


def emit_log_event(
        *,
        event_name: str,
        payload: Mapping[str, Any],
        level: int = logging.INFO,
        extra_secret_keys: Optional[Iterable[str]] = None,
        logger: Optional[logging.Logger] = None
    ) -> dict:
    """
        Scrub secrets out of ``payload`` and emit it as a
        structured log line on the auth logger.

        The redacted payload is also returned so callers /
        tests can assert against the exact bytes that landed
        on the logger without re-scrubbing.

        :param event_name: Stable event-name constant from
                           this module.
        :param payload: Payload mapping; secret keys are
                        scrubbed before emission.
        :param level: ``logging.INFO`` by default; rejection
                      events typically pass
                      ``logging.WARNING``.
        :param extra_secret_keys: Optional additional secret
                                  keys to redact.
        :param logger: Optional logger override; defaults to
                       :data:`LOGGER_NAME`.

        :returns: The scrubbed payload that was logged.
    """
    materialized_logger = (
        logger if logger is not None
        else logging.getLogger(LOGGER_NAME)
    )
    redacted = redact_secrets(
        payload=payload, extra_secret_keys=extra_secret_keys,
    )
    materialized_logger.log(
        level,
        event_name,
        extra={"event_name": event_name, "payload": redacted},
    )
    rtnval = redacted
    return rtnval


def _redact_recursive(
        *, node: Any, secret_keys: set
    ) -> Any:
    if isinstance(node, Mapping):
        rtnval: dict = {}
        for key, value in node.items():
            if key in secret_keys:
                rtnval[key] = SECRET_REDACTED_MARKER
                continue
            rtnval[key] = _redact_recursive(
                node=value, secret_keys=secret_keys,
            )
        return rtnval
    if isinstance(node, (list, tuple)):
        materialized: list = []
        for element in node:
            materialized.append(
                _redact_recursive(node=element, secret_keys=secret_keys),
            )
        if isinstance(node, tuple):
            return tuple(materialized)
        return materialized
    rtnval = node
    return rtnval
