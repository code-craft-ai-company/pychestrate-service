"""
.. module:: notifications.run_notifier
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Send the notifications a run's end asks for, off the request path (ORG-F08).

.. moduleauthor:: Code Craft AI LLC

When a run fails or completes, the state machine publishes ``entity.run.failed`` or
``entity.run.completed`` on the in-process bus, inside the commit of the request that
ingests the pod's result. The routing rules turn that into messages
(:mod:`~ccai.pychestrate.webservice.notifications.router`), but sending mail or calling a
webhook must not run inside that request: a slow relay would hold the pod's upload, and a
failing one would fail it. So the subscriber only queues the event; one daemon thread per
process takes events off a bounded queue and delivers them with its own database session.
When the queue is full the event is dropped, logged and counted, never blocking the run.

A process delivers the events published in that process, so with several gunicorn workers
each event is delivered exactly once, by the worker that committed the run's end.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import queue
import threading

from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.jobs.run.state.events import RunStateEventTopics
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent, subscribe, unsubscribe
from ccai.pychestrate.webservice.notifications import router as notification_router
from ccai.pychestrate.webservice.projects.models import Project


_LOGGER = logging.getLogger(__name__)

SessionFactory = Callable[[], DbSession]

#: The run events a rule can ask to be told about.
NOTIFIED_TOPICS: Tuple[str, ...] = (RunStateEventTopics.FAILED, RunStateEventTopics.COMPLETED)

QUEUE_LIMIT: int = 1000

_STOP = object()


def build_template_payload(*, db_session: DbSession, event_payload: Mapping[str, Any]) -> Dict[str, Any]:
    """
        The mapping a notification template renders from a run event: the run id, the
        project (id and slug), the state the run ended in and the reason, if any.

        :param db_session: A session, to name the project.
        :param event_payload: The bus event's payload.

        :returns: The template payload.
    """
    project_id = event_payload.get("project_id", None)
    slug = None
    if project_id is not None:
        try:
            row = db_session.query(Project.slug).filter(Project.project_id == project_id).first()
            slug = row[0] if row is not None else None
        except Exception:  # noqa: BLE001 -- a message with the id is better than none
            slug = None
    rtnval = {
        "run_id": str(event_payload.get("run_id", "")),
        "project_id": str(project_id) if project_id is not None else None,
        "project_slug": slug if slug is not None else (str(project_id) if project_id is not None else "<unknown>"),
        "to_state": str(event_payload.get("to_state", "")),
        "reason": str(event_payload.get("reason", "") or ""),
    }
    return rtnval


class RunNotifier:
    """
        Queues run events and delivers them from one daemon thread.

        :param session_factory: Returns a fresh session for each event.
        :param limiter: The per-rule rate limiter (one per process).
        :param queue_limit: Events held before new ones are dropped.
    """

    def __init__(
            self,
            *,
            session_factory: SessionFactory,
            limiter: Optional[notification_router.RuleRateLimiter] = None,
            queue_limit: int = QUEUE_LIMIT
        ) -> None:
        self._session_factory = session_factory
        self._limiter = limiter if limiter is not None else notification_router.RuleRateLimiter()
        self._queue: "queue.Queue[Any]" = queue.Queue(maxsize=queue_limit)
        self._thread: Optional[threading.Thread] = None
        self._dropped = 0
        self._handled = 0

    @property
    def dropped(self) -> int:
        """How many events were dropped because the queue was full."""
        return self._dropped

    @property
    def handled(self) -> int:
        """How many events the worker has finished (delivered, skipped or failed)."""
        return self._handled

    def start(self) -> None:
        """Start the delivery thread (once)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="pychestrate-run-notifier", daemon=True)
        self._thread.start()
        return

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        """Ask the thread to finish what is queued and stop, and wait for it."""
        thread = self._thread
        if thread is None:
            return
        self._queue.put(_STOP)
        thread.join(timeout=timeout_seconds)
        self._thread = None
        return

    def on_event(self, event: EntityEvent) -> None:
        """
            The bus subscriber: queue the event and return at once. A full queue drops it.

            :param event: The published run event.

            :returns: None.
        """
        try:
            self._queue.put_nowait((event.topic, dict(event.payload)))
        except queue.Full:
            self._dropped += 1
            _LOGGER.error("pychestrate.notifications.queue_full: dropped %s for run %s", event.topic, event.payload.get("run_id", ""))
        return

    def wait_until_idle(self, *, timeout_seconds: float = 5.0) -> bool:
        """
            Block until every queued event has been handled (tests use this).

            :returns: ``True`` when the queue drained within the timeout.
        """
        done = threading.Event()

        def _wait() -> None:
            self._queue.join()
            done.set()

        waiter = threading.Thread(target=_wait, daemon=True)
        waiter.start()
        return done.wait(timeout=timeout_seconds)

    def handle(self, *, topic: str, event_payload: Mapping[str, Any]) -> List[notification_router.RouteOutcome]:
        """
            Deliver one event now, on the calling thread (the worker's body, and what tests call).

            :param topic: The event's topic.
            :param event_payload: The event's payload.

            :returns: What became of each delivery the rules asked for.
        """
        session = self._session_factory()
        try:
            payload = build_template_payload(db_session=session, event_payload=event_payload)
            rtnval = notification_router.route_event(db_session=session, topic=topic, payload=payload, limiter=self._limiter)
        finally:
            session.close()
        return rtnval

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _STOP:
                    return
                topic, event_payload = item
                self.handle(topic=topic, event_payload=event_payload)
            except (KeyboardInterrupt, SystemExit):
                raise
            except BaseException as xcpt:  # noqa: BLE001 -- the worker must outlive one bad event
                _LOGGER.error("pychestrate.notifications.worker_error: %s: %s", type(xcpt).__name__, str(xcpt).replace("\n", " | "))
            finally:
                if item is not _STOP:
                    self._handled += 1
                self._queue.task_done()


_NOTIFIER: Optional[RunNotifier] = None
_LOCK = threading.Lock()


def wire_run_notifications(*, session_factory: SessionFactory, queue_limit: int = QUEUE_LIMIT) -> RunNotifier:
    """
        Subscribe a :class:`RunNotifier` to the run failed and completed topics and start it.
        Calling it again replaces the earlier notifier (a re-bootstrap must not deliver twice).

        :param session_factory: Returns a fresh session.
        :param queue_limit: Events held before new ones are dropped.

        :returns: The running notifier.
    """
    global _NOTIFIER
    with _LOCK:
        unwire_run_notifications()
        notifier = RunNotifier(session_factory=session_factory, queue_limit=queue_limit)
        for topic in NOTIFIED_TOPICS:
            subscribe(topic=topic, subscriber=notifier.on_event)
        notifier.start()
        _NOTIFIER = notifier
    _LOGGER.info("pychestrate.notifications.notifier_started: topics=%s queue_limit=%d", ",".join(NOTIFIED_TOPICS), queue_limit)
    return notifier


def unwire_run_notifications() -> None:
    """Unsubscribe and stop the notifier wired by :func:`wire_run_notifications`, if any."""
    global _NOTIFIER
    notifier = _NOTIFIER
    if notifier is None:
        return
    for topic in NOTIFIED_TOPICS:
        try:
            unsubscribe(topic=topic, subscriber=notifier.on_event)
        except Exception:  # noqa: BLE001 -- already gone
            pass
    notifier.stop()
    _NOTIFIER = None
    return


__all__ = [
    "NOTIFIED_TOPICS",
    "RunNotifier",
    "build_template_payload",
    "unwire_run_notifications",
    "wire_run_notifications",
]
