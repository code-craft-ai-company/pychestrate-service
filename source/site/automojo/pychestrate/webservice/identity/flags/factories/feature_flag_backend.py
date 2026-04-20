"""
.. module:: identity.flags.factories.feature_flag_backend
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: FactoryProtocolBase for pluggable feature flag backends.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, Tuple

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase
from automojo.pychestrate.webservice.identity.flags.models import FlagContext, FlagKind


@dataclass(frozen=True)
class BackendEvaluation:
    """
        Outcome of a backend evaluation.

        :param value: The resolved flag value.
        :param reason: Short string describing which rule decided.
    """
    value: Any
    reason: str


@dataclass(frozen=True)
class BackendHealth:
    """
        Health report returned by the backend.

        :param healthy: Current health status.
        :param reason: Short reason string when unhealthy.
    """
    healthy: bool
    reason: str


@dataclass(frozen=True)
class FlagDescriptor:
    """
        Minimal metadata used by list operations.

        :param flag_key: Registered key.
        :param flag_kind: :class:`FlagKind` for this flag.
    """
    flag_key: str
    flag_kind: FlagKind


class FeatureFlagBackendProtocol(FactoryProtocolBase):
    """
        Contract for a ``feature_flag_backend`` implementation.
    """

    factory_protocol_name: str = "feature_flag_backend"
    protocol_schema_version: int = 1

    @classmethod
    def backend_name(cls) -> str:
        """
            Return the backend's unique name.

            :returns: Backend name string.
        """
        raise NotImplementedError("Subclasses must implement backend_name")

    @classmethod
    def flag_key_pattern(cls) -> str:
        """
            Glob pattern claimed by this backend.

            :returns: Pattern string.
        """
        raise NotImplementedError("Subclasses must implement flag_key_pattern")

    @classmethod
    def evaluate(
            cls,
            *,
            flag_key: str,
            context: FlagContext,
            default: Any
        ) -> BackendEvaluation:
        """
            Evaluate a flag in this backend.

            :returns: :class:`BackendEvaluation`.
        """
        raise NotImplementedError("Subclasses must implement evaluate")

    @classmethod
    def list_flags(cls) -> Tuple[FlagDescriptor, ...]:
        """
            List the flags the backend owns.

            :returns: Tuple of :class:`FlagDescriptor`.
        """
        raise NotImplementedError("Subclasses must implement list_flags")

    @classmethod
    def health_check(cls) -> BackendHealth:
        """
            Report current backend health.

            :returns: :class:`BackendHealth`.
        """
        raise NotImplementedError("Subclasses must implement health_check")
