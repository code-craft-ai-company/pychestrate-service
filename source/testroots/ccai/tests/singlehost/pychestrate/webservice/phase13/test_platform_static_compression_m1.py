"""
.. module:: test_platform_static_compression_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Regression locks for gzip-encoded static text assets
               (audit XC-06) and the nginx site template that
               compresses proxied responses.

.. moduleauthor:: Code Craft AI LLC

Every shell page loads the ~1.6 MB mj-* component library. Before
XC-06 neither the app nor the nginx site config compressed it, so
each page shipped ~1.8 MB. These tests pin:

* the static handler gzip-encodes text assets when the request
  accepts gzip, and only then;
* the gzip body decodes to the file bytes;
* small files and already-compressed types stay identity-encoded;
* each representation has its own ETag and revalidates to 304;
* ``Vary: Accept-Encoding`` on every compressible asset;
* ``If-None-Match`` uses weak comparison (a proxy may weaken the tag);
* the nginx site template turns gzip on for the text types in the
  server block and every placeholder is rendered by the deploy script.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import gzip
import os
import re
import shutil
import tempfile

from typing import Any, Dict, Optional

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.foundation import static_files


class _Mapping:
    def __init__(self, values: Optional[Dict[str, str]] = None) -> None:
        self._values = values if values is not None else {}
        return

    def get(self, key: str, default: Any = None) -> Any:
        rtnval = self._values.get(key, default)
        return rtnval


class _FakeRequest:
    def __init__(
            self,
            *,
            filepath: str,
            headers: Optional[Dict[str, str]] = None,
            query: Optional[Dict[str, str]] = None
        ) -> None:
        self.path = "/static/" + filepath
        self.path_params = {"filepath": filepath}
        self.query_params = _Mapping(query)
        self.headers = _Mapping(headers)
        return


_JS_BODY: bytes = (b"export function f(){return 'pychestrate component library';}\n" * 400)


def _static_root_with(*, name: str, content: bytes) -> str:
    root = tempfile.mkdtemp(prefix="pyc-static-gz-")
    with open(os.path.join(root, name), "wb") as fh:
        fh.write(content)
    static_files.reset_static_asset_cache_for_testing()
    return root


def _serve(*, root: str, name: str, headers: Optional[Dict[str, str]] = None) -> Any:
    rtnval = static_files.serve_static_file(
        request=_FakeRequest(filepath=name, headers=headers),
        static_root=root,
    )
    return rtnval


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    rtnval = os.path.normpath(
        os.path.join(here, "..", "..", "..", "..", "..", "..", "..", "..")
    )
    return rtnval


# ---------------------------------------------------------------------------
# App-side compression of static text assets
# ---------------------------------------------------------------------------


def test_javascript_is_gzip_encoded_when_the_client_accepts_gzip():
    """
    **Feature: static asset compression (XC-06)**
    **Property: a JavaScript asset requested with Accept-Encoding: gzip
    is answered Content-Encoding: gzip.**
    """
    root = _static_root_with(name="lib.js", content=_JS_BODY)
    try:
        response = _serve(root=root, name="lib.js", headers={"Accept-Encoding": "gzip, deflate, br"})
    finally:
        shutil.rmtree(root, ignore_errors=True)
    testbase.assert_equal(response.headers.get("Content-Encoding"), "gzip")
    return


def test_gzip_body_decodes_to_the_file_bytes():
    """
    **Feature: static asset compression (XC-06)**
    **Property: the gzip body is smaller than the file and decompresses
    to exactly the file bytes.**
    """
    root = _static_root_with(name="lib.js", content=_JS_BODY)
    try:
        response = _serve(root=root, name="lib.js", headers={"Accept-Encoding": "gzip"})
    finally:
        shutil.rmtree(root, ignore_errors=True)
    testbase.assert_equal(
        (len(response.body) < len(_JS_BODY), gzip.decompress(response.body) == _JS_BODY),
        (True, True),
    )
    return


def test_identity_body_is_served_without_accept_encoding():
    """
    **Feature: static asset compression (XC-06)**
    **Property: a request that does not accept gzip receives the file
    bytes with no Content-Encoding.**
    """
    root = _static_root_with(name="lib.js", content=_JS_BODY)
    try:
        response = _serve(root=root, name="lib.js")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    testbase.assert_equal(
        ("Content-Encoding" in response.headers, response.body == _JS_BODY),
        (False, True),
    )
    return


def test_gzip_refused_with_zero_quality_is_honored():
    """
    **Feature: static asset compression (XC-06)**
    **Property: Accept-Encoding "gzip;q=0, *" refuses gzip, so the
    asset is sent identity-encoded.**
    """
    root = _static_root_with(name="lib.js", content=_JS_BODY)
    try:
        response = _serve(root=root, name="lib.js", headers={"Accept-Encoding": "gzip;q=0, *"})
    finally:
        shutil.rmtree(root, ignore_errors=True)
    testbase.assert_equal("Content-Encoding" in response.headers, False)
    return


def test_small_text_asset_is_not_compressed():
    """
    **Feature: static asset compression (XC-06)**
    **Property: a text asset below the minimum size is sent as-is even
    when gzip is accepted.**
    """
    root = _static_root_with(name="tiny.css", content=b"p{margin:0}")
    try:
        response = _serve(root=root, name="tiny.css", headers={"Accept-Encoding": "gzip"})
    finally:
        shutil.rmtree(root, ignore_errors=True)
    testbase.assert_equal("Content-Encoding" in response.headers, False)
    return


def test_binary_asset_is_not_compressed():
    """
    **Feature: static asset compression (XC-06)**
    **Property: an already-compressed type (PNG) is never gzip-encoded.**
    """
    root = _static_root_with(name="logo.png", content=b"\x89PNG" + b"\x00" * 4096)
    try:
        response = _serve(root=root, name="logo.png", headers={"Accept-Encoding": "gzip"})
    finally:
        shutil.rmtree(root, ignore_errors=True)
    testbase.assert_equal("Content-Encoding" in response.headers, False)
    return


def test_compressible_asset_varies_on_accept_encoding():
    """
    **Feature: static asset compression (XC-06)**
    **Property: both representations of a compressible asset carry
    Vary: Accept-Encoding so shared caches keep them apart.**
    """
    root = _static_root_with(name="lib.js", content=_JS_BODY)
    try:
        gz = _serve(root=root, name="lib.js", headers={"Accept-Encoding": "gzip"})
        plain = _serve(root=root, name="lib.js")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    testbase.assert_equal(
        (gz.headers.get("Vary"), plain.headers.get("Vary")),
        ("Accept-Encoding", "Accept-Encoding"),
    )
    return


def test_gzip_and_identity_representations_have_distinct_etags():
    """
    **Feature: static asset compression (XC-06)**
    **Property: the gzip representation's ETag differs from the
    identity ETag.**
    """
    root = _static_root_with(name="lib.js", content=_JS_BODY)
    try:
        gz = _serve(root=root, name="lib.js", headers={"Accept-Encoding": "gzip"})
        plain = _serve(root=root, name="lib.js")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    testbase.assert_not_equal(gz.headers["ETag"], plain.headers["ETag"])
    return


def test_gzip_representation_revalidates_to_304():
    """
    **Feature: static asset compression (XC-06)**
    **Property: If-None-Match carrying the gzip ETag on a gzip request
    yields 304 with an empty body.**
    """
    root = _static_root_with(name="lib.js", content=_JS_BODY)
    try:
        first = _serve(root=root, name="lib.js", headers={"Accept-Encoding": "gzip"})
        second = _serve(
            root=root,
            name="lib.js",
            headers={"Accept-Encoding": "gzip", "If-None-Match": first.headers["ETag"]},
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    testbase.assert_equal((second.status_code, second.body), (304, b""))
    return


def test_weakened_etag_still_revalidates():
    """
    **Feature: static asset compression (XC-06)**
    **Property: If-None-Match is compared weakly -- a W/-prefixed copy
    of the ETag (as a proxy may send) still yields 304.**
    """
    root = _static_root_with(name="lib.js", content=_JS_BODY)
    try:
        first = _serve(root=root, name="lib.js")
        second = _serve(
            root=root,
            name="lib.js",
            headers={"If-None-Match": "W/" + first.headers["ETag"]},
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    testbase.assert_equal(second.status_code, 304)
    return


def test_changed_file_is_served_fresh():
    """
    **Feature: static asset compression (XC-06)**
    **Property: the in-process asset cache is keyed on mtime and size,
    so a rewritten file is served with its new bytes.**
    """
    root = _static_root_with(name="lib.js", content=_JS_BODY)
    try:
        _serve(root=root, name="lib.js", headers={"Accept-Encoding": "gzip"})
        path = os.path.join(root, "lib.js")
        with open(path, "wb") as fh:
            fh.write(_JS_BODY + b"// v2\n")
        stat_result = os.stat(path)
        os.utime(path, ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns + 1_000_000_000))
        response = _serve(root=root, name="lib.js", headers={"Accept-Encoding": "gzip"})
    finally:
        shutil.rmtree(root, ignore_errors=True)
    testbase.assert_equal(gzip.decompress(response.body), _JS_BODY + b"// v2\n")
    return


# ---------------------------------------------------------------------------
# nginx site template
# ---------------------------------------------------------------------------


def _nginx_template_text() -> str:
    path = os.path.join(_repo_root(), "deployment", "pychestrate.nginx.conf.template")
    with open(path, "r", encoding="utf-8") as fh:
        rtnval = fh.read()
    return rtnval


def _https_server_block(text: str) -> str:
    start = text.index("listen 443 ssl")
    rtnval = text[start:]
    return rtnval


def test_nginx_template_enables_gzip_in_the_https_server_block():
    """
    **Feature: static asset compression (XC-06)**
    **Property: the nginx site template turns gzip on inside the HTTPS
    server block (not at http level, where the stock nginx.conf
    already declares it).**
    """
    text = _nginx_template_text()
    before_server = text[: text.index("server {")]
    testbase.assert_equal(
        (
            re.search(r"^\s*gzip\s+on;", _https_server_block(text), re.MULTILINE) is not None,
            re.search(r"^\s*gzip\s+on;", before_server, re.MULTILINE) is not None,
        ),
        (True, False),
    )
    return


def test_nginx_template_compresses_the_text_asset_types():
    """
    **Feature: static asset compression (XC-06)**
    **Property: gzip_types covers JavaScript, CSS, JSON and SVG.**
    """
    match = re.search(r"gzip_types([^;]*);", _nginx_template_text())
    types = set(match.group(1).split()) if match is not None else set()
    required = {"application/javascript", "text/javascript", "text/css", "application/json", "image/svg+xml"}
    testbase.assert_equal(sorted(required - types), [])
    return


def test_deploy_script_renders_every_nginx_template_placeholder():
    """
    **Feature: static asset compression (XC-06)**
    **Property: every @PLACEHOLDER@ in the nginx template is substituted
    by the deploy script's sed render.**
    """
    placeholders = set(re.findall(r"@[A-Z_]+@", _nginx_template_text()))
    script_path = os.path.join(_repo_root(), "deployment", "deploy-alpha-to-host.sh")
    with open(script_path, "r", encoding="utf-8") as fh:
        script = fh.read()
    rendered = set(re.findall(r"s\|(@[A-Z_]+@)\|", script))
    testbase.assert_equal(sorted(placeholders - rendered), [])
    return
