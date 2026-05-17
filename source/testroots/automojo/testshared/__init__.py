"""
.. module:: automojo.testshared
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Shared resource factories + test helpers for the
               pychestrate-service test tree.

.. moduleauthor:: Automation Mojo LLC

Per the project's testbase conventions
(see ``AGENTS.md`` / ``# Writing Tests``), the test tree should
contain ONLY resource origination declarations and tests --
factories belong in ``testshared/factories/``. This namespace
is the home for those factories plus small cross-test helpers
like the ``BASE_URL`` resolver in ``test_config``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
