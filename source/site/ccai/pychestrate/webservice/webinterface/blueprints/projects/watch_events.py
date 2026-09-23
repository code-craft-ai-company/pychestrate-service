"""
.. module:: webinterface.blueprints.projects.watch_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Fire project watches from what the projects pages do.

.. moduleauthor:: Code Craft AI LLC

Watches listen for four events: new commits, new branches and new tags
in a project repository, and a build that finished. The repository
events are found by a fetch (:meth:`RepositoryManager.fetch_latest`)
and build completion is reported through
:meth:`BuildManager.complete_build`; both hand each event to an event
sink. The sink built here processes the event with the project's
watches, running their actions as the signed-in user and with the RPA
trigger the core managers do not have.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional


def build_watch_event_sink(
        *, db_session: Any, user_id: Optional[str]
    ) -> Callable[..., List[Any]]:
    """
        The ``event_sink`` :class:`RepositoryManager` and
        :class:`BuildManager` take: ``(*, trigger_source, source_id,
        event_data, user_id=None)`` returning the trigger logs of the
        watches that fired.

        :param db_session: Open SQLAlchemy session.
        :param user_id: The signed-in user; the watches' actions run as
                        this user unless the event names another.

        :returns: The sink.
    """
    def _sink(
            *, trigger_source: Any, source_id: int, event_data: Dict[str, Any],
            user_id: Optional[str] = None
        ) -> List[Any]:
        from ccai.pychestrate.core.managers.watch_manager import (  # noqa: E402
            dispatch_watch_event,
        )
        from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes_rpa import (  # noqa: E402
            build_watch_rpa_trigger,
        )
        rtnval = dispatch_watch_event(
            db_session=db_session,
            trigger_source=trigger_source,
            source_id=source_id,
            event_data=event_data,
            user_id=user_id or bound_user_id,
            rpa_trigger=build_watch_rpa_trigger(db_session=db_session),
        )
        return rtnval

    bound_user_id = str(user_id) if user_id else None
    return _sink


def describe_fetch(*, repository: Any) -> str:
    """
        The message shown after a fetch: what changed since the previous
        fetch and how many watches fired.

        :param repository: The :class:`RepositoryResponse` the fetch
                           returned.

        :returns: One or two sentences.
    """
    changes = list(getattr(repository, "ref_changes", None) or [])
    fired = int(getattr(repository, "watches_triggered", 0) or 0)

    commits = sorted({c["name"] for c in changes if c.get("change") == "commit"})
    branches = sorted({c["name"] for c in changes if c.get("change") == "branch_created"})
    tags = sorted({c["name"] for c in changes if c.get("change") == "tag_created"})

    parts: List[str] = []
    if len(commits) > 0:
        parts.append("new commits on {}".format(", ".join(commits)))
    if len(branches) > 0:
        parts.append("new {} {}".format("branch" if len(branches) == 1 else "branches", ", ".join(branches)))
    if len(tags) > 0:
        parts.append("new {} {}".format("tag" if len(tags) == 1 else "tags", ", ".join(tags)))

    if getattr(repository, "refs_first_recorded", False) is True:
        rtnval = (
            "Repository information updated. Its branches and tags are recorded now; "
            "later fetches start this repository's watches for new commits, branches and tags."
        )
    elif len(parts) == 0:
        rtnval = "Repository information updated. No new commits, branches or tags since the last fetch."
    else:
        rtnval = "Repository information updated: {}.".format("; ".join(parts))
        if fired == 1:
            rtnval = rtnval + " 1 watch triggered."
        elif fired > 1:
            rtnval = rtnval + " {} watches triggered.".format(fired)
        else:
            rtnval = rtnval + " No watch matched."
    return rtnval


__all__ = [
    "build_watch_event_sink",
    "describe_fetch",
]
