"""
.. module:: identity.flags.factories.local_backend
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference feature-flag backend backed by the local DB tables.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Tuple

from automojo.pychestrate.webservice.identity.flags.factories.feature_flag_backend import (
    BackendEvaluation,
    BackendHealth,
    FeatureFlagBackendProtocol,
    FlagDescriptor,
)
from automojo.pychestrate.webservice.identity.flags.models import FlagContext


class LocalDatabaseFeatureFlagBackend(FeatureFlagBackendProtocol):
    """
        Reference ``feature_flag_backend`` implementation. Claims
        ``flag_key_pattern = "*"`` so it serves any key not taken by a
        higher-priority backend. Evaluation and listing are implemented
        in :mod:`flag_evaluator`; this class exposes only the factory
        surface so operators can enumerate registered backends.
    """

    factory_protocol_name: str = "feature_flag_backend"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def backend_name(cls) -> str:
        rtnval = "local-db"
        return rtnval

    @classmethod
    def flag_key_pattern(cls) -> str:
        rtnval = "*"
        return rtnval

    @classmethod
    def evaluate(
            cls,
            *,
            flag_key: str,
            context: FlagContext,
            default: Any
        ) -> BackendEvaluation:
        # The service layer performs local evaluation directly against the
        # SQLAlchemy session. This method exists so the registry returns
        # a conforming object when iterating registered backends.
        rtnval = BackendEvaluation(
            value=default,
            reason="local_backend_delegated_to_service_layer",
        )
        return rtnval

    @classmethod
    def list_flags(cls) -> Tuple[FlagDescriptor, ...]:
        rtnval: Tuple[FlagDescriptor, ...] = ()
        return rtnval

    @classmethod
    def health_check(cls) -> BackendHealth:
        rtnval = BackendHealth(healthy=True, reason="")
        return rtnval
