"""
.. module:: cli.openapi_cache
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Server-version-aware cache for OpenAPI documents.

.. moduleauthor:: Automation Mojo LLC

The CLI builds its argparse tree from an OpenAPI document. Refetching
on every invocation is wasteful, so the document is cached under
``~/.pychestrate/cache/openapi/<server-url-hash>.json``. The cached
copy is reused until the server's reported ``info.version`` changes,
at which point the file is refreshed.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json
import os

from pathlib import Path
from typing import Callable, Dict, Optional

from automojo.pychestrate.cli.exceptions import OpenApiUnavailableError


CACHE_DIR_RELATIVE: str = ".pychestrate/cache/openapi"
PYC_OPENAPI_CACHE_DIR_ENV_VAR: str = "PYC_OPENAPI_CACHE_DIR"


def _resolve_cache_dir() -> Path:
    """
        Return the cache directory path, honoring the test override env
        var :data:`PYC_OPENAPI_CACHE_DIR_ENV_VAR`.

        :returns: Absolute :class:`pathlib.Path`.
    """
    override = os.environ.get(PYC_OPENAPI_CACHE_DIR_ENV_VAR, None)
    if override is not None and len(override) > 0:
        rtnval = Path(override).expanduser().resolve()
        return rtnval
    rtnval = Path.home() / CACHE_DIR_RELATIVE
    return rtnval


def _hash_server_url(*, server_url: str) -> str:
    """
        Compute a stable filename hash for ``server_url``.

        :param server_url: Fully qualified server URL.

        :returns: Hex-encoded SHA-256 prefix (16 chars).
    """
    digest = hashlib.sha256(server_url.encode("utf-8")).hexdigest()
    rtnval = digest[:16]
    return rtnval


def _cache_path_for(*, server_url: str) -> Path:
    """
        Return the on-disk path for the cache entry of ``server_url``.

        :param server_url: Fully qualified server URL.

        :returns: Absolute :class:`pathlib.Path`.
    """
    cache_dir = _resolve_cache_dir()
    file_name = "{}.json".format(_hash_server_url(server_url=server_url))
    rtnval = cache_dir / file_name
    return rtnval


def _read_cached(*, cache_path: Path) -> Optional[Dict]:
    """
        Load a cached OpenAPI document if present and well-formed.

        :param cache_path: Absolute path to the cache file.

        :returns: Parsed dict or ``None`` on miss / corruption.
    """
    if not cache_path.is_file():
        rtnval: Optional[Dict] = None
        return rtnval
    try:
        text = cache_path.read_text(encoding="utf-8")
        rtnval = json.loads(text)
    except (OSError, json.JSONDecodeError):
        rtnval = None
    return rtnval


def _write_cached(*, cache_path: Path, document: Dict) -> None:
    """
        Atomically write ``document`` to ``cache_path``.

        :param cache_path: Destination cache path.
        :param document: OpenAPI document dict.

        :returns: None.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    os.replace(str(tmp_path), str(cache_path))
    return


def _document_version(*, document: Dict) -> str:
    """
        Read the server version key from an OpenAPI document.

        :param document: Parsed OpenAPI dict.

        :returns: Version string (empty when missing).
    """
    info_block = document.get("info", {})
    if isinstance(info_block, dict):
        rtnval = str(info_block.get("version", ""))
        return rtnval
    rtnval = ""
    return rtnval


def load_or_fetch(
        *,
        server_url: str,
        fetch_callable: Callable[[], Dict]
    ) -> Dict:
    """
        Return the OpenAPI document for ``server_url``, refreshing the
        cache when the server reports a different version.

        :param server_url: Fully qualified server URL.
        :param fetch_callable: No-arg callable that performs the actual
                               HTTP fetch and returns a parsed dict.
                               Exposed for testability.

        :returns: Live OpenAPI document.
        :raises: OpenApiUnavailableError when both cache and fetch fail.
    """
    cache_path = _cache_path_for(server_url=server_url)
    cached_document = _read_cached(cache_path=cache_path)

    fetched_document: Optional[Dict] = None
    fetch_failure_reason: Optional[str] = None
    try:
        fetched_document = fetch_callable()
    except Exception as xcpt:  # noqa: BLE001 — purposeful capture
        fetch_failure_reason = "{}: {}".format(type(xcpt).__name__, xcpt)

    if fetched_document is not None:
        cached_version = "" if cached_document is None else _document_version(document=cached_document)
        fetched_version = _document_version(document=fetched_document)
        if cached_document is None or cached_version != fetched_version:
            _write_cached(cache_path=cache_path, document=fetched_document)
        rtnval = fetched_document
        return rtnval

    if cached_document is not None:
        rtnval = cached_document
        return rtnval

    err_msg_lines = ["OpenAPI document is not available."]
    err_msg_lines.append("SERVER_URL: {}".format(server_url))
    err_msg_lines.append("CACHE_PATH: {}".format(cache_path))
    if fetch_failure_reason is not None:
        err_msg_lines.append("FETCH_ERROR: {}".format(fetch_failure_reason))
    err_msg = os.linesep.join(err_msg_lines)
    raise OpenApiUnavailableError(err_msg) from None
