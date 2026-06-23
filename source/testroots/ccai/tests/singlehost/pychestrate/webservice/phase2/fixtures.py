"""
.. module:: tests.singlehost.pychestrate.webservice.phase2.fixtures
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Shared test fixtures for Phase-2 tests.

.. moduleauthor:: Code Craft AI LLC

Extends the Phase-1 fixtures by also registering the Phase-2 built-in
extension packs so tests can exercise the new feature surfaces without
having to register them individually.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.phase2_bootstrap import (
    register_phase2_builtin_extensions,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def reset_phase2_runtime() -> None:
    """
        Reset the Phase-1 runtime and then register Phase-2 built-in
        extensions on top. Tests should call this at the top of every
        Phase-2 test that depends on extension state.

        :returns: None.
    """
    reset_phase1_runtime()
    register_phase2_builtin_extensions()
    return
