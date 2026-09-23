"""
.. module:: cli.renderer
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Print command results as a table, JSON, YAML, TSV, or
               the server's raw answer.

.. moduleauthor:: Code Craft AI LLC

``-o/--output`` picks the format; without it, results print as a
table on a terminal and as JSON anywhere else, so a pipeline gets
machine-readable output without asking::

    table   aligned columns for people (default on a terminal)
    json    one JSON document: an array for lists, an object otherwise
            (default when stdout is not a terminal)
    yaml    the same document as YAML
    tsv     a header row, then one tab-separated row per item
    raw     the server's response body exactly as it was sent

A list response (``{"items": [...], "meta": {...}}``) is printed as
its items -- JSON output is an array ``jq`` can read directly. An
envelope that carries more than pagination data (``generated_at``,
``dynamic_mount``) stays an object in JSON / YAML; tables still show
its items.

``--fields a,b,c`` keeps those fields in that order (``labels.env``
reaches into objects; a field no item has is a usage error), and
``-q/--quiet`` prints only each item's identifier, one per line
(``pyc projects list -q`` prints slugs).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import re

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, TextIO, Tuple

from ccai.pychestrate.cli import suggestions
from ccai.pychestrate.cli.exceptions import CliUsageError


FORMAT_TABLE: str = "table"
FORMAT_JSON: str = "json"
FORMAT_YAML: str = "yaml"
FORMAT_TSV: str = "tsv"
FORMAT_RAW: str = "raw"

OUTPUT_FORMATS: Tuple[str, ...] = (FORMAT_TABLE, FORMAT_JSON, FORMAT_YAML, FORMAT_TSV, FORMAT_RAW)

#: Envelope keys that only describe pagination.
PAGINATION_KEYS: Tuple[str, ...] = (
    "meta", "total", "page", "per_page", "next_cursor", "has_more", "count", "limit", "offset",
)

#: Identifier fields tried by ``--quiet``, after the command's own.
IDENTIFIER_FIELDS: Tuple[str, ...] = ("id", "slug", "key", "name")

#: Longest cell a table prints (longer text ends in "...").
TABLE_CELL_LIMIT: int = 48

#: Width assumed for a terminal whose size cannot be read.
DEFAULT_TERMINAL_WIDTH: int = 120

TABLE_EMPTY_TEXT: str = "(no items)"
TABLE_ABSENT_TEXT: str = "-"

_PLAIN_YAML_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_./@+-]*$")
_YAML_RESERVED_WORDS = (
    "true", "false", "yes", "no", "on", "off", "null", "y", "n", "~",
)


@dataclass(frozen=True)
class OutputOptions:
    """
        How a command prints its result.

        :param output_format: One of :data:`OUTPUT_FORMATS`, or
                              ``None`` for the terminal-aware default.
        :param fields: Fields to keep (``--fields``), in order.
        :param quiet: Print identifiers only (``--quiet``).
    """
    output_format: Optional[str] = None
    fields: Tuple[str, ...] = field(default_factory=tuple)
    quiet: bool = False


def parse_output_format(raw: str) -> str:
    """
        Validate an ``--output`` value.

        :param raw: Value as typed.

        :returns: The format.
        :raises: CliUsageError
    """
    value = str(raw).strip().lower()
    if value in OUTPUT_FORMATS:
        return value
    hint = suggestions.did_you_mean(word=value, candidates=OUTPUT_FORMATS)
    raise CliUsageError(
        "--output must be one of {}{}".format(
            ", ".join(OUTPUT_FORMATS), "; " + hint if len(hint) > 0 else ""
        )
    )


def parse_fields(raw: str) -> Tuple[str, ...]:
    """
        Split a ``--fields`` value (``a,b,c``).

        :param raw: Value as typed.

        :returns: Field names in order.
        :raises: CliUsageError when no field is named.
    """
    names = []
    for part in str(raw).split(","):
        name = part.strip()
        if len(name) > 0 and name not in names:
            names.append(name)
    if len(names) == 0:
        raise CliUsageError("--fields needs a comma-separated list of field names")
    rtnval = tuple(names)
    return rtnval


def is_terminal(stream: Any) -> bool:
    """
        Whether ``stream`` is an interactive terminal.

        :param stream: Output stream.

        :returns: Boolean.
    """
    try:
        rtnval = bool(stream.isatty())
    except Exception:  # noqa: BLE001 -- any stream without isatty is not a terminal
        rtnval = False
    return rtnval


def effective_format(*, options: OutputOptions, stream: Any, default: Optional[str] = None) -> str:
    """
        The format to print in: ``--output``, else ``default``, else
        ``table`` on a terminal and ``json`` anywhere else.

        :param options: Output options.
        :param stream: Output stream.
        :param default: A command's own default (``None`` for the
                        terminal-aware one).

        :returns: A format name.
    """
    if options.output_format is not None:
        return options.output_format
    if default is not None:
        return default
    rtnval = FORMAT_TABLE if is_terminal(stream) else FORMAT_JSON
    return rtnval


def list_key_of(value: Any) -> Optional[str]:
    """
        The key holding the items of a list response: ``items`` when
        the object has an ``items`` array, else its only array-valued
        key when every other key is pagination data (``{"jobs": [...],
        "total": 3, "offset": 0, "limit": 50}``).

        :param value: Decoded body.

        :returns: Key or ``None`` when ``value`` is not a list response.
    """
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("items", None), list):
        return "items"
    array_keys = [key for key, item in value.items() if isinstance(item, list)]
    other_keys = [key for key in value.keys() if key not in array_keys]
    if len(array_keys) == 1 and all(key in PAGINATION_KEYS for key in other_keys):
        rtnval: Optional[str] = array_keys[0]
        return rtnval
    return None


def is_list_envelope(value: Any) -> bool:
    """
        Whether ``value`` is a list response (see :func:`list_key_of`).

        :param value: Decoded body.

        :returns: Boolean.
    """
    rtnval = list_key_of(value) is not None
    return rtnval


def is_pure_list_envelope(value: Any) -> bool:
    """
        Whether ``value`` is a list response carrying nothing but
        pagination data besides its items.

        :param value: Decoded body.

        :returns: Boolean.
    """
    list_key = list_key_of(value)
    if list_key is None:
        return False
    extra = [key for key in value.keys() if key != list_key and key not in PAGINATION_KEYS]
    rtnval = len(extra) == 0
    return rtnval


def items_of(value: Any) -> Optional[List[Any]]:
    """
        The items of a list response or list, else ``None``.

        :param value: Decoded body.

        :returns: Items or ``None``.
    """
    if isinstance(value, list):
        return value
    list_key = list_key_of(value)
    if list_key is None:
        return None
    rtnval = value[list_key]
    return rtnval


def document_for(value: Any) -> Any:
    """
        The document JSON / YAML output prints: a pure list envelope
        becomes its items array, anything else stays as it is.

        :param value: Decoded body.

        :returns: Document.
    """
    if is_pure_list_envelope(value) is True:
        rtnval = value[list_key_of(value)]
        return rtnval
    rtnval = value
    return rtnval


def _lookup(item: Any, path: str) -> Tuple[bool, Any]:
    """
        The value at a dotted ``path`` of ``item``.

        :param item: Object.
        :param path: ``a`` or ``a.b``.

        :returns: ``(found, value)``.
    """
    current = item
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            rtnval = (False, None)
            return rtnval
    rtnval = (True, current)
    return rtnval


def _available_fields(rows: Sequence[Any]) -> List[str]:
    """
        Every top-level field of ``rows``, in first-seen order.

        :param rows: Objects.

        :returns: Field names.
    """
    names: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row.keys():
            if key not in names:
                names.append(str(key))
    rtnval = names
    return rtnval


def check_fields(*, rows: Sequence[Any], fields: Sequence[str]) -> None:
    """
        Refuse ``--fields`` naming a field no row has.

        :param rows: Objects (an empty list accepts anything).
        :param fields: Requested fields.

        :returns: None.
        :raises: CliUsageError
    """
    object_rows = [row for row in rows if isinstance(row, dict)]
    if len(object_rows) == 0:
        return
    available = _available_fields(object_rows)
    for name in fields:
        found_anywhere = False
        for row in object_rows:
            found, _value = _lookup(row, name)
            if found is True:
                found_anywhere = True
                break
        if found_anywhere is False:
            hint = suggestions.did_you_mean(word=name, candidates=available)
            raise CliUsageError(
                "--fields: no item has a field '{}'{} (fields: {})".format(
                    name, "; " + hint if len(hint) > 0 else "", ", ".join(available)
                )
            )
    return


def project(*, value: Any, fields: Sequence[str]) -> Any:
    """
        Keep only ``fields`` (in that order) of an object or of every
        object in a list; a dotted field keeps its dotted name.

        :param value: Object or list.
        :param fields: Fields.

        :returns: Projected value.
    """
    if len(fields) == 0:
        return value
    if isinstance(value, list):
        rtnval = [project(value=item, fields=fields) for item in value]
        return rtnval
    if not isinstance(value, dict):
        return value
    projected: Dict[str, Any] = {}
    for name in fields:
        found, field_value = _lookup(value, name)
        projected[name] = field_value if found is True else None
    rtnval = projected
    return rtnval


def _is_scalar(value: Any) -> bool:
    rtnval = value is None or isinstance(value, (str, int, float, bool))
    return rtnval


def _scalar_text(value: Any) -> str:
    """
        A value as cell text: ``true`` / ``false``, numbers, strings,
        compact JSON for objects and lists.

        :param value: Value.

        :returns: Text.
    """
    if isinstance(value, bool):
        rtnval = "true" if value is True else "false"
        return rtnval
    if isinstance(value, (dict, list)):
        rtnval = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        return rtnval
    rtnval = str(value)
    return rtnval


def _table_cell(value: Any) -> str:
    """
        A value as a table cell: ``-`` when absent, one line, at most
        :data:`TABLE_CELL_LIMIT` characters.

        :param value: Value.

        :returns: Text.
    """
    if value is None:
        return TABLE_ABSENT_TEXT
    text = " ".join(_scalar_text(value).split())
    if len(text) > TABLE_CELL_LIMIT:
        text = text[:TABLE_CELL_LIMIT - 3] + "..."
    rtnval = text
    return rtnval


def _tsv_cell(value: Any) -> str:
    """
        A value as a TSV cell: empty when absent; tab, newline,
        carriage return and backslash escaped.

        :param value: Value.

        :returns: Text.
    """
    if value is None:
        return ""
    text = _scalar_text(value)
    text = text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
    rtnval = text
    return rtnval


def _default_columns(rows: Sequence[Dict[str, Any]]) -> List[str]:
    """
        The columns a table shows without ``--fields``: every field
        holding a plain value (not an object or list) in some row.

        :param rows: Objects.

        :returns: Field names in first-seen order.
    """
    columns: List[str] = []
    for row in rows:
        for key, value in row.items():
            if key not in columns and _is_scalar(value):
                columns.append(key)
    rtnval = columns
    return rtnval


def terminal_width(*, stream: Any, environ: Optional[Dict[str, str]] = None) -> Optional[int]:
    """
        The width a table must fit, or ``None`` when the output is not
        a terminal (a table written to a file keeps every column).

        :param stream: Output stream.
        :param environ: Environment (``COLUMNS`` wins).

        :returns: Columns or ``None``.
    """
    if is_terminal(stream) is False:
        return None
    columns_text = str((environ or {}).get("COLUMNS", "") or "")
    if columns_text.isdigit() and int(columns_text) > 0:
        rtnval: Optional[int] = int(columns_text)
        return rtnval
    try:
        rtnval = os.get_terminal_size(stream.fileno()).columns
    except (AttributeError, OSError, ValueError):
        rtnval = DEFAULT_TERMINAL_WIDTH
    return rtnval


def _render_table_rows(
        *,
        rows: Sequence[Dict[str, Any]],
        columns: Sequence[str],
        width: Optional[int]
    ) -> Tuple[List[str], List[str]]:
    """
        Lay out ``rows`` as aligned columns, dropping trailing columns
        that do not fit ``width``.

        :param rows: Objects.
        :param columns: Fields to show.
        :param width: Terminal width or ``None`` for no limit.

        :returns: ``(lines, dropped_columns)``.
    """
    cells: List[List[str]] = []
    for row in rows:
        row_cells = []
        for column in columns:
            _found, value = _lookup(row, column)
            row_cells.append(_table_cell(value))
        cells.append(row_cells)

    widths = []
    for index, column in enumerate(columns):
        column_width = len(column)
        for row_cells in cells:
            column_width = max(column_width, len(row_cells[index]))
        widths.append(column_width)

    shown = len(columns)
    if width is not None:
        used = 0
        shown = 0
        for column_width in widths:
            needed = column_width if shown == 0 else column_width + 2
            if shown > 0 and used + needed > width:
                break
            used = used + needed
            shown = shown + 1

    lines = []
    header = "  ".join(columns[index].ljust(widths[index]) for index in range(shown))
    lines.append(header.rstrip())
    for row_cells in cells:
        line = "  ".join(row_cells[index].ljust(widths[index]) for index in range(shown))
        lines.append(line.rstrip())
    rtnval = (lines, list(columns[shown:]))
    return rtnval


def _yaml_scalar(value: Any) -> str:
    """
        A scalar as YAML: plain when unambiguous, else a JSON-quoted
        string (valid YAML).

        :param value: Scalar.

        :returns: Text.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        rtnval = "true" if value is True else "false"
        return rtnval
    if isinstance(value, (int, float)):
        if value != value or value in (float("inf"), float("-inf")):
            rtnval = json.dumps(str(value))
            return rtnval
        rtnval = json.dumps(value)
        return rtnval
    text = str(value)
    if _PLAIN_YAML_PATTERN.match(text) is not None and text.lower() not in _YAML_RESERVED_WORDS:
        return text
    rtnval = json.dumps(text, ensure_ascii=False)
    return rtnval


