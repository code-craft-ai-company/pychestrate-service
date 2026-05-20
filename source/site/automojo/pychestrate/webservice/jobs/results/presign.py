"""
.. module:: jobs.results.presign
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Presigned result-upload URL minting + signature verification.

.. moduleauthor:: Automation Mojo LLC

PR p19l closes the last server gap in the orchestration loop's
result path: the pod client agent can build a result manifest but
has no credentialed way to push the result tree to the shared
results backend.

The shared results backend on the dev / alpha deploy is a SQLite
metadata store plus a *local filesystem* result tree -- the
:class:`SharedResultsBackend` allocates a ``backend_key_prefix``
and the result-ingest scanner reads that prefix verbatim as a
filesystem path. There is no S3-compatible object store in tree,
and the Layer-0 ``ObjectStore`` facade has zero in-tree driver
implementations, so an S3-style ``presign_put`` cannot be honored
on the alpha deploy.

This module therefore implements a **local-filesystem presign
fallback**. ``presign_put`` mints a short-lived HMAC-signed URL
that points back at a dedicated server endpoint
(``PUT /api/v1/runs/{run_id}/artifacts/_local-upload``). The
signature is an HMAC-SHA256 over ``run_id`` + relative path +
expiry, so the URL is tamper-proof without object-store
credentials ever reaching the client. The client's code path is
identical to the S3 case: it always PUTs bytes to a URL.

When an operator later wires a real S3-compatible object store the
``presign_put`` seam can dispatch to the driver's native presign
instead; the HTTP surface (the ``:presign`` operation) does not
change.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import hmac
import os

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List
from urllib.parse import quote, urlencode

from automojo.pychestrate.webservice.jobs.results.errors import (
    ArtifactPathInvalidError,
    PresignSignatureInvalidError,
    TooManyArtifactPathsError,
)


#: Hard cap on the number of artifact paths a single ``:presign``
#: request may ask for. A result tree larger than this is almost
#: certainly a walk that escaped its root -- the client batches its
#: walk so this is a generous ceiling, not a tuning knob.
MAX_ARTIFACT_PATHS: int = 512

#: Hard cap on the summed character length of every requested
#: relative path. Guards against a request that stays under
#: :data:`MAX_ARTIFACT_PATHS` but smuggles pathological path
#: lengths.
MAX_TOTAL_PATH_CHARS: int = 64 * 1024

#: Per-path length cap. A single result-tree relative path longer
#: than this is rejected.
MAX_SINGLE_PATH_CHARS: int = 1024

#: Default lifetime of a minted presigned URL. The client PUTs the
#: bytes immediately after a ``:presign`` call so 15 minutes is a
#: comfortable upper bound that still bounds replay exposure.
DEFAULT_PRESIGN_TTL_SECONDS: int = 15 * 60

#: The path segment the local-fs fallback upload endpoint is
#: mounted under, relative to ``/api/v1/runs/{run_id}/artifacts``.
LOCAL_UPLOAD_PATH_SEGMENT: str = "_local-upload"


@dataclass(frozen=True)
class ArtifactUploadTarget:
    """
        One minted presigned upload target returned to the client.

        :param path: The relative artifact path the target covers
                     (echoed back verbatim from the request).
        :param put_url: Absolute (or path-absolute) URL the client
                        PUTs the artifact bytes to.
        :param expires_at: UTC timestamp after which the URL is
                           rejected.
        :param headers: Headers the client must send verbatim on
                        the PUT. For the local-fs fallback this is
                        empty -- the signature travels in the URL
                        query string.
    """
    path: str
    put_url: str
    expires_at: datetime
    headers: dict


def canonicalize_relative_path(*, raw: str) -> str:
    """
        Validate + canonicalize a single client-supplied relative
        artifact path.

        The path is rejected when it is empty, absolute, contains a
        ``..`` traversal segment, carries a drive letter / backslash,
        or exceeds :data:`MAX_SINGLE_PATH_CHARS`. On success the
        path is returned with backslashes folded to forward slashes
        and any leading ``./`` stripped.

        :param raw: Caller-supplied relative path.

        :returns: Canonicalized relative path.
        :raises: ArtifactPathInvalidError when the path cannot be
                 accepted.
    """
    if raw is None:
        err_msg = "Artifact path is None."
        raise ArtifactPathInvalidError(err_msg) from None
    if isinstance(raw, str) is False:
        err_msg = "Artifact path must be a string."
        raise ArtifactPathInvalidError(err_msg) from None

    candidate = raw.strip()
    if len(candidate) == 0:
        err_msg = "Artifact path is empty."
        raise ArtifactPathInvalidError(err_msg) from None
    if len(candidate) > MAX_SINGLE_PATH_CHARS:
        err_lines = ["Artifact path is too long."]
        err_lines.append("LENGTH: {}".format(len(candidate)))
        err_lines.append("MAX: {}".format(MAX_SINGLE_PATH_CHARS))
        err_msg = os.linesep.join(err_lines)
        raise ArtifactPathInvalidError(err_msg) from None

    folded = candidate.replace("\\", "/")
    if folded.startswith("/") is True:
        err_lines = ["Artifact path must be relative, not absolute."]
        err_lines.append("PATH: {}".format(raw))
        err_msg = os.linesep.join(err_lines)
        raise ArtifactPathInvalidError(err_msg) from None

    if folded.startswith("./") is True:
        folded = folded[2:]

    segments = folded.split("/")
    for segment in segments:
        if segment == "..":
            err_lines = ["Artifact path contains a parent traversal segment."]
            err_lines.append("PATH: {}".format(raw))
            err_msg = os.linesep.join(err_lines)
            raise ArtifactPathInvalidError(err_msg) from None
        if segment == "":
            continue
        if ":" in segment:
            err_lines = ["Artifact path segment carries a drive / scheme separator."]
            err_lines.append("PATH: {}".format(raw))
            err_msg = os.linesep.join(err_lines)
            raise ArtifactPathInvalidError(err_msg) from None

    non_empty_segments: List[str] = []
    for segment in segments:
        if len(segment) > 0:
            non_empty_segments.append(segment)
    if len(non_empty_segments) == 0:
        err_lines = ["Artifact path canonicalizes to empty."]
        err_lines.append("PATH: {}".format(raw))
        err_msg = os.linesep.join(err_lines)
        raise ArtifactPathInvalidError(err_msg) from None

    rtnval = "/".join(non_empty_segments)
    return rtnval


def validate_artifact_path_batch(*, paths: List[str]) -> List[str]:
    """
        Canonicalize + bound-check a whole batch of requested
        artifact paths.

        :param paths: List of caller-supplied relative paths.

        :returns: List of canonicalized relative paths, in request
                  order.
        :raises: TooManyArtifactPathsError when the count or summed
                 length exceeds the configured caps;
                 ArtifactPathInvalidError when any single path is
                 unacceptable.
    """
    if paths is None:
        err_msg = "Artifact path batch is None."
        raise ArtifactPathInvalidError(err_msg) from None
    if isinstance(paths, list) is False:
        err_msg = "Artifact path batch must be a list."
        raise ArtifactPathInvalidError(err_msg) from None
    if len(paths) == 0:
        err_msg = "Artifact path batch is empty."
        raise ArtifactPathInvalidError(err_msg) from None
    if len(paths) > MAX_ARTIFACT_PATHS:
        err_lines = ["Too many artifact paths in one presign request."]
        err_lines.append("COUNT: {}".format(len(paths)))
        err_lines.append("MAX: {}".format(MAX_ARTIFACT_PATHS))
        err_msg = os.linesep.join(err_lines)
        raise TooManyArtifactPathsError(err_msg) from None

    total_chars = 0
    for path in paths:
        if isinstance(path, str) is True:
            total_chars = total_chars + len(path)
    if total_chars > MAX_TOTAL_PATH_CHARS:
        err_lines = ["Artifact path batch exceeds the total length cap."]
        err_lines.append("TOTAL_CHARS: {}".format(total_chars))
        err_lines.append("MAX: {}".format(MAX_TOTAL_PATH_CHARS))
        err_msg = os.linesep.join(err_lines)
        raise TooManyArtifactPathsError(err_msg) from None

    canonical_paths: List[str] = []
    for path in paths:
        canonical = canonicalize_relative_path(raw=path)
        canonical_paths.append(canonical)
    rtnval = canonical_paths
    return rtnval


def _signing_message(
        *,
        run_id: str,
        relative_path: str,
        expires_epoch: int
    ) -> bytes:
    """
        Build the canonical byte string the upload signature is
        computed over. Newline-joined fields keep the message
        unambiguous so two different ``(run_id, path, expiry)``
        tuples can never collide on the same message.

        :param run_id: Run UUID.
        :param relative_path: Canonicalized relative artifact path.
        :param expires_epoch: Expiry as a Unix epoch second.

        :returns: The message bytes.
    """
    field_lines = [
        "pychestrate-artifact-upload-v1",
        run_id,
        relative_path,
        str(expires_epoch),
    ]
    joined = "\n".join(field_lines)
    rtnval = joined.encode("utf-8")
    return rtnval


def compute_upload_signature(
        *,
        secret: bytes,
        run_id: str,
        relative_path: str,
        expires_epoch: int
    ) -> str:
    """
        Compute the HMAC-SHA256 signature for a local-fs upload
        URL.

        :param secret: The server-held signing secret.
        :param run_id: Run UUID.
        :param relative_path: Canonicalized relative artifact path.
        :param expires_epoch: Expiry as a Unix epoch second.

        :returns: Lowercase hex signature.
    """
    message = _signing_message(
        run_id=run_id,
        relative_path=relative_path,
        expires_epoch=expires_epoch,
    )
    digest = hmac.new(secret, message, hashlib.sha256)
    rtnval = digest.hexdigest()
    return rtnval


def verify_upload_signature(
        *,
        secret: bytes,
        run_id: str,
        relative_path: str,
        expires_epoch: int,
        signature: str,
        now: datetime
    ) -> None:
    """
        Verify a presented local-fs upload signature, raising on
        any mismatch or on expiry.

        The HMAC comparison uses :func:`hmac.compare_digest` so the
        check does not leak timing information about how far a
        forged signature matched.

        :param secret: The server-held signing secret.
        :param run_id: Run UUID from the upload request.
        :param relative_path: Canonicalized relative artifact path
                              from the upload request.
        :param expires_epoch: Expiry epoch second carried in the
                              upload URL.
        :param signature: Hex signature carried in the upload URL.
        :param now: Current UTC time used for the expiry check.

        :returns: None.
        :raises: PresignSignatureInvalidError when the signature is
                 malformed, does not match, or has expired.
    """
    if signature is None or isinstance(signature, str) is False or len(signature) == 0:
        err_msg = "Upload signature is missing."
        raise PresignSignatureInvalidError(err_msg) from None

    now_utc = now
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_epoch = int(now_utc.timestamp())
    if now_epoch > expires_epoch:
        err_lines = ["Upload signature has expired."]
        err_lines.append("NOW_EPOCH: {}".format(now_epoch))
        err_lines.append("EXPIRES_EPOCH: {}".format(expires_epoch))
        err_msg = os.linesep.join(err_lines)
        raise PresignSignatureInvalidError(err_msg) from None

    expected = compute_upload_signature(
        secret=secret,
        run_id=run_id,
        relative_path=relative_path,
        expires_epoch=expires_epoch,
    )
    matched = hmac.compare_digest(expected, signature)
    if matched is False:
        err_lines = ["Upload signature does not match."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append("PATH: {}".format(relative_path))
        err_msg = os.linesep.join(err_lines)
        raise PresignSignatureInvalidError(err_msg) from None
    return


def mint_local_upload_targets(
        *,
        secret: bytes,
        run_id: str,
        version_prefix: str,
        relative_paths: List[str],
        now: datetime,
        ttl_seconds: int = DEFAULT_PRESIGN_TTL_SECONDS
    ) -> List[ArtifactUploadTarget]:
    """
        Mint one :class:`ArtifactUploadTarget` per relative path,
        each carrying an HMAC-signed local-fs upload URL.

        The URL points at
        ``{version_prefix}/runs/{run_id}/artifacts/_local-upload``
        with the relative path, expiry, and signature carried as
        query parameters. The bytes the client PUTs land under the
        run's allocated ``backend_key_prefix`` once the upload
        endpoint verifies the signature.

        :param secret: Server-held signing secret.
        :param run_id: Run UUID.
        :param version_prefix: Versioned API prefix (``/api/v1``).
        :param relative_paths: Canonicalized relative paths.
        :param now: Current UTC time -- the expiry is computed from
                    this.
        :param ttl_seconds: Lifetime of the minted URLs.

        :returns: List of :class:`ArtifactUploadTarget`, in input
                  order.
    """
    now_utc = now
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    expires_at = now_utc + timedelta(seconds=ttl_seconds)
    expires_epoch = int(expires_at.timestamp())

    upload_base = "{}/runs/{}/artifacts/{}".format(
        version_prefix,
        quote(run_id, safe=""),
        LOCAL_UPLOAD_PATH_SEGMENT,
    )

    targets: List[ArtifactUploadTarget] = []
    for relative_path in relative_paths:
        signature = compute_upload_signature(
            secret=secret,
            run_id=run_id,
            relative_path=relative_path,
            expires_epoch=expires_epoch,
        )
        query = urlencode(
            {
                "path": relative_path,
                "expires": expires_epoch,
                "signature": signature,
            }
        )
        put_url = "{}?{}".format(upload_base, query)
        target = ArtifactUploadTarget(
            path=relative_path,
            put_url=put_url,
            expires_at=expires_at,
            headers={},
        )
        targets.append(target)

    rtnval = targets
    return rtnval


__all__ = [
    "MAX_ARTIFACT_PATHS",
    "MAX_TOTAL_PATH_CHARS",
    "MAX_SINGLE_PATH_CHARS",
    "DEFAULT_PRESIGN_TTL_SECONDS",
    "LOCAL_UPLOAD_PATH_SEGMENT",
    "ArtifactUploadTarget",
    "canonicalize_relative_path",
    "validate_artifact_path_batch",
    "compute_upload_signature",
    "verify_upload_signature",
    "mint_local_upload_targets",
]
