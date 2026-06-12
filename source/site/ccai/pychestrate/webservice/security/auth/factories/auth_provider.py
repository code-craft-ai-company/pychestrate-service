"""
.. module:: security.auth.factories.auth_provider
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: FactoryProtocolBase for pluggable authentication providers.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ccai.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind


@dataclass(frozen=True)
class RedirectDescriptor:
    """
        Where to send the user next to begin an auth flow.

        :param target_url: Fully-qualified URL to redirect to.
        :param state_token: Opaque state/transition token held by the caller.
    """
    target_url: str
    state_token: str


@dataclass(frozen=True)
class InboundFlowPayload:
    """
        Normalized inbound payload from the provider's redirect or assertion.

        :param fields: Opaque mapping produced by the flow.
    """
    fields: Mapping[str, Any]


@dataclass(frozen=True)
class CompletedFlow:
    """
        The result of completing an auth flow.

        :param user_id: Resolved principal id from ``identity_users``.
        :param provider_kind: Kind of provider that opened the flow.
        :param provider_name: Named provider instance.
        :param access_token_payload: Optional sealed access-token bytes.
        :param refresh_token_payload: Optional sealed refresh-token bytes.
        :param mfa_method_name: MFA method used, if any.
    """
    user_id: str
    provider_kind: AuthProviderKind
    provider_name: str
    access_token_payload: Optional[bytes]
    refresh_token_payload: Optional[bytes]
    mfa_method_name: Optional[str]


class AuthProviderProtocol(FactoryProtocolBase):
    """
        Contract for an ``auth_provider`` implementation. Each provider
        implements the begin-redirect and complete-callback halves of a flow
        and declares which ``AuthProviderKind`` it represents.
    """

    factory_protocol_name: str = "auth_provider"
    protocol_schema_version: int = 1

    is_published: bool = True
    published_docs_url: str = "https://docs.pychestrate.io/plugin-api/auth_provider"
    published_reference: str = (
        "ccai.pychestrate.webservice.security.auth.factories.local_provider"
        ".LocalCredentialAuthProvider"
    )

    @classmethod
    def provider_kind(cls) -> AuthProviderKind:
        """
            Declare whether this provider is OIDC, SAML, or LOCAL.

            :returns: The :class:`AuthProviderKind`.
        """
        raise NotImplementedError("Subclasses must implement provider_kind")

    @classmethod
    def build_begin_login_redirect(
            cls,
            *,
            provider_name: str,
            redirect_target: str
        ) -> RedirectDescriptor:
        """
            Construct the initial redirect for the flow.

            :param provider_name: Named provider instance.
            :param redirect_target: Where to send the user after login completes.

            :returns: The populated :class:`RedirectDescriptor`.
        """
        raise NotImplementedError("Subclasses must implement build_begin_login_redirect")

    @classmethod
    def complete_callback(
            cls,
            *,
            provider_name: str,
            inbound: InboundFlowPayload
        ) -> CompletedFlow:
        """
            Consume the provider callback and return claims + token bundle.

            :param provider_name: Named provider instance.
            :param inbound: Normalized inbound payload.

            :returns: The populated :class:`CompletedFlow`.
        """
        raise NotImplementedError("Subclasses must implement complete_callback")
