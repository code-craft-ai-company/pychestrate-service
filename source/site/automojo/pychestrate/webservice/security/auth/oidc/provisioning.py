"""
.. module:: security.auth.oidc.provisioning
    :synopsis: Map id_token claims onto identity_users rows.

The OIDC callback path returns a validated id_token whose
claim set identifies an end user. ``resolve_user_from_claims``
turns those claims into a persisted ``IdentityUser`` row
through one of three strategies:

1. **Match by external id** — ``provisioning_source`` +
   ``external_id`` from the claims uniquely identify the
   row. Used by every IdP that advertises a stable
   ``sub`` (the OIDC core mandate).
2. **Match by primary email** — fallback for migrating
   users who pre-existed before the IdP was wired in. The
   matched row is upgraded with the IdP's external_id so
   subsequent logins use strategy #1.
3. **Provision** — when neither match hits, the helper
   creates a fresh ``IdentityUser`` through the existing
   ``user_service.create_user`` so the audit + bus
   emissions stay unchanged.

Per-claim mapping uses :class:`OidcClaimMapping` so
operators can configure which claim populates which user
field. The defaults follow the OpenID Connect Core 1.0
recommendation (sub / email / name / zoneinfo).

When a matched row is in :data:`UserStatus.DEACTIVATED`,
the helper raises :class:`UserDeactivatedError` so the
callback path surfaces a 403 and refuses to seat a
session — deactivated accounts must be reactivated
explicitly through ``user_service.reactivate_user`` before
they can log back in.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.identity.users import user_service
from automojo.pychestrate.webservice.identity.users.models import (
    IdentityUser,
    UserStatus,
)
from automojo.pychestrate.webservice.identity.users.repositories import (
    user_repository,
)


DEFAULT_TIMEZONE: str = "UTC"


class UserDeactivatedError(Exception):
    """
        Raised when an OIDC callback resolves to a row in
        :data:`UserStatus.DEACTIVATED`. The controller
        surfaces a 403 and refuses to seat a session.
    """


class ClaimsMissingError(Exception):
    """
        Raised when the configured claim mapping cannot
        find a required field on the id_token claim set.
    """


@dataclass(frozen=True)
class OidcClaimMapping:
    """
        Per-provider claim → user-field mapping.

        :param external_id_claim: Claim that carries the
                                  IdP-stable user id.
                                  Default ``"sub"``.
        :param email_claim: Claim carrying the primary
                            email. Default ``"email"``.
        :param login_name_claim: Optional claim carrying a
                                 desired login name. When
                                 ``None``, the local part
                                 of the email is used.
        :param display_name_claim: Claim carrying the
                                   display name. Default
                                   ``"name"``.
        :param timezone_claim: Claim carrying the user's
                               timezone. Default
                               ``"zoneinfo"``; falls back
                               to UTC.
    """
    external_id_claim: str = "sub"
    email_claim: str = "email"
    login_name_claim: Optional[str] = None
    display_name_claim: str = "name"
    timezone_claim: str = "zoneinfo"


@dataclass(frozen=True)
class ProvisioningResult:
    """
        Outcome of :func:`resolve_user_from_claims`.

        :param user: Resolved or newly-created
                     :class:`IdentityUser`.
        :param outcome: ``"matched_by_external_id"`` /
                        ``"matched_by_email_upgraded"`` /
                        ``"provisioned"``.
        :param external_id: The IdP-stable id from the
                            claims.
    """
    user: IdentityUser
    outcome: str
    external_id: str


def resolve_user_from_claims(
        *,
        db_session: DbSession,
        provider_name: str,
        claims: Mapping[str, Any],
        mapping: Optional[OidcClaimMapping] = None,
        actor_user_id: Optional[str] = None
    ) -> ProvisioningResult:
    """
        Map an id_token's claims onto a persisted
        :class:`IdentityUser` row using the three-strategy
        match-first / provision-second contract.

        :raises: ClaimsMissingError when the required
                 external_id_claim or email_claim is
                 missing or empty;
                 UserDeactivatedError when the matched
                 row's status is DEACTIVATED.
    """
    if claims is None:
        err_lines = ["resolve_user_from_claims requires non-None claims."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if provider_name is None or len(provider_name) == 0:
        err_lines = [
            "resolve_user_from_claims requires non-empty provider_name.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    materialized_mapping = (
        mapping if mapping is not None else OidcClaimMapping()
    )
    external_id = _extract_required_claim(
        claims=claims, claim=materialized_mapping.external_id_claim,
    )
    email = _extract_required_claim(
        claims=claims, claim=materialized_mapping.email_claim,
    )
    normalized_email = email.strip().lower()

    # Strategy 1 — match by (provisioning_source, external_id).
    matched_by_external = _find_by_external_id(
        db_session=db_session,
        provisioning_source=provider_name,
        external_id=external_id,
    )
    if matched_by_external is not None:
        _require_active(user=matched_by_external)
        rtnval = ProvisioningResult(
            user=matched_by_external,
            outcome="matched_by_external_id",
            external_id=external_id,
        )
        return rtnval

    # Strategy 2 — fallback: match by primary email and
    # upgrade the row with the IdP's external_id.
    matched_by_email = user_repository.get_by_email(
        db_session=db_session, primary_email=normalized_email,
    )
    if matched_by_email is not None:
        _require_active(user=matched_by_email)
        matched_by_email.provisioning_source = provider_name
        matched_by_email.external_id = external_id
        db_session.flush()
        db_session.commit()
        rtnval = ProvisioningResult(
            user=matched_by_email,
            outcome="matched_by_email_upgraded",
            external_id=external_id,
        )
        return rtnval

    # Strategy 3 — provision. Routes through user_service so
    # the audit + bus emissions stay unchanged.
    display_name = _extract_optional_claim(
        claims=claims, claim=materialized_mapping.display_name_claim,
    ) or normalized_email
    timezone = _extract_optional_claim(
        claims=claims, claim=materialized_mapping.timezone_claim,
    ) or DEFAULT_TIMEZONE
    login_name = _resolve_login_name(
        claims=claims,
        mapping=materialized_mapping,
        normalized_email=normalized_email,
    )
    provisioned = user_service.create_user(
        db_session=db_session,
        login_name=login_name,
        primary_email=normalized_email,
        display_name=display_name,
        timezone=timezone,
        provisioning_source=provider_name,
        external_id=external_id,
        actor_user_id=actor_user_id,
    )
    rtnval = ProvisioningResult(
        user=provisioned,
        outcome="provisioned",
        external_id=external_id,
    )
    return rtnval


def _find_by_external_id(
        *,
        db_session: DbSession,
        provisioning_source: str,
        external_id: str
    ) -> Optional[IdentityUser]:
    rtnval = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.provisioning_source == provisioning_source)
        .filter(IdentityUser.external_id == external_id)
        .first()
    )
    return rtnval


def _require_active(*, user: IdentityUser) -> None:
    if user.status == UserStatus.DEACTIVATED:
        err_lines = ["Resolved user is deactivated."]
        err_lines.append("USER_ID: {}".format(user.user_id))
        err_lines.append("LOGIN_NAME: {}".format(user.login_name))
        err_msg = os.linesep.join(err_lines)
        raise UserDeactivatedError(err_msg) from None
    return


def _extract_required_claim(
        *,
        claims: Mapping[str, Any],
        claim: str
    ) -> str:
    value = claims.get(claim)
    if value is None or not isinstance(value, str) or len(value.strip()) == 0:
        err_lines = ["OIDC claims missing a required field."]
        err_lines.append("CLAIM: {}".format(claim))
        err_lines.append("CLAIM_KEYS: {}".format(sorted(claims.keys())))
        err_msg = os.linesep.join(err_lines)
        raise ClaimsMissingError(err_msg) from None
    rtnval = value.strip()
    return rtnval


def _extract_optional_claim(
        *,
        claims: Mapping[str, Any],
        claim: str
    ) -> Optional[str]:
    value = claims.get(claim)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if len(stripped) == 0:
        return None
    return stripped


def _resolve_login_name(
        *,
        claims: Mapping[str, Any],
        mapping: OidcClaimMapping,
        normalized_email: str
    ) -> str:
    if mapping.login_name_claim is not None:
        candidate = _extract_optional_claim(
            claims=claims, claim=mapping.login_name_claim,
        )
        if candidate is not None:
            rtnval = candidate.lower()
            return rtnval
    local, _, _ = normalized_email.partition("@")
    if len(local) == 0:
        rtnval = normalized_email
        return rtnval
    return local