def _yaml_lines(value: Any, indent: int) -> List[str]:
    """
        Block-style YAML lines for ``value``.

        :param value: Document node.
        :param indent: Current indentation.

        :returns: Lines.
    """
    pad = " " * indent
    lines: List[str] = []
    if isinstance(value, dict):
        if len(value) == 0:
            lines.append(pad + "{}")
            return lines
        for key, item in value.items():
            key_text = _yaml_scalar(str(key))
            if isinstance(item, dict) and len(item) > 0:
                lines.append("{}{}:".format(pad, key_text))
                lines.extend(_yaml_lines(item, indent + 2))
            elif isinstance(item, list) and len(item) > 0:
                lines.append("{}{}:".format(pad, key_text))
                lines.extend(_yaml_lines(item, indent))
            else:
                lines.append("{}{}: {}".format(pad, key_text, _yaml_inline(item)))
        return lines
    if isinstance(value, list):
        if len(value) == 0:
            lines.append(pad + "[]")
            return lines
        for item in value:
            if isinstance(item, (dict, list)) and len(item) > 0:
                nested = _yaml_lines(item, indent + 2)
                first = nested[0][indent + 2:]
                lines.append("{}- {}".format(pad, first))
                lines.extend(nested[1:])
            else:
                lines.append("{}- {}".format(pad, _yaml_inline(item)))
        return lines
    lines.append(pad + _yaml_scalar(value))
    return lines


