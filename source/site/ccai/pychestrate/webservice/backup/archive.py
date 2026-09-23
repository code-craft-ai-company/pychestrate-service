"""
.. module:: backup.archive
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The on-disk format of a backup archive.

.. moduleauthor:: Code Craft AI LLC

A backup archive is a gzip-compressed tar file,
``<backup_id>.backup.tar.gz``, holding:

* ``database/pychestrate.sqlite`` or ``database/pychestrate.pgdump``
  -- the database snapshot (see :mod:`backup.database_snapshot`);
* ``artifacts/...`` -- the run-artifact tree, relative to the artifact
  root;
* ``manifest.json`` -- written last, describing exactly what was
  added: format version, backup id, timestamps, the database dialect,
  its SHA-256, table / row counts and alembic revision, the artifact
  file count and bytes, and the id + SHA-256 fingerprint of every key
  in the separate key bundle (never the key bytes).

Next to the archive, ``<archive>.sha256`` carries the archive's
checksum in ``sha256sum`` format, so an archive copied off-host can be
verified (``sha256sum -c``) without the database that recorded it.

Extraction only accepts the member layout above and uses tarfile's
``data`` filter, so a crafted archive cannot write outside the
extraction directory.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import json
import os
import tarfile

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ccai.pychestrate.webservice.backup.database_snapshot import (
    DatabaseSnapshot,
    file_sha256,
)
from ccai.pychestrate.webservice.backup.errors import BackupArchiveInvalidError


ARCHIVE_FORMAT: str = "pychestrate-backup"
ARCHIVE_FORMAT_VERSION: int = 1
ARCHIVE_SUFFIX: str = ".backup.tar.gz"
CHECKSUM_SUFFIX: str = ".sha256"
MANIFEST_MEMBER: str = "manifest.json"
DATABASE_MEMBER_DIR: str = "database"
ARTIFACTS_MEMBER_DIR: str = "artifacts"


@dataclass(frozen=True)
class ArtifactInventory:
    """
        What was archived from the artifact root.

        :ivar root: Artifact root that was walked.
        :ivar file_count: Regular files added.
        :ivar total_bytes: Their total size.
    """
    root: str
    file_count: int
    total_bytes: int


@dataclass(frozen=True)
class BuiltArchive:
    """
        Result of :func:`build_archive`.

        :ivar path: Archive file.
        :ivar sha256: Hex SHA-256 of the archive.
        :ivar size_bytes: Archive size.
        :ivar manifest: The manifest written into it.
    """
    path: str
    sha256: str
    size_bytes: int
    manifest: Dict[str, Any]


def _add_artifact_tree(*, archive: tarfile.TarFile, artifact_root: str) -> ArtifactInventory:
    """
        Add every regular file under ``artifact_root`` to the archive
        below ``artifacts/``. Symlinks and special files are skipped
        (artifacts are plain files uploaded by pods).

        :param archive: Open archive.
        :param artifact_root: Directory to walk.

        :returns: :class:`ArtifactInventory`.
    """
    file_count = 0
    total_bytes = 0
    if os.path.isdir(artifact_root) is True:
        for current, directories, files in os.walk(artifact_root):
            directories.sort()
            for file_name in sorted(files):
                full_path = os.path.join(current, file_name)
                if os.path.islink(full_path) is True or os.path.isfile(full_path) is False:
                    continue
                relative = os.path.relpath(full_path, artifact_root).replace(os.sep, "/")
                try:
                    archive.add(full_path, arcname=ARTIFACTS_MEMBER_DIR + "/" + relative, recursive=False)
                except FileNotFoundError:
                    # Removed between the walk and the add (retention);
                    # it is simply not part of this backup.
                    continue
                file_count += 1
                total_bytes += os.path.getsize(full_path)
    rtnval = ArtifactInventory(root=artifact_root, file_count=file_count, total_bytes=total_bytes)
    return rtnval


def build_archive(
        *,
        destination_path: str,
        manifest: Dict[str, Any],
        database_snapshot: Optional[DatabaseSnapshot],
        artifact_root: Optional[str]
    ) -> BuiltArchive:
    """
        Write a backup archive.

        :param destination_path: Archive file to create (mode 0600).
        :param manifest: Manifest skeleton; the ``database`` and
                         ``object_store`` sections are filled in here.
        :param database_snapshot: Snapshot to include, or ``None``.
        :param artifact_root: Artifact root to include, or ``None``.

        :returns: :class:`BuiltArchive`.
    """
    final_manifest = dict(manifest)
    final_manifest["format"] = ARCHIVE_FORMAT
    final_manifest["format_version"] = ARCHIVE_FORMAT_VERSION

    descriptor = os.open(destination_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        with tarfile.open(fileobj=handle, mode="w:gz") as archive:
            if database_snapshot is not None:
                member = DATABASE_MEMBER_DIR + "/" + database_snapshot.file_name
                archive.add(database_snapshot.file_path, arcname=member, recursive=False)
                final_manifest["database"] = {
                    "included": True,
                    "dialect": database_snapshot.dialect,
                    "artifact": member,
                    "size_bytes": database_snapshot.size_bytes,
                    "sha256": database_snapshot.sha256,
                    "table_count": database_snapshot.table_count,
                    "alembic_revision": database_snapshot.alembic_revision,
                    "row_counts": dict(database_snapshot.row_counts),
                }
            else:
                final_manifest["database"] = {"included": False}

            if artifact_root is not None:
                inventory = _add_artifact_tree(archive=archive, artifact_root=artifact_root)
                final_manifest["object_store"] = {
                    "included": True,
                    "artifact_root": inventory.root,
                    "artifact": ARTIFACTS_MEMBER_DIR + "/",
                    "object_count": inventory.file_count,
                    "size_bytes": inventory.total_bytes,
                }
            else:
                final_manifest["object_store"] = {"included": False}

            manifest_bytes = json.dumps(final_manifest, indent=2, sort_keys=True).encode("utf-8")
            info = tarfile.TarInfo(name=MANIFEST_MEMBER)
            info.size = len(manifest_bytes)
            info.mode = 0o600
            info.mtime = 0
            archive.addfile(info, io.BytesIO(manifest_bytes))
        handle.flush()
        os.fsync(handle.fileno())

    rtnval = BuiltArchive(
        path=destination_path,
        sha256=file_sha256(path=destination_path),
        size_bytes=os.path.getsize(destination_path),
        manifest=final_manifest,
    )
    return rtnval


def write_checksum_sidecar(*, archive_path: str, sha256: str) -> str:
    """
        Write ``<archive>.sha256`` in ``sha256sum`` format.

        :param archive_path: Archive file.
        :param sha256: Its hex digest.

        :returns: Sidecar path.
    """
    sidecar = archive_path + CHECKSUM_SUFFIX
    with open(sidecar, "w", encoding="utf-8") as handle:
        handle.write("{}  {}\n".format(sha256, os.path.basename(archive_path)))
    os.chmod(sidecar, 0o600)
    rtnval = sidecar
    return rtnval


def read_checksum_sidecar(*, archive_path: str) -> Optional[str]:
    """
        Read the digest from ``<archive>.sha256``.

        :param archive_path: Archive file.

        :returns: Hex digest, or ``None`` when there is no sidecar.
    """
    sidecar = archive_path + CHECKSUM_SUFFIX
    if os.path.isfile(sidecar) is False:
        return None
    with open(sidecar, "r", encoding="utf-8") as handle:
        first = handle.readline().strip()
    rtnval = first.split()[0] if len(first) > 0 else None
    return rtnval


def _check_member_name(*, name: str) -> None:
    """
        Refuse archive members outside the known layout.

        :param name: Member name.

        :raises: BackupArchiveInvalidError for an unexpected or unsafe
                 name.
    """
    if name == MANIFEST_MEMBER:
        return
    parts = name.split("/")
    if name.startswith("/") or ".." in parts:
        raise BackupArchiveInvalidError("Unsafe archive member: {}".format(name)) from None
    if parts[0] not in (DATABASE_MEMBER_DIR, ARTIFACTS_MEMBER_DIR):
        raise BackupArchiveInvalidError("Unexpected archive member: {}".format(name)) from None
    return


def read_archive_manifest(*, archive_path: str) -> Dict[str, Any]:
    """
        Read ``manifest.json`` from an archive and check its format.

        :param archive_path: Archive file.

        :returns: Parsed manifest.
        :raises: BackupArchiveInvalidError when unreadable or not a
                 pychestrate backup.
    """
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            manifest: Optional[Dict[str, Any]] = None
            for member in archive:
                _check_member_name(name=member.name)
                if member.name == MANIFEST_MEMBER:
                    extracted = archive.extractfile(member)
                    manifest = json.loads(extracted.read().decode("utf-8"))
    except (OSError, EOFError, tarfile.TarError, ValueError) as xcpt:
        err_lines = ["Cannot read the backup archive."]
        err_lines.append("PATH: {}".format(archive_path))
        err_lines.append("CAUSE: {}".format(xcpt))
        raise BackupArchiveInvalidError(os.linesep.join(err_lines)) from None

    if manifest is None or manifest.get("format") != ARCHIVE_FORMAT:
        raise BackupArchiveInvalidError(
            "Not a pychestrate backup archive (no manifest): {}".format(archive_path)
        ) from None
    if int(manifest.get("format_version", 0)) > ARCHIVE_FORMAT_VERSION:
        raise BackupArchiveInvalidError(
            "Backup archive format {} is newer than this service understands ({}).".format(
                manifest.get("format_version"), ARCHIVE_FORMAT_VERSION,
            )
        ) from None
    rtnval = manifest
    return rtnval


def extract_archive(*, archive_path: str, destination_dir: str) -> Dict[str, Any]:
    """
        Extract an archive into ``destination_dir`` after checking its
        member layout.

        :param archive_path: Archive file.
        :param destination_dir: Empty directory to extract into.

        :returns: The archive manifest.
        :raises: BackupArchiveInvalidError on an unsafe or unreadable
                 archive.
    """
    manifest = read_archive_manifest(archive_path=archive_path)
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members: List[tarfile.TarInfo] = []
            for member in archive:
                _check_member_name(name=member.name)
                members.append(member)
            archive.extractall(destination_dir, members=members, filter="data")
    except (OSError, EOFError, tarfile.TarError) as xcpt:
        err_lines = ["Cannot extract the backup archive."]
        err_lines.append("PATH: {}".format(archive_path))
        err_lines.append("CAUSE: {}".format(xcpt))
        raise BackupArchiveInvalidError(os.linesep.join(err_lines)) from None
    rtnval = manifest
    return rtnval


def archive_sha256_matches(*, archive_path: str, expected_sha256: str) -> bool:
    """
        Compare an archive's SHA-256 with an expected digest.

        :param archive_path: Archive file.
        :param expected_sha256: Hex digest.

        :returns: True on a match.
    """
    rtnval = file_sha256(path=archive_path) == str(expected_sha256).strip().lower()
    return rtnval


__all__ = [
    "ARCHIVE_FORMAT",
    "ARCHIVE_FORMAT_VERSION",
    "ARCHIVE_SUFFIX",
    "ARTIFACTS_MEMBER_DIR",
    "ArtifactInventory",
    "BuiltArchive",
    "CHECKSUM_SUFFIX",
    "DATABASE_MEMBER_DIR",
    "MANIFEST_MEMBER",
    "archive_sha256_matches",
    "build_archive",
    "extract_archive",
    "read_archive_manifest",
    "read_checksum_sidecar",
    "write_checksum_sidecar",
]
