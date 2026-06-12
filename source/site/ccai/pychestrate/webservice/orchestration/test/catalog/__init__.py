"""
.. module:: orchestration.test.catalog
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 6-test-catalog — registered test suites.

.. moduleauthor:: Code Craft AI LLC

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

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.orchestration.test.catalog.canonicalization import (
    canonicalize_entry,
    compute_digest,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.catalog import (
    list_entries,
    retire_entry,
    snapshot_for_dispatch,
    upsert_entry,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.errors import (
    CatalogEntryNotFoundError,
    CatalogError,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.factories.testbase_project import (
    TestbaseProjectImporter,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.factories.importer_protocol import (
    TestCatalogImporterProtocol,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.models import (
    TestCatalogEntry,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.payloads import (
    ImporterEntryPayload,
    TestCatalogEntrySnapshot,
    TestCatalogEntryView,
)