def _yaml_inline(value: Any) -> str:
    """
        A scalar or an empty collection on one line.

        :param value: Node.

        :returns: Text.
    """
    if isinstance(value, dict):
        return "{}"
    if isinstance(value, list):
        return "[]"
    rtnval = _yaml_scalar(value)
    return rtnval


def to_yaml(value: Any) -> str:
    """
        ``value`` (JSON-shaped data) as a YAML document.

        :param value: Document.

        :returns: YAML text ending in a newline.
    """
    rtnval = "\n".join(_yaml_lines(value, 0)) + "\n"
    return rtnval


def identifier_of(*, item: Any, preferred: Sequence[str]) -> Optional[str]:
    """
        The identifier ``--quiet`` prints for ``item``: the first of
        ``preferred`` fields it has, then ``id``, ``slug``, ``key``,
        ``name``, then any ``*_id`` field.

        :param item: Object (a plain value is its own identifier).
        :param preferred: The command's identifying fields.

        :returns: Text, or ``None`` when nothing identifies it.
    """
    if _is_scalar(item) and item is not None:
        rtnval: Optional[str] = _scalar_text(item)
        return rtnval
    if not isinstance(item, dict):
        return None
    for name in list(preferred) + list(IDENTIFIER_FIELDS):
        found, value = _lookup(item, name)
        if found is True and value is not None and _is_scalar(value):
            rtnval = _scalar_text(value)
            return rtnval
    for key, value in item.items():
        if str(key).endswith("_id") and value is not None and _is_scalar(value):
            rtnval = _scalar_text(value)
            return rtnval
    return None


