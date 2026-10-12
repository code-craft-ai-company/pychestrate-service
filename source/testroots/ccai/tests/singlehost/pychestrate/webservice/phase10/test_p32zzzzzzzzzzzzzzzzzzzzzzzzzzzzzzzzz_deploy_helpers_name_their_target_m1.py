"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_deploy_helpers_name_their_target_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The deployment helper scripts and the deploy workflow name no particular host (DOC-12).

.. moduleauthor:: Code Craft AI LLC

``deploy-alpha-to-host.sh`` stopped defaulting to the maintainers' host earlier; ``renew-cert.sh``, ``install-deploy-sudoers.sh`` and
``bootstrap-client-ca.sh`` and the ``deploy`` workflow still did, so someone who left a flag out renewed a certificate on, or installed
sudo rules on, a machine that was not theirs to touch. Each now requires its target, stops before any ``ssh`` call when one is missing, and
accepts both ``--flag=value`` and ``--flag value``.

Nothing here reaches the network: the scripts run from the repository with a stub ``ssh`` first on ``PATH`` that logs its arguments and
fails.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import shutil
import subprocess
import tempfile

from pathlib import Path
from typing import List, Tuple

from ccai import testbase

from ccai.testshared.factories.pyc.pyc_harness import find_repository_root
from ccai.testshared.skip_helper import skip_test


HELPERS = ("renew-cert.sh", "install-deploy-sudoers.sh", "bootstrap-client-ca.sh")

MAINTAINER_NAMES = ("tc-app-server", "tailb75ce6", "myron")

#: Logs its arguments and fails, like an unreachable host.
STUB = "#!/bin/sh\nprintf '%s %s\\n' \"$(basename \"$0\")\" \"$*\" >> \"$STUB_LOG\"\nexit 255\n"


class _Sandbox:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="pyc-helpers-"))
        self.stubs = self.root / "stubs"
        self.stubs.mkdir()
        for tool in ("ssh", "scp", "sudo", "curl"):
            stub = self.stubs / tool
            stub.write_text(STUB, encoding="utf-8")
            os.chmod(str(stub), 0o755)
        self.log = self.root / "calls.log"
        return

    def run(self, script: str, *args: str) -> subprocess.CompletedProcess:
        bash = shutil.which("bash")
        if bash is None:
            skip_test(reason="bash is not installed")
        environment = {
            "PATH": str(self.stubs) + os.pathsep + "/usr/bin" + os.pathsep + "/bin",
            "HOME": str(self.root), "STUB_LOG": str(self.log), "LC_ALL": "C",
        }
        return subprocess.run(
            [str(bash), str(find_repository_root() / "deployment" / script), *args],
            env=environment, capture_output=True, text=True, timeout=60, check=False,
        )

    def calls(self) -> List[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def close(self) -> None:
        shutil.rmtree(str(self.root), ignore_errors=True)
        return


def test_a_missing_target_stops_before_any_ssh_call():
    """
    **Feature: deployment helpers (DOC-12)**
    **Property: each helper run with no arguments, or with a target left out, exits 1 with a message naming the flags, and made no ssh, scp
    or sudo call.**
    """
    sandbox = _Sandbox()
    try:
        outcomes: List[Tuple[int, bool]] = []
        for script, args in (
            ("renew-cert.sh", ()),
            ("renew-cert.sh", ("--host=app", "--user=deploy")),
            ("install-deploy-sudoers.sh", ()),
            ("install-deploy-sudoers.sh", ("--host", "app", "--public-hostname", "app.example.ts.net")),
            ("bootstrap-client-ca.sh", ()),
            ("bootstrap-client-ca.sh", ("--host=app",)),
        ):
            completed = sandbox.run(script, *args)
            outcomes.append((completed.returncode, "required" in completed.stderr and "--host" in completed.stderr))
        calls = sandbox.calls()
    finally:
        sandbox.close()

    testbase.assert_equal((outcomes, calls), ([(1, True)] * 6, []))
    return


def test_both_flag_forms_are_read_and_a_valueless_flag_is_refused():
    """
    **Feature: deployment helpers (DOC-12)**
    **Property: '--host=H --user=U' and '--host H --user U' both name the target (the scripts reach their ssh pre-flight or banner for
    deploy@app.example.test), and a flag with no value stops with "needs a value".**
    """
    sandbox = _Sandbox()
    try:
        equals = sandbox.run("renew-cert.sh", "--host=app.example.test", "--user=deploy", "--public-hostname=app.example.ts.net")
        spaced = sandbox.run("renew-cert.sh", "--host", "app.example.test", "--user", "deploy", "--public-hostname", "app.example.ts.net")
        banner = sandbox.run("bootstrap-client-ca.sh", "--host", "app.example.test", "--user", "deploy")
        valueless = sandbox.run("renew-cert.sh", "--host")
    finally:
        sandbox.close()

    testbase.assert_equal(
        (
            equals.returncode, "deploy@app.example.test" in equals.stderr,
            spaced.returncode, "deploy@app.example.test" in spaced.stderr,
            "deploy@app.example.test" in banner.stdout,
            valueless.returncode, "needs a value" in valueless.stderr,
        ),
        (2, True, 2, True, True, 1, True),
    )
    return


def test_help_and_the_files_name_no_particular_host():
    """
    **Feature: deployment helpers (DOC-12)**
    **Property: the three helpers (their text and ``--help``) and the deploy workflow contain none of the maintainers' host, tailnet or
    account names, and the workflow's ``target_host`` and ``target_user`` inputs have no default.**
    """
    root = find_repository_root()
    sandbox = _Sandbox()
    try:
        helps = [sandbox.run(script, "--help").stdout for script in HELPERS]
    finally:
        sandbox.close()
    texts = [(root / "deployment" / script).read_text(encoding="utf-8") for script in HELPERS] + helps
    workflow = (root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    texts.append(workflow)
    found = sorted({name for name in MAINTAINER_NAMES for text in texts if name in text})

    host_block = workflow.split("target_host:", 1)[1].split("target_port:", 1)[0]
    testbase.assert_equal((found, "default:" in host_block, all("HOST" in text or "host" in text for text in helps)), ([], False, True))
    return
