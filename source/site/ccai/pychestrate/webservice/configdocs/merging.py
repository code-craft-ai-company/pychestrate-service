"""
.. module:: configdocs.merging
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Concatenation of the ``.d`` directory document form.

.. moduleauthor:: Code Craft AI LLC

Requirement 4.6 lets a domain's document be split across a ``.d``
directory -- ``landscape.d/lab-west.yaml`` beside
``landscape.d/lab-east.yaml`` -- loaded in lexical order and
concatenated.

Concatenation is deliberately dumber than an include graph: entries
append, mappings shallow-merge, and a repeated entry identity is an
error rather than an override. Lexical order is a tie-breaker for
mapping keys, never a precedence rule for entries, so no file can
silently redefine a machine declared by another. That is what makes
per-team file ownership safe.

Merging is canonical-model knowledge, not format knowledge, which is
why it lives here rather than on the format protocol.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, List, Mapping, Sequence, Tuple

from ccai.pychestrate.webservice.configdocs.domains import ConfigDocumentDomain
from ccai.pychestrate.webservice.configdocs.models import (
    ConfigDocument,
    CredentialsDocument,
    LandscapeDocument,
    ResourceSpecDocument,
    TopologyDocument,
)
from ccai.pychestrate.webservice.configdocs.validation import (
    Diagnostic,
    DiagnosticCodes,
    DiagnosticSeverity,
    ValidationReport,
    build_report,
)


def _merge_mappings(
        *,
        domain: str,
        field_name: str,
        sources: Sequence[Tuple[str, Mapping[str, Any]]],
        diagnostics: List[Diagnostic]
    ) -> Dict[str, Any]:
    """
        Shallow-merge mappings across files, warning on a key that two
        files give different values for.

        :param domain: Domain value, for diagnostics.
        :param field_name: Name of the merged field, for diagnostics.
        :param sources: ``(source_path, mapping)`` pairs in load order.
        :param diagnostics: Accumulator appended to in place.

        :returns: The merged mapping.
    """
    merged: Dict[str, Any] = {}
    origin: Dict[str, str] = {}

    for source_path, mapping in sources:
        for key, value in mapping.items():
            if key in merged and merged[key] != value:
                diagnostics.append(
                    Diagnostic(
                        code=DiagnosticCodes.DUPLICATE_ACROSS_FILES,
                        message=(
                            "Key '{}' in '{}' is given conflicting values by "
                            "'{}' and '{}'; the later file wins.".format(
                                key, field_name, origin[key], source_path,
                            )
                        ),
                        domain=domain,
                        source_path=source_path,
                        location="{}.{}".format(field_name, key),
                        severity=DiagnosticSeverity.WARNING,
                    ),
                )
            merged[key] = value
            origin[key] = source_path

    return merged


def _collect_entries(
        *,
        domain: str,
        field_name: str,
        documents: Sequence[ConfigDocument],
        diagnostics: List[Diagnostic]
    ) -> Tuple[Any, ...]:
    """
        Concatenate one entry collection across documents, rejecting a
        repeated identity.

        :param domain: Domain value, for diagnostics.
        :param field_name: Attribute holding the entry tuple.
        :param documents: Parsed documents in load order.
        :param diagnostics: Accumulator appended to in place.

        :returns: The concatenated entries.
    """
    collected: List[Any] = []
    seen: Dict[str, str] = {}

    for document in documents:
        for entry in getattr(document, field_name, tuple()):
            identity = getattr(entry, "identity", "")
            if identity in seen:
                diagnostics.append(
                    Diagnostic(
                        code=DiagnosticCodes.DUPLICATE_ACROSS_FILES,
                        message=(
                            "Entry identity '{}' is declared in both '{}' and "
                            "'{}'.".format(
                                identity, seen[identity], document.source_path,
                            )
                        ),
                        domain=domain,
                        source_path=document.source_path,
                        location="{}[{}]".format(field_name, identity),
                        severity=DiagnosticSeverity.ERROR,
                    ),
                )
                continue
            seen[identity] = document.source_path
            collected.append(entry)

    rtnval = tuple(collected)
    return rtnval


def merge_documents(
        *,
        domain: ConfigDocumentDomain,
        documents: Sequence[ConfigDocument],
        source_format: str
    ) -> Tuple[ConfigDocument, ValidationReport]:
    """
        Concatenate documents loaded from a ``.d`` directory.

        :param domain: The domain being merged.
        :param documents: Parsed documents, in lexical file order.
        :param source_format: ``format_name`` of the producing
                              implementation.

        :returns: ``(merged_document, report)``. The report carries an
                  error diagnostic per repeated entry identity and a
                  warning per conflicting mapping key.
    """
    diagnostics: List[Diagnostic] = []
    domain_value = domain.value

    source_paths = [document.source_path for document in documents]
    merged_path = os_path_join_display(paths=source_paths)

    extras = _merge_mappings(
        domain=domain_value,
        field_name="extra_attributes",
        sources=[(doc.source_path, doc.extra_attributes) for doc in documents],
        diagnostics=diagnostics,
    )

    if domain == ConfigDocumentDomain.LANDSCAPE:
        environment = _merge_mappings(
            domain=domain_value,
            field_name="environment",
            sources=[(doc.source_path, doc.environment) for doc in documents],
            diagnostics=diagnostics,
        )
        vpn = _merge_mappings(
            domain=domain_value,
            field_name="vpn",
            sources=[(doc.source_path, doc.vpn) for doc in documents],
            diagnostics=diagnostics,
        )
        merged: ConfigDocument = LandscapeDocument(
            source_path=merged_path,
            source_format=source_format,
            extra_attributes=extras,
            environment=environment,
            clients=_collect_entries(
                domain=domain_value, field_name="clients",
                documents=documents, diagnostics=diagnostics,
            ),
            infrastructure=_collect_entries(
                domain=domain_value, field_name="infrastructure",
                documents=documents, diagnostics=diagnostics,
            ),
            services=_collect_entries(
                domain=domain_value, field_name="services",
                documents=documents, diagnostics=diagnostics,
            ),
            vpn=vpn,
        )
    elif domain == ConfigDocumentDomain.TOPOLOGY:
        merged = TopologyDocument(
            source_path=merged_path,
            source_format=source_format,
            extra_attributes=extras,
            topologies=_collect_entries(
                domain=domain_value, field_name="topologies",
                documents=documents, diagnostics=diagnostics,
            ),
        )
    elif domain == ConfigDocumentDomain.CREDENTIALS:
        merged = CredentialsDocument(
            source_path=merged_path,
            source_format=source_format,
            extra_attributes=extras,
            credentials=_collect_credentials(
                domain=domain_value, documents=documents, diagnostics=diagnostics,
            ),
        )
    else:
        merged = ResourceSpecDocument(
            source_path=merged_path,
            source_format=source_format,
            extra_attributes=extras,
            specifications=_collect_entries(
                domain=domain_value, field_name="specifications",
                documents=documents, diagnostics=diagnostics,
            ),
        )

    rtnval = (merged, build_report(diagnostics=diagnostics))
    return rtnval


def _collect_credentials(
        *,
        domain: str,
        documents: Sequence[ConfigDocument],
        diagnostics: List[Diagnostic]
    ) -> Tuple[Any, ...]:
    """
        Concatenate credential references, keyed by ``name`` -- a
        credential reference's identity is its name, since that is
        what landscape entries cite.

        :param domain: Domain value, for diagnostics.
        :param documents: Parsed documents in load order.
        :param diagnostics: Accumulator appended to in place.

        :returns: The concatenated references.
    """
    collected: List[Any] = []
    seen: Dict[str, str] = {}

    for document in documents:
        for entry in getattr(document, "credentials", tuple()):
            name = entry.name
            if name in seen:
                diagnostics.append(
                    Diagnostic(
                        code=DiagnosticCodes.DUPLICATE_ACROSS_FILES,
                        message=(
                            "Credential '{}' is declared in both '{}' and "
                            "'{}'.".format(name, seen[name], document.source_path)
                        ),
                        domain=domain,
                        source_path=document.source_path,
                        location="credentials[{}]".format(name),
                        severity=DiagnosticSeverity.ERROR,
                    ),
                )
                continue
            seen[name] = document.source_path
            collected.append(entry)

    rtnval = tuple(collected)
    return rtnval


def os_path_join_display(*, paths: Sequence[str]) -> str:
    """
        A single ``source_path`` string standing for several files.

        A merged document came from more than one path, but
        ``source_path`` is one string; rendering the directory plus a
        count keeps diagnostics readable while the per-entry
        diagnostics carry the exact file.

        :param paths: The contributing paths, in load order.

        :returns: A display path.
    """
    if len(paths) == 0:
        return ""
    if len(paths) == 1:
        return paths[0]

    directory = os.path.dirname(paths[0])
    rtnval = "{} ({} files)".format(directory, len(paths))
    return rtnval
