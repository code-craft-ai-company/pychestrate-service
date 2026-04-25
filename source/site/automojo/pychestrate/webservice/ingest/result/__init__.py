"""
.. module:: ingest.result
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-5 result-tree ingester.

.. moduleauthor:: Automation Mojo LLC

The result ingester is the *passive* receiver of the testbase
result tree (``testrun_summary.json``,
``testrun_results_stream.jsos``, ``testrun_results.json``,
``artifacts/``, ``taskings/``, ``tc-by-products/``,
``diagnostics/``) once a client lands the tree on the shared
object store.

Public surface:

* :func:`scan_once` — invoked by callers (M1 tests, M2 daemon)
  to scan a single allocation's path and persist what it finds.
* :class:`TestBaseResultTreeParser` — in-tree
  ``result_tree_parser`` factory.
* :func:`register_builtin_extensions`.
* Persistence: :class:`RunResultSummary`, :class:`TaskResult`,
  :class:`RunArtifact`, :class:`ResultScanAttempt`.
* Topics: :class:`ResultEventTopics`.
* Errors: :class:`ResultIngestError`,
  :class:`ResultTreeNotFoundError`,
  :class:`ResultTreeFormatError`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.ingest.result.errors import (
    ResultIngestError,
    ResultTreeFormatError,
    ResultTreeNotFoundError,
)
from automojo.pychestrate.webservice.ingest.result.events import (
    ResultEventTopics,
)
from automojo.pychestrate.webservice.ingest.result.factories.testbase_v1 import (
    TestBaseResultTreeParser,
)
from automojo.pychestrate.webservice.ingest.result.models import (
    ResultScanAttempt,
    RunArtifact,
    RunResultSummary,
    TaskResult,
)
from automojo.pychestrate.webservice.ingest.result.scanner import (
    ScanOutcome,
    scan_once,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``result_tree_parser`` factory.
    """
    register_factory_implementation(implementation=TestBaseResultTreeParser)
    return
