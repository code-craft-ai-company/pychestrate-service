"""
.. module:: extensions.phase8_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register the in-tree Layer-8 (public surface) extensions.

.. moduleauthor:: Code Craft AI LLC

Layer 8 hosts the public surface — REST API, webhooks (in /
out), CLI, embeddable views, and the plugin API. M1 lands the
in-tree :class:`WebhookNotificationChannel` reference under
``notification_channel``. M2 widens to email + slack +
pagerduty channels and adds the inbound webhook parser pack.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.clients.upgrades import (
    register_builtin_extensions as agent_upgrades_register,
)
from ccai.pychestrate.webservice.ops.release import (
    register_builtin_extensions as releases_register,
)
from ccai.pychestrate.webservice.webhooks_in import (
    register_builtin_extensions as webhooks_in_register,
)
from ccai.pychestrate.webservice.webhooks_out import (
    register_builtin_extensions as webhooks_out_register,
)

# Side-effect imports so Layer-8 model tables attach to the metadata.
from ccai.pychestrate.webservice.clients.upgrades import models as _upgrades_models  # noqa: F401
from ccai.pychestrate.webservice.ops.release import models as _ops_release_models  # noqa: F401
from ccai.pychestrate.webservice.webhooks_in import models as _webhooks_in_models  # noqa: F401
from ccai.pychestrate.webservice.webhooks_out import models as _webhooks_out_models  # noqa: F401


SessionFactory = Callable[[], DbSession]


@dataclass(frozen=True)
class Phase8BootstrapConfig:
    """
        Operator-supplied Phase-8 bootstrap configuration.
    """
    session_factory: Optional[SessionFactory]


def register_phase8_builtin_extensions() -> None:
    """
        Register Layer-8 in-tree factory implementations.
    """
    webhooks_out_register()
    webhooks_in_register()
    releases_register()
    agent_upgrades_register()
    return


def bootstrap_phase8_runtime(*, config: Phase8BootstrapConfig) -> None:
    """
        Layer-8 runtime bootstrap. M1 only registers extensions;
        M2 wires the outbound dispatcher worker + the inbound
        parser pack.
    """
    register_phase8_builtin_extensions()
    _ = config
    return
