"""
.. module:: jobs.reconcile.errors
    :synopsis: Reconciler exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ReconcileError(Exception):
    """
        Base for recoverable reconciler errors.
    """
