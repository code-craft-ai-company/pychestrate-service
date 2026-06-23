"""
.. module:: maintenance
    :synopsis: 0-maintenance-mode — service drain / read-only gate.

Public surface:

* :class:`MaintenanceModeRow`, :class:`MaintenanceModeAudit` —
  persistence rows.
* :class:`MaintenanceMode` — enum (active / read_only /
  draining).
* :class:`MaintenanceScopeView`,
  :class:`EffectiveModeView` — IO shapes.
* :func:`get_gate`, :func:`reset_for_testing`,
  :func:`mode_precedence`,
  :func:`set_scope_mode`, :func:`clear_scope_mode`,
  :func:`get_scope_mode`, :func:`get_effective_mode`,
  :func:`list_active_scopes`,
  :func:`list_audit_for_scope`.
* :class:`MaintenanceEventTopics`.
* Errors: :class:`MaintenanceError`,
  :class:`MaintenanceScopeInvalidError`,
  :class:`MaintenanceScopeNotFoundError`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.maintenance.errors import (
    MaintenanceError,
    MaintenanceScopeInvalidError,
    MaintenanceScopeNotFoundError,
)
from ccai.pychestrate.webservice.maintenance.events import (
    MaintenanceEventTopics,
)
from ccai.pychestrate.webservice.maintenance.gate import (
    MaintenanceGate,
    MaintenanceMode,
    get_gate,
    mode_precedence,
    reset_for_testing,
)
from ccai.pychestrate.webservice.maintenance.models import (
    MaintenanceModeAudit,
    MaintenanceModeRow,
)
from ccai.pychestrate.webservice.maintenance.service import (
    EffectiveModeView,
    MaintenanceScopeView,
    clear_scope_mode,
    get_effective_mode,
    get_scope_mode,
    list_active_scopes,
    list_audit_for_scope,
    set_scope_mode,
)
