"""
.. module:: pods.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bus topics published by Layer-3 pod features.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class PodDefinitionEventTopics:
    """
        Topics owned by 3-pod-definitions.
    """
    DEFINITION_CREATED: str = "entity.pod.definition_created"
    DEFINITION_VALIDATION_FAILED: str = "entity.pod.validation_failed"


class PodLifecycleEventTopics:
    """
        Topics owned by 3-pod-lifecycle.
    """
    POD_STATE_CHANGED: str = "entity.pod.state_changed"


class StaticPodEventTopics:
    """
        Topics owned by 3-static-pods.
    """
    POD_REGISTERED: str = "entity.pod.registered"
    POD_DEREGISTERED: str = "entity.pod.deregistered"
    POD_REGISTERED_CLIENT_LOST: str = "entity.pod.registered_client_lost"
    POD_REGISTERED_CLIENT_RECOVERED: str = "entity.pod.registered_client_recovered"
    POD_REGISTRATION_REJECTED: str = "entity.pod.registration_rejected"


class DynamicPodEventTopics:
    """
        Topics owned by 3-dynamic-pods.
    """
    MATERIALIZATION_STARTED: str = "entity.pod.materialization_started"
    MATERIALIZATION_RENDER_OK: str = "entity.pod.materialization_render_ok"
    MATERIALIZATION_READY: str = "entity.pod.materialization_ready"
    MATERIALIZATION_FAILED: str = "entity.pod.materialization_failed"


class PodScopedConfigEventTopics:
    """
        Topics owned by 3-pod-scoped-config.
    """
    SCOPED_VARIABLE_SET: str = "entity.pod.scoped_variable_set"
    SCOPED_VARIABLE_DELETED: str = "entity.pod.scoped_variable_deleted"
    SCOPED_PURGED: str = "entity.pod.scoped_purged"
