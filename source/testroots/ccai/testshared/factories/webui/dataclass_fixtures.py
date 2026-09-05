"""
.. module:: ccai.testshared.factories.webui.dataclass_fixtures
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Generic populator for ``@dataclass`` response types.

.. moduleauthor:: Code Craft AI LLC

The consumer web UI handlers pass manager response dataclasses
(``ProjectResponse``, ``WatchResponse``, ...) straight into jinja.
A template that reads an attribute the dataclass does not define
renders an empty string under jinja's default ``Undefined`` and
ships a blank cell, or a "None", to the user. The render-smoke
suite catches that class of drift by rendering every template
under ``StrictUndefined`` against instances built here, so the
fixtures must be shaped *exactly* like the production types --
which is why they are derived from the dataclass type hints
rather than hand-written.

Two build modes:

* :data:`MODE_POPULATED` -- every ``Optional`` is set, every
  ``List`` holds one element, every ``Dict`` holds one entry.
  Exercises every branch that renders data.
* :data:`MODE_SPARSE` -- every ``Optional`` is ``None``, lists and
  dicts are empty. Exercises empty states and surfaces raw
  ``None`` leaks (``{{ build.duration_seconds }}s`` -> ``Nones``).

Usage::

    from ccai.testshared.factories.webui.dataclass_fixtures import (
        build_fixture, MODE_POPULATED)

    watch = build_fixture(WatchResponse, mode=MODE_POPULATED)
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import dataclasses
import enum
import typing

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Type


MODE_POPULATED: str = "populated"
MODE_SPARSE: str = "sparse"

FIXTURE_DATETIME: datetime = datetime(2026, 9, 4, 13, 45, 30, tzinfo=timezone.utc)
FIXTURE_DATE: date = date(2026, 9, 4)

_MAX_DEPTH: int = 6


def _is_dataclass_type(candidate: Any) -> bool:
    rtnval = isinstance(candidate, type) and dataclasses.is_dataclass(candidate)
    return rtnval


def _unwrap_optional(hint: Any) -> "tuple[Any, bool]":
    """
        Split ``Optional[T]`` (``Union[T, None]``) into ``(T, True)``.
        Returns ``(hint, False)`` for non-optional hints.
    """
    origin = typing.get_origin(hint)
    if origin is typing.Union:
        args = [a for a in typing.get_args(hint) if a is not type(None)]
        if len(args) == 1 and len(typing.get_args(hint)) == 2:
            return args[0], True
    rtnval = (hint, False)
    return rtnval


def build_value(
        *,
        hint: Any,
        field_name: str,
        mode: str,
        depth: int = 0
    ) -> Any:
    """
        Produce a fixture value for a single type hint.

        :param hint: The ``typing`` hint (``int``, ``Optional[str]``,
                     ``List[Foo]``, a dataclass, an Enum, ...).
        :param field_name: Field name, used to make string values
                           self-describing (``"name-value"``).
        :param mode: :data:`MODE_POPULATED` or :data:`MODE_SPARSE`.
        :param depth: Recursion guard for self-referential types.

        :returns: A value of the requested shape.
    """
    if depth > _MAX_DEPTH:
        return None

    inner, is_optional = _unwrap_optional(hint)
    if is_optional is True and mode == MODE_SPARSE:
        return None

    if inner is Any or inner is object:
        rtnval = "{}-value".format(field_name)
        return rtnval

    origin = typing.get_origin(inner)
    args = typing.get_args(inner)

    if origin in (list, List):
        if mode == MODE_SPARSE:
            return []
        elem_hint = args[0] if len(args) > 0 else Any
        rtnval = [build_value(hint=elem_hint, field_name=field_name, mode=mode, depth=depth + 1)]
        return rtnval

    if origin in (dict, Dict):
        if mode == MODE_SPARSE:
            return {}
        key_hint = args[0] if len(args) > 0 else str
        val_hint = args[1] if len(args) > 1 else Any
        key = build_value(hint=key_hint, field_name=field_name + "_key", mode=mode, depth=depth + 1)
        val = build_value(hint=val_hint, field_name=field_name + "_val", mode=mode, depth=depth + 1)
        rtnval = {key: val}
        return rtnval

    if origin in (tuple, typing.Tuple):
        rtnval = tuple(
            build_value(hint=a, field_name=field_name, mode=mode, depth=depth + 1)
            for a in args if a is not Ellipsis
        )
        return rtnval

    if origin is typing.Union:
        # Non-optional union: pick the first alternative.
        rtnval = build_value(hint=args[0], field_name=field_name, mode=mode, depth=depth + 1)
        return rtnval

    if isinstance(inner, type):
        if issubclass(inner, enum.Enum):
            members = list(inner)
            rtnval = members[0] if len(members) > 0 else None
            return rtnval
        if inner is bool:
            return True
        if inner is int:
            if field_name.endswith("_id") or field_name == "id":
                return 7
            return 3
        if inner is float:
            return 1.5
        if inner is str:
            if field_name.endswith("_id") or field_name == "id":
                return "{}-7".format(field_name)
            rtnval = "{}-value".format(field_name)
            return rtnval
        if inner is datetime:
            return FIXTURE_DATETIME
        if inner is date:
            return FIXTURE_DATE
        if inner is timedelta:
            return timedelta(minutes=5)
        if inner is bytes:
            return b"bytes-value"
        if _is_dataclass_type(inner):
            rtnval = build_fixture(inner, mode=mode, depth=depth + 1)
            return rtnval

    # Forward references or unknown hints fall back to a string so
    # the template at least receives *something* and any attribute
    # access on it fails loudly under StrictUndefined.
    rtnval = "{}-value".format(field_name)
    return rtnval


def build_fixture(
        dataclass_type: Type[Any],
        *,
        mode: str = MODE_POPULATED,
        overrides: Optional[Dict[str, Any]] = None,
        depth: int = 0
    ) -> Any:
    """
        Instantiate ``dataclass_type`` with fixture values for every
        field.

        :param dataclass_type: A ``@dataclass`` class.
        :param mode: :data:`MODE_POPULATED` or :data:`MODE_SPARSE`.
        :param overrides: Optional ``{field: value}`` overrides
                          applied after generation.
        :param depth: Recursion guard.

        :returns: An instance of ``dataclass_type``.
        :raises: TypeError when ``dataclass_type`` is not a dataclass.
    """
    if _is_dataclass_type(dataclass_type) is False:
        raise TypeError(
            "build_fixture requires a dataclass type, got {!r}".format(dataclass_type)
        )

    try:
        hints = typing.get_type_hints(dataclass_type)
    except Exception:
        hints = {f.name: f.type for f in dataclasses.fields(dataclass_type)}

    kwargs: Dict[str, Any] = {}
    for field in dataclasses.fields(dataclass_type):
        if field.init is False:
            continue
        hint = hints.get(field.name, field.type)
        kwargs[field.name] = build_value(
            hint=hint, field_name=field.name, mode=mode, depth=depth
        )

    if overrides is not None:
        kwargs.update(overrides)

    rtnval = dataclass_type(**kwargs)
    return rtnval


def build_fixture_list(
        dataclass_type: Type[Any],
        *,
        mode: str = MODE_POPULATED,
        count: int = 2
    ) -> List[Any]:
    """
        Build a list of fixtures. Sparse mode returns an empty list
        so list pages exercise their empty-state branch.

        :param dataclass_type: A ``@dataclass`` class.
        :param mode: Build mode.
        :param count: Number of populated items.

        :returns: List of instances (possibly empty).
    """
    if mode == MODE_SPARSE:
        return []
    rtnval = [build_fixture(dataclass_type, mode=mode) for _ in range(count)]
    return rtnval


__all__ = [
    "MODE_POPULATED",
    "MODE_SPARSE",
    "FIXTURE_DATETIME",
    "FIXTURE_DATE",
    "build_value",
    "build_fixture",
    "build_fixture_list",
]
