"""rpa: specifications and jobs the web UI made are keyed by the registry project, as the REST surface's are

The web UI stored a project's RPA specifications and jobs under the text of its integer id ("1") and the REST surface under the project's UUID, so one project had two disjoint
sets (the jobs list on the page said "No RPA jobs yet" while the REST surface listed the jobs). The UI now uses the registry project's UUID (``specs/project-model-bridge.md``:
the registry project is the system of record); this re-keys the rows the UI already made: the UUID of the registry project bridged to that integer id
(``projects_projects.legacy_proj_id``), or, for a project with no registry row, the UUID derived from the integer (the one a bridged web-UI project keeps).

A specification whose name is already taken in the registry project (a spec of that name made through the REST surface) is renamed "<name> (web UI)", then "<name> (web UI 2)", and so
on, so none is lost. Nothing is deleted. Not reversed on downgrade: the old key cannot be told apart from the new one afterwards, and the previous release reads neither.

Revision ID: a3c5e7f9b1d2
Revises: f7b2c9a4d1e6
Create Date: 2026-10-15 09:00:00+00:00

"""
import uuid

from typing import Dict, Sequence, Union

from alembic import op
import sqlalchemy as sa

from ccai.pychestrate.webservice.projects.legacy_identity import derived_project_uuid


# revision identifiers, used by Alembic.
revision: str = "a3c5e7f9b1d2"
down_revision: Union[str, Sequence[str], None] = "f7b2c9a4d1e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NAME_MAX = 128


def _bridged_projects(connection: sa.engine.Connection) -> Dict[str, str]:
    """
        ``{integer id text: registry project UUID text}`` for every registry project bridged to a web-UI project.
    """
    rtnval: Dict[str, str] = {}
    inspector = sa.inspect(connection)
    if "projects_projects" not in inspector.get_table_names():
        return rtnval
    rows = connection.execute(sa.text("SELECT project_id, legacy_proj_id FROM projects_projects WHERE legacy_proj_id IS NOT NULL")).fetchall()
    for project_id, legacy_id in rows:
        rtnval[str(int(legacy_id))] = str(uuid.UUID(str(project_id)))
    return rtnval


def _free_name(connection: sa.engine.Connection, *, project: str, name: str) -> str:
    """
        ``name`` if no specification of the project has it, else "<name> (web UI)", "<name> (web UI 2)", ... cut to the column's length.
    """
    def _taken(candidate: str) -> bool:
        return connection.execute(
            sa.text("SELECT 1 FROM orch_rpa_spec WHERE project_id = :project AND name = :name"), {"project": project, "name": candidate},
        ).first() is not None

    if not _taken(name):
        return name
    number = 1
    while True:
        suffix = " (web UI)" if number == 1 else " (web UI {})".format(number)
        candidate = name[: NAME_MAX - len(suffix)] + suffix
        if not _taken(candidate):
            return candidate
        number += 1


def upgrade() -> None:
    """
        Re-key the web UI's RPA specifications and jobs to the registry project's UUID.
    """
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()
    if "orch_rpa_spec" not in tables or "orch_rpa_job" not in tables:
        return
    bridged = _bridged_projects(connection)

    keys = set()
    for table in ("orch_rpa_spec", "orch_rpa_job"):
        for (value,) in connection.execute(sa.text("SELECT DISTINCT project_id FROM {}".format(table))).fetchall():
            if value is not None and str(value).strip().isdigit():
                keys.add(str(value).strip())

    for key in sorted(keys):
        target = bridged.get(str(int(key)), derived_project_uuid(key))
        for spec_id, name in connection.execute(
            sa.text("SELECT spec_id, name FROM orch_rpa_spec WHERE project_id = :key ORDER BY created_at, spec_id"), {"key": key},
        ).fetchall():
            connection.execute(
                sa.text("UPDATE orch_rpa_spec SET project_id = :target, name = :name WHERE spec_id = :spec_id"),
                {"target": target, "name": _free_name(connection, project=target, name=name), "spec_id": spec_id},
            )
        connection.execute(sa.text("UPDATE orch_rpa_job SET project_id = :target WHERE project_id = :key"), {"target": target, "key": key})
    return


def downgrade() -> None:
    """
        Nothing to undo: see the module note.
    """
    return
