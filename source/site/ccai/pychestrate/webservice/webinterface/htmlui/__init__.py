"""
.. module:: webinterface.htmlui
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: HTML-surface support modules for the unified login
               flow (Requirement 5 of 1-authentication).

.. moduleauthor:: Code Craft AI LLC

This package owns the browser-side helpers that sit between the
incoming HTTP request and the existing authentication primitives
(``security.auth.local_flow``, ``security.auth.session_service``).
PR1 of the unified-login refactor ships only the
``next_validator`` module; the full ``login_view`` / ``logout_view``
extraction lands as part of a later slice.

See :mod:`ccai.pychestrate.webservice.webinterface.htmlui.next_validator`
for the same-origin guard applied to the post-login ``next`` query
parameter.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"
