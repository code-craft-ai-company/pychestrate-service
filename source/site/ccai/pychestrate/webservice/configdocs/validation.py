"""
.. module:: configdocs.validation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Diagnostics and the accumulating validation report.

.. moduleauthor:: Code Craft AI LLC

Requirement 8.2 requires every diagnostic across all four domains to
be accumulated before anything raises, so an operator fixes their
documents in one pass rather than one error per run. That makes the
report -- not an exception -- the primary result of validation.

Not to be confused with :class:`ccai.pychestrate.webservice.pods.
factories.validator.ValidationReport`, which is the pod-spec
validator's simpler string-list report. This one carries structured
:class:`Diagnostic` rows with stable codes so the admin surface can
group and link them.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple


class DiagnosticSeverity(str, enum.Enum):
    """
        Whether a diagnostic blocks projection.
    """
    ERROR = "error"
    WARNING = "warning"


class DiagnosticCodes:
    """
        Stable diagnostic codes (Requirement 8.1). These are part of
        the operator-facing contract -- rename one and you break
        anybody filtering their logs on it.
    """

    #: A device entry carried the legacy single ``host`` string
    #: instead of an ``addresses`` mapping (Requirement 3.4).
    LEGACY_HOST_FIELD: str = "legacy_host_field"

    #: The document carried a top-level key another domain claims.
    DOMAIN_BLEED: str = "domain_bleed"

    #: Two entries in one document resolved to one identity.
    DUPLICATE_IDENTITY: str = "duplicate_identity"

    #: The same entry identity appeared in two files of a ``.d`` set.
    DUPLICATE_ACROSS_FILES: str = "duplicate_across_files"

    #: A credentials document carried inline secret material.
    INLINE_SECRET: str = "inline_secret"

    #: A credential reference named no resolvable credential.
    UNRESOLVED_CREDENTIAL: str = "unresolved_credential"

    #: The format implementation could not parse the document.
    PARSE_FAILED: str = "parse_failed"

    #: Two implementations claimed one (domain, format_name) pair.
    FORMAT_SHADOWED: str = "format_shadowed"

    #: An entry omitted a field the canonical model requires.
    MISSING_REQUIRED_FIELD: str = "missing_required_field"

    #: The document parsed but declared a schema version this build
    #: does not understand.
    UNSUPPORTED_SCHEMA_VERSION: str = "unsupported_schema_version"


@dataclass(frozen=True)
class Diagnostic:
    """
        One finding against one document.

        :param code: A :class:`DiagnosticCodes` value.
        :param message: Human-readable description. Never carries
                        secret material.
        :param domain: The document domain that produced it.
        :param source_path: Absolute path of the offending document.
        :param location: Pointer within the document, e.g.
                         ``clients[3].host``. Empty when the finding
                         is about the document as a whole.
        :param severity: Whether the finding blocks projection.
    """
    code: str
    message: str
    domain: str
    source_path: str = ""
    location: str = ""
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR

    def to_mapping(self) -> Dict[str, Any]:
        """
            Render as a plain mapping for API and audit surfaces.

            :returns: Dict of the diagnostic's fields.
        """
        rtnval = {
            "code": self.code,
            "message": self.message,
            "domain": self.domain,
            "source_path": self.source_path,
            "location": self.location,
            "severity": self.severity.value,
        }
        return rtnval

    def __str__(self) -> str:
        where = self.source_path
        if len(self.location) > 0:
            where = "{}:{}".format(where, self.location)
        rtnval = "[{}] {} ({})".format(self.code, self.message, where)
        return rtnval


@dataclass(frozen=True)
class ValidationReport:
    """
        Accumulated diagnostics for one or more documents.

        Reports are immutable; :meth:`with_diagnostic` and
        :meth:`merged_with` return new reports. That keeps a report
        safe to hand to a caller without it being mutated underneath
        them by a later domain's load.
    """
    diagnostics: Tuple[Diagnostic, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> Tuple[Diagnostic, ...]:
        """
            Blocking diagnostics.

            :returns: Tuple of error-severity diagnostics.
        """
        rtnval = tuple([
            item for item in self.diagnostics
            if item.severity == DiagnosticSeverity.ERROR
        ])
        return rtnval

    @property
    def warnings(self) -> Tuple[Diagnostic, ...]:
        """
            Non-blocking diagnostics.

            :returns: Tuple of warning-severity diagnostics.
        """
        rtnval = tuple([
            item for item in self.diagnostics
            if item.severity == DiagnosticSeverity.WARNING
        ])
        return rtnval

    @property
    def ok(self) -> bool:
        """
            True when nothing blocks projection.

            :returns: True when the report carries no errors.
        """
        rtnval = len(self.errors) == 0
        return rtnval

    def with_diagnostic(self, *, diagnostic: Diagnostic) -> "ValidationReport":
        """
            Return a copy carrying one more diagnostic.

            :param diagnostic: The finding to append.

            :returns: A new report.
        """
        rtnval = ValidationReport(diagnostics=self.diagnostics + (diagnostic,))
        return rtnval

    def merged_with(self, *, other: "ValidationReport") -> "ValidationReport":
        """
            Return a copy carrying this report's diagnostics followed
            by ``other``'s.

            :param other: The report to append.

            :returns: A new report.
        """
        rtnval = ValidationReport(diagnostics=self.diagnostics + other.diagnostics)
        return rtnval

    def to_mapping(self) -> Dict[str, Any]:
        """
            Render as a plain mapping for API and audit surfaces.

            :returns: Dict with ``ok``, ``errors``, ``warnings``.
        """
        rtnval = {
            "ok": self.ok,
            "errors": [item.to_mapping() for item in self.errors],
            "warnings": [item.to_mapping() for item in self.warnings],
        }
        return rtnval


def build_report(*, diagnostics: Optional[Iterable[Diagnostic]] = None) -> ValidationReport:
    """
        Build a report from an iterable of diagnostics.

        :param diagnostics: The findings, or None for an empty report.

        :returns: The report.
    """
    if diagnostics is None:
        rtnval = ValidationReport(diagnostics=tuple())
    else:
        rtnval = ValidationReport(diagnostics=tuple(diagnostics))
    return rtnval


def merge_reports(*, reports: Sequence[ValidationReport]) -> ValidationReport:
    """
        Accumulate several reports into one (Requirement 8.2).

        :param reports: The reports to combine, in order.

        :returns: One report carrying every diagnostic.
    """
    collected: list = []
    for report in reports:
        collected.extend(report.diagnostics)

    rtnval = ValidationReport(diagnostics=tuple(collected))
    return rtnval
