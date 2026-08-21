"""
.. module:: metrics.dashboards.service
    :synopsis: Dashboard facade — create / read / update / delete.

M1 ships:

* :func:`create_dashboard` — name UNIQUE per project; tiles
  validated against their kind's ``validate_config``.
* :func:`get_dashboard` / :func:`list_dashboards_for_project`.
* :func:`update_dashboard_tiles` — replace the tile array;
  per-tile validation; bumps the version (optimistic
  concurrency counter).
* :func:`update_dashboard` — in-place update of name /
  description / grid width / tiles; name-conflict checked;
  bumps the version.
* :func:`delete_dashboard` — idempotent on miss.
* :func:`list_tile_kinds` — read every registered tile kind
  in PRECEDENCE order.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.metrics.dashboards import repository
from ccai.pychestrate.webservice.metrics.dashboards.errors import (
    DashboardConflictError,
    DashboardNotFoundError,
    TileConfigInvalidError,
    TileKindUnknownError,
)
from ccai.pychestrate.webservice.metrics.dashboards.events import (
    DashboardEventTopics,
)
from ccai.pychestrate.webservice.metrics.dashboards.factories.tile_kind_protocol import (
    DashboardTileKindProtocol,
    TileKindRecord,
)
from ccai.pychestrate.webservice.metrics.dashboards.models import (
    Dashboard,
)


DASHBOARD_TILE_KIND_PROTOCOL: str = "dashboard_tile_kind"
DEFAULT_GRID_COLUMNS_MAX: int = 12


@dataclass(frozen=True)
class TileInstance:
    """
        Caller-supplied tile placement.
    """
    tile_id: str
    kind: str
    x: int
    y: int
    w: int
    h: int
    config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DashboardView:
    """
        Caller-facing read-model.
    """
    dashboard_id: str
    project_id: str
    name: str
    description: str
    owner_principal_id: Optional[str]
    grid_columns_max: int
    tiles: Tuple[TileInstance, ...]
    version: int
    created_at: datetime
    updated_at: datetime


def create_dashboard(
        *,
        db_session: DbSession,
        project_id: str,
        name: str,
        description: str = "",
        owner_principal_id: Optional[str] = None,
        grid_columns_max: int = DEFAULT_GRID_COLUMNS_MAX,
        tiles: Optional[List[TileInstance]] = None
    ) -> DashboardView:
    """
        Persist a fresh dashboard. Per-tile validation runs
        against the kind's ``validate_config``. UNIQUE on
        ``(project_id, name)`` — re-using a name raises
        :class:`DashboardConflictError`.
    """
    if name is None or len(name) == 0:
        err_lines = ["Dashboard name must be non-empty."]
        err_msg = os.linesep.join(err_lines)
        raise TileConfigInvalidError(err_msg) from None

    existing = repository.find_by_name(
        db_session=db_session, project_id=project_id, name=name,
    )
    if existing is not None:
        err_lines = ["Dashboard name already exists in project."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("NAME: {}".format(name))
        err_msg = os.linesep.join(err_lines)
        raise DashboardConflictError(err_msg) from None

    effective_tiles = list(tiles or [])
    _validate_tiles(tiles=effective_tiles)

    now = utc_now()
    row = repository.insert_dashboard(
        db_session=db_session,
        project_id=project_id,
        name=name,
        description=description,
        owner_principal_id=owner_principal_id,
        grid_columns_max=grid_columns_max,
        tiles=[_tile_to_payload(tile=t) for t in effective_tiles],
        created_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=DashboardEventTopics.CREATED,
            payload={
                "dashboard_id": str(row.dashboard_id),
                "project_id": project_id,
                "name": name,
                "tile_count": len(effective_tiles),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def get_dashboard(
        *,
        db_session: DbSession,
        dashboard_id: str
    ) -> DashboardView:
    """
        Read by id.

        :raises: DashboardNotFoundError on miss.
    """
    row = repository.find_by_id(
        db_session=db_session, dashboard_id=dashboard_id,
    )
    if row is None:
        err_lines = ["Dashboard not found."]
        err_lines.append("DASHBOARD_ID: {}".format(dashboard_id))
        err_msg = os.linesep.join(err_lines)
        raise DashboardNotFoundError(err_msg) from None
    rtnval = _to_view(row=row)
    return rtnval


def list_dashboards_for_project(
        *,
        db_session: DbSession,
        project_id: str
    ) -> List[DashboardView]:
    """
        Project-scoped list, name ascending.
    """
    rows = repository.list_for_project(
        db_session=db_session, project_id=project_id,
    )
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def update_dashboard_tiles(
        *,
        db_session: DbSession,
        dashboard_id: str,
        tiles: List[TileInstance],
        expected_version: Optional[int] = None
    ) -> DashboardView:
    """
        Replace the tile array. Validates every tile through
        the kind's ``validate_config``. ``expected_version``
        enables optimistic concurrency — when supplied, the
        caller's version must match the persisted version.

        :raises: DashboardNotFoundError, TileKindUnknownError,
                 TileConfigInvalidError,
                 DashboardConflictError on version mismatch.
    """
    row = repository.find_by_id(
        db_session=db_session, dashboard_id=dashboard_id,
    )
    if row is None:
        err_lines = ["Dashboard not found."]
        err_lines.append("DASHBOARD_ID: {}".format(dashboard_id))
        err_msg = os.linesep.join(err_lines)
        raise DashboardNotFoundError(err_msg) from None

    if expected_version is not None and expected_version != row.version:
        err_lines = ["Dashboard version mismatch."]
        err_lines.append("EXPECTED: {}".format(expected_version))
        err_lines.append("ACTUAL: {}".format(row.version))
        err_msg = os.linesep.join(err_lines)
        raise DashboardConflictError(err_msg) from None

    _validate_tiles(tiles=tiles)
    now = utc_now()
    row.tiles = [_tile_to_payload(tile=t) for t in tiles]
    row.version = row.version + 1
    row.updated_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=DashboardEventTopics.UPDATED,
            payload={
                "dashboard_id": str(row.dashboard_id),
                "project_id": str(row.project_id),
                "tile_count": len(tiles),
                "version": row.version,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def update_dashboard(
        *,
        db_session: DbSession,
        dashboard_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        grid_columns_max: Optional[int] = None,
        tiles: Optional[List[TileInstance]] = None,
        expected_version: Optional[int] = None
    ) -> DashboardView:
    """
        Update a dashboard in place. Only the supplied fields
        change -- pass ``None`` to keep the persisted value. A
        supplied ``tiles`` list replaces the whole tile array
        after per-tile validation. Renaming to a name already
        used by another dashboard in the same project raises
        :class:`DashboardConflictError`. ``expected_version``
        enables optimistic concurrency -- when supplied, the
        caller's version must match the persisted version.

        :param db_session: Active SQLAlchemy session.
        :param dashboard_id: Dashboard UUID to update.
        :param name: Replacement name, or ``None`` to keep.
        :param description: Replacement description, or ``None``
                            to keep.
        :param grid_columns_max: Replacement grid width, or
                                 ``None`` to keep.
        :param tiles: Replacement tile array, or ``None`` to
                      keep.
        :param expected_version: Optional optimistic-concurrency
                                 version guard.

        :returns: The updated :class:`DashboardView`.

        :raises: DashboardNotFoundError, TileKindUnknownError,
                 TileConfigInvalidError,
                 DashboardConflictError on name or version
                 conflict.
    """
    row = repository.find_by_id(
        db_session=db_session, dashboard_id=dashboard_id,
    )
    if row is None:
        err_lines = ["Dashboard not found."]
        err_lines.append("DASHBOARD_ID: {}".format(dashboard_id))
        err_msg = os.linesep.join(err_lines)
        raise DashboardNotFoundError(err_msg) from None

    if expected_version is not None and expected_version != row.version:
        err_lines = ["Dashboard version mismatch."]
        err_lines.append("EXPECTED: {}".format(expected_version))
        err_lines.append("ACTUAL: {}".format(row.version))
        err_msg = os.linesep.join(err_lines)
        raise DashboardConflictError(err_msg) from None

    if name is not None and name != row.name:
        if len(name) == 0:
            err_lines = ["Dashboard name must be non-empty."]
            err_msg = os.linesep.join(err_lines)
            raise TileConfigInvalidError(err_msg) from None
        existing = repository.find_by_name(
            db_session=db_session,
            project_id=str(row.project_id),
            name=name,
        )
        if existing is not None:
            err_lines = ["Dashboard name already exists in project."]
            err_lines.append("PROJECT_ID: {}".format(row.project_id))
            err_lines.append("NAME: {}".format(name))
            err_msg = os.linesep.join(err_lines)
            raise DashboardConflictError(err_msg) from None
        row.name = name

    if description is not None:
        row.description = description

    if grid_columns_max is not None:
        row.grid_columns_max = grid_columns_max

    if tiles is not None:
        _validate_tiles(tiles=tiles)
        row.tiles = [_tile_to_payload(tile=t) for t in tiles]

    now = utc_now()
    row.version = row.version + 1
    row.updated_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=DashboardEventTopics.UPDATED,
            payload={
                "dashboard_id": str(row.dashboard_id),
                "project_id": str(row.project_id),
                "tile_count": len(row.tiles or []),
                "version": row.version,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def delete_dashboard(
        *,
        db_session: DbSession,
        dashboard_id: str
    ) -> bool:
    """
        Idempotent delete. Returns ``True`` when a row was
        deleted; ``False`` on miss.
    """
    row = repository.find_by_id(
        db_session=db_session, dashboard_id=dashboard_id,
    )
    if row is None:
        return False
    project_id = str(row.project_id)
    repository.delete_dashboard_row(db_session=db_session, row=row)
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=DashboardEventTopics.DELETED,
            payload={
                "dashboard_id": dashboard_id,
                "project_id": project_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return True


def list_tile_kinds() -> Tuple[TileKindRecord, ...]:
    """
        Enumerate registered tile-kind records in PRECEDENCE
        order.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=DASHBOARD_TILE_KIND_PROTOCOL,
    )
    rtnval = tuple(impl.record() for impl in candidates)
    return rtnval


