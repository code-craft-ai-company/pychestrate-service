"""
.. module:: ingest.result.extensions.artifact_classifier
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``ArtifactClassifierExtension`` resource base.

.. moduleauthor:: Code Craft AI LLC

5-result-ingest-watcher walks each completed run's result tree and
calls every loaded :class:`ArtifactClassifierExtension` to assign a
``(category, tags)`` label to each file. The first non-``OTHER``
classification wins; the ingest pipeline persists the labels
alongside the artifact row so downstream filters (UI, retention,
metrics) can group by category without re-parsing the file.

Categories are documented constants — the in-tree set is small and
stable, so consumers can switch on them without runtime catalog
lookups. Subclasses may emit additional category strings; the
ingest pipeline treats any unrecognized category as the wire value
opaquely.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import ClassVar, Tuple

from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension


CATEGORY_LOG: str = "log"
CATEGORY_REPORT: str = "report"
CATEGORY_DIAGNOSTIC: str = "diagnostic"
CATEGORY_TASKING: str = "tasking"
CATEGORY_OTHER: str = "other"


@dataclass(frozen=True)
class ArtifactClassification:
    """
        Outcome of classifying one file.

        :param category: One of the ``CATEGORY_*`` constants or an
                         extension-defined string.
        :param tags: Tuple of additional descriptors (e.g.,
                     ``("testbase",)``) that retention / UI use to
                     filter without re-parsing.
        :param matched: True iff the classifier owned this file. The
                        ingest pipeline keeps walking subsequent
                        classifiers when ``matched`` is False.
    """
    category: str
    tags: Tuple[str, ...] = field(default_factory=tuple)
    matched: bool = True


CLASSIFICATION_NO_MATCH: ArtifactClassification = ArtifactClassification(
    category=CATEGORY_OTHER,
    tags=tuple(),
    matched=False,
)


class ArtifactClassifierExtension(ResourceExtension):
    """
        Base class for an artifact classifier contributed to
        ``5-result-ingest-watcher``.

        Subclasses set :attr:`classifier_name` and implement
        :meth:`classify`. Implementations should return
        :data:`CLASSIFICATION_NO_MATCH` when they do not own the file
        so the next classifier in precedence order gets a chance.
    """

    resource_extension_name: ClassVar[str] = "artifact_classifier"
    classifier_name: ClassVar[str] = ""

    is_published: ClassVar[bool] = True
    published_docs_url: ClassVar[str] = (
        "https://docs.pychestrate.io/plugin-api/ArtifactClassifierExtension"
    )
    published_reference: ClassVar[str] = (
        "ccai.pychestrate.webservice.ingest.result.extensions.testbase_classifier"
        ".TestbaseArtifactClassifier"
    )

    @classmethod
    def classify(
            cls,
            *,
            relative_path: str,
            mime_type: str,
            magic_prefix: bytes
        ) -> ArtifactClassification:
        """
            Inspect a file and return its classification.

            :param relative_path: Path of the file relative to the run
                                  result root (e.g.,
                                  ``"diagnostics/host.log"``).
            :param mime_type: Best-effort MIME type from the ingest
                              scanner; may be empty when unknown.
            :param magic_prefix: First few bytes of the file (already
                                 read by the scanner). Empty bytes
                                 when the file was empty / unreadable.

            :returns: :class:`ArtifactClassification`.
        """
        raise NotImplementedError("Subclasses must implement classify")