@dataclass
class RenderRequest:
    """
        One result to print.

        :param value: Decoded body (or the merged items of every page).
        :param raw_text: The body exactly as the server sent it (for
                         ``raw``); ``None`` when the value was built by
                         pyc.
        :param identifier_fields: Fields that identify an item of this
                                  command (``--quiet``), best first.
        :param default_format: The command's own default format
                               (``None`` for table-on-a-terminal /
                               JSON elsewhere).
    """
    value: Any
    raw_text: Optional[str] = None
    identifier_fields: Tuple[str, ...] = field(default_factory=tuple)
    default_format: Optional[str] = None


def render(
        *,
        request: RenderRequest,
        options: OutputOptions,
        stream: TextIO,
        notes: TextIO,
        environ: Optional[Dict[str, str]] = None
    ) -> None:
    """
        Print one result in the chosen format.

        :param request: What to print.
        :param options: ``--output`` / ``--fields`` / ``--quiet``.
        :param stream: Standard output.
        :param notes: Where hints about the output go (stderr).
        :param environ: Environment (``COLUMNS``).

        :returns: None.
        :raises: CliUsageError for ``--fields`` naming an unknown field
                 or options that do not apply to ``raw``.
    """
    output_format = effective_format(options=options, stream=stream, default=request.default_format)
    value = request.value

    if output_format == FORMAT_RAW:
        if len(options.fields) > 0 or options.quiet is True:
            raise CliUsageError("--fields and --quiet do not apply to -o raw (the server's answer as sent)")
        if request.raw_text is not None and len(request.raw_text) > 0:
            text = request.raw_text
        elif value is None:
            text = ""
        else:
            text = json.dumps(value, indent=2, ensure_ascii=False)
        if len(text) > 0:
            stream.write(text if text.endswith("\n") else text + "\n")
        return

    if value is None:
        return
    if isinstance(value, str):
        # A text answer (logs, a plain-text page) prints as it is.
        stream.write(value if value.endswith("\n") else value + "\n")
        return

    rows = items_of(value)

    if len(options.fields) > 0:
        check_fields(rows=rows if rows is not None else [value], fields=options.fields)

    if options.quiet is True:
        targets = rows if rows is not None else [value]
        for item in targets:
            identifier = identifier_of(item=item, preferred=list(options.fields) + list(request.identifier_fields))
            if identifier is not None:
                stream.write(identifier + "\n")
        return

    if output_format in (FORMAT_JSON, FORMAT_YAML):
        document = document_for(value)
        if rows is not None and document is not rows and len(options.fields) > 0:
            # An envelope with more than pagination data keeps its
            # other keys; only its items are narrowed.
            document = dict(document)
            document[list_key_of(value)] = project(value=rows, fields=options.fields)
        else:
            document = project(value=document, fields=options.fields)
        if output_format == FORMAT_JSON:
            stream.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        else:
            stream.write(to_yaml(document))
        return

    if output_format == FORMAT_TSV:
        _render_tsv(rows=rows, value=value, fields=options.fields, stream=stream)
        return

    _render_table(
        rows=rows, value=value, fields=options.fields, stream=stream, notes=notes, environ=environ,
    )
    return


