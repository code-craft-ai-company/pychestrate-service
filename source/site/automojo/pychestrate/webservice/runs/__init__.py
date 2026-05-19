"""
.. module:: webservice.runs
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST surface for run read + ingest endpoints.

.. moduleauthor:: Automation Mojo LLC

The ``runs`` package owns the operator-facing read endpoints
(``GET /api/v1/runs`` + ``GET /api/v1/runs/{id}``) and the
agent-facing ingest endpoints (``POST .../progress``,
``POST .../results/complete``, ``POST .../dispatch-ack``).

The domain logic lives elsewhere (``jobs.run.state.repository``,
``ingest.progress.service``, ``ingest.result.scanner``,
``jobs.dispatch.receipt.service``); this package is the HTTP
adapter only.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
