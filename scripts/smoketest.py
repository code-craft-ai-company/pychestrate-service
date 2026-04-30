"""
.. module:: scripts.smoketest
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: HTTP smoke test that exercises the running pychestrate service.

.. moduleauthor:: Automation Mojo LLC

Drives a small set of REST endpoints against a running pychestrate
service to confirm the wiring is correct end-to-end. Designed to be
run after :mod:`scripts.bootstrapadmin` has produced a session cookie.

Usage::

    PYCHESTRATE_BASE_URL=http://localhost:8080 \\
        PYCHESTRATE_SESSION_COOKIE=<session-id from bootstrapadmin> \\
        python scripts/smoketest.py

Exits 0 when every step passes, 1 on the first failure.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import json
import os
import sys
import time

from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


BASE_URL_ENV_VAR = "PYCHESTRATE_BASE_URL"
SESSION_COOKIE_ENV_VAR = "PYCHESTRATE_SESSION_COOKIE"
SESSION_COOKIE_NAME = "pychestrate_session"
DEFAULT_BASE_URL = "http://localhost:8080"


def _build_request(
        *,
        base_url: str,
        method: str,
        path: str,
        cookie: Optional[str],
        json_body: Optional[Any] = None,
        yaml_body: Optional[str] = None,
    ) -> Request:
    """
        Build an :class:`urllib.request.Request` for ``method path``
        on the configured service.
    """
    url = "{0}{1}".format(base_url, path)
    headers: Dict[str, str] = {}
    if cookie is not None:
        if len(cookie) > 0:
            headers["Cookie"] = "{0}={1}".format(SESSION_COOKIE_NAME, cookie)
    body: Optional[bytes] = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif yaml_body is not None:
        body = yaml_body.encode("utf-8")
        headers["Content-Type"] = "application/yaml"
    rtnval = Request(url=url, data=body, method=method, headers=headers)
    return rtnval


def _do(
        *,
        base_url: str,
        method: str,
        path: str,
        cookie: Optional[str],
        json_body: Optional[Any] = None,
        yaml_body: Optional[str] = None,
    ) -> Tuple[int, bytes]:
    """
        Execute a single HTTP request and return ``(status, body)``.

        :raises SystemExit: When the server is unreachable.
    """
    request = _build_request(
        base_url=base_url, method=method, path=path, cookie=cookie,
        json_body=json_body, yaml_body=yaml_body,
    )
    try:
        with urlopen(request) as response:
            status = response.status
            body = response.read()
    except HTTPError as exc:
        status = exc.code
        body = exc.read()
    except URLError as exc:
        sys.stderr.write(
            "ERROR: cannot reach {0} ({1}){2}".format(
                base_url, exc, os.linesep,
            ),
        )
        raise SystemExit(2) from None
    rtnval = (status, body)
    return rtnval


def _step(
        *,
        label: str,
        status: int,
        expected: Tuple[int, ...],
        body: bytes,
    ) -> bool:
    """
        Report a step's result to stdout. Returns True on success.
    """
    if status in expected:
        sys.stdout.write(
            "PASS  [{0}] {1}{2}".format(status, label, os.linesep),
        )
        return True
    sys.stdout.write(
        "FAIL  [{0}] {1}{2}".format(status, label, os.linesep),
    )
    sys.stdout.write(
        "      body: {0}{1}".format(
            body.decode("utf-8", errors="replace")[:240],
            os.linesep,
        ),
    )
    return False


def _smoke_workflow_yaml() -> str:
    """
        Return a one-task taskplus workflow that runs ``echo``.
    """
    rtnval = (
        "name: smoke\n"
        "environment: {}\n"
        "parameters: {}\n"
        "flow:\n"
        "  - task: noop\n"
        "    tasktype: automojo.taskplus.tasks.runcommand@RunCommand\n"
        "    command: echo smoketest\n"
    )
    return rtnval


def main(*, argv: Optional[list] = None) -> int:
    """
        CLI entry point.
    """
    parser = argparse.ArgumentParser(
        description="HTTP smoke test for the pychestrate service.",
    )
    parser.add_argument(
        "--base-url",
        dest="base_url",
        default=os.environ.get(BASE_URL_ENV_VAR, DEFAULT_BASE_URL),
    )
    parser.add_argument(
        "--cookie",
        dest="cookie",
        default=os.environ.get(SESSION_COOKIE_ENV_VAR, ""),
        help="Session cookie value emitted by scripts/bootstrapadmin.py.",
    )
    parser.add_argument(
        "--skip-flow",
        dest="skip_flow",
        action="store_true",
        help="Skip the flow submission step (faster).",
    )
    args = parser.parse_args(argv)

    sys.stdout.write(
        "Smoke target: {0}{1}".format(args.base_url, os.linesep),
    )

    all_pass = True

    # 1. RBAC permissions — registry-only, anonymous OK
    status, body = _do(
        base_url=args.base_url, method="GET",
        path="/api/v1/rbac/permissions", cookie=None,
    )
    all_pass = _step(
        label="GET /api/v1/rbac/permissions (anonymous)",
        status=status, expected=(200,), body=body,
    ) and all_pass

    # 2. Same with cookie attached — should still 200
    if args.cookie:
        status, body = _do(
            base_url=args.base_url, method="GET",
            path="/api/v1/rbac/permissions", cookie=args.cookie,
        )
        all_pass = _step(
            label="GET /api/v1/rbac/permissions (with cookie)",
            status=status, expected=(200,), body=body,
        ) and all_pass

    # 3. Project create — needs DB
    project_slug = "smoke-{0}".format(int(time.time()))
    status, body = _do(
        base_url=args.base_url, method="POST", path="/api/v1/projects",
        cookie=args.cookie,
        json_body={
            "slug": project_slug,
            "display_name": "Smoke",
            "description": "smoketest project",
        },
    )
    all_pass = _step(
        label="POST /api/v1/projects",
        status=status, expected=(201,), body=body,
    ) and all_pass

    if not args.skip_flow:
        # 4. Flow submission
        status, body = _do(
            base_url=args.base_url, method="POST", path="/api/v1/flows",
            cookie=args.cookie,
            yaml_body=_smoke_workflow_yaml(),
        )
        all_pass = _step(
            label="POST /api/v1/flows",
            status=status, expected=(202,), body=body,
        ) and all_pass

        if status == 202:
            decoded = json.loads(body.decode("utf-8"))
            flow_id = decoded["flow_id"]

            # 5. Poll until terminal
            terminal_state: Optional[str] = None
            deadline = time.time() + 10.0
            poll_status = 0
            poll_body = b""
            while time.time() < deadline:
                poll_status, poll_body = _do(
                    base_url=args.base_url, method="GET",
                    path="/api/v1/flows/{0}".format(flow_id),
                    cookie=args.cookie,
                )
                if poll_status != 200:
                    break
                state = json.loads(poll_body.decode("utf-8"))["state"]
                if state in ("SUCCEEDED", "FAILED"):
                    terminal_state = state
                    break
                time.sleep(0.1)

            all_pass = _step(
                label="GET /api/v1/flows/{id} terminal=SUCCEEDED",
                status=200 if terminal_state == "SUCCEEDED" else poll_status,
                expected=(200,), body=poll_body,
            ) and all_pass and (terminal_state == "SUCCEEDED")

    if all_pass is True:
        sys.stdout.write(
            "{0}All smoke steps passed.{0}".format(os.linesep),
        )
        return 0
    sys.stdout.write(
        "{0}One or more smoke steps FAILED.{0}".format(os.linesep),
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
