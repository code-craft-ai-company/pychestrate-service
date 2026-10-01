"""
.. module:: metrics.slos
    :synopsis: 7-slo-views — SLO catalog + status computation.

Public surface:

* :class:`SLO`, :class:`SLOBurnRateState` — persistence rows.
* :class:`SLOView`, :class:`SLOStatus`,
  :class:`SLOBurnRateStateView`, :class:`SLOKindRecord` —
  IO shapes.
* :func:`create_slo`, :func:`get_slo`,
  :func:`list_slos_for_project`, :func:`update_slo`, :func:`delete_slo`,
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

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.metrics.slos.errors import (
    SLOConfigInvalidError,
    SLOConflictError,
    SLOError,
    SLOKindUnknownError,
    SLONotFoundError,
)
from ccai.pychestrate.webservice.metrics.slos.events import (
    SLOEventTopics,
)
from ccai.pychestrate.webservice.metrics.slos.factories.availability_ratio_kind import (
    AvailabilityRatioSloKind,
)
from ccai.pychestrate.webservice.metrics.slos.factories.kind_protocol import (
    SLODefinitionProtocol,
    SLOKindRecord,
)
from ccai.pychestrate.webservice.metrics.slos.models import (
    SLO,
    SLOBurnRateState,
)
from ccai.pychestrate.webservice.metrics.slos.service import (
    SLOBurnRateStateView,
    SLOStatus,
    SLOView,
    compute_status,
    create_slo,
    delete_slo,
    get_slo,
    list_slo_kinds,
    list_slos_for_project,
    update_slo,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`AvailabilityRatioSloKind`
        reference.
    """
    register_factory_implementation(implementation=AvailabilityRatioSloKind)
    return
