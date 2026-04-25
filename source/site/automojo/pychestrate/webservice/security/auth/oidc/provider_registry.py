"""
.. module:: security.auth.oidc.provider_registry
    :synopsis: Process-level registry of configured OIDC providers.

The :class:`OidcAuthProvider` factory implementation is
keyed on ``provider_name`` — a string the controller pulls
from the request URL (``/auth/oidc/{provider_name}/login``).
For the factory to know which IdP that name maps to, the
service bootstrap registers an :class:`OidcProviderConfig`
per configured provider through :func:`register_oidc_provider`.

The registry is intentionally tiny: a process-local dict
guarded by a lock plus :func:`reset_for_testing` so each
test starts clean. Production deployments register every
configured provider once at app startup; multi-instance
deployments register the same set on every instance because
the OIDC swap is stateless once the state row lands in
Postgres.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.security.auth.oidc.id_token import (
    JwksKeyResolver,
)
from automojo.pychestrate.webservice.security.auth.oidc.token_exchange import (
    TokenExchangeFetcher,
)


SessionFactory = Callable[[], DbSession]


@dataclass(frozen=True)
class OidcProviderConfig:
    """
        Per-provider configuration the
        :class:`OidcAuthProvider` factory consults at flow
        time.

        :param provider_name: Stable name (matches the URL
                              segment in
                              ``/auth/oidc/{provider_name}/...``).
        :param authorization_endpoint: IdP authorization
                                       endpoint URL.
        :param token_endpoint: IdP token endpoint URL.
        :param expected_issuer: Issuer the id_token's ``iss``
                                claim must equal.
        :param client_id: OIDC client id.
        :param redirect_uri: Same redirect_uri the IdP echoes
                             back on the callback.
        :param token_fetcher: Pluggable token-exchange
                              callable. Production wires
                              ``urllib``; tests hand in a
                              deterministic stub.
        :param key_resolver: Pluggable JWKS-key resolver.
        :param session_factory: Callable returning a fresh
                                ``DbSession`` for the begin
                                / complete halves of the flow.
        :param client_secret: Optional confidential-client
                              secret.
        :param scopes: OAuth scopes the begin-redirect
                       requests; defaults to
                       ``("openid", "email", "profile")``.
    """
    provider_name: str
    authorization_endpoint: str
    token_endpoint: str
    expected_issuer: str
    client_id: str
    redirect_uri: str
    token_fetcher: TokenExchangeFetcher
    key_resolver: JwksKeyResolver
    session_factory: SessionFactory
    client_secret: Optional[str] = None
    scopes: Tuple[str, ...] = ("openid", "email", "profile")


_GUARD: threading.Lock = threading.Lock()
_REGISTRY: Dict[str, OidcProviderConfig] = {}


def register_oidc_provider(*, config: OidcProviderConfig) -> None:
    """
        Register an :class:`OidcProviderConfig` so the
        :class:`OidcAuthProvider` factory can dispatch to
        it by name.

        :raises: ValueError on empty / malformed config or
                 duplicate ``provider_name``.
    """
    if config is None:
        err_lines = ["register_oidc_provider requires a config."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    _validate_config(config=config)
    with _GUARD:
        existing = _REGISTRY.get(config.provider_name)
        if existing is not None:
            err_lines = [
                "OIDC provider already registered.",
                "PROVIDER_NAME: {}".format(config.provider_name),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        _REGISTRY[config.provider_name] = config
    return


def get_oidc_provider_config(*, provider_name: str) -> OidcProviderConfig:
    """
        Look up the :class:`OidcProviderConfig` registered
        under ``provider_name``.

        :raises: KeyError when no config is registered for
                 the name.
    """
    if provider_name is None or len(provider_name) == 0:
        err_lines = ["get_oidc_provider_config requires a provider_name."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    with _GUARD:
        existing = _REGISTRY.get(provider_name)
    if existing is None:
        err_lines = [
            "No OIDC provider registered for the given name.",
            "PROVIDER_NAME: {}".format(provider_name),
        ]
        err_msg = os.linesep.join(err_lines)
        raise KeyError(err_msg) from None
    rtnval = existing
    return rtnval


def list_oidc_provider_names() -> List[str]:
    """
        Snapshot the currently-registered provider names,
        sorted lexicographically.
    """
    with _GUARD:
        names = sorted(_REGISTRY.keys())
    rtnval = names
    return rtnval


def reset_for_testing() -> None:
    """
        Clear the registry. Test-only seam.
    """
    with _GUARD:
        _REGISTRY.clear()
    return


def _validate_config(*, config: OidcProviderConfig) -> None:
    fields_to_check = [
        ("provider_name", config.provider_name),
        ("authorization_endpoint", config.authorization_endpoint),
        ("token_endpoint", config.token_endpoint),
        ("expected_issuer", config.expected_issuer),
        ("client_id", config.client_id),
        ("redirect_uri", config.redirect_uri),
    ]
    for field_name, field_value in fields_to_check:
        if field_value is None or len(field_value) == 0:
            err_lines = [
                "OidcProviderConfig has an empty required field.",
                "FIELD: {}".format(field_name),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
    if config.token_fetcher is None:
        err_lines = ["OidcProviderConfig.token_fetcher must not be None."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if config.key_resolver is None:
        err_lines = ["OidcProviderConfig.key_resolver must not be None."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if config.session_factory is None:
        err_lines = ["OidcProviderConfig.session_factory must not be None."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if config.scopes is None or len(config.scopes) == 0:
        err_lines = ["OidcProviderConfig.scopes must contain at least one scope."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    return
