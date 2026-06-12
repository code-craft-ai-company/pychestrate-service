"""
.. module:: identity.flags.backend_router
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Pattern + precedence resolution of feature_flag_backend implementations.

.. moduleauthor:: Code Craft AI LLC

The router asks the extension registry for every registered
``feature_flag_backend`` implementation, filters by glob match against
``flag_key_pattern``, and breaks ties by ascending ``PRECEDENCE``
(lower value wins, mirroring the ``codecraftai-extension`` convention).
When two backends claim the same key, the loser is logged as
``flags.backend.override`` so operators can see who shadowed whom.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import fnmatch
import logging
import os
import threading

from typing import Dict, List, Set, Tuple, Type

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.identity.flags.factories.feature_flag_backend import (
    FeatureFlagBackendProtocol,
)


logger = logging.getLogger(__name__)


_FACTORY_PROTOCOL_NAME: str = "feature_flag_backend"


_OVERRIDE_LOCK = threading.RLock()
_LOGGED_OVERRIDES: Set[Tuple[str, str, str]] = set()


def list_registered_backends() -> Tuple[Type[FeatureFlagBackendProtocol], ...]:
    """
        Return all registered ``feature_flag_backend`` implementations
        ordered by ascending ``PRECEDENCE``.

        :returns: Tuple of implementation classes.
    """
    rtnval = list_factory_implementations(factory_protocol_name=_FACTORY_PROTOCOL_NAME)
    return rtnval


def _matches_pattern(*, pattern: str, flag_key: str) -> bool:
    """
        Glob-match ``flag_key`` against ``pattern``.

        :param pattern: Glob pattern.
        :param flag_key: Flag key under evaluation.

        :returns: True when the pattern matches.
    """
    rtnval = fnmatch.fnmatchcase(flag_key, pattern)
    return rtnval


def _log_override_once(
        *,
        flag_key: str,
        winner_name: str,
        loser_name: str
    ) -> None:
    """
        Emit ``flags.backend.override`` exactly once per
        (flag_key, winner, loser) triple so multi-evaluator workloads do
        not flood the log.

        :param flag_key: Flag key whose pattern matched both backends.
        :param winner_name: Backend that took precedence.
        :param loser_name: Backend that was shadowed.

        :returns: None.
    """
    triple: Tuple[str, str, str] = (flag_key, winner_name, loser_name)
    with _OVERRIDE_LOCK:
        if triple in _LOGGED_OVERRIDES:
            return
        _LOGGED_OVERRIDES.add(triple)

    logger.info(
        "flags.backend.override flag_key=%s winner=%s loser=%s",
        flag_key, winner_name, loser_name
    )
    return


def reset_override_log_for_testing() -> None:
    """
        Clear the dedup cache used by :func:`_log_override_once`.

        :returns: None.
    """
    with _OVERRIDE_LOCK:
        _LOGGED_OVERRIDES.clear()
    return


def resolve_backend(*, flag_key: str) -> Type[FeatureFlagBackendProtocol]:
    """
        Resolve the highest-priority backend whose ``flag_key_pattern``
        matches ``flag_key``. When two patterns tie on precedence, the
        first-registered backend wins; the shadowed backend is logged.

        :param flag_key: Flag key under evaluation.

        :returns: Selected backend class.
        :raises: ConfigurationError when no backend matches.
    """
    candidates = list_registered_backends()
    if len(candidates) == 0:
        err_msg_lines = ["No feature_flag_backend implementations are registered."]
        err_msg_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    matched: List[Type[FeatureFlagBackendProtocol]] = []
    for backend_cls in candidates:
        pattern = backend_cls.flag_key_pattern()
        if _matches_pattern(pattern=pattern, flag_key=flag_key) is True:
            matched.append(backend_cls)

    if len(matched) == 0:
        err_msg_lines = ["No feature_flag_backend matches flag_key."]
        err_msg_lines.append("FLAG_KEY: {}".format(flag_key))
        err_msg_lines.append("REGISTERED: {}".format(", ".join([
            backend_cls.backend_name() for backend_cls in candidates
        ])))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    matched.sort(key=lambda backend_cls: getattr(backend_cls, "PRECEDENCE", 1000))

    winner = matched[0]
    winner_name = winner.backend_name()
    for shadow in matched[1:]:
        loser_name = shadow.backend_name()
        _log_override_once(
            flag_key=flag_key, winner_name=winner_name, loser_name=loser_name
        )

    rtnval = winner
    return rtnval


def list_backends_for_pattern(*, flag_key: str) -> List[Type[FeatureFlagBackendProtocol]]:
    """
        Return every backend whose pattern matches ``flag_key``, ordered
        by ascending ``PRECEDENCE``. Read-only inspection helper used by
        the admin REST surface.

        :param flag_key: Flag key under inspection.

        :returns: List of backend classes (may be empty).
    """
    candidates = list_registered_backends()
    matched: List[Type[FeatureFlagBackendProtocol]] = []
    for backend_cls in candidates:
        pattern = backend_cls.flag_key_pattern()
        if _matches_pattern(pattern=pattern, flag_key=flag_key) is True:
            matched.append(backend_cls)

    matched.sort(key=lambda backend_cls: getattr(backend_cls, "PRECEDENCE", 1000))
    rtnval = matched
    return rtnval


def diagnostic_snapshot() -> Dict[str, Dict]:
    """
        Return a serializable view of every registered backend keyed by
        backend name. Used by ``/api/v1/flags/backends`` and by tests.

        :returns: Dict mapping backend_name to descriptor dict.
    """
    snapshot: Dict[str, Dict] = {}
    for backend_cls in list_registered_backends():
        snapshot[backend_cls.backend_name()] = {
            "backend_name": backend_cls.backend_name(),
            "flag_key_pattern": backend_cls.flag_key_pattern(),
            "precedence": int(getattr(backend_cls, "PRECEDENCE", 1000)),
        }
    rtnval = snapshot
    return rtnval
