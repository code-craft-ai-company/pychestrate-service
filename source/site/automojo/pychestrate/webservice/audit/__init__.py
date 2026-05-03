"""
.. module:: audit
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 1-audit-log feature — INSERT-only canonical audit with fan-out.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    register_resource_extension,
)

from automojo.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension
from automojo.pychestrate.webservice.audit.extensions.flag_events import (
    FlagCreatedAuditEvents,
    FlagRemovedAuditEvents,
    FlagRetiredAuditEvents,
    FlagUpdatedAuditEvents,
)
from automojo.pychestrate.webservice.audit.extensions.project_events import (
    ProjectArchivedAuditEvents,
    ProjectCreatedAuditEvents,
    ProjectDeletedAuditEvents,
    ProjectMemberAddedAuditEvents,
    ProjectMemberRemovedAuditEvents,
    ProjectUnarchivedAuditEvents,
)
from automojo.pychestrate.webservice.audit.extensions.role_events import RoleBindingAuditEvents
from automojo.pychestrate.webservice.audit.extensions.secret_events import (
    SecretAccessedAuditEvents,
    SecretCreatedAuditEvents,
    SecretRotatedAuditEvents,
)
from automojo.pychestrate.webservice.audit.extensions.session_events import (
    LoginRejectedAuditEvents,
    MfaChallengeVerifiedAuditEvents,
    MfaEnrollmentAuditEvents,
    SessionClosedAuditEvents,
    SessionOpenedAuditEvents,
    SessionsRevokedAuditEvents,
)
from automojo.pychestrate.webservice.audit.extensions.unknown_events import (
    UnknownAuditKindAuditEvents,
)
from automojo.pychestrate.webservice.audit.extensions.user_events import UserLifecycleAuditEvents
from automojo.pychestrate.webservice.audit.extensions.variable_events import (
    VariableSetAuditEvents,
    VariableUnsetAuditEvents,
)
from automojo.pychestrate.webservice.audit.factories.json_file_sink import (
    JsonFileAuditSink,
)
from automojo.pychestrate.webservice.audit.factories.local_db_sink import LocalDatabaseAuditSink


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``audit_sink`` implementations and
        the M1 + M2 ``AuditEventTypeExtension`` packs. The
        ``audit.unknown`` fallback pack is always registered so
        the writer's catch-all path always has a target.

        :returns: None.
    """
    register_factory_implementation(implementation=LocalDatabaseAuditSink)
    register_factory_implementation(implementation=JsonFileAuditSink)
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
        base_class=AuditEventTypeExtension, extension=SecretRotatedAuditEvents
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
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=SessionOpenedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=SessionClosedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=SessionsRevokedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=LoginRejectedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=MfaEnrollmentAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=MfaChallengeVerifiedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=FlagCreatedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=FlagUpdatedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=FlagRetiredAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=FlagRemovedAuditEvents
    )
    register_resource_extension(
        base_class=AuditEventTypeExtension, extension=UnknownAuditKindAuditEvents
    )
    return
