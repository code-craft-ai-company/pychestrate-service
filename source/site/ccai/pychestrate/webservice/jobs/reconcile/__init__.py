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

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.jobs.reconcile.errors import (
    ReconcileError,
)
from ccai.pychestrate.webservice.jobs.reconcile.models import (
    ReconcileDecision,
    ReconcileOutcome,
)
from ccai.pychestrate.webservice.jobs.reconcile.reconciler import (
    RunReconciler,
)
