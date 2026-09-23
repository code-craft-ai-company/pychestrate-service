"""
.. module:: cli.commands.runs
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc runs wait`` and ``--wait``: block until a run
               finishes and exit with its result.

.. moduleauthor:: Code Craft AI LLC

A CI step triggers a run and must fail when the run fails::

    pyc test-runs trigger <project_id> --data @run.json --wait
    pyc runs wait <run_id> [--wait-timeout 3600] [--interval 5]

Both poll ``GET /api/v1/runs/{run_id}``, print a line on stderr at
every state change, print the final run on stdout (in the ``--output``
format: a table on a terminal, JSON otherwise), and exit:

* ``0``  -- the run completed successfully;
* ``10`` -- it finished any other way (failed, cancelled, dispatch
  failed / lost) or needs investigation;
* ``11`` -- it had not finished when the timeout expired.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import time

from typing import Any, Dict, Optional, Sequence

from ccai.pychestrate.cli import exit_codes, transport
from ccai.pychestrate.cli.argparsing import CliArgumentParser
from ccai.pychestrate.cli.context import CliContext
from ccai.pychestrate.cli.exceptions import RunFailedError, WaitTimeoutError
from ccai.pychestrate.cli.models import CliProfile, RestOperation


RUN_READ_PATH: str = "/api/v1/runs/{run_id}"

#: States the server treats as final.
TERMINAL_STATES = ("completed", "failed", "cancelled", "dispatch_failed", "dispatch_lost")

#: A state no run leaves without a person acting; waiting on it would
#: only run into the timeout.
STUCK_STATES = ("needs_investigation",)

SUCCESS_OUTCOME: str = "success"


def _run_operation() -> RestOperation:
    """
        ``GET /api/v1/runs/{run_id}``.

        :returns: :class:`RestOperation`.
    """
    rtnval = RestOperation(
        operation_id="runs_get_by_id",
        method="GET",
        path_template=RUN_READ_PATH,
        path_param_names=("run_id",),
        required_path_param_names=("run_id",),
    )
    return rtnval


def wait_for_run(
        *,
        ctx: CliContext,
        profile: CliProfile,
        run_id: str,
        timeout_seconds: float,
        interval_seconds: float
    ) -> int:
    """
        Poll a run until it finishes.

        :param ctx: Invocation context.
        :param profile: Active profile.
        :param run_id: Run id.
        :param timeout_seconds: Give up after this long.
        :param interval_seconds: Poll interval.

        :returns: :data:`exit_codes.EXIT_OK` when the run succeeded.
        :raises: RunFailedError, WaitTimeoutError (and transport errors)
    """
    sleep = ctx.sleep if ctx.sleep is not None else time.sleep
    started = ctx.now()
    last_state: Optional[str] = None
    run: Dict[str, Any] = {}

    while True:
        response = transport.execute_request(
            profile=profile,
            operation=_run_operation(),
            path_params={"run_id": run_id},
            query_params={},
            body=None,
            idempotency_key=None,
            timeout_seconds=None,
            opener=ctx.request_opener,
        )
        run = response.body if isinstance(response.body, dict) else {}
        state = str(run.get("state", "") or "")
        if state != last_state:
            ctx.stderr.write("run {}: {}\n".format(run_id, state or "(no state)"))
            last_state = state

        if state in TERMINAL_STATES or state in STUCK_STATES:
            ctx.emit_result(value=run, raw_text=response.raw_text, identifier_fields=("run_id",))
            outcome = str(run.get("terminal_outcome", "") or "")
            if state == "completed" and outcome in ("", SUCCESS_OUTCOME):
                rtnval = exit_codes.EXIT_OK
                return rtnval
            raise RunFailedError(
                "run {} finished as {}{}".format(
                    run_id, state, " ({})".format(outcome) if len(outcome) > 0 else ""
                )
            )

        elapsed = (ctx.now() - started).total_seconds()
        if elapsed >= timeout_seconds:
            ctx.emit_result(value=run, raw_text=response.raw_text, identifier_fields=("run_id",))
            raise WaitTimeoutError(
                "run {} was still {} after {:g}s".format(run_id, state or "unknown", timeout_seconds)
            )
        sleep(max(0.0, min(interval_seconds, timeout_seconds - elapsed)))


def run_runs_wait(*, ctx: CliContext, profile_resolver, args: Sequence[str]) -> int:
    """
        ``pyc runs wait <run_id> [--wait-timeout S] [--interval S]``
        (``--timeout`` stays the global per-request timeout).

        :param ctx: Invocation context.
        :param profile_resolver: Zero-arg callable returning the
                                 active profile.
        :param args: Arguments after ``runs wait``.

        :returns: Exit code.
    """
    command_parser = CliArgumentParser(
        prog="pyc runs wait",
        description=(
            "Wait for a run to finish. Exit 0 when it completed successfully,\n"
            "10 when it finished any other way, 11 when --wait-timeout expired."
        ),
        out_stream=ctx.stdout,
        err_stream=ctx.stderr,
    )
    command_parser.add_argument("run_id", help="the run to wait for")
    command_parser.add_argument(
        "--wait-timeout", dest="wait_timeout", type=float, default=3600.0, metavar="SECONDS",
        help="give up after this long (default 3600)",
    )
    command_parser.add_argument(
        "--interval", type=float, default=5.0, metavar="SECONDS",
        help="poll interval (default 5)",
    )
    namespace = command_parser.parse_args(list(args))
    profile = profile_resolver()
    rtnval = wait_for_run(
        ctx=ctx,
        profile=profile,
        run_id=namespace.run_id,
        timeout_seconds=namespace.wait_timeout,
        interval_seconds=namespace.interval,
    )
    return rtnval


__all__ = [
    "STUCK_STATES",
    "TERMINAL_STATES",
    "run_runs_wait",
    "wait_for_run",
]
