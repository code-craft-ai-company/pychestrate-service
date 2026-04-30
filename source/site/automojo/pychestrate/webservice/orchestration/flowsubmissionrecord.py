"""
.. module:: pychestrate.webservice.orchestration.flowsubmissionrecord
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy ORM model for persistent flow submissions.

.. moduleauthor:: Automation Mojo LLC

A row per submitted taskplus workflow. The :class:`FlowRuntime` reads
and writes through this model so submissions survive a service
restart.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)


class FlowSubmissionRecord(PychestratePhase1Base):
    """
        Persisted state of one taskplus flow submission.

        :ivar flow_id: Server-issued primary key (UUID string).
        :ivar name: Workflow name extracted from the YAML doc.
        :ivar state: Lifecycle state — PENDING / RUNNING /
                     SUCCEEDED / FAILED.
        :ivar submitted_at: Timestamp when the submission was
                            accepted by the runtime.
        :ivar started_at: Timestamp when the worker thread picked
                          the submission up. Null while PENDING.
        :ivar completed_at: Timestamp when the worker exited. Null
                            until terminal.
        :ivar result_code: Taskplus exit code (0 = OK, 1 = errors).
                           Null while not terminal.
        :ivar error_text: Stringified exception when the worker
                          crashed; null otherwise.
        :ivar workflow_yaml: Verbatim YAML body submitted by the
                             caller.
        :ivar log_text: Captured stdout + log lines emitted by the
                        FlowEngine + tasks during execution.
        :ivar actor_user_id: User id from
                             ``request.auth.principal.identifier``
                             at submission time, or null when
                             anonymous.
    """

    __tablename__ = "flow_submission"

    flow_id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False, default="<unnamed>")
    state = Column(String(32), nullable=False, default="PENDING")
    submitted_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    result_code = Column(Integer, nullable=True)
    error_text = Column(Text, nullable=True)
    workflow_yaml = Column(Text, nullable=False, default="")
    log_text = Column(Text, nullable=False, default="")
    actor_user_id = Column(String(36), nullable=True)
