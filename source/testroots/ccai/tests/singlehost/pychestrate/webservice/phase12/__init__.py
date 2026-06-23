"""
.. module:: ccai.tests.singlehost.pychestrate.webservice.phase12
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-12 tests -- site-shell rendering smoke
               against a live deploy.

.. moduleauthor:: Code Craft AI LLC

Phase 12 is the first round of tests covering the unified site
shell from ``specs/9-site-shell``. M1 ships only the rendering
smoke: hit the root path, assert the shell document mounts and
references the prebuilt bundle. M2/M3 tests follow with the
sidebar registry / palette / observability work.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"
