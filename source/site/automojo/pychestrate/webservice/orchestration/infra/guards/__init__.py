"""
.. module:: orchestration.infra.guards
    :synopsis: 6-blast-radius-guards — pre-action decision engine.

Public surface:

* :class:`GuardAttachment` — persistence row.
* :class:`GuardContext`, :class:`GuardVerdict`,
  :class:`GuardDecision`, :class:`GuardTrace`,
  :class:`GuardRuleRecord`, :class:`GuardAttachmentView` — IO
  shapes.
* :func:`set_attachment`, :func:`disable_attachment`,
  :func:`list_attachments_for_environment`, :func:`allow`,
  :func:`explain`, :func:`list_rule_records`.
* :class:`GuardRuleProtocol` factory contract +
  reference :class:`FrozenEnvBlockRule`,
  :class:`ApplyRequiresInfraOperatorRoleRule`.
* :class:`GuardEventTopics`.
* Errors: :class:`GuardError`,
  :class:`GuardAttachmentNotFoundError`,
  :class:`GuardRuleUnknownError`,
  :class:`GuardEnvironmentNotFoundError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.orchestration.infra.guards.errors import (
    GuardAttachmentNotFoundError,
    GuardEnvironmentNotFoundError,
    GuardError,
    GuardRuleUnknownError,
)
from automojo.pychestrate.webservice.orchestration.infra.guards.events import (
    GuardEventTopics,
)
from automojo.pychestrate.webservice.orchestration.infra.guards.factories.apply_requires_role_rule import (
    APPLY_REQUIRES_INFRA_OPERATOR_ROLE_RULE_ID,
    ApplyRequiresInfraOperatorRoleRule,
)
from automojo.pychestrate.webservice.orchestration.infra.guards.factories.frozen_env_block_rule import (
    FROZEN_ENV_BLOCK_RULE_ID,
    FrozenEnvBlockRule,
)
from automojo.pychestrate.webservice.orchestration.infra.guards.factories.rule_protocol import (
    GuardContext,
    GuardDecision,
    GuardRuleProtocol,
    GuardVerdict,
)
from automojo.pychestrate.webservice.orchestration.infra.guards.models import (
    GuardAttachment,
)
from automojo.pychestrate.webservice.orchestration.infra.guards.service import (
    GuardAttachmentView,
    GuardRuleRecord,
    GuardTrace,
    allow,
    disable_attachment,
    explain,
    list_attachments_for_environment,
    list_rule_records,
    set_attachment,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`FrozenEnvBlockRule` +
        :class:`ApplyRequiresInfraOperatorRoleRule` references.
    """
    register_factory_implementation(implementation=FrozenEnvBlockRule)
    register_factory_implementation(
        implementation=ApplyRequiresInfraOperatorRoleRule,
    )
    return
