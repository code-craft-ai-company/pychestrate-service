"""
.. module:: jobs.envelope
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-5 JobEnvelope — canonical, signed dispatch payload.

.. moduleauthor:: Automation Mojo LLC

Public surface:

* :class:`JobEnvelope` — canonical envelope dataclass
  (:mod:`.schema`).
* :class:`SignedJobEnvelope`, :class:`DispatchRequest` — codec IO
  types (:mod:`.codec`).
* :func:`build`, :func:`sign`, :func:`parse`, :func:`verify` —
  codec facade (:mod:`.codec`).
* :func:`persist_signed_envelope`, :func:`get_envelope`,
  :func:`list_envelopes_for_run` — archive persistence
  (:mod:`.repository`).
* :func:`install_envelope_signer` + :class:`EnvelopeSignerBootstrapConfig`
  — service-startup hook (:mod:`.startup`).

Layer-5 downstream features (``5-job-dispatch``,
``5-dispatch-receipt``, ``5-run-state-machine``) consume this package
only through the codec + repository surfaces.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.jobs.envelope.codec import (
    DispatchRequest,
    SignedJobEnvelope,
    build,
    parse,
    sign,
    verify,
)
from automojo.pychestrate.webservice.jobs.envelope.errors import (
    EnvelopeClaimMissingError,
    EnvelopeSchemaVersionError,
    EnvelopeSerializationError,
    EnvelopeSigningKeyMissingError,
    JobEnvelopeError,
)
from automojo.pychestrate.webservice.jobs.envelope.models import (
    JobEnvelopeRecord,
)
from automojo.pychestrate.webservice.jobs.envelope.repository import (
    get_envelope,
    list_envelopes_for_run,
    persist_signed_envelope,
)
from automojo.pychestrate.webservice.jobs.envelope.schema import (
    ENVELOPE_SCHEMA_VERSION,
    JobDeadline,
    JobEnvelope,
    JobForwardingInfo,
    JobPipelineRef,
    JobRefs,
    JobResultsLocator,
    ScopedSecret,
    SUPPORTED_SCHEMA_VERSIONS,
)
from automojo.pychestrate.webservice.jobs.envelope.startup import (
    EnvelopeSignerBootstrapConfig,
    build_bootstrap_config_from_environment,
    install_envelope_signer,
    install_envelope_signer_from_environment,
)
