"""
.. module:: webinterface.site_shell.ui_profile
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 9-ui-profiles -- configurable automation surfaces.

.. moduleauthor:: Code Craft AI LLC

A **surface** is a named slice of the UI (navigation entries, project
sub-nav tabs, dashboard tiles, palette providers) that can be shown or
hidden as a unit: Build Automation, Testing Automation, Robotic Process
Automation, and Infrastructure. Entries without a surface tag are
*core* and always shown.

The deployment default lives in the SYSTEM-scope global variable
:data:`DEPLOYMENT_VARIABLE_NAME` (a JSON list of surface values); an
absent or unparseable value means "every surface". M2 adds the
per-user override; the resolution helpers already take the
``override`` argument so the shape does not change.

Surfaces gate presentation only. Hidden routes stay reachable by URL
and stay governed by RBAC.

Request scoping: the shell wrappers resolve the profile once per
request and publish it on a :class:`contextvars.ContextVar`; the
jinja global ``ui_profile`` is a proxy that reads that variable, so
fragments (the project sub-nav, for example) can branch on
``ui_profile.is_enabled('build')`` without every handler threading
the profile through its context.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import contextlib
import contextvars
import enum
import json
import logging
import time

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, Iterator, List, Optional, Sequence, Tuple


_LOGGER = logging.getLogger("pychestrate.ui_profile")

# Import for the side effect of attaching the preference table to the
# shared metadata (tests create_all against it).
from ccai.pychestrate.webservice.webinterface.site_shell.preferences_models import (  # noqa: E402
    PREFERENCE_KEY_UI_SURFACES,
    UserPreference,
)


class UiSurface(str, enum.Enum):
    """
        The fixed surface vocabulary.
    """
    BUILD = "build"
    TESTING = "testing"
    RPA = "rpa"
    INFRA = "infra"


#: Display order for forms and lists.
SURFACE_ORDER: Tuple[UiSurface, ...] = (
    UiSurface.BUILD,
    UiSurface.TESTING,
    UiSurface.RPA,
    UiSurface.INFRA,
)

SURFACE_DISPLAY: Dict[UiSurface, str] = {
    UiSurface.BUILD: "Build Automation",
    UiSurface.TESTING: "Testing Automation",
    UiSurface.RPA: "Robotic Process Automation",
    UiSurface.INFRA: "Infrastructure",
}

SURFACE_DESCRIPTIONS: Dict[UiSurface, str] = {
    UiSurface.BUILD: (
        "Builds and pipelines: compiling and packaging software from"
        " source."
    ),
    UiSurface.TESTING: (
        "Test runs, the test catalog, and test metrics: executing and"
        " analysing automated tests."
    ),
    UiSurface.RPA: (
        "RPA specifications and jobs: versioned automations that process"
        " a work packet on a pod."
    ),
    UiSurface.INFRA: (
        "Environments, provisioning runs, and blast-radius guards:"
        " infrastructure-as-code orchestration."
    ),
}

ALL_SURFACES: FrozenSet[UiSurface] = frozenset(SURFACE_ORDER)
ALL_SURFACE_VALUES: Tuple[str, ...] = tuple(s.value for s in SURFACE_ORDER)

#: SYSTEM-scope global variable holding the deployment profile.
DEPLOYMENT_VARIABLE_NAME: str = "ui.profile.surfaces"

#: Bus topic emitted when the deployment profile changes.
DEPLOYMENT_CHANGED_TOPIC: str = "entity.ui_profile.deployment_changed"

#: Seconds the deployment profile is cached in-process between reads.
DEPLOYMENT_CACHE_TTL_SECONDS: float = 2.0


@dataclass(frozen=True)
class UiProfile:
    """
        The resolved profile for one request.

        :param deployment_surfaces: What the deployment allows.
        :param override_surfaces: The user's own selection, or ``None``.
        :param effective_surfaces: ``override ∩ deployment`` when that
                                   is non-empty, else the deployment set.
        :param override_reset: True when a non-empty override collapsed
                               to nothing and the deployment set was used.
    """
    deployment_surfaces: FrozenSet[UiSurface]
    override_surfaces: Optional[FrozenSet[UiSurface]]
    effective_surfaces: FrozenSet[UiSurface]
    override_reset: bool = False

    @property
    def effective_values(self) -> List[str]:
        """
            Effective surfaces as sorted value strings, display order.
        """
        rtnval = [s.value for s in SURFACE_ORDER if s in self.effective_surfaces]
        return rtnval

    @property
    def deployment_values(self) -> List[str]:
        rtnval = [s.value for s in SURFACE_ORDER if s in self.deployment_surfaces]
        return rtnval

    @property
    def override_values(self) -> Optional[List[str]]:
        if self.override_surfaces is None:
            return None
        rtnval = [s.value for s in SURFACE_ORDER if s in self.override_surfaces]
        return rtnval

    @property
    def hidden_values(self) -> List[str]:
        rtnval = [s.value for s in SURFACE_ORDER if s not in self.effective_surfaces]
        return rtnval

    def is_enabled(self, surface: Any) -> bool:
        """
            Whether ``surface`` (a :class:`UiSurface` or its value) is
            in the effective set. Unknown values are treated as core
            (always enabled) so a typo never hides a page.
        """
        try:
            member = surface if isinstance(surface, UiSurface) else UiSurface(str(surface))
        except ValueError:
            return True
        rtnval = member in self.effective_surfaces
        return rtnval

    def any_enabled(self, surfaces: Iterable[Any]) -> bool:
        """
            Whether any of ``surfaces`` is enabled. An empty
            collection means core and is always enabled.
        """
        listed = list(surfaces or [])
        if len(listed) == 0:
            return True
        for candidate in listed:
            if self.is_enabled(candidate):
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        rtnval: Dict[str, Any] = {
            "deployment_surfaces": self.deployment_values,
            "effective_surfaces": self.effective_values,
            "override_surfaces": self.override_values,
            "override_reset": self.override_reset,
            "surfaces": [
                {
                    "surface": s.value,
                    "label": SURFACE_DISPLAY[s],
                    "description": SURFACE_DESCRIPTIONS[s],
                    "enabled": s in self.effective_surfaces,
                    "allowed": s in self.deployment_surfaces,
                }
                for s in SURFACE_ORDER
            ],
        }
        return rtnval


DEFAULT_PROFILE = UiProfile(
    deployment_surfaces=ALL_SURFACES,
    override_surfaces=None,
    effective_surfaces=ALL_SURFACES,
    override_reset=False,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def parse_surfaces(value: Any) -> Tuple[Optional[FrozenSet[UiSurface]], List[str]]:
    """
        Parse a surface list from a JSON string, a list of strings, or
        a comma-separated string.

        :returns: ``(surfaces, issues)``. ``surfaces`` is ``None`` when
                  the value could not be parsed at all; ``issues`` lists
                  unknown names and structural problems.
    """
    issues: List[str] = []
    raw = value
    if raw is None:
        return (None, ["no value"])
    if isinstance(raw, str):
        text = raw.strip()
        if len(text) == 0:
            return (None, ["empty value"])
        if text.startswith("["):
            try:
                raw = json.loads(text)
            except ValueError as xcpt:
                return (None, ["not valid JSON: {}".format(xcpt)])
        else:
            raw = [part.strip() for part in text.split(",") if len(part.strip()) > 0]
    if isinstance(raw, (set, frozenset, tuple)):
        raw = list(raw)
    if not isinstance(raw, list):
        return (None, ["expected a list of surface names"])
    members: List[UiSurface] = []
    for item in raw:
        name = str(getattr(item, "value", item)).strip().lower()
        try:
            member = UiSurface(name)
        except ValueError:
            issues.append("unknown surface '{}'".format(name))
            continue
        if member not in members:
            members.append(member)
    rtnval: Tuple[Optional[FrozenSet[UiSurface]], List[str]] = (frozenset(members), issues)
    return rtnval


def compute_effective(
        *,
        deployment: FrozenSet[UiSurface],
        override: Optional[FrozenSet[UiSurface]]
    ) -> Tuple[FrozenSet[UiSurface], bool]:
    """
        ``override ∩ deployment`` when non-empty, else ``deployment``.

        :returns: ``(effective, override_reset)``.
    """
    allowed = frozenset(deployment) if len(deployment) > 0 else ALL_SURFACES
    if override is None:
        return (allowed, False)
    intersection = frozenset(override) & allowed
    if len(intersection) == 0:
        return (allowed, True)
    return (intersection, False)


def build_profile(
        *,
        deployment: FrozenSet[UiSurface],
        override: Optional[FrozenSet[UiSurface]] = None
    ) -> UiProfile:
    effective, reset = compute_effective(deployment=deployment, override=override)
    rtnval = UiProfile(
        deployment_surfaces=frozenset(deployment) if len(deployment) > 0 else ALL_SURFACES,
        override_surfaces=frozenset(override) if override is not None else None,
        effective_surfaces=effective,
        override_reset=reset,
    )
    return rtnval


def filter_by_surface(items: Sequence[Any], *, enabled: Iterable[Any], attribute: str = "surfaces") -> List[Any]:
    """
        Keep the items whose ``attribute`` (a collection of surface
        values; empty means core) intersects ``enabled``.
    """
    enabled_values = set()
    for candidate in enabled:
        enabled_values.add(str(getattr(candidate, "value", candidate)))
    rtnval: List[Any] = []
    for item in items:
        tags = getattr(item, attribute, ()) or ()
        if isinstance(tags, str):
            tags = (tags,)
        tag_values = [str(getattr(t, "value", t)) for t in tags]
        if len(tag_values) == 0 or any(t in enabled_values for t in tag_values):
            rtnval.append(item)
    return rtnval


def validate_surface_tags(tags: Iterable[Any]) -> List[str]:
    """
        Return the unknown surface names among ``tags``.
    """
    unknown: List[str] = []
    for tag in tags:
        name = str(getattr(tag, "value", tag))
        try:
            UiSurface(name)
        except ValueError:
            unknown.append(name)
    return unknown


# ---------------------------------------------------------------------------
# Deployment profile persistence (SYSTEM global variable)
# ---------------------------------------------------------------------------


_DEPLOYMENT_CACHE: Dict[str, Any] = {"surfaces": None, "expires_at": 0.0}


def invalidate_deployment_cache() -> None:
    """
        Drop the cached deployment surfaces so the next read hits the
        variable store.
    """
    _DEPLOYMENT_CACHE["surfaces"] = None
    _DEPLOYMENT_CACHE["expires_at"] = 0.0
    return


def _read_deployment_variable(*, db_session: Any) -> Any:
    from ccai.pychestrate.webservice.variables.system_store import (  # noqa: E402
        SystemVariableStore,
    )
    store = SystemVariableStore(db_session)
    rtnval = store.get_value(DEPLOYMENT_VARIABLE_NAME, None)
    return rtnval


def resolve_deployment_surfaces(*, db_session: Any, use_cache: bool = True) -> FrozenSet[UiSurface]:
    """
        The deployment's allowed surfaces. Falls back to every surface
        (with a warning) when the variable is absent or unparseable.
    """
    now = time.monotonic()
    cached = _DEPLOYMENT_CACHE.get("surfaces", None)
    if use_cache and cached is not None and now < float(_DEPLOYMENT_CACHE.get("expires_at", 0.0)):
        return cached

    surfaces = ALL_SURFACES
    try:
        raw = _read_deployment_variable(db_session=db_session)
    except Exception as xcpt:
        _LOGGER.warning(
            "pychestrate.ui_profile.deployment_read_failed variable=%s error=%s",
            DEPLOYMENT_VARIABLE_NAME, xcpt,
        )
        raw = None
    if raw is not None:
        parsed, issues = parse_surfaces(raw)
        if parsed is None or len(parsed) == 0:
            _LOGGER.warning(
                "pychestrate.ui_profile.deployment_invalid variable=%s issues=%s;"
                " falling back to every surface",
                DEPLOYMENT_VARIABLE_NAME, "; ".join(issues) or "empty list",
            )
        else:
            if len(issues) > 0:
                _LOGGER.warning(
                    "pychestrate.ui_profile.deployment_partial variable=%s issues=%s",
                    DEPLOYMENT_VARIABLE_NAME, "; ".join(issues),
                )
            surfaces = parsed

    _DEPLOYMENT_CACHE["surfaces"] = surfaces
    _DEPLOYMENT_CACHE["expires_at"] = now + DEPLOYMENT_CACHE_TTL_SECONDS
    return surfaces


def set_deployment_surfaces(*, db_session: Any, surfaces: Iterable[Any], actor_id: Optional[str] = None) -> FrozenSet[UiSurface]:
    """
        Persist the deployment profile. Creates the variable when it
        does not exist yet.

        :raises: ValueError on unknown names or an empty selection.
    """
    parsed, issues = parse_surfaces(list(surfaces))
    if parsed is None or len(issues) > 0:
        raise ValueError("Unknown surface(s): {}".format("; ".join(issues) or "none given"))
    if len(parsed) == 0:
        raise ValueError("At least one surface must stay enabled.")

    from ccai.pychestrate.webservice.variables.system_store import (  # noqa: E402
        SystemVariableCreateRequest,
        SystemVariableUpdateRequest,
    )
    from ccai.pychestrate.core.orm import VariableType  # noqa: E402
    from ccai.pychestrate.webservice.variables.system_store import SystemVariableStore  # noqa: E402

    value = [s.value for s in SURFACE_ORDER if s in parsed]
    store = SystemVariableStore(db_session)
    existing = store.get_variable(DEPLOYMENT_VARIABLE_NAME)
    if existing is None:
        store.create_variable(
            SystemVariableCreateRequest(
                name=DEPLOYMENT_VARIABLE_NAME,
                value=value,
                var_type=VariableType.JSON,
                description="UI profile: automation surfaces the deployment presents by default.",
                default_value=list(ALL_SURFACE_VALUES),
            ),
            user_id=actor_id,
        )
    else:
        store.update_variable(
            DEPLOYMENT_VARIABLE_NAME,
            SystemVariableUpdateRequest(value=value),
            user_id=actor_id,
        )
    invalidate_deployment_cache()
    _LOGGER.info(
        "pychestrate.ui_profile.deployment_changed surfaces=%s actor=%s", ",".join(value), actor_id,
    )
    try:
        from ccai.pychestrate.core.defaults import new_uuid  # noqa: E402
        from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent  # noqa: E402
        from ccai.pychestrate.webservice.messaging.outbox import enqueue_event  # noqa: E402
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=DEPLOYMENT_CHANGED_TOPIC,
                payload={"surfaces": value, "actor_id": actor_id},
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
    except Exception as xcpt:
        _LOGGER.debug("pychestrate.ui_profile.deployment_event_skipped error=%s", xcpt)
        try:
            db_session.rollback()
        except Exception:
            pass
    return parsed


def resolve_profile(*, db_session: Any, user_id: Optional[str] = None) -> UiProfile:
    """
        The effective profile for a request: the deployment default
        narrowed by the user's saved override when one exists.
    """
    deployment = resolve_deployment_surfaces(db_session=db_session)
    override = get_user_override(db_session=db_session, user_id=user_id)
    rtnval = build_profile(deployment=deployment, override=override)
    return rtnval


# ---------------------------------------------------------------------------
# Per-user override (ui_user_preference)
# ---------------------------------------------------------------------------


def get_user_override(*, db_session: Any, user_id: Optional[str]) -> Optional[FrozenSet[UiSurface]]:
    """
        The user's saved surface override, or ``None`` when absent or
        unparseable.
    """
    if user_id is None or len(str(user_id)) == 0:
        return None
    try:
        row = (
            db_session.query(UserPreference)
            .filter(UserPreference.user_id == str(user_id))
            .filter(UserPreference.key == PREFERENCE_KEY_UI_SURFACES)
            .first()
        )
    except Exception as xcpt:
        _LOGGER.debug("pychestrate.ui_profile.override_read_failed user=%s error=%s", user_id, xcpt)
        return None
    if row is None:
        return None
    value = row.value_json
    if isinstance(value, dict):
        value = value.get("surfaces", None)
    parsed, _issues = parse_surfaces(value)
    if parsed is None:
        return None
    rtnval = parsed
    return rtnval


def set_user_override(*, db_session: Any, user_id: str, surfaces: Iterable[Any]) -> FrozenSet[UiSurface]:
    """
        Save the user's surface override.

        :raises: ValueError on unknown names or an empty selection.
    """
    parsed, issues = parse_surfaces(list(surfaces))
    if parsed is None or len(issues) > 0:
        raise ValueError("Unknown surface(s): {}".format("; ".join(issues) or "none given"))
    if len(parsed) == 0:
        raise ValueError("Select at least one surface, or use the deployment default.")
    value = [s.value for s in SURFACE_ORDER if s in parsed]
    row = (
        db_session.query(UserPreference)
        .filter(UserPreference.user_id == str(user_id))
        .filter(UserPreference.key == PREFERENCE_KEY_UI_SURFACES)
        .first()
    )
    if row is None:
        row = UserPreference(user_id=str(user_id), key=PREFERENCE_KEY_UI_SURFACES, value_json={"surfaces": value})
        db_session.add(row)
    else:
        row.value_json = {"surfaces": value}
    from ccai.pychestrate.core.defaults import utc_now  # noqa: E402
    row.updated_at = utc_now()
    db_session.commit()
    return parsed


def clear_user_override(*, db_session: Any, user_id: str) -> bool:
    """
        Delete the user's override. Returns whether one existed.
    """
    row = (
        db_session.query(UserPreference)
        .filter(UserPreference.user_id == str(user_id))
        .filter(UserPreference.key == PREFERENCE_KEY_UI_SURFACES)
        .first()
    )
    if row is None:
        return False
    db_session.delete(row)
    db_session.commit()
    return True


def publish_user_profile(*, db_session: Any, user_id: Optional[str]) -> UiProfile:
    """
        Resolve the profile for ``user_id`` (deployment default plus the
        user's override) and publish it for the current request scope.
        Called by the consumer-UI auth resolver once the session is
        known; failures fall back to the deployment profile.
    """
    try:
        profile = resolve_profile(db_session=db_session, user_id=user_id)
    except Exception as xcpt:
        _LOGGER.debug("pychestrate.ui_profile.publish_failed user=%s error=%s", user_id, xcpt)
        profile = current_profile()
    set_current_profile(profile)
    return profile


# ---------------------------------------------------------------------------
# Request scoping + jinja global
# ---------------------------------------------------------------------------


_CURRENT_PROFILE: "contextvars.ContextVar[Optional[UiProfile]]" = contextvars.ContextVar(
    "pychestrate_ui_profile", default=None,
)


def current_profile() -> UiProfile:
    """
        The profile published for the current request, or
        :data:`DEFAULT_PROFILE` outside a request scope.
    """
    profile = _CURRENT_PROFILE.get()
    rtnval = profile if profile is not None else DEFAULT_PROFILE
    return rtnval


def set_current_profile(profile: Optional[UiProfile]) -> Any:
    """
        Publish ``profile`` for the current context. Returns the reset
        token.
    """
    rtnval = _CURRENT_PROFILE.set(profile)
    return rtnval


def reset_current_profile(token: Any) -> None:
    try:
        _CURRENT_PROFILE.reset(token)
    except (ValueError, RuntimeError):
        _CURRENT_PROFILE.set(None)
    return


def resolve_request_profile(*, user_id: Optional[str] = None) -> UiProfile:
    """
        Resolve the profile for the current request by opening a
        short-lived session from the runtime session factory. Any
        failure (no factory yet, DB error) yields the default profile
        so a page never fails because of a preference lookup.
    """
    try:
        from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS  # noqa: E402
        factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    except Exception:
        factory = None
    if factory is None:
        cached = _DEPLOYMENT_CACHE.get("surfaces", None)
        if cached is not None:
            rtnval = build_profile(deployment=cached, override=None)
            return rtnval
        return DEFAULT_PROFILE
    db_session = None
    try:
        db_session = factory()
        rtnval = resolve_profile(db_session=db_session, user_id=user_id)
    except Exception as xcpt:
        _LOGGER.debug("pychestrate.ui_profile.request_resolve_failed error=%s", xcpt)
        rtnval = DEFAULT_PROFILE
    finally:
        if db_session is not None:
            try:
                db_session.close()
            except Exception:
                pass
    return rtnval


@contextlib.contextmanager
def request_profile_scope(*, user_id: Optional[str] = None) -> Iterator[UiProfile]:
    """
        Resolve the request profile and publish it for the duration of
        the block.
    """
    profile = resolve_request_profile(user_id=user_id)
    token = set_current_profile(profile)
    try:
        yield profile
    finally:
        reset_current_profile(token)


class UiProfileProxy:
    """
        Jinja-facing proxy: attribute access is forwarded to the
        profile of the current request.
    """

    def __getattr__(self, name: str) -> Any:
        rtnval = getattr(current_profile(), name)
        return rtnval

    def __repr__(self) -> str:
        rtnval = "UiProfileProxy({})".format(current_profile().effective_values)
        return rtnval


def install_ui_profile_global(*, environment: Any) -> None:
    """
        Install the ``ui_profile`` global on a jinja environment.
    """
    environment.globals["ui_profile"] = UiProfileProxy()
    return


__all__ = [
    "UiSurface",
    "UiProfile",
    "SURFACE_ORDER",
    "SURFACE_DISPLAY",
    "SURFACE_DESCRIPTIONS",
    "ALL_SURFACES",
    "ALL_SURFACE_VALUES",
    "DEPLOYMENT_VARIABLE_NAME",
    "DEFAULT_PROFILE",
    "parse_surfaces",
    "compute_effective",
    "build_profile",
    "filter_by_surface",
    "validate_surface_tags",
    "invalidate_deployment_cache",
    "resolve_deployment_surfaces",
    "set_deployment_surfaces",
    "resolve_profile",
    "get_user_override",
    "set_user_override",
    "clear_user_override",
    "publish_user_profile",
    "PREFERENCE_KEY_UI_SURFACES",
    "UserPreference",
    "current_profile",
    "set_current_profile",
    "reset_current_profile",
    "resolve_request_profile",
    "request_profile_scope",
    "UiProfileProxy",
    "install_ui_profile_global",
]
