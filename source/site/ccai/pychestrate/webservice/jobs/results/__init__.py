"""
.. module:: jobs.results
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Shared results backend — per-run path allocation on the object store.

.. moduleauthor:: Code Craft AI LLC

Public surface:

* :class:`SharedResultsBackend` — facade with ``allocate`` /
  ``resolve``.
* :class:`AllocatedResultPath` — read-model returned to callers.
* :func:`build_canonical_prefix` — deterministic naming helper.
* :class:`AllocationNotFoundError` — exception raised by
  ``resolve`` when an ``allocate`` was never recorded for the
  given run.

The dispatcher (``5-job-dispatch``) calls ``allocate`` before
building the envelope so the envelope's ``results.backend_key_prefix``
points at the freshly-allocated path. The result-watcher
(``5-result-ingest-watcher``) calls ``resolve`` to turn a run id
into the prefix it should poll.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.jobs.results.backend import (
    AllocatedResultPath,
    SharedResultsBackend,
)
from ccai.pychestrate.webservice.jobs.results.errors import (
    AllocationNotFoundError,
    ArtifactPathInvalidError,
    PresignSignatureInvalidError,
    TooManyArtifactPathsError,
)
from ccai.pychestrate.webservice.jobs.results.models import (
    SharedResultsAllocation,
)
from ccai.pychestrate.webservice.jobs.results.path_builder import (
    build_canonical_prefix,
    canonicalize_component,
)
from ccai.pychestrate.webservice.jobs.results.presign import (
    ArtifactUploadTarget,
)
