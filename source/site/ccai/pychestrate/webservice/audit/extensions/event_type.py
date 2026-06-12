"""
.. module:: audit.extensions.event_type
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ResourceExtension base declaring an audit event kind.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar, Dict

from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension


class AuditEventTypeExtension(ResourceExtension):
    """
        Base class declaring a single audit kind + source topic.

        Implementations set:

        - ``kind``: canonical audit kind (e.g. ``audit.user.created``).
        - ``source_topic``: originating bus topic (e.g. ``entity.user.created``).
        - ``payload_schema``: JSON-schema dict validating the payload.
        - ``description``: free-form description.
    """

    resource_extension_name: ClassVar[str] = "audit_event_type"
    kind: ClassVar[str] = ""
    source_topic: ClassVar[str] = ""
    payload_schema: ClassVar[Dict] = {}
    description: ClassVar[str] = ""
