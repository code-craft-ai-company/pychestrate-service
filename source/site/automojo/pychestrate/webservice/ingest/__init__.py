"""
.. module:: ingest
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-5 ingest plane — progress + result-tree receivers.

.. moduleauthor:: Automation Mojo LLC

The ``ingest`` package owns the inbound side of run observation:
forwarded progress summaries from running clients
(``ingest.progress``) and result-tree landings on the shared
backend (``ingest.result``). Both feed the run state machine
through bus events.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
