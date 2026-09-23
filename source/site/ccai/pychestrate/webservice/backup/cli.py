"""
.. module:: backup.cli
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pychestrate-admin backup`` -- create, list, verify and
               restore backups from the command line.

.. moduleauthor:: Code Craft AI LLC

Run as ``python -m ccai.pychestrate.admin backup <command>`` with the
same environment as the service (``PYCHESTRATE_*`` variables, presence
directory), e.g. through ``development/run-staging-gunicorn admin``
on the alpha host::

    backup create [--note TEXT] [--no-database] [--no-artifacts]
                  [--no-keys] [--keep N]
    backup list
    backup verify ARCHIVE [--keys BUNDLE]
    backup restore ARCHIVE [--keys BUNDLE] --yes [--overwrite-keys]
                   [--skip-keys] [--skip-artifacts] [--keys-dir DIR]

``create`` works while the service runs (the snapshot is consistent)
and is what the scheduled ``pychestrate-backup.timer`` runs.
``restore`` requires the service to be **stopped**: it replaces the
database, the artifact root and the key files, keeping each replaced
item as ``pre-restore-<timestamp>``.

Exit codes: 0 success, 1 the operation failed, 2 usage error or
missing confirmation, 3 verification failed.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import os
import sys

from typing import Optional, Sequence, TextIO

from ccai.pychestrate.webservice.backup.errors import BackupError


EXIT_OK: int = 0
EXIT_FAILED: int = 1
EXIT_USAGE: int = 2
EXIT_VERIFICATION_FAILED: int = 3


def _build_parser() -> argparse.ArgumentParser:
    """
        Build the ``backup`` argument parser.

        :returns: Configured parser.
    """
    parser = argparse.ArgumentParser(
        prog="pychestrate-admin backup",
        description="Create, list, verify and restore pychestrate backups.",
    )
    parser.add_argument("--presence-dir", default=None,
                        help="pychestrate presence directory (default: PYCHESTRATE_PRESENCE_DIR or ~/pychestrate)")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="back up the database, run artifacts and keys now")
    create.add_argument("--note", default="", help="free-text note stored on the backup record")
    create.add_argument("--no-database", action="store_true", help="leave the database out")
    create.add_argument("--no-artifacts", action="store_true", help="leave the run artifacts out")
    create.add_argument("--no-keys", action="store_true", help="do not write a key bundle")
    create.add_argument("--keep", type=int, default=None,
                        help="afterwards delete all but the newest N archives (with their key bundles)")

    commands.add_parser("list", help="list the archives in the backup root")

    verify = commands.add_parser("verify", help="check that an archive (and key bundle) can be restored")
    verify.add_argument("archive", help="path to <backup_id>.backup.tar.gz")
    verify.add_argument("--keys", default=None, help="path to <backup_id>.keys.tar (default: the key-bundle directory)")

    restore = commands.add_parser("restore", help="restore a backup over this host (service stopped)")
    restore.add_argument("archive", help="path to <backup_id>.backup.tar.gz")
    restore.add_argument("--keys", default=None, help="path to <backup_id>.keys.tar (default: the key-bundle directory)")
    restore.add_argument("--yes", action="store_true", help="confirm: the service is stopped and may be overwritten")
    restore.add_argument("--overwrite-keys", action="store_true",
                         help="replace configured key files that hold different keys")
    restore.add_argument("--skip-keys", action="store_true", help="do not restore key material")
    restore.add_argument("--skip-artifacts", action="store_true", help="do not restore run artifacts")
    restore.add_argument("--keys-dir", default=None,
                         help="where to put keys the environment does not load from a file"
                              " (default: <presence>/restored-keys)")
    return parser


def _establish_persona(*, presence_dir: Optional[str]) -> str:
    """
        Establish the pychestrate persona (presence directory +
        settings.config) so configuration resolves exactly as it does
        in the service. A no-op when the process already has one.

        :param presence_dir: ``--presence-dir`` value, if given.

        :returns: The presence directory in effect.
    """
    from ccai.thisapp import wellknown
    from ccai.thisapp.persona import establish_app_persona
    from ccai.pychestrate.webservice.pychestrate_presence import resolve_presence_dir

    argv = ["--presence-dir", presence_dir] if presence_dir else []
    resolved = resolve_presence_dir(argv=argv)
    if wellknown.THISAPPLICATION_SINGLETON is None:
        establish_app_persona(
            name="pychestrate",
            logger_name="scms",
            log_basename="pychestrate",
            presence_dir=resolved,
        )
    rtnval = resolved
    return rtnval


def _database_url() -> str:
    """
        Resolve the database URL the service would use.

        :returns: SQLAlchemy URL string.
    """
    from ccai.thisapp.wellknown import ThisApplicationSingleton
    from ccai.pychestrate.webservice.pychestrate_variables import (
        PychestrateVariables,
        PychestrateVariablesDesc,
    )

    ThisApplicationSingleton().forget_variable(PychestrateVariablesDesc.PYCHESTRATE_DATABASE_URL)
    rtnval = str(PychestrateVariables.PYCHESTRATE_DATABASE_URL)
    return rtnval


def _print_report(*, report, out: TextIO) -> None:
    """
        Print a verification report, one line per check.

        :param report: :class:`VerificationReport`.
        :param out: Output stream.

        :returns: None.
    """
    for check in report.checks:
        out.write("  [{}] {:<28} {}\n".format("ok" if check.ok else "FAIL", check.name, check.detail))
    return


def _default_key_bundle(*, archive: str) -> Optional[str]:
    """
        Guess the key bundle for an archive: same backup id, in the
        configured key-bundle directory.

        :param archive: Archive path.

        :returns: Bundle path, or ``None`` when it does not exist.
    """
    from ccai.pychestrate.webservice.backup.archive import ARCHIVE_SUFFIX
    from ccai.pychestrate.webservice.backup.locations import resolve_backup_keys_dir
    from ccai.pychestrate.webservice.backup.service import key_bundle_path_for

    name = os.path.basename(archive)
    if name.endswith(ARCHIVE_SUFFIX) is False:
        return None
    candidate = key_bundle_path_for(keys_dir=resolve_backup_keys_dir(), backup_id=name[: -len(ARCHIVE_SUFFIX)])
    rtnval = candidate if os.path.isfile(candidate) else None
    return rtnval


def _command_create(*, args: argparse.Namespace, out: TextIO) -> int:
    """
        ``backup create``.

        :param args: Parsed arguments.
        :param out: Output stream.

        :returns: Exit code.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from ccai.pychestrate.webservice.backup.service import (
        BackupAspects,
        prune_backups,
        resolve_backup_sources,
        trigger_backup,
    )

    engine = create_engine(_database_url())
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        view = trigger_backup(
            db_session=session,
            aspects=BackupAspects(
                include_database=not args.no_database,
                include_object_store=not args.no_artifacts,
                include_secrets=not args.no_keys,
                note=args.note,
            ),
            actor_id=None,
            sources=resolve_backup_sources(engine=engine),
        )
    finally:
        session.close()
        engine.dispose()

    manifest = view.manifest
    out.write("backup {} {}\n".format(view.backup_id, view.status))
    out.write("  archive   {} ({} bytes, sha256 {})\n".format(view.archive_uri, view.size_bytes, view.archive_sha256))
    database = manifest.get("database", {})
    if database.get("included"):
        out.write("  database  {} snapshot, {} tables\n".format(database.get("dialect"), database.get("table_count")))
    object_store = manifest.get("object_store", {})
    if object_store.get("included"):
        out.write("  artifacts {} files from {}\n".format(object_store.get("object_count"), object_store.get("artifact_root")))
    secrets = manifest.get("secrets", {})
    if secrets.get("included"):
        names = ", ".join(str(key.get("name")) for key in secrets.get("keys", []))
        out.write("  keys      {} -> {}\n".format(names, secrets.get("key_bundle")))
        out.write("            store the key bundle apart from the archive\n")

    if args.keep is not None:
        removed = prune_backups(keep=args.keep)
        out.write("  pruned    {} file(s), keeping the newest {} archive(s)\n".format(len(removed), args.keep))
    rtnval = EXIT_OK
    return rtnval


