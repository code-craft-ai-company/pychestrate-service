"""
.. module:: test_p50a_config_formats_m1
    :synopsis: Tests for P50a — 0-config-formats M1.

.. moduleauthor:: Code Craft AI LLC

M1 lands the protocol, the canonical models, and the loader. The
in-tree ``codecraftai`` formats arrive in M2, so every test here
drives the pipeline through a JSON-backed stub format -- which is
also the point: if the loader needed a real format to be exercised,
the format seam would not be doing its job.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import itertools
import json
import logging
import os
import tempfile

from typing import Any, Tuple

from ccai import testbase

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.configdocs import (
    ConfigDocumentDomain,
    ConfigDocumentDomainBleedError,
    ConfigDocumentFormatProtocol,
    ConfigDocumentParseError,
    CredentialReference,
    CredentialsDocument,
    DeviceAddresses,
    DiagnosticCodes,
    LandscapeDevice,
    LandscapeDocument,
    ResourceSpecDocument,
    TopologyDocument,
    build_report,
    load_all_documents,
    load_document,
    register_config_document_format,
    resolve_format_implementation,
)
from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)


# ---------------------------------------------------------------
# Stub formats
# ---------------------------------------------------------------

class _JsonFormatBase(ConfigDocumentFormatProtocol):
    """
        A JSON-backed stub. Real formats land in M2; this one exists
        to exercise the seam.
    """

    PRECEDENCE: int = 1000

    @classmethod
    def format_name(cls) -> str:
        return "codecraftai"

    @classmethod
    def file_basenames(cls) -> Tuple[str, ...]:
        return ("{}.json".format(cls.STEM),)

    @classmethod
    def probe_top_level_keys(cls, *, path: str, text: str) -> Tuple[str, ...]:
        payload = json.loads(text)
        return tuple(sorted(payload.keys()))

    @classmethod
    def validate(cls, *, document: Any):
        return build_report(diagnostics=None)

    @classmethod
    def _load(cls, *, path: str, text: str) -> Any:
        try:
            rtnval = json.loads(text)
        except ValueError as verr:
            raise ConfigDocumentParseError(
                domain=cls.document_domain(),
                format_name=cls.format_name(),
                source_path=path,
                message=str(verr),
            ) from None
        return rtnval


class StubLandscapeFormat(_JsonFormatBase):
    """
        Stub reader for the landscape domain.
    """

    STEM: str = "landscape"

    @classmethod
    def document_domain(cls) -> str:
        return ConfigDocumentDomain.LANDSCAPE.value

    @classmethod
    def claimed_top_level_keys(cls) -> Tuple[str, ...]:
        return ("environment", "apod", "clients", "infrastructure", "services", "vpn")

    @classmethod
    def parse(cls, *, path: str, text: str) -> LandscapeDocument:
        payload = cls._load(path=path, text=text)

        devices = []
        for entry in payload.get("clients", []):
            devices.append(
                LandscapeDevice(
                    identity=entry["identity"],
                    name=entry.get("name", entry["identity"]),
                    device_type=entry.get("deviceType", ""),
                    role=entry.get("role", None),
                    addresses=DeviceAddresses(
                        private=entry.get("host", None),
                    ),
                    credential_refs=tuple(entry.get("credentials", [])),
                    skipped=bool(entry.get("skip", False)),
                    extra_attributes=entry.get("extra", {}),
                ),
            )

        rtnval = LandscapeDocument(
            source_path=path,
            source_format=cls.format_name(),
            environment=payload.get("environment", {}),
            clients=tuple(devices),
            extra_attributes=payload.get("extra", {}),
        )
        return rtnval


class StubCredentialsFormat(_JsonFormatBase):
    """
        Stub reader for the credentials domain.
    """

    STEM: str = "credentials"

    @classmethod
    def document_domain(cls) -> str:
        return ConfigDocumentDomain.CREDENTIALS.value

    @classmethod
    def claimed_top_level_keys(cls) -> Tuple[str, ...]:
        return ("credentials",)

    @classmethod
    def parse(cls, *, path: str, text: str) -> CredentialsDocument:
        payload = cls._load(path=path, text=text)
        refs = []
        for entry in payload.get("credentials", []):
            refs.append(
                CredentialReference(
                    name=entry["name"],
                    category=entry.get("category", ""),
                    vault_key=entry.get("vault_key", ""),
                ),
            )
        rtnval = CredentialsDocument(
            source_path=path,
            source_format=cls.format_name(),
            credentials=tuple(refs),
        )
        return rtnval


class StubTopologyFormat(_JsonFormatBase):
    """
        Stub reader for the topology domain.
    """

    STEM: str = "topology"

    @classmethod
    def document_domain(cls) -> str:
        return ConfigDocumentDomain.TOPOLOGY.value

    @classmethod
    def claimed_top_level_keys(cls) -> Tuple[str, ...]:
        return ("topologies",)

    @classmethod
    def parse(cls, *, path: str, text: str) -> TopologyDocument:
        cls._load(path=path, text=text)
        rtnval = TopologyDocument(source_path=path, source_format=cls.format_name())
        return rtnval


class StubResourceSpecFormat(_JsonFormatBase):
    """
        Stub reader for the resource-specification domain.
    """

    STEM: str = "resource-specs"

    @classmethod
    def document_domain(cls) -> str:
        return ConfigDocumentDomain.RESOURCE_SPEC.value

    @classmethod
    def claimed_top_level_keys(cls) -> Tuple[str, ...]:
        return ("specifications",)

    @classmethod
    def parse(cls, *, path: str, text: str) -> ResourceSpecDocument:
        cls._load(path=path, text=text)
        rtnval = ResourceSpecDocument(source_path=path, source_format=cls.format_name())
        return rtnval


class EnterpriseLandscapeFormat(StubLandscapeFormat):
    """
        A second landscape reader at enterprise precedence, selected
        by name rather than by displacing the default.
    """

    PRECEDENCE: int = 100

    @classmethod
    def format_name(cls) -> str:
        return "acme-cmdb"

    @classmethod
    def file_basenames(cls) -> Tuple[str, ...]:
        return ("landscape.acme",)


class BadDomainFormat(StubLandscapeFormat):
    """
        Declares a domain that does not exist.
    """

    @classmethod
    def document_domain(cls) -> str:
        return "machines"


class EmptyNameFormat(StubLandscapeFormat):
    """
        Declares an empty format name.
    """

    @classmethod
    def format_name(cls) -> str:
        return ""


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def _prepare_runtime() -> None:
    """
        Reset the registry and register the stub formats for all four
        domains.
    """
    reset_registry_for_testing()
    register_config_document_format(implementation=StubLandscapeFormat)
    register_config_document_format(implementation=StubCredentialsFormat)
    register_config_document_format(implementation=StubTopologyFormat)
    register_config_document_format(implementation=StubResourceSpecFormat)
    return


def _write(*, directory: str, name: str, payload: Any) -> str:
    """
        Write a JSON document into ``directory``.

        :returns: The absolute path written.
    """
    path = os.path.join(directory, name)
    parent = os.path.dirname(path)
    if os.path.isdir(parent) is not True:
        os.makedirs(parent)
    with open(path, "w", encoding="utf-8") as handle:
        if isinstance(payload, str) is True:
            handle.write(payload)
        else:
            handle.write(json.dumps(payload))
    return path


def _device(*, identity: str, host: str = "10.0.0.1") -> dict:
    """
        A minimal client entry for the stub landscape format.
    """
    rtnval = {"identity": identity, "name": identity, "host": host}
    return rtnval


# ---------------------------------------------------------------
# Canonical model — DeviceAddresses (Requirement 1, 3.3)
# ---------------------------------------------------------------

def test_address_resolution_is_total_across_every_plane_combination():
    """
    **Feature: 0-config-formats (M1)**
    **Property: resolve() is total over every present/absent plane
    combination -- it returns the requested plane when present, walks
    fallbacks in order otherwise, and never raises.**
    """
    planes = ["public", "private", "overlay"]

    for present in itertools.chain.from_iterable(
            itertools.combinations(planes, count) for count in range(0, 4)):
        addresses = DeviceAddresses(
            public="1.1.1.1" if "public" in present else None,
            private="10.0.0.1" if "private" in present else None,
            overlay={"tailscale": "100.64.0.1"} if "overlay" in present else {},
        )
        for requested in planes:
            for fallback in itertools.permutations(planes, 2):
                answer = addresses.resolve(
                    plane=requested, fallback_planes=list(fallback),
                )
                expected = None
                for candidate in [requested] + list(fallback):
                    if candidate in present:
                        expected = addresses.plane_value(plane=candidate)
                        break
                testbase.assert_equal(answer, expected)
    return


def test_address_resolution_tolerates_unknown_plane():
    """
    **Feature: 0-config-formats (M1)**
    **Property: an unknown plane name yields None rather than raising,
    because callers resolve addresses where an exception would be
    worse than an absence.**
    """
    addresses = DeviceAddresses(private="10.0.0.1")
    testbase.assert_equal(addresses.resolve(plane="quantum"), None)
    testbase.assert_equal(
        addresses.resolve(plane="quantum", fallback_planes=["private"]),
        "10.0.0.1",
    )
    return


def test_overlay_without_provider_takes_first_in_insertion_order():
    """
    **Feature: 0-config-formats (M1)**
    **Property: overlay() with no provider returns the first provider
    in insertion order, matching landscaping's device-address-set
    Requirement 1.5.**
    """
    addresses = DeviceAddresses(
        overlay={"tailscale": "100.64.0.1", "zerotier": "10.147.0.1"},
    )
    testbase.assert_equal(addresses.resolve(plane="overlay"), "100.64.0.1")
    testbase.assert_equal(
        addresses.resolve(plane="overlay", provider="zerotier"), "10.147.0.1",
    )
    return


def test_absent_planes_are_omitted_not_nulled():
    """
    **Feature: 0-config-formats (M1)**
    **Property: to_mapping omits absent planes rather than emitting
    null, matching the provisioning emit contract.**
    """
    mapping = DeviceAddresses(private="10.0.0.1").to_mapping()
    testbase.assert_equal("public" in mapping, False)
    testbase.assert_equal("overlay" in mapping, False)
    testbase.assert_equal(mapping["private"], "10.0.0.1")
    return


def test_documents_round_trip_to_mapping():
    """
    **Feature: 0-config-formats (M1)**
    **Property: every canonical document renders to a plain mapping
    carrying its domain and envelope (Requirement 1.5).**
    """
    documents = [
        LandscapeDocument(source_format="codecraftai"),
        TopologyDocument(source_format="codecraftai"),
        CredentialsDocument(source_format="codecraftai"),
        ResourceSpecDocument(source_format="codecraftai"),
    ]
    for document in documents:
        mapping = document.to_mapping()
        testbase.assert_equal(mapping["domain"], document.domain().value)
        testbase.assert_equal(mapping["source_format"], "codecraftai")
        testbase.assert_equal(mapping["schema_version"], 1)
    return


# ---------------------------------------------------------------
# Registration guards (Requirement 2.4, 2.5)
# ---------------------------------------------------------------

def test_unknown_domain_registration_is_rejected():
    """
    **Feature: 0-config-formats (M1)**
    **Property: an implementation naming an undeclared domain is
    rejected at registration, since nothing could ever resolve it.**
    """
    reset_registry_for_testing()
    try:
        register_config_document_format(implementation=BadDomainFormat)
        testbase.assert_equal("no error raised", "ConfigurationError")
    except ConfigurationError as cerr:
        testbase.assert_equal("machines" in str(cerr), True)
        testbase.assert_equal("landscape" in str(cerr), True)
    return


def test_empty_format_name_registration_is_rejected():
    """
    **Feature: 0-config-formats (M1)**
    **Property: an implementation with an empty format name is
    rejected -- it could never be selected.**
    """
    reset_registry_for_testing()
    try:
        register_config_document_format(implementation=EmptyNameFormat)
        testbase.assert_equal("no error raised", "ConfigurationError")
    except ConfigurationError as cerr:
        testbase.assert_equal("empty format name" in str(cerr), True)
    return


def test_enterprise_format_overrides_one_domain_only():
    """
    **Feature: 0-config-formats (M1)**
    **Property: selecting a non-default format for one domain leaves
    the other three on codecraftai (Requirement 5.3).**
    """
    _prepare_runtime()
    register_config_document_format(implementation=EnterpriseLandscapeFormat)

    chosen = resolve_format_implementation(
        domain=ConfigDocumentDomain.LANDSCAPE, format_name="acme-cmdb",
    )
    testbase.assert_equal(chosen is EnterpriseLandscapeFormat, True)

    default = resolve_format_implementation(
        domain=ConfigDocumentDomain.LANDSCAPE, format_name=None,
    )
    testbase.assert_equal(default is StubLandscapeFormat, True)

    for domain, expected in (
            (ConfigDocumentDomain.CREDENTIALS, StubCredentialsFormat),
            (ConfigDocumentDomain.TOPOLOGY, StubTopologyFormat),
            (ConfigDocumentDomain.RESOURCE_SPEC, StubResourceSpecFormat)):
        resolved = resolve_format_implementation(domain=domain, format_name=None)
        testbase.assert_equal(resolved is expected, True)
    return


def test_unknown_format_name_lists_registered_and_does_not_fall_back():
    """
    **Feature: 0-config-formats (M1)**
    **Property: a configured format naming no implementation fails
    loudly listing what is registered, rather than silently reading
    the operator's files with the default reader (Requirement 5.2).**
    """
    _prepare_runtime()
    try:
        resolve_format_implementation(
            domain=ConfigDocumentDomain.LANDSCAPE, format_name="nope",
        )
        testbase.assert_equal("no error raised", "ConfigurationError")
    except ConfigurationError as cerr:
        message = str(cerr)
        testbase.assert_equal("nope" in message, True)
        testbase.assert_equal("codecraftai" in message, True)
    return


# ---------------------------------------------------------------
# Locating documents (Requirement 4)
# ---------------------------------------------------------------

def test_absent_document_is_not_configured_and_does_not_fail():
    """
    **Feature: 0-config-formats (M1)**
    **Property: an absent document leaves the domain unconfigured with
    an empty canonical document rather than failing startup
    (Requirement 4.5).**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = load_document(
            domain=ConfigDocumentDomain.LANDSCAPE,
            config_dir=tmpdir,
            environ={},
        )
    testbase.assert_equal(outcome.configured, False)
    testbase.assert_equal(outcome.ok, True)
    testbase.assert_equal(len(outcome.source_paths), 0)
    testbase.assert_equal(isinstance(outcome.document, LandscapeDocument), True)
    testbase.assert_equal(len(outcome.document.clients), 0)
    return


