"""
.. module:: test_platform_startup_logging_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Regression locks for the startup lines reaching the log
               (audit LD-11).

.. moduleauthor:: Code Craft AI LLC

When stdout is a file (systemd ``StandardOutput=append:``, ``nohup ...
> log``) Python block-buffers it, and a long-running server never
flushes: the "Initial-admin token path" line and the start banner
printed by :mod:`app_pychestrate_main` never reached the log. These
tests pin:

* every ``print`` in the entry point passes ``flush=True``;
* the systemd unit and the staging launcher run Python unbuffered.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import ast
import os

from typing import List

from ccai import testbase


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    rtnval = os.path.normpath(
        os.path.join(here, "..", "..", "..", "..", "..", "..", "..", "..")
    )
    return rtnval


def _read(*parts: str) -> str:
    with open(os.path.join(_repo_root(), *parts), "r", encoding="utf-8") as handle:
        rtnval = handle.read()
    return rtnval


def _print_calls(source: str) -> List[ast.Call]:
    calls: List[ast.Call] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            calls.append(node)
    return calls


def test_entry_point_prints_the_token_path():
    """
    **Feature: startup logging (LD-11)**
    **Property: both entry points print the initial-admin token path
    (so the flush property below is not vacuous).**
    """
    source = _read("source", "site", "app_pychestrate_main.py")
    testbase.assert_equal(source.count('print("Initial-admin token path: {}".format(token_path)'), 2)
    return


def test_every_entry_point_print_is_flushed():
    """
    **Feature: startup logging (LD-11)**
    **Property: every print() in app_pychestrate_main passes
    flush=True, so the line reaches a log file while the server keeps
    running.**
    """
    source = _read("source", "site", "app_pychestrate_main.py")
    unflushed = []
    for call in _print_calls(source):
        flushed = any(
            keyword.arg == "flush" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
            for keyword in call.keywords
        )
        if flushed is False:
            unflushed.append(call.lineno)
    testbase.assert_equal(unflushed, [])
    return


def test_systemd_unit_runs_python_unbuffered():
    """
    **Feature: startup logging (LD-11)**
    **Property: the service unit sets PYTHONUNBUFFERED=1.**
    """
    unit = _read("deployment", "pychestrate.service.template")
    testbase.assert_true('Environment="PYTHONUNBUFFERED=1"' in unit)
    return


def test_staging_launcher_runs_python_unbuffered():
    """
    **Feature: startup logging (LD-11)**
    **Property: development/run-staging-gunicorn exports
    PYTHONUNBUFFERED (defaulting to 1) for hand runs too.**
    """
    launcher = _read("development", "run-staging-gunicorn")
    testbase.assert_true('export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"' in launcher)
    return