def _command_list(*, out: TextIO) -> int:
    """
        ``backup list``.

        :param out: Output stream.

        :returns: Exit code.
    """
    from ccai.pychestrate.webservice.backup.archive import ARCHIVE_SUFFIX
    from ccai.pychestrate.webservice.backup.locations import (
        resolve_backup_keys_dir,
        resolve_backup_root,
    )
    from ccai.pychestrate.webservice.backup.service import key_bundle_path_for

    root = resolve_backup_root()
    keys_dir = resolve_backup_keys_dir()
    out.write("backup root: {}\nkey bundles: {}\n".format(root, keys_dir))
    if os.path.isdir(root) is False:
        out.write("  (no backups)\n")
        return EXIT_OK
    archives = sorted(
        (name for name in os.listdir(root) if name.endswith(ARCHIVE_SUFFIX)),
        key=lambda name: os.path.getmtime(os.path.join(root, name)),
    )
    for name in archives:
        path = os.path.join(root, name)
        backup_id = name[: -len(ARCHIVE_SUFFIX)]
        has_keys = os.path.isfile(key_bundle_path_for(keys_dir=keys_dir, backup_id=backup_id))
        out.write("  {}  {:>12} bytes  keys: {}\n".format(name, os.path.getsize(path), "yes" if has_keys else "no"))
    rtnval = EXIT_OK
    return rtnval


