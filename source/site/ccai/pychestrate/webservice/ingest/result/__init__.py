"""
.. module:: ingest.result
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-5 result-tree ingester.

.. moduleauthor:: Code Craft AI LLC

The result ingester is the *passive* receiver of the testbase
result tree (``testrun_summary.json``,
``testrun_results_stream.jsos``, ``testrun_results.json``,
``artifacts/``, ``taskings/``, ``tc-by-products/``,
``diagnostics/``) once a client lands the tree on the shared
object store.

Public surface:

* :func:`scan_once` — invoked by callers (M1 tests, M2 daemon)
  to scan a single allocation's path and persist what it finds.
* :class:`TestBaseResultTreeParser`, :class:`JUnitXmlResultTreeParser` —
  in-tree ``result_tree_parser`` factories; the scanner picks the one
  that recognizes a tree's format.
* :func:`register_builtin_extensions`.
* Persistence: :class:`RunResultSummary`, :class:`TaskResult`,
  :class:`RunArtifact`, :class:`ResultScanAttempt`.
* Topics: :class:`ResultEventTopics`.
* Errors: :class:`ResultIngestError`,
  :class:`ResultTreeNotFoundError`,
  :class:`ResultTreeFormatError`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.ingest.result.errors import (
    ResultIngestError,
    ResultTreeFormatError,
    ResultTreeNotFoundError,
)
from ccai.pychestrate.webservice.ingest.result.events import (
    ResultEventTopics,
)
from ccai.pychestrate.webservice.ingest.result.factories.junit_xml import (
    JUnitXmlResultTreeParser,
)
from ccai.pychestrate.webservice.ingest.result.factories.testbase_v1 import (
    TestBaseResultTreeParser,
)
from ccai.pychestrate.webservice.ingest.result.models import (
    ResultScanAttempt,
    RunArtifact,
    RunResultSummary,
    TaskResult,
)
from ccai.pychestrate.webservice.ingest.result.scanner import (
    ScanOutcome,
    scan_once,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``result_tree_parser`` factories: testbase
        (the fallback) and JUnit / xUnit XML.
    """
    register_factory_implementation(implementation=TestBaseResultTreeParser)
    register_factory_implementation(implementation=JUnitXmlResultTreeParser)
    return
