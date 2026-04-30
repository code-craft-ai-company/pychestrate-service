"""
.. module:: scripts.registerpod
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One-shot CLI that creates a project + pod + enrollment token.

.. moduleauthor:: Automation Mojo LLC

Hardware-onboarding helper. Drives a running pychestrate service via
HTTP to:

1. Look up the project by slug; create it when missing.
2. Register a pod-definition under the project (a single linux_host
   member by default; override via ``--member-kind`` /
   ``--hostname``).
3. Mint an enrollment token scoped to ``(project_id, pod_name)`` and
   print the secret + token id.

The agent on the target host then POSTs to
``/api/v1/enrollment-tokens/redeem`` with the secret + its host
metadata to receive a bearer token (and optionally a signed cert).

Example::

    PYCHESTRATE_BASE_URL=http://localhost:8080 \\
        PYCHESTRATE_SESSION_COOKIE=$(...) \\
        python scripts/registerpod.py \\
            --project-slug lab \\
            --pod-name raspi-01 \\
            --hostname raspi-01.lab.local
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import json
import os
import sys

from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen


BASE_URL_ENV_VAR = "PYCHESTRATE_BASE_URL"
SESSION_COOKIE_ENV_VAR = "PYCHESTRATE_SESSION_COOKIE"
SESSION_COOKIE_NAME = "pychestrate_session"
DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_TOKEN_TTL_SECONDS = 60 * 60


def _do(
        *,
        base_url: str,
        method: str,
        path: str,
        cookie: str,
        json_body: Optional[Any] = None,
    ) -> Tuple[int, bytes]:
    """
        Execute an HTTP request and return ``(status_code, body)``.
    """
    headers: Dict[str, str] = {
        "Cookie": "{0}={1}".format(SESSION_COOKIE_NAME, cookie),
    }
    body: Optional[bytes] = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = UrlRequest(
        url="{0}{1}".format(base_url, path),
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urlopen(request) as response:
            rtnval = (response.status, response.read())
            return rtnval
    except HTTPError as exc:
        rtnval = (exc.code, exc.read())
        return rtnval
    except URLError as exc:
        sys.stderr.write(
            "ERROR: cannot reach {0} ({1}){2}".format(
                base_url, exc, os.linesep,
            ),
        )
        raise SystemExit(2) from None


def _resolve_project_id(
        *,
        base_url: str,
        cookie: str,
        slug: str,
        display_name: str,
        description: str,
    ) -> str:
    """
        Look up the project by slug; create it when missing.
    """
    status, body = _do(
        base_url=base_url, method="GET",
        path="/api/v1/projects/{0}".format(slug),
        cookie=cookie,
    )
    if status == 200:
        project = json.loads(body.decode("utf-8"))
        sys.stdout.write(
            "Project '{0}' already exists ({1}){2}".format(
                slug, project["project_id"], os.linesep,
            ),
        )
        rtnval = project["project_id"]
        return rtnval
    if status != 404:
        sys.stderr.write(
            "ERROR: GET /api/v1/projects/{0} returned {1}: {2}{3}".format(
                slug, status, body[:240], os.linesep,
            ),
        )
        raise SystemExit(2)

    create_status, create_body = _do(
        base_url=base_url, method="POST", path="/api/v1/projects",
        cookie=cookie,
        json_body={
            "slug": slug,
            "display_name": display_name,
            "description": description,
        },
    )
    if create_status != 201:
        sys.stderr.write(
            "ERROR: POST /api/v1/projects returned {0}: {1}{2}".format(
                create_status, create_body[:240], os.linesep,
            ),
        )
        raise SystemExit(2)
    project = json.loads(create_body.decode("utf-8"))
    sys.stdout.write(
        "Created project '{0}' ({1}){2}".format(
            slug, project["project_id"], os.linesep,
        ),
    )
    rtnval = project["project_id"]
    return rtnval


def _register_pod_definition(
        *,
        base_url: str,
        cookie: str,
        project_id: str,
        pod_name: str,
        member_kind: str,
        hostname: str,
    ) -> str:
    """
        POST a minimal pod-definition. Returns the pod_id.
    """
    spec = {
        "members": [
            {"name": pod_name, "kind": member_kind, "hostname": hostname},
        ],
    }
    status, body = _do(
        base_url=base_url, method="POST",
        path="/api/v1/projects/{0}/pod-definitions".format(project_id),
        cookie=cookie,
        json_body={"pod_name": pod_name, "spec": spec},
    )
    if status not in (200, 201):
        sys.stderr.write(
            "ERROR: POST pod-definitions returned {0}: {1}{2}".format(
                status, body[:240], os.linesep,
            ),
        )
        raise SystemExit(2)
    definition = json.loads(body.decode("utf-8"))
    sys.stdout.write(
        "Registered pod definition '{0}' ({1}){2}".format(
            pod_name, definition["pod_id"], os.linesep,
        ),
    )
    rtnval = definition["pod_id"]
    return rtnval


def _mint_enrollment_token(
        *,
        base_url: str,
        cookie: str,
        project_id: str,
        pod_name: str,
        ttl_seconds: int,
        one_shot: bool,
    ) -> Dict[str, Any]:
    """
        Mint an enrollment token bound to ``(project_id, pod_name)``.
    """
    status, body = _do(
        base_url=base_url, method="POST",
        path="/api/v1/enrollment-tokens",
        cookie=cookie,
        json_body={
            "project_id": project_id,
            "pod_name": pod_name,
            "ttl_seconds": ttl_seconds,
            "one_shot": one_shot,
        },
    )
    if status != 201:
        sys.stderr.write(
            "ERROR: POST /api/v1/enrollment-tokens returned {0}: {1}{2}".format(
                status, body[:240], os.linesep,
            ),
        )
        raise SystemExit(2)
    rtnval = json.loads(body.decode("utf-8"))
    return rtnval


def main(*, argv: Optional[list] = None) -> int:
    """
        CLI entry point.
    """
    parser = argparse.ArgumentParser(
        description="Register a project + pod + enrollment token.",
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
        help=(
            "Admin session cookie value emitted by "
            "scripts/bootstrapadmin.py."
        ),
    )
    parser.add_argument("--project-slug", dest="project_slug", required=True)
    parser.add_argument(
        "--project-display-name", dest="project_display_name", default=None,
    )
    parser.add_argument(
        "--project-description",
        dest="project_description",
        default="Created by registerpod.py",
    )
    parser.add_argument("--pod-name", dest="pod_name", required=True)
    parser.add_argument(
        "--member-kind",
        dest="member_kind",
        default="linux_host",
        help="Pod member kind. Defaults to linux_host.",
    )
    parser.add_argument(
        "--hostname",
        dest="hostname",
        default=None,
        help="Hostname recorded on the pod member. Defaults to the pod name.",
    )
    parser.add_argument(
        "--ttl-seconds",
        dest="ttl_seconds",
        type=int,
        default=DEFAULT_TOKEN_TTL_SECONDS,
        help="Enrollment-token lifetime in seconds. Defaults to 1 hour.",
    )
    parser.add_argument(
        "--one-shot",
        dest="one_shot",
        action="store_true",
        default=True,
    )
    parser.add_argument(
        "--reusable",
        dest="one_shot",
        action="store_false",
        help="Allow the token to be redeemed multiple times.",
    )
    args = parser.parse_args(argv)

    if args.cookie is None or len(args.cookie) == 0:
        sys.stderr.write(
            "ERROR: session cookie not configured. Run "
            "scripts/bootstrapadmin.py first and pass --cookie or "
            "{0}.{1}".format(SESSION_COOKIE_ENV_VAR, os.linesep),
        )
        return 2

    project_display_name = args.project_display_name
    if project_display_name is None:
        project_display_name = args.project_slug.title()

    hostname = args.hostname
    if hostname is None:
        hostname = args.pod_name

    project_id = _resolve_project_id(
        base_url=args.base_url,
        cookie=args.cookie,
        slug=args.project_slug,
        display_name=project_display_name,
        description=args.project_description,
    )
    pod_id = _register_pod_definition(
        base_url=args.base_url,
        cookie=args.cookie,
        project_id=project_id,
        pod_name=args.pod_name,
        member_kind=args.member_kind,
        hostname=hostname,
    )
    issued = _mint_enrollment_token(
        base_url=args.base_url,
        cookie=args.cookie,
        project_id=project_id,
        pod_name=args.pod_name,
        ttl_seconds=args.ttl_seconds,
        one_shot=args.one_shot,
    )

    sys.stdout.write(
        "{0}Enrollment token minted.{0}".format(os.linesep),
    )
    sys.stdout.write(
        "  PROJECT_ID:   {0}{1}".format(project_id, os.linesep),
    )
    sys.stdout.write(
        "  POD_ID:       {0}{1}".format(pod_id, os.linesep),
    )
    sys.stdout.write(
        "  TOKEN_ID:     {0}{1}".format(issued["token_id"], os.linesep),
    )
    sys.stdout.write(
        "  POD_NAME:     {0}{1}".format(issued["pod_name"], os.linesep),
    )
    sys.stdout.write(
        "  EXPIRES_AT:   {0}{1}".format(issued["expires_at"], os.linesep),
    )
    sys.stdout.write(
        "  SECRET:       {0} (returned exactly once){1}".format(
            issued["secret"], os.linesep,
        ),
    )
    sys.stdout.write(
        "{0}Hand the SECRET + POD_NAME to the agent on the target host. "
        "The agent should POST to "
        "/api/v1/enrollment-tokens/redeem with that secret to obtain "
        "its bearer token.{1}".format(os.linesep, os.linesep),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
