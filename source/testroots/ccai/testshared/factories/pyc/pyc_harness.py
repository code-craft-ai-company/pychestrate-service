"""
.. module:: ccai.testshared.factories.pyc.pyc_harness
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Run ``pyc`` in-process against a fake server, with its
               configuration and cache in a throw-away directory.

.. moduleauthor:: Code Craft AI LLC

:class:`PycSandbox` points ``HOME``, ``XDG_CONFIG_HOME``,
``XDG_CACHE_HOME`` and ``PYC_OPENAPI_CACHE_DIR`` at a temporary
directory for the life of a test, so no test reads or writes the
developer's own ``~/.config/pychestrate`` or ``~/.cache``.
:class:`PycFakeServer` stands in for the HTTP opener and records
every request; :func:`run_pyc` drives ``entry.main`` and returns
``(exit_code, stdout, stderr)``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import json
import os
import tempfile

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from ccai.pychestrate.cli import entry
from ccai.pychestrate.cli.models import RestResponse


SERVER: str = "https://pyc.example.test"
TOKEN: str = "pyc_" + "T" * 43

#: The environment variables a sandbox redirects.
_SANDBOXED_VARIABLES = ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "PYC_OPENAPI_CACHE_DIR")

_REAL_DOCUMENT_CACHE: Dict[str, Any] = {}


def find_repository_root() -> Path:
    """
        The service checkout this test tree belongs to (the directory
        holding ``specs/``).

        :returns: Path.
    """
    current = Path(__file__).resolve()
    while not (current / "specs").is_dir() and current.parent != current:
        current = current.parent
    rtnval = current
    return rtnval


def load_real_openapi_document() -> Dict[str, Any]:
    """
        ``specs/openapi/pychestrate.yaml`` as the server serves it
        (``servers`` replaced with ``/api/v1``); parsed once per run.

        :returns: A deep copy of the document.
    """
    if "document" not in _REAL_DOCUMENT_CACHE:
        import yaml  # noqa: E402 -- test-only dependency

        loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
        spec_path = find_repository_root() / "specs" / "openapi" / "pychestrate.yaml"
        with open(spec_path, "r", encoding="utf-8") as fh:
            raw = yaml.load(fh, Loader=loader)
        document = json.loads(json.dumps(raw, default=str))
        document["servers"] = [{"url": "/api/v1"}]
        _REAL_DOCUMENT_CACHE["document"] = json.dumps(document)
    rtnval = json.loads(_REAL_DOCUMENT_CACHE["document"])
    return rtnval


class PycSandbox:
    """
        A temporary HOME / XDG config / XDG cache for one test.
        ``close()`` restores the process environment and deletes the
        directory.
    """

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="pyc-test-")
        self.root: Path = Path(self._tmp.name)
        self.environ: Dict[str, str] = {
            "HOME": str(self.root / "home"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_CACHE_HOME": str(self.root / "cache"),
            "PYC_OPENAPI_CACHE_DIR": str(self.root / "cache" / "pychestrate" / "openapi"),
        }
        (self.root / "home").mkdir(parents=True, exist_ok=True)
        self._saved: Dict[str, Optional[str]] = {}
        for name in _SANDBOXED_VARIABLES:
            self._saved[name] = os.environ.get(name, None)
            os.environ[name] = self.environ[name]
        return

    @property
    def credentials_path(self) -> Path:
        rtnval = self.root / "config" / "pychestrate" / "credentials"
        return rtnval

    @property
    def openapi_cache_dir(self) -> Path:
        rtnval = Path(self.environ["PYC_OPENAPI_CACHE_DIR"])
        return rtnval

    def write_credentials(self, text: str, mode: int = 0o600) -> None:
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)
        self.credentials_path.write_text(text, encoding="utf-8")
        os.chmod(str(self.credentials_path), mode)
        return

    def log_in(self, *, server_url: str = SERVER, token: str = TOKEN, extra: str = "") -> None:
        """
            Write a default profile holding ``server_url`` and
            ``token`` (what ``pyc login`` would have stored).
        """
        self.write_credentials(
            "[default]\nserver_url = {}\nbearer_token = {}\n{}".format(server_url, token, extra)
        )
        return

    def close(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self._tmp.cleanup()
        return


class PycFakeServer:
    """
        Fake HTTP opener: answers by ``(method, path)`` and records
        every request (method, url, path, query, headers, body).
        An answer may be a body (sent as 200 JSON), a
        :class:`RestResponse`, or a zero-argument callable returning
        either. Unknown routes answer a 404 problem document.
    """

    def __init__(self, routes: Optional[Dict[Tuple[str, str], Any]] = None) -> None:
        self.routes: Dict[Tuple[str, str], Any] = dict(routes or {})
        self.requests: List[Dict[str, Any]] = []
        return

    def __call__(self, *, request, timeout, context) -> RestResponse:
        parts = urlsplit(request.full_url)
        body = request.data.decode("utf-8") if request.data else None
        self.requests.append({
            "method": request.get_method(),
            "url": request.full_url,
            "path": parts.path,
            "query": parts.query,
            "headers": {k.lower(): v for k, v in request.header_items()},
            "body": json.loads(body) if body else None,
        })
        answer = self.routes.get((request.get_method(), parts.path), None)
        if callable(answer):
            answer = answer()
        if answer is None:
            rtnval = RestResponse(
                status_code=404, headers={"content-type": "application/problem+json"}, body=None,
                raw_text='{"title": "Not Found", "detail": "no route", "status": 404}',
            )
            return rtnval
        if isinstance(answer, RestResponse):
            return answer
        rtnval = RestResponse(
            status_code=200, headers={"content-type": "application/json"},
            body=answer, raw_text=json.dumps(answer),
        )
        return rtnval

    def paths(self) -> List[str]:
        rtnval = [request["path"] for request in self.requests]
        return rtnval


class TerminalStream(io.StringIO):
    """
        A text stream that reports itself as a terminal.
    """

    def isatty(self) -> bool:
        return True


def run_pyc(
        *,
        sandbox: PycSandbox,
        argv: List[str],
        opener: Any = None,
        environ: Optional[Dict[str, str]] = None,
        stdin_text: str = "",
        openapi_fetcher: Optional[Callable[[], Dict]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        stdout: Optional[io.StringIO] = None
    ) -> Tuple[int, str, str]:
    """
        Run ``pyc`` in-process with the sandbox environment.

        :param sandbox: The sandbox.
        :param argv: Arguments after ``pyc``.
        :param opener: HTTP opener seam (a :class:`PycFakeServer`).
        :param environ: Extra environment variables.
        :param stdin_text: Standard input.
        :param openapi_fetcher: OpenAPI fetch seam.
        :param sleep: ``--wait`` sleep seam (default: no sleeping).
        :param stdout: Output stream (a :class:`TerminalStream` to
                       act like a terminal).

        :returns: ``(exit_code, stdout_text, stderr_text)``.
    """
    env = dict(sandbox.environ)
    env.update(environ or {})
    out = stdout if stdout is not None else io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=argv, stdout=out, stderr=err, stdin=io.StringIO(stdin_text),
        environ=env, request_opener=opener, openapi_fetcher=openapi_fetcher,
        sleep=sleep if sleep is not None else (lambda seconds: None),
    )
    result = (rtnval, out.getvalue(), err.getvalue())
    return result


__all__ = [
    "PycFakeServer",
    "PycSandbox",
    "SERVER",
    "TOKEN",
    "TerminalStream",
    "find_repository_root",
    "load_real_openapi_document",
    "run_pyc",
]
