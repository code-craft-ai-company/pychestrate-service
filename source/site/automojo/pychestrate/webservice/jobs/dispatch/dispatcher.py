"""
.. module:: jobs.dispatch.dispatcher
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: JobDispatcher — build envelope + transmit + record attempt.

.. moduleauthor:: Automation Mojo LLC

The dispatcher is the single entry point that turns a dispatch
request into (a) a signed envelope persisted to the envelope
archive, (b) a ``dispatch_attempt`` row, and (c) a transport call
that hands the envelope to the pod client. M1 ships the happy
path only — ack timers, backoff queue, and run-state hand-off land
in M2 per ``specs/5-job-dispatch/tasks.md``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import ConfigurationError, SemanticError

from automojo.pychestrate.core.defaults import utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    resolve_factory_implementation,
)
from automojo.pychestrate.webservice.jobs.dispatch import repository
from automojo.pychestrate.webservice.jobs.dispatch.errors import (
    DispatchNoCandidatesError,
    DispatchStrategyNotRegisteredError,
    DispatchTransportError,
)
from automojo.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
    DispatchStrategyProtocol,
)
from automojo.pychestrate.webservice.jobs.dispatch.models import (
    DispatchAttempt,
    DispatchAttemptStatus,
)
from automojo.pychestrate.webservice.jobs.dispatch.transport_adapter import (
    ClientTransportProtocol,
)
from automojo.pychestrate.webservice.jobs.envelope import (
    DEFAULT_JOB_KIND,
    DispatchRequest as EnvelopeDispatchRequest,
    JobDeadline,
    JobForwardingInfo,
    JobPipelineRef,
    JobRefs,
    JobResultsLocator,
    ScopedSecret,
    SignedJobEnvelope,
    build as build_envelope,
    persist_signed_envelope,
    sign as sign_envelope,
)


DISPATCH_STRATEGY_PROTOCOL: str = "dispatch_strategy"


@dataclass(frozen=True)
class DispatchRequestInputs:
    """
        Caller-supplied inputs that drive one dispatch. The
        dispatcher fills in service-side fields (envelope id,
        issued_at, issuer) inside :meth:`dispatch`.

        :param run_id: Pre-created run UUID.
        :param project_id: Owning project UUID.
        :param job_id: Job-catalog UUID.
        :param job_name: Human-readable job identifier.
        :param job_type: Job-type string.
        :param job_kind: Job-class discriminator
                         (``"test"`` / ``"build"`` / ``"provision"``).
                         Defaults to ``"test"`` so existing test-run
                         dispatch callsites need no change.
        :param issuer: Service DNS-name + release string.
        :param refs: Build / branch / commit references.
        :param params: JSON-serializable parameter map.
        :param scoped_secrets: Materialized short-lived credentials
                               (empty tuple is permitted on M1).
        :param results: Results-backend path + driver.
        :param forwarding: Live progress / summary endpoints.
        :param deadline: Soft + hard deadlines.
        :param pipeline: Optional pipeline reference.
        :param extension_claims: Extension-contributed claims (M1
                                 ignores them).
        :param candidates: Non-empty list of eligible targets. In
                           M1 the caller populates this directly;
                           M2 wires the ``3-client-registry`` +
                           ``3-pod-lifecycle`` eligibility filter.
    """
    run_id: str
    project_id: str
    job_id: str
    job_name: str
    job_type: str
    issuer: str
    refs: JobRefs
    params: Dict[str, Any]
    scoped_secrets: Tuple[ScopedSecret, ...]
    results: JobResultsLocator
    forwarding: JobForwardingInfo
    deadline: JobDeadline
    pipeline: Optional[JobPipelineRef] = None
    extension_claims: Optional[Dict[str, Any]] = None
    candidates: Sequence[DispatchCandidate] = field(default_factory=tuple)
    job_kind: str = DEFAULT_JOB_KIND


@dataclass(frozen=True)
class DispatchOutcome:
    """
        Returned from :meth:`JobDispatcher.dispatch` on success.

        :param attempt_id: Persisted ``dispatch_attempt`` row UUID.
        :param envelope_id: Envelope UUID on the attempt.
        :param signed: The signed envelope (also archived).
        :param strategy_name: Strategy that picked the candidate.
        :param transport_name: Transport the envelope travelled on.
        :param client_id: Chosen target client UUID.
        :param pod_id: Chosen target pod UUID.
        :param status: Post-transmit attempt status — ``TRANSMITTED``
                       on the happy path, ``TRANSPORT_FAILED`` when
                       the transport adapter raised.
    """
    attempt_id: str
    envelope_id: str
    signed: SignedJobEnvelope
    strategy_name: str
    transport_name: str
    client_id: str
    pod_id: str
    status: DispatchAttemptStatus


class JobDispatcher:
    """
        Dispatch facade the REST / orchestration layer calls. One
        :class:`JobDispatcher` is constructed per process; it is
        stateless at the instance level so callers can also create
        a fresh one per request with no penalty.
    """

    def __init__(
            self,
            *,
            transport: ClientTransportProtocol
        ) -> None:
        """
            Construct the dispatcher.

            :param transport: :class:`ClientTransportProtocol`
                              implementation the dispatcher hands
                              signed envelopes to.

            :returns: None.
        """
        self._transport: ClientTransportProtocol = transport
        return

    def dispatch(
            self,
            *,
            db_session: DbSession,
            inputs: DispatchRequestInputs
        ) -> DispatchOutcome:
        """
            Build a signed envelope for the caller's request, pick
            a target via the active :class:`DispatchStrategyProtocol`,
            persist the envelope + attempt rows, and hand the
            envelope to the transport. Transport failures are
            recorded on the attempt row as ``TRANSPORT_FAILED`` and
            surfaced as :class:`DispatchTransportError`; other
            failures (no candidates, no strategy) are raised before
            any row is persisted.

            :param db_session: Active SQLAlchemy session.
            :param inputs: Caller-supplied :class:`DispatchRequestInputs`.

            :returns: :class:`DispatchOutcome`.
            :raises: DispatchNoCandidatesError,
                     DispatchStrategyNotRegisteredError,
                     DispatchTransportError, SemanticError.
        """
        if inputs.candidates is None or len(inputs.candidates) == 0:
            err_lines = ["Dispatch rejected — no eligible candidates supplied."]
            err_lines.append("RUN_ID: {}".format(inputs.run_id))
            err_lines.append("PROJECT_ID: {}".format(inputs.project_id))
            err_msg = os.linesep.join(err_lines)
            raise DispatchNoCandidatesError(err_msg) from None

        strategy = self._resolve_strategy()
        chosen = strategy.pick(candidates=inputs.candidates)
        if chosen is None:
            err_lines = ["Dispatch strategy rejected every candidate."]
            err_lines.append("RUN_ID: {}".format(inputs.run_id))
            err_lines.append("STRATEGY: {}".format(strategy.strategy_name()))
            err_lines.append("CANDIDATE_COUNT: {}".format(len(inputs.candidates)))
            err_msg = os.linesep.join(err_lines)
            raise DispatchNoCandidatesError(err_msg) from None

        extension_claims = inputs.extension_claims
        if extension_claims is None:
            extension_claims = {}

        envelope_request = EnvelopeDispatchRequest(
            project_id=inputs.project_id,
            job_id=inputs.job_id,
            job_name=inputs.job_name,
            job_type=inputs.job_type,
            job_kind=inputs.job_kind,
            run_id=inputs.run_id,
            client_id=chosen.client_id,
            pod_id=chosen.pod_id,
            issuer=inputs.issuer,
            pipeline=inputs.pipeline,
            refs=inputs.refs,
            params=dict(inputs.params),
            scoped_secrets=tuple(inputs.scoped_secrets),
            results=inputs.results,
            forwarding=inputs.forwarding,
            deadline=inputs.deadline,
            extension_claims=dict(extension_claims),
        )
        envelope = build_envelope(request=envelope_request)
        signed = sign_envelope(envelope=envelope)
        persist_signed_envelope(db_session=db_session, signed=signed)

        now = utc_now()
        attempt = repository.create_attempt(
            db_session=db_session,
            run_id=inputs.run_id,
            project_id=inputs.project_id,
            client_id=chosen.client_id,
            pod_id=chosen.pod_id,
            envelope_id=envelope.envelope_id,
            strategy_name=strategy.strategy_name(),
            transport_name=self._transport.transport_name(),
            created_at=now,
        )

        try:
            self._transport.transmit(
                client_id=chosen.client_id,
                pod_id=chosen.pod_id,
                signed=signed,
            )
        except DispatchTransportError as xcpt:
            repository.mark_attempt_transport_failed(
                db_session=db_session,
                attempt=attempt,
                failure_reason=str(xcpt),
            )
            db_session.commit()
            raise

        repository.mark_attempt_transmitted(
            db_session=db_session,
            attempt=attempt,
            transmitted_at=utc_now(),
        )
        db_session.commit()

        rtnval = DispatchOutcome(
            attempt_id=str(attempt.attempt_id),
            envelope_id=envelope.envelope_id,
            signed=signed,
            strategy_name=strategy.strategy_name(),
            transport_name=self._transport.transport_name(),
            client_id=chosen.client_id,
            pod_id=chosen.pod_id,
            status=DispatchAttemptStatus.TRANSMITTED,
        )
        return rtnval

    def _resolve_strategy(self):
        """
            Fetch the highest-precedence registered
            :class:`DispatchStrategyProtocol` or raise.

            :returns: Strategy class.
            :raises: DispatchStrategyNotRegisteredError.
        """
        try:
            rtnval = resolve_factory_implementation(
                factory_protocol_name=DISPATCH_STRATEGY_PROTOCOL,
                predicate=None,
            )
        except ConfigurationError as xcpt:
            err_lines = ["No dispatch_strategy implementation is registered."]
            err_lines.append("HINT: call register_builtin_extensions() on startup.")
            err_lines.append("UNDERLYING: {}".format(str(xcpt)))
            err_msg = os.linesep.join(err_lines)
            raise DispatchStrategyNotRegisteredError(err_msg) from xcpt
        return rtnval
