"""
.. module:: ops.release
    :synopsis: 10-release-channels — signed release ledger + canary publish.

Public surface:

* :class:`ReleaseRow`, :class:`ChannelStateRow`,
  :class:`ReleaseStageEvent`, :class:`ConsumerOutcomeRow`,
  :class:`TrustedIssuerKey` — persistence rows.
* :class:`ReleaseComponent`, :class:`ReleaseChannel`,
  :class:`ReleaseStatus`, :class:`StageEventKind`,
  :class:`ConsumerOutcome` — enums.
* :class:`ReleaseAspects`, :class:`LogVerbosity`,
  :func:`build_default_release_aspects`.
* :func:`publish_release` + :class:`ReleaseRecord`,
  :func:`get_release`, :func:`list_releases`,
  :func:`get_current_manifest`.
* :class:`ReleaseChannelPolicyProtocol` factory contract +
  reference :class:`HashRingChannelPolicy`.
* :class:`ConsumerDescriptor`, :class:`EligibleConsumerSet`.
* :func:`resolve_policy`.
* :class:`SigningKey`, :func:`generate_signing_key`,
  :func:`load_signing_key`, :func:`set_active_signing_key`,
  :func:`get_active_signing_key`,
  :func:`reset_for_testing`,
  :func:`sign_manifest`,
  :func:`build_canonical_manifest`.
* :class:`ManifestVerificationResult`,
  :func:`verify_manifest`,
  :func:`register_trusted_issuer_key`.
* :class:`ReleaseEventTopics`.
* Errors: :class:`ReleaseError`,
  :class:`ReleaseSigningKeyUnavailableError`,
  :class:`ReleaseStageInProgressError`,
  :class:`ReleaseBakeNotMetError`,
  :class:`NoPriorReleaseError`,
  :class:`ReleaseNotActiveError`,
  :class:`ManifestVerificationError`,
  :class:`ReleaseConflictError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.ops.release.errors import (
    ManifestVerificationError,
    NoPriorReleaseError,
    ReleaseBakeNotMetError,
    ReleaseConflictError,
    ReleaseError,
    ReleaseNotActiveError,
    ReleaseSigningKeyUnavailableError,
    ReleaseStageInProgressError,
)
from automojo.pychestrate.webservice.ops.release.events import (
    ReleaseEventTopics,
)
from automojo.pychestrate.webservice.ops.release.factories.hash_ring_policy import (
    HashRingChannelPolicy,
)
from automojo.pychestrate.webservice.ops.release.factories.release_channel_policy import (
    ConsumerDescriptor,
    EligibleConsumerSet,
    ReleaseChannelPolicyProtocol,
)
from automojo.pychestrate.webservice.ops.release.manifest_signer import (
    SigningKey,
    generate_signing_key,
    get_active_signing_key,
    load_signing_key,
    reset_for_testing,
    set_active_signing_key,
    sign_manifest,
)
from automojo.pychestrate.webservice.ops.release.manifest_verifier import (
    ManifestVerificationResult,
    register_trusted_issuer_key,
    verify_manifest,
)
from automojo.pychestrate.webservice.ops.release.models import (
    ChannelStateRow,
    ConsumerOutcome,
    ConsumerOutcomeRow,
    ReleaseChannel,
    ReleaseComponent,
    ReleaseRow,
    ReleaseStageEvent,
    ReleaseStatus,
    StageEventKind,
    TrustedIssuerKey,
)
from automojo.pychestrate.webservice.ops.release.policy_router import (
    resolve_policy,
)
from automojo.pychestrate.webservice.ops.release.release_aspects import (
    LogVerbosity,
    ReleaseAspects,
    build_default_release_aspects,
)
from automojo.pychestrate.webservice.ops.release.release_service import (
    ReleaseRecord,
    build_canonical_manifest,
    get_current_manifest,
    get_release,
    list_releases,
    publish_release,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`HashRingChannelPolicy`
        reference under the ``release_channel_policy``
        factory protocol.
    """
    register_factory_implementation(implementation=HashRingChannelPolicy)
    return
