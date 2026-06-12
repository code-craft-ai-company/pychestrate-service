"""
.. module:: jobs.envelope
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-5 JobEnvelope — canonical, signed dispatch payload.

.. moduleauthor:: Code Craft AI LLC

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

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.jobs.envelope.codec import (
    DispatchRequest,
    SignedJobEnvelope,
    build,
    parse,
    sign,
    verify,
)
from ccai.pychestrate.webservice.jobs.envelope.errors import (
    EnvelopeClaimMissingError,
    EnvelopeSchemaVersionError,
    EnvelopeSerializationError,
    EnvelopeSigningKeyMissingError,
    JobEnvelopeError,
)
from ccai.pychestrate.webservice.jobs.envelope.models import (
    JobEnvelopeRecord,
)
from ccai.pychestrate.webservice.jobs.envelope.repository import (
    get_envelope,
    list_envelopes_for_run,
    persist_signed_envelope,
)
from ccai.pychestrate.webservice.jobs.envelope.schema import (
    DEFAULT_JOB_KIND,
    ENVELOPE_SCHEMA_VERSION,
    JOB_KIND_BUILD,
    JOB_KIND_PROVISION,
    JOB_KIND_TEST,
    JobDeadline,
    JobEnvelope,
    JobForwardingInfo,
    JobPipelineRef,
    JobRefs,
    JobResultsLocator,
    JobSourceRef,
    ScopedSecret,
    SOURCE_KIND_GIT,
    SUPPORTED_JOB_KINDS,
    SUPPORTED_SCHEMA_VERSIONS,
    SUPPORTED_SOURCE_KINDS,
)
from ccai.pychestrate.webservice.jobs.envelope.startup import (
    EnvelopeSignerBootstrapConfig,
    build_bootstrap_config_from_environment,
    install_envelope_signer,
    install_envelope_signer_from_environment,
)
