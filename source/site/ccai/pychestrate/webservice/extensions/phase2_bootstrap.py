"""
.. module:: extensions.phase2_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register the in-tree Phase-2 extensions at service startup.

.. moduleauthor:: Code Craft AI LLC

Mirrors :mod:`extensions.bootstrap` but focused on the Layer-2 features
landed in this PR: 2-projects, 2-tagging, 2-global-variables,
2-notification-hub, 2-project-templates, 2-retention-policies.

Callers typically invoke :func:`register_phase1_builtin_extensions`
followed by :func:`register_phase2_builtin_extensions` at service start,
or use :func:`bootstrap_phase2_runtime` to register Phase-2 extensions
and re-wire the audit bus subscriber against the new audit event kinds.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.audit.bus_subscriber import wire_bus_subscribers
from ccai.pychestrate.webservice.notifications.run_notifier import wire_run_notifications
from ccai.pychestrate.webservice.projects.bus_subscriber import (
    wire_bus_subscribers as wire_projects_bus_subscribers,
)
from ccai.pychestrate.webservice.notifications import (
    register_builtin_extensions as notifications_register,
)
from ccai.pychestrate.webservice.project_templates import (
    register_builtin_extensions as project_templates_register,
)
from ccai.pychestrate.webservice.projects import (
    register_builtin_extensions as projects_register,
)
from ccai.pychestrate.webservice.retention import (
    register_builtin_extensions as retention_register,
)
from ccai.pychestrate.webservice.tagging import (
    register_builtin_extensions as tagging_register,
)
from ccai.pychestrate.webservice.variables import (
    register_builtin_extensions as variables_register,
)

# Side-effect imports: ensure every Phase-2 model module is loaded so its
# tables attach to ``PychestratePhase1Base.metadata`` before create_all
# runs in tests or Alembic inspects the metadata in production.
from ccai.pychestrate.webservice.hardening import idempotency as _hardening_idempotency  # noqa: F401
from ccai.pychestrate.webservice.notifications import models as _notifications_models  # noqa: F401
from ccai.pychestrate.webservice.projects import models as _projects_models  # noqa: F401
from ccai.pychestrate.webservice.retention import legal_hold as _retention_legal_hold  # noqa: F401
from ccai.pychestrate.webservice.retention import models as _retention_models  # noqa: F401
from ccai.pychestrate.webservice.tagging import models as _tagging_models  # noqa: F401
from ccai.pychestrate.webservice.variables import models as _variables_models  # noqa: F401


SessionFactory = Callable[[], DbSession]


@dataclass(frozen=True)
class Phase2BootstrapConfig:
    """
        Operator-supplied Phase-2 bootstrap configuration.

        :param session_factory: Callable returning a new SQLAlchemy
                                session; used by the audit bus subscriber
                                to persist audit rows from Phase-2 topics
                                outside the originating request's
                                transaction. Pass ``None`` to skip audit
                                re-wiring when Phase-1 bootstrap already
                                covered it.
    """
    session_factory: Optional[SessionFactory]


def register_phase2_builtin_extensions() -> None:
    """
        Register every in-tree Phase-2 factory protocol implementation and
        resource extension pack. The order matches ``specs/2-*`` numeric
        ordering so dependency direction is clear.

        :returns: None.
    """
    projects_register()
    tagging_register()
    variables_register()
    notifications_register()
    project_templates_register()
    retention_register()
    return


def bootstrap_phase2_runtime(*, config: Phase2BootstrapConfig) -> None:
    """
        Register Phase-2 extensions and re-wire the audit bus subscriber so
        it picks up the new ``AuditEventTypeExtension`` packs added by this
        PR. Intended to be called once at service startup, after
        :func:`bootstrap_phase1_runtime`.

        :param config: Caller-supplied :class:`Phase2BootstrapConfig`.

        :returns: None.
    """
    register_phase2_builtin_extensions()

    if config.session_factory is not None:
        wire_bus_subscribers(session_factory=config.session_factory)
        wire_projects_bus_subscribers(session_factory=config.session_factory)
        # Run failures and completions reach the notification rules (ORG-F08).
        wire_run_notifications(session_factory=config.session_factory)

    return