def _validate_tiles(*, tiles: List[TileInstance]) -> None:
    issues: List[str] = []
    seen_ids: List[str] = []
    for index, tile in enumerate(tiles):
        if tile.tile_id in seen_ids:
            issues.append(
                "tiles[{}].tile_id duplicate: '{}'".format(
                    index, tile.tile_id,
                )
            )
        seen_ids.append(tile.tile_id)
        kind_cls = _try_resolve_kind(kind_name=tile.kind)
        if kind_cls is None:
            err_lines = ["Tile references an unknown kind."]
            err_lines.append("TILE_ID: {}".format(tile.tile_id))
            err_lines.append("KIND: {}".format(tile.kind))
            err_lines.append("REGISTERED: {}".format(", ".join(
                impl.kind_name() for impl in list_factory_implementations(
                    factory_protocol_name=DASHBOARD_TILE_KIND_PROTOCOL,
                )
            )))
            err_msg = os.linesep.join(err_lines)
            raise TileKindUnknownError(err_msg) from None
        ok, kind_issues = kind_cls.validate_config(config=tile.config)
        if ok is False:
            for issue in kind_issues:
                issues.append(
                    "tiles[{}] '{}': {}".format(index, tile.tile_id, issue),
                )

        if tile.x < 0 or tile.y < 0 or tile.w <= 0 or tile.h <= 0:
            issues.append(
                "tiles[{}].(x, y, w, h) must be non-negative with positive size".format(
                    index,
                )
            )

    if len(issues) > 0:
        err_lines = [
            "Tile validation failed: {} issue(s).".format(len(issues)),
        ]
        for index, issue in enumerate(issues):
            err_lines.append("  [{}] {}".format(index + 1, issue))
        err_msg = os.linesep.join(err_lines)
        raise TileConfigInvalidError(err_msg) from None
    return


