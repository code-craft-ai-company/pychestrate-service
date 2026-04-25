"""
.. module:: extensions.phase4_bootstrap
    :synopsis: Register the in-tree Layer-4 (resources) extensions.

.. moduleauthor:: Automation Mojo LLC

Phase-4 / Layer-4 hosts the resource-management plane. M1
registers the in-tree :class:`DeviceResourceKind` reference. M2
adds custom kinds, allocation strategies, conflict rules, and
health probes through additional factory protocol packs.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.resources.inventory import (
    register_builtin_extensions as inventory_register,
)

# Side-effect imports so Layer-4 model tables attach to the metadata.
from automojo.pychestrate.webservice.resources.inventory import models as _inventory_models  # noqa: F401
from automojo.pychestrate.webservice.resources.pools import models as _pools_models  # noqa: F401


SessionFactory = Callable[[], DbSession]


@dataclass(frozen=True)
class Phase4BootstrapConfig:
    """
        Operator-supplied Phase-4 bootstrap configuration.
    """
    session_factory: Optional[SessionFactory]


def register_phase4_builtin_extensions() -> None:
    """
        Register Layer-4 in-tree factory implementations.
    """
    inventory_register()
    return


def bootstrap_phase4_runtime(*, config: Phase4BootstrapConfig) -> None:
    """
        Phase-4 runtime bootstrap. M1 only registers extensions;
        future M2 work (allocation strategies, health probe
        scheduler) extends this function.
    """
    register_phase4_builtin_extensions()
    _ = config
    return