def test_single_file_loads_from_config_dir():
    """
    **Feature: 0-config-formats (M1)**
    **Property: the domain's stem plus the format's extension is found
    under <presence_dir>/config.**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        _write(
            directory=tmpdir, name="landscape.json",
            payload={"environment": {"label": "lab"},
                     "clients": [_device(identity="casey-01")]},
        )
        outcome = load_document(
            domain=ConfigDocumentDomain.LANDSCAPE, config_dir=tmpdir, environ={},
        )
    testbase.assert_equal(outcome.configured, True)
    testbase.assert_equal(outcome.ok, True)
    testbase.assert_equal(len(outcome.document.clients), 1)
    testbase.assert_equal(outcome.document.clients[0].identity, "casey-01")
    testbase.assert_equal(outcome.document.environment["label"], "lab")
    return


def test_environment_override_path_wins():
    """
    **Feature: 0-config-formats (M1)**
    **Property: PYCHESTRATE_CONFIG_<DOMAIN>_PATH takes precedence over
    the default location (Requirement 4.7).**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        _write(
            directory=tmpdir, name="landscape.json",
            payload={"clients": [_device(identity="default-location")]},
        )
        elsewhere = _write(
            directory=tmpdir, name="somewhere-else.json",
            payload={"clients": [_device(identity="override-location")]},
        )
        outcome = load_document(
            domain=ConfigDocumentDomain.LANDSCAPE,
            config_dir=tmpdir,
            environ={"PYCHESTRATE_CONFIG_LANDSCAPE_PATH": elsewhere},
        )
    testbase.assert_equal(outcome.document.clients[0].identity, "override-location")
    return


