"""
.. module:: automojo.testshared.factories
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Container for shared resource factories used across
               the pychestrate-service test tree.

.. moduleauthor:: Automation Mojo LLC

Factories live under per-category subpackages:

* :mod:`automojo.testshared.factories.browsers` -- Playwright
  browser + browser-context factories for UI tests.

Tests originate factory-produced resources via
``testbase.originate.parameter(...)`` at the appropriate scope
node (typically the package ``__init__.py``).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
