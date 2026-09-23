"""
.. module:: clients.enrollment.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Enrollment service — issue, redeem, list, revoke tokens + clients.

.. moduleauthor:: Code Craft AI LLC

M1 scope:

* :func:`issue_enrollment_token` — admin call. Generates a secret via the
  registered ``enrollment_token_issuer``, persists the digest, publishes
  ``entity.client.token_issued``, and returns the secret exactly once.
* :func:`redeem_enrollment_token` — agent call. Loads the matching token
  row by consulting every registered issuer (secrets self-identify by
  their stored ``issuer_algorithm``), verifies the digest, runs the
  ``client_identity_verifier``, and materializes the client by calling
  :func:`clients.registry.service.register_client`. The client is then
  registered on the pod the token names, which makes it a dispatch
  candidate.
* :func:`list_enrollment_tokens` — admin listing with optional filters.
* :func:`revoke_enrollment_token` — admin token rescission.
* :func:`revoke_client` — flips ``clients_clients.status`` to ``REVOKED``
  and records a ``clients_client_revocations`` row.

The CSR / mTLS layer is M2; this module issues a bearer token the agent
presents on subsequent requests. The bearer token is the raw secret
re-hashed under the same issuer and persisted on the client row so M2
can rotate it or replace it with a cert without touching the service
API surface.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, List, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.clients.enrollment import ca_adapter
from ccai.pychestrate.webservice.clients.enrollment.factories.identity_verifier import (
    ClientIdentityVerifierProtocol,
    EnrollmentPayload,
    TokenScope,
    VerificationReport,
)
from ccai.pychestrate.webservice.clients.enrollment.factories.token_issuer import (
    EnrollmentTokenIssuerProtocol,
    IssuedSecret,
)
from ccai.pychestrate.webservice.clients.enums import (
    ClientStatus,
    RevocationReason,
    TokenStatus,
)
from ccai.pychestrate.webservice.clients.events import ClientEventTopics
from ccai.pychestrate.webservice.clients.exceptions import (
    CertificateAuthorityUnavailableError,
    ClientNotFoundError,
    CsrScopeMismatchError,
    CsrValidationError,
    EnrollmentRejectedError,
    EnrollmentTokenInvalidError,
    EnrollmentTokenNotFoundError,
)
from ccai.pychestrate.webservice.clients.models import (
    Client,
    ClientCert,
    ClientRevocation,
    EnrollmentToken,
)
from ccai.pychestrate.webservice.clients.registry.service import (
    register_client,
)
from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
    resolve_factory_implementation,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.pods.static_service import bind_enrolled_client


DEFAULT_TOKEN_ENTROPY_BITS: int = 128
MAX_TOKEN_TTL_SECONDS: int = 86400
TOKEN_ISSUER_PROTOCOL: str = "enrollment_token_issuer"
IDENTITY_VERIFIER_PROTOCOL: str = "client_identity_verifier"


@dataclass(frozen=True)
class IssuedEnrollmentToken:
    """
        Returned to the admin after a successful :func:`issue_enrollment_token`.

        :param token_id: UUID of the persisted token row.
        :param secret: Secret string returned exactly once.
        :param project_id: Scope the token commits to.
        :param pod_name: Pod the token commits to.
        :param expires_at_iso: ISO-8601 expiry timestamp.
        :param algorithm_name: Issuer algorithm used.
    """
    token_id: str
    secret: str
    project_id: str
    pod_name: str
    expires_at_iso: str
    algorithm_name: str


@dataclass(frozen=True)
class TokenView:
    """
        Read-model returned by :func:`list_enrollment_tokens`. Never
        contains the secret.

        :param token_id: UUID of the token row.
        :param project_id: Scope the token commits to.
        :param pod_name: Pod the token commits to.
        :param status: :class:`TokenStatus` enum value.
        :param issued_at_iso: ISO-8601 issue timestamp.
        :param expires_at_iso: ISO-8601 expiry timestamp.
        :param one_shot: Whether the token is one-shot.
        :param algorithm_name: Issuer algorithm string.
        :param redeemed_at_iso: ISO-8601 redemption timestamp (nullable).
        :param redeemed_by_client_id: Redeeming client UUID (nullable).
    """
    token_id: str
    project_id: str
    pod_name: str
    status: TokenStatus
    issued_at_iso: str
    expires_at_iso: str
    one_shot: bool
    algorithm_name: str
    redeemed_at_iso: Optional[str]
    redeemed_by_client_id: Optional[str]


@dataclass(frozen=True)
class RedemptionResult:
    """
        Returned to the agent after a successful
        :func:`redeem_enrollment_token`.

        In M1 only the bearer fields were populated. M2 adds
        ``cert_serial``, ``cert_pem``, and ``cert_chain_pem`` when the
        redemption request included a CSR. Clients that did not
        supply a CSR receive only bearer credentials as before.

        :param client_id: Server-assigned UUID of the new client row.
        :param project_id: Scope the token committed to.
        :param pod_name: Pod the token committed to.
        :param bearer_token: Secret the agent carries on subsequent
                             requests.
        :param bearer_algorithm: Algorithm that produced the bearer
                                 digest.
        :param cert_serial: Hex serial of the issued cert, or ``None``
                            when the redemption was bearer-only.
        :param cert_pem: PEM-encoded issued certificate, or ``None``.
        :param cert_chain_pem: PEM-encoded issuer chain, or ``None``.
    """
    client_id: str
    project_id: str
    pod_name: str
    bearer_token: str
    bearer_algorithm: str
    cert_serial: Optional[str] = None
    cert_pem: Optional[bytes] = None
    cert_chain_pem: Optional[bytes] = None


def _resolve_token_issuer_for_hashing() -> type:
    """
        Return the highest-priority registered token issuer.

        :returns: Issuer class.
        :raises: ConfigurationError when none is registered.
    """
    rtnval = resolve_factory_implementation(
        factory_protocol_name=TOKEN_ISSUER_PROTOCOL,
        predicate=None,
    )
    return rtnval


def _resolve_token_issuer_by_algorithm(*, algorithm_name: str) -> type:
    """
        Return the registered token issuer whose ``algorithm_name`` matches.

        :param algorithm_name: Algorithm stored on the token row.

        :returns: Issuer class.
        :raises: ConfigurationError when no match is found.
    """
    if algorithm_name is None or len(algorithm_name) == 0:
        rtnval = _resolve_token_issuer_for_hashing()
        return rtnval

    candidates = list_factory_implementations(factory_protocol_name=TOKEN_ISSUER_PROTOCOL)
    for impl in candidates:
        if impl.algorithm_name() == algorithm_name:
            return impl

    err_msg_lines = ["No registered enrollment_token_issuer matches the stored algorithm."]
    err_msg_lines.append("ALGORITHM: {}".format(algorithm_name))
    err_msg_lines.append("REGISTERED: ({})".format(len(candidates)))
    for impl in candidates:
        err_msg_lines.append("    {} (PRECEDENCE={})".format(
            impl.algorithm_name(),
            getattr(impl, "PRECEDENCE", 1000),
        ))
    err_msg = os.linesep.join(err_msg_lines)
    raise ConfigurationError(err_msg) from None


def _resolve_identity_verifier() -> type:
    """
        Return the highest-priority registered identity verifier.

        :returns: Verifier class.
        :raises: ConfigurationError when none is registered.
    """
    rtnval = resolve_factory_implementation(
        factory_protocol_name=IDENTITY_VERIFIER_PROTOCOL,
        predicate=None,
    )
    return rtnval


def issue_enrollment_token(
        *,
        db_session: DbSession,
        project_id: str,
        pod_name: str,
        ttl_seconds: int,
        one_shot: bool,
        issued_by: Optional[str],
        entropy_bits: int = DEFAULT_TOKEN_ENTROPY_BITS
    ) -> IssuedEnrollmentToken:
    """
        Create a new enrollment token row and return the secret (shown
        exactly once).

        :param db_session: Active SQLAlchemy session.
        :param project_id: Scope project UUID.
        :param pod_name: Pod scope.
        :param ttl_seconds: Lifetime in seconds; capped at
                           :data:`MAX_TOKEN_TTL_SECONDS`.
        :param one_shot: If True, the token is consumed on first redemption.
        :param issued_by: Acting admin UUID (nullable for system flows).
        :param entropy_bits: Minimum acceptable secret entropy.

        :returns: :class:`IssuedEnrollmentToken`.
        :raises: ConfigurationError when no issuer is registered.
    """
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be > 0")
    capped_ttl = min(ttl_seconds, MAX_TOKEN_TTL_SECONDS)

    issuer = _resolve_token_issuer_for_hashing()
    secret_bundle: IssuedSecret = issuer.generate(entropy_bits=entropy_bits)

    now = utc_now()
    expires_at = now + timedelta(seconds=capped_ttl)
    token = EnrollmentToken(
        token_id=new_uuid(),
        token_hash=secret_bundle.stored_hash,
        project_id=project_id,
        pod_name=pod_name,
        issued_by=issued_by,
        issued_at=now,
        expires_at=expires_at,
        one_shot=one_shot,
        status=TokenStatus.PENDING,
        redeemed_at=None,
        redeemed_by_client_id=None,
        issuer_algorithm=secret_bundle.algorithm_name,
    )
    db_session.add(token)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ClientEventTopics.TOKEN_ISSUED,
            payload={
                "token_id": str(token.token_id),
                "project_id": str(project_id),
                "pod_name": pod_name,
                "issued_by": issued_by,
                "issued_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "one_shot": bool(one_shot),
                "algorithm_name": secret_bundle.algorithm_name,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    rtnval = IssuedEnrollmentToken(
        token_id=str(token.token_id),
        secret=secret_bundle.secret,
        project_id=str(project_id),
        pod_name=pod_name,
        expires_at_iso=expires_at.isoformat(),
        algorithm_name=secret_bundle.algorithm_name,
    )
    return rtnval


def list_enrollment_tokens(
        *,
        db_session: DbSession,
        project_id: Optional[str] = None,
        status: Optional[TokenStatus] = None
    ) -> List[TokenView]:
    """
        Return tokens matching optional filters. Never returns secrets.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Optional project filter.
        :param status: Optional status filter.

        :returns: List of :class:`TokenView` ordered by issued_at.
    """
    query = db_session.query(EnrollmentToken)
    if project_id is not None:
        query = query.filter(EnrollmentToken.project_id == project_id)
    if status is not None:
        query = query.filter(EnrollmentToken.status == status)
    rows = query.order_by(EnrollmentToken.issued_at.asc()).all()

    rtnval: List[TokenView] = []
    for row in rows:
        rtnval.append(TokenView(
            token_id=str(row.token_id),
            project_id=str(row.project_id),
            pod_name=row.pod_name,
            status=row.status,
            issued_at_iso=row.issued_at.isoformat() if row.issued_at is not None else "",
            expires_at_iso=row.expires_at.isoformat() if row.expires_at is not None else "",
            one_shot=bool(row.one_shot),
            algorithm_name=row.issuer_algorithm,
            redeemed_at_iso=row.redeemed_at.isoformat() if row.redeemed_at is not None else None,
            redeemed_by_client_id=(
                str(row.redeemed_by_client_id) if row.redeemed_by_client_id is not None else None
            ),
        ))
    return rtnval


def revoke_enrollment_token(
        *,
        db_session: DbSession,
        token_id: str,
        actor_user_id: Optional[str]
    ) -> None:
    """
        Mark a pending or redeemed token as ``REVOKED``. No-op when the
        token is already in ``REVOKED``.

        :param db_session: Active SQLAlchemy session.
        :param token_id: Target token UUID.
        :param actor_user_id: Acting admin UUID (nullable).

        :returns: None.
        :raises: EnrollmentTokenNotFoundError
    """
    token = (
        db_session.query(EnrollmentToken)
        .filter(EnrollmentToken.token_id == token_id)
        .first()
    )
    if token is None:
        err_msg_lines = ["Cannot revoke token — token_id not found."]
        err_msg_lines.append("TOKEN_ID: {}".format(token_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise EnrollmentTokenNotFoundError(err_msg) from None

    if token.status == TokenStatus.REVOKED:
        return

    token.status = TokenStatus.REVOKED
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ClientEventTopics.TOKEN_REVOKED,
            payload={
                "token_id": str(token.token_id),
                "project_id": str(token.project_id),
                "pod_name": token.pod_name,
                "actor_user_id": actor_user_id,
                "revoked_at": utc_now().isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    return


def redeem_enrollment_token(
        *,
        db_session: DbSession,
        secret: str,
        payload: EnrollmentPayload
    ) -> RedemptionResult:
    """
        Redeem an enrollment secret. Looks up every ``PENDING`` token row
        whose issuer algorithm still verifies the supplied secret,
        rejects if the candidate fails the identity verifier, and
        materializes the client by calling
        :func:`clients.registry.service.register_client`. The client is
        registered on the pod the token names
        (:func:`pods.static_service.bind_enrolled_client`), which makes
        it eligible for dispatch.

        :param db_session: Active SQLAlchemy session.
        :param secret: Secret returned at issue time.
        :param payload: Normalized enrollment payload.

        :returns: :class:`RedemptionResult` the agent carries on
                  subsequent requests.
        :raises: EnrollmentTokenNotFoundError, EnrollmentTokenInvalidError,
                 EnrollmentRejectedError, ClientAlreadyExistsError
    """
    if secret is None or len(secret) == 0:
        err_msg_lines = ["Cannot redeem enrollment token — empty secret."]
        err_msg = os.linesep.join(err_msg_lines)
        raise EnrollmentTokenNotFoundError(err_msg) from None

    now = utc_now()

    # Expire stale PENDING tokens eagerly so every downstream path works on
    # a fresh candidate list.
    stale = (
        db_session.query(EnrollmentToken)
        .filter(EnrollmentToken.status == TokenStatus.PENDING)
        .filter(EnrollmentToken.expires_at <= now)
        .all()
    )
    for row in stale:
        row.status = TokenStatus.EXPIRED
    if len(stale) > 0:
        db_session.flush()

    # Scan every row so "secret matches but token is non-pending" produces
    # a distinct error from "secret matches no row at all."
    all_rows = db_session.query(EnrollmentToken).all()

    matched_row: Optional[EnrollmentToken] = None
    for row in all_rows:
        issuer = _resolve_token_issuer_by_algorithm(algorithm_name=row.issuer_algorithm)
        if issuer.verify(secret=secret, stored_hash=bytes(row.token_hash)) is True:
            matched_row = row
            break

    if matched_row is None:
        err_msg_lines = ["Enrollment secret did not match any enrollment token."]
        err_msg = os.linesep.join(err_msg_lines)
        raise EnrollmentTokenNotFoundError(err_msg) from None

    if matched_row.status != TokenStatus.PENDING:
        err_msg_lines = ["Enrollment token cannot be redeemed in its current state."]
        err_msg_lines.append("TOKEN_ID: {}".format(matched_row.token_id))
        err_msg_lines.append("STATUS: {}".format(matched_row.status.value))
        err_msg = os.linesep.join(err_msg_lines)
        raise EnrollmentTokenInvalidError(err_msg) from None

    verifier = _resolve_identity_verifier()
    scope = TokenScope(project_id=str(matched_row.project_id), pod_name=matched_row.pod_name)
    report: VerificationReport = verifier.verify(token_scope=scope, payload=payload)
    if report.accepted is False:
        matched_token_id = str(matched_row.token_id)
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=ClientEventTopics.ENROLL_REJECTED,
                payload={
                    "token_id": matched_token_id,
                    "project_id": str(matched_row.project_id),
                    "pod_name": matched_row.pod_name,
                    "reason": report.reason,
                    "at": now.isoformat(),
                },
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()

        err_msg_lines = ["Enrollment rejected by identity verifier."]
        err_msg_lines.append("TOKEN_ID: {}".format(matched_token_id))
        err_msg_lines.append("REASON: {}".format(report.reason))
        err_msg = os.linesep.join(err_msg_lines)
        raise EnrollmentRejectedError(err_msg) from None

    # The client id is minted up front and the CSR is signed BEFORE
    # any row is written. The certificate carries the client id as
    # its identity (see ca_adapter), so the id must exist first; and
    # signing is the step most likely to refuse the request (no CA
    # installed, CSR scope mismatch). Registering the client first
    # used to commit a client row and then fail here, leaving a
    # phantom client that blocked the pod name with a 409 on every
    # retry.
    client_id = new_uuid()
    signed_cert: Optional[ca_adapter.SignedCertificate] = None
    if payload.csr_pem is not None and len(payload.csr_pem) > 0:
        signed_cert = ca_adapter.sign_csr(
            csr_pem=payload.csr_pem,
            expected_subject_cn=matched_row.pod_name,
            issued_subject_cn=client_id,
        )

    # Generate a fresh bearer token the agent carries on future requests.
    issuer = _resolve_token_issuer_for_hashing()
    bearer_bundle: IssuedSecret = issuer.generate(entropy_bits=DEFAULT_TOKEN_ENTROPY_BITS)

    # The client row, its certificate row and the redeemed token are
    # written in one transaction.
    try:
        client = register_client(
            db_session=db_session,
            project_id=str(matched_row.project_id),
            pod_name=matched_row.pod_name,
            bearer_token_hash=bearer_bundle.stored_hash,
            agent_version=payload.agent_version,
            transport_name=payload.transport_name,
            client_id=client_id,
            commit=False,
        )

        if signed_cert is not None:
            cert_row = ClientCert(
                cert_serial=signed_cert.cert_serial,
                client_id=client.client_id,
                not_before=signed_cert.not_before,
                not_after=signed_cert.not_after,
                issuer_subject=signed_cert.issuer_subject,
                subject_cn=signed_cert.subject_cn,
                pem_public=signed_cert.pem_public.decode("utf-8"),
                issued_at=now,
            )
            db_session.add(cert_row)

        if matched_row.one_shot is True:
            matched_row.status = TokenStatus.REDEEMED
        matched_row.redeemed_at = now
        matched_row.redeemed_by_client_id = client.client_id
        db_session.flush()

        # The token names the pod this client serves. Registering the
        # client on that pod is what makes it a dispatch candidate;
        # nothing else in the product creates the registration.
        registration = bind_enrolled_client(
            db_session=db_session,
            project_id=str(matched_row.project_id),
            pod_name=matched_row.pod_name,
            client_id=str(client.client_id),
        )

        enrolled_payload = {
            "client_id": str(client.client_id),
            "token_id": str(matched_row.token_id),
            "project_id": str(matched_row.project_id),
            "pod_name": matched_row.pod_name,
            "agent_version": payload.agent_version,
            "transport_name": payload.transport_name,
            "enrolled_at": now.isoformat(),
            "pod_id": str(registration.pod_id),
            "registration_id": str(registration.registration_id),
        }
        if signed_cert is not None:
            enrolled_payload["cert_serial"] = signed_cert.cert_serial
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=ClientEventTopics.ENROLLED,
                payload=enrolled_payload,
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
    except BaseException:
        db_session.rollback()
        raise

    cert_serial_out: Optional[str] = None
    cert_pem_out: Optional[bytes] = None
    cert_chain_out: Optional[bytes] = None
    if signed_cert is not None:
        cert_serial_out = signed_cert.cert_serial
        cert_pem_out = signed_cert.pem_public
        cert_chain_out = signed_cert.chain_pem

    rtnval = RedemptionResult(
        client_id=str(client.client_id),
        project_id=str(matched_row.project_id),
        pod_name=matched_row.pod_name,
        bearer_token=bearer_bundle.secret,
        bearer_algorithm=bearer_bundle.algorithm_name,
        cert_serial=cert_serial_out,
        cert_pem=cert_pem_out,
        cert_chain_pem=cert_chain_out,
    )
    return rtnval


def revoke_client(
        *,
        db_session: DbSession,
        client_id: str,
        reason: RevocationReason,
        revoked_by: Optional[str],
        note: str = "",
        cert_serial: Optional[str] = None
    ) -> None:
    """
        Flip a client to ``REVOKED`` and record a
        ``clients_client_revocations`` row. When ``cert_serial`` is
        supplied it is persisted on the revocation row so
        :func:`is_cert_revoked` can do a constant-time lookup.
        When ``cert_serial`` is ``None`` and the client has an active
        :class:`ClientCert` row, the most recently issued serial is
        used so M1 flows keep working without the caller having to
        pass a serial explicitly.

        :param db_session: Active SQLAlchemy session.
        :param client_id: Target client UUID.
        :param reason: :class:`RevocationReason` enum value.
        :param revoked_by: Acting admin UUID (nullable).
        :param note: Free-form note persisted on the revocation row.
        :param cert_serial: Optional specific cert serial being
                            revoked. Defaults to the client's most
                            recently-issued cert serial when
                            available.

        :returns: None.
        :raises: ClientNotFoundError
    """
    client = db_session.query(Client).filter(Client.client_id == client_id).first()
    if client is None:
        err_msg_lines = ["Cannot revoke client — client_id not found."]
        err_msg_lines.append("CLIENT_ID: {}".format(client_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ClientNotFoundError(err_msg) from None

    resolved_serial = cert_serial
    if resolved_serial is None:
        latest_cert = (
            db_session.query(ClientCert)
            .filter(ClientCert.client_id == client.client_id)
            .order_by(ClientCert.issued_at.desc())
            .first()
        )
        if latest_cert is not None:
            resolved_serial = latest_cert.cert_serial

    now = utc_now()
    revocation = ClientRevocation(
        revocation_id=new_uuid(),
        client_id=client.client_id,
        cert_serial=resolved_serial,
        reason=reason,
        revoked_by=revoked_by,
        revoked_at=now,
        note=note,
    )
    db_session.add(revocation)

    client.status = ClientStatus.REVOKED
    client.revision_token = new_uuid()
    db_session.flush()

    revoked_payload = {
        "client_id": str(client.client_id),
        "project_id": str(client.project_id),
        "pod_name": client.pod_name,
        "reason": reason.value,
        "revoked_by": revoked_by,
        "revoked_at": now.isoformat(),
        "note": note,
    }
    if resolved_serial is not None:
        revoked_payload["cert_serial"] = resolved_serial
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ClientEventTopics.REVOKED,
            payload=revoked_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    return


def is_cert_revoked(
        *,
        db_session: DbSession,
        cert_serial: str
    ) -> bool:
    """
        Return whether the supplied cert serial appears in
        ``clients_client_revocations``. Exposed as a simple boolean
        query so ``3-client-agent-protocol`` can gate inbound
        authenticated requests on a single lookup.

        :param db_session: Active SQLAlchemy session.
        :param cert_serial: Hex serial returned at enrollment time.

        :returns: True when a revocation row exists for ``cert_serial``.
    """
    if cert_serial is None or len(cert_serial) == 0:
        return False
    match = (
        db_session.query(ClientRevocation)
        .filter(ClientRevocation.cert_serial == cert_serial)
        .first()
    )
    rtnval = match is not None
    return rtnval
