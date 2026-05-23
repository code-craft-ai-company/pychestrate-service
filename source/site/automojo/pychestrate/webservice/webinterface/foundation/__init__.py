"""
.. module:: webinterface.foundation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-side foundation for the consumer-facing
               web UI port.

.. moduleauthor:: Automation Mojo LLC

The blueprints under ``webinterface/blueprints/{config,
projects,resources}/`` build on this package for jinja2 rendering,
static asset serving, CSRF, and the cookie-backed UI session:

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
