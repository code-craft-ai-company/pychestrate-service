"""
.. module:: backup.key_material
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Back up and restore the keys a database backup needs.

.. moduleauthor:: Code Craft AI LLC

A database backup is only usable with the keys that were active when
it was taken: every stored secret is wrapped under the KEK, and every
password hash mixes in the pepper. This module collects those keys
from the service's configured sources (``PYCHESTRATE_<KEY>_SOURCE`` =
``file`` | ``env``, the same variables the runtime loaders read) and
writes them to a **key bundle** -- ``<backup_id>.keys.tar``, mode
0600 -- that is stored apart from the data archive. The archive's
manifest records only each key's id and SHA-256 fingerprint, so an
archive and a bundle can be matched without the archive containing
key bytes.

Keys covered (skipped when not configured, except the KEK):

* ``kek`` -- decrypts every stored secret (required);
* ``password_pepper`` -- without it no password verifies;
* ``ui_cookie_secret`` -- signs UI session cookies;
* ``envelope_signing_key`` -- signs job envelopes pods verify;
* ``enrollment_ca`` -- signs pod client certificates.

Restore writes each key back to the path the *restoring* environment
configures (``<KEY>_FILE_PATH``), refusing to replace a different key
unless asked; keys the environment does not source from a file are
written to a fallback directory with the variables to set.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import io
import json
import os
import tarfile

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Mapping, Optional, Tuple

from ccai.pychestrate.webservice.backup.errors import (
    BackupArchiveInvalidError,
    BackupKeyMaterialError,
)


KEY_BUNDLE_FORMAT: str = "pychestrate-backup-keys"
KEY_BUNDLE_FORMAT_VERSION: int = 1
KEY_BUNDLE_SUFFIX: str = ".keys.tar"
KEY_BUNDLE_MANIFEST_MEMBER: str = "keys.json"
KEY_MEMBER_PREFIX: str = "keys/"

SOURCE_FILE: str = "file"
SOURCE_ENV: str = "env"


@dataclass(frozen=True)
class KeyMaterialSpec:
    """
        One key the service loads at startup.

        :ivar name: Stable identifier used in bundles and manifests.
        :ivar env_prefix: Prefix of its ``_SOURCE`` / ``_FILE_PATH`` /
                          ``_ENV_VAR`` / ``_ID`` variables.
        :ivar required: Whether a backup must include it.
        :ivar purpose: What losing it costs, for operators.
    """
    name: str
    env_prefix: str
    required: bool
    purpose: str

    def variable(self, suffix: str) -> str:
        """
            Name of one of the key's configuration variables.

            :param suffix: ``SOURCE``, ``FILE_PATH``, ``ENV_VAR`` or ``ID``.

            :returns: Variable name.
        """
        rtnval = "{}_{}".format(self.env_prefix, suffix)
        return rtnval


KEY_MATERIAL_SPECS: Tuple[KeyMaterialSpec, ...] = (
    KeyMaterialSpec(
        name="kek",
        env_prefix="PYCHESTRATE_KEK",
        required=True,
        purpose="key-encryption key; without it no stored secret decrypts",
    ),
    KeyMaterialSpec(
        name="password_pepper",
        env_prefix="PYCHESTRATE_PASSWORD_PEPPER",
        required=False,
        purpose="password pepper; without it no password verifies",
    ),
    KeyMaterialSpec(
        name="ui_cookie_secret",
        env_prefix="PYCHESTRATE_UI_COOKIE_SECRET",
        required=False,
        purpose="UI session cookie signing secret; a new one signs everyone out",
    ),
    KeyMaterialSpec(
        name="envelope_signing_key",
        env_prefix="PYCHESTRATE_ENVELOPE_SIGNING_KEY",
        required=False,
        purpose="job-envelope signing key pods verify",
    ),
    KeyMaterialSpec(
        name="enrollment_ca",
        env_prefix="PYCHESTRATE_ENROLLMENT_CA",
        required=False,
        purpose="pod enrollment CA; a new one means re-enrolling every pod",
    ),
)


@dataclass(frozen=True)
class CollectedKey:
    """
        Key material read from its configured source.

        :ivar name: Spec name.
        :ivar key_id: Operator-assigned id, when the key has one.
        :ivar source: ``file`` or ``env``.
        :ivar origin: File path, or name of the environment variable.
        :ivar material: The key bytes.
    """
    name: str
    key_id: Optional[str]
    source: str
    origin: str
    material: bytes

    @property
    def sha256(self) -> str:
        """
            Hex SHA-256 fingerprint of the key bytes.

            :returns: Hex digest.
        """
        rtnval = hashlib.sha256(self.material).hexdigest()
        return rtnval

    def describe(self) -> Dict[str, object]:
        """
            Manifest record for the key: everything except the bytes.

            :returns: JSON-friendly dict.
        """
        rtnval: Dict[str, object] = {
            "name": self.name,
            "key_id": self.key_id,
            "source": self.source,
            "origin": self.origin,
            "sha256": self.sha256,
            "size_bytes": len(self.material),
        }
        return rtnval


@dataclass(frozen=True)
class KeyCollection:
    """
        Result of :func:`collect_key_material`.

        :ivar keys: Keys that were read.
        :ivar skipped: ``{name: reason}`` for keys not backed up.
    """
    keys: List[CollectedKey]
    skipped: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KeyBundle:
    """
        A key bundle read back from disk.

        :ivar manifest: Parsed ``keys.json``.
        :ivar materials: ``{name: bytes}``.
    """
    manifest: Dict[str, object]
    materials: Dict[str, bytes]

    def records(self) -> List[Dict[str, object]]:
        """
            The per-key records in the bundle manifest.

            :returns: List of dicts.
        """
        rtnval = list(self.manifest.get("keys", []))
        return rtnval


@dataclass(frozen=True)
class KeyRestoreOutcome:
    """
        What happened to one key during restore.

        :ivar name: Spec name.
        :ivar action: ``written`` | ``unchanged`` | ``replaced`` |
                      ``written-to-fallback``.
        :ivar path: File the key now lives in.
        :ivar previous_copy: Where a replaced key was moved, if any.
        :ivar instruction: Configuration the operator must apply, if
                           any.
    """
    name: str
    action: str
    path: str
    previous_copy: Optional[str] = None
    instruction: Optional[str] = None


def _spec_by_name(name: str) -> Optional[KeyMaterialSpec]:
    """
        Look a spec up by name.

        :param name: Spec name.

        :returns: The spec or ``None``.
    """
    for spec in KEY_MATERIAL_SPECS:
        if spec.name == name:
            return spec
    return None


def collect_key_material(*, environ: Optional[Mapping[str, str]] = None) -> KeyCollection:
    """
        Read every configured key from its source.

        :param environ: Environment to read configuration from;
                        defaults to :data:`os.environ`.

        :returns: :class:`KeyCollection`.
        :raises: BackupKeyMaterialError when a configured key cannot be
                 read, or the required KEK is not configured.
    """
    env = environ if environ is not None else os.environ
    keys: List[CollectedKey] = []
    skipped: Dict[str, str] = {}
    for spec in KEY_MATERIAL_SPECS:
        source = str(env.get(spec.variable("SOURCE"), "") or "").strip().lower()
        key_id = env.get(spec.variable("ID"), None) or None
        if len(source) == 0:
            if spec.required is True:
                raise BackupKeyMaterialError(
                    "{} is not configured; a backup without the KEK cannot"
                    " decrypt its secrets.".format(spec.variable("SOURCE"))
                ) from None
            skipped[spec.name] = "not configured"
            continue

        if source == SOURCE_FILE:
            path = str(env.get(spec.variable("FILE_PATH"), "") or "")
            try:
                with open(path, "rb") as handle:
                    material = handle.read()
            except OSError as xcpt:
                err_lines = ["Cannot read key material for the backup."]
                err_lines.append("KEY: {}".format(spec.name))
                err_lines.append("PATH: {}".format(path))
                err_lines.append("CAUSE: {}".format(xcpt))
                raise BackupKeyMaterialError(os.linesep.join(err_lines)) from None
            keys.append(CollectedKey(
                name=spec.name, key_id=key_id, source=SOURCE_FILE, origin=path, material=material,
            ))
            continue

        if source == SOURCE_ENV:
            env_var = str(env.get(spec.variable("ENV_VAR"), "") or "")
            raw = env.get(env_var, None) if len(env_var) > 0 else None
            if raw is None:
                err_lines = ["Cannot read key material for the backup."]
                err_lines.append("KEY: {}".format(spec.name))
                err_lines.append("ENV_VAR: {} is not set".format(env_var or spec.variable("ENV_VAR")))
                raise BackupKeyMaterialError(os.linesep.join(err_lines)) from None
            keys.append(CollectedKey(
                name=spec.name, key_id=key_id, source=SOURCE_ENV, origin=env_var,
                material=raw.encode("utf-8"),
            ))
            continue

        if spec.required is True:
            raise BackupKeyMaterialError(
                "{}={} cannot be backed up (only file and env sources are).".format(
                    spec.variable("SOURCE"), source,
                )
            ) from None
        skipped[spec.name] = "source '{}' is not backed up".format(source)

    rtnval = KeyCollection(keys=keys, skipped=skipped)
    return rtnval


def write_key_bundle(
        *,
        keys: List[CollectedKey],
        destination_path: str,
        backup_id: str,
        created_at: datetime
    ) -> str:
    """
        Write a key bundle atomically with mode 0600.

        :param keys: Keys to include.
        :param destination_path: Final bundle path.
        :param backup_id: Backup the bundle belongs to.
        :param created_at: Backup timestamp.

        :returns: Hex SHA-256 of the written bundle.
    """
    manifest = {
        "format": KEY_BUNDLE_FORMAT,
        "format_version": KEY_BUNDLE_FORMAT_VERSION,
        "backup_id": backup_id,
        "created_at": created_at.isoformat(),
        "keys": [dict(key.describe(), member=KEY_MEMBER_PREFIX + key.name) for key in keys],
    }
    partial = destination_path + ".partial"
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        with tarfile.open(fileobj=handle, mode="w") as archive:
            _add_bytes(archive=archive, name=KEY_BUNDLE_MANIFEST_MEMBER,
                       data=json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))
            for key in keys:
                _add_bytes(archive=archive, name=KEY_MEMBER_PREFIX + key.name, data=key.material)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(partial, 0o600)
    os.replace(partial, destination_path)

    hasher = hashlib.sha256()
    with open(destination_path, "rb") as handle:
        hasher.update(handle.read())
    rtnval = hasher.hexdigest()
    return rtnval


def _add_bytes(*, archive: tarfile.TarFile, name: str, data: bytes) -> None:
    """
        Add an in-memory member (mode 0600, mtime 0) to a tar archive.

        :param archive: Open archive.
        :param name: Member name.
        :param data: Member bytes.

        :returns: None.
    """
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mode = 0o600
    info.mtime = 0
    archive.addfile(info, io.BytesIO(data))
    return


def read_key_bundle(*, path: str) -> KeyBundle:
    """
        Read and validate a key bundle.

        :param path: Bundle file.

        :returns: :class:`KeyBundle`.
        :raises: BackupArchiveInvalidError when the bundle is unreadable
                 or a member does not match its recorded fingerprint.
    """
    try:
        with tarfile.open(path, mode="r") as archive:
            manifest_member = archive.extractfile(KEY_BUNDLE_MANIFEST_MEMBER)
            if manifest_member is None:
                raise BackupArchiveInvalidError("Key bundle has no keys.json.") from None
            manifest = json.loads(manifest_member.read().decode("utf-8"))
            if manifest.get("format") != KEY_BUNDLE_FORMAT:
                raise BackupArchiveInvalidError("Not a pychestrate key bundle: {}".format(path)) from None
            materials: Dict[str, bytes] = {}
            for record in manifest.get("keys", []):
                name = str(record.get("name", ""))
                if _spec_by_name(name) is None:
                    raise BackupArchiveInvalidError("Key bundle names an unknown key: {}".format(name)) from None
                member = archive.extractfile(KEY_MEMBER_PREFIX + name)
                if member is None:
                    raise BackupArchiveInvalidError("Key bundle is missing key {}".format(name)) from None
                data = member.read()
                if hashlib.sha256(data).hexdigest() != record.get("sha256"):
                    raise BackupArchiveInvalidError(
                        "Key {} in the bundle does not match its fingerprint.".format(name)
                    ) from None
                materials[name] = data
    except (OSError, tarfile.TarError, KeyError, ValueError) as xcpt:
        err_lines = ["Cannot read the key bundle."]
        err_lines.append("PATH: {}".format(path))
        err_lines.append("CAUSE: {}".format(xcpt))
        raise BackupArchiveInvalidError(os.linesep.join(err_lines)) from None

    rtnval = KeyBundle(manifest=manifest, materials=materials)
    return rtnval


def check_bundle_matches_manifest(
        *,
        bundle: KeyBundle,
        manifest_keys: List[Dict[str, object]]
    ) -> List[str]:
    """
        Compare a bundle with the key fingerprints an archive manifest
        recorded.

        :param bundle: Key bundle.
        :param manifest_keys: ``manifest["secrets"]["keys"]`` records.

        :returns: Names of keys whose fingerprints differ or that the
                  bundle lacks (empty when the pair matches).
    """
    in_bundle = {str(record.get("name")): record.get("sha256") for record in bundle.records()}
    mismatched: List[str] = []
    for record in manifest_keys:
        name = str(record.get("name"))
        if in_bundle.get(name, None) != record.get("sha256"):
            mismatched.append(name)
    rtnval = mismatched
    return rtnval


def _write_private_file(*, path: str, data: bytes) -> None:
    """
        Write a key file with mode 0600, creating its directory 0700.

        :param path: Destination.
        :param data: Key bytes.

        :returns: None.
    """
    directory = os.path.dirname(path)
    if len(directory) > 0:
        os.makedirs(directory, mode=0o700, exist_ok=True)
    partial = path + ".restoring"
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(partial, 0o600)
    os.replace(partial, path)
    return


def restore_key_material(
        *,
        bundle: KeyBundle,
        fallback_dir: str,
        overwrite: bool,
        now: datetime,
        environ: Optional[Mapping[str, str]] = None
    ) -> List[KeyRestoreOutcome]:
    """
        Put each key in the bundle where the restoring environment
        loads it from. Plans every key before writing any, so a refused
        overwrite leaves nothing half-restored.

        :param bundle: Key bundle.
        :param fallback_dir: Directory for keys the environment does
                             not source from a file.
        :param overwrite: Replace a configured key file that holds a
                          different key (the old file is kept as
                          ``<path>.pre-restore-<timestamp>``).
        :param now: Timestamp for safety-copy names.
        :param environ: Environment to read configuration from.

        :returns: One :class:`KeyRestoreOutcome` per key.
        :raises: BackupKeyMaterialError when a configured key file holds
                 a different key and ``overwrite`` is False.
    """
    env = environ if environ is not None else os.environ
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    plan: List[Tuple[KeyMaterialSpec, Dict[str, object], bytes, str, str]] = []
    conflicts: List[str] = []
    for record in bundle.records():
        spec = _spec_by_name(str(record.get("name")))
        data = bundle.materials[spec.name]
        source = str(env.get(spec.variable("SOURCE"), "") or "").strip().lower()
        path = str(env.get(spec.variable("FILE_PATH"), "") or "")
        if source == SOURCE_FILE and len(path) > 0:
            if os.path.exists(path) is False:
                plan.append((spec, record, data, path, "written"))
                continue
            with open(path, "rb") as handle:
                current = handle.read()
            if current == data:
                plan.append((spec, record, data, path, "unchanged"))
                continue
            if overwrite is False:
                conflicts.append("{} ({})".format(spec.name, path))
                continue
            plan.append((spec, record, data, path, "replaced"))
            continue
        plan.append((spec, record, data, os.path.join(fallback_dir, spec.name), "written-to-fallback"))

    if len(conflicts) > 0:
        err_lines = ["Configured key files hold different keys than the backup."]
        err_lines.append("KEYS: {}".format(", ".join(conflicts)))
        err_lines.append(
            "HINT: restoring a database without its own keys leaves its secrets"
            " undecryptable; pass --overwrite-keys to replace them (the current"
            " files are kept as <path>.pre-restore-<timestamp>)."
        )
        raise BackupKeyMaterialError(os.linesep.join(err_lines)) from None

    outcomes: List[KeyRestoreOutcome] = []
    for spec, record, data, path, action in plan:
        previous_copy: Optional[str] = None
        instruction: Optional[str] = None
        if action == "replaced":
            previous_copy = "{}.pre-restore-{}".format(path, stamp)
            os.replace(path, previous_copy)
        if action != "unchanged":
            _write_private_file(path=path, data=data)
        if action == "written-to-fallback":
            instruction = "set {}=file and {}={}".format(
                spec.variable("SOURCE"), spec.variable("FILE_PATH"), path,
            )
        key_id = record.get("key_id")
        configured_id = env.get(spec.variable("ID"), None)
        if key_id and configured_id and key_id != configured_id:
            id_note = "set {}={} (the backup's key id)".format(spec.variable("ID"), key_id)
            instruction = id_note if instruction is None else instruction + "; " + id_note
        outcomes.append(KeyRestoreOutcome(
            name=spec.name,
            action=action,
            path=path,
            previous_copy=previous_copy,
            instruction=instruction,
        ))
    rtnval = outcomes
    return rtnval


__all__ = [
    "CollectedKey",
    "KEY_BUNDLE_SUFFIX",
    "KEY_MATERIAL_SPECS",
    "KeyBundle",
    "KeyCollection",
    "KeyMaterialSpec",
    "KeyRestoreOutcome",
    "check_bundle_matches_manifest",
    "collect_key_material",
    "read_key_bundle",
    "restore_key_material",
    "write_key_bundle",
]
