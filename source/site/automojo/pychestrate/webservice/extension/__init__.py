"""
.. module:: extension
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Author-tooling subsystems for Pychestrate extension authors.

.. moduleauthor:: Automation Mojo LLC

This package hosts code-generation and developer-tooling subsystems
that accompany the Layer E extension model. It is intentionally a
sibling of (not nested under) :mod:`automojo.pychestrate.webservice.extensions`,
which owns the runtime registry / factory protocol surface used by the
service itself. Splitting them keeps service-runtime imports lean and
keeps tool-only dependencies (Jinja2, file generation, CLI argparse) out
of the request path.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
