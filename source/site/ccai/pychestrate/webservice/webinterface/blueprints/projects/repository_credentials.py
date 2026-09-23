"""
.. module:: webinterface.blueprints.projects.repository_credentials
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Read project repositories' credential secrets from the
               secrets vault on behalf of the signed-in user.

.. moduleauthor:: Code Craft AI LLC

A repository that authenticates (``https_token`` / ``ssh_key``) names a
secret in the secrets vault (System > Secrets) by its reference. The
repository pages used to build their :class:`RepositoryManager` without
any way to read secrets, so the reference was never resolved and only
public repositories worked.

The secret is read with :func:`secrets_service.read_secret` as the
signed-in user, so the vault's access rules apply (an ORG secret needs
``system:secrets.read``; a personal secret, its owner) and every read
is audited. Checking the same read when a repository is saved means
nobody can point a repository at a secret they could not read
themselves. The value is handed straight to git and is never logged,
flashed or rendered.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Callable, List


_module_logger = logging.getLogger(__name__)

#: Most secret references offered in the repository forms' picker.
SECRET_PICKER_LIMIT: int = 200


def _principal_for(*, user_id: Any) -> Any:
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthProviderKind,
    )
    from ccai.pychestrate.webservice.security.auth.session_service import (  # noqa: E402
        AuthPrincipal,
    )
    rtnval = AuthPrincipal(
        user_id=str(user_id),
        session_id="",
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
    )
    return rtnval


def read_repository_secret(*, db_session: Any, user_id: Any, secret_ref: str) -> str:
    """
        Read one secret from the vault as ``user_id``.

        :param db_session: Open SQLAlchemy session.
        :param user_id: The signed-in user.
        :param secret_ref: The secret's reference.

        :returns: The secret value as text.

        :raises RepositoryCredentialError: with a message for the user
            when the secret does not exist, is not readable by the user,
            has expired, or cannot be decrypted.
    """
    from ccai.pychestrate.core.managers.repository_manager import (  # noqa: E402
        RepositoryCredentialError,
    )
    from ccai.pychestrate.webservice.secrets import secrets_service  # noqa: E402
    from ccai.pychestrate.webservice.secrets.exceptions import (  # noqa: E402
        SecretAccessDeniedError,
        SecretNotFoundError,
        SecretVersionExpiredError,
    )
    from ccai.pychestrate.webservice.secrets.secrets_aspects import (  # noqa: E402
        build_default_aspects,
    )

    reference = str(secret_ref or "").strip()
    try:
        read = secrets_service.read_secret(
            db_session=db_session,
            principal=_principal_for(user_id=user_id),
            secret_ref=reference,
            aspects=build_default_aspects(),
        )
    except SecretNotFoundError:
        raise RepositoryCredentialError(
            "There is no secret named {} in the secrets vault (System > Secrets).".format(reference)
        ) from None
    except SecretAccessDeniedError:
        raise RepositoryCredentialError(
            "You do not have access to the secret {} in System > Secrets. Ask "
            "an administrator for access to it.".format(reference)
        ) from None
    except SecretVersionExpiredError:
        raise RepositoryCredentialError(
            "The secret {} has expired. Rotate it in System > Secrets.".format(reference)
        ) from None
    except Exception:
        _module_logger.exception(
            "pychestrate.repository.credential_read_failed secret_ref=%s", reference
        )
        raise RepositoryCredentialError(
            "The secret {} could not be read. An administrator can find the "
            "details in the server log.".format(reference)
        ) from None

    try:
        rtnval = read.plaintext.reveal().decode("utf-8")
    except UnicodeDecodeError:
        raise RepositoryCredentialError(
            "The secret {} is not text, so it cannot be used as a repository "
            "credential.".format(reference)
        ) from None
    finally:
        try:
            read.plaintext.close()
        except Exception:
            pass
    return rtnval


def build_credential_resolver(*, db_session: Any, user_id: Any) -> Callable[[str], str]:
    """
        The ``credential_resolver`` :class:`RepositoryManager` takes, for
        the signed-in user.

        :param db_session: Open SQLAlchemy session.
        :param user_id: The signed-in user.

        :returns: ``(secret_ref) -> str``.
    """
    def _resolve(secret_ref: str) -> str:
        rtnval = read_repository_secret(
            db_session=db_session, user_id=user_id, secret_ref=secret_ref,
        )
        return rtnval

    return _resolve


def check_credential_reference(*, db_session: Any, user_id: Any, secret_ref: str) -> None:
    """
        Refuse a credential reference the user could not use: the secret
        must exist and the user must be able to read it. The value read
        is discarded at once.

        :param db_session: Open SQLAlchemy session.
        :param user_id: The signed-in user.
        :param secret_ref: The reference typed into the form.

        :raises RepositoryCredentialError: when the reference is unusable.
    """
    read_repository_secret(db_session=db_session, user_id=user_id, secret_ref=secret_ref)
    return


def list_readable_secret_refs(*, db_session: Any, user_id: Any) -> List[str]:
    """
        Secret references to suggest in the repository forms: the ORG
        secrets when the user may read them, and the user's own
        personal secrets. Metadata only -- no value is read. Any failure
        yields an empty list (the field still accepts a typed reference,
        which is checked on save).

        :param db_session: Open SQLAlchemy session.
        :param user_id: The signed-in user.

        :returns: Sorted secret references.
    """
    try:
        from ccai.pychestrate.webservice.secrets.models import (  # noqa: E402
            SecretRecord,
            SecretScopeKind,
        )
        from ccai.pychestrate.webservice.security.rbac import rbac_evaluator  # noqa: E402

        principal = _principal_for(user_id=user_id)
        now = datetime.now(timezone.utc)

        def _holds(key: str) -> bool:
            decision = rbac_evaluator.check_permission(
                db_session=db_session, principal=principal, permission_key=key, now=now,
            )
            return decision.allowed is True

        is_admin = _holds("system:secrets.admin")
        can_read_org = is_admin or _holds("system:secrets.read")

        refs: List[str] = []
        for record in db_session.query(SecretRecord).order_by(SecretRecord.secret_ref.asc()).all():
            if is_admin is True:
                refs.append(record.secret_ref)
            elif record.scope_kind == SecretScopeKind.ORG and can_read_org is True:
                refs.append(record.secret_ref)
            elif record.scope_kind == SecretScopeKind.USER and str(record.scope_ref) == str(user_id):
                refs.append(record.secret_ref)
            if len(refs) >= SECRET_PICKER_LIMIT:
                break
        rtnval = refs
    except Exception:
        _module_logger.exception("pychestrate.repository.secret_picker_failed")
        rtnval = []
    return rtnval


__all__ = [
    "SECRET_PICKER_LIMIT",
    "read_repository_secret",
    "build_credential_resolver",
    "check_credential_reference",
    "list_readable_secret_refs",
]
