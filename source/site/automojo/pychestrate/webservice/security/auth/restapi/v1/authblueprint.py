"""
.. module:: security.auth.restapi.v1.auth_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/auth on automojo-webworks.

.. moduleauthor:: Automation Mojo LLC

This module is the **worked example** for the P24a Flask → automojo-webworks
migration. It exposes the v1 ``/api/v1/auth`` surface (providers picker,
provider enable/disable, logout, MFA challenge/verify) as webworks
:class:`~automojo.webworks.endpoints.restblueprint.RestBlueprint` endpoints.

Migration pattern (apply to the remaining REST controllers):

* ``flask_restx.Namespace`` + ``Resource``  →  :class:`RestBlueprint`
  subclass with a ``base_path`` class attribute. Path-param syntax shifts
  from Flask ``<string:foo>`` to webworks ``{foo}``.
* ``@auth_ns.route("/x") class Foo(Resource): def post(self):``  →
  ``@RestBlueprint.attach_at(path="/api/v1/auth/x", methods=["POST"])``
  on a class method whose signature is ``def foo(request)`` — handlers
  are plain functions on the class (**no** ``self`` parameter; webworks
  calls them directly with the :class:`Request`). The decorator is
  ``RestBlueprint.attach_at`` (not ``AuthBlueprint.attach_at``) because
  the subclass does not exist yet inside its own class body, so the
  ``base_path`` cannot be applied automatically — the full path is
  written explicitly. ``base_path`` is still used by
  :meth:`RestBlueprint.register` to filter descriptors when pushing
  them to the Router.
* ``flask.g.db_session``  →  ``request.db_session`` populated by
  :class:`automojo.pychestrate.webservice.dbsessionmiddleware.DbSessionMiddleware`.
* ``flask.request.get_json()``  →  ``request.json()`` (sync; webworks
  pre-buffers the body).
* Path params: ``flask.request.view_args["kind"]`` →
  ``request.path_params["kind"]``.
* ``auth_ns.abort(404, "msg")``  →  ``raise HTTPException(404, "msg")``.
  The webworks dispatcher converts it to the JSON
  ``{"detail": ..., "status_code": ...}`` body shape.
* ``return (body, 200)``  →
  ``return JSONResponse(content=body, status_code=200)``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, Optional

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse
from automojo.webworks.security.accesspolicy import AccessPolicy


_ADMIN_POLICY = AccessPolicy(roles=("system-admin",))

from automojo.pychestrate.webservice.security.auth import (
    local_flow,
    mfa_service,
    provider_directory,
    session_service,
)
from automojo.pychestrate.webservice.security.auth.cookiepolicy import (
    load_cookie_policy_from_env,
    render_set_cookie_header,
)
from automojo.pychestrate.webservice.security.auth.cookies import (
    SESSION_COOKIE_NAME,
    build_session_cookie,
)
from automojo.pychestrate.webservice.security.auth.exceptions import (
    AuthenticationError,
    MfaChallengeExpiredError,
    MfaChallengeRejectedError,
    MfaChallengeUnknownError,
    MfaEnrollmentNotFoundError,
    MfaEnrollmentNotVerifiedError,
    MfaMethodUnknownError,
    MfaRequiredError,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
)


AUTH_BASE_PATH = "/api/v1/auth"


_VALID_PROVIDER_KINDS = {kind.value for kind in AuthProviderKind}


def _first_verified_enrollment(*, db_session, user_id: str):
    """
        Return the first verified MFA enrollment for ``user_id``, or
        ``None`` when the user has none.

        Used by the login endpoint to detect "MFA required" without
        committing to a particular method ordering. Today the
        AuthMfaEnrollment query is small (per-user, max a handful of
        rows) so a linear scan in Python is fine.
    """
    enrollments = mfa_service.list_enrollments_for_user(
        db_session=db_session, user_id=user_id,
    )
    for enrollment in enrollments:
        if enrollment.verified is True:
            return enrollment
    return None


def _require_db_session(*, request: Request) -> Any:
    """
        Pull the request-scoped ``db_session`` set by
        :class:`DbSessionMiddleware`.

        :param request: The incoming HTTP request.

        :returns: The SQLAlchemy session attached by the middleware.

        :raises HTTPException: 503 when the middleware did not run.
    """
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        err_lines = [
            "Request-scoped db_session not configured.",
            "DbSessionMiddleware must be installed in the pipeline.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise HTTPException(status_code=503, detail=err_msg)
    return db_session


def _resolve_provider_kind(*, kind_segment: str) -> AuthProviderKind:
    """
        Coerce a URL segment to an :class:`AuthProviderKind` or 404.

        :param kind_segment: Raw path-param value (e.g. ``"oidc"``).

        :returns: The resolved :class:`AuthProviderKind`.

        :raises HTTPException: 404 when ``kind_segment`` is unknown.
    """
    if kind_segment is None:
        raise HTTPException(status_code=404, detail="kind_unknown")
    upper = kind_segment.upper()
    if upper not in _VALID_PROVIDER_KINDS:
        raise HTTPException(status_code=404, detail="kind_unknown")
    rtnval = AuthProviderKind(upper)
    return rtnval


def _read_json_body(*, request: Request) -> Dict[str, Any]:
    """
        Parse the request body as a JSON object.

        :param request: The incoming HTTP request.

        :returns: The decoded JSON object as a dict.

        :raises HTTPException: 400 when the body is missing or not an
                               object.
    """
    raw_body = request.body
    if raw_body is None:
        raise HTTPException(status_code=400, detail="request body required")
    if len(raw_body) == 0:
        raise HTTPException(status_code=400, detail="request body required")
    try:
        decoded = request.json()
    except Exception as exc:
        err_msg = "request body must be valid JSON"
        raise HTTPException(status_code=400, detail=err_msg) from exc
    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object",
        )
    rtnval = decoded
    return rtnval


class AuthBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/auth`` endpoints.
    """

    base_path = AUTH_BASE_PATH
    tags = ["auth", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/auth/login",
        methods=["POST"],
        doc=Doc(
            summary="Open a session via local credentials",
            description=(
                "Verify a (login_name, password) pair against the local "
                "credential store, open an auth session, and return 200 "
                "with a Set-Cookie header carrying the session id. "
                "Cookie attributes are sourced from the "
                "PYCHESTRATE_COOKIE_* environment variables — see "
                "usersguide/configuration.md for the full reference."
            ),
        ),
    )
    def login(request: Request) -> JSONResponse:
        """
            Verify local credentials and open a session.

            :param request: The incoming HTTP request. Body must be a
                            JSON object with string ``login_name`` and
                            ``password`` keys; ``mfa_code`` is
                            optional.

            :returns: 200 with ``{"session_id": ..., "user_id": ...,
                      "expires_in_seconds": ...}`` plus a Set-Cookie
                      header. 401 on invalid credentials. 503 when
                      the request-scoped db_session is missing.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)

        login_name = str(payload.get("login_name", ""))
        password = str(payload.get("password", ""))
        mfa_code_raw = payload.get("mfa_code", None)
        if mfa_code_raw is None:
            mfa_code = None
        else:
            mfa_code = str(mfa_code_raw)
        challenge_id_raw = payload.get("challenge_id", None)
        if challenge_id_raw is None:
            challenge_id = None
        else:
            challenge_id = str(challenge_id_raw)

        # Best-effort source-IP for the backoff key. The webworks
        # Request does not yet expose a parsed remote_addr, so we
        # read the X-Forwarded-For header when present and fall back
        # to a placeholder.
        forwarded = request.get_header("X-Forwarded-For", default=None)
        if forwarded is None:
            source_ip = "unknown"
        else:
            source_ip = forwarded.split(",")[0].strip()

        try:
            outcome = local_flow.verify_local_credentials(
                login_name=login_name,
                password=password,
                mfa_code=mfa_code,
                source_ip=source_ip,
                db_session=db_session,
            )
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=401, detail=str(exc),
            ) from exc
        except MfaRequiredError as exc:
            raise HTTPException(
                status_code=401, detail=str(exc),
            ) from exc

        # Two-stage MFA: if the user has any verified enrollment, the
        # first /auth/login call returns mfa_required=true with a
        # freshly-issued challenge_id (no Set-Cookie). The caller then
        # POSTs /auth/login a second time including challenge_id +
        # mfa_code; on success the session opens.
        verified_enrollment = _first_verified_enrollment(
            db_session=db_session, user_id=outcome.user_id,
        )
        used_method_name: Optional[str] = None
        if verified_enrollment is not None:
            if challenge_id is None or mfa_code is None:
                challenge = mfa_service.initiate_challenge(
                    db_session=db_session,
                    user_id=outcome.user_id,
                    method_name=verified_enrollment.method_name,
                )
                body = {
                    "mfa_required": True,
                    "user_id": outcome.user_id,
                    "challenge_id": challenge.challenge_id,
                    "method_name": challenge.method_name,
                    "expires_at": challenge.expires_at.isoformat(),
                }
                rtnval = JSONResponse(content=body, status_code=200)
                return rtnval
            try:
                verification = mfa_service.verify_challenge(
                    db_session=db_session,
                    challenge_id=challenge_id,
                    response_fields={"code": mfa_code},
                )
            except MfaChallengeUnknownError as exc:
                raise HTTPException(
                    status_code=401, detail="challenge_unknown",
                ) from exc
            except MfaChallengeExpiredError as exc:
                raise HTTPException(
                    status_code=401, detail="challenge_expired",
                ) from exc
            except MfaChallengeRejectedError as exc:
                raise HTTPException(
                    status_code=401, detail="challenge_rejected",
                ) from exc
            if verification.accepted is False:
                raise HTTPException(
                    status_code=401, detail="challenge_rejected",
                )
            used_method_name = verified_enrollment.method_name

        cookie_policy = load_cookie_policy_from_env()
        seated = session_service.open_session(
            db_session=db_session,
            user_id=outcome.user_id,
            provider_kind=AuthProviderKind.LOCAL,
            provider_name="local",
            mfa_method_name=used_method_name,
            access_token_payload=None,
            refresh_token_payload=None,
            request_fingerprint=RequestFingerprint(
                ip_fingerprint=source_ip,
                user_agent_fingerprint=request.get_header(
                    "User-Agent", default="unknown",
                ),
            ),
            idle_timeout_seconds=cookie_policy.max_age_seconds,
            max_lifetime_seconds=cookie_policy.max_age_seconds,
        )
        session_id = str(seated.session_id)

        cookie_spec = build_session_cookie(
            session_id=session_id,
            max_age_seconds=cookie_policy.max_age_seconds,
            domain=cookie_policy.domain,
            same_site=cookie_policy.same_site,
            secure=cookie_policy.secure,
            path=cookie_policy.path,
        )
        set_cookie_value = render_set_cookie_header(spec=cookie_spec)

        body = {
            "session_id": session_id,
            "user_id": outcome.user_id,
            "expires_in_seconds": cookie_policy.max_age_seconds,
            "cookie_name": SESSION_COOKIE_NAME,
        }
        rtnval = JSONResponse(
            content=body,
            status_code=200,
            headers={"Set-Cookie": set_cookie_value},
        )
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/auth/providers",
        methods=["GET"],
        doc=Doc(
            summary="List enabled credential modes",
            description=(
                "Return the providers the login picker should render. "
                "When a request-scoped db_session is attached, kind-level "
                "feature flags (auth.oidc_enabled / auth.saml_enabled / "
                "auth.local_fallback_enabled) gate the result."
            ),
        ),
    )
    def list_providers(request: Request) -> JSONResponse:
        """
            Return the picker view of enabled credential modes.

            :param request: The incoming HTTP request.

            :returns: 200 with a ``{"providers": [...]}`` body.
        """
        db_session = getattr(request, "db_session", None)
        if db_session is not None:
            modes = provider_directory.list_enabled_credential_modes_with_flags(
                db_session=db_session,
            )
        else:
            modes = provider_directory.list_enabled_credential_modes()
        provider_entries = []
        for mode in modes:
            entry = {
                "kind": mode.kind.value,
                "provider_name": mode.provider_name,
                "display_label": mode.display_label,
                "login_path": mode.login_path,
                "enabled": mode.enabled,
            }
            provider_entries.append(entry)
        body = {"providers": provider_entries}
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/auth/providers/{kind_segment}/{provider_name}/enable",
        methods=["POST"],
        doc=Doc(
            summary="Enable a credential mode",
            description=(
                "Hot-flip the directory's enabled flag for the named "
                "(kind, provider_name) pair to True so the picker resumes "
                "advertising it."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def enable_provider(request: Request) -> JSONResponse:
        """
            Set ``enabled=True`` on the named credential mode.

            :param request: The incoming HTTP request. Path params
                            ``kind_segment`` and ``provider_name`` are
                            populated by the dispatcher.

            :returns: 200 with the updated mode view.
        """
        kind_segment = request.path_params.get("kind_segment", "")
        provider_name = request.path_params.get("provider_name", "")
        kind = _resolve_provider_kind(kind_segment=kind_segment)
        try:
            view = provider_directory.set_enabled(
                kind=kind, provider_name=provider_name, enabled=True,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="credential_mode_not_registered",
            ) from exc
        body = {
            "kind": view.kind.value,
            "provider_name": view.provider_name,
            "enabled": view.enabled,
        }
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/auth/providers/{kind_segment}/{provider_name}/disable",
        methods=["POST"],
        doc=Doc(
            summary="Disable a credential mode",
            description=(
                "Hot-flip the directory's enabled flag for the named "
                "(kind, provider_name) pair to False so the picker stops "
                "advertising it. The provider's controller routes remain "
                "wired."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def disable_provider(request: Request) -> JSONResponse:
        """
            Set ``enabled=False`` on the named credential mode.

            :param request: The incoming HTTP request. Path params
                            ``kind_segment`` and ``provider_name`` are
                            populated by the dispatcher.

            :returns: 200 with the updated mode view.
        """
        kind_segment = request.path_params.get("kind_segment", "")
        provider_name = request.path_params.get("provider_name", "")
        kind = _resolve_provider_kind(kind_segment=kind_segment)
        try:
            view = provider_directory.set_enabled(
                kind=kind, provider_name=provider_name, enabled=False,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="credential_mode_not_registered",
            ) from exc
        body = {
            "kind": view.kind.value,
            "provider_name": view.provider_name,
            "enabled": view.enabled,
        }
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/auth/logout",
        methods=["POST"],
        doc=Doc(
            summary="Close authenticated session",
            description=(
                "Close the supplied session id. The request-scoped "
                "db_session must be populated by DbSessionMiddleware."
            ),
        ),
    )
    def logout(request: Request) -> JSONResponse:
        """
            Close the supplied session.

            :param request: The incoming HTTP request. Body must be a
                            JSON object with a ``session_id`` string key.

            :returns: 200 with ``{"session_id": ..., "status": "closed"}``.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        session_id_raw = payload.get("session_id", "")
        session_id = str(session_id_raw) if session_id_raw is not None else ""

        session_service.close_session(
            db_session=db_session, session_id=session_id,
        )

        body = {"session_id": session_id, "status": "closed"}
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/auth/mfa/challenge",
        methods=["POST"],
        doc=Doc(
            summary="Issue an MFA challenge",
            description=(
                "Issue a fresh challenge for the (user, method) row and "
                "stash it in the active-challenge store so a follow-up "
                "/auth/mfa/verify can consume it."
            ),
        ),
    )
    def mfa_challenge(request: Request) -> JSONResponse:
        """
            Issue a fresh MFA challenge.

            :param request: The incoming HTTP request. Body must be a
                            JSON object with ``user_id`` and
                            ``method_name`` string keys.

            :returns: 201 with the challenge descriptor.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        user_id = str(payload.get("user_id", ""))
        method_name = str(payload.get("method_name", ""))

        if len(user_id) == 0:
            raise HTTPException(
                status_code=400, detail="user_id must be non-empty",
            )
        if len(method_name) == 0:
            raise HTTPException(
                status_code=400, detail="method_name must be non-empty",
            )

        try:
            challenge = mfa_service.initiate_challenge(
                db_session=db_session,
                user_id=user_id,
                method_name=method_name,
            )
        except MfaMethodUnknownError as exc:
            raise HTTPException(
                status_code=404, detail="method_unknown",
            ) from exc
        except MfaEnrollmentNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail="enrollment_not_found",
            ) from exc
        except MfaEnrollmentNotVerifiedError as exc:
            raise HTTPException(
                status_code=409, detail="enrollment_not_verified",
            ) from exc

        body = {
            "challenge_id": challenge.challenge_id,
            "method_name": challenge.method_name,
            "user_id": challenge.user_id,
            "issued_at": challenge.issued_at.isoformat(),
            "expires_at": challenge.expires_at.isoformat(),
            "payload": dict(challenge.payload),
        }
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/auth/mfa/verify",
        methods=["POST"],
        doc=Doc(
            summary="Verify an MFA challenge response",
            description=(
                "Consume the named challenge from the active-challenge "
                "store, verify the response against the underlying MFA "
                "method extension, and emit the matching challenge-"
                "verified or challenge-rejected event."
            ),
        ),
    )
    def mfa_verify(request: Request) -> JSONResponse:
        """
            Verify an MFA challenge response.

            :param request: The incoming HTTP request. Body must be a
                            JSON object with ``challenge_id`` (string)
                            and ``response`` (object) keys.

            :returns: 200 with ``{"challenge_id": ..., "accepted": ...,
                      "reason": ...}``.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        challenge_id = str(payload.get("challenge_id", ""))
        response_fields = payload.get("response", None)

        if len(challenge_id) == 0:
            raise HTTPException(
                status_code=400, detail="challenge_id must be non-empty",
            )
        if response_fields is None:
            raise HTTPException(
                status_code=400, detail="response must be an object",
            )
        if not isinstance(response_fields, dict):
            raise HTTPException(
                status_code=400, detail="response must be an object",
            )

        try:
            outcome = mfa_service.verify_challenge(
                db_session=db_session,
                challenge_id=challenge_id,
                response_fields=response_fields,
            )
        except MfaChallengeUnknownError as exc:
            raise HTTPException(
                status_code=404, detail="challenge_unknown",
            ) from exc
        except MfaChallengeExpiredError as exc:
            raise HTTPException(
                status_code=410, detail="challenge_expired",
            ) from exc
        except MfaChallengeRejectedError as exc:
            raise HTTPException(
                status_code=401, detail="challenge_rejected",
            ) from exc
        except MfaEnrollmentNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail="enrollment_not_found",
            ) from exc

        body = {
            "challenge_id": challenge_id,
            "accepted": outcome.accepted,
            "reason": outcome.reason,
        }
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
