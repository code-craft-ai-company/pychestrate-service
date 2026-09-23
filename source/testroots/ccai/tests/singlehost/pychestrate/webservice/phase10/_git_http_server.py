"""
.. module:: tests.singlehost.pychestrate.webservice.phase10._git_http_server
    :platform: Darwin, Linux, Unix
    :synopsis: A Git repository served over HTTP on 127.0.0.1 --
               private (basic authentication) or public -- for
               repository credential and watch tests.

.. moduleauthor:: Code Craft AI LLC

:class:`PrivateGitServer` creates a bare repository with one commit on
``main`` and serves it with ``git http-backend`` (smart HTTP, so
``git ls-remote`` works), by default behind basic authentication. Every
request's ``Authorization`` header is recorded, so a test can tell
whether the client sent credentials at all and which. Its ``commit``,
``create_branch`` and ``tag`` methods change the repository the way a
push would.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import os
import shutil
import subprocess
import tempfile
import threading

from contextlib import contextmanager

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator, List, Optional, Tuple


#: Name of the repository directory under the server root.
REPOSITORY_DIR_NAME: str = "private.git"


@contextmanager
def isolated_git_config() -> Iterator[None]:
    """
        Keep the developer's own git configuration (credential helpers,
        URL rewrites) out of the git commands the app runs while the
        block executes.
    """
    saved = {key: os.environ.get(key) for key in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return


def _isolated_git_env() -> dict:
    """
        The environment for the server's own git commands: no system or
        global configuration (signing, hooks, default branch) applies.
    """
    rtnval = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return rtnval


def _run_git(*, args: List[str], cwd: Optional[str] = None) -> str:
    completed = subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=60, check=True,
        env=_isolated_git_env(),
    )
    return completed.stdout.strip()


def _parse_cgi_output(*, output: bytes) -> Tuple[int, List[Tuple[str, str]], bytes]:
    """
        Split a CGI response into status, headers and body.
    """
    separator = b"\r\n\r\n" if b"\r\n\r\n" in output else b"\n\n"
    head, _, body = output.partition(separator)
    status = 200
    headers: List[Tuple[str, str]] = []
    for raw_line in head.splitlines():
        line = raw_line.decode("latin-1").strip()
        if len(line) == 0:
            continue
        name, _, value = line.partition(":")
        if name.lower() == "status":
            status = int(value.strip().split()[0])
        else:
            headers.append((name.strip(), value.strip()))
    rtnval = (status, headers, body)
    return rtnval


class PrivateGitServer:
    """
        A bare repository behind basic authentication (or, with
        ``require_auth=False``, a public one). :meth:`commit`,
        :meth:`create_branch` and :meth:`tag` change it the way a push
        would.

        :param username: The user name the server accepts.
        :param password: The password (token) the server accepts.
        :param port: Port to bind on 127.0.0.1 (0 picks a free one).
        :param require_auth: False serves the repository to anyone.
    """

    def __init__(
            self, *, username: str = "x-access-token", password: str = "",
            port: int = 0, require_auth: bool = True
        ) -> None:
        self.username: str = username
        self.password: str = password
        self.require_auth: bool = require_auth
        self.authorizations: List[str] = []
        self.root: str = tempfile.mkdtemp(prefix="pyc-git-http-")
        self.head_sha: str = self._create_repository()

        server = self

        class _Handler(BaseHTTPRequestHandler):
            def _handle(self) -> None:
                server._serve(handler=self)
                return

            do_GET = _handle
            do_POST = _handle

            def log_message(self, *args: Any) -> None:
                return

        self._httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return

    @property
    def url(self) -> str:
        rtnval = "http://127.0.0.1:{}/{}".format(self._httpd.server_address[1], REPOSITORY_DIR_NAME)
        return rtnval

    def _create_repository(self) -> str:
        work = os.path.join(self.root, "work")
        os.makedirs(work)
        _run_git(args=["init", "-q", "-b", "main", work], cwd=self.root)
        with open(os.path.join(work, "README.md"), "w") as readme:
            readme.write("private\n")
        _run_git(args=["add", "README.md"], cwd=work)
        _run_git(
            args=["-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                  "commit", "-q", "-m", "Initial commit"],
            cwd=work,
        )
        _run_git(
            args=["clone", "-q", "--bare", work, os.path.join(self.root, REPOSITORY_DIR_NAME)],
            cwd=self.root,
        )
        rtnval = _run_git(args=["rev-parse", "HEAD"], cwd=work)
        return rtnval

    def _push(self, *, refspec: str) -> None:
        work = os.path.join(self.root, "work")
        _run_git(
            args=["push", "-q", os.path.join(self.root, REPOSITORY_DIR_NAME), refspec],
            cwd=work,
        )
        return

    def commit(self, *, branch: str = "main", message: str = "Change") -> str:
        """
            Commit a change on ``branch`` (which must exist) and push it.

            :returns: The new commit's SHA.
        """
        work = os.path.join(self.root, "work")
        _run_git(args=["checkout", "-q", branch], cwd=work)
        with open(os.path.join(work, "CHANGES.txt"), "a") as changes:
            changes.write(message + "\n")
        _run_git(args=["add", "CHANGES.txt"], cwd=work)
        _run_git(
            args=["-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                  "commit", "-q", "-m", message],
            cwd=work,
        )
        self._push(refspec="{0}:refs/heads/{0}".format(branch))
        rtnval = _run_git(args=["rev-parse", "HEAD"], cwd=work)
        if branch == "main":
            self.head_sha = rtnval
        return rtnval

    def create_branch(self, *, name: str, start: str = "main") -> str:
        """
            Create branch ``name`` at ``start`` and push it.

            :returns: The commit the branch points at.
        """
        work = os.path.join(self.root, "work")
        _run_git(args=["branch", name, start], cwd=work)
        self._push(refspec="{0}:refs/heads/{0}".format(name))
        rtnval = _run_git(args=["rev-parse", name], cwd=work)
        return rtnval

    def tag(self, *, name: str, target: str = "main") -> str:
        """
            Create the annotated tag ``name`` on ``target`` and push it.

            :returns: The commit the tag points at.
        """
        work = os.path.join(self.root, "work")
        _run_git(
            args=["-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                  "tag", "-a", "-m", name, name, target],
            cwd=work,
        )
        self._push(refspec="refs/tags/{0}:refs/tags/{0}".format(name))
        rtnval = _run_git(args=["rev-parse", target], cwd=work)
        return rtnval

    def _expected_authorization(self) -> str:
        pair = "{}:{}".format(self.username, self.password).encode("utf-8")
        rtnval = "Basic " + base64.b64encode(pair).decode("ascii")
        return rtnval

    def _serve(self, *, handler: BaseHTTPRequestHandler) -> None:
        authorization = handler.headers.get("Authorization", "") or ""
        self.authorizations.append(authorization)
        if self.require_auth is True and authorization != self._expected_authorization():
            handler.send_response(401)
            handler.send_header("WWW-Authenticate", 'Basic realm="private"')
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return

        path, _, query = handler.path.partition("?")
        length = int(handler.headers.get("Content-Length") or 0)
        body = handler.rfile.read(length) if length > 0 else b""
        env = {
            "PATH": os.environ.get("PATH", ""),
            "GIT_PROJECT_ROOT": self.root,
            "GIT_HTTP_EXPORT_ALL": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "REQUEST_METHOD": handler.command,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_TYPE": handler.headers.get("Content-Type", "") or "",
            "CONTENT_LENGTH": str(length),
            "REMOTE_USER": self.username,
            "REMOTE_ADDR": "127.0.0.1",
            "GIT_PROTOCOL": handler.headers.get("Git-Protocol", "") or "",
            "HTTP_CONTENT_ENCODING": handler.headers.get("Content-Encoding", "") or "",
        }
        completed = subprocess.run(
            ["git", "http-backend"], input=body, env=env, capture_output=True, timeout=60,
        )
        status, headers, payload = _parse_cgi_output(output=completed.stdout)
        handler.send_response(status)
        for name, value in headers:
            handler.send_header(name, value)
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)
        return

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        shutil.rmtree(self.root, ignore_errors=True)
        return


__all__ = [
    "REPOSITORY_DIR_NAME",
    "PrivateGitServer",
    "isolated_git_config",
]
