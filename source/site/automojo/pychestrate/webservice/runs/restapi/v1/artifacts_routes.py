"""
.. module:: runs.restapi.v1.artifacts_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for the presigned result-upload surface.

.. moduleauthor:: Automation Mojo LLC

PR p19l closes the last server gap in the orchestration loop's
result path. The pod client agent (``pychestrate-client`` M3) can
build a result manifest but had no credentialed way to upload the
result tree to the shared results backend. This module mints
short-lived presigned PUT URLs server-side so object-store
credentials never leave the server.

Two operations are hosted here:

* ``POST /api/v1/runs/{run_id}/artifacts:presign`` (tag: results)

  The client posts the relative artifact paths from its
  result-tree walk; the handler verifies the calling mTLS
  certificate owns the run's current dispatch, then returns one
  presigned upload target per path.

* ``PUT /api/v1/runs/{run_id}/artifacts/_local-upload`` (tag: results)

  The local-filesystem presign fallback's upload sink. The dev /
  alpha deploy has no S3-compatible object store, so the
  ``:presign`` operation mints URLs that point back here. The URL
  carries an HMAC signature over ``run_id`` + path + expiry; this
  handler re-verifies the signature, then writes the request body
  under the run's allocated ``backend_key_prefix``. The signature
  is the auth contract for this endpoint -- a forged or expired URL
  is rejected with 403, so no object-store credential is needed.

Both operations are mTLS-gated -- the presence of an
nginx-verified client certificate (forwarded as
``SSL_CLIENT_S_DN_CN``) is required. Until nginx is wired for
``ssl_verify_client on`` every call short-circuits to 401, exactly
as the sibling ingest endpoints in
:mod:`runs.restapi.v1.runs_routes` do.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.jobs.dispatch.receipt import (
    repository as receipt_repo,
)
from automojo.pychestrate.webservice.jobs.results import presign
from automojo.pychestrate.webservice.jobs.results.backend import (
    SharedResultsBackend,
)
from automojo.pychestrate.webservice.jobs.results.errors import (
    AllocationNotFoundError,
    ArtifactPathInvalidError,
    PresignSignatureInvalidError,
    TooManyArtifactPathsError,
)
from automojo.pychestrate.webservice.jobs.run.state import repository as run_repo
from automojo.pychestrate.webservice.jobs.run.state.enums import RunState


RUNS_PATH = "/runs"

#: WSGI environ key nginx populates with the verified client cert
#: common-name after a successful mTLS handshake. Mirrors the seam
#: documented on :mod:`runs.restapi.v1.runs_routes`.
MTLS_CLIENT_CN_ENVIRON_KEY = "SSL_CLIENT_S_DN_CN"

#: Env var the deploy can stage with the HMAC secret used to sign
#: local-fs upload URLs. When unset the bootstrap publishes a
#: per-process random secret -- correct for a single-worker dev
#: deploy, but a multi-worker production deploy must stage a real
#: shared secret here.
ENV_PRESIGN_SIGNING_SECRET = "PYCHESTRATE_RESULT_PRESIGN_SECRET"

#: Run states that still accept result-tree upload. A run that has
#: already reached a terminal state has had its result tree scanned
#: (or abandoned); minting fresh upload URLs for it would race the
#: ingest scanner, so the handler rejects those with 409.
UPLOAD_ACCEPTING_STATES = frozenset({
    RunState.DISPATCHED,
    RunState.DISPATCH_UNCONFIRMED,
    RunState.RUNNING,
    RunState.PROGRESS_STALLED,
    RunState.COMPLETING,
})

#: Hard cap on the size of a single artifact body the local-fs
#: upload sink will accept. A result-tree artifact larger than this
#: is rejected with 413 -- the client chunks larger payloads or the
#: operator wires a real object store.
MAX_LOCAL_UPLOAD_BYTES: int = 256 * 1024 * 1024

#: Module-level seam carrying the HMAC signing secret. Published by
#: :func:`set_presign_signing_secret` from the bootstrap; tests
#: override it directly.
ACTIVE_PRESIGN_SIGNING_SECRET: Optional[bytes] = None

#: Module-level seam carrying the :class:`SharedResultsBackend`.
#: Published by :func:`set_shared_results_backend` from the
#: bootstrap so the handler can mint URLs without re-reading the
#: driver config on every request.
ACTIVE_SHARED_RESULTS_BACKEND: Optional[SharedResultsBackend] = None

_LOGGER = logging.getLogger("pychestrate.runs.artifacts_routes")


# ---------------------------------------------------------------------------
# Seam plumbing
# ---------------------------------------------------------------------------


def set_presign_signing_secret(*, secret: Optional[bytes]) -> None:
    """
        Publish the HMAC signing secret used for local-fs upload
        URLs.

        :param secret: Secret bytes, or ``None`` to clear.

        :returns: None.
    """
    global ACTIVE_PRESIGN_SIGNING_SECRET
    ACTIVE_PRESIGN_SIGNING_SECRET = secret
    return


def set_shared_results_backend(
        *, backend: Optional[SharedResultsBackend]
    ) -> None:
    """
        Publish the :class:`SharedResultsBackend` instance the
        presign handler delegates URL minting to.

        :param backend: Backend instance, or ``None`` to clear.

        :returns: None.
    """
    global ACTIVE_SHARED_RESULTS_BACKEND
    ACTIVE_SHARED_RESULTS_BACKEND = backend
    return


def resolve_presign_signing_secret_from_environment() -> bytes:
    """
        Resolve the HMAC signing secret from the deploy
        environment, falling back to a per-process random secret
        when the env var is unset.

        :returns: Secret bytes.
    """
    raw = os.environ.get(ENV_PRESIGN_SIGNING_SECRET, "")
    if raw is not None and len(raw.strip()) > 0:
        rtnval = raw.strip().encode("utf-8")
        return rtnval

    _LOGGER.warning(
        "pychestrate.runs.artifacts.presign_secret_random: %s is unset;"
        " generating a per-process random secret. A multi-worker"
        " deploy must stage a shared secret here.",
        ENV_PRESIGN_SIGNING_SECRET,
    )
    rtnval = os.urandom(32)
    return rtnval


# ---------------------------------------------------------------------------
# Problem-flow plumbing (mirrors runs_routes._ProblemAbort)
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition
        once and the top-level handler can convert it to a return
        value at the boundary.
    """

    def __init__(self, response: Response) -> None:
        super().__init__("problem abort")
        self.response: Response = response
        return


