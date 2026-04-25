"""
.. module:: extensions.sandbox.authority
    :synopsis: CapabilityAuthority — process-singleton in-memory state.

The authority owns three frozen mappings:

* ``active`` — current ``ext_name → frozenset(capability)``.
* ``protocol_requirements`` — ``protocol_name → frozenset(capability)``.
* ``topic_requirements`` — ``topic → frozenset(capability)``.

The M1 ``authorize_*`` methods return True when the active set
is a superset of the requirement set; the M2 work hooks the
factory + hook-router gates that raise / drop on denial.

The closed vocabulary is the single source of truth — manifests
declaring an unknown capability raise
:class:`UnknownCapabilityError` at parse time so we never
end up tracking grants that no factory will ever check.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import os
import threading

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, Mapping, Optional, Tuple

from automojo.pychestrate.webservice.extensions.sandbox.errors import (
    UnknownCapabilityError,
)


class CapabilityVocabulary:
    """
        Closed vocabulary of capability strings. Any other
        string is rejected at manifest parse time.
    """
    READ_SECRETS: str = "read:secrets"
    WRITE_ARTIFACTS: str = "write:artifacts"
    DISPATCH_JOBS: str = "dispatch:jobs"
    NET_OUTBOUND: str = "net:outbound"
    PROCESS_SUBPROCESS: str = "process:subprocess"


CAPABILITY_VOCABULARY: FrozenSet[str] = frozenset({
    CapabilityVocabulary.READ_SECRETS,
    CapabilityVocabulary.WRITE_ARTIFACTS,
    CapabilityVocabulary.DISPATCH_JOBS,
    CapabilityVocabulary.NET_OUTBOUND,
    CapabilityVocabulary.PROCESS_SUBPROCESS,
})


class CapabilityGrantSource(str, enum.Enum):
    """
        How a grant entered the active set.
    """
    MANIFEST = "manifest"
    ADMIN = "admin"


@dataclass(frozen=True)
class ExtensionManifest:
    """
        Frozen-dataclass view of an extension's manifest. The
        full manifest format lands with E-extension-manifest;
        the M1 authority only consumes the name + declared
        capabilities.
    """
    ext_name: str
    declared_capabilities: FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class CapabilityAuthorityState:
    """
        Snapshot of the authority's current state surfaced for
        diagnostics + tests.
    """
    vocabulary: FrozenSet[str]
    active: Mapping[str, FrozenSet[str]]
    protocol_requirements: Mapping[str, FrozenSet[str]]
    topic_requirements: Mapping[str, FrozenSet[str]]


class CapabilityAuthority:
    """
        Process-singleton tracking the active capability grant
        set per extension. The M1 ``authorize_*`` helpers are
        pass-through subset checks — they never raise. The
        factory + hook router gates that bubble denials land in
        M2.
    """

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._vocabulary: FrozenSet[str] = CAPABILITY_VOCABULARY
        self._active: Dict[str, FrozenSet[str]] = {}
        self._protocol_requirements: Dict[str, FrozenSet[str]] = {}
        self._topic_requirements: Dict[str, FrozenSet[str]] = {}
        return

    @property
    def vocabulary(self) -> FrozenSet[str]:
        rtnval = self._vocabulary
        return rtnval

    def reload_from_manifests(
            self,
            *,
            manifests: Iterable[ExtensionManifest]
        ) -> None:
        """
            Replace the active set with the manifest-declared
            grants. The closed vocabulary is enforced — any
            unknown capability raises
            :class:`UnknownCapabilityError`.
        """
        new_active: Dict[str, FrozenSet[str]] = {}
        for manifest in manifests:
            self._validate_capability_set(
                ext_name=manifest.ext_name,
                capabilities=manifest.declared_capabilities,
            )
            new_active[manifest.ext_name] = frozenset(
                manifest.declared_capabilities,
            )
        with self._lock:
            self._active = new_active
        return

    def replace_active_for_extension(
            self,
            *,
            ext_name: str,
            capabilities: Iterable[str]
        ) -> FrozenSet[str]:
        """
            Atomically replace the active capability set for a
            single extension. Used by the persistence-layer
            reload path; the M1 grant / revoke helpers prefer
            :meth:`grant_capability_in_memory` /
            :meth:`revoke_capability_in_memory` for delta-style
            updates.
        """
        capabilities_set = frozenset(capabilities)
        self._validate_capability_set(
            ext_name=ext_name, capabilities=capabilities_set,
        )
        with self._lock:
            self._active[ext_name] = capabilities_set
        return capabilities_set

    def grant_capability_in_memory(
            self,
            *,
            ext_name: str,
            capability: str
        ) -> FrozenSet[str]:
        """
            Add a capability to the in-memory set. Returns the
            updated set.
        """
        self._validate_capability(capability=capability)
        with self._lock:
            current = self._active.get(ext_name, frozenset())
            new_set = frozenset(current | {capability})
            self._active[ext_name] = new_set
        return new_set

    def revoke_capability_in_memory(
            self,
            *,
            ext_name: str,
            capability: str
        ) -> FrozenSet[str]:
        """
            Remove a capability from the in-memory set. Returns
            the updated set.
        """
        self._validate_capability(capability=capability)
        with self._lock:
            current = self._active.get(ext_name, frozenset())
            new_set = frozenset(current - {capability})
            self._active[ext_name] = new_set
        return new_set

    def granted_for(self, *, ext_name: str) -> FrozenSet[str]:
        """
            Active capabilities for an extension. Returns an
            empty frozenset for a never-seen extension.
        """
        with self._lock:
            rtnval = self._active.get(ext_name, frozenset())
        return rtnval

    def declare_protocol_requirements(
            self,
            *,
            protocol_name: str,
            required: Iterable[str]
        ) -> None:
        """
            Record the capability set required to lookup or
            invoke a factory protocol. Called by the
            E-factory-protocols bootstrap once a protocol
            class is registered.
        """
        required_set = frozenset(required)
        self._validate_capability_set(
            ext_name=protocol_name, capabilities=required_set,
        )
        with self._lock:
            self._protocol_requirements[protocol_name] = required_set
        return

    def declare_topic_requirements(
            self,
            *,
            topic: str,
            required: Iterable[str]
        ) -> None:
        """
            Record the capability set required to deliver a
            topic to an extension hook. Called by the
            hook-router bootstrap.
        """
        required_set = frozenset(required)
        self._validate_capability_set(
            ext_name=topic, capabilities=required_set,
        )
        with self._lock:
            self._topic_requirements[topic] = required_set
        return

    def required_for_protocol(
            self,
            *,
            protocol_name: str
        ) -> FrozenSet[str]:
        with self._lock:
            rtnval = self._protocol_requirements.get(
                protocol_name, frozenset(),
            )
        return rtnval

    def required_for_topic(self, *, topic: str) -> FrozenSet[str]:
        with self._lock:
            rtnval = self._topic_requirements.get(topic, frozenset())
        return rtnval

    def authorize_factory_call(
            self,
            *,
            ext_name: str,
            protocol_name: str
        ) -> bool:
        """
            Pass-through subset check. M1 returns True for the
            zero-capability default — i.e. when the protocol
            declares no requirements. M2 raises
            :class:`PermissionError` on denial.
        """
        required = self.required_for_protocol(protocol_name=protocol_name)
        granted = self.granted_for(ext_name=ext_name)
        rtnval = required.issubset(granted)
        return rtnval

    def authorize_hook_delivery(
            self,
            *,
            ext_name: str,
            topic: str
        ) -> bool:
        """
            Pass-through subset check. M1 returns True for the
            zero-capability default. M2 drops the delivery on
            denial.
        """
        required = self.required_for_topic(topic=topic)
        granted = self.granted_for(ext_name=ext_name)
        rtnval = required.issubset(granted)
        return rtnval

    def snapshot_state(self) -> CapabilityAuthorityState:
        """
            Frozen-dataclass snapshot of the authority's
            current state.
        """
        with self._lock:
            active_snapshot = {
                ext: frozenset(caps) for ext, caps in self._active.items()
            }
            protocol_snapshot = {
                name: frozenset(caps)
                for name, caps in self._protocol_requirements.items()
            }
            topic_snapshot = {
                name: frozenset(caps)
                for name, caps in self._topic_requirements.items()
            }
        rtnval = CapabilityAuthorityState(
            vocabulary=self._vocabulary,
            active=active_snapshot,
            protocol_requirements=protocol_snapshot,
            topic_requirements=topic_snapshot,
        )
        return rtnval

    def reset(self) -> None:
        """
            Clear every in-memory mapping. Test-only.
        """
        with self._lock:
            self._active.clear()
            self._protocol_requirements.clear()
            self._topic_requirements.clear()
        return

    def _validate_capability(self, *, capability: str) -> None:
        if capability not in self._vocabulary:
            err_lines = ["Unknown capability."]
            err_lines.append("CAPABILITY: {!r}".format(capability))
            err_lines.append("VOCABULARY: {}".format(
                ", ".join(sorted(self._vocabulary)),
            ))
            err_msg = os.linesep.join(err_lines)
            raise UnknownCapabilityError(err_msg) from None
        return

    def _validate_capability_set(
            self,
            *,
            ext_name: str,
            capabilities: Iterable[str]
        ) -> None:
        for capability in capabilities:
            if capability not in self._vocabulary:
                err_lines = ["Manifest declared an unknown capability."]
                err_lines.append("EXT_NAME: {}".format(ext_name))
                err_lines.append("CAPABILITY: {!r}".format(capability))
                err_lines.append("VOCABULARY: {}".format(
                    ", ".join(sorted(self._vocabulary)),
                ))
                err_msg = os.linesep.join(err_lines)
                raise UnknownCapabilityError(err_msg) from None
        return


_AUTHORITY_LOCK = threading.RLock()
_AUTHORITY_INSTANCE: Optional[CapabilityAuthority] = None


def get_capability_authority() -> CapabilityAuthority:
    """
        Process-singleton accessor. The first caller creates
        the instance; subsequent callers see the same object.
    """
    global _AUTHORITY_INSTANCE
    with _AUTHORITY_LOCK:
        if _AUTHORITY_INSTANCE is None:
            _AUTHORITY_INSTANCE = CapabilityAuthority()
        rtnval = _AUTHORITY_INSTANCE
    return rtnval


def reset_authority_for_testing() -> None:
    """
        Drop the singleton + clear in-memory state. Tests call
        this to isolate from cross-test bleed.
    """
    global _AUTHORITY_INSTANCE
    with _AUTHORITY_LOCK:
        if _AUTHORITY_INSTANCE is not None:
            _AUTHORITY_INSTANCE.reset()
        _AUTHORITY_INSTANCE = None
    return
