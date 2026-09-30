"""
.. module:: webinterface.blueprints.projects.dashboard_activity
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: What a person should look at first on the projects dashboard (PRJ-21).

.. moduleauthor:: Code Craft AI LLC

The projects dashboard led with a count ("3"), listed builds and tests from
tables nothing fills ("Project #1", "Recent Tests" always empty) and said nothing
about what was broken. This module reads the runs the service actually holds, for
the projects the viewer can reach: the runs that failed in the last week (what
needs attention), the most recent runs, and each listed project's last run. The
web UI's projects are bridged to the registry projects that runs belong to, so a
run is looked up by the registry id of the project it ran in.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import sqlalchemy as sa

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.jobs.run.state.enums import RunState
from ccai.pychestrate.webservice.jobs.run.state.models import Run
from ccai.pychestrate.webservice.projects.models import Project


#: Run states that mean something went wrong and a person should look.
ATTENTION_STATES = (
    RunState.FAILED,
    RunState.DISPATCH_FAILED,
    RunState.DISPATCH_LOST,
    RunState.NEEDS_INVESTIGATION,
)

#: How far back a failure still counts as needing attention.
ATTENTION_WINDOW_DAYS: int = 7

#: Rows shown in the "needs attention" list and in the recent-runs list.
ATTENTION_LIMIT: int = 5
RECENT_LIMIT: int = 8

_KIND_PREFIXES = (("rpa-", "RPA"), ("build-", "Build"), ("provision-", "Provisioning"))

_TONES = {
    "completed": "success",
    "failed": "danger", "dispatch_failed": "danger", "dispatch_lost": "danger", "needs_investigation": "danger",
    "progress_stalled": "warning", "dispatch_unconfirmed": "warning", "cancel_requested": "warning",
    "cancelling": "warning", "cancelled": "warning",
    "running": "info", "dispatching": "info", "dispatched": "info", "completing": "info",
    "pending": "secondary",
}


def run_kind_label(job_type: Any) -> str:
    """
        What kind of run this is, for a row: ``build-makefile`` -> ``Build · makefile``,
        anything without a known prefix is a test run.

        :param job_type: The run's job type.

        :returns: Text for the row.
    """
    text = str(job_type or "").strip()
    if len(text) == 0:
        return "Run"
    for prefix, label in _KIND_PREFIXES:
        if text.startswith(prefix):
            detail = text[len(prefix):]
            return "{} · {}".format(label, detail) if len(detail) > 0 else label
    return "Test · {}".format(text)


def state_tone(state: str) -> str:
    """
        The badge tone for a run state (the words the tone filter uses).

        :param state: The run state's value.

        :returns: ``success``, ``danger``, ``warning``, ``info`` or ``secondary``.
    """
    return _TONES.get(state, "secondary")


def state_label(state: str) -> str:
    """
        A run state as words: ``dispatch_failed`` -> ``Dispatch failed``.

        :param state: The run state's value.

        :returns: Text for a badge.
    """
    text = state.replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _row(run: Run, projects: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    state = run.state.value if hasattr(run.state, "value") else str(run.state)
    project = projects.get(str(run.project_id), {"legacy_id": None, "name": "Unknown project"})
    return {
        "run_id": str(run.run_id),
        "project_legacy_id": project["legacy_id"],
        "project_name": project["name"],
        "kind": run_kind_label(run.job_type),
        "state": state,
        "state_label": state_label(state),
        "tone": state_tone(state),
        "at": _as_utc(run.entered_state_at),
    }


def registry_projects(*, db_session: DbSession, legacy_ids: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    """
        The registry projects the web UI's projects are bridged to.

        :param db_session: Active session.
        :param legacy_ids: Web-UI project ids (integers or their text).

        :returns: ``{registry uuid: {"legacy_id": int, "name": display name}}``; a
                  project with no registry counterpart has no runs and is absent.
    """
    wanted = []
    for value in legacy_ids:
        try:
            wanted.append(int(value))
        except (TypeError, ValueError):
            continue
    if len(wanted) == 0:
        return {}
    rows = (
        db_session.query(Project.project_id, Project.legacy_proj_id, Project.display_name, Project.slug)
        .filter(Project.legacy_proj_id.in_(wanted))
        .all()
    )
    return {
        str(project_id): {"legacy_id": legacy_id, "name": display_name or slug}
        for project_id, legacy_id, display_name, slug in rows
    }


def _projects_by_uuid(*, db_session: DbSession, uuids: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    """The same mapping, looked up by registry id (for the few projects a list of runs names)."""
    wanted = [uuid_value for uuid_value in uuids]
    if len(wanted) == 0:
        return {}
    rows = (
        db_session.query(Project.project_id, Project.legacy_proj_id, Project.display_name, Project.slug)
        .filter(Project.project_id.in_(wanted))
        .all()
    )
    return {
        str(project_id): {"legacy_id": legacy_id, "name": display_name or slug}
        for project_id, legacy_id, display_name, slug in rows
    }


def collect_run_activity(
        *,
        db_session: DbSession,
        accessible_legacy_ids: Optional[Iterable[Any]],
        listed_legacy_ids: Iterable[Any],
        now: Optional[datetime] = None
    ) -> Dict[str, Any]:
    """
        The runs a viewer should see first.

        :param db_session: Active session.
        :param accessible_legacy_ids: Every web-UI project the viewer can reach, or ``None``
                                      for a viewer who can reach all of them (an administrator).
        :param listed_legacy_ids: The projects the dashboard's table lists (each gets a last run).
        :param now: The moment "the last week" is counted back from (tests pass one).

        :returns: ``{"attention": [...], "recent": [...], "last_by_project": {legacy id: row}}``
                  where a row has ``run_id``, ``project_legacy_id``, ``project_name``, ``kind``,
                  ``state``, ``state_label``, ``tone`` and ``at``.
    """
    moment = now if now is not None else datetime.now(timezone.utc)
    empty: Dict[str, Any] = {"attention": [], "recent": [], "last_by_project": {}}
    if accessible_legacy_ids is None:
        # Every bridged project: a subquery, so nothing is loaded per project.
        scope = Run.project_id.in_(sa.select(Project.project_id).where(Project.legacy_proj_id.isnot(None)))
    else:
        reachable = registry_projects(db_session=db_session, legacy_ids=accessible_legacy_ids)
        if len(reachable) == 0:
            return empty
        scope = Run.project_id.in_(list(reachable.keys()))
    attention = (
        db_session.query(Run)
        .filter(scope, Run.state.in_(ATTENTION_STATES), Run.entered_state_at >= moment - timedelta(days=ATTENTION_WINDOW_DAYS))
        .order_by(Run.entered_state_at.desc())
        .limit(ATTENTION_LIMIT)
        .all()
    )
    recent = (
        db_session.query(Run)
        .filter(scope)
        .order_by(Run.entered_state_at.desc())
        .limit(RECENT_LIMIT)
        .all()
    )
    listed = registry_projects(db_session=db_session, legacy_ids=listed_legacy_ids)
    if accessible_legacy_ids is not None:
        # A listed project the viewer cannot reach has no last run to show.
        reachable_ids = set(reachable.keys())
        listed = {uuid_text: info for uuid_text, info in listed.items() if uuid_text in reachable_ids}
    named = _projects_by_uuid(db_session=db_session, uuids=set(str(run.project_id) for run in attention + recent))
    named.update(listed)
    last_by_project: Dict[Any, Dict[str, Any]] = {}
    for uuid_text, info in listed.items():
        last = (
            db_session.query(Run)
            .filter(Run.project_id == uuid_text)
            .order_by(Run.entered_state_at.desc())
            .first()
        )
        if last is not None:
            last_by_project[info["legacy_id"]] = _row(last, named)
    return {
        "attention": [_row(run, named) for run in attention],
        "recent": [_row(run, named) for run in recent],
        "last_by_project": last_by_project,
    }


__all__ = [
    "ATTENTION_LIMIT",
    "ATTENTION_STATES",
    "ATTENTION_WINDOW_DAYS",
    "RECENT_LIMIT",
    "collect_run_activity",
    "registry_projects",
    "run_kind_label",
    "state_label",
    "state_tone",
]