def test_environment_override_naming_nothing_fails():
    """
    **Feature: 0-config-formats (M1)**
    **Property: an override pointing at a missing path is an operator
    error worth surfacing, unlike an absent default-location file.**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            load_document(
                domain=ConfigDocumentDomain.LANDSCAPE,
                config_dir=tmpdir,
                environ={
                    "PYCHESTRATE_CONFIG_LANDSCAPE_PATH":
                        os.path.join(tmpdir, "missing.json"),
                },
            )
            testbase.assert_equal("no error raised", "ConfigurationError")
        except ConfigurationError as cerr:
            testbase.assert_equal("does not exist" in str(cerr), True)
    return


def test_directory_form_concatenates_in_lexical_order():
    """
    **Feature: 0-config-formats (M1)**
    **Property: a <stem>.d directory loads every matching file in
    lexical order and concatenates their entries (Requirement 4.6).**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        _write(
            directory=os.path.join(tmpdir, "landscape.d"), name="20-west.json",
            payload={"clients": [_device(identity="west-01")]},
        )
        _write(
            directory=os.path.join(tmpdir, "landscape.d"), name="10-east.json",
            payload={"clients": [_device(identity="east-01")]},
        )
        _write(
            directory=os.path.join(tmpdir, "landscape.d"), name="notes.txt",
            payload="ignored — wrong extension",
        )
        outcome = load_document(
            domain=ConfigDocumentDomain.LANDSCAPE, config_dir=tmpdir, environ={},
        )

    testbase.assert_equal(len(outcome.source_paths), 2)
    testbase.assert_equal(outcome.ok, True)
    identities = [item.identity for item in outcome.document.clients]
    testbase.assert_equal(identities, ["east-01", "west-01"])
    return


