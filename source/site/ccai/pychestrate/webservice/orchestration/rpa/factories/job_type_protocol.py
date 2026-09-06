"""
.. module:: orchestration.rpa.factories.job_type_protocol
    :synopsis: ``rpa_job_type`` factory contract — code-defined RPA job types.

.. moduleauthor:: Code Craft AI LLC

An extension pack can ship RPA job types as code instead of registering
them through the REST API or the admin page. A code-defined type
declares the same fields an administrator would enter (slug, display
name, execution mode, packet schema, secret fields, capability
requirements) plus the versions it publishes. The service mirrors every
registered implementation into the registry tables through
:func:`orchestration.rpa.service.sync_code_defined_job_types`; a row an
administrator already created wins on conflict (display fields are
left alone, versions the database already has are not rewritten).

Two convenience bases fix the execution mode:
:class:`ProcessJobType` (simple process jobs) and
:class:`TaskplusJobType` (tasker-based jobs).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


RPA_JOB_TYPE_PROTOCOL: str = "rpa_job_type"


@dataclass(frozen=True)
class CodeDefinedVersion:
    """
        One version a code-defined job type publishes.
    """
    version: str
    entrypoint: Mapping[str, Any]
    source_kind: str = "package"
    source_ref: str = ""
    environment: Mapping[str, str] = field(default_factory=dict)
    timeout_minutes: int = 60


class RpaJobTypeProtocol(FactoryProtocolBase):
    """
        Contract for ``rpa_job_type`` extensions.
    """
    factory_protocol_name: str = RPA_JOB_TYPE_PROTOCOL
    protocol_schema_version: int = 1
    is_published: bool = True
    published_docs_url: str = "https://docs.pychestrate.io/plugin-api/rpa_job_type"
    published_reference: str = (
        "ccai.pychestrate.webservice.orchestration.rpa.factories.job_type_protocol"
        ".ProcessJobType"
    )

    @classmethod
    def type_id(cls) -> str:
        """
            Stable slug (lowercase, digits, hyphen; 3 to 64 chars).
        """
        raise NotImplementedError("Subclasses must implement type_id")

    @classmethod
    def display_name(cls) -> str:
        raise NotImplementedError("Subclasses must implement display_name")

    @classmethod
    def description(cls) -> str:
        return ""

    @classmethod
    def execution_mode(cls) -> str:
        """
            ``process`` or ``tasker``.
        """
        raise NotImplementedError("Subclasses must implement execution_mode")

    @classmethod
    def capability_requirements(cls) -> Sequence[str]:
        return ()

    @classmethod
    def packet_schema(cls) -> Optional[Mapping[str, Any]]:
        return None

    @classmethod
    def secret_fields(cls) -> Sequence[str]:
        return ()

    @classmethod
    def versions(cls) -> Sequence[CodeDefinedVersion]:
        """
            Versions to publish. Empty means the type is registered but
            not runnable until an administrator publishes one.
        """
        return ()

    @classmethod
    def validate_packet(cls, *, packet: Mapping[str, Any]) -> Tuple[bool, Tuple[str, ...]]:
        """
            Optional extra validation beyond the JSON schema. Default
            accepts every packet.
        """
        rtnval: Tuple[bool, Tuple[str, ...]] = (True, ())
        return rtnval


class ProcessJobType(RpaJobTypeProtocol):
    """
        Base for code-defined simple process job types.
    """
    factory_protocol_name: str = RPA_JOB_TYPE_PROTOCOL

    @classmethod
    def execution_mode(cls) -> str:
        rtnval = "process"
        return rtnval


class TaskplusJobType(RpaJobTypeProtocol):
    """
        Base for code-defined tasker-based job types.
    """
    factory_protocol_name: str = RPA_JOB_TYPE_PROTOCOL

    @classmethod
    def execution_mode(cls) -> str:
        rtnval = "tasker"
        return rtnval


def describe_code_defined_type(implementation: Any) -> Dict[str, Any]:
    """
        Plain-dict description of a code-defined type (used by the
        catalog and diagnostics).
    """
    rtnval = {
        "type_id": implementation.type_id(),
        "display_name": implementation.display_name(),
        "execution_mode": implementation.execution_mode(),
        "implementation": "{}.{}".format(implementation.__module__, implementation.__name__),
        "versions": [v.version for v in implementation.versions()],
    }
    return rtnval
