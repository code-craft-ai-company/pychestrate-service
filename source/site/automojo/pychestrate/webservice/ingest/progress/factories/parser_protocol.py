"""
.. module:: ingest.progress.factories.parser_protocol
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``progress_parser`` factory protocol contract.

.. moduleauthor:: Automation Mojo LLC

A progress parser turns the inbound JSON body of a forwarded
summary / record post into the canonical
:class:`ProgressSummary` / :class:`ProgressRecord` shape.
Different runner formats (testbase default, gtest-json,
JUnit-live) ship as separate factory implementations and are
selected by the ``format_tag`` field on the inbound payload.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Mapping

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)
from automojo.pychestrate.webservice.ingest.progress.schema import (
    ProgressRecord,
    ProgressSummary,
)


class ProgressParserProtocol(FactoryProtocolBase):
    """
        Contract for a forwarded-progress parser. Implementations
        declare a ``format_tag`` they handle and parse the inbound
        dict to the canonical schema.
    """

    factory_protocol_name: str = "progress_parser"
    protocol_schema_version: int = 1

    is_published: bool = True
    published_docs_url: str = "https://docs.pychestrate.io/plugin-api/progress_parser"
    published_reference: str = (
        "automojo.pychestrate.webservice.ingest.progress.factories.testbase_v1"
        ".TestBaseProgressParser"
    )

    @classmethod
    def format_tag(cls) -> str:
        """
            Stable identifier the inbound payload's ``format_tag``
            field matches against. Used by the ingest service to
            select the right parser without iterating every
            registered implementation.

            :returns: Tag string.
        """
        raise NotImplementedError("Subclasses must implement format_tag")

    @classmethod
    def parse_summary(
            cls,
            *,
            run_id: str,
            client_id: str,
            payload: Mapping[str, Any]
        ) -> ProgressSummary:
        """
            Parse a forwarded summary payload.

            :param run_id: Run UUID from the URL path.
            :param client_id: Authenticated client UUID.
            :param payload: Decoded JSON dict.

            :returns: :class:`ProgressSummary`.
        """
        raise NotImplementedError("Subclasses must implement parse_summary")

    @classmethod
    def parse_record(
            cls,
            *,
            run_id: str,
            client_id: str,
            record_index: int,
            payload: Mapping[str, Any]
        ) -> ProgressRecord:
        """
            Parse a single forwarded record payload.

            :param run_id: Run UUID.
            :param client_id: Authenticated client UUID.
            :param record_index: Monotonically-increasing record id
                                 inside the run's stream.
            :param payload: Decoded JSON dict.

            :returns: :class:`ProgressRecord`.
        """
        raise NotImplementedError("Subclasses must implement parse_record")
