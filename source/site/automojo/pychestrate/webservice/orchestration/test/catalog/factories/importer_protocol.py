"""
.. module:: orchestration.test.catalog.factories.importer_protocol
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``test_catalog_importer`` factory contract.

.. moduleauthor:: Automation Mojo LLC

A test-catalog importer takes some operator-supplied source
descriptor (a project path on disk, a gtest binary, a pytest
collect output) and produces a list of
:class:`ImporterEntryPayload` instances. The catalog upserts each
payload, idempotent on the natural key.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)
from automojo.pychestrate.webservice.orchestration.test.catalog.payloads import (
    ImporterEntryPayload,
)


class TestCatalogImporterProtocol(FactoryProtocolBase):
    """
        Contract for catalog importers.
    """

    factory_protocol_name: str = "test_catalog_importer"
    protocol_schema_version: int = 1

    @classmethod
    def importer_tag(cls) -> str:
        """
            Stable identifier the catalog persists alongside each
            entry — uniquifies the natural key when the same
            entry name comes from multiple importers.
        """
        raise NotImplementedError("Subclasses must implement importer_tag")

    @classmethod
    def import_entries(
            cls,
            *,
            project_id: str,
            source: Mapping[str, Any]
        ) -> List[ImporterEntryPayload]:
        """
            Walk the importer-specific source descriptor and
            return the entries discovered.

            :param project_id: Owning project UUID.
            :param source: Importer-specific descriptor (e.g.
                           ``{"project_path": "..."}``).

            :returns: List of payloads.
        """
        raise NotImplementedError("Subclasses must implement import_entries")
