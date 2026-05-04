"""
.. module:: webinterface.foundation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-side foundation for the consumer-facing
               web UI port.

.. moduleauthor:: Automation Mojo LLC

The flask blueprints under ``webinterface/blueprints/{config,
projects,resources}/`` are pre-migration scaffold pending their
own webworks port. This package is the foundation those ports
will build on:

* :mod:`templating` — jinja2 environment + render helpers that
  produce :class:`HTMLResponse` objects from the existing
  ``templates/`` jinja2 files (no rewrite needed).

* :mod:`static_files` — static asset handler + registrar so the
  webinterface CSS / JS / images can be served from
  ``webinterface/static/`` once the blueprints are ported.

CSRF helpers and the cookie-backed UI session land alongside the
first blueprint port (the ``config`` blueprint at #137 / similar)
because they are exercised end-to-end by the first form-driven
flow.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