def test_directory_form_rejects_repeated_identity():
    """
    **Feature: 0-config-formats (M1)**
    **Property: a repeated entry identity across files is an error,
    not an override -- no file may silently redefine a machine another
    declared.**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        _write(
            directory=os.path.join(tmpdir, "landscape.d"), name="a.json",
            payload={"clients": [_device(identity="casey-01", host="10.0.0.1")]},
        )
        _write(
            directory=os.path.join(tmpdir, "landscape.d"), name="b.json",
            payload={"clients": [_device(identity="casey-01", host="10.0.0.9")]},
        )
        outcome = load_document(
            domain=ConfigDocumentDomain.LANDSCAPE, config_dir=tmpdir, environ={},
        )

    testbase.assert_equal(outcome.ok, False)
    codes = [item.code for item in outcome.report.errors]
    testbase.assert_equal(DiagnosticCodes.DUPLICATE_ACROSS_FILES in codes, True)
    # The first declaration survives; the duplicate is dropped.
    testbase.assert_equal(len(outcome.document.clients), 1)
    testbase.assert_equal(
        outcome.document.clients[0].addresses.private, "10.0.0.1",
    )
    return


# ---------------------------------------------------------------
# Domain bleed (Requirement 4.3)
# ---------------------------------------------------------------

def test_domain_bleed_is_rejected():
    """
    **Feature: 0-config-formats (M1)**
    **Property: a landscape file carrying a credentials block is
    rejected rather than parsed -- the path by which an inline secret
    would otherwise reach a version control system.**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        _write(
            directory=tmpdir, name="landscape.json",
            payload={
                "clients": [_device(identity="casey-01")],
                "credentials": [{"name": "pi-cluster"}],
            },
        )
        outcome = load_document(
            domain=ConfigDocumentDomain.LANDSCAPE, config_dir=tmpdir, environ={},
        )

    testbase.assert_equal(outcome.ok, False)
    errors = outcome.report.errors
    testbase.assert_equal(errors[0].code, DiagnosticCodes.DOMAIN_BLEED)
    testbase.assert_equal("credentials" in errors[0].message, True)
    # The offending file is not parsed at all.
    testbase.assert_equal(len(outcome.document.clients), 0)
    return


