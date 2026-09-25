"""
.. module:: configdocs.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Canonical configuration-document models.

.. moduleauthor:: Code Craft AI LLC

These dataclasses are the only shape the rest of Pychestrate ever
sees (Requirement 1.3). A format implementation's whole job is to
turn bytes on disk into one of them; downstream code never learns
whether those bytes were ``codecraftai`` YAML, a CMDB export, or
anything else.

Two consequences are deliberate:

* Every model is frozen. A document is a snapshot of what was on
  disk at load time, not a mutable working set.
* Every model round-trips through :meth:`to_mapping` (Requirement
  1.5), so a document can be diffed against a later load without the
  caller reaching for the original file.

:class:`DeviceAddresses` mirrors the semantics of landscaping's
``DeviceAddressSet`` (``codecraftai-landscaping/specs/device-address-set``)
rather than re-implementing them differently: ``resolve`` is total,
pure, and never raises, so a device resolved here and the same device
resolved inside landscaping agree on the answer.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ccai.pychestrate.webservice.configdocs.domains import ConfigDocumentDomain


#: Schema version of the canonical models themselves. Bumped when a
#: canonical dataclass changes shape incompatibly -- independent of
#: any on-disk format's own versioning.
CANONICAL_SCHEMA_VERSION: int = 1


class AddressPlane(str, enum.Enum):
    """
        The network planes a device may be reachable on.
    """
    PUBLIC = "public"
    PRIVATE = "private"
    OVERLAY = "overlay"


def _clean(value: Any) -> Optional[str]:
    """
        Trim a value to a non-empty string, or None.

        :param value: Any value.

        :returns: The trimmed string, or None when empty/absent.
    """
    if value is None:
        return None
    text = str(value).strip()
    if len(text) == 0:
        return None
    return text


@dataclass(frozen=True)
class DeviceAddresses:
    """
        A device's reachable addresses, one per plane.

        ``overlay`` is keyed by mesh-VPN provider name because a
        device can sit on more than one overlay at once; insertion
        order decides the answer when a caller asks for "the" overlay
        address without naming a provider.

        :param public: Address on the public plane, or None.
        :param private: Address on the private plane, or None.
        :param overlay: Mapping of provider name to address.
    """
    public: Optional[str] = None
    private: Optional[str] = None
    overlay: Mapping[str, str] = field(default_factory=dict)

    def plane_value(
            self,
            *,
            plane: Any,
            provider: Optional[str] = None
        ) -> Optional[str]:
        """
            The address on one plane, without fallback.

            Total and never raises: an unknown plane name yields None
            rather than an error, because callers resolve addresses on
            paths where an exception would be worse than an absence.

            :param plane: An :class:`AddressPlane` or its string value.
            :param provider: Overlay provider name. When None and the
                             plane is OVERLAY, the first provider in
                             insertion order wins (Requirement 1 of
                             landscaping's device-address-set spec).

            :returns: The address, or None.
        """
        try:
            resolved_plane = AddressPlane(str(getattr(plane, "value", plane)))
        except ValueError:
            return None

        if resolved_plane == AddressPlane.PUBLIC:
            return _clean(self.public)

        if resolved_plane == AddressPlane.PRIVATE:
            return _clean(self.private)

        if provider is not None:
            return _clean(self.overlay.get(provider, None))

        for _name, address in self.overlay.items():
            cleaned = _clean(address)
            if cleaned is not None:
                return cleaned

        return None

    def resolve(
            self,
            *,
            plane: Any,
            fallback_planes: Optional[Sequence[Any]] = None,
            provider: Optional[str] = None
        ) -> Optional[str]:
        """
            The address on ``plane``, falling back in order.

            Total, pure, and never raises (Requirement 2 of
            landscaping's device-address-set spec). The same
            ``(set, plane, fallback)`` triple always yields the same
            answer.

            :param plane: The preferred plane.
            :param fallback_planes: Planes to try, in order, when the
                                    preferred one is absent.
            :param provider: Overlay provider name, when relevant.

            :returns: The first address found, or None.
        """
        primary = self.plane_value(plane=plane, provider=provider)
        if primary is not None:
            return primary

        if fallback_planes is None:
            return None

        for candidate in fallback_planes:
            found = self.plane_value(plane=candidate, provider=provider)
            if found is not None:
                return found

        return None

    def is_empty(self) -> bool:
        """
            True when no plane carries an address.

            :returns: True when the set is empty.
        """
        if _clean(self.public) is not None:
            return False
        if _clean(self.private) is not None:
            return False
        for _name, address in self.overlay.items():
            if _clean(address) is not None:
                return False
        return True

    def to_mapping(self) -> Dict[str, Any]:
        """
            Render as a plain mapping. Absent planes are omitted
            rather than emitted as null, matching the emit contract in
            ``codecraftai-provisioning/specs/landscape-inventory-emit``.

            :returns: Dict of present planes.
        """
        rtnval: Dict[str, Any] = {}
        public = _clean(self.public)
        if public is not None:
            rtnval["public"] = public
        private = _clean(self.private)
        if private is not None:
            rtnval["private"] = private

        overlays = {}
        for name, address in self.overlay.items():
            cleaned = _clean(address)
            if cleaned is not None:
                overlays[name] = cleaned
        if len(overlays) > 0:
            rtnval["overlay"] = overlays

        return rtnval


@dataclass(frozen=True)
class ConfigDocument:
    """
        Fields every canonical document carries.

        :param schema_version: Canonical model version.
        :param source_path: Absolute path the document was read from.
                            Empty for a synthesized document.
        :param source_format: ``format_name`` of the implementation
                              that produced it.
        :param extra_attributes: Format-carried data the canonical
                                 model has no field for. Preserved
                                 rather than dropped (Requirement 1.4).
    """
    schema_version: int = CANONICAL_SCHEMA_VERSION
    source_path: str = ""
    source_format: str = ""
    extra_attributes: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def domain(cls) -> ConfigDocumentDomain:
        """
            The domain this document belongs to.

            :returns: The domain.
        """
        raise NotImplementedError("Subclasses must implement domain()")

    def _base_mapping(self) -> Dict[str, Any]:
        """
            The envelope fields shared by every document.

            :returns: Dict of the base fields.
        """
        rtnval = {
            "schema_version": self.schema_version,
            "source_path": self.source_path,
            "source_format": self.source_format,
            "domain": self.domain().value,
        }
        if len(self.extra_attributes) > 0:
            rtnval["extra_attributes"] = dict(self.extra_attributes)
        return rtnval

    def to_mapping(self) -> Dict[str, Any]:
        """
            Render as a plain mapping (Requirement 1.5).

            :returns: Dict of the document's fields.
        """
        raise NotImplementedError("Subclasses must implement to_mapping()")


# ---------------------------------------------------------------
# landscape
# ---------------------------------------------------------------

@dataclass(frozen=True)
class LandscapeDevice:
    """
        One machine in a landscape.

        :param identity: Canonical identity (Requirement 7.1), derived
                         from the landscaping identity model rather
                         than from a hostname/MAC hash.
        :param name: Operator-facing name.
        :param device_type: Landscaping ``deviceType``, e.g.
                            ``network/client-linux``.
        :param role: Declared role, e.g. ``taskerserver``.
        :param group: Grouping label, when the format carries one.
        :param addresses: Reachable addresses per plane.
        :param credential_refs: Names resolved against the credentials
                                domain. Never secret material.
        :param features: Format-declared feature flags for the device.
        :param skipped: True when the entry declared ``skip: true``.
                        Retained rather than dropped (Requirement 3.5)
                        so a later sync does not read the omission as
                        a removal.
        :param extra_attributes: Unmapped format data.
    """
    identity: str
    name: str
    device_type: str = ""
    role: Optional[str] = None
    group: Optional[str] = None
    addresses: DeviceAddresses = field(default_factory=DeviceAddresses)
    credential_refs: Tuple[str, ...] = field(default_factory=tuple)
    features: Mapping[str, Any] = field(default_factory=dict)
    skipped: bool = False
    extra_attributes: Mapping[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> Dict[str, Any]:
        """
            Render as a plain mapping.

            :returns: Dict of the device's fields.
        """
        rtnval: Dict[str, Any] = {
            "identity": self.identity,
            "name": self.name,
            "device_type": self.device_type,
            "skipped": self.skipped,
        }
        if self.role is not None:
            rtnval["role"] = self.role
        if self.group is not None:
            rtnval["group"] = self.group

        addresses = self.addresses.to_mapping()
        if len(addresses) > 0:
            rtnval["addresses"] = addresses
        if len(self.credential_refs) > 0:
            rtnval["credentials"] = list(self.credential_refs)
        if len(self.features) > 0:
            rtnval["features"] = dict(self.features)
        if len(self.extra_attributes) > 0:
            rtnval["extra_attributes"] = dict(self.extra_attributes)
        return rtnval


@dataclass(frozen=True)
class LandscapeService:
    """
        A managed service in a landscape (power controller, vSphere,
        DNS, and similar).

        :param identity: Canonical identity.
        :param name: Operator-facing name.
        :param service_type: Landscaping ``serviceType``.
        :param addresses: Reachable addresses per plane.
        :param credential_refs: Names resolved against the credentials
                                domain.
        :param skipped: True when the entry declared ``skip: true``.
        :param extra_attributes: Unmapped format data.
    """
    identity: str
    name: str
    service_type: str = ""
    addresses: DeviceAddresses = field(default_factory=DeviceAddresses)
    credential_refs: Tuple[str, ...] = field(default_factory=tuple)
    skipped: bool = False
    extra_attributes: Mapping[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> Dict[str, Any]:
        """
            Render as a plain mapping.

            :returns: Dict of the service's fields.
        """
        rtnval: Dict[str, Any] = {
            "identity": self.identity,
            "name": self.name,
            "service_type": self.service_type,
            "skipped": self.skipped,
        }
        addresses = self.addresses.to_mapping()
        if len(addresses) > 0:
            rtnval["addresses"] = addresses
        if len(self.credential_refs) > 0:
            rtnval["credentials"] = list(self.credential_refs)
        if len(self.extra_attributes) > 0:
            rtnval["extra_attributes"] = dict(self.extra_attributes)
        return rtnval


@dataclass(frozen=True)
class LandscapeDocument(ConfigDocument):
    """
        The machines, infrastructure, and services of one landscape.

        :param environment: The document's ``environment`` block.
        :param clients: Client devices.
        :param infrastructure: Infrastructure devices.
        :param services: Managed services.
        :param vpn: The ``vpn`` block, when the format carries one.
    """
    environment: Mapping[str, Any] = field(default_factory=dict)
    clients: Tuple[LandscapeDevice, ...] = field(default_factory=tuple)
    infrastructure: Tuple[LandscapeDevice, ...] = field(default_factory=tuple)
    services: Tuple[LandscapeService, ...] = field(default_factory=tuple)
    vpn: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def domain(cls) -> ConfigDocumentDomain:
        rtnval = ConfigDocumentDomain.LANDSCAPE
        return rtnval

    def all_devices(self) -> Tuple[LandscapeDevice, ...]:
        """
            Clients and infrastructure together.

            :returns: Tuple of every device entry.
        """
        rtnval = tuple(self.clients) + tuple(self.infrastructure)
        return rtnval

    def to_mapping(self) -> Dict[str, Any]:
        rtnval = self._base_mapping()
        rtnval["environment"] = dict(self.environment)
        rtnval["clients"] = [item.to_mapping() for item in self.clients]
        rtnval["infrastructure"] = [item.to_mapping() for item in self.infrastructure]
        rtnval["services"] = [item.to_mapping() for item in self.services]
        if len(self.vpn) > 0:
            rtnval["vpn"] = dict(self.vpn)
        return rtnval


# ---------------------------------------------------------------
# topology
# ---------------------------------------------------------------

@dataclass(frozen=True)
class TopologyMember:
    """
        One member slot of a topology.

        :param name: Slot name, unique within its topology.
        :param member_kind: Kind name reconciled against the
                            ``3-pod-definitions`` member-kind
                            extensions during projection.
        :param device_identity: Canonical identity of the landscape
                                device filling the slot, when the
                                topology binds one.
        :param attributes: Kind-specific attributes.
    """
    name: str
    member_kind: str
    device_identity: Optional[str] = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> Dict[str, Any]:
        """
            Render as a plain mapping.

            :returns: Dict of the member's fields.
        """
        rtnval: Dict[str, Any] = {
            "name": self.name,
            "member_kind": self.member_kind,
        }
        if self.device_identity is not None:
            rtnval["device_identity"] = self.device_identity
        if len(self.attributes) > 0:
            rtnval["attributes"] = dict(self.attributes)
        return rtnval


@dataclass(frozen=True)
class TopologyEntry:
    """
        One named topology -- the shape a pod takes.

        :param identity: Canonical identity.
        :param name: Operator-facing name.
        :param members: The member slots.
        :param tags: Free-form labels.
        :param extra_attributes: Unmapped format data.
    """
    identity: str
    name: str
    members: Tuple[TopologyMember, ...] = field(default_factory=tuple)
    tags: Tuple[str, ...] = field(default_factory=tuple)
    extra_attributes: Mapping[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> Dict[str, Any]:
        """
            Render as a plain mapping.

            :returns: Dict of the topology's fields.
        """
        rtnval: Dict[str, Any] = {
            "identity": self.identity,
            "name": self.name,
            "members": [item.to_mapping() for item in self.members],
        }
        if len(self.tags) > 0:
            rtnval["tags"] = list(self.tags)
        if len(self.extra_attributes) > 0:
            rtnval["extra_attributes"] = dict(self.extra_attributes)
        return rtnval


@dataclass(frozen=True)
class TopologyDocument(ConfigDocument):
    """
        Every topology a deployment declares.

        :param topologies: The declared topologies.
    """
    topologies: Tuple[TopologyEntry, ...] = field(default_factory=tuple)

    @classmethod
    def domain(cls) -> ConfigDocumentDomain:
        rtnval = ConfigDocumentDomain.TOPOLOGY
        return rtnval

    def to_mapping(self) -> Dict[str, Any]:
        rtnval = self._base_mapping()
        rtnval["topologies"] = [item.to_mapping() for item in self.topologies]
        return rtnval


# ---------------------------------------------------------------
# credentials
# ---------------------------------------------------------------

@dataclass(frozen=True)
class CredentialReference:
    """
        A pointer to credential material held elsewhere.

        This model has no field capable of holding a secret. That is
        the point: Requirement 6.1 makes the credentials document a
        set of *references* resolved through ``CredentialManager`` or
        the ``1-secrets-vault`` backend, so an inventory file is safe
        to commit.

        :param name: Reference name landscape entries cite.
        :param category: Credential category, e.g. ``ssh``, ``basic``.
        :param vault_key: Key resolved against the backing vault.
        :param identity: Login identity, when the category carries one.
                         A username is not secret material; a password
                         is, and has no field here.
        :param attributes: Non-secret, category-specific attributes.
    """
    name: str
    category: str = ""
    vault_key: str = ""
    identity: Optional[str] = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> Dict[str, Any]:
        """
            Render as a plain mapping.

            :returns: Dict of the reference's fields.
        """
        rtnval: Dict[str, Any] = {
            "name": self.name,
            "category": self.category,
            "vault_key": self.vault_key,
        }
        if self.identity is not None:
            rtnval["identity"] = self.identity
        if len(self.attributes) > 0:
            rtnval["attributes"] = dict(self.attributes)
        return rtnval


@dataclass(frozen=True)
class CredentialsDocument(ConfigDocument):
    """
        The credential references a deployment declares.

        :param credentials: The declared references.
    """
    credentials: Tuple[CredentialReference, ...] = field(default_factory=tuple)

    @classmethod
    def domain(cls) -> ConfigDocumentDomain:
        rtnval = ConfigDocumentDomain.CREDENTIALS
        return rtnval

    def names(self) -> Tuple[str, ...]:
        """
            Every declared reference name.

            :returns: Tuple of names.
        """
        rtnval = tuple([item.name for item in self.credentials])
        return rtnval

    def to_mapping(self) -> Dict[str, Any]:
        rtnval = self._base_mapping()
        rtnval["credentials"] = [item.to_mapping() for item in self.credentials]
        return rtnval


# ---------------------------------------------------------------
# resource_spec
# ---------------------------------------------------------------

@dataclass(frozen=True)
class ResourceSpecEntry:
    """
        One declared resource specification.

        :param identity: Canonical identity.
        :param name: Operator-facing name.
        :param kind: ``resource_kind`` name the entry registers under.
        :param attributes: Kind-specific attributes, validated by the
                           kind implementation during projection.
        :param tags: Free-form labels.
        :param extra_attributes: Unmapped format data.
    """
    identity: str
    name: str
    kind: str
    attributes: Mapping[str, Any] = field(default_factory=dict)
    tags: Tuple[str, ...] = field(default_factory=tuple)
    extra_attributes: Mapping[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> Dict[str, Any]:
        """
            Render as a plain mapping.

            :returns: Dict of the entry's fields.
        """
        rtnval: Dict[str, Any] = {
            "identity": self.identity,
            "name": self.name,
            "kind": self.kind,
            "attributes": dict(self.attributes),
        }
        if len(self.tags) > 0:
            rtnval["tags"] = list(self.tags)
        if len(self.extra_attributes) > 0:
            rtnval["extra_attributes"] = dict(self.extra_attributes)
        return rtnval


@dataclass(frozen=True)
class ResourceSpecDocument(ConfigDocument):
    """
        Every resource specification a deployment declares.

        :param specifications: The declared specifications.
    """
    specifications: Tuple[ResourceSpecEntry, ...] = field(default_factory=tuple)

    @classmethod
    def domain(cls) -> ConfigDocumentDomain:
        rtnval = ConfigDocumentDomain.RESOURCE_SPEC
        return rtnval

    def to_mapping(self) -> Dict[str, Any]:
        rtnval = self._base_mapping()
        rtnval["specifications"] = [item.to_mapping() for item in self.specifications]
        return rtnval


#: Canonical document type per domain. The loader uses this to build
#: the empty document for an absent file (Requirement 4.5).
DOCUMENT_TYPES: Dict[ConfigDocumentDomain, type] = {
    ConfigDocumentDomain.RESOURCE_SPEC: ResourceSpecDocument,
    ConfigDocumentDomain.LANDSCAPE: LandscapeDocument,
    ConfigDocumentDomain.TOPOLOGY: TopologyDocument,
    ConfigDocumentDomain.CREDENTIALS: CredentialsDocument,
}
