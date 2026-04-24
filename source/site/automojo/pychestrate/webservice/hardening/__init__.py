"""
.. module:: hardening
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Cross-cutting Layer-2 M3 infrastructure.

.. moduleauthor:: Automation Mojo LLC

Provides the hardening primitives consumed by every Layer-2 feature at
M3: idempotency middleware, rate limiter, metrics registry, structured
logger, and an extension-collision helper that feature modules call
during bootstrap.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
