"""
.. module:: orchestration.test.catalog.factories.testbase_project
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: TestbaseProjectImporter — reference catalog importer.

.. moduleauthor:: Automation Mojo LLC

The reference importer accepts an explicit list of
``{entries: [{...}, ...]}`` payloads — sufficient for M1 tests
and a manual-curation pathway. M2 wires it to walk a testbase
project tree and discover entries via the testbase manifest.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping

from automojo.pychestrate.webservice.orchestration.test.catalog.factories.importer_protocol import (
    TestCatalogImporterProtocol,
)
from automojo.pychestrate.webservice.orchestration.test.catalog.payloads import (
    ImporterEntryPayload,
)


TESTBASE_PROJECT_IMPORTER_TAG: str = "testbase-project"


class TestbaseProjectImporter(TestCatalogImporterProtocol):
    """
        Reference importer. Accepts a source dict shaped like:

        ``{"entries": [{"entry_key": "...", "display_name": "...",
                        "description": "...",
                        "required_capability_tags": [...],
                        "param_schema": {...},
                        "raw_metadata": {"runner_kind": "testbase",
                                         "includes": ["..."], ...}}, ...]}``

        Returns one :class:`ImporterEntryPayload` per dict.
    """

    factory_protocol_name: str = "test_catalog_importer"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def importer_tag(cls) -> str:
        rtnval = TESTBASE_PROJECT_IMPORTER_TAG
        return rtnval

    @classmethod
    def import_entries(
            cls,
            *,
            project_id: str,
            source: Mapping[str, Any]
        ) -> List[ImporterEntryPayload]:
        rtnval: List[ImporterEntryPayload] = []
        if source is None:
            return rtnval
        entries = source.get("entries", [])
        if isinstance(entries, list) is False:
            return rtnval
        for raw in entries:
            if isinstance(raw, dict) is False:
                continue
            entry_key = raw.get("entry_key", "") or ""
            if isinstance(entry_key, str) is False or len(entry_key) == 0:
                continue
            display_name = raw.get("display_name", entry_key) or entry_key
            description = raw.get("description", "") or ""
            tags_raw = raw.get("required_capability_tags", [])
            if isinstance(tags_raw, list) is False:
                tags_raw = []
            tags = tuple(str(item) for item in tags_raw)
            param_schema = raw.get("param_schema", {})
            if isinstance(param_schema, dict) is False:
                param_schema = {}
            raw_metadata = raw.get("raw_metadata", {})
            if isinstance(raw_metadata, dict) is False:
                raw_metadata = {}
            rtnval.append(
                ImporterEntryPayload(
                    entry_key=entry_key,
                    display_name=display_name,
                    description=description,
                    required_capability_tags=tags,
                    param_schema=dict(param_schema),
                    raw_metadata=dict(raw_metadata),
                )
            )
        return rtnval