def _command_verify(*, args: argparse.Namespace, out: TextIO) -> int:
    """
        ``backup verify``.

        :param args: Parsed arguments.
        :param out: Output stream.

        :returns: Exit code.
    """
    from ccai.pychestrate.webservice.backup.service import verify_backup

    keys = args.keys if args.keys is not None else _default_key_bundle(archive=args.archive)
    report = verify_backup(archive_path=os.path.abspath(args.archive), key_bundle_path=keys)
    out.write("verify {}{}\n".format(args.archive, " with keys " + keys if keys else ""))
    _print_report(report=report, out=out)
    out.write("result: {}\n".format("restorable" if report.ok else "NOT restorable"))
    rtnval = EXIT_OK if report.ok else EXIT_VERIFICATION_FAILED
    return rtnval


def _command_restore(*, args: argparse.Namespace, presence_dir: str, out: TextIO, err: TextIO) -> int:
    """
        ``backup restore``.

        :param args: Parsed arguments.
        :param presence_dir: Presence directory in effect.
        :param out: Output stream.
        :param err: Error stream.

        :returns: Exit code.
    """
    from ccai.pychestrate.webservice.backup.locations import resolve_backup_root
    from ccai.pychestrate.webservice.backup.service import restore_backup
    from ccai.pychestrate.webservice.jobs.results.artifact_root import resolve_artifact_root

    database_url = _database_url()
    artifact_root = resolve_artifact_root()
    if args.yes is False:
        err.write(
            "restore replaces the database ({}), the artifact root ({}) and the key files"
            " configured for this service.\nStop the service first, then re-run with --yes.\n".format(
                database_url.split("@")[-1], artifact_root,
            )
        )
        return EXIT_USAGE

    keys = None
    if args.skip_keys is False:
        keys = args.keys if args.keys is not None else _default_key_bundle(archive=args.archive)
    fallback_dir = args.keys_dir if args.keys_dir is not None else os.path.join(presence_dir, "restored-keys")
    report = restore_backup(
        archive_path=os.path.abspath(args.archive),
        key_bundle_path=keys,
        database_url=database_url,
        artifact_root=artifact_root,
        fallback_keys_dir=fallback_dir,
        safety_copy_dir=resolve_backup_root(),
        overwrite_keys=args.overwrite_keys,
        restore_keys=not args.skip_keys,
        restore_artifacts=not args.skip_artifacts,
    )

    out.write("restored backup {}\n".format(report.backup_id))
    if report.database is not None:
        out.write("  database  {} ({})\n".format(report.database.target, report.database.dialect))
        if report.database.previous_copy:
            out.write("            previous state kept at {}\n".format(report.database.previous_copy))
    if report.artifact_root is not None:
        out.write("  artifacts {}\n".format(report.artifact_root))
        if report.artifacts_previous_copy:
            out.write("            previous tree kept at {}\n".format(report.artifacts_previous_copy))
    for outcome in report.keys:
        out.write("  key       {:<22} {:<20} {}\n".format(outcome.name, outcome.action, outcome.path))
        if outcome.previous_copy:
            out.write("            previous key kept at {}\n".format(outcome.previous_copy))
        if outcome.instruction:
            out.write("            ACTION: {}\n".format(outcome.instruction))
    out.write("start the service and sign in to check the restore.\n")
    rtnval = EXIT_OK
    return rtnval


def main(*, argv: Optional[Sequence[str]], out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    """
        Dispatch a ``backup`` invocation.

        :param argv: Arguments after ``backup``.
        :param out: Output stream (default stdout).
        :param err: Error stream (default stderr).

        :returns: Process exit code.
    """
    out_stream = out if out is not None else sys.stdout
    err_stream = err if err is not None else sys.stderr
    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])
    except SystemExit as exit_request:
        rtnval = EXIT_OK if exit_request.code in (0, None) else EXIT_USAGE
        return rtnval

    presence_dir = _establish_persona(presence_dir=args.presence_dir)
    try:
        if args.command == "create":
            rtnval = _command_create(args=args, out=out_stream)
        elif args.command == "list":
            rtnval = _command_list(out=out_stream)
        elif args.command == "verify":
            rtnval = _command_verify(args=args, out=out_stream)
        else:
            rtnval = _command_restore(args=args, presence_dir=presence_dir, out=out_stream, err=err_stream)
    except BackupError as xcpt:
        err_stream.write("backup {} failed:\n{}\n".format(args.command, xcpt))
        rtnval = EXIT_FAILED
    out_stream.flush()
    return rtnval


__all__ = [
    "EXIT_FAILED",
    "EXIT_OK",
    "EXIT_USAGE",
    "EXIT_VERIFICATION_FAILED",
    "main",
]


if __name__ == "__main__":
    sys.exit(main(argv=None))
