"""
.. module:: agents
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-3 agent specs (client-agent-protocol,
               client-capability-advertisement, client-inventory-ui,
               agent-upgrade-channel) bundled in a single package.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.agents.extensions.capability_kind import (
    CapabilityKindExtension,
    ConcurrencyCapability,
    PodMemberOwnershipCapability,
    ToolchainCapability,
)
from ccai.pychestrate.webservice.agents.factories.in_memory_transport import (
    InMemoryLoopbackTransport,
)
from ccai.pychestrate.webservice.agents.factories.object_store_artifact_source import (
    ObjectStoreArtifactSource,
)
from ccai.pychestrate.webservice.agents.factories.rollout_policy import (
    FixedSetRolloutPolicy,
)
from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    register_resource_extension,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree Layer-3 agent extensions:

        - ``client_transport`` — :class:`InMemoryLoopbackTransport`.
        - ``upgrade_artifact_source`` — :class:`ObjectStoreArtifactSource`.
        - ``rollout_policy`` — :class:`FixedSetRolloutPolicy`.
        - ``CapabilityKindExtension`` — Toolchain / PodMemberOwnership / Concurrency.

        :returns: None.
    """
    register_factory_implementation(implementation=InMemoryLoopbackTransport)
    register_factory_implementation(implementation=ObjectStoreArtifactSource)
    register_factory_implementation(implementation=FixedSetRolloutPolicy)
    register_resource_extension(base_class=CapabilityKindExtension, extension=ToolchainCapability)
    register_resource_extension(base_class=CapabilityKindExtension, extension=PodMemberOwnershipCapability)
    register_resource_extension(base_class=CapabilityKindExtension, extension=ConcurrencyCapability)
    return