def _abort_problem(
        *,
        request: Request,
        status: int,
        detail: str,
        extensions: Optional[Dict[str, Any]] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional namespaced extension members.

        :returns: Never returns.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session attached by the
        session middleware, or ``None`` when none is bound.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session.
    """
    db_session = _resolve_db_session(request=request)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured.",
        )
    rtnval = db_session
    return rtnval


def _resolve_mtls_client_cn(request: Request) -> Optional[str]:
    """
        Return the verified client common-name nginx forwarded for
        this request, or ``None`` when no mTLS handshake completed.

        :param request: Incoming webworks request.

        :returns: Client common-name string or None.
    """
    explicit = getattr(request, "mtls_client_cn", None)
    if isinstance(explicit, str) and len(explicit) > 0:
        rtnval = explicit
        return rtnval

    environ = getattr(request, "environ", None)
    if isinstance(environ, dict):
        candidate = environ.get(MTLS_CLIENT_CN_ENVIRON_KEY, None)
        if isinstance(candidate, str) and len(candidate) > 0:
            rtnval = candidate
            return rtnval

    scope = getattr(request, "scope", None)
    if isinstance(scope, dict):
        candidate = scope.get(MTLS_CLIENT_CN_ENVIRON_KEY, None)
        if isinstance(candidate, str) and len(candidate) > 0:
            rtnval = candidate
            return rtnval

    rtnval = None
    return rtnval


def _require_mtls_client_cn(request: Request) -> str:
    """
        Resolve the mTLS-verified client common-name or abort 401.

        :param request: Incoming webworks request.

        :returns: Client common-name string.
    """
    candidate = _resolve_mtls_client_cn(request=request)
    if candidate is None:
        _abort_problem(
            request=request,
            status=401,
            detail=(
                "Mutual-TLS client certificate required (nginx must"
                " forward SSL_CLIENT_S_DN_CN)."
            ),
        )
    rtnval = candidate
    return rtnval


def _decode_json_object_or_abort(*, request: Request) -> Dict[str, Any]:
    """
        Decode the request body as a JSON object, aborting 400 on
        missing / malformed / non-dict.

        :param request: Incoming webworks request.

        :returns: Decoded dict.
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        _abort_problem(
            request=request,
            status=400,
            detail="Request body must be JSON.",
        )
    if isinstance(payload, dict) is False:
        _abort_problem(
            request=request,
            status=400,
            detail="Request body must be a JSON object.",
        )

    rtnval = payload
    return rtnval


def _require_run_exists(*, request: Request, db_session: Any, run_id: str) -> Any:
    """
        Fetch the run row, aborting 404 when missing.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID from the path.

        :returns: The :class:`Run` row.
    """
    row = run_repo.find_run(db_session=db_session, run_id=run_id)
    if row is None:
        _abort_problem(
            request=request,
            status=404,
            detail="Run not found.",
            extensions={"run_id": run_id},
        )
    rtnval = row
    return rtnval


def _require_cert_owns_run(
        *,
        request: Request,
        db_session: Any,
        run_id: str,
        client_cn: str
    ) -> None:
    """
        Enforce that the mTLS-verified client common-name owns the
        run's current dispatch.

        The dispatch receipt row binds a run to the ``client_id``
        that accepted its envelope. The cert common-name is the
        enrolled client UUID, so a match between the receipt's
        ``client_id`` and the cert CN proves the calling client is
        the one running the job. A missing receipt means the run
        has not been accepted by any client yet -- there is nothing
        to upload, so the request is also rejected.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID from the path.
        :param client_cn: Common-name nginx forwarded.

        :returns: None.
    """
    receipt = receipt_repo.find_by_run(db_session=db_session, run_id=run_id)
    if receipt is None:
        _abort_problem(
            request=request,
            status=403,
            detail=(
                "Run has no dispatch receipt; no client owns this"
                " run's result upload."
            ),
            extensions={"run_id": run_id},
        )

    owner_client_id = str(receipt.client_id)
    if owner_client_id != client_cn:
        _abort_problem(
            request=request,
            status=403,
            detail=(
                "Client certificate common-name does not own this"
                " run's current dispatch."
            ),
            extensions={
                "run_id": run_id,
                "cert_client_cn": client_cn,
                "run_owner_client_id": owner_client_id,
            },
        )
    return


def _require_run_accepts_upload(*, request: Request, run_row: Any) -> None:
    """
        Enforce that the run is in a state that still accepts a
        result-tree upload.

        :param request: Incoming webworks request.
        :param run_row: The :class:`Run` row.

        :returns: None.
    """
    state = getattr(run_row, "state", None)
    if state not in UPLOAD_ACCEPTING_STATES:
        state_value = getattr(state, "value", None)
        if state_value is None:
            state_value = str(state)
        _abort_problem(
            request=request,
            status=409,
            detail=(
                "Run is not in a state that accepts result upload."
            ),
            extensions={"run_state": state_value},
        )
    return


def _require_signing_secret(request: Request) -> bytes:
    """
        Resolve the published HMAC signing secret or abort 503.

        :param request: Incoming webworks request.

        :returns: Secret bytes.
    """
    secret = ACTIVE_PRESIGN_SIGNING_SECRET
    if secret is None or len(secret) == 0:
        _abort_problem(
            request=request,
            status=503,
            detail=(
                "Result-upload presigning is not configured on this"
                " service instance."
            ),
        )
    rtnval = secret
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/runs/{run_id}/artifacts:presign
# ---------------------------------------------------------------------------


def _upload_target_to_dict(*, target: presign.ArtifactUploadTarget) -> Dict[str, Any]:
    """
        Serialize an :class:`ArtifactUploadTarget` to the OpenAPI
        ``ArtifactUploadTarget`` schema.

        :param target: Minted upload target.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "path": target.path,
        "put_url": target.put_url,
        "expires_at": target.expires_at.isoformat(),
        "headers": dict(target.headers),
    }
    return rtnval


def handle_presign_artifacts(request: Request) -> Response:
    """
        ``POST /api/v1/runs/{run_id}/artifacts:presign`` -- mint
        short-lived presigned PUT URLs for a run's result tree.

        The pod client agent posts the relative artifact paths from
        its result-tree walk. The handler verifies the calling mTLS
        certificate owns the run's current dispatch, that the run
        still accepts uploads, and bound-checks the path batch,
        then returns one presigned upload target per path.

        :param request: Incoming webworks request.

        :returns: 200 + JSON body on success; 401 / 403 / 404 / 409
                  / 422 / 503 problem responses on failure.
    """
    run_id = request.path_params.get("run_id", "")
    try:
        client_cn = _require_mtls_client_cn(request=request)
        payload = _decode_json_object_or_abort(request=request)
        db_session = _require_session(request=request)
        signing_secret = _require_signing_secret(request=request)

        backend = ACTIVE_SHARED_RESULTS_BACKEND
        if backend is None:
            _abort_problem(
                request=request,
                status=503,
                detail=(
                    "Shared results backend is not configured on this"
                    " service instance."
                ),
            )

        run_row = _require_run_exists(
            request=request, db_session=db_session, run_id=run_id,
        )
        _require_cert_owns_run(
            request=request,
            db_session=db_session,
            run_id=run_id,
            client_cn=client_cn,
        )
        _require_run_accepts_upload(request=request, run_row=run_row)

        raw_paths = payload.get("paths", None)
        try:
            canonical_paths: List[str] = presign.validate_artifact_path_batch(
                paths=raw_paths,
            )
        except TooManyArtifactPathsError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )
            canonical_paths = []  # unreachable -- _abort_problem raises.
        except ArtifactPathInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )
            canonical_paths = []  # unreachable

        try:
            targets = backend.presign_put(
                run_id=run_id,
                version_prefix="/api/v1",
                relative_paths=canonical_paths,
                signing_secret=signing_secret,
            )
        except AllocationNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )
            targets = []  # unreachable

        uploads: List[Dict[str, Any]] = []
        for target in targets:
            uploads.append(_upload_target_to_dict(target=target))

        _LOGGER.info(
            "pychestrate.runs.artifacts.presign run_id=%s client_cn=%s count=%d",
            run_id,
            client_cn,
            len(uploads),
        )

        body: Dict[str, Any] = {
            "run_id": run_id,
            "uploads": uploads,
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# PUT /api/v1/runs/{run_id}/artifacts/_local-upload
# ---------------------------------------------------------------------------


def _resolve_query_param(*, request: Request, name: str) -> Optional[str]:
    """
        Return a single query-param value, normalizing the
        list-or-scalar shape webworks may present.

        :param request: Incoming webworks request.
        :param name: Query-param name.

        :returns: String value or None.
    """
    raw = request.query_params.get(name, None)
    if raw is None:
        rtnval = None
        return rtnval
    if isinstance(raw, list):
        if len(raw) == 0:
            rtnval = None
            return rtnval
        rtnval = str(raw[0])
        return rtnval
    rtnval = str(raw)
    return rtnval


def _request_body_bytes(request: Request) -> bytes:
    """
        Return the raw request body bytes, normalizing the various
        shapes webworks / test fakes present.

        :param request: Incoming webworks request.

        :returns: Body bytes (possibly empty).
    """
    body = getattr(request, "body", None)
    if callable(body) is True:
        body = body()
    if body is None:
        rtnval = b""
        return rtnval
    if isinstance(body, bytes):
        rtnval = body
        return rtnval
    if isinstance(body, str):
        rtnval = body.encode("utf-8")
        return rtnval
    rtnval = bytes(body)
    return rtnval


def handle_local_upload(request: Request) -> Response:
    """
        ``PUT /api/v1/runs/{run_id}/artifacts/_local-upload`` --
        the local-filesystem presign fallback's upload sink.

        The URL the client PUTs to was minted by
        :func:`handle_presign_artifacts` and carries an HMAC
        signature over ``run_id`` + relative path + expiry. This
        handler re-verifies the signature against the server-held
        secret, resolves the run's allocated ``backend_key_prefix``,
        and writes the request body to ``<prefix>/<relative path>``.

        The signature -- not a permission check -- is the auth
        contract: a forged or expired URL is rejected with 403, so
        no object-store credential is required.

        :param request: Incoming webworks request.

        :returns: 201 on success; 401 / 403 / 404 / 413 / 503
                  problem responses on failure.
    """
    run_id = request.path_params.get("run_id", "")
    try:
        _require_mtls_client_cn(request=request)
        db_session = _require_session(request=request)
        signing_secret = _require_signing_secret(request=request)

        backend = ACTIVE_SHARED_RESULTS_BACKEND
        if backend is None:
            _abort_problem(
                request=request,
                status=503,
                detail=(
                    "Shared results backend is not configured on this"
                    " service instance."
                ),
            )

        raw_path = _resolve_query_param(request=request, name="path")
        raw_expires = _resolve_query_param(request=request, name="expires")
        raw_signature = _resolve_query_param(request=request, name="signature")

        missing: List[str] = []
        if raw_path is None or len(raw_path) == 0:
            missing.append("path")
        if raw_expires is None or len(raw_expires) == 0:
            missing.append("expires")
        if raw_signature is None or len(raw_signature) == 0:
            missing.append("signature")
        if len(missing) > 0:
            _abort_problem(
                request=request,
                status=400,
                detail="Missing required query parameter(s): {}".format(
                    ", ".join(missing),
                ),
                extensions={"missing_query_params": missing},
            )

        try:
            relative_path = presign.canonicalize_relative_path(raw=raw_path)
        except ArtifactPathInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )
            relative_path = ""  # unreachable

        try:
            expires_epoch = int(raw_expires)
        except ValueError:
            _abort_problem(
                request=request,
                status=400,
                detail="Query parameter 'expires' must be an integer epoch.",
                extensions={"raw_value": raw_expires},
            )
            expires_epoch = 0  # unreachable

        now = datetime.now(timezone.utc)
        try:
            presign.verify_upload_signature(
                secret=signing_secret,
                run_id=run_id,
                relative_path=relative_path,
                expires_epoch=expires_epoch,
                signature=raw_signature,
                now=now,
            )
        except PresignSignatureInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=403,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )

        _require_run_exists(
            request=request, db_session=db_session, run_id=run_id,
        )

        try:
            allocation = backend.resolve(
                db_session=db_session, run_id=run_id,
            )
        except AllocationNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )
            allocation = None  # unreachable

        body_bytes = _request_body_bytes(request)
        if len(body_bytes) > MAX_LOCAL_UPLOAD_BYTES:
            _abort_problem(
                request=request,
                status=413,
                detail="Uploaded artifact body exceeds the size cap.",
                extensions={
                    "body_bytes": len(body_bytes),
                    "max_bytes": MAX_LOCAL_UPLOAD_BYTES,
                },
            )

        destination = _write_local_artifact(
            request=request,
            prefix=allocation.backend_key_prefix,
            relative_path=relative_path,
            body_bytes=body_bytes,
        )

        _LOGGER.info(
            "pychestrate.runs.artifacts.local_upload run_id=%s path=%s bytes=%d",
            run_id,
            relative_path,
            len(body_bytes),
        )

        body: Dict[str, Any] = {
            "run_id": run_id,
            "path": relative_path,
            "bytes_written": len(body_bytes),
            "stored_at": destination,
        }
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def _write_local_artifact(
        *,
        request: Request,
        prefix: str,
        relative_path: str,
        body_bytes: bytes
    ) -> str:
    """
        Write an uploaded artifact body under the run's allocated
        result-tree prefix.

        The ``relative_path`` was already canonicalized (no
        absolute paths, no ``..`` traversal) so the join cannot
        escape ``prefix``. A defensive ``commonpath`` check guards
        the invariant a second time.

        :param request: Incoming webworks request (for problem
                         aborts).
        :param prefix: The run's allocated ``backend_key_prefix``
                       -- a local filesystem directory on the alpha
                       deploy.
        :param relative_path: Canonicalized relative artifact path.
        :param body_bytes: The artifact bytes to write.

        :returns: The absolute filesystem path the bytes landed at.
    """
    prefix_abs = os.path.abspath(prefix)
    destination = os.path.abspath(os.path.join(prefix_abs, relative_path))

    common = os.path.commonpath([prefix_abs, destination])
    if common != prefix_abs:
        _abort_problem(
            request=request,
            status=400,
            detail="Resolved artifact path escapes the run result tree.",
            extensions={"relative_path": relative_path},
        )

    parent_dir = os.path.dirname(destination)
    os.makedirs(parent_dir, exist_ok=True)

    with open(destination, "wb") as handle:
        handle.write(body_bytes)

    rtnval = destination
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_artifacts_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the presigned result-upload routes to a webworks
        application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + RUNS_PATH
    app.attach_route(
        base + "/{run_id}/artifacts:presign", methods=["POST"],
    )(handle_presign_artifacts)
    app.attach_route(
        base + "/{run_id}/artifacts/" + presign.LOCAL_UPLOAD_PATH_SEGMENT,
        methods=["PUT"],
    )(handle_local_upload)

    _LOGGER.warning(
        "pychestrate.runs.artifacts_routes.mtls_not_wired: the"
        " result-upload endpoints require nginx mTLS but will reject"
        " every request with 401 until SSL_CLIENT_S_DN_CN is"
        " forwarded."
    )
    return


__all__ = [
    "RUNS_PATH",
    "MTLS_CLIENT_CN_ENVIRON_KEY",
    "ENV_PRESIGN_SIGNING_SECRET",
    "UPLOAD_ACCEPTING_STATES",
    "MAX_LOCAL_UPLOAD_BYTES",
    "ACTIVE_PRESIGN_SIGNING_SECRET",
    "ACTIVE_SHARED_RESULTS_BACKEND",
    "set_presign_signing_secret",
    "set_shared_results_backend",
    "resolve_presign_signing_secret_from_environment",
    "handle_presign_artifacts",
    "handle_local_upload",
    "register_artifacts_routes",
]
