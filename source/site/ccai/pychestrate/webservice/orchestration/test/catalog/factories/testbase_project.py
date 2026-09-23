"""
.. module:: orchestration.test.catalog.factories.testbase_project
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: TestbaseProjectImporter — reference catalog importer.

.. moduleauthor:: Code Craft AI LLC

The reference importer turns an operator-supplied source into catalog
entries. The service cannot walk a testbase project tree -- the test
code lives with the pods that run it -- so the source names the tests
explicitly, in either of two forms:

* ``includes`` -- testbase include names (the dotted module / package
  paths ``testbase testing run --includes`` takes), one entry per
  include, plus the optional ``root`` (the testbase root the pod runs
  from, e.g. ``source/testroots/ccai``), ``ref`` (the branch the tests
  are checked out at) and ``required_capability_tags`` that apply to
  every entry;
* ``entries`` -- fully described entry dicts.

A source that yields no entries, or that holds a malformed include or
entry, is refused with a :class:`ValueError` that names the problem --
an import never "succeeds" with nothing imported (audit ORC-06).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import Any, List, Mapping, Tuple

from ccai.pychestrate.webservice.orchestration.test.catalog.factories.importer_protocol import (
    TestCatalogImporterProtocol,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.payloads import (
    ImporterEntryPayload,
)


TESTBASE_PROJECT_IMPORTER_TAG: str = "testbase-project"

#: The testbase runner kind every imported entry runs with.
TESTBASE_RUNNER_KIND: str = "testbase"

#: A testbase include expression as ``testbase testing run --includes``
#: takes it: ``pkg.module``, optionally followed by ``@TestClass`` and /
#: or ``#test_name`` (``pkg.module@#test_name`` selects one test).
TESTBASE_INCLUDE_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*"
    r"(@([A-Za-z_][A-Za-z0-9_]*)?)?"
    r"(#[A-Za-z_][A-Za-z0-9_]*)?$"
)

#: Upper bound on the entries one import may create.
MAX_IMPORT_ENTRIES: int = 2000


class TestbaseProjectImporter(TestCatalogImporterProtocol):
    """
        Reference importer. Accepts a source dict shaped like either

        ``{"includes": ["ccai.tests.singlehost.feature.test_x", ...],
           "root": "source/testroots/ccai", "ref": "main",
           "required_capability_tags": ["linux"]}``

        or

        ``{"entries": [{"entry_key": "...", "display_name": "...",
                        "description": "...",
                        "required_capability_tags": [...],
                        "param_schema": {...},
                        "raw_metadata": {"runner_kind": "testbase",
                                         "includes": ["..."], ...}}, ...]}``

        (both keys may be combined). Returns one
        :class:`ImporterEntryPayload` per include / entry.
    """

    factory_protocol_name: str = "test_catalog_importer"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def importer_tag(cls) -> str:
        rtnval = TESTBASE_PROJECT_IMPORTER_TAG
        return rtnval

    @classmethod
    def import_entries(
            cls,
            *,
            project_id: str,
            source: Mapping[str, Any]
        ) -> List[ImporterEntryPayload]:
        """
            Build the catalog payloads described by ``source``.

            :param project_id: Owning project UUID.
            :param source: ``includes`` / ``entries`` descriptor (see the
                           class docstring).

            :returns: One payload per include / entry (never empty).

            :raises: ValueError when the source is empty or holds a
                     malformed include / entry.
        """
        if source is None:
            source = {}

        issues: List[str] = []
        payloads: List[ImporterEntryPayload] = []

        include_payloads, include_issues = _payloads_from_includes(source=source)
        payloads.extend(include_payloads)
        issues.extend(include_issues)

        entry_payloads, entry_issues = _payloads_from_entries(source=source)
        payloads.extend(entry_payloads)
        issues.extend(entry_issues)

        if len(issues) > 0:
            err_lines = ["The import source has {} problem(s); nothing was imported.".format(
                len(issues),
            )]
            for index, issue in enumerate(issues):
                err_lines.append("  [{}] {}".format(index + 1, issue))
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg)

        if len(payloads) == 0:
            err_lines = ["Nothing to import: the source lists no tests."]
            err_lines.append(
                "Provide 'includes' (testbase include names such as"
                " ccai.tests.singlehost.feature.test_module, one per entry)"
                " or 'entries'."
            )
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg)

        if len(payloads) > MAX_IMPORT_ENTRIES:
            err_lines = ["The import source lists too many tests."]
            err_lines.append("COUNT: {}".format(len(payloads)))
            err_lines.append("MAXIMUM: {}".format(MAX_IMPORT_ENTRIES))
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg)

        rtnval = payloads
        return rtnval


def _optional_string(*, source: Mapping[str, Any], key: str, issues: List[str]) -> str:
    """
        Read an optional string field, recording a problem when it is
        present but not a string.

        :returns: The stripped value, or ``""``.
    """
    value = source.get(key, None)
    if value is None:
        return ""
    if isinstance(value, str) is False:
        issues.append("'{}' must be a string".format(key))
        return ""
    rtnval = value.strip()
    return rtnval


def _capability_tags(*, source: Mapping[str, Any], issues: List[str]) -> Tuple[str, ...]:
    """
        Read the optional ``required_capability_tags`` list applied to
        every include.

        :returns: The tags.
    """
    raw = source.get("required_capability_tags", None)
    if raw is None:
        return ()
    if isinstance(raw, list) is False:
        issues.append("'required_capability_tags' must be a list of strings")
        return ()
    tags: List[str] = []
    for item in raw:
        if isinstance(item, str) is False or len(item.strip()) == 0:
            issues.append("'required_capability_tags' entries must be non-empty strings")
            return ()
        tags.append(item.strip())
    rtnval = tuple(tags)
    return rtnval


def _payloads_from_includes(
        *, source: Mapping[str, Any]
    ) -> Tuple[List[ImporterEntryPayload], List[str]]:
    """
        One payload per testbase include in ``source["includes"]``.

        :returns: ``(payloads, issues)``.
    """
    issues: List[str] = []
    payloads: List[ImporterEntryPayload] = []
    raw_includes = source.get("includes", None)
    if raw_includes is None:
        return (payloads, issues)
    if isinstance(raw_includes, list) is False:
        issues.append("'includes' must be a list of testbase include names")
        return (payloads, issues)

    root = _optional_string(source=source, key="root", issues=issues)
    ref = _optional_string(source=source, key="ref", issues=issues)
    tags = _capability_tags(source=source, issues=issues)

    seen: List[str] = []
    for index, raw in enumerate(raw_includes):
        if isinstance(raw, str) is False:
            issues.append("includes[{}] is not a string".format(index))
            continue
        include = raw.strip()
        if len(include) == 0:
            continue
        if TESTBASE_INCLUDE_PATTERN.match(include) is None:
            issues.append(
                "includes[{}] {!r} is not a testbase include expression"
                " (pkg.module, optionally '@#test_name')".format(index, include)
            )
            continue
        if include in seen:
            continue
        seen.append(include)
        raw_metadata = {
            "runner_kind": TESTBASE_RUNNER_KIND,
            "includes": [include],
        }
        if len(root) > 0:
            raw_metadata["root"] = root
        if len(ref) > 0:
            raw_metadata["branch"] = ref
        if "#" in include:
            display_name = include.split("#")[-1]
        else:
            display_name = include.split("@")[0].split(".")[-1]
        payloads.append(
            ImporterEntryPayload(
                entry_key=include,
                display_name=display_name,
                description="",
                required_capability_tags=tags,
                param_schema={},
                raw_metadata=raw_metadata,
            )
        )
    rtnval = (payloads, issues)
    return rtnval


def _payloads_from_entries(
        *, source: Mapping[str, Any]
    ) -> Tuple[List[ImporterEntryPayload], List[str]]:
    """
        One payload per entry dict in ``source["entries"]``.

        :returns: ``(payloads, issues)``.
    """
    issues: List[str] = []
    payloads: List[ImporterEntryPayload] = []
    entries = source.get("entries", None)
    if entries is None:
        return (payloads, issues)
    if isinstance(entries, list) is False:
        issues.append("'entries' must be a list of entry objects")
        return (payloads, issues)
    for index, raw in enumerate(entries):
        if isinstance(raw, dict) is False:
            issues.append("entries[{}] is not an object".format(index))
            continue
        entry_key = raw.get("entry_key", "") or ""
        if isinstance(entry_key, str) is False or len(entry_key) == 0:
            issues.append("entries[{}] has no 'entry_key'".format(index))
            continue
        display_name = raw.get("display_name", entry_key) or entry_key
        description = raw.get("description", "") or ""
        tags_raw = raw.get("required_capability_tags", [])
        if isinstance(tags_raw, list) is False:
            tags_raw = []
        tags = tuple(str(item) for item in tags_raw)
        param_schema = raw.get("param_schema", {})
        if isinstance(param_schema, dict) is False:
            param_schema = {}
        raw_metadata = raw.get("raw_metadata", {})
        if isinstance(raw_metadata, dict) is False:
            raw_metadata = {}
        payloads.append(
            ImporterEntryPayload(
                entry_key=entry_key,
                display_name=display_name,
                description=description,
                required_capability_tags=tags,
                param_schema=dict(param_schema),
                raw_metadata=dict(raw_metadata),
            )
        )
    rtnval = (payloads, issues)
    return rtnval
