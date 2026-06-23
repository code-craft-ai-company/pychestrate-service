"""
.. module:: jobs
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-5 job-execution plane — envelope, dispatch, receipt, run state.

.. moduleauthor:: Code Craft AI LLC

The ``jobs`` package owns the signed-envelope / dispatch / receipt /
run-state-machine pipeline that Pychestrate hands to pod client agents.
Layer 5 sub-packages land in Phase 3:

- ``jobs.envelope`` — canonical, signed dispatch payload.
- ``jobs.run.state`` — authoritative run state machine + outbox.
- ``jobs.dispatch`` — scheduler + transport + attempt persistence (later).
- ``jobs.dispatch.receipt`` — client-issued local-run-id correlation (later).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"
