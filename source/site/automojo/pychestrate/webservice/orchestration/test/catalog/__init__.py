"""
.. module:: orchestration.test.catalog
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 6-test-catalog — registered test suites.

.. moduleauthor:: Automation Mojo LLC

Public surface:

* :class:`TestCatalogEntry` — persistence row.
* :class:`ImporterEntryPayload` / :class:`TestCatalogEntryView` /
  :class:`TestCatalogEntrySnapshot` — IO shapes.
* :func:`upsert_entry`, :func:`snapshot_for_dispatch`,
  :func:`list_entries`, :func:`retire_entry`,
  :func:`canonicalize_entry`, :func:`compute_digest`.
* :class:`TestbaseProjectImporter` — in-tree importer factory.
* :class:`TestCatalogImporterProtocol` — factory contract.
* Errors: :class:`CatalogError`, :class:`CatalogEntryNotFoundError`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.orchestration.test.catalog.canonicalization import (
    canonicalize_entry,
    compute_digest,
)
from automojo.pychestrate.webservice.orchestration.test.catalog.catalog import (
    list_entries,
    retire_entry,
    snapshot_for_dispatch,
    upsert_entry,
)
from automojo.pychestrate.webservice.orchestration.test.catalog.errors import (
    CatalogEntryNotFoundError,
    CatalogError,
)
from automojo.pychestrate.webservice.orchestration.test.catalog.factories.testbase_project import (
    TestbaseProjectImporter,
)
from automojo.pychestrate.webservice.orchestration.test.catalog.factories.importer_protocol import (
    TestCatalogImporterProtocol,
)
from automojo.pychestrate.webservice.orchestration.test.catalog.models import (
    TestCatalogEntry,
)
from automojo.pychestrate.webservice.orchestration.test.catalog.payloads import (
    ImporterEntryPayload,
    TestCatalogEntrySnapshot,
    TestCatalogEntryView,
)
