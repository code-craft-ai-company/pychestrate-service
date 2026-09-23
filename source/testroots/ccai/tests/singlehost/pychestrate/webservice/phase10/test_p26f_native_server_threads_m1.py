"""
.. module:: test_p26f_native_server_threads_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The built-in server started by ``make dev-up`` /
               ``make serve-prod`` serves requests on a thread pool
               (LD-01).

.. moduleauthor:: Code Craft AI LLC

``pychestrate_website_main`` called webworks ``run_server`` without a
``worker_class``; webworks defaults to ``"sync"`` and only builds a
thread pool for ``"thread"``, so the server handled one connection at a
time and every asset waited out the previous connection's 2 s
keep-alive (10-13 s per page). ``PYCHESTRATE_THREADS`` had no effect.

The test boots ``pychestrate_website_main`` in a subprocess with
``run_server`` replaced by a recorder (no socket is opened) and checks
the arguments the server would have been started with.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

from typing import Any, Dict, Optional

from ccai import testbase


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    rtnval = os.path.normpath(os.path.join(here, "..", "..", "..", "..", "..", "..", "..", ".."))
    return rtnval


_DRIVER_SCRIPT = textwrap.dedent('''\
    import json
    import os
    import sys

    REPO_ROOT = {repo_root!r}
    for component in ("source/site", "source/packages"):
        full = os.path.join(REPO_ROOT, component)
        if full not in sys.path:
            sys.path.insert(0, full)

    import app_pychestrate_main

    captured = {{}}

    def _record_run_server(**kwargs):
        captured.update({{name: value for name, value in kwargs.items() if name != "app"}})

    app_pychestrate_main.run_server = _record_run_server
    app_pychestrate_main.pychestrate_website_main()
    print("RUN_SERVER: " + json.dumps(captured, sort_keys=True))
''')


def _run_server_arguments(*, threads: Optional[str]) -> Dict[str, Any]:
    """
        Run ``pychestrate_website_main`` with ``run_server`` recorded.

        :param threads: Value for ``PYCHESTRATE_THREADS`` or ``None`` to
                        leave it unset.

        :returns: The keyword arguments ``run_server`` received.
    """
    workdir = tempfile.mkdtemp(prefix="pyc-p26f-")
    try:
        kek_path = os.path.join(workdir, "kek")
        with open(kek_path, "wb") as handle:
            handle.write(b"\x2f" * 32)
        # The KEK loader refuses a key file others can read.
        os.chmod(kek_path, 0o600)
        env = os.environ.copy()
        for name in list(env):
            if name.startswith("PYCHESTRATE_"):
                env.pop(name)
        env.update({
            "PYCHESTRATE_RUNTIME_ENVIRONMENT": "testing",
            "PYCHESTRATE_AUTO_CREATE_SCHEMA": "true",
            "PYCHESTRATE_DATABASE_URL": "sqlite:///" + os.path.join(workdir, "native.sqlite"),
            "PYCHESTRATE_PRESENCE_DIR": workdir,
            "PYCHESTRATE_KEK_SOURCE": "file",
            "PYCHESTRATE_KEK_ID": "p26f-kek",
            "PYCHESTRATE_KEK_FILE_PATH": kek_path,
            "PYCHESTRATE_BIND_HOST": "127.0.0.1",
            "PYCHESTRATE_BIND_PORT": "8999",
        })
        if threads is not None:
            env["PYCHESTRATE_THREADS"] = threads
        process = subprocess.run(
            [sys.executable, "-c", _DRIVER_SCRIPT.format(repo_root=_repo_root())],
            cwd=_repo_root(), env=env, capture_output=True, text=True, timeout=300,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    for line in process.stdout.splitlines():
        if line.startswith("RUN_SERVER: "):
            rtnval = json.loads(line[len("RUN_SERVER: "):])
            return rtnval
    raise AssertionError("run_server was not reached; stderr tail:\n{}".format(process.stderr[-3000:]))


def test_native_server_defaults_to_a_thread_pool():
    """
    **Feature: local server concurrency (LD-01)**
    **Property: with PYCHESTRATE_THREADS unset the built-in server is
    started with worker_class="thread" and 8 threads, so a page's assets
    load in parallel and a pod long-poll holds only one thread.**
    """
    arguments = _run_server_arguments(threads=None)
    testbase.assert_equal(
        (arguments.get("worker_class"), arguments.get("threads")),
        ("thread", 8),
    )
    return


def test_native_server_honours_pychestrate_threads():
    """
    **Feature: local server concurrency (LD-01)**
    **Property: PYCHESTRATE_THREADS sets the thread-pool size (it had no
    effect before).**
    """
    arguments = _run_server_arguments(threads="4")
    testbase.assert_equal(
        (arguments.get("worker_class"), arguments.get("threads")),
        ("thread", 4),
    )
    return
