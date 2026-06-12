"""
.. module:: security.auth.factories.local_provider
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference implementation for the ``LOCAL`` auth provider.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.security.auth.factories.auth_provider import (
    AuthProviderProtocol,
    CompletedFlow,
    InboundFlowPayload,
    RedirectDescriptor,
)
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind


class LocalCredentialAuthProvider(AuthProviderProtocol):
    """
        In-tree reference implementation of the LOCAL credential provider.

        The M1 skeleton wires the factory surface. The Argon2id verification
        path lives in :mod:`local_flow` and is invoked by
        :func:`complete_callback` once the flow lands in M1.
    """

    factory_protocol_name: str = "auth_provider"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def provider_kind(cls) -> AuthProviderKind:
        rtnval = AuthProviderKind.LOCAL
        return rtnval

    @classmethod
    def build_begin_login_redirect(
            cls,
            *,
            provider_name: str,
            redirect_target: str
        ) -> RedirectDescriptor:
        rtnval = RedirectDescriptor(
            target_url=redirect_target,
            state_token="",
        )
        return rtnval

    @classmethod
    def complete_callback(
            cls,
            *,
            provider_name: str,
            inbound: InboundFlowPayload
        ) -> CompletedFlow:
        from ccai.pychestrate.webservice.security.auth.local_flow import verify_local_credentials

        login_name = str(inbound.fields.get("login_name", ""))
        password = str(inbound.fields.get("password", ""))
        source_ip = str(inbound.fields.get("source_ip", ""))
        db_session = inbound.fields.get("db_session", None)

        completed = verify_local_credentials(
            login_name=login_name,
            password=password,
            mfa_code=None,
            source_ip=source_ip,
            db_session=db_session,
        )
        rtnval = CompletedFlow(
            user_id=completed.user_id,
            provider_kind=AuthProviderKind.LOCAL,
            provider_name=provider_name,
            access_token_payload=None,
            refresh_token_payload=None,
            mfa_method_name=None,
        )
        return rtnval
