"""
.. module:: orchestration.infra.environment
    :synopsis: 6-environment-registry — declarative environment catalog.

Public surface:

* :class:`Environment`, :class:`EnvironmentHistory`,
  :class:`EnvironmentState`, :class:`EnvironmentEventKind` —
  persistence rows + enums.
* :class:`EnvironmentView`, :class:`EnvironmentDeclareInputs` —
  IO shapes.
* :func:`declare_environment`, :func:`get_environment`,
  :func:`list_environments`, :func:`update_attrs`,
  :func:`freeze_environment`, :func:`unfreeze_environment`,
  :func:`archive_environment`,
  :func:`record_apply`, :func:`mark_destroyed`.
* :class:`EnvironmentKindProtocol` factory contract +
  reference :class:`K8sClusterEnvironmentKind`.
* :class:`EnvironmentEventTopics`.
* Errors: :class:`EnvironmentError`,
  :class:`EnvironmentNotFoundError`,
  :class:`EnvironmentKindUnknownError`,
  :class:`EnvironmentAttrsInvalidError`,
  :class:`EnvironmentStateError`,
  :class:`EnvironmentNameConflictError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.orchestration.infra.environment.errors import (
    EnvironmentAttrsInvalidError,
    EnvironmentError,
    EnvironmentKindUnknownError,
    EnvironmentNameConflictError,
    EnvironmentNotFoundError,
    EnvironmentStateError,
)
from automojo.pychestrate.webservice.orchestration.infra.environment.events import (
    EnvironmentEventTopics,
)
from automojo.pychestrate.webservice.orchestration.infra.environment.factories.k8s_cluster_kind import (
    K8sClusterEnvironmentKind,
)
from automojo.pychestrate.webservice.orchestration.infra.environment.factories.kind_protocol import (
    EnvironmentKindProtocol,
)
from automojo.pychestrate.webservice.orchestration.infra.environment.models import (
    Environment,
    EnvironmentEventKind,
    EnvironmentHistory,
    EnvironmentState,
)
from automojo.pychestrate.webservice.orchestration.infra.environment.service import (
    EnvironmentDeclareInputs,
    EnvironmentView,
    archive_environment,
    declare_environment,
    freeze_environment,
    get_environment,
    list_environments,
    mark_destroyed,
    record_apply,
    unfreeze_environment,
    update_attrs,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`K8sClusterEnvironmentKind`
        reference.
    """
    register_factory_implementation(
        implementation=K8sClusterEnvironmentKind,
    )
    return
