"""
.. module:: security.auth.provider_directory
    :synopsis: Unified directory of selectable credential modes.

A "credential mode" is a (kind, provider_name) tuple the
operator has wired up — e.g. ``(OIDC, "okta")``,
``(SAML, "auth0-saml")``, ``(LOCAL, "local")``. The
:mod:`oidc.provider_registry` and
:mod:`saml.provider_registry` modules ship the per-IdP
configuration (endpoints, fetchers, signature verifiers);
this directory layers a thin metadata sheet (display label,
enabled flag, login URL path) on top so the login picker
and the admin toggle endpoints can present a single
ordered list to the UI without each caller having to walk
two registries plus the LOCAL provider.

The directory is intentionally *separate* from the OIDC /
SAML configs so the existing
:class:`OidcProviderConfig` / :class:`SamlProviderConfig`
shapes stay backwards-compatible. A directory entry
referencing a kind/provider_name that has no backing config
is filtered out of :func:`list_credential_modes` so the
picker can never advertise a half-shaped provider.

LOCAL has no per-IdP configuration object, so the
:func:`register_credential_mode` call against the LOCAL
kind doubles as the registration of the local fallback —
an operator who never registers a LOCAL entry simply has
no local-fallback button on the login picker.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)
from automojo.pychestrate.webservice.security.auth.oidc import (
    provider_registry as oidc_provider_registry,
)
from automojo.pychestrate.webservice.security.auth.saml import (
    provider_registry as saml_provider_registry,
)


# Per-kind feature-flag keys consulted by *_with_flags
# helpers. Each defaults to True when the flag is not yet
# created, so an operator who hasn't seeded any rows still
# gets the directory's in-memory enabled flag honored.
KIND_FEATURE_FLAG_KEYS: Dict[AuthProviderKind, str] = {
    AuthProviderKind.OIDC: "auth.oidc_enabled",
    AuthProviderKind.SAML: "auth.saml_enabled",
    AuthProviderKind.LOCAL: "auth.local_fallback_enabled",
}


@dataclass(frozen=True)
class CredentialModeView:
    """
        Caller-facing view of a single registered credential
        mode the login picker renders.

        :param kind: ``OIDC | SAML | LOCAL``.
        :param provider_name: Stable name (matches the URL
                              segment in
                              ``/auth/{kind}/{provider_name}/...``);
                              ``"local"`` for LOCAL.
        :param display_label: Human-facing label the picker
                              renders.
        :param enabled: ``True`` when the mode is selectable;
                        a disabled mode stays registered (so
                        the controller routes are reachable
                        for diagnostics) but is filtered out
                        of :func:`list_enabled_credential_modes`.
        :param login_path: URL path the picker submits to —
                           ``"/auth/oidc/{provider_name}/login"``
                           or ``"/auth/saml/{provider_name}/login"``
                           or ``"/api/v1/auth/local/login"``.
    """
    kind: AuthProviderKind
    provider_name: str
    display_label: str
    enabled: bool
    login_path: str


@dataclass
class _CredentialModeEntry:
    """
        Mutable in-process record (``enabled`` flips at
        runtime via :func:`set_enabled`).
    """
    kind: AuthProviderKind
    provider_name: str
    display_label: str
    enabled: bool
    login_path: str


_GUARD: threading.RLock = threading.RLock()
_DIRECTORY: Dict[Tuple[AuthProviderKind, str], _CredentialModeEntry] = {}


def register_credential_mode(
        *,
        kind: AuthProviderKind,
        provider_name: str,
        display_label: str,
        enabled: bool = True,
        login_path: Optional[str] = None
    ) -> CredentialModeView:
    """
        Add a credential mode to the directory. ``login_path``
        defaults to the canonical
        ``/auth/{kind_lower}/{provider_name}/login`` for OIDC
        / SAML and ``/api/v1/auth/local/login`` for LOCAL.

        :raises: ValueError on missing inputs or duplicate
                 ``(kind, provider_name)`` registration.
    """
    if kind is None:
        err_lines = ["register_credential_mode requires a kind."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if provider_name is None or len(provider_name) == 0:
        err_lines = [
            "register_credential_mode requires a non-empty provider_name.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if display_label is None or len(display_label) == 0:
        err_lines = [
            "register_credential_mode requires a non-empty display_label.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    materialized_path = (
        login_path if login_path is not None and len(login_path) > 0
        else _default_login_path(
            kind=kind, provider_name=provider_name,
        )
    )

    key = (kind, provider_name)
    with _GUARD:
        if key in _DIRECTORY:
            err_lines = [
                "Credential mode is already registered.",
                "KIND: {}".format(kind.value),
                "PROVIDER_NAME: {}".format(provider_name),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        entry = _CredentialModeEntry(
            kind=kind,
            provider_name=provider_name,
            display_label=display_label,
            enabled=bool(enabled),
            login_path=materialized_path,
        )
        _DIRECTORY[key] = entry
    rtnval = _entry_to_view(entry=entry)
    return rtnval


def unregister_credential_mode(
        *,
        kind: AuthProviderKind,
        provider_name: str
    ) -> bool:
    """
        Drop the directory entry. Returns ``True`` when an
        entry was removed, ``False`` when none existed.
    """
    key = (kind, provider_name)
    with _GUARD:
        if key not in _DIRECTORY:
            return False
        del _DIRECTORY[key]
    return True


def set_enabled(
        *,
        kind: AuthProviderKind,
        provider_name: str,
        enabled: bool
    ) -> CredentialModeView:
    """
        Hot-flip the ``enabled`` flag on a registered mode
        without re-registering. Used by the admin REST
        toggle and tests.

        :raises: KeyError when the mode is not registered.
    """
    key = (kind, provider_name)
    with _GUARD:
        entry = _DIRECTORY.get(key)
        if entry is None:
            err_lines = [
                "Credential mode is not registered.",
                "KIND: {}".format(kind.value),
                "PROVIDER_NAME: {}".format(provider_name),
            ]
            err_msg = os.linesep.join(err_lines)
            raise KeyError(err_msg) from None
        entry.enabled = bool(enabled)
        rtnval = _entry_to_view(entry=entry)
    return rtnval


def is_enabled(
        *,
        kind: AuthProviderKind,
        provider_name: str
    ) -> bool:
    """
        Return ``True`` when the mode is registered AND
        enabled AND has a backing OIDC / SAML provider config
        (LOCAL needs no backing config).
    """
    key = (kind, provider_name)
    with _GUARD:
        entry = _DIRECTORY.get(key)
    if entry is None:
        return False
    if entry.enabled is False:
        return False
    if _has_backing_config(entry=entry) is False:
        return False
    return True


def list_credential_modes() -> List[CredentialModeView]:
    """
        Snapshot every registered mode (enabled or not),
        filtered down to the entries that have a backing
        config. Sorted by ``(kind, provider_name)``.
    """
    with _GUARD:
        snapshot = list(_DIRECTORY.values())
    matched: List[CredentialModeView] = []
    for entry in snapshot:
        if _has_backing_config(entry=entry) is False:
            continue
        matched.append(_entry_to_view(entry=entry))
    matched.sort(key=lambda v: (v.kind.value, v.provider_name))
    rtnval = matched
    return rtnval


def list_enabled_credential_modes() -> List[CredentialModeView]:
    """
        Snapshot of every enabled mode that has a backing
        config — exactly what the login picker renders.
    """
    rtnval = [v for v in list_credential_modes() if v.enabled is True]
    return rtnval


def reset_for_testing() -> None:
    """
        Clear the directory. Test-only seam.
    """
    with _GUARD:
        _DIRECTORY.clear()
    return


def is_enabled_with_flags(
        *,
        kind: AuthProviderKind,
        provider_name: str,
        db_session: DbSession,
        bucketing_key: str = "anonymous"
    ) -> bool:
    """
        Combined check: directory ``enabled`` flag AND the
        kind-level feature flag (``auth.oidc_enabled`` /
        ``auth.saml_enabled`` / ``auth.local_fallback_enabled``).

        :param db_session: Active SQLAlchemy session used to
                           consult the feature-flag store.
        :param bucketing_key: Optional rollout bucket — for
                              the picker the
                              ``"anonymous"`` default is
                              correct because the user
                              hasn't authenticated yet.

        :returns: ``True`` only when both the directory and
                  the feature flag agree.
    """
    if is_enabled(kind=kind, provider_name=provider_name) is False:
        return False
    flag_key = KIND_FEATURE_FLAG_KEYS.get(kind)
    if flag_key is None:
        return True
    rtnval = _evaluate_flag(
        db_session=db_session,
        flag_key=flag_key,
        bucketing_key=bucketing_key,
    )
    return rtnval


def list_enabled_credential_modes_with_flags(
        *,
        db_session: DbSession,
        bucketing_key: str = "anonymous"
    ) -> List[CredentialModeView]:
    """
        Snapshot of every enabled mode that has a backing
        config AND whose kind-level feature flag is on. This
        is what the picker endpoint returns when a request-
        scoped DB session is available.
    """
    matched: List[CredentialModeView] = []
    for view in list_enabled_credential_modes():
        flag_key = KIND_FEATURE_FLAG_KEYS.get(view.kind)
        if flag_key is None:
            matched.append(view)
            continue
        if _evaluate_flag(
            db_session=db_session,
            flag_key=flag_key,
            bucketing_key=bucketing_key,
        ) is True:
            matched.append(view)
    rtnval = matched
    return rtnval


def _evaluate_flag(
        *,
        db_session: DbSession,
        flag_key: str,
        bucketing_key: str
    ) -> bool:
    """
        Read a feature flag value with a ``True`` default so
        the picker honors the directory in deployments that
        haven't seeded any auth feature flags.
    """
    # Imported lazily so the directory module doesn't drag
    # the feature-flag stack onto callers that never use the
    # *_with_flags helpers.
    from automojo.pychestrate.webservice.identity.flags.flag_evaluator import (
        evaluate_boolean,
    )
    from automojo.pychestrate.webservice.identity.flags.models import (
        FlagContext,
    )

    context = FlagContext(
        bucketing_key=bucketing_key,
        user_id=None,
        project_id=None,
    )
    rtnval = evaluate_boolean(
        db_session=db_session,
        flag_key=flag_key,
        context=context,
        default=True,
    )
    return rtnval


def _default_login_path(
        *,
        kind: AuthProviderKind,
        provider_name: str
    ) -> str:
    if kind == AuthProviderKind.LOCAL:
        rtnval = "/api/v1/auth/local/login"
        return rtnval
    if kind == AuthProviderKind.OIDC:
        rtnval = "/auth/oidc/{}/login".format(provider_name)
        return rtnval
    if kind == AuthProviderKind.SAML:
        rtnval = "/auth/saml/{}/login".format(provider_name)
        return rtnval
    err_lines = ["Unrecognized AuthProviderKind for default login path."]
    err_lines.append("KIND: {!r}".format(kind))
    err_msg = os.linesep.join(err_lines)
    raise ValueError(err_msg) from None


def _has_backing_config(*, entry: _CredentialModeEntry) -> bool:
    """
        Cross-reference the entry against the kind-specific
        provider registry so a directory row referencing a
        config that has been unregistered is filtered out.
        LOCAL has no backing config and always passes.
    """
    if entry.kind == AuthProviderKind.LOCAL:
        return True
    if entry.kind == AuthProviderKind.OIDC:
        try:
            oidc_provider_registry.get_oidc_provider_config(
                provider_name=entry.provider_name,
            )
        except (KeyError, ValueError):
            return False
        return True
    if entry.kind == AuthProviderKind.SAML:
        try:
            saml_provider_registry.get_saml_provider_config(
                provider_name=entry.provider_name,
            )
        except (KeyError, ValueError):
            return False
        return True
    return False


def _entry_to_view(*, entry: _CredentialModeEntry) -> CredentialModeView:
    rtnval = CredentialModeView(
        kind=entry.kind,
        provider_name=entry.provider_name,
        display_label=entry.display_label,
        enabled=entry.enabled,
        login_path=entry.login_path,
    )
    return rtnval
