"""
.. module:: pods.topology_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 3-pod-topology-view pure-function composition.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.extensions.registry import list_resource_extensions
from automojo.pychestrate.webservice.pods.definitions_service import (
    read_pod_definition,
    read_pod_definition_version,
)
from automojo.pychestrate.webservice.pods.extensions.renderer import (
    PodMemberRendererExtension,
)
from automojo.pychestrate.webservice.pods.lifecycle_service import read_state
from automojo.pychestrate.webservice.pods.static_service import (
    read_active_registration,
)


@dataclass(frozen=True)
class TopologyMember:
    """
        One node in the :class:`TopologyGraph`.
    """
    name: str
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    hint: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TopologyLink:
    """
        One edge in the :class:`TopologyGraph`.
    """
    source: str
    target: str
    label: str = ""


@dataclass(frozen=True)
class TopologyGraph:
    """
        A pure view over a pod definition + its registration + lifecycle.
    """
    pod_id: str
    pod_name: str
    version: int
    state: str
    members: Tuple[TopologyMember, ...] = field(default_factory=tuple)
    links: Tuple[TopologyLink, ...] = field(default_factory=tuple)
    etag: str = ""


_TOPOLOGY_CACHE: Dict[str, TopologyGraph] = {}


def invalidate_cache_for_pod(*, pod_id: str) -> None:
    """
        Drop the memoized topology for ``pod_id``.
    """
    _TOPOLOGY_CACHE.pop(str(pod_id), None)
    return


def reset_cache_for_testing() -> None:
    """
        Clear the topology cache. Test-only.
    """
    _TOPOLOGY_CACHE.clear()
    return


def compose_topology(
        *,
        db_session: DbSession,
        pod_id: str
    ) -> TopologyGraph:
    """
        Build a :class:`TopologyGraph` from the definition version +
        registration + runtime state. Memoized; invalidated by bus
        subscribers on definition/state change.
    """
    cached = _TOPOLOGY_CACHE.get(str(pod_id), None)
    if cached is not None:
        return cached

    definition = read_pod_definition(db_session=db_session, pod_id=pod_id)
    version = read_pod_definition_version(
        db_session=db_session, pod_id=pod_id, version=int(definition.current_version),
    )
    try:
        state_row = read_state(db_session=db_session, pod_id=pod_id)
        state_label = state_row.state.value
    except Exception:  # noqa: BLE001 — state row may not exist yet at M1
        state_label = "UNKNOWN"

    active = read_active_registration(db_session=db_session, pod_id=pod_id)
    report_members_by_name: Dict[str, Mapping[str, Any]] = {}
    if active is not None and isinstance(active.report_json, Mapping) is True:
        for row in active.report_json.get("members", []) or []:
            if isinstance(row, Mapping) is True and row.get("name", None) is not None:
                report_members_by_name[row["name"]] = row

    renderer_map = _load_renderer_map()

    members: List[TopologyMember] = []
    links: List[TopologyLink] = []

    spec_members = (version.spec_json or {}).get("members", [])
    for entry in spec_members:
        if isinstance(entry, Mapping) is False:
            continue
        name = entry.get("name", "")
        kind = entry.get("kind", "")
        report = report_members_by_name.get(name, {})
        hint_cls = renderer_map.get(kind, None) or renderer_map.get("*", None)
        hint = hint_cls.render_hint(member=entry) if hint_cls is not None else {"icon": "generic", "shape": "box", "label": name}
        members.append(TopologyMember(
            name=name,
            kind=kind,
            payload=dict(report),
            hint=hint,
        ))

    for edge in (version.spec_json or {}).get("links", []) or []:
        if isinstance(edge, Mapping) is False:
            continue
        links.append(TopologyLink(
            source=str(edge.get("source", "")),
            target=str(edge.get("target", "")),
            label=str(edge.get("label", "")),
        ))

    report_hash = active.report_hash if active is not None else ""
    etag_seed = json.dumps([version.version, report_hash, state_label], sort_keys=True).encode("utf-8")
    etag = hashlib.sha256(etag_seed).hexdigest()

    rtnval = TopologyGraph(
        pod_id=str(definition.pod_id),
        pod_name=definition.pod_name,
        version=int(version.version),
        state=state_label,
        members=tuple(members),
        links=tuple(links),
        etag=etag,
    )
    _TOPOLOGY_CACHE[str(pod_id)] = rtnval
    return rtnval


def _load_renderer_map() -> Dict[str, Any]:
    """
        Build a ``member_kind → renderer_class`` mapping over every
        registered :class:`PodMemberRendererExtension`.
    """
    rtnval: Dict[str, Any] = {}
    for pack in list_resource_extensions(base_class=PodMemberRendererExtension):
        kind = getattr(pack, "member_kind", "")
        if kind is None or len(kind) == 0:
            continue
        rtnval[kind] = pack
    return rtnval


def topology_as_dict(*, graph: TopologyGraph) -> Mapping[str, Any]:
    """
        Return a JSON-serializable dict of a :class:`TopologyGraph`.
    """
    payload = asdict(graph)
    rtnval = payload
    return rtnval
