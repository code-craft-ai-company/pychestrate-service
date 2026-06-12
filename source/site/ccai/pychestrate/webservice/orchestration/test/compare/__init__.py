"""
.. module:: orchestration.test.compare
    :synopsis: 6-compare-runs — per-test diff between two runs.

Public surface:

* :class:`CompareReport`, :class:`CompareStatus` —
  persistence row + enum.
* :class:`TestDiff`, :class:`TestDiffStatus`,
  :class:`CompareReportView` — IO shapes.
* :func:`compute_test_diffs`, :func:`build_compare_report`,
  :func:`get_compare_report`,
  :func:`select_diff_viewer`.
* :class:`ArtifactDiffViewerProtocol` factory contract +
  reference :class:`GenericTwoPaneDiffViewer`.
* :class:`CompareEventTopics`.
* Errors: :class:`CompareError`,
  :class:`CompareReportNotFoundError`,
  :class:`CompareInputInvalidError`,
  :class:`NoMatchingDiffViewerError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.orchestration.test.compare.errors import (
    CompareError,
    CompareInputInvalidError,
    CompareReportNotFoundError,
    NoMatchingDiffViewerError,
)
from ccai.pychestrate.webservice.orchestration.test.compare.events import (
    CompareEventTopics,
)
from ccai.pychestrate.webservice.orchestration.test.compare.factories.diff_viewer_protocol import (
    ArtifactDiffViewerProtocol,
    DiffViewerMatch,
    DiffViewerRecord,
)
from ccai.pychestrate.webservice.orchestration.test.compare.factories.generic_two_pane_viewer import (
    GenericTwoPaneDiffViewer,
)
from ccai.pychestrate.webservice.orchestration.test.compare.models import (
    CompareReport,
    CompareStatus,
)
from ccai.pychestrate.webservice.orchestration.test.compare.service import (
    CompareReportView,
    DiffArtifactRef,
    DiffViewerChoice,
    OutcomeForRun,
    TestDiff,
    TestDiffStatus,
    build_compare_report,
    compute_test_diffs,
    get_compare_report,
    select_diff_viewer,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`GenericTwoPaneDiffViewer`
        reference renderer.
    """
    register_factory_implementation(implementation=GenericTwoPaneDiffViewer)
    return
