"""
.. module:: ccai.tests.singlehost.pychestrate.webservice.phase13
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-13 tests -- UI remediation guardrails.

.. moduleauthor:: Code Craft AI LLC

Phase 13 carries the guardrail suite introduced by the UI
remediation roadmap (Phase 0): every consumer-UI template is
rendered under ``jinja2.StrictUndefined`` against fixtures shaped
like the manager response dataclasses the handlers pass, and
every ``url_for`` endpoint referenced by a template is checked
against the route registry. Neither needs a database, a browser,
or a running server.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"
