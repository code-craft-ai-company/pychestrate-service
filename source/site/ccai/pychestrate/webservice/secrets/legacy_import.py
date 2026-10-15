"""
.. module:: secrets.legacy_import
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Carry the legacy secrets into the secrets vault (audit ADM-07, ``specs/model-convergence.md`` section 9).

.. moduleauthor:: Code Craft AI LLC

Admin, Secrets (legacy) and Admin, Secret Scopes write the older ``secrets`` / ``secret_scopes`` tables, which nothing in the product reads: repositories, webhooks and
notification channels use the vault. This copies what is in the older store into the vault, on an administrator's request: each secret is decrypted with the legacy key and
stored service-wide under ``<scope>/<name>`` through the vault's own service (so its access rules and audit apply). A name the vault already holds is skipped, never
overwritten; a secret that cannot be decrypted or stored is reported by name and changes nothing. No value is shown, logged or kept. The legacy rows are left alone.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from dataclasses import dataclass
from typing import Any, List, Tuple

from ccai.pychestrate.webservice.secrets import secrets_service
from ccai.pychestrate.webservice.secrets.exceptions import SecretAccessDeniedError, SecretAlreadyExistsError, SecretNotFoundError
from ccai.pychestrate.webservice.secrets.models import SecretScopeKind
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from ccai.pychestrate.webservice.secrets.secrets_aspects import build_default_aspects


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class LegacyImportResult:
    """
        What an import did.

        :param imported: Vault names stored.
        :param skipped: Vault names that were already in the vault (left as they are).
        :param failed: ``(vault name, reason)`` for each secret that could not be carried over; the reason never contains a value.
    """
    imported: Tuple[str, ...]
    skipped: Tuple[str, ...]
    failed: Tuple[Tuple[str, str], ...]


def vault_name_for(*, scope_name: str, secret_name: str) -> str:
    """
        The vault name a legacy secret is stored under: ``<scope>/<name>``, the form its references took.

        :param scope_name: The legacy scope's name.
        :param secret_name: The legacy secret's name.
    """
    return "{}/{}".format(scope_name, secret_name)


def _legacy_rows(*, db_session: Any) -> List[Tuple[str, str, int]]:
    """
        ``(scope name, secret name, scope id)`` of every legacy secret that is not deleted, by scope and name.
    """
    from ccai.pychestrate.core.orm import Secret, SecretScope  # noqa: E402

    rows = (
        db_session.query(SecretScope.name, Secret.name, Secret.scope_id)
        .join(Secret, Secret.scope_id == SecretScope.id)
        .filter(Secret.is_deleted == False)  # noqa: E712 -- SQL comparison
        .order_by(SecretScope.name, Secret.name)
        .all()
    )
    return [(row[0], row[1], row[2]) for row in rows]


def count_legacy_secrets(*, db_session: Any) -> int:
    """
        How many legacy secrets there are (those not deleted).
    """
    return len(_legacy_rows(db_session=db_session))


def import_legacy_secrets(*, db_session: Any, principal: Any, secret_manager: Any) -> LegacyImportResult:
    """
        Copy every legacy secret into the vault, service-wide, under ``<scope>/<name>``.

        :param db_session: Active SQLAlchemy session.
        :param principal: The administrator, whose vault rights apply (and who is named in the audit records).
        :param secret_manager: The legacy :class:`SecretManager` (it holds the key).

        :returns: What was imported, skipped and failed.
    """
    imported: List[str] = []
    skipped: List[str] = []
    failed: List[Tuple[str, str]] = []
    for scope_name, secret_name, scope_id in _legacy_rows(db_session=db_session):
        vault_name = vault_name_for(scope_name=scope_name, secret_name=secret_name)
        try:
            secrets_service.get_secret_record(db_session=db_session, secret_ref=vault_name)
            skipped.append(vault_name)
            continue
        except SecretNotFoundError:
            pass
        try:
            value = secret_manager.get_secret_value(secret_name, scope_id, None).value
        except Exception as xcpt:  # noqa: BLE001 -- reported by name, with the error's type only
            _LOGGER.warning("pychestrate.secrets.legacy_import_unreadable secret=%s error=%s", vault_name, type(xcpt).__name__)
            failed.append((vault_name, "it could not be decrypted with the legacy key"))
            continue
        payload = SecretBytes(str(value).encode("utf-8"))
        try:
            secrets_service.put_secret(
                db_session=db_session, principal=principal, secret_ref=vault_name, plaintext=payload,
                aspects=build_default_aspects(), scope_kind=SecretScopeKind.ORG, scope_ref=None,
            )
            imported.append(vault_name)
        except SecretAccessDeniedError:
            db_session.rollback()
            failed.append((vault_name, "you may not store secrets in the vault"))
        except SecretAlreadyExistsError:
            db_session.rollback()
            skipped.append(vault_name)
        except Exception as xcpt:  # noqa: BLE001 -- reported by name, with the error's type only
            db_session.rollback()
            _LOGGER.warning("pychestrate.secrets.legacy_import_failed secret=%s error=%s", vault_name, type(xcpt).__name__)
            failed.append((vault_name, "the vault refused it ({})".format(type(xcpt).__name__)))
        finally:
            payload.close()
    return LegacyImportResult(imported=tuple(imported), skipped=tuple(skipped), failed=tuple(failed))


__all__ = ["LegacyImportResult", "count_legacy_secrets", "import_legacy_secrets", "vault_name_for"]
