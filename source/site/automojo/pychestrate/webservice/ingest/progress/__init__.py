"""
.. module:: ingest.progress
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-5 progress receiver — testbase ForwardingInfo intake.

.. moduleauthor:: Automation Mojo LLC

Public surface:

* :class:`ProgressSummary`, :class:`ProgressRecord` — caller-facing
  IO shapes (matching testbase ``ForwardingInfo``).
* :func:`ingest_summary`, :func:`ingest_record`,
  :func:`get_summary`, :func:`list_records` — service API.
* :class:`TestBaseProgressParser` — in-tree
  ``progress_parser`` factory protocol implementation.
* :func:`register_builtin_extensions` — seed the registry.
* Persistence rows: :class:`RunProgressSummary`,
  :class:`RunProgressRecord`, :class:`RunProgressCounters`.
* Topic constants: :class:`ProgressEventTopics`.
* Errors: :class:`ProgressError`,
  :class:`ProgressClientMismatchError`,
  :class:`ProgressUnknownRunError`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.ingest.progress.errors import (
    ProgressClientMismatchError,
    ProgressError,
    ProgressUnknownRunError,
)
from automojo.pychestrate.webservice.ingest.progress.events import (
    ProgressEventTopics,
)
from automojo.pychestrate.webservice.ingest.progress.factories.testbase_v1 import (
    TestBaseProgressParser,
)
from automojo.pychestrate.webservice.ingest.progress.models import (
    RunProgressCounters,
    RunProgressRecord,
    RunProgressSummary,
)
from automojo.pychestrate.webservice.ingest.progress.schema import (
    ProgressRecord,
    ProgressSummary,
)
from automojo.pychestrate.webservice.ingest.progress.service import (
    get_summary,
    ingest_record,
    ingest_summary,
    list_records,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``progress_parser`` factory
        implementations.
    """
    register_factory_implementation(implementation=TestBaseProgressParser)
    return