def test_domain_bleed_raises_in_strict_mode():
    """
    **Feature: 0-config-formats (M1)**
    **Property: strict mode raises ConfigDocumentDomainBleedError for
    callers with nothing to accumulate across.**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        _write(
            directory=tmpdir, name="landscape.json",
            payload={"clients": [], "credentials": [{"name": "pi-cluster"}]},
        )
        try:
            load_document(
                domain=ConfigDocumentDomain.LANDSCAPE,
                config_dir=tmpdir, environ={}, strict=True,
            )
            testbase.assert_equal("no error raised", "DomainBleedError")
        except ConfigDocumentDomainBleedError as berr:
            testbase.assert_equal("credentials" in str(berr), True)
    return


def test_own_claimed_keys_are_not_bleed():
    """
    **Feature: 0-config-formats (M1)**
    **Property: a domain's own claimed keys never trip the bleed
    check, even when another domain's format is registered.**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        _write(
            directory=tmpdir, name="landscape.json",
            payload={
                "environment": {"label": "lab"},
                "apod": {},
                "clients": [_device(identity="casey-01")],
                "infrastructure": [],
                "services": [],
                "vpn": {},
            },
        )
        outcome = load_document(
            domain=ConfigDocumentDomain.LANDSCAPE, config_dir=tmpdir, environ={},
        )
    testbase.assert_equal(outcome.ok, True)
    return


