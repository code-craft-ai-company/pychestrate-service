"""
.. module:: resources.inventory
    :synopsis: 4-resource-inventory — registry of operator-owned resources.

Public surface:

* :class:`Resource`, :class:`ResourceState` — persistence row + enum.
* :class:`ResourceView` — caller-facing read-model.
* :func:`register_resource`, :func:`get_resource`,
  :func:`list_resources`, :func:`transition_state`.
* :class:`ResourceKindProtocol` + reference :class:`DeviceResourceKind`.
* Errors: :class:`ResourceError`,
  :class:`ResourceIdentityConflictError`,
  :class:`ResourceNotFoundError`,
  :class:`ResourceKindUnknownError`.
* :class:`ResourceEventTopics`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.resources.inventory.errors import (
    ResourceError,
    ResourceIdentityConflictError,
    ResourceKindUnknownError,
    ResourceNotFoundError,
)
from ccai.pychestrate.webservice.resources.inventory.events import (
    ResourceEventTopics,
)
from ccai.pychestrate.webservice.resources.inventory.kinds.device_kind import (
    DeviceResourceKind,
)
from ccai.pychestrate.webservice.resources.inventory.kinds.kind_protocol import (
    ResourceKindProtocol,
)
from ccai.pychestrate.webservice.resources.inventory.models import (
    Resource,
    ResourceState,
)
from ccai.pychestrate.webservice.resources.inventory.service import (
    ResourceView,
    get_resource,
    list_resources,
    register_resource,
    transition_state,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`DeviceResourceKind` reference
        implementation. Operators add custom resource kinds by
        registering additional :class:`ResourceKindProtocol`
        subclasses with lower ``PRECEDENCE``.
    """
    register_factory_implementation(implementation=DeviceResourceKind)
    return
