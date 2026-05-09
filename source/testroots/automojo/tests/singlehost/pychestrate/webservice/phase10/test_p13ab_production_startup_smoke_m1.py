"""
.. module:: test_p13ab_production_startup_smoke_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Production startup smoke test --
               ``build_wsgi_application_for_production()`` end-to-end
               against an alembic-migrated SQLite DB.

.. moduleauthor:: Automation Mojo LLC

The phase-10 e2e modules (p13q / p13r / p13u / p13v) all run
against a *consumer-UI-only* slice of the production app:
they reuse the ``app_pychestrate_main.app`` persona singleton
but only register the three consumer-UI registrars
(``register_config_routes`` / ``register_resources_routes`` /
``register_projects_web_ui_routes``) and skip the REST API
half. That coverage is meaningful for the consumer surface
but it does NOT exercise:

* The 17 ``register_*_routes`` REST API registrars
  (``flags``, ``audit``, ``catalog``, ``channels``, ``auth``,
  ``templates``, ``secrets``, ``agents``, ``users``,
  ``tags``, ``retention``, ``variables``, ``clients``,
  ``rbac``, ``enrollment``, ``pods``, ``projects``).
* The phase-1..6 builtin extension registrations
  (``register_phase1_builtin_extensions`` through
  ``register_phase6_builtin_extensions``).
* ``mount_extension_routes`` from the extension router.
* ``build_and_validate_plugin_api_catalog``.
* The bus-subscriber wiring in ``Phase-2``  /
  ``Phase-3 bootstrap``.
* ``install_pychestrate_session_middleware``.

This module fills that gap with one test that boots the FULL
``build_wsgi_application_for_production()`` pipeline against
an alembic-migrated SQLite database in an isolated
subprocess, then drives a single HTTP probe at the resulting
WSGI app. If anything in the production import / registrar /
bus-subscriber / lifecycle chain breaks, this test surfaces
it.

Subprocess isolation is required because
``establish_webapp_persona`` is a process-global singleton
and the consumer-UI e2e tests have already established it in
the parent process. Forking gives the smoke test a clean
slate.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import subprocess
import sys
import tempfile
import textwrap

from automojo import testbase


def _repo_root() -> str:
    """
        Resolve the repo root from the test file location.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    rtnval = os.path.normpath(
        os.path.join(
            here, "..", "..", "..", "..", "..", "..", "..", "..",
        )
    )
    return rtnval


# The driver script the subprocess runs. It:
#
# * Sets up sys.path so the production app modules import
#   the same way ``alembic`` and ``run-website.sh`` do.
# * Calls ``build_wsgi_application_for_production()`` --
#   reads the env vars that the subprocess inherits.
# * Drives a single PEP-3333 environ at the resulting WSGI
#   app and prints the captured status line + a body excerpt.
#
# The harness asserts on the printed output rather than on
# the subprocess return code alone -- that way we can
# distinguish "import failed" from "200 / 500" from
# "lifecycle never reached INFRASTRUCTURE_READY".
_DRIVER_SCRIPT_TEMPLATE = textwrap.dedent('''\
    import io
    import os
    import sys
    import traceback

    REPO_ROOT = {repo_root!r}
    for component in ("source/site", "source/packages", "source/service"):
        full = os.path.join(REPO_ROOT, component)
        if full not in sys.path:
            sys.path.insert(0, full)

    try:
        from app_pychestrate_main import (
            build_wsgi_application_for_production,
        )
    except BaseException:
        print("STAGE: import-failed")
        traceback.print_exc()
        sys.exit(2)

    try:
        wsgi_app = build_wsgi_application_for_production()
    except BaseException:
        print("STAGE: bootstrap-failed")
        traceback.print_exc()
        sys.exit(3)

    print("STAGE: bootstrap-ok")

    # Drive one probe at the root URL. The hello-world handler
    # at "/" comes from app_pychestrate_main itself -- it doesn't
    # require auth or any DB query, so it's the simplest probe
    # of "the wsgi pipeline answers requests".
    captured = {{}}

    def _start_response(status, headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = headers

        def _writer(chunk):
            return None

        return _writer

    environ = {{
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/",
        "QUERY_STRING": "",
        "SERVER_NAME": "smoke.invalid",
        "SERVER_PORT": "80",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "SCRIPT_NAME": "",
        "wsgi.input": io.BytesIO(b""),
        "wsgi.errors": sys.stderr,
        "wsgi.url_scheme": "http",
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "wsgi.version": (1, 0),
        "CONTENT_LENGTH": "",
    }}

    try:
        chunks = list(wsgi_app(environ, _start_response))
    except BaseException:
        print("STAGE: probe-failed")
        traceback.print_exc()
        sys.exit(4)

    body = b"".join(c for c in chunks if c is not None and len(c) > 0)
    body_excerpt = body[:80].decode("utf-8", errors="replace")
    print("STAGE: probe-ok")
    print("STATUS: " + captured["status"])
    print("BODY_HEAD: " + body_excerpt.replace("\\n", " "))
    sys.exit(0)
''')


# ===========================================================================
# Tests
# ===========================================================================


