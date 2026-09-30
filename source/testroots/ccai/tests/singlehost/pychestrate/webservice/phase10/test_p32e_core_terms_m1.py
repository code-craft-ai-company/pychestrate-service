"""
.. module:: test_p32e_core_terms_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One meaning per core term, defined in the glossary (ORG-F21).

.. moduleauthor:: Code Craft AI LLC

The audit found the same word doing different jobs: "agent" for the pod client
(the client's own README says never), "Release Channels" in the sidebar for
Pychestrate's own updates while a project has release channels of its own,
"environment" for a deployment target, a set of variables and the service's
runtime mode, and "reservation" sometimes for the check-out itself. The
glossary defines the terms and the interface uses one word for each. These tests
keep the definitions in the glossary and the word "agent" out of what people
read in the interface.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import glob
import os
import re

from typing import Dict, List

from ccai import testbase

import ccai.pychestrate.webservice.webinterface as webinterface_package


def _repo_root() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "userguide")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return current


def _glossary() -> str:
    with open(os.path.join(_repo_root(), "userguide", "18-00-ui-glossary.rst"), encoding="utf-8") as handle:
        return handle.read()


def test_the_glossary_defines_the_terms_that_had_several_meanings():
    """
    **Feature: one meaning per core term (ORG-F21)**
    **Property: the glossary defines Pod / Client, Pychestrate updates and
    Environment, says the client is never called an agent, tells a project's
    release channels from Pychestrate's own, and says a reservation is never the
    check-out itself.**
    """
    text = " ".join(_glossary().split())
    needed = [
        "``Pod`` / ``Client``",
        "never *agent*",
        "``Pychestrate updates``",
        "A project's own releases and channels are a different thing",
        "``Environment``",
        "*environment variables*",
        "*runtime environment*",
        "A reservation is a future-dated claim on a resource",
        "is never itself the check-out",
    ]

    testbase.assert_equal([phrase for phrase in needed if phrase not in text], [])
    return


def test_the_interface_never_calls_the_pod_client_an_agent():
    """
    **Feature: one meaning per core term (ORG-F21)**
    **Property: no bundle view or server-rendered template says "agent" or
    "agents" (the API resource names agent-rollouts and the release component
    agent-runtime, which are identifiers, are not prose and are not matched; a line
    carrying the marker ``// api-value`` is an API identifier sent as it is, and is
    skipped).**
    """
    root = os.path.dirname(os.path.abspath(webinterface_package.__file__))
    paths: List[str] = []
    for bundle in glob.glob(os.path.join(root, "static", "javascript", "pyc-*-bundle")):
        paths.extend(path for path in glob.glob(os.path.join(bundle, "*.js")) if os.path.basename(path) != "index.js")
    paths.extend(glob.glob(os.path.join(root, "static", "javascript", "shared", "*.js")))
    paths.extend(glob.glob(os.path.join(root, "blueprints", "**", "*.html"), recursive=True))
    paths.extend(glob.glob(os.path.join(root, "site_shell", "**", "*.html"), recursive=True))
    found: Dict[str, List[int]] = {}
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if re.search(r"\b[Aa]gents?\b(?![-_])", line) and "user-agent" not in line.lower() and "// api-value" not in line:
                    found.setdefault(os.path.relpath(path, root), []).append(number)

    testbase.assert_equal((len(paths) > 100, found), (True, {}))
    return