# ---------------------------------------------------------------
# Parse failure (Requirement 2.6)
# ---------------------------------------------------------------

def test_parse_failure_becomes_a_diagnostic_without_falling_back():
    """
    **Feature: 0-config-formats (M1)**
    **Property: a malformed document produces a parse_failed
    diagnostic; the loader never retries with a different format.**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        _write(directory=tmpdir, name="landscape.json", payload="{ not json")
        outcome = load_document(
            domain=ConfigDocumentDomain.LANDSCAPE, config_dir=tmpdir, environ={},
        )

    testbase.assert_equal(outcome.ok, False)
    testbase.assert_equal(outcome.configured, True)
    testbase.assert_equal(outcome.report.errors[0].code, DiagnosticCodes.PARSE_FAILED)
    return


def test_parse_failure_raises_in_strict_mode():
    """
    **Feature: 0-config-formats (M1)**
    **Property: strict mode surfaces ConfigDocumentParseError with the
    domain, format, and path.**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        _write(directory=tmpdir, name="landscape.json", payload="{ not json")
        try:
            load_document(
                domain=ConfigDocumentDomain.LANDSCAPE,
                config_dir=tmpdir, environ={}, strict=True,
            )
            testbase.assert_equal("no error raised", "ParseError")
        except ConfigDocumentParseError as perr:
            testbase.assert_equal(perr.domain, "landscape")
            testbase.assert_equal(perr.format_name, "codecraftai")
    return


# ---------------------------------------------------------------
# Accumulation across domains (Requirement 8.2)
# ---------------------------------------------------------------

def test_load_all_accumulates_every_domain_before_returning():
    """
    **Feature: 0-config-formats (M1)**
    **Property: load_all_documents reports problems in several domains
    at once rather than stopping at the first, so an operator fixes
    their documents in one pass.**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        _write(directory=tmpdir, name="landscape.json", payload="{ not json")
        _write(directory=tmpdir, name="credentials.json", payload="also not json")
        _write(
            directory=tmpdir, name="topology.json", payload={"topologies": []},
        )

        outcomes = load_all_documents(config_dir=tmpdir, environ={})

    testbase.assert_equal(len(outcomes), 4)
    testbase.assert_equal(outcomes[ConfigDocumentDomain.LANDSCAPE].ok, False)
    testbase.assert_equal(outcomes[ConfigDocumentDomain.CREDENTIALS].ok, False)
    testbase.assert_equal(outcomes[ConfigDocumentDomain.TOPOLOGY].ok, True)
    testbase.assert_equal(
        outcomes[ConfigDocumentDomain.RESOURCE_SPEC].configured, False,
    )
    return


def test_extra_attributes_are_preserved_not_dropped():
    """
    **Feature: 0-config-formats (M1)**
    **Property: format data the canonical model has no field for is
    preserved under extra_attributes (Requirement 1.4).**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        _write(
            directory=tmpdir, name="landscape.json",
            payload={
                "clients": [{
                    "identity": "casey-01", "name": "casey-01",
                    "host": "10.0.0.1",
                    "extra": {"rack": "B7", "asset_tag": "AM-4411"},
                }],
                "extra": {"authored_by": "lab-team"},
            },
        )
        outcome = load_document(
            domain=ConfigDocumentDomain.LANDSCAPE, config_dir=tmpdir, environ={},
        )

    device = outcome.document.clients[0]
    testbase.assert_equal(device.extra_attributes["rack"], "B7")
    testbase.assert_equal(outcome.document.extra_attributes["authored_by"], "lab-team")
    testbase.assert_equal(
        device.to_mapping()["extra_attributes"]["asset_tag"], "AM-4411",
    )
    return


