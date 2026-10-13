"""
.. module:: webinterface.foundation.permission_presentation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Permission keys grouped and worded for people (ADM-06).

.. moduleauthor:: Code Craft AI LLC

Building a role meant picking from 73 raw permission keys in one scroll box,
52 of them described as "... via the REST surface". This module groups the
keys by product area ("Builds", "Resource pools"), gives each area and action
a plain name, and cleans the descriptions of the implementation wording, so the
role forms can show a short filterable list of areas with "Read", "Write" and
"Administer" under each. It changes only how keys are shown: the checkbox value
is still the canonical key.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from functools import lru_cache
from typing import Any, Dict, List, Tuple


#: Plain names for the area part of a key (``system:<area>.<action>``).
AREA_LABELS: Dict[str, str] = {
    "users": "Users",
    "groups": "Groups",
    "rbac": "Roles and access",
    "secrets": "Secrets",
    "project_secrets": "Project secrets",
    "audit": "Audit log",
    "flags": "Feature flags",
    "directory": "User directory",
    "auth": "Sign-in and sessions",
    "resources": "Resources",
    "resource_pools": "Resource pools",
    "ui": "Interface",
    "runs": "Runs",
    "test_catalog": "Test catalog",
    "test_runs": "Test runs",
    "builds": "Builds",
    "rpa": "RPA",
    "pipelines": "Pipelines",
    "pipeline_runs": "Pipeline runs",
    "source_integrations": "Source integrations",
    "environments": "Environments",
    "provisioning": "Provisioning",
    "drift": "Drift checks",
    "projects": "Projects",
    "metrics": "Metrics",
    "dashboards": "Dashboards",
    "metric_alerts": "Alert rules",
    "pods": "Pods",
    "clients": "Clients",
    "webhooks": "Webhooks",
    "embed": "Embeddable views",
    "plugin_api": "Plugin API",
    "guards": "Blast-radius guards",
    "slos": "SLOs",
    "release_channels": "Release channels",
    "release_templates": "Release templates",
    "backups": "Backups",
}

#: Plain names for the action part of a key.
ACTION_LABELS: Dict[str, str] = {
    "read": "View",
    "write": "Change",
    "admin": "Administer",
    "manage": "Manage",
    "create": "Start",
    "cancel": "Cancel",
    "run": "Run",
    "check": "Run checks",
    "sign": "Sign links",
    "sync": "Sync",
    "view": "See in the menu",
    "access": "Use the area",
}

#: The order actions are shown in within an area; anything else follows alphabetically.
ACTION_ORDER: Tuple[str, ...] = ("read", "access", "view", "create", "run", "check", "write", "cancel", "sign", "sync", "manage", "admin")

_REST_SURFACE = re.compile(r"\s*\(?\bvia the REST surface\)?", re.IGNORECASE)


def humanize(token: str) -> str:
    """
        ``resource_pools`` -> ``Resource pools``.

        :param token: A snake-case name.

        :returns: Sentence-case text.
    """
    text = token.replace("_", " ").replace(".", " ").strip()
    rtnval = text[:1].upper() + text[1:]
    return rtnval


def plain_description(text: str) -> str:
    """
        A catalog description without the implementation wording.

        :param text: The description as the catalog states it.

        :returns: The text a person should read.
    """
    rtnval = _REST_SURFACE.sub("", text or "").strip()
    return rtnval


def split_key(key: str) -> Tuple[str, str, str]:
    """
        ``system:projects.members.manage`` -> ``("system", "projects", "members.manage")``.

        :param key: A canonical permission key.

        :returns: (scope prefix, area, action).
    """
    prefix, _, rest = key.partition(":")
    if len(rest) == 0:
        prefix, rest = "", key
    area, _, action = rest.partition(".")
    return prefix, area, action


def area_label(prefix: str, area: str) -> str:
    """
        The name of an area; a key outside the ``system:`` scope is named with its scope.

        :param prefix: The key's scope prefix.
        :param area: The area token.

        :returns: The heading for the area.
    """
    label = AREA_LABELS.get(area, humanize(area))
    if len(prefix) > 0 and prefix != "system":
        label = "{} · {}".format(humanize(prefix), label)
    return label


def action_label(action: str) -> str:
    """
        The name of an action (``members.manage`` -> ``Members · manage``).

        :param action: The action part of a key.

        :returns: Text for the checkbox.
    """
    if action in ACTION_LABELS:
        return ACTION_LABELS[action]
    if len(action) == 0:
        return "Allow"
    parts = action.split(".")
    tail = ACTION_LABELS.get(parts[-1], parts[-1].replace("_", " "))
    if len(parts) == 1:
        return humanize(tail)
    return "{} · {}".format(humanize(".".join(parts[:-1])), tail.lower())


def _action_rank(action: str) -> Tuple[int, str]:
    tail = action.split(".")[-1]
    rank = ACTION_ORDER.index(tail) if tail in ACTION_ORDER else len(ACTION_ORDER)
    return (rank, action)


def _permission_phrase(key: str) -> str:
    """A permission named the way the picker shows it: ``Interface › Admin · view``."""
    prefix, area, action = split_key(key)
    return "{} › {}".format(area_label(prefix, area), action_label(action))


@lru_cache(maxsize=1)
def menu_requirements() -> Dict[str, Any]:
    """
        What the navigation menu asks of a role, beyond the one permission a person ticks.

        A menu entry is shown only to someone who holds *every* key it needs: its own, and its group's
        (the whole Admin menu needs ``system:ui.admin.view``). A role that holds only one of them gets no
        entry and no message saying why, so the picker says it next to each permission involved.

        :returns: ``{"entries": {key: [(entry label, [other keys needed with it])]}, "groups": {key: group
                  label}}``; ``entries`` lists only entries that need more than one key, ``groups`` the
                  group-level keys.
    """
    from ccai.pychestrate.webservice.webinterface.site_shell import nav_manifest  # noqa: E402

    groups = {group.group_id: group for group in nav_manifest.NAV_GROUPS}
    entries: Dict[str, List[Tuple[str, List[str]]]] = {}
    group_keys: Dict[str, str] = {}
    for entry in nav_manifest.NAV_ENTRIES:
        group = groups.get(entry.group_id)
        needed: List[str] = []
        for key in list(entry.required_permissions) + (list(group.required_permissions) if group is not None else []):
            if key not in needed:
                needed.append(key)
        if len(needed) < 2:
            continue
        label = entry.label.replace(nav_manifest.PREVIEW_LABEL_SUFFIX, "")
        for key in needed:
            entries.setdefault(key, []).append((label, [other for other in needed if other != key]))
        if group is not None:
            for key in group.required_permissions:
                group_keys[key] = group.label
    return {"entries": entries, "groups": group_keys}


def menu_hint(key: str) -> str:
    """
        The sentence the role picker shows under a permission that a menu entry needs together with others.

        :param key: A canonical permission key.

        :returns: The hint, or ``""`` when no menu entry needs this key together with another.
    """
    requirements = menu_requirements()
    if key in requirements["groups"]:
        return "Shows the {} menu. Each entry in it also needs its own permission.".format(requirements["groups"][key])
    sentences: List[str] = []
    by_others: Dict[Tuple[str, ...], List[str]] = {}
    for label, others in requirements["entries"].get(key, []):
        by_others.setdefault(tuple(others), []).append(label)
    for others, labels in by_others.items():
        sentences.append("In the menu, {} also needs {}.".format(
            " and ".join(labels), " and ".join(_permission_phrase(other) for other in others),
        ))
    return " ".join(sentences)


def group_permissions(permissions: Any) -> List[Dict[str, Any]]:
    """
        Group permission entries by area for the role forms.

        Each entry needs ``name`` (the canonical key) and may have
        ``description``. The result is sorted by area name; within an area,
        view before change before administer.

        :param permissions: Iterable of permission entries.

        :returns: ``[{"area": <group key>, "label": <heading>, "items": [
                  {"permission": <entry>, "label": <checkbox text>,
                  "description": <plain description>, "menu_hint": <what the menu also needs, or "">}]}]``.
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for permission in permissions or []:
        key = str(getattr(permission, "name", "") or getattr(permission, "id", ""))
        prefix, area, action = split_key(key)
        group_key = "{}:{}".format(prefix, area)
        group = groups.get(group_key)
        if group is None:
            group = {"area": group_key, "label": area_label(prefix, area), "items": [], "_actions": []}
            groups[group_key] = group
        group["items"].append({
            "permission": permission,
            "label": action_label(action),
            "description": plain_description(str(getattr(permission, "description", "") or "")),
            "menu_hint": menu_hint(key),
            "_action": action,
        })
    rtnval = sorted(groups.values(), key=lambda entry: entry["label"].lower())
    for group in rtnval:
        group["items"].sort(key=lambda item: _action_rank(item["_action"]))
    return rtnval


__all__ = [
    "ACTION_LABELS",
    "AREA_LABELS",
    "action_label",
    "area_label",
    "group_permissions",
    "humanize",
    "menu_hint",
    "menu_requirements",
    "plain_description",
    "split_key",
]
