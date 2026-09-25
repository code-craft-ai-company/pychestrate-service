"""
.. module:: configdocs.loader
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Resolve, parse, and validate configuration documents.

.. moduleauthor:: Code Craft AI LLC

The loader owns the sequence -- locate, probe for domain bleed, parse,
validate, merge -- and owns nothing about any particular format.

Requirement 8.2 asks for every diagnostic across all four domains
before anything raises, so the default mode accumulates: a bleed or a
parse failure becomes a diagnostic on the returned report rather than
an exception, and the caller decides when to stop. ``strict=True``
inverts that for callers that want the specific exception type at the
first problem -- a CLI import, say, where there is nothing to
accumulate across.

Loading never writes. Projection onto the database is a separate,
explicitly invoked step (M4).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Type

from ccai.pychestrate.core.defaults import utc_now

from ccai.pychestrate.webservice.configdocs.domains import (
    DEFAULT_FORMAT_NAME,
    ConfigDocumentDomain,
)
from ccai.pychestrate.webservice.configdocs.errors import (
    ConfigDocumentDomainBleedError,
    ConfigDocumentParseError,
)
from ccai.pychestrate.webservice.configdocs.merging import merge_documents
from ccai.pychestrate.webservice.configdocs.models import (
    DOCUMENT_TYPES,
    ConfigDocument,
)
from ccai.pychestrate.webservice.configdocs.protocol import (
    ConfigDocumentFormatProtocol,
)
from ccai.pychestrate.webservice.configdocs.resolver import (
    claimed_keys_by_other_domains,
    resolve_document_paths,
    resolve_format_implementation,
)
from ccai.pychestrate.webservice.configdocs.validation import (
    Diagnostic,
    DiagnosticCodes,
    DiagnosticSeverity,
    ValidationReport,
    build_report,
    merge_reports,
)


_LOGGER = logging.getLogger("pychestrate.configdocs")


@dataclass(frozen=True)
class LoadOutcome:
    """
        The result of loading one domain's document.

        :param domain: The domain loaded.
        :param format_name: The format that read it.
        :param implementation: Qualified name of the implementation
                               class, for the admin surface
                               (Requirement 5.4).
        :param source_paths: Files that contributed, in load order.
                             Empty when the domain is not configured.
        :param document: The canonical document. An empty document of
                         the right type when not configured -- never
                         None, so callers need no absent-case branch.
        :param report: Accumulated diagnostics.
        :param configured: False when no document file was found.
        :param loaded_at: When the load ran.
    """
    domain: ConfigDocumentDomain
    format_name: str
    implementation: str
    source_paths: Tuple[str, ...]
    document: ConfigDocument
    report: ValidationReport
    configured: bool
    loaded_at: datetime

    @property
    def ok(self) -> bool:
        """
            True when nothing blocks projection.

            :returns: True when the report carries no errors.
        """
        rtnval = self.report.ok
        return rtnval

    def to_mapping(self) -> Dict[str, Any]:
        """
            Render for the admin surface. The document itself is not
            included -- it can be large, and the admin listing wants
            provenance, not content.

            :returns: Dict of the outcome's metadata.
        """
        rtnval = {
            "domain": self.domain.value,
            "format": self.format_name,
            "implementation": self.implementation,
            "source_paths": list(self.source_paths),
            "configured": self.configured,
            "loaded_at": self.loaded_at.isoformat(),
            "report": self.report.to_mapping(),
        }
        return rtnval


def _empty_document(
        *,
        domain: ConfigDocumentDomain,
        format_name: str
    ) -> ConfigDocument:
    """
        The empty canonical document for an unconfigured domain
        (Requirement 4.5).

        :param domain: The domain.
        :param format_name: The selected format name.

        :returns: An empty document of the domain's type.
    """
    document_type = DOCUMENT_TYPES[domain]
    rtnval = document_type(source_path="", source_format=format_name)
    return rtnval


def _read_text(*, path: str) -> str:
    """
        Read a document's text as UTF-8.

        :param path: Absolute path.

        :returns: The file's text.
    """
    with open(path, "r", encoding="utf-8") as handle:
        rtnval = handle.read()
    return rtnval


def _check_domain_bleed(
        *,
        domain: ConfigDocumentDomain,
        implementation: Type[ConfigDocumentFormatProtocol],
        path: str,
        text: str,
        foreign_claims: Tuple[Tuple[str, str], ...]
    ) -> Optional[Tuple[Tuple[str, ...], str]]:
    """
        Detect top-level keys another domain claims (Requirement 4.3).

        Runs before :meth:`parse` so a misfiled document is rejected
        without a full parser running over it.

        :param domain: The domain being loaded.
        :param implementation: The selected format implementation.
        :param path: Absolute path of the document.
        :param text: The document's text.
        :param foreign_claims: ``(key, owning_domain)`` pairs from the
                               other domains.

        :returns: ``(offending_keys, owning_domain)`` or None when
                  clean.
    """
    own_keys = set(implementation.claimed_top_level_keys())

    try:
        present = set(implementation.probe_top_level_keys(path=path, text=text))
    except Exception:
        # A probe that cannot read the document is not the bleed
        # check's problem; parse() will produce the real diagnostic.
        return None

    offenders: List[str] = []
    owner = ""
    for key, owning_domain in foreign_claims:
        if key in own_keys:
            continue
        if key in present:
            offenders.append(key)
            owner = owning_domain

    if len(offenders) == 0:
        return None

    rtnval = (tuple(sorted(set(offenders))), owner)
    return rtnval


def load_document(
        *,
        domain: ConfigDocumentDomain,
        format_name: Optional[str] = None,
        format_names: Optional[Dict[ConfigDocumentDomain, str]] = None,
        config_dir: Optional[str] = None,
        presence_dir: Optional[str] = None,
        environ: Optional[dict] = None,
        strict: bool = False
    ) -> LoadOutcome:
    """
        Load one domain's document.

        :param domain: The domain to load.
        :param format_name: Format selection for this domain,
                            defaulting to ``codecraftai``.
        :param format_names: Per-domain selections, used to build the
                             other domains' bleed claim list.
        :param config_dir: Explicit config directory.
        :param presence_dir: Explicit presence directory.
        :param environ: Environment mapping, defaulting to
                        ``os.environ``.
        :param strict: When True, raise
                       :class:`ConfigDocumentDomainBleedError` or
                       :class:`ConfigDocumentParseError` at the first
                       problem instead of recording a diagnostic.

        :returns: The outcome.
        :raises: ConfigurationError when the selected format names no
                 registered implementation, or when a per-domain path
                 override points at nothing.
    """
    if format_name is None:
        format_name = DEFAULT_FORMAT_NAME

    implementation = resolve_format_implementation(
        domain=domain, format_name=format_name,
    )
    implementation_name = "{}.{}".format(
        implementation.__module__, implementation.__qualname__,
    )

    paths = resolve_document_paths(
        domain=domain,
        basenames=implementation.file_basenames(),
        config_dir=config_dir,
        presence_dir=presence_dir,
        environ=environ,
    )

    if len(paths) == 0:
        _LOGGER.debug(
            "pychestrate: domain '%s' is not configured; no document found.",
            domain.value,
        )
        rtnval = LoadOutcome(
            domain=domain,
            format_name=format_name,
            implementation=implementation_name,
            source_paths=tuple(),
            document=_empty_document(domain=domain, format_name=format_name),
            report=build_report(diagnostics=None),
            configured=False,
            loaded_at=utc_now(),
        )
        return rtnval

    foreign_claims = claimed_keys_by_other_domains(
        domain=domain, format_names=format_names,
    )

    parsed: List[ConfigDocument] = []
    reports: List[ValidationReport] = []
    diagnostics: List[Diagnostic] = []

    for path in paths:
        text = _read_text(path=path)

        bleed = _check_domain_bleed(
            domain=domain,
            implementation=implementation,
            path=path,
            text=text,
            foreign_claims=foreign_claims,
        )
        if bleed is not None:
            offending_keys, owner = bleed
            if strict is True:
                raise ConfigDocumentDomainBleedError(
                    domain=domain.value,
                    source_path=path,
                    offending_keys=offending_keys,
                    claimed_by=owner,
                )
            diagnostics.append(
                Diagnostic(
                    code=DiagnosticCodes.DOMAIN_BLEED,
                    message=(
                        "Document carries top-level keys owned by the '{}' "
                        "domain: {}. Each domain owns its own file.".format(
                            owner, list(offending_keys),
                        )
                    ),
                    domain=domain.value,
                    source_path=path,
                    location="",
                    severity=DiagnosticSeverity.ERROR,
                ),
            )
            continue

        try:
            document = implementation.parse(path=path, text=text)
        except ConfigDocumentParseError as parse_error:
            if strict is True:
                raise
            diagnostics.append(
                Diagnostic(
                    code=DiagnosticCodes.PARSE_FAILED,
                    message=str(parse_error).replace(os.linesep, " "),
                    domain=domain.value,
                    source_path=path,
                    location="",
                    severity=DiagnosticSeverity.ERROR,
                ),
            )
            continue

        parsed.append(document)
        reports.append(implementation.validate(document=document))

    if len(parsed) == 0:
        merged: ConfigDocument = _empty_document(
            domain=domain, format_name=format_name,
        )
    elif len(parsed) == 1:
        merged = parsed[0]
    else:
        merged, merge_report = merge_documents(
            domain=domain, documents=parsed, source_format=format_name,
        )
        reports.append(merge_report)

    report = merge_reports(
        reports=[build_report(diagnostics=diagnostics)] + reports,
    )

    rtnval = LoadOutcome(
        domain=domain,
        format_name=format_name,
        implementation=implementation_name,
        source_paths=tuple(paths),
        document=merged,
        report=report,
        configured=True,
        loaded_at=utc_now(),
    )
    return rtnval


def load_all_documents(
        *,
        format_names: Optional[Dict[ConfigDocumentDomain, str]] = None,
        config_dir: Optional[str] = None,
        presence_dir: Optional[str] = None,
        environ: Optional[dict] = None
    ) -> Dict[ConfigDocumentDomain, LoadOutcome]:
    """
        Load every domain, accumulating diagnostics across all four
        (Requirement 8.2).

        Never raises for a document-level problem; the caller inspects
        each outcome's report. A deployment misconfiguration -- an
        unknown format name, a dangling path override -- still raises,
        because that is a startup failure rather than a document to
        fix.

        :param format_names: Per-domain format selections.
        :param config_dir: Explicit config directory.
        :param presence_dir: Explicit presence directory.
        :param environ: Environment mapping, defaulting to
                        ``os.environ``.

        :returns: Mapping of domain to outcome, one entry per domain.
    """
    if format_names is None:
        format_names = {}

    outcomes: Dict[ConfigDocumentDomain, LoadOutcome] = {}
    for domain in ConfigDocumentDomain:
        outcomes[domain] = load_document(
            domain=domain,
            format_name=format_names.get(domain, None),
            format_names=format_names,
            config_dir=config_dir,
            presence_dir=presence_dir,
            environ=environ,
            strict=False,
        )

    return outcomes


def combined_report(
        *,
        outcomes: Dict[ConfigDocumentDomain, LoadOutcome]
    ) -> ValidationReport:
    """
        One report spanning every loaded domain.

        :param outcomes: The per-domain outcomes.

        :returns: The merged report.
    """
    ordered = [outcomes[domain].report for domain in ConfigDocumentDomain
               if domain in outcomes]
    rtnval = merge_reports(reports=ordered)
    return rtnval