def _render_tsv(*, rows: Optional[List[Any]], value: Any, fields: Sequence[str], stream: TextIO) -> None:
    """
        TSV output: a header row, then one row per item (an object is
        one row).

        :param rows: Items, or ``None`` for a single object.
        :param value: The object when ``rows`` is ``None``.
        :param fields: ``--fields``.
        :param stream: Standard output.

        :returns: None.
    """
    targets = rows if rows is not None else [value]
    object_rows = [row for row in targets if isinstance(row, dict)]
    if len(object_rows) == 0:
        for item in targets:
            stream.write(_tsv_cell(item) + "\n")
        return
    columns = list(fields) if len(fields) > 0 else _available_fields(object_rows)
    stream.write("\t".join(columns) + "\n")
    for row in object_rows:
        cells = []
        for column in columns:
            _found, cell_value = _lookup(row, column)
            cells.append(_tsv_cell(cell_value))
        stream.write("\t".join(cells) + "\n")
    return


def _render_table(
        *,
        rows: Optional[List[Any]],
        value: Any,
        fields: Sequence[str],
        stream: TextIO,
        notes: TextIO,
        environ: Optional[Dict[str, str]]
    ) -> None:
    """
        Table output: aligned columns for a list, ``field  value``
        lines for an object.

        :param rows: Items, or ``None`` for a single object.
        :param value: The object when ``rows`` is ``None``.
        :param fields: ``--fields``.
        :param stream: Standard output.
        :param notes: stderr, for hints about hidden columns.
        :param environ: Environment (``COLUMNS``).

        :returns: None.
    """
    width = terminal_width(stream=stream, environ=environ)
    if rows is None:
        if not isinstance(value, dict):
            stream.write(_scalar_text(value) + "\n")
            return
        names = list(fields) if len(fields) > 0 else [str(key) for key in value.keys()]
        name_width = max([len(name) for name in names] + [1])
        for name in names:
            _found, field_value = _lookup(value, name)
            text = TABLE_ABSENT_TEXT if field_value is None else " ".join(_scalar_text(field_value).split())
            stream.write("{}  {}\n".format(name.ljust(name_width), text))
        return

    list_key = list_key_of(value)
    if list_key is not None:
        for key, extra in value.items():
            if key == list_key or key in PAGINATION_KEYS or not _is_scalar(extra):
                continue
            stream.write("{}: {}\n".format(key, _table_cell(extra)))

    object_rows = [row for row in rows if isinstance(row, dict)]
    if len(rows) == 0:
        stream.write(TABLE_EMPTY_TEXT + "\n")
        return
    if len(object_rows) == 0:
        for item in rows:
            stream.write(_table_cell(item) + "\n")
        return
    columns = list(fields) if len(fields) > 0 else _default_columns(object_rows)
    lines, dropped = _render_table_rows(rows=object_rows, columns=columns, width=width)
    stream.write("\n".join(lines) + "\n")
    if len(dropped) > 0:
        notes.write(
            "note: {} more column(s) did not fit: {}; use --fields or -o json.\n".format(
                len(dropped), ", ".join(dropped)
            )
        )
    return


__all__ = [
    "FORMAT_JSON",
    "FORMAT_RAW",
    "FORMAT_TABLE",
    "FORMAT_TSV",
    "FORMAT_YAML",
    "OUTPUT_FORMATS",
    "OutputOptions",
    "RenderRequest",
    "check_fields",
    "document_for",
    "effective_format",
    "identifier_of",
    "is_list_envelope",
    "is_pure_list_envelope",
    "is_terminal",
    "items_of",
    "list_key_of",
    "parse_fields",
    "parse_output_format",
    "project",
    "render",
    "terminal_width",
    "to_yaml",
]
