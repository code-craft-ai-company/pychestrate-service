"""
.. module:: jobs.reconcile
    :synopsis: 5-cancel-reconcile reconciler half.

Public surface:

* :class:`RunReconciler` — invoked on
  ``entity.client.reconnected`` events to align service-side
  state with the client's authoritative truth.
* Persistence: :class:`ReconcileDecision`.
* Errors: :class:`ReconcileError`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.jobs.reconcile.errors import (
    ReconcileError,
)
from automojo.pychestrate.webservice.jobs.reconcile.models import (
    ReconcileDecision,
    ReconcileOutcome,
)
from automojo.pychestrate.webservice.jobs.reconcile.reconciler import (
    RunReconciler,
)
