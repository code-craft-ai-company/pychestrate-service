"""
.. module:: extensions.phase3_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register the in-tree Phase-3 (Layer-3) extensions at startup.

.. moduleauthor:: Code Craft AI LLC

Follows the same pattern as :mod:`extensions.phase2_bootstrap`. Callers
run :func:`bootstrap_phase1_runtime` + :func:`bootstrap_phase2_runtime`
+ :func:`bootstrap_phase3_runtime` at service start.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.agents import (
    register_builtin_extensions as agents_register,
)
from ccai.pychestrate.webservice.pods import (
    register_builtin_extensions as pods_register,
)
from ccai.pychestrate.webservice.agents.bus_subscriber import (
    wire_bus_subscribers as wire_agents_bus_subscribers,
)
from ccai.pychestrate.webservice.pods.bus_subscriber import (
    wire_bus_subscribers as wire_pods_bus_subscribers,
)

# Side-effect imports so Layer-3 model tables attach to the metadata.
from ccai.pychestrate.webservice.agents import models as _agents_models  # noqa: F401
from ccai.pychestrate.webservice.pods import models as _pods_models  # noqa: F401


SessionFactory = Callable[[], DbSession]


@dataclass(frozen=True)
class Phase3BootstrapConfig:
    """
        Operator-supplied Phase-3 bootstrap configuration.

        :param session_factory: Optional session factory used for bus
                                subscribers owned by Phase-3 features
                                (currently the scoped-config purge
                                subscriber).
    """
    session_factory: Optional[SessionFactory]


def register_phase3_builtin_extensions() -> None:
    """
        Register every in-tree Phase-3 factory + resource extension.
    """
    pods_register()
    agents_register()
    return


def bootstrap_phase3_runtime(*, config: Phase3BootstrapConfig) -> None:
    """
        Register Phase-3 extensions and wire Phase-3 bus subscribers.
    """
    register_phase3_builtin_extensions()
    if config.session_factory is not None:
        wire_pods_bus_subscribers(session_factory=config.session_factory)
        wire_agents_bus_subscribers(session_factory=config.session_factory)
    return
