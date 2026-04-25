"""
.. module:: extensions.sandbox
    :synopsis: E-extension-sandbox — capability authority + grant ledger.

Public surface:

* :class:`ExtensionCapabilityGrant` — persistence row.
* :class:`CapabilityVocabulary`,
  :class:`ExtensionManifest`,
  :class:`CapabilityGrantSource`,
  :class:`CapabilityAuthorityState`,
  :class:`CapabilityGrantView` — IO shapes / value types.
* :class:`CapabilityAuthority` — process-singleton.
* :func:`get_capability_authority`,
  :func:`reset_authority_for_testing`,
  :func:`reload_authority_from_db`,
  :func:`grant_capability`, :func:`revoke_capability`,
  :func:`list_grants_for_extension`.
* :class:`SandboxEventTopics`.
* Errors: :class:`SandboxError`,
  :class:`UnknownCapabilityError`,
  :class:`UnknownExtensionError`.

The M1 surface populates the in-memory authority + persistence
ledger and exposes pass-through ``authorize_*`` helpers that
return True when the extension carries the required capability
set. The factory-call gate that raises :class:`PermissionError`
on denial and the hook-delivery gate that drops on denial land
in M2.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.sandbox.authority import (
    CAPABILITY_VOCABULARY,
    CapabilityAuthority,
    CapabilityAuthorityState,
    CapabilityGrantSource,
    CapabilityVocabulary,
    ExtensionManifest,
    get_capability_authority,
    reset_authority_for_testing,
)
from automojo.pychestrate.webservice.extensions.sandbox.errors import (
    SandboxError,
    UnknownCapabilityError,
    UnknownExtensionError,
)
from automojo.pychestrate.webservice.extensions.sandbox.events import (
    SandboxEventTopics,
)
from automojo.pychestrate.webservice.extensions.sandbox.models import (
    ExtensionCapabilityGrant,
)
from automojo.pychestrate.webservice.extensions.sandbox.service import (
    CapabilityGrantView,
    grant_capability,
    list_grants_for_extension,
    reload_authority_from_db,
    revoke_capability,
)
