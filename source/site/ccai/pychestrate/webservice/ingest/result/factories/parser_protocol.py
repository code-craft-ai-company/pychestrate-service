"""
.. module:: ingest.result.factories.parser_protocol
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``result_tree_parser`` factory protocol.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Mapping, Optional

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


@dataclass(frozen=True)
class ParsedSummary:
    """
        Roll-up the parser produces from the run's ``testrun_summary.json``.
    """
    tests_total: int
    tests_passed: int
    tests_failed: int
    tests_skipped: int
    tests_errored: int
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class ParsedTaskResult:
    """
        One persisted task row produced by the parser.
    """
    instance_uuid: str
    test_name: str
    rtype: str
    result: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class ParsedArtifact:
    """
        One catalogued artifact file.
    """
    relative_path: str
    classification: str
    size_bytes: int
    content_type: Optional[str]


@dataclass(frozen=True)
class ParsedResultTree:
    """
        Aggregate output of one parser run over a result-tree
        directory.
    """
    summary: Optional[ParsedSummary]
    tasks: List[ParsedTaskResult] = field(default_factory=list)
    artifacts: List[ParsedArtifact] = field(default_factory=list)
    files_seen: int = 0


class ResultTreeParserProtocol(FactoryProtocolBase):
    """
        Contract for parsers that walk a result-tree directory
        and produce a :class:`ParsedResultTree`.
    """

    factory_protocol_name: str = "result_tree_parser"
    protocol_schema_version: int = 1

    is_published: bool = True
    published_docs_url: str = "/docs/extensions/protocols/result_tree_parser.html"
    published_reference: str = (
        "ccai.pychestrate.webservice.ingest.result.factories.testbase_v1"
        ".TestBaseResultTreeParser"
    )

    @classmethod
    def parser_tag(cls) -> str:
        """
            Stable identifier persisted alongside parsed rows.
        """
        raise NotImplementedError("Subclasses must implement parser_tag")

    @classmethod
    def recognizes_tree(cls, *, tree_path: str) -> bool:
        """
            Whether the tree under ``tree_path`` is in this parser's
            format. The scanner uses the first registered parser (in
            precedence order) that recognizes a tree, and falls back to
            the first registered parser when none does. The default
            claims every tree.
        """
        rtnval = True
        return rtnval

    @classmethod
    def parse_tree(cls, *, tree_path: str) -> ParsedResultTree:
        """
            Walk the tree under ``tree_path`` and return its
            :class:`ParsedResultTree`. Implementations are
            tolerant of partial trees — a missing
            ``testrun_summary.json`` is reflected by
            ``summary=None`` rather than an exception.
        """
        raise NotImplementedError("Subclasses must implement parse_tree")