def test_skipped_devices_are_retained_not_dropped():
    """
    **Feature: 0-config-formats (M1)**
    **Property: skip: true keeps the entry marked skipped so a later
    inventory sync does not read the omission as a removal
    (Requirement 3.5).**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        entry = _device(identity="casey-09")
        entry["skip"] = True
        _write(
            directory=tmpdir, name="landscape.json", payload={"clients": [entry]},
        )
        outcome = load_document(
            domain=ConfigDocumentDomain.LANDSCAPE, config_dir=tmpdir, environ={},
        )

    testbase.assert_equal(len(outcome.document.clients), 1)
    testbase.assert_equal(outcome.document.clients[0].skipped, True)
    return


def test_outcome_renders_provenance_for_the_admin_surface():
    """
    **Feature: 0-config-formats (M1)**
    **Property: the outcome carries the selected format, resolving
    class, source paths, and load time (Requirement 5.4).**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        _write(directory=tmpdir, name="landscape.json", payload={"clients": []})
        outcome = load_document(
            domain=ConfigDocumentDomain.LANDSCAPE, config_dir=tmpdir, environ={},
        )

    mapping = outcome.to_mapping()
    testbase.assert_equal(mapping["domain"], "landscape")
    testbase.assert_equal(mapping["format"], "codecraftai")
    testbase.assert_equal("StubLandscapeFormat" in mapping["implementation"], True)
    testbase.assert_equal(len(mapping["source_paths"]), 1)
    testbase.assert_equal(mapping["configured"], True)
    testbase.assert_equal(mapping["report"]["ok"], True)
    return


class ShadowingLandscapeFormat(StubLandscapeFormat):
    """
        Claims the same (domain, format_name) pair as the shipped
        default, at enterprise precedence.
    """

    PRECEDENCE: int = 100


def test_shadowing_the_default_format_wins_and_warns():
    """
    **Feature: 0-config-formats (M1)**
    **Property: an implementation claiming an already-held (domain,
    format_name) pair displaces the incumbent by PRECEDENCE and logs
    pychestrate_config_format_shadowed naming both classes. Shadowing
    is allowed -- it is how an enterprise reader replaces the default
    outright -- but never silent.**
    """
    _prepare_runtime()

    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = _Capture()
    logger = logging.getLogger("pychestrate.configdocs")
    logger.addHandler(handler)
    try:
        register_config_document_format(implementation=ShadowingLandscapeFormat)
    finally:
        logger.removeHandler(handler)

    shadow_lines = [
        line for line in records
        if "pychestrate_config_format_shadowed" in line
    ]
    testbase.assert_equal(len(shadow_lines), 1)
    testbase.assert_equal("ShadowingLandscapeFormat" in shadow_lines[0], True)
    testbase.assert_equal("StubLandscapeFormat" in shadow_lines[0], True)

    resolved = resolve_format_implementation(
        domain=ConfigDocumentDomain.LANDSCAPE, format_name="codecraftai",
    )
    testbase.assert_equal(resolved is ShadowingLandscapeFormat, True)
    return


def test_shadowed_default_still_reads_the_document():
    """
    **Feature: 0-config-formats (M1)**
    **Property: after shadowing, the loader routes through the winning
    implementation -- the override is real, not just a lookup result.**
    """
    _prepare_runtime()
    register_config_document_format(implementation=ShadowingLandscapeFormat)

    with tempfile.TemporaryDirectory() as tmpdir:
        _write(
            directory=tmpdir, name="landscape.json",
            payload={"clients": [_device(identity="casey-01")]},
        )
        outcome = load_document(
            domain=ConfigDocumentDomain.LANDSCAPE, config_dir=tmpdir, environ={},
        )

    testbase.assert_equal(
        "ShadowingLandscapeFormat" in outcome.implementation, True,
    )
    testbase.assert_equal(outcome.ok, True)
    return
