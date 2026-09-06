"""
.. module:: ingest.progress
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-5 progress receiver — testbase ForwardingInfo intake.

.. moduleauthor:: Code Craft AI LLC

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

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.ingest.progress.errors import (
    ProgressClientMismatchError,
    ProgressError,
    ProgressUnknownRunError,
)
from ccai.pychestrate.webservice.ingest.progress.events import (
    ProgressEventTopics,
)
from ccai.pychestrate.webservice.ingest.progress.factories.testbase_v1 import (
    TestBaseProgressParser,
)
from ccai.pychestrate.webservice.ingest.progress.models import (
    RunProgressCounters,
    RunProgressFrame,
    RunProgressRecord,
    RunProgressSummary,
)
from ccai.pychestrate.webservice.ingest.progress.schema import (
    SUPPORTED_FRAME_KINDS,
    FRAME_KIND_BUILD,
    FRAME_KIND_PROVISION,
    FRAME_KIND_RPA,
    FRAME_KIND_TEST,
    ProgressFrameEnvelope,
    ProgressRecord,
    ProgressSummary,
)
from ccai.pychestrate.webservice.ingest.progress.service import (
    get_latest_frame,
    get_summary,
    ingest_frame,
    ingest_record,
    ingest_summary,
    list_frames,
    list_records,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``progress_parser`` factory
        implementations.
    """
    register_factory_implementation(implementation=TestBaseProgressParser)
    return
