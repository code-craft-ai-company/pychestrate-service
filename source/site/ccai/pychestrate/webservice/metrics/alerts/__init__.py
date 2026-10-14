"""
.. module:: metrics.alerts
    :synopsis: 7-alerts-budgets — alert rules + live-state engine.

Public surface:

* :class:`AlertRule`, :class:`AlertLiveState` — persistence rows.
* :class:`AlertState`, :class:`AlertSeverity` — enums.
* :class:`AlertRuleView`, :class:`AlertLiveStateView`,
  :class:`AlertEvaluationResult`, :class:`AlertRuleKindRecord`
  — IO shapes.
* :func:`create_alert_rule`, :func:`get_alert_rule`,
  :func:`list_alert_rules_for_project`,
  :func:`disable_alert_rule`, :func:`evaluate_alert_rule`,
  :func:`get_live_state`, :func:`list_alert_kinds`.
* :class:`AlertRuleKindProtocol` factory contract +
  reference :class:`ThresholdAlertRuleKind`.
* :class:`AlertEventTopics`.
* Errors: :class:`AlertError`,
  :class:`AlertRuleNotFoundError`,
  :class:`AlertRuleConflictError`,
  :class:`AlertRuleKindUnknownError`,
  :class:`AlertRuleConfigInvalidError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.metrics.alerts.errors import (
    AlertError,
    AlertRuleConfigInvalidError,
    AlertRuleConflictError,
    AlertRuleKindUnknownError,
    AlertRuleNotFoundError,
)
from ccai.pychestrate.webservice.metrics.alerts.events import (
    AlertEventTopics,
)
from ccai.pychestrate.webservice.metrics.alerts.factories.rule_kind_protocol import (
    AlertRuleKindProtocol,
    AlertRuleKindRecord,
)
from ccai.pychestrate.webservice.metrics.alerts.factories.threshold_rule_kind import (
    ComparisonOp,
    ThresholdAlertRuleKind,
)
from ccai.pychestrate.webservice.metrics.alerts.models import (
    AlertLiveState,
    AlertRule,
    AlertSeverity,
    AlertState,
)
from ccai.pychestrate.webservice.metrics.alerts.service import (
    AlertEvaluationResult,
    AlertLiveStateView,
    AlertRuleView,
    create_alert_rule,
    delete_alert_rule,
    disable_alert_rule,
    evaluate_alert_rule,
    evaluate_enabled_alert_rules,
    get_alert_rule,
    get_live_state,
    list_alert_kinds,
    list_alert_rules_for_project,
    update_alert_rule,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`ThresholdAlertRuleKind`
        reference.
    """
    register_factory_implementation(implementation=ThresholdAlertRuleKind)
    return
