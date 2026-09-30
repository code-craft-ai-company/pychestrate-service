"""
.. module:: test_p32b_deployment_readme_generic_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``deployment/README.md`` is a guide anyone can follow (DOC-12).

.. moduleauthor:: Code Craft AI LLC

The deployment guide was written from the maintainer's own machine: 48
references to their host and user name, two step 7s in the table of what the
deploy does, a service said to run under both tmux and systemd, a
made-up authentication scheme ("API-key REST"), an admin token that looked
real, and a database path that disagreed with the script. It now uses
``HOST``, ``USER`` and ``PUBLIC_HOSTNAME`` placeholders, numbers the steps once,
says the service runs under systemd, and matches the script. This test keeps it
that way.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import List

from ccai import testbase


def _repo_root() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "deployment")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return current


def _readme() -> str:
    with open(os.path.join(_repo_root(), "deployment", "README.md"), encoding="utf-8") as handle:
        return handle.read()


def test_the_readme_names_no_one_machine_and_makes_no_false_claim():
    """
    **Feature: a generic deployment guide (DOC-12)**
    **Property: the README contains none of the maintainer's host names or
    account name, no certificate CN taken from a real setup, no "API-key" scheme
    the product does not have, no /config/login address, and no token-looking
    string in an example.**
    """
    text = _readme()
    banned = ["myron", "tc-app-server", "tailb75ce6", "worker-1", "API-key", "/config/login"]
    found = [word for word in banned if word in text]
    long_words = re.findall(r"(?<![A-Za-z0-9_./-])[A-Za-z0-9_-]{40,}(?![A-Za-z0-9_./-])", text)
    # a random token mixes upper and lower case; a metric name such as pychestrate_backup_last_success_timestamp_seconds does not
    token_like = [word for word in long_words if re.search(r"[A-Z]", word) and re.search(r"[a-z]", word)]

    testbase.assert_equal((found, token_like), ([], []))
    return


def test_the_step_table_numbers_each_step_once_and_the_service_runs_under_systemd():
    """
    **Feature: a generic deployment guide (DOC-12)**
    **Property: the "What runs on the remote" table lists steps 1 to 9 once
    each and in order (the script has eight steps and a probe), the README
    never says the service runs under tmux, and it puts the database where the
    script does (~/pychestrate/pychestrate.sqlite).**
    """
    text = _readme()
    section = text.split("### What runs on the remote", 1)[1].split("###", 1)[0]
    numbers: List[int] = [int(match) for match in re.findall(r"^\| (\d+) \|", section, re.M)]
    says_tmux_runs_it = re.search(r"runs under `?tmux|in tmux|tmux session", text, re.I) is not None

    testbase.assert_equal(
        (numbers, says_tmux_runs_it, "~/pychestrate/pychestrate.sqlite" in text, ".cache/dev-db" in text),
        (list(range(1, 10)), False, True, False),
    )
    return


def test_the_readme_says_what_its_placeholders_mean():
    """
    **Feature: a generic deployment guide (DOC-12)**
    **Property: the README explains HOST, USER and PUBLIC_HOSTNAME once near
    the top, and uses each in its examples.**
    """
    text = _readme()
    top = text[:1600]

    testbase.assert_equal(
        ([name for name in ("HOST", "USER", "PUBLIC_HOSTNAME") if "`{}`".format(name) in top], "ssh USER@HOST" in text, "--public-hostname PUBLIC_HOSTNAME" in text),
        (["HOST", "USER", "PUBLIC_HOSTNAME"], True, True),
    )
    return
