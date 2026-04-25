"""
.. module:: metrics.slos
    :synopsis: 7-slo-views — SLO catalog + status computation.

Public surface:

* :class:`SLO`, :class:`SLOBurnRateState` — persistence rows.
* :class:`SLOView`, :class:`SLOStatus`,
  :class:`SLOBurnRateStateView`, :class:`SLOKindRecord` —
  IO shapes.
* :func:`create_slo`, :func:`get_slo`,
  :func:`list_slos_for_project`, :func:`delete_slo`,
  :func:`compute_status`, :func:`list_slo_kinds`.
* :class:`SLODefinitionProtocol` factory contract +
  reference :class:`AvailabilityRatioSloKind`.
* :class:`SLOEventTopics`.
* Errors: :class:`SLOError`,
  :class:`SLONotFoundError`,
  :class:`SLOConflictError`,
  :class:`SLOKindUnknownError`,
  :class:`SLOConfigInvalidError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.metrics.slos.errors import (
    SLOConfigInvalidError,
    SLOConflictError,
    SLOError,
    SLOKindUnknownError,
    SLONotFoundError,
)
from automojo.pychestrate.webservice.metrics.slos.events import (
    SLOEventTopics,
)
from automojo.pychestrate.webservice.metrics.slos.factories.availability_ratio_kind import (
    AvailabilityRatioSloKind,
)
from automojo.pychestrate.webservice.metrics.slos.factories.kind_protocol import (
    SLODefinitionProtocol,
    SLOKindRecord,
)
from automojo.pychestrate.webservice.metrics.slos.models import (
    SLO,
    SLOBurnRateState,
)
from automojo.pychestrate.webservice.metrics.slos.service import (
    SLOBurnRateStateView,
    SLOStatus,
    SLOView,
    compute_status,
    create_slo,
    delete_slo,
    get_slo,
    list_slo_kinds,
    list_slos_for_project,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`AvailabilityRatioSloKind`
        reference.
    """
    register_factory_implementation(implementation=AvailabilityRatioSloKind)
    return