def test_production_startup_completes_against_alembic_migrated_db():
    """
    **Feature: production startup smoke T18.1**
    **Property: ``build_wsgi_application_for_production()``
    completes end-to-end against a fresh SQLite database
    whose schema came from ``alembic upgrade head`` -- every
    REST + UI registrar imports cleanly, every Phase-1..6
    builtin extension registers cleanly, the lifecycle
    advances to ``INFRASTRUCTURE_READY``, and the resulting
    WSGI app answers a probe to ``GET /`` with a 2xx
    response.

    Runs the bootstrap in a subprocess so the production
    persona singleton stays isolated from the rest of the
    test suite.**
    """
    # Set up the per-run scratch state: tempfile DB + tempfile
    # KEK. Both get deleted at the end.
    db_fd, db_path = tempfile.mkstemp(
        prefix="pych-smoke-db-", suffix=".sqlite",
    )
    os.close(db_fd)
    try:
        os.unlink(db_path)
    except OSError:
        pass

    kek_fd, kek_path = tempfile.mkstemp(
        prefix="pych-smoke-kek-", suffix=".bin",
    )
    try:
        os.write(kek_fd, b"\x77" * 32)
    finally:
        os.close(kek_fd)

    repo_root = _repo_root()
    db_url = "sqlite:///" + db_path

    env = os.environ.copy()
    env["PYCHESTRATE_DATABASE_URL"] = db_url
    env["PYCHESTRATE_RUNTIME_ENVIRONMENT"] = "testing"
    env["PYCHESTRATE_AUTO_CREATE_SCHEMA"] = "false"
    env["PYCHESTRATE_KEK_SOURCE"] = "file"
    env["PYCHESTRATE_KEK_ID"] = "smoke-test-kek"
    env["PYCHESTRATE_KEK_FILE_PATH"] = kek_path
    # Pepper + UI cookie secret are optional in the bootstrap
    # config (the runtime tolerates them being unset).
    env.pop("PYCHESTRATE_PEPPER_SOURCE", None)
    env.pop("PYCHESTRATE_PEPPER_FILE_PATH", None)
    env.pop("PYCHESTRATE_PEPPER_ENV_VAR", None)
    env.pop("PYCHESTRATE_UI_COOKIE_SECRET_SOURCE", None)
    env.pop("PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH", None)
    env.pop("PYCHESTRATE_UI_COOKIE_SECRET_ENV_VAR", None)

    try:
        # Step 1: alembic upgrade head against the fresh DB.
        # Use the ``alembic`` console script rather than
        # ``python -m alembic`` -- the repo root contains an
        # ``alembic/`` migrations dir (configured in
        # alembic.ini), and ``-m alembic`` from repo root has
        # Python's namespace-package search resolve it to that
        # local dir, shadowing the installed library.
        alembic_script = os.path.join(
            os.path.dirname(sys.executable), "alembic"
        )
        upgrade_proc = subprocess.run(
            [alembic_script, "upgrade", "head"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
        )
        if upgrade_proc.returncode != 0:
            err_msg_lines = ["alembic upgrade head failed."]
            err_msg_lines.append("STDOUT:")
            err_msg_lines.append(upgrade_proc.stdout)
            err_msg_lines.append("STDERR:")
            err_msg_lines.append(upgrade_proc.stderr)
            err_msg = os.linesep.join(err_msg_lines)
            raise AssertionError(err_msg)

        # Step 2: drive the production startup in a subprocess.
        driver_script = _DRIVER_SCRIPT_TEMPLATE.format(
            repo_root=repo_root,
        )
        startup_proc = subprocess.run(
            [sys.executable, "-c", driver_script],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass
        try:
            os.unlink(kek_path)
        except OSError:
            pass

    # Step 3: assert on the subprocess output. Build a
    # diagnostic message that's useful in the failure case;
    # too many things can go wrong end-to-end and a bare
    # ``assert_equal(returncode, 0)`` doesn't help.
    err_msg_lines = []
    err_msg_lines.append(
        "production startup smoke failed."
    )
    err_msg_lines.append(
        "RETURNCODE: {}".format(startup_proc.returncode)
    )
    err_msg_lines.append("STDOUT:")
    err_msg_lines.append(startup_proc.stdout)
    err_msg_lines.append("STDERR:")
    err_msg_lines.append(startup_proc.stderr)
    err_msg = os.linesep.join(err_msg_lines)

    bootstrap_ok = "STAGE: bootstrap-ok" in startup_proc.stdout
    if bootstrap_ok is False:
        raise AssertionError(err_msg)
    probe_ok = "STAGE: probe-ok" in startup_proc.stdout
    if probe_ok is False:
        raise AssertionError(err_msg)

    # The hello-world handler returns a 200 with a small HTML
    # body. The status line should start with ``200``.
    status_line = ""
    for line in startup_proc.stdout.splitlines():
        if line.startswith("STATUS: "):
            status_line = line[len("STATUS: "):]
            break
    if not status_line.startswith("200"):
        err_msg_lines.append("FOUND_STATUS: {}".format(status_line))
        raise AssertionError(os.linesep.join(err_msg_lines))

    testbase.assert_equal(startup_proc.returncode, 0)
    return
