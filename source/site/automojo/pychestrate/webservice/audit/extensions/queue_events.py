"""
.. module:: audit.extensions.queue_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds for worker-job queue lifecycle events.

.. moduleauthor:: Automation Mojo LLC

The worker-job queue is a sensitive surface — it dispatches
shell commands to physical hosts. Operators need a tamper-
evident record of who enqueued what, when, with what payload.
This pack registers the queue-side ``AuditEventTypeExtension``
kinds so the canonical audit chain can record them.

Events (each one a separate kind):

* ``audit.queue.job.enqueued`` — a new ``WorkerJob`` row was
  created. Payload: job_id, kind, target_pod_name, target_kind,
  command (when run-command), priority, project_id, attempt,
  max_attempts, lease_holder, required_capabilities,
  actor_user_id (admin path) or actor_service_identity (agent
  path).
* ``audit.queue.job.claimed`` — a worker atomically flipped a
  PENDING row to CLAIMED. Payload: job_id, worker_id, attempt.
* ``audit.queue.job.reported`` — a worker reported a terminal
  result. Payload: job_id, worker_id, attempt, state,
  result_code.
* ``audit.queue.lease.acquired`` — explicit lease acquire
  (typically via the workers REST surface; the implicit
  acquire-on-claim path is captured by ``job.claimed``).
* ``audit.queue.lease.released`` — explicit lease release.

The chain is tamper-evident — the audit_writer's SHA-256
record-hash chain catches retroactive deletion of a job
enqueue.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.audit.extensions.event_type import (
    AuditEventTypeExtension,
)


class QueueJobEnqueuedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.queue.job.enqueued``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.queue.job.enqueued"
    source_topic: str = "entity.queue.job.enqueued"
    payload_schema: dict = {
        "type": "object",
        "required": ["job_id", "kind"],
        "properties": {
            "job_id": {"type": "string"},
            "kind": {"type": "string"},
            "target_pod_name": {"type": ["string", "null"]},
            "target_kind": {"type": ["string", "null"]},
            "priority": {"type": "integer"},
            "project_id": {"type": ["string", "null"]},
            "attempt": {"type": "integer"},
            "max_attempts": {"type": "integer"},
            "lease_holder": {"type": ["string", "null"]},
            "required_capabilities": {"type": "array"},
            "command": {"type": ["string", "null"]},
        },
    }
    description: str = "A new worker_job row was enqueued."


class QueueJobClaimedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.queue.job.claimed``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.queue.job.claimed"
    source_topic: str = "entity.queue.job.claimed"
    payload_schema: dict = {
        "type": "object",
        "required": ["job_id", "worker_id"],
        "properties": {
            "job_id": {"type": "string"},
            "worker_id": {"type": "string"},
            "attempt": {"type": "integer"},
            "lease_holder": {"type": ["string", "null"]},
        },
    }
    description: str = (
        "A worker atomically flipped a PENDING worker_job to CLAIMED."
    )


class QueueJobReportedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.queue.job.reported``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.queue.job.reported"
    source_topic: str = "entity.queue.job.reported"
    payload_schema: dict = {
        "type": "object",
        "required": ["job_id", "worker_id", "state"],
        "properties": {
            "job_id": {"type": "string"},
            "worker_id": {"type": "string"},
            "attempt": {"type": "integer"},
            "state": {"type": "string"},
            "result_code": {"type": ["integer", "null"]},
            "is_retry": {"type": "boolean"},
        },
    }
    description: str = (
        "A worker reported a (terminal or retry) outcome for a job."
    )


class QueueLeaseAcquiredAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.queue.lease.acquired``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.queue.lease.acquired"
    source_topic: str = "entity.queue.lease.acquired"
    payload_schema: dict = {
        "type": "object",
        "required": ["worker_id", "holder"],
        "properties": {
            "worker_id": {"type": "string"},
            "holder": {"type": "string"},
            "ttl_seconds": {"type": "integer"},
        },
    }
    description: str = (
        "An explicit lease was acquired or refreshed on a worker."
    )


class QueueLeaseReleasedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.queue.lease.released``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.queue.lease.released"
    source_topic: str = "entity.queue.lease.released"
    payload_schema: dict = {
        "type": "object",
        "required": ["worker_id", "holder"],
        "properties": {
            "worker_id": {"type": "string"},
            "holder": {"type": "string"},
        },
    }
    description: str = "An explicit lease was released on a worker."
