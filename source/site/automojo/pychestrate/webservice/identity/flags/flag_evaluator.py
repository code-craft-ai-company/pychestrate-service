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


from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.identity.flags import cache as flag_cache
from automojo.pychestrate.webservice.identity.flags.models import (
    FeatureFlag,
    FeatureFlagVersion,
    FlagContext,
    FlagKind,
    FlagState,
)
from automojo.pychestrate.webservice.identity.flags.rules import evaluate_rollout


def _match_attribute_rule(*, context: FlagContext, rules: Dict) -> Optional[Any]:
    """
        Walk the optional ``attribute_matches`` list in declaration order and
        return the first rule whose ``attr == equals`` test fires against the
        evaluation context.

        :param context: Evaluation context.
        :param rules: Decoded ``rules_json`` dict.

        :returns: The matched rule's ``return`` value, or None when no rule fires.
    """
    matches_raw = rules.get("attribute_matches", None)
    if matches_raw is None:
        rtnval: Optional[Any] = None
        return rtnval

    matches: List[Dict] = list(matches_raw)
    if len(matches) == 0:
        rtnval = None
        return rtnval

    attribute_lookup: Dict[str, str] = {}
    for attr_pair in context.attributes:
        attr_key, attr_value = attr_pair
        attribute_lookup[attr_key] = attr_value
    if context.user_id is not None:
        attribute_lookup["user_id"] = context.user_id
    if context.project_id is not None:
        attribute_lookup["project_id"] = context.project_id

    for rule in matches:
        attr_name = rule.get("attr", None)
        equals_value = rule.get("equals", None)
        return_value = rule.get("return", None)
        if attr_name is None or equals_value is None:
            continue
        observed = attribute_lookup.get(attr_name, None)
        if observed is None:
            continue
        if observed == equals_value:
            rtnval = return_value
            return rtnval

    rtnval = None
    return rtnval


def _compute_for_kind(
        *,
        flag_kind: FlagKind,
        flag_key: str,
        context: FlagContext,
        rules: Dict,
        default_value: Any,
        default: Any
    ) -> Any:
    """
        Decide the evaluation result for a given kind / version row.

        :param flag_kind: The flag's kind.
        :param flag_key: Flag identifier (used by hash-based rollout).
        :param context: Evaluation context.
        :param rules: Decoded rules dict.
        :param default_value: The version's default value.
        :param default: Caller-supplied fallback.

        :returns: The decided value.
    """
    if flag_kind == FlagKind.BOOLEAN:
        attribute_match = _match_attribute_rule(context=context, rules=rules)
        if attribute_match is not None:
            rtnval = bool(attribute_match)
            return rtnval
        rtnval = bool(default_value)
        return rtnval

    if flag_kind == FlagKind.PERCENTAGE:
        rollout_bp = int(rules.get("rollout_percentage_bp", 0))
        decision = evaluate_rollout(
            flag_key=flag_key, context=context, rollout_percentage_bp=rollout_bp
        )
        rtnval = decision
        return rtnval

    if flag_kind == FlagKind.STRING:
        attribute_match = _match_attribute_rule(context=context, rules=rules)
        if attribute_match is not None:
            rtnval = str(attribute_match)
            return rtnval
        if default_value is None:
            rtnval = default
            return rtnval
        rtnval = str(default_value)
        return rtnval

    if flag_kind == FlagKind.ENUM:
        choices_raw = rules.get("enum_choices", None)
        choices: List[str] = []
        if choices_raw is not None:
            for choice in choices_raw:
                choices.append(str(choice))
        attribute_match = _match_attribute_rule(context=context, rules=rules)
        if attribute_match is not None:
            attribute_match_str = str(attribute_match)
            if len(choices) == 0 or attribute_match_str in choices:
                rtnval = attribute_match_str
                return rtnval
        if default_value is None:
            rtnval = default
            return rtnval
        default_value_str = str(default_value)
        if len(choices) > 0 and default_value_str not in choices:
            rtnval = default
            return rtnval
        rtnval = default_value_str
        return rtnval

    rtnval = default
    return rtnval


def evaluate_flag(
        *,
        db_session: DbSession,
        flag_key: str,
        context: FlagContext,
        default: Any
    ) -> Any:
    """
        Evaluate a feature flag for the given context.

        Handles BOOLEAN, PERCENTAGE, STRING, and ENUM kinds against the
        local backend rows. Unknown flag keys, retired flags, and missing
        rules all fall back to ``default``. Successful evaluations are
        cached for the configured staleness window
        (:mod:`identity.flags.cache`).

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

    flag_version = int(flag.current_version)
    cached_value = flag_cache.lookup(
        flag_key=flag_key, flag_version=flag_version, bucketing_key=context.bucketing_key
    )
    if cached_value is not None:
        rtnval = cached_value
        return rtnval

    version = (
        db_session.query(FeatureFlagVersion)
        .filter(FeatureFlagVersion.flag_key == flag_key)
        .filter(FeatureFlagVersion.version == flag_version)
        .first()
    )
    if version is None:
        rtnval = default
        return rtnval

    rules: Dict = version.rules_json or {}
    default_value = version.default_value

    computed = _compute_for_kind(
        flag_kind=flag.flag_kind,
        flag_key=flag_key,
        context=context,
        rules=rules,
        default_value=default_value,
        default=default,
    )

    flag_cache.store(
        flag_key=flag_key,
        flag_version=flag_version,
        bucketing_key=context.bucketing_key,
        value=computed,
    )

    rtnval = computed
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
