"""
.. module:: identity.flags.flag_evaluator
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Hot-path feature-flag evaluator.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.identity.flags.models import (
    FeatureFlag,
    FeatureFlagVersion,
    FlagContext,
    FlagKind,
    FlagState,
)
from automojo.pychestrate.webservice.identity.flags.rules import evaluate_rollout


def evaluate_flag(
        *,
        db_session: DbSession,
        flag_key: str,
        context: FlagContext,
        default: Any
    ) -> Any:
    """
        Evaluate a feature flag for the given context.

        The M1 skeleton handles BOOLEAN and PERCENTAGE kinds against the
        local backend rows; STRING / ENUM arrive in M2. Unknown flag keys,
        retired flags, and missing rules all fall back to ``default``.

        :param db_session: Active SQLAlchemy session.
        :param flag_key: Registered flag key.
        :param context: Evaluation context carrying ``bucketing_key``.
        :param default: Returned if the flag is unknown.

        :returns: The flag's value for ``context``.
        :raises: SemanticError on missing ``bucketing_key``.
    """
    if context is None or context.bucketing_key is None or len(context.bucketing_key) == 0:
        raise SemanticError("evaluate_flag requires a non-empty FlagContext.bucketing_key")

    flag = db_session.query(FeatureFlag).filter(FeatureFlag.flag_key == flag_key).first()
    if flag is None:
        rtnval = default
        return rtnval

    if flag.state == FlagState.RETIRED:
        rtnval = default
        return rtnval

    version = (
        db_session.query(FeatureFlagVersion)
        .filter(FeatureFlagVersion.flag_key == flag_key)
        .filter(FeatureFlagVersion.version == flag.current_version)
        .first()
    )
    if version is None:
        rtnval = default
        return rtnval

    if flag.flag_kind == FlagKind.BOOLEAN:
        default_value = version.default_value
        rtnval = bool(default_value)
        return rtnval

    if flag.flag_kind == FlagKind.PERCENTAGE:
        rules = version.rules_json or {}
        rollout_bp = int(rules.get("rollout_percentage_bp", 0))
        decision = evaluate_rollout(
            flag_key=flag_key, context=context, rollout_percentage_bp=rollout_bp
        )
        rtnval = decision
        return rtnval

    rtnval = default
    return rtnval


def evaluate_boolean(
        *,
        db_session: DbSession,
        flag_key: str,
        context: FlagContext,
        default: bool
    ) -> bool:
    """
        Type-safe wrapper returning the boolean evaluation of a flag.

        :param db_session: Active SQLAlchemy session.
        :param flag_key: Registered flag key.
        :param context: Evaluation context.
        :param default: Fallback boolean.

        :returns: The evaluated boolean.
    """
    value = evaluate_flag(
        db_session=db_session, flag_key=flag_key, context=context, default=default
    )
    rtnval = bool(value)
    return rtnval
