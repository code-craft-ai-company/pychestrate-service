"""
.. module:: orchestration.test.live.snapshot
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Snapshot + delta-merge for live progress.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class ProgressSnapshot:
    """
        Read-model of a run's current progress state.

        :param run_id: Run UUID.
        :param project_id: Owning project UUID.
        :param tests_total: Total tests planned.
        :param tests_passed / tests_failed / tests_skipped /
                              tests_errored: rolling counters.
        :param percent_complete: Optional float [0, 100].
        :param state: Current run state from
                      ``5-run-state-machine`` (string-typed for
                      transport).
        :param latest_event_at: UTC timestamp of the most recent
                                event merged.
        :param sequence: Monotonically-increasing event sequence
                         the relay assigns. Subscribers use this
                         as the SSE ``id:`` field for replay.
        :param latest_progress_frame: The most recent generalized
                                      build / provision progress
                                      frame payload merged, or
                                      ``None`` for a test run (or a
                                      build / provision run before
                                      its first frame). Lets a
                                      late-joining SSE subscriber
                                      snapshot the current build /
                                      provision progress.
    """
    run_id: str
    project_id: str
    tests_total: Optional[int]
    tests_passed: int
    tests_failed: int
    tests_skipped: int
    tests_errored: int
    percent_complete: Optional[float]
    state: str
    latest_event_at: datetime
    sequence: int
    latest_progress_frame: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class ProgressEvent:
    """
        One progress observation broadcast on the relay.

        :param run_id: Run UUID.
        :param project_id: Owning project UUID.
        :param kind: Event kind tag (``"progress.summary"``,
                     ``"progress.record"``, ``"state_changed"``,
                     ``"result_tree.landed"``).
        :param payload: Untyped passthrough.
        :param recorded_at: UTC timestamp the producer assigned.
        :param sequence: Monotonic per-run id assigned by the
                         relay on append.
    """
    run_id: str
    project_id: str
    kind: str
    payload: Mapping[str, Any]
    recorded_at: datetime
    sequence: int


def empty_snapshot(*, run_id: str, project_id: str) -> ProgressSnapshot:
    """
        Construct a zeroed snapshot — used when the first event
        arrives for a run without prior state.
    """
    rtnval = ProgressSnapshot(
        run_id=run_id,
        project_id=project_id,
        tests_total=None,
        tests_passed=0,
        tests_failed=0,
        tests_skipped=0,
        tests_errored=0,
        percent_complete=None,
        state="",
        latest_event_at=datetime.now(timezone.utc),
        sequence=0,
        latest_progress_frame=None,
    )
    return rtnval


def merge_event(
        *,
        snapshot: ProgressSnapshot,
        event: ProgressEvent
    ) -> ProgressSnapshot:
    """
        Apply ``event`` to ``snapshot`` and return a new snapshot.
        Pure function — never mutates the input.

        Recognized event kinds:

        - ``"progress.summary"`` — overwrites the count fields
          from the event payload.
        - ``"progress.frame"`` — stores the generalized build /
          provision progress frame payload as
          ``latest_progress_frame``.
        - ``"state_changed"`` — overwrites ``state``.
        - others — only update ``latest_event_at`` + ``sequence``.

        :param snapshot: Prior snapshot.
        :param event: Event to merge.

        :returns: Updated snapshot.
    """
    tests_total = snapshot.tests_total
    tests_passed = snapshot.tests_passed
    tests_failed = snapshot.tests_failed
    tests_skipped = snapshot.tests_skipped
    tests_errored = snapshot.tests_errored
    percent_complete = snapshot.percent_complete
    state = snapshot.state
    latest_progress_frame = snapshot.latest_progress_frame

    if event.kind == "progress.summary":
        payload = event.payload
        if isinstance(payload, Mapping):
            tests_total = payload.get("tests_total", tests_total)
            tests_passed = int(payload.get("tests_passed", tests_passed))
            tests_failed = int(payload.get("tests_failed", tests_failed))
            tests_skipped = int(payload.get("tests_skipped", tests_skipped))
            tests_errored = int(payload.get("tests_errored", tests_errored))
            percent_complete = payload.get("percent_complete", percent_complete)

    if event.kind == "progress.frame":
        payload = event.payload
        if isinstance(payload, Mapping):
            latest_progress_frame = dict(payload)
            frame_percent = payload.get("percent_complete", None)
            if frame_percent is not None:
                percent_complete = frame_percent

    if event.kind == "state_changed":
        if isinstance(event.payload, Mapping):
            new_state = event.payload.get("to_state", state)
            if isinstance(new_state, str) is True:
                state = new_state

    rtnval = ProgressSnapshot(
        run_id=snapshot.run_id,
        project_id=snapshot.project_id,
        tests_total=tests_total,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        tests_skipped=tests_skipped,
        tests_errored=tests_errored,
        percent_complete=percent_complete,
        state=state,
        latest_event_at=event.recorded_at,
        sequence=event.sequence,
        latest_progress_frame=latest_progress_frame,
    )
    return rtnval
