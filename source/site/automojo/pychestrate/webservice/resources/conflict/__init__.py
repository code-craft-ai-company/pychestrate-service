"""
.. module:: resources.conflict
    :synopsis: 4-conflict-deconfliction — reservation conflict rules.

Public surface:

* :class:`RuleDecision`, :class:`ConflictEvaluation`,
  :class:`ActiveReservationSnapshot` — IO shapes.
* :class:`ConflictRuleProtocol` factory contract +
  :class:`ExclusiveModeRule` + :class:`SharedModeRule` reference
  rules.
* :func:`evaluate` — runs registered rules and returns a
  ``ConflictEvaluation``.
* :func:`register_builtin_extensions`.
* :class:`ConflictError` exception base.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.resources.conflict.errors import (
    ConflictError,
)
from automojo.pychestrate.webservice.resources.conflict.evaluator import (
    ActiveReservationSnapshot,
    CandidateReservation,
    ConflictEvaluation,
    RuleDecision,
    evaluate,
)
from automojo.pychestrate.webservice.resources.conflict.rules.exclusive_rule import (
    ExclusiveModeRule,
)
from automojo.pychestrate.webservice.resources.conflict.rules.rule_protocol import (
    ConflictRuleProtocol,
)
from automojo.pychestrate.webservice.resources.conflict.rules.shared_rule import (
    SharedModeRule,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree :class:`ExclusiveModeRule` and
        :class:`SharedModeRule` ``conflict_rule`` factory
        implementations.
    """
    register_factory_implementation(implementation=ExclusiveModeRule)
    register_factory_implementation(implementation=SharedModeRule)
    return
