"""
.. module:: audit
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 1-audit-log feature — INSERT-only canonical audit with fan-out.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    register_resource_extension,
)

from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension
from ccai.pychestrate.webservice.audit.extensions.project_events import (
    ProjectArchivedAuditEvents,
    ProjectCreatedAuditEvents,
    ProjectDeletedAuditEvents,
    ProjectMemberAddedAuditEvents,
    ProjectMemberRemovedAuditEvents,
    ProjectUnarchivedAuditEvents,
)
from ccai.pychestrate.webservice.audit.extensions.data_change_events import (
    DATA_CHANGE_AUDIT_EVENT_TYPES,
)
from ccai.pychestrate.webservice.audit.extensions.role_events import (
    ROLE_AUDIT_EVENT_TYPES,
    RoleBindingAuditEvents,
)
from ccai.pychestrate.webservice.audit.extensions.ip_allocation_events import (
    IpAllocationForceReleasedAuditEvents,
)
from ccai.pychestrate.webservice.audit.extensions.reservation_events import (
    ReservationOverriddenAuditEvents,
)
from ccai.pychestrate.webservice.audit.extensions.resource_events import RESOURCE_AUDIT_EVENT_TYPES
from ccai.pychestrate.webservice.audit.extensions.rpa_events import RPA_AUDIT_EVENT_TYPES
from ccai.pychestrate.webservice.audit.extensions.ui_profile_events import (
    UiProfileDeploymentChangedAuditEvents,
)
from ccai.pychestrate.webservice.audit.extensions.secret_events import (
    SecretAccessedAuditEvents,
    SecretCreatedAuditEvents,
    SecretDeletedAuditEvents,
    SecretUpdatedAuditEvents,
)
from ccai.pychestrate.webservice.audit.extensions.session_events import (
    SESSION_AUDIT_EVENT_TYPES,
)
from ccai.pychestrate.webservice.audit.extensions.user_events import (
    USER_AUDIT_EVENT_TYPES,
    UserLifecycleAuditEvents,
)
from ccai.pychestrate.webservice.audit.extensions.variable_events import (
    VariableSetAuditEvents,
    VariableUnsetAuditEvents,
)
from ccai.pychestrate.webservice.audit.factories.local_db_sink import LocalDatabaseAuditSink


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``audit_sink`` implementation and the minimal
        Phase-1 ``AuditEventTypeExtension`` packs.

        :returns: None.
    """
    register_factory_implementation(implementation=LocalDatabaseAuditSink)
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=ReservationOverriddenAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=IpAllocationForceReleasedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=UserLifecycleAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=RoleBindingAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=SecretAccessedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=SecretCreatedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=SecretUpdatedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=SecretDeletedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=ProjectCreatedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=ProjectArchivedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=ProjectUnarchivedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=ProjectDeletedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=ProjectMemberAddedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=ProjectMemberRemovedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=VariableSetAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=VariableUnsetAuditEvents
    )
    for rpa_event_type in RPA_AUDIT_EVENT_TYPES:
        register_resource_extension(
            base_class=AuditEventTypeExtension, extension=rpa_event_type
        )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=UiProfileDeploymentChangedAuditEvents
    )
    # Admin, identity and session activity, plus the web UI's own
    # stores through the data-change bridge (audit ADM-02).
    already_registered = (UserLifecycleAuditEvents, RoleBindingAuditEvents)
    for extra_event_type in (
            USER_AUDIT_EVENT_TYPES
            + ROLE_AUDIT_EVENT_TYPES
            + SESSION_AUDIT_EVENT_TYPES
            + RESOURCE_AUDIT_EVENT_TYPES
            + DATA_CHANGE_AUDIT_EVENT_TYPES):
        if extra_event_type in already_registered:
            continue
        register_resource_extension(
            base_class=AuditEventTypeExtension, extension=extra_event_type
        )
    return
