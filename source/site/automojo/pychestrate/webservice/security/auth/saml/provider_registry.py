"""
.. module:: security.auth.saml.provider_registry
    :synopsis: Process-level registry of configured SAML providers.

Mirrors the OIDC :mod:`oidc.provider_registry` pattern: the
:class:`SamlAuthProvider` factory implementation is keyed
on ``provider_name`` (the URL segment in
``/auth/saml/{provider_name}/{login,acs}``) and consults
this registry to look up the per-IdP configuration.

Each registered provider declares its metadata URL
(consumed by :mod:`saml.metadata` for trust-set rotation),
its ACS URL, the SP entityID, the optional configured
``InResponseTo`` policy, and the pluggable signature
verifier and metadata fetcher seams. The registry itself
is a process-local dict guarded by a lock plus a
:func:`reset_for_testing` seam.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.security.auth.saml.assertion import (
    SamlSignatureVerifier,
)
from automojo.pychestrate.webservice.security.auth.saml.metadata import (
    SamlMetadataFetcher,
)


SessionFactory = Callable[[], DbSession]


@dataclass(frozen=True)
class SamlProviderConfig:
    """
        Per-provider SAML configuration consulted by the
        :class:`SamlAuthProvider` factory.

        :param provider_name: Stable name (matches the URL
                              segment in
                              ``/auth/saml/{provider_name}/...``).
        :param sp_entity_id: SP entityID — used for
                             ``Issuer`` on outgoing
                             AuthnRequests and as the
                             expected ``Audience`` on inbound
                             assertions.
        :param acs_url: SP ACS URL — used for
                        ``AssertionConsumerServiceURL`` on
                        AuthnRequests and as the expected
                        ``SubjectConfirmationData/@Recipient``
                        on assertions.
        :param metadata_url: IdP metadata document URL —
                             passed to
                             :func:`saml.metadata.refresh_metadata_document`.
        :param metadata_fetcher: Pluggable metadata-document
                                 fetcher.
        :param signature_verifier: Pluggable assertion
                                   signature verifier;
                                   ``None`` skips signature
                                   checks (test-only).
        :param session_factory: Callable returning a fresh
                                ``DbSession`` for the begin /
                                complete halves of the flow.
    """
    provider_name: str
    sp_entity_id: str
    acs_url: str
    metadata_url: str
    metadata_fetcher: SamlMetadataFetcher
    session_factory: SessionFactory
    signature_verifier: Optional[SamlSignatureVerifier] = None


_GUARD: threading.Lock = threading.Lock()
_REGISTRY: Dict[str, SamlProviderConfig] = {}


def register_saml_provider(*, config: SamlProviderConfig) -> None:
    """
        Register a :class:`SamlProviderConfig` so the
        :class:`SamlAuthProvider` factory can dispatch to
        it by name.

        :raises: ValueError on missing fields or duplicate
                 ``provider_name``.
    """
    if config is None:
        err_lines = ["register_saml_provider requires a config."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    _validate_config(config=config)
    with _GUARD:
        existing = _REGISTRY.get(config.provider_name)
        if existing is not None:
            err_lines = [
                "SAML provider already registered.",
                "PROVIDER_NAME: {}".format(config.provider_name),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        _REGISTRY[config.provider_name] = config
    return


def get_saml_provider_config(
        *, provider_name: str
    ) -> SamlProviderConfig:
    """
        Look up the :class:`SamlProviderConfig` registered
        under ``provider_name``.

        :raises: KeyError when no config is registered;
                 ValueError on empty input.
    """
    if provider_name is None or len(provider_name) == 0:
        err_lines = ["get_saml_provider_config requires a provider_name."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    with _GUARD:
        existing = _REGISTRY.get(provider_name)
    if existing is None:
        err_lines = [
            "No SAML provider registered for the given name.",
            "PROVIDER_NAME: {}".format(provider_name),
        ]
        err_msg = os.linesep.join(err_lines)
        raise KeyError(err_msg) from None
    rtnval = existing
    return rtnval


def list_saml_provider_names() -> List[str]:
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


def _validate_config(*, config: SamlProviderConfig) -> None:
    fields_to_check = [
        ("provider_name", config.provider_name),
        ("sp_entity_id", config.sp_entity_id),
        ("acs_url", config.acs_url),
        ("metadata_url", config.metadata_url),
    ]
    for field_name, field_value in fields_to_check:
        if field_value is None or len(field_value) == 0:
            err_lines = [
                "SamlProviderConfig has an empty required field.",
                "FIELD: {}".format(field_name),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
    if config.metadata_fetcher is None:
        err_lines = [
            "SamlProviderConfig.metadata_fetcher must not be None.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if config.session_factory is None:
        err_lines = [
            "SamlProviderConfig.session_factory must not be None.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    return
