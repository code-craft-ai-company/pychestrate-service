"""
.. module:: orchestration.test.factories.runner_protocol
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``test_runner_kind`` factory contract.

.. moduleauthor:: Automation Mojo LLC

A test-runner-kind validates inputs and produces the runtime
parameter map the dispatcher embeds in the envelope. Different
runners (testbase, gtest, pytest, custom) ship as separate
factory implementations.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Mapping

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)
from automojo.pychestrate.webservice.orchestration.test.catalog.payloads import (
    TestCatalogEntrySnapshot,
)


class TestRunnerKindProtocol(FactoryProtocolBase):
    """
        Contract for a test-runner kind.
    """

    factory_protocol_name: str = "test_runner_kind"
    protocol_schema_version: int = 1

    is_published: bool = True
    published_docs_url: str = "https://docs.pychestrate.io/plugin-api/test_runner_kind"
    published_reference: str = (
        "automojo.pychestrate.webservice.orchestration.test.factories.testbase_runner"
        ".TestbaseRunnerKind"
    )

    @classmethod
    def runner_kind(cls) -> str:
        """
            Stable identifier the catalog snapshot's
            ``runner_kind`` field matches against.
        """
        raise NotImplementedError("Subclasses must implement runner_kind")

    @classmethod
    def validate_inputs(
            cls,
            *,
            snapshot: TestCatalogEntrySnapshot,
            inputs: Mapping[str, Any]
        ) -> None:
        """
            Raise on invalid inputs. Implementations SHOULD use
            multi-line :class:`SemanticError` messages naming
            offending fields.
        """
        raise NotImplementedError("Subclasses must implement validate_inputs")

    @classmethod
    def build_envelope_params(
            cls,
            *,
            snapshot: TestCatalogEntrySnapshot,
            inputs: Mapping[str, Any]
        ) -> Mapping[str, Any]:
        """
            Produce the JSON-serializable params dict the
            dispatcher embeds in :class:`JobEnvelope.params`.
        """
        raise NotImplementedError("Subclasses must implement build_envelope_params")
