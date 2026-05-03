"""
.. module:: security.auth.oidc.flow
    :synopsis: OIDC begin-login orchestration.

The ``begin_oidc_login`` entry point composes the PKCE pair
and the state / nonce tokens, persists the
``auth_oidc_state`` row, and returns the authorization URL
the controller redirects the browser to.

The matching ``complete_oidc_callback`` lands in a follow-on
slice — it consumes the state row, validates the IdP's
``id_token``, and opens an ``auth_sessions`` row through
the existing session_service.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping, Optional, Tuple
from urllib import parse as urlparse

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.security.auth.oidc.pkce import (
    PkcePair,
    generate_pkce_pair,
)
from automojo.pychestrate.webservice.security.auth.oidc.state import (
    DEFAULT_STATE_TTL,
    generate_nonce,
    generate_state_token,
    insert_state,
)


@dataclass(frozen=True)
class BeginLoginRedirect:
    """
        The output the controller redirects the browser to.

        :param authorization_url: Fully-formed authorization
                                  endpoint URL with every
                                  query parameter folded in.
        :param state: State token the IdP echoes back; the
                      callback path passes this to
                      ``consume_state`` to retrieve the
                      original PKCE verifier + nonce.
        :param nonce: Nonce the callback path uses to
                      validate the returned ``id_token``.
        :param pkce: PkcePair captured for tests and audit;
                     production controllers only need the
                     state value.
    """
    authorization_url: str
    state: str
    nonce: str
    pkce: PkcePair


def begin_oidc_login(
        *,
        db_session: DbSession,
        provider_name: str,
        authorization_endpoint: str,
        client_id: str,
        redirect_uri: str,
        scopes: Tuple[str, ...] = ("openid", "email", "profile"),
        redirect_target: str = "",
        ttl: Optional[timedelta] = None,
        extra_params: Optional[Mapping[str, str]] = None
    ) -> BeginLoginRedirect:
    """
        Generate PKCE + state + nonce, persist the
        ``auth_oidc_state`` row, and assemble the
        authorization URL.

        :param db_session: Active SQLAlchemy session.
        :param provider_name: Name of the registered OIDC
                              provider (e.g.
                              ``"google-workspace"``).
        :param authorization_endpoint: IdP's authorization
                                       endpoint URL (from
                                       discovery).
        :param client_id: OIDC client id.
        :param redirect_uri: Callback URL the IdP redirects
                             back to.
        :param scopes: Tuple of scope strings; defaults to
                       ``openid email profile``.
        :param redirect_target: Optional in-app target the
                                callback path will
                                redirect the user to after
                                a successful login.
        :param ttl: Optional state-row TTL override.
        :param extra_params: Optional caller-supplied query
                             parameters to fold into the
                             authorization URL.

        :returns: :class:`BeginLoginRedirect`.
        :raises: ValueError on empty provider_name /
                 authorization_endpoint / client_id /
                 redirect_uri.
    """
    if provider_name is None or len(provider_name) == 0:
        err_lines = [
            "begin_oidc_login requires a non-empty provider_name.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if authorization_endpoint is None or len(authorization_endpoint) == 0:
        err_lines = [
            "begin_oidc_login requires a non-empty authorization_endpoint.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if client_id is None or len(client_id) == 0:
        err_lines = ["begin_oidc_login requires a non-empty client_id."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if redirect_uri is None or len(redirect_uri) == 0:
        err_lines = ["begin_oidc_login requires a non-empty redirect_uri."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if scopes is None or len(scopes) == 0:
        err_lines = ["begin_oidc_login requires at least one scope."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    pkce = generate_pkce_pair()
    state = generate_state_token()
    nonce = generate_nonce()

    insert_state(
        db_session=db_session,
        state=state,
        nonce=nonce,
        pkce_verifier=pkce.verifier.encode("ascii"),
        provider_name=provider_name,
        redirect_target=redirect_target or "",
        ttl=ttl if ttl is not None else DEFAULT_STATE_TTL,
    )

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "nonce": nonce,
        "code_challenge": pkce.challenge,
        "code_challenge_method": pkce.method,
    }
    if extra_params is not None:
        for key, value in extra_params.items():
            if key in params:
                continue
            params[key] = value

    authorization_url = _build_authorization_url(
        endpoint=authorization_endpoint, params=params,
    )
    rtnval = BeginLoginRedirect(
        authorization_url=authorization_url,
        state=state,
        nonce=nonce,
        pkce=pkce,
    )
    return rtnval


def _build_authorization_url(
        *,
        endpoint: str,
        params: Mapping[str, str]
    ) -> str:
    """
        Append ``params`` to ``endpoint`` as a query string,
        preserving any existing query already on the
        endpoint URL (some IdPs include implementation
        params).
    """
    parsed = urlparse.urlparse(endpoint)
    existing = urlparse.parse_qsl(parsed.query, keep_blank_values=True)
    merged = list(existing)
    for key, value in params.items():
        merged.append((key, value))
    new_query = urlparse.urlencode(merged)
    rebuilt = parsed._replace(query=new_query)
    rtnval = urlparse.urlunparse(rebuilt)
    return rtnval
