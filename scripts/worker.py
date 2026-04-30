"""
.. module:: scripts.worker
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Standalone agent for ``remote-machine`` workers.

.. moduleauthor:: Automation Mojo LLC

Run this script on a Raspberry Pi / UEFI host / VM that pychestrate
should treat as a worker. It:

1. (Optionally) redeems an enrollment-token secret via
   ``POST /api/v1/enrollment-tokens/redeem`` to obtain a bearer token,
   when ``--redeem-secret`` is supplied.
2. Self-registers with the service via
   ``POST /api/v1/workers/register`` using the bearer token.
3. Loops:

   * POST ``/api/v1/workers/{worker_id}/jobs/poll`` to claim the
     next job;
   * runs the command via ``subprocess.run`` with the job's
     ``timeout_seconds`` (default 300);
   * POST ``/api/v1/workers/{worker_id}/jobs/{job_id}/result``
     with stdout / stderr / exit code;
   * heartbeats on ``--heartbeat-interval`` so the registry
     sees the worker as live.

4. On SIGTERM / SIGINT or after a single ``--drain`` pass, exits
   cleanly. Setting ``--deregister-on-exit`` deletes the
   :class:`Worker` row outright; otherwise the row is left behind
   (useful when the host is expected to come back).

Bearer token sources, in priority order:

* ``--bearer-token`` CLI arg.
* ``PYCHESTRATE_WORKER_BEARER_TOKEN`` env var.
* ``--redeem-secret`` (or ``PYCHESTRATE_WORKER_REDEEM_SECRET``) +
  the redeem flow.

Example::

    PYCHESTRATE_BASE_URL=https://pychestrate.lab.local \\
        PYCHESTRATE_WORKER_REDEEM_SECRET=ek_... \\
        python scripts/worker.py \\
            --pod-name raspi-01 \\
            --worker-name raspi-01 \\
            --heartbeat-interval 30
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time

from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen


BASE_URL_ENV_VAR = "PYCHESTRATE_BASE_URL"
BEARER_TOKEN_ENV_VAR = "PYCHESTRATE_WORKER_BEARER_TOKEN"
REDEEM_SECRET_ENV_VAR = "PYCHESTRATE_WORKER_REDEEM_SECRET"
DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_COMMAND_TIMEOUT_SECONDS = 300.0


class WorkerAgentError(Exception):
    """
        Raised when the agent encounters an unrecoverable error
        (auth failure, missing required arg, server returns 5xx
        repeatedly, etc.).
    """
    pass


def _do_request(
        *,
        base_url: str,
        method: str,
        path: str,
        bearer_token: Optional[str],
        json_body: Optional[Any] = None,
        timeout_seconds: float = 30.0,
    ) -> Tuple[int, bytes]:
    """
        Execute one HTTP request and return ``(status_code, body)``.

        :returns: status code and raw response body bytes.
    """
    headers: Dict[str, str] = {}
    if bearer_token is not None and len(bearer_token) > 0:
        headers["Authorization"] = "Bearer {0}".format(bearer_token)
    body_bytes: Optional[bytes] = None
    if json_body is not None:
        body_bytes = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = UrlRequest(
        url="{0}{1}".format(base_url, path),
        data=body_bytes,
        method=method,
        headers=headers,
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status_code = int(response.getcode())
            response_body = response.read()
            return status_code, response_body
    except HTTPError as http_exc:
        status_code = int(http_exc.code)
        response_body = http_exc.read()
        return status_code, response_body
    except URLError as url_exc:
        err_lines = [
            "Worker agent network error.",
            "URL: {0}{1}".format(base_url, path),
            "REASON: {0}".format(url_exc.reason),
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerAgentError(err_msg) from url_exc


def _decode_json_response(*, body: bytes) -> Dict[str, Any]:
    if body is None or len(body) == 0:
        return {}
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(decoded, dict):
        return {}
    rtnval = decoded
    return rtnval


def redeem_bearer_token(
        *,
        base_url: str,
        secret: str,
        pod_name: str,
        agent_version: Optional[str] = None,
        extras: Optional[Dict[str, Any]] = None,
    ) -> str:
    """
        Exchange an enrollment-token secret for a bearer token.

        :raises WorkerAgentError: When the redeem call fails.
    """
    payload: Dict[str, Any] = {
        "secret": secret,
        "pod_name": pod_name,
    }
    if agent_version is not None:
        payload["agent_version"] = agent_version
    if extras is not None:
        payload["extras"] = extras
    status_code, body = _do_request(
        base_url=base_url,
        method="POST",
        path="/api/v1/enrollment-tokens/redeem",
        bearer_token=None,
        json_body=payload,
    )
    if status_code != 200:
        decoded = _decode_json_response(body=body)
        err_lines = [
            "Enrollment-token redeem failed.",
            "STATUS: {0}".format(status_code),
            "DETAIL: {0}".format(decoded.get("detail", body[:200])),
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerAgentError(err_msg) from None
    decoded = _decode_json_response(body=body)
    bearer = decoded.get("bearer_token", None)
    if bearer is None or len(bearer) == 0:
        err_lines = [
            "Enrollment-token redeem succeeded but no bearer_token in response.",
            "BODY: {0}".format(body[:200]),
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerAgentError(err_msg) from None
    rtnval = str(bearer)
    return rtnval


def register_worker(
        *,
        base_url: str,
        bearer_token: str,
        worker_name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> str:
    """
        Register a ``remote-machine`` worker. Returns ``worker_id``.

        :raises WorkerAgentError: On non-2xx response.
    """
    payload: Dict[str, Any] = {
        "name": worker_name,
        "kind": "remote-machine",
    }
    if attributes is not None:
        payload["attributes"] = attributes
    status_code, body = _do_request(
        base_url=base_url,
        method="POST",
        path="/api/v1/workers/register",
        bearer_token=bearer_token,
        json_body=payload,
    )
    if status_code == 409:
        # Already registered for this principal — adopt the row.
        decoded = _decode_json_response(body=body)
        if "worker_id" in decoded:
            rtnval = str(decoded["worker_id"])
            return rtnval
    if status_code != 201:
        decoded = _decode_json_response(body=body)
        err_lines = [
            "Worker register failed.",
            "STATUS: {0}".format(status_code),
            "DETAIL: {0}".format(decoded.get("detail", body[:200])),
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerAgentError(err_msg) from None
    decoded = _decode_json_response(body=body)
    worker_id = decoded.get("worker_id", None)
    if worker_id is None:
        err_lines = [
            "Worker register response missing worker_id.",
            "BODY: {0}".format(body[:200]),
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerAgentError(err_msg) from None
    rtnval = str(worker_id)
    return rtnval


def heartbeat(
        *,
        base_url: str,
        bearer_token: str,
        worker_id: str,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
    """
        Heartbeat the worker, optionally setting status. Returns
        the worker view dict.
    """
    payload: Dict[str, Any] = {}
    if status is not None:
        payload["status"] = status
    if len(payload) == 0:
        body_arg: Optional[Dict[str, Any]] = None
    else:
        body_arg = payload
    status_code, body = _do_request(
        base_url=base_url,
        method="POST",
        path="/api/v1/workers/{0}/heartbeat".format(worker_id),
        bearer_token=bearer_token,
        json_body=body_arg,
    )
    if status_code != 200:
        return {}
    rtnval = _decode_json_response(body=body)
    return rtnval


def poll_next_job(
        *,
        base_url: str,
        bearer_token: str,
        worker_id: str,
    ) -> Optional[Dict[str, Any]]:
    """
        Ask the service for the next job. Returns the job dict or
        ``None`` when the queue had nothing.
    """
    status_code, body = _do_request(
        base_url=base_url,
        method="POST",
        path="/api/v1/workers/{0}/jobs/poll".format(worker_id),
        bearer_token=bearer_token,
        json_body=None,
    )
    if status_code != 200:
        return None
    decoded = _decode_json_response(body=body)
    job = decoded.get("job", None)
    if job is None:
        return None
    if not isinstance(job, dict):
        return None
    rtnval = job
    return rtnval


def report_result(
        *,
        base_url: str,
        bearer_token: str,
        worker_id: str,
        job_id: str,
        result_code: int,
        stdout: str,
        stderr: str,
        error_text: Optional[str],
    ) -> bool:
    """
        Submit a result for a claimed job. Returns ``True`` on
        success.
    """
    payload: Dict[str, Any] = {
        "result_code": int(result_code),
        "stdout": stdout if stdout is not None else "",
        "stderr": stderr if stderr is not None else "",
    }
    if error_text is not None:
        payload["error_text"] = error_text
    status_code, _body = _do_request(
        base_url=base_url,
        method="POST",
        path="/api/v1/workers/{0}/jobs/{1}/result".format(
            worker_id, job_id,
        ),
        bearer_token=bearer_token,
        json_body=payload,
    )
    rtnval = status_code == 200
    return rtnval


def deregister_worker(
        *,
        base_url: str,
        bearer_token: str,
        worker_id: str,
    ) -> bool:
    """
        Best-effort removal of the worker row. Returns ``True``
        when the service confirmed.
    """
    status_code, _body = _do_request(
        base_url=base_url,
        method="DELETE",
        path="/api/v1/workers/{0}".format(worker_id),
        bearer_token=bearer_token,
    )
    rtnval = status_code in (200, 204, 404)
    return rtnval


def _execute_job_command(
        *,
        command: str,
        timeout_seconds: float,
    ) -> Tuple[int, str, str, Optional[str]]:
    """
        Run ``command`` via subprocess and return
        ``(result_code, stdout, stderr, error_text)``.
    """
    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        if exc.stdout is None:
            stdout_value = ""
        else:
            if isinstance(exc.stdout, bytes):
                stdout_value = exc.stdout.decode(
                    "utf-8", errors="replace",
                )
            else:
                stdout_value = exc.stdout
        if exc.stderr is None:
            stderr_value = ""
        else:
            if isinstance(exc.stderr, bytes):
                stderr_value = exc.stderr.decode(
                    "utf-8", errors="replace",
                )
            else:
                stderr_value = exc.stderr
        error_text = "command timed out after {0:.1f}s".format(
            timeout_seconds,
        )
        return 1, stdout_value, stderr_value, error_text
    except Exception as exc:
        return 1, "", "", "subprocess crashed: {0}".format(exc)
    rtnval = (
        int(completed.returncode),
        completed.stdout if completed.stdout is not None else "",
        completed.stderr if completed.stderr is not None else "",
        None,
    )
    return rtnval


class WorkerAgent:
    """
        The long-running agent loop.
    """

    def __init__(
            self,
            *,
            base_url: str,
            bearer_token: str,
            worker_id: str,
            poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
            heartbeat_interval_seconds: float = (
                DEFAULT_HEARTBEAT_INTERVAL_SECONDS
            ),
            default_command_timeout_seconds: float = (
                DEFAULT_COMMAND_TIMEOUT_SECONDS
            ),
            log_writer=None,
        ):
        self._base_url: str = base_url
        self._bearer_token: str = bearer_token
        self._worker_id: str = worker_id
        self._poll_interval_seconds: float = poll_interval_seconds
        self._heartbeat_interval_seconds: float = (
            heartbeat_interval_seconds
        )
        self._default_command_timeout_seconds: float = (
            default_command_timeout_seconds
        )
        if log_writer is None:
            self._log_writer = sys.stdout
        else:
            self._log_writer = log_writer
        self._stop_event: threading.Event = threading.Event()
        self._last_heartbeat_at: float = 0.0
        return

    @property
    def worker_id(self) -> str:
        rtnval = self._worker_id
        return rtnval

    def request_stop(self) -> None:
        """
            Signal the loop to exit at the next iteration.
        """
        self._stop_event.set()
        return

    def run(self, *, drain_after_one: bool = False) -> int:
        """
            Run the agent loop until ``request_stop`` is called or
            the registry marks the row DRAINING.

            :param drain_after_one: When True, exit after handling
                                    a single job (or one empty
                                    poll). Useful for ``--drain``.

            :returns: 0 on clean exit; 1 on fatal error.
        """
        self._log("worker.start worker_id={0}".format(self._worker_id))
        try:
            while self._stop_event.is_set() is False:
                stop_now = self._tick()
                if stop_now is True:
                    break
                if drain_after_one is True:
                    break
        except WorkerAgentError as exc:
            self._log("worker.fatal {0}".format(exc))
            return 1
        self._log("worker.stop worker_id={0}".format(self._worker_id))
        return 0

    def _tick(self) -> bool:
        """
            One iteration. Returns ``True`` when the worker should
            exit (registry says DRAINING).
        """
        now = time.time()
        if now - self._last_heartbeat_at >= self._heartbeat_interval_seconds:
            view = heartbeat(
                base_url=self._base_url,
                bearer_token=self._bearer_token,
                worker_id=self._worker_id,
                status=None,
            )
            self._last_heartbeat_at = now
            if view.get("status", None) == "draining":
                self._log("worker.draining_observed")
                return True

        job = poll_next_job(
            base_url=self._base_url,
            bearer_token=self._bearer_token,
            worker_id=self._worker_id,
        )
        if job is None:
            self._stop_event.wait(self._poll_interval_seconds)
            return False

        kind = job.get("kind", "")
        job_id = job.get("job_id", "")
        if kind != "run-command":
            report_result(
                base_url=self._base_url,
                bearer_token=self._bearer_token,
                worker_id=self._worker_id,
                job_id=job_id,
                result_code=1,
                stdout="",
                stderr="",
                error_text="unsupported job kind: {0}".format(kind),
            )
            return False

        payload = job.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        command_raw = payload.get("command", None)
        if command_raw is None or len(str(command_raw)) == 0:
            report_result(
                base_url=self._base_url,
                bearer_token=self._bearer_token,
                worker_id=self._worker_id,
                job_id=job_id,
                result_code=1,
                stdout="",
                stderr="",
                error_text="missing 'command' in job payload",
            )
            return False
        timeout_raw = payload.get(
            "timeout_seconds", self._default_command_timeout_seconds,
        )
        try:
            timeout_value = float(timeout_raw)
        except (TypeError, ValueError):
            timeout_value = self._default_command_timeout_seconds

        self._log(
            "worker.job.start job_id={0} command={1}".format(
                job_id, command_raw,
            ),
        )
        result_code, stdout_value, stderr_value, err_text = (
            _execute_job_command(
                command=str(command_raw),
                timeout_seconds=timeout_value,
            )
        )
        report_result(
            base_url=self._base_url,
            bearer_token=self._bearer_token,
            worker_id=self._worker_id,
            job_id=job_id,
            result_code=result_code,
            stdout=stdout_value,
            stderr=stderr_value,
            error_text=err_text,
        )
        self._log(
            "worker.job.done job_id={0} rc={1}".format(
                job_id, result_code,
            ),
        )
        return False

    def _log(self, line: str) -> None:
        timestamp = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.gmtime(),
        )
        text = "[{0}] {1}\n".format(timestamp, line)
        self._log_writer.write(text)
        self._log_writer.flush()
        return


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Standalone agent for a remote-machine pychestrate worker."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get(BASE_URL_ENV_VAR, DEFAULT_BASE_URL),
        help=(
            "Pychestrate service base URL. Defaults to "
            "$PYCHESTRATE_BASE_URL or {0}.".format(DEFAULT_BASE_URL)
        ),
    )
    parser.add_argument(
        "--bearer-token",
        default=os.environ.get(BEARER_TOKEN_ENV_VAR, None),
        help=(
            "Bearer token for the Authorization header. Falls back "
            "to $PYCHESTRATE_WORKER_BEARER_TOKEN, then to redeeming "
            "--redeem-secret."
        ),
    )
    parser.add_argument(
        "--redeem-secret",
        default=os.environ.get(REDEEM_SECRET_ENV_VAR, None),
        help=(
            "Enrollment-token secret to redeem for a bearer token. "
            "Falls back to $PYCHESTRATE_WORKER_REDEEM_SECRET. "
            "Ignored when --bearer-token is provided."
        ),
    )
    parser.add_argument(
        "--pod-name",
        default=socket.gethostname(),
        help=(
            "Pod-name claimed during redeem. Defaults to the host's "
            "hostname."
        ),
    )
    parser.add_argument(
        "--worker-name",
        default=None,
        help=(
            "Worker name to register. Defaults to --pod-name."
        ),
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Seconds between empty polls.",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        help="Seconds between heartbeats.",
    )
    parser.add_argument(
        "--command-timeout",
        type=float,
        default=DEFAULT_COMMAND_TIMEOUT_SECONDS,
        help="Default subprocess timeout when a job omits one.",
    )
    parser.add_argument(
        "--drain",
        action="store_true",
        help=(
            "Run a single iteration and exit (one job, or one empty "
            "poll). Useful for cron-driven testing."
        ),
    )
    parser.add_argument(
        "--deregister-on-exit",
        action="store_true",
        help="DELETE the worker row when the agent shuts down.",
    )
    parser.add_argument(
        "--agent-version",
        default="pychestrate-worker/0.0.1",
        help="agent_version reported during enrollment redeem.",
    )
    return parser


def _resolve_bearer_token(*, args: argparse.Namespace) -> str:
    if args.bearer_token is not None and len(args.bearer_token) > 0:
        rtnval = args.bearer_token
        return rtnval
    if args.redeem_secret is None or len(args.redeem_secret) == 0:
        err_lines = [
            "Worker agent requires either --bearer-token or",
            "--redeem-secret (or the corresponding env vars).",
        ]
        err_msg = os.linesep.join(err_lines)
        raise WorkerAgentError(err_msg)
    rtnval = redeem_bearer_token(
        base_url=args.base_url,
        secret=args.redeem_secret,
        pod_name=args.pod_name,
        agent_version=args.agent_version,
        extras={
            "host": socket.gethostname(),
            "platform": sys.platform,
        },
    )
    return rtnval


def _resolve_worker_name(*, args: argparse.Namespace) -> str:
    if args.worker_name is not None and len(args.worker_name) > 0:
        rtnval = args.worker_name
        return rtnval
    rtnval = args.pod_name
    return rtnval


def main(*, argv: Optional[list] = None) -> int:
    """
        CLI entry point.

        :param argv: Optional override for ``sys.argv[1:]``; tests
                     supply this directly.
        :returns: Process exit code.
    """
    parser = _build_argument_parser()
    args = parser.parse_args(argv)

    try:
        bearer_token = _resolve_bearer_token(args=args)
    except WorkerAgentError as exc:
        sys.stderr.write("{0}\n".format(exc))
        return 2

    worker_name = _resolve_worker_name(args=args)

    try:
        worker_id = register_worker(
            base_url=args.base_url,
            bearer_token=bearer_token,
            worker_name=worker_name,
            attributes={
                "host": socket.gethostname(),
                "platform": sys.platform,
                "pod_name": args.pod_name,
            },
        )
    except WorkerAgentError as exc:
        sys.stderr.write("{0}\n".format(exc))
        return 2

    agent = WorkerAgent(
        base_url=args.base_url,
        bearer_token=bearer_token,
        worker_id=worker_id,
        poll_interval_seconds=args.poll_interval,
        heartbeat_interval_seconds=args.heartbeat_interval,
        default_command_timeout_seconds=args.command_timeout,
    )

    def _on_signal(signum, _frame):
        sys.stderr.write(
            "worker.signal received={0}\n".format(signum),
        )
        agent.request_stop()
        return

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    exit_code = agent.run(drain_after_one=args.drain)

    if args.deregister_on_exit is True:
        deregister_worker(
            base_url=args.base_url,
            bearer_token=bearer_token,
            worker_id=worker_id,
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
