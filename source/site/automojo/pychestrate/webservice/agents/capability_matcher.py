"""
.. module:: agents.capability_matcher
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Client-capability predicate matcher for 3-client-capability-advertisement M2.

.. moduleauthor:: Automation Mojo LLC

Supports two predicate forms:

- ``has(kind)`` — client has any capability with kind ``kind``.
- ``kind.path=value`` — client has a capability ``kind`` whose
  JSON body has ``path`` == ``value`` (``path`` is dot-separated).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, List, Mapping, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.agents.models import ClientCapability


_HAS_PATTERN = re.compile(r"^has\(\s*([a-z][a-z0-9_]{0,63})\s*\)$")
_EQ_PATTERN = re.compile(
    r"^([a-z][a-z0-9_]{0,63})\.([A-Za-z0-9_.]+)\s*=\s*(.+)$"
)


def find_clients_matching(
        *,
        db_session: DbSession,
        predicates: List[str]
    ) -> List[str]:
    """
        Return every client id whose capability set satisfies every
        predicate.

        :param predicates: Strings like ``has(toolchain)`` or
                           ``concurrency.max_parallel_jobs=4``.

        :returns: Sorted list of client ids.
    """
    capabilities_by_client: dict = {}
    for row in db_session.query(ClientCapability).all():
        bucket = capabilities_by_client.setdefault(str(row.client_id), {})
        value = row.value_json.get("value") if isinstance(row.value_json, Mapping) else None
        bucket[row.kind] = value

    matched: List[str] = []
    for client_id, caps in capabilities_by_client.items():
        if all(_eval_predicate(predicate=p, caps=caps) is True for p in (predicates or [])):
            matched.append(client_id)

    matched.sort()
    return matched


def _eval_predicate(*, predicate: str, caps: Mapping[str, Any]) -> bool:
    """
        Evaluate a single predicate against a client's capabilities.
    """
    predicate = (predicate or "").strip()
    if len(predicate) == 0:
        return True

    has_match = _HAS_PATTERN.match(predicate)
    if has_match is not None:
        kind = has_match.group(1)
        return kind in caps

    eq_match = _EQ_PATTERN.match(predicate)
    if eq_match is not None:
        kind = eq_match.group(1)
        path = eq_match.group(2)
        expected = eq_match.group(3).strip()
        if kind not in caps:
            return False
        actual = _walk_path(value=caps[kind], path=path)
        return _values_equal(expected=expected, actual=actual)

    return False


def _walk_path(*, value: Any, path: str) -> Any:
    """
        Walk a dotted path inside ``value``.
    """
    current = value
    for segment in path.split("."):
        if isinstance(current, Mapping) is False:
            return None
        current = current.get(segment, None)
        if current is None:
            return None
    return current


def _values_equal(*, expected: str, actual: Any) -> bool:
    """
        Best-effort scalar comparison across str / int / bool.
    """
    if actual is None:
        return False
    if isinstance(actual, bool) is True:
        return expected.lower() == str(actual).lower()
    if isinstance(actual, int) is True:
        try:
            return int(expected) == actual
        except ValueError:
            return False
    return str(actual) == expected
