"""
.. module:: pods.factories.validator
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pod_spec_validator`` factory protocol base.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, ClassVar, List, Mapping

from ccai.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


@dataclass(frozen=True)
class ValidationReport:
    """
        Outcome of a single pod-spec validator invocation.

        :param ok: True when the spec passes.
        :param errors: List of human-readable validation errors.
        :param warnings: List of non-blocking warnings.
    """
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class PodSpecValidatorProtocol(FactoryProtocolBase):
    """
        Contract implemented by pod-spec validators.
    """

    factory_protocol_name: ClassVar[str] = "pod_spec_validator"
    protocol_schema_version: ClassVar[int] = 1

    @classmethod
    def validate(cls, *, spec: Mapping[str, Any]) -> ValidationReport:
        """
            Validate ``spec`` and return a :class:`ValidationReport`.

            :param spec: The pod spec dict to check.

            :returns: The report.
        """
        raise NotImplementedError("Subclasses must implement validate()")