def _try_resolve_kind(
        *, kind_name: str
    ) -> Optional[Type[DashboardTileKindProtocol]]:
    candidates = list_factory_implementations(
        factory_protocol_name=DASHBOARD_TILE_KIND_PROTOCOL,
    )
    for impl in candidates:
        if impl.kind_name() == kind_name:
            return impl
    return None


def _tile_to_payload(*, tile: TileInstance) -> Dict[str, Any]:
    rtnval: Dict[str, Any] = {
        "tile_id": tile.tile_id,
        "kind": tile.kind,
        "x": tile.x,
        "y": tile.y,
        "w": tile.w,
        "h": tile.h,
        "config": dict(tile.config),
    }
    return rtnval


def _payload_to_tile(*, payload: Mapping[str, Any]) -> TileInstance:
    rtnval = TileInstance(
        tile_id=payload.get("tile_id", ""),
        kind=payload.get("kind", ""),
        x=payload.get("x", 0),
        y=payload.get("y", 0),
        w=payload.get("w", 0),
        h=payload.get("h", 0),
        config=dict(payload.get("config", {})),
    )
    return rtnval


def _to_view(*, row: Dashboard) -> DashboardView:
    tile_views = tuple(
        _payload_to_tile(payload=p) for p in (row.tiles or [])
    )
    rtnval = DashboardView(
        dashboard_id=str(row.dashboard_id),
        project_id=str(row.project_id),
        name=row.name,
        description=row.description,
        owner_principal_id=(
            str(row.owner_principal_id)
            if row.owner_principal_id is not None
            else None
        ),
        grid_columns_max=row.grid_columns_max,
        tiles=tile_views,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return rtnval
