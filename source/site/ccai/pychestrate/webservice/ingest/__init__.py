"""
.. module:: ingest
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-5 ingest plane — progress + result-tree receivers.

.. moduleauthor:: Code Craft AI LLC

The ``ingest`` package owns the inbound side of run observation:
forwarded progress summaries from running clients
(``ingest.progress``) and result-tree landings on the shared
backend (``ingest.result``). Both feed the run state machine
through bus events.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"
