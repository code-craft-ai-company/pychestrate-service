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


from typing import ClassVar, Dict, Tuple

from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension


class AuditEventTypeExtension(ResourceExtension):
    """
        Base class declaring a single audit kind + source topic.

        Implementations set:

        - ``kind``: canonical audit kind (e.g. ``audit.user.created``).
        - ``source_topic``: originating bus topic (e.g. ``entity.user.created``).
        - ``payload_schema``: JSON-schema dict validating the payload.
        - ``description``: free-form description.
        - ``captured_inline``: True when the producer writes the audit
          record itself (``audit_writer.capture_event`` inside its own
          transaction) and publishes the entity event only for other
          subscribers. The bus subscriber then does not capture the
          event again -- doing so wrote every secret event twice, the
          second copy without an actor.
        - ``actor_payload_keys``: payload keys, in order, that may name
          the acting principal. The first non-empty one wins; a UUID
          becomes the record's ``actor_user_id``, any other value
          (``extension:...``) its ``actor_service_identity``.
    """

    resource_extension_name: ClassVar[str] = "audit_event_type"
    kind: ClassVar[str] = ""
    source_topic: ClassVar[str] = ""
    payload_schema: ClassVar[Dict] = {}
    description: ClassVar[str] = ""
    captured_inline: ClassVar[bool] = False
    actor_payload_keys: ClassVar[Tuple[str, ...]] = ("actor_user_id",)
