"""
.. module:: resource_import
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reads a spreadsheet of devices (CSV, or a paste from a
               spreadsheet) into rows that can be checked before anything
               is created (RES-22).

.. moduleauthor:: Code Craft AI LLC

Registering two dozen devices took about a hundred and seventy form
interactions. This module turns pasted text into :class:`ImportRow`
objects and finds what is wrong with each row, with no database and no
framework in it: the route reads the pools and the existing names and
hands them to :func:`check_against_lab`, then creates the rows only when
every one is fine.

The first row names the columns. ``name`` is required; ``type``,
``pool``, ``capacity``, ``description``, ``tags`` (separated by spaces,
commas or semicolons) and ``metadata`` (a JSON object) are optional, and a
column called ``meta.<key>`` (for example ``meta.serial``) sets one
metadata key without hand-typed JSON. A column this module does not know
is refused rather than ignored, so a typo in a header cannot silently drop
a whole column of data.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import csv
import io
import json
import re

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ccai.pychestrate.core.managers.resource_manager import (
    SUPPORTED_RESOURCE_TYPES,
    validate_resource_name,
    validate_tag_name,
)


#: Most devices one import may hold, and the most text it may be.
MAX_IMPORT_ROWS = 500
MAX_IMPORT_CHARACTERS = 262144

#: The header spellings that are accepted, by the field they fill.
COLUMN_ALIASES: Dict[str, str] = {
    "name": "name", "resource": "name", "device": "name",
    "type": "resource_type", "resource_type": "resource_type",
    "pool": "pool",
    "capacity": "capacity",
    "description": "description",
    "tags": "tags", "tag": "tags",
    "metadata": "metadata",
}

#: The columns as the page lists them.
DOCUMENTED_COLUMNS: List[Tuple[str, str, str]] = [
    ("name", "required", "Letters, digits, underscores, hyphens and periods, starting with a letter or digit."),
    ("type", "optional", "One of: {}. Default device.".format(", ".join(sorted(SUPPORTED_RESOURCE_TYPES)))),
    ("pool", "optional", "The name of an existing pool. Blank uses the default pool."),
    ("capacity", "optional", "How many can hold it at once. Default 1."),
    ("description", "optional", "Free text."),
    ("tags", "optional", "Separated by spaces, commas or semicolons; new tags are created."),
    ("metadata", "optional", "A JSON object, for example {\"os\": \"22.04\"}."),
    ("meta.<key>", "optional", "One metadata key, for example meta.serial; use it instead of JSON."),
]

EXAMPLE_TEXT = (
    "name,type,pool,capacity,tags,meta.serial,meta.os\n"
    "phone-01,device,android-phones,1,android rack-3,SN-1001,14\n"
    "phone-02,device,android-phones,1,android rack-3,SN-1002,14\n"
)

_TAG_SEPARATOR = re.compile(r"[\s,;]+")
_META_PREFIXES = ("meta.", "metadata.")


@dataclass
class ImportRow:
    """
        One device of the import, as read and as checked.

        :param number: The row's number in the spreadsheet (the header is
                       row 1, so the first device is row 2).
        :param problems: ``{field: message}`` for what is wrong (one
                         message per field).
        :param pool_id: The pool it resolves to, once checked against the
                        lab (None for the default pool when none is flagged).
    """
    number: int
    name: str = ""
    resource_type: str = "device"
    pool_name: str = ""
    capacity: int = 1
    description: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    problems: Dict[str, str] = field(default_factory=dict)
    pool_id: Optional[int] = None

    @property
    def ok(self) -> bool:
        return len(self.problems) == 0


@dataclass
class ImportPreview:
    """What a pasted spreadsheet holds: its columns, its rows and what is wrong with the file as a whole."""
    columns: List[str] = field(default_factory=list)
    rows: List[ImportRow] = field(default_factory=list)
    file_problems: List[str] = field(default_factory=list)

    @property
    def problem_rows(self) -> int:
        return len([row for row in self.rows if not row.ok])

    @property
    def importable(self) -> bool:
        """True when there is at least one device and nothing at all is wrong."""
        return len(self.rows) > 0 and len(self.file_problems) == 0 and self.problem_rows == 0


def _delimiter(*, first_line: str) -> str:
    """A tab when the text was pasted from a spreadsheet, otherwise a comma."""
    return "\t" if first_line.count("\t") > first_line.count(",") else ","


def _column_for(*, header: str) -> Optional[Tuple[str, str]]:
    """
        What a header fills.

        :returns: ``(field, "")`` for a plain column, ``("metadata_key",
                  key)`` for a ``meta.<key>`` column, or None when the
                  header is not known.
    """
    text = header.strip().lower().replace(" ", "_")
    if text in COLUMN_ALIASES:
        return (COLUMN_ALIASES[text], "")
    original = header.strip()
    for prefix in _META_PREFIXES:
        if text.startswith(prefix) and len(original) > len(prefix):
            return ("metadata_key", original[len(prefix):].strip())
    return None


def _split_tags(*, cell: str) -> List[str]:
    seen: List[str] = []
    for tag in _TAG_SEPARATOR.split(cell.strip()):
        if len(tag) > 0 and tag not in seen:
            seen.append(tag)
    return seen


def _read_row(*, number: int, cells: Dict[int, str], layout: List[Tuple[str, str]], extra: int) -> ImportRow:
    """One data row: fill the fields from its cells and note what is wrong."""
    row = ImportRow(number=number)
    metadata_cells: Dict[str, str] = {}
    metadata_json = ""
    capacity_text = ""
    for index, (target, key) in enumerate(layout):
        value = cells.get(index, "").strip()
        if target == "name":
            row.name = value
        elif target == "resource_type":
            row.resource_type = value.lower() if len(value) > 0 else "device"
        elif target == "pool":
            row.pool_name = value
        elif target == "capacity":
            capacity_text = value
        elif target == "description":
            row.description = value
        elif target == "tags":
            row.tags = _split_tags(cell=value)
        elif target == "metadata":
            metadata_json = value
        elif target == "metadata_key" and len(value) > 0:
            metadata_cells[key] = value

    if extra > 0:
        row.problems["row"] = "This row has more cells than the header has columns."
    if not validate_resource_name(row.name):
        row.problems["name"] = (
            "A name is required: 1 to 128 characters of letters, digits, underscores, hyphens and periods,"
            " starting with a letter or digit."
        )
    if row.resource_type not in SUPPORTED_RESOURCE_TYPES:
        row.problems["type"] = "Type must be one of: {}.".format(", ".join(sorted(SUPPORTED_RESOURCE_TYPES)))
    if len(capacity_text) > 0:
        if re.fullmatch(r"\d+", capacity_text) is None or int(capacity_text) < 1:
            row.problems["capacity"] = "Capacity must be a whole number of at least 1."
        else:
            row.capacity = int(capacity_text)
    for tag in row.tags:
        if not validate_tag_name(tag):
            row.problems["tags"] = (
                "The tag \"{}\" is not valid: letters, digits, underscores and hyphens, starting with a letter or digit."
            ).format(tag)
            break
    if len(metadata_json) > 0:
        try:
            parsed = json.loads(metadata_json)
        except ValueError as refusal:
            row.problems["metadata"] = "The metadata is not valid JSON ({}).".format(refusal)
        else:
            if isinstance(parsed, dict):
                row.metadata.update(parsed)
            else:
                row.problems["metadata"] = "The metadata must be a JSON object, like {\"key\": \"value\"}."
    row.metadata.update(metadata_cells)
    return row


def parse_import(*, text: str) -> ImportPreview:
    """
        Read pasted spreadsheet text.

        :param text: CSV, or tab-separated text pasted from a spreadsheet,
                     with the columns named in the first row.

        :returns: The preview: rows with their own problems, and the
                  problems that make the whole file unusable (no header, an
                  unknown column, too many rows).
    """
    preview = ImportPreview()
    text = text.lstrip("﻿")
    if len(text.strip()) == 0:
        preview.file_problems.append("Paste your devices above: the first row names the columns, then one device per row.")
        return preview
    if len(text) > MAX_IMPORT_CHARACTERS:
        preview.file_problems.append(
            "That is too much text for one import (at most {} characters). Split it into two.".format(MAX_IMPORT_CHARACTERS)
        )
        return preview

    first_line = next(line for line in text.splitlines() if len(line.strip()) > 0)
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(first_line=first_line), skipinitialspace=True)
        table = [cells for cells in reader if any(len(cell.strip()) > 0 for cell in cells)]
    except csv.Error as refusal:
        preview.file_problems.append("The text could not be read as a spreadsheet: {}.".format(refusal))
        return preview

    if len(table) == 0:
        preview.file_problems.append("Paste your devices above: the first row names the columns, then one device per row.")
        return preview
    header = table[0]
    layout: List[Tuple[str, str]] = []
    unknown: List[str] = []
    for title in header:
        found = _column_for(header=title)
        if found is None:
            unknown.append(title.strip() or "(empty)")
            layout.append(("", ""))
        else:
            layout.append(found)
    preview.columns = [title.strip() for title in header]
    if len(unknown) > 0:
        preview.file_problems.append(
            "These column names are not known: {}. Use name, type, pool, capacity, description, tags, metadata or meta.<key>."
            .format(", ".join('"{}"'.format(title) for title in unknown))
        )
    fields = [target for target, _key in layout]
    if "name" not in fields:
        preview.file_problems.append("There is no name column. The first row must name the columns, and one of them must be name.")
    repeated = sorted({target for target in fields if target not in ("", "metadata_key") and fields.count(target) > 1})
    if len(repeated) > 0:
        preview.file_problems.append("These columns appear more than once: {}.".format(", ".join(repeated)))
    if len(table) - 1 > MAX_IMPORT_ROWS:
        preview.file_problems.append(
            "That is {} devices; one import takes at most {}. Split it into two.".format(len(table) - 1, MAX_IMPORT_ROWS)
        )
        return preview
    if len(preview.file_problems) > 0:
        return preview

    for offset, cells in enumerate(table[1:], start=2):
        indexed = {index: value for index, value in enumerate(cells[:len(layout)])}
        preview.rows.append(_read_row(number=offset, cells=indexed, layout=layout, extra=max(len(cells) - len(layout), 0)))
    if len(preview.rows) == 0:
        preview.file_problems.append("There is a header row but no devices under it.")

    seen: Dict[Tuple[str, str], int] = {}
    for row in preview.rows:
        key = (row.pool_name, row.name)
        if len(row.name) > 0 and key in seen and "name" not in row.problems:
            row.problems["name"] = "The same name and pool as row {}: a pool cannot hold two of one name.".format(seen[key])
        elif len(row.name) > 0:
            seen.setdefault(key, row.number)
    return preview


def check_against_lab(
        *,
        rows: List[ImportRow],
        pool_ids_by_name: Dict[str, int],
        default_pool_id: Optional[int],
        existing: Set[Tuple[Optional[int], str]]
    ) -> None:
    """
        Check the rows against what is already in the lab: the pool each
        one names must exist, and no pool may already hold a resource of
        the same name. Adds to each row's problems; touches nothing else.

        :param rows: The rows to check.
        :param pool_ids_by_name: Every pool's id, by name.
        :param default_pool_id: The pool a blank pool cell means (or None).
        :param existing: ``(pool id, name)`` of every resource already there
                         with one of the rows' names.
    """
    for row in rows:
        if len(row.pool_name) > 0:
            if row.pool_name not in pool_ids_by_name:
                row.problems["pool"] = "There is no pool called \"{}\". Create it first, or leave the pool blank.".format(row.pool_name)
                continue
            row.pool_id = pool_ids_by_name[row.pool_name]
        else:
            row.pool_id = default_pool_id
        if "name" not in row.problems and (row.pool_id, row.name) in existing:
            where = "The pool \"{}\"".format(row.pool_name) if len(row.pool_name) > 0 else "The default pool"
            row.problems["name"] = "{} already has a resource called \"{}\".".format(where, row.name)
    return
