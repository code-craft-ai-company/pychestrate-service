"""
.. module:: test_p31zzl_setup_signs_in_first_admin_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The setup wizard signs the new administrator in (XC-08).

.. moduleauthor:: Code Craft AI LLC

The last step of the setup wizard created the administrator and sent them to
the sign-in page to type the password they had just chosen. It now signs them
in, through the ordinary sign-in path (``SecurityManager.authenticate``, so
the audit trail and lockout accounting see it), and sends them to the home
page. When the credentials are not accepted for any reason the wizard falls
back to the sign-in page. One test walks the whole wizard against a fresh
database in a subprocess (the process-global app persona cannot be booted
twice); the others call the sign-in helper in process, with a right and a
wrong password.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import ast
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

from typing import Any, Dict, List, Optional

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.foundation import cookie_session
from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from ccai.pychestrate.webservice.webinterface.blueprints.config import routes as config_routes

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    ensure_seeded_admin,
)


ADMIN_PASSWORD: str = "Wizard-Pass-9271-xQ!"


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    rtnval = os.path.normpath(os.path.join(here, "..", "..", "..", "..", "..", "..", "..", ".."))
    return rtnval


# ---------------------------------------------------------------------------
# The whole wizard, in a subprocess against a fresh database
# ---------------------------------------------------------------------------

_WIZARD_DRIVER = textwrap.dedent('''\
    import io
    import os
    import sys
    import traceback
    import urllib.parse
    from http.cookies import SimpleCookie

    REPO_ROOT = {repo_root!r}
    for component in ("source/site", "source/packages", "source/service"):
        full = os.path.join(REPO_ROOT, component)
        if full not in sys.path:
            sys.path.insert(0, full)

    try:
        from app_pychestrate_main import build_wsgi_application_for_production
        wsgi_app = build_wsgi_application_for_production()
    except BaseException:
        print("STAGE: bootstrap-failed")
        traceback.print_exc()
        sys.exit(3)

    with open(os.path.join(os.environ["PYCHESTRATE_PRESENCE_DIR"], "initial-admin-token")) as handle:
        token = handle.read().strip()

    jar = {{}}

    def call(method, path, form=None):
        body = urllib.parse.urlencode(form).encode("ascii") if form is not None else b""
        captured = {{}}

        def _start_response(status, headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = headers
            return lambda chunk: None

        environ = {{
            "REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": "",
            "SERVER_NAME": "wizard.invalid", "SERVER_PORT": "8888", "SERVER_PROTOCOL": "HTTP/1.1",
            "SCRIPT_NAME": "", "REMOTE_ADDR": "127.0.0.1",
            "CONTENT_TYPE": "application/x-www-form-urlencoded", "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body), "wsgi.errors": sys.stderr, "wsgi.url_scheme": "http",
            "wsgi.multithread": False, "wsgi.multiprocess": False, "wsgi.run_once": False,
            "wsgi.version": (1, 0),
        }}
        if len(jar) > 0:
            environ["HTTP_COOKIE"] = "; ".join("{{}}={{}}".format(k, v) for k, v in jar.items() if v != "")
        chunks = list(wsgi_app(environ, _start_response))
        location = ""
        for name, value in captured["headers"]:
            if name.lower() == "location":
                location = value
            if name.lower() == "set-cookie":
                parsed = SimpleCookie()
                parsed.load(value)
                for cookie_name, morsel in parsed.items():
                    jar[cookie_name] = morsel.value
        text = b"".join(chunks).decode("utf-8", "replace")
        return int(captured["status"].split()[0]), location, text

    try:
        print("HOME_BEFORE", call("GET", "/"))
        print("UNLOCK", call("POST", "/setup/unlock", {{"token": token}}))
        print("ADMIN", call("POST", "/setup/admin", {{
            "login_name": "first-admin", "email": "first.admin@example.test", "display_name": "First Admin",
            "password": {password!r}, "password_confirm": {password!r},
        }}))
        print("HOME_AFTER", call("GET", "/"))
        print("ADMIN_AGAIN", call("POST", "/setup/admin", {{
            "login_name": "second-admin", "email": "second.admin@example.test", "display_name": "Second",
            "password": {password!r}, "password_confirm": {password!r},
        }}))
    except BaseException:
        print("STAGE: drive-failed")
        traceback.print_exc()
        sys.exit(4)
    print("STAGE: done")
    sys.exit(0)
''')


_WIZARD_OUTPUT: Optional[Dict[str, Any]] = None
_WIZARD_STDERR: str = ""


def _wizard_walk() -> Dict[str, Any]:
    """Walk the wizard once (cached): the (status, location) of each step."""
    global _WIZARD_OUTPUT, _WIZARD_STDERR
    if _WIZARD_OUTPUT is not None:
        return _WIZARD_OUTPUT

    workdir = tempfile.mkdtemp(prefix="pych-wizard-")
    db_path = os.path.join(workdir, "wizard.sqlite")
    kek_path = os.path.join(workdir, "kek.bin")
    presence_dir = os.path.join(workdir, "presence")
    os.makedirs(presence_dir, mode=0o700)
    with open(kek_path, "wb") as kek_file:
        kek_file.write(b"\x66" * 32)
    os.chmod(kek_path, 0o600)
    pepper_path = os.path.join(workdir, "pepper.bin")
    cookie_secret_path = os.path.join(workdir, "ui-cookie-secret.bin")
    for secret_path, material in ((pepper_path, b"\x55" * 32), (cookie_secret_path, b"\x44" * 32)):
        with open(secret_path, "wb") as secret_file:
            secret_file.write(material)
        os.chmod(secret_path, 0o600)

    repo_root = _repo_root()
    env = os.environ.copy()
    env["PYCHESTRATE_DATABASE_URL"] = "sqlite:///" + db_path
    env["PYCHESTRATE_RUNTIME_ENVIRONMENT"] = "testing"
    env["PYCHESTRATE_AUTO_CREATE_SCHEMA"] = "false"
    env["PYCHESTRATE_KEK_SOURCE"] = "file"
    env["PYCHESTRATE_KEK_ID"] = "wizard-kek"
    env["PYCHESTRATE_KEK_FILE_PATH"] = kek_path
    env["PYCHESTRATE_PRESENCE_DIR"] = presence_dir
    env["PYCHESTRATE_PASSWORD_PEPPER_SOURCE"] = "file"
    env["PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH"] = pepper_path
    env["PYCHESTRATE_UI_COOKIE_SECRET_SOURCE"] = "file"
    env["PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH"] = cookie_secret_path
    env.pop("PYCHESTRATE_TRUSTED_PROXY_ADDRESSES", None)

    try:
        alembic_script = os.path.join(os.path.dirname(sys.executable), "alembic")
        upgrade = subprocess.run([alembic_script, "upgrade", "head"], cwd=repo_root, env=env, capture_output=True, text=True)
        if upgrade.returncode != 0:
            raise AssertionError("alembic upgrade head failed:\n{}{}".format(upgrade.stdout, upgrade.stderr))
        driver = subprocess.run(
            [sys.executable, "-c", _WIZARD_DRIVER.format(repo_root=repo_root, password=ADMIN_PASSWORD)],
            cwd=repo_root, env=env, capture_output=True, text=True, timeout=240,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    _WIZARD_STDERR = driver.stderr
    if "STAGE: done" not in driver.stdout:
        raise AssertionError("wizard driver failed (rc={}):\nSTDOUT:\n{}\nSTDERR:\n{}".format(
            driver.returncode, driver.stdout, driver.stderr[-3000:]))

    steps: Dict[str, Any] = {}
    for line in driver.stdout.splitlines():
        for name in ("HOME_BEFORE", "UNLOCK", "ADMIN", "HOME_AFTER", "ADMIN_AGAIN"):
            if line.startswith(name + " "):
                steps[name] = ast.literal_eval(line[len(name) + 1:])  # a printed (status, location, body) tuple
    _WIZARD_OUTPUT = steps
    return _WIZARD_OUTPUT


def test_finishing_the_wizard_signs_the_new_administrator_in():
    """
    **Feature: sign in after setup (XC-08)**
    **Property: on a fresh database, before setup the home page sends a visitor
    to the wizard; finishing the wizard answers 303 to ``/`` (not to
    ``/login``); the home page then opens for the new administrator (200)
    with the cookie the wizard set; and a second submit of the wizard is
    refused (404) and signs nobody in.**
    """
    steps = _wizard_walk()

    testbase.assert_equal(
        (
            steps["HOME_BEFORE"][1].endswith("/setup/unlock"),
            steps["UNLOCK"][0],
            steps["ADMIN"][:2],
            steps["HOME_AFTER"][0],
            steps["ADMIN_AGAIN"][0],
        ),
        (True, 303, (303, "/"), 200, 404),
    )
    return


# ---------------------------------------------------------------------------
# The helper, in process
# ---------------------------------------------------------------------------


class _FakeRequest:
    """The parts of a request the sign-in path reads; the client address is optional there."""

    def __init__(self) -> None:
        self.headers: Dict[str, str] = {"User-Agent": "wizard-test"}
        self.cookies: Dict[str, str] = {}
        self.path: str = "/setup/admin"
        self.query_string: str = ""


def _session_cookie_payload(response: Any) -> Dict[str, Any]:
    secret = SITE_SHARED_GLOBALS.UI_COOKIE_SECRET
    for name, value in response._get_all_headers():
        if name.lower() != "set-cookie":
            continue
        cookie_name, _, rest = value.partition("=")
        if cookie_name == cookie_session.COOKIE_NAME:
            payload = cookie_session.verify_session_payload(cookie_value=rest.split(";", 1)[0], secret=secret)
            return payload or {}
    return {}


def test_the_helper_signs_in_with_the_right_password_and_sets_a_real_session():
    """
    **Feature: sign in after setup (XC-08)**
    **Property: with the right login and password the helper answers 303 to
    ``/`` and sets a signed session that names the user and carries the
    session token and a CSRF token, as ``POST /login`` does.**
    """
    handle = ensure_app()
    admin = ensure_seeded_admin()
    response = config_routes.sign_in_after_setup(request=_FakeRequest(), username=admin.login, password=admin.password)
    payload = _session_cookie_payload(response) if response is not None else {}

    testbase.assert_equal(
        (
            response.status_code if response is not None else None,
            response._headers.get("Location") if response is not None else None,
            payload.get("user_id") == admin.user_id,
            len(str(payload.get("session_token", ""))) > 0,
            len(str(payload.get("csrf_token", payload.get("_csrf", "")))) > 0 or any("csrf" in key for key in payload),
        ),
        (303, "/", True, True, True),
    )
    return


def test_the_helper_signs_nobody_in_with_the_wrong_password_or_an_unknown_login():
    """
    **Feature: sign in after setup (XC-08)**
    **Property: a wrong password or an unknown login gives ``None``, so the
    wizard falls back to the sign-in page and no session is created.**
    """
    handle = ensure_app()
    admin = ensure_seeded_admin()

    wrong_password = config_routes.sign_in_after_setup(request=_FakeRequest(), username=admin.login, password=admin.password + "x")
    unknown = config_routes.sign_in_after_setup(request=_FakeRequest(), username="nobody-here", password=admin.password)

    testbase.assert_equal((wrong_password, unknown), (None, None))
    return
