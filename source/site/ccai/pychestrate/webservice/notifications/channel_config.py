"""
.. module:: notifications.channel_config
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Check a notification channel's configuration and sort its secrets from its plain settings.

.. moduleauthor:: Code Craft AI LLC

A channel's settings are declared by its kind (:class:`ChannelConfigField`). The rules, decided with the notification hub spec
(``specs/2-notification-hub/design.md``, Security Considerations):

* every setting a kind declares is checked: required ones are present, values have the right shape, an address starts ``http://`` or
  ``https://``, and a setting the kind does not declare is refused (so a typo does not become a silent no-op);
* a *secret* setting is never accepted as plain text in ``config``. It arrives as ``secrets.<name>`` (the service stores it in the secrets
  vault) or as ``config.<name> = "secret://<vault name>"`` (an existing vault secret, which the acting user must be allowed to read);
* a kind that declares no settings is stored as given (extension kinds written before settings were declared).

This module is pure: it touches neither the database nor the vault. :mod:`notifications.service` does that with the result.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from ccai.pychestrate.webservice.notifications.exceptions import ChannelConfigInvalidError
from ccai.pychestrate.webservice.notifications.factories.channel import ChannelConfigField


SECRET_REF_PREFIX: str = "secret://"

#: The vault name of a secret the service stores for a channel: ``notifications.channel.<channel_id>.<setting>``.
CHANNEL_SECRET_NAME_PREFIX: str = "notifications.channel"

#: Used to mask a value that must not be shown, for a kind that declares no settings.
_SECRET_LOOKING_MARKERS: Tuple[str, ...] = ("password", "secret", "token", "key", "authorization", "credential")

MASKED_VALUE: str = "********"


@dataclass(frozen=True)
class PreparedChannelConfig:
    """
        The outcome of checking a channel's configuration.

        :param config: What to store: the plain settings, and a ``secret://`` reference for each secret setting that points at an existing vault secret.
        :param new_secrets: Secret setting name to the plain value the service must store in the vault (and then replace by a reference).
        :param bound_refs: Secret setting name to the vault name of an existing secret that is new to this channel.
    """
    config: Dict[str, Any]
    new_secrets: Dict[str, str]
    bound_refs: Dict[str, str]


def channel_secret_name(*, channel_id: str, setting: str) -> str:
    """
        The vault name the service stores a channel's secret under.

        :param channel_id: The channel's id.
        :param setting: The setting's name, for example ``password``.

        :returns: ``notifications.channel.<channel_id>.<setting>``.
    """
    rtnval = "{}.{}.{}".format(CHANNEL_SECRET_NAME_PREFIX, channel_id, setting)
    return rtnval


def secret_ref_for(*, name: str) -> str:
    """
        The reference a channel keeps for a vault secret.

        :param name: The vault name.

        :returns: ``secret://<name>``.
    """
    rtnval = SECRET_REF_PREFIX + name
    return rtnval


def secret_name_from_ref(*, ref: str) -> str:
    """
        The vault name inside a ``secret://`` reference.

        :param ref: The reference.

        :returns: The name without the prefix.
    """
    rtnval = ref[len(SECRET_REF_PREFIX):]
    return rtnval


def is_secret_ref(*, value: Any) -> bool:
    """
        Whether a stored value is a ``secret://`` reference.

        :param value: A stored setting.

        :returns: True for a string that starts with ``secret://``.
    """
    rtnval = isinstance(value, str) is True and value.startswith(SECRET_REF_PREFIX) is True
    return rtnval


def is_http_url(*, text: str) -> bool:
    """
        Whether text is an address starting ``http://`` or ``https://`` with a host.

        :param text: The text.

        :returns: True for such an address.
    """
    parts = urlsplit(text.strip())
    rtnval = parts.scheme in ("http", "https") and len(parts.netloc) > 0
    return rtnval


def prepare_channel_config(
        *,
        fields: Tuple[ChannelConfigField, ...],
        kind: str,
        config: Optional[Mapping[str, Any]],
        secrets: Optional[Mapping[str, Any]],
        current_config: Optional[Mapping[str, Any]] = None
    ) -> PreparedChannelConfig:
    """
        Check a configuration against a kind's declared settings.

        :param fields: The kind's declared settings (``config_fields``).
        :param kind: The kind's name, for messages.
        :param config: The plain settings, and ``secret://`` references.
        :param secrets: Secret setting name to the new plain value.
        :param current_config: What the channel stores now, when it is being changed: a secret setting whose reference or legacy value is
                               unchanged is kept without being checked again.

        :returns: The :class:`PreparedChannelConfig`.
        :raises: ChannelConfigInvalidError listing every problem found.
    """
    given = dict(config) if config is not None else {}
    new_values = dict(secrets) if secrets is not None else {}
    current = dict(current_config) if current_config is not None else {}

    if len(fields) == 0:
        if len(new_values) > 0:
            raise ChannelConfigInvalidError(["The {} channel kind declares no secret settings, so 'secrets' cannot be used.".format(kind)])
        rtnval = PreparedChannelConfig(config=given, new_secrets={}, bound_refs={})
        return rtnval

    by_name = {field.name: field for field in fields}
    problems: List[str] = []

    for name in given:
        if name not in by_name:
            problems.append("'{}' is not a setting of the {} channel. Its settings are: {}.".format(name, kind, ", ".join(by_name)))
    for name in new_values:
        if name not in by_name:
            problems.append("'{}' is not a setting of the {} channel. Its settings are: {}.".format(name, kind, ", ".join(by_name)))
        elif by_name[name].secret is False:
            problems.append("{} ('{}') is not a secret setting: give it in 'config'.".format(by_name[name].label, name))

    stored: Dict[str, Any] = {}
    new_secrets: Dict[str, str] = {}
    bound_refs: Dict[str, str] = {}

    for field in fields:
        label = "{} ('{}')".format(field.label, field.name)
        if field.secret is True:
            in_config = given.get(field.name, None)
            in_secrets = new_values.get(field.name, None)
            has_config = in_config is not None and (isinstance(in_config, str) is False or len(in_config.strip()) > 0)
            has_secret = in_secrets is not None and (isinstance(in_secrets, str) is False or len(in_secrets) > 0)
            if has_config is True and has_secret is True:
                problems.append("{}: give either a new value in 'secrets' or a vault reference in 'config', not both.".format(label))
                continue
            if has_secret is True:
                if isinstance(in_secrets, str) is False:
                    problems.append("{} must be text.".format(label))
                    continue
                problem = _value_problem(field=field, label=label, value=in_secrets)
                if problem is not None:
                    problems.append(problem)
                    continue
                new_secrets[field.name] = in_secrets
                continue
            if has_config is True:
                if in_config == current.get(field.name, None):
                    stored[field.name] = in_config
                    continue
                if is_secret_ref(value=in_config) is False:
                    problems.append(
                        "{} is a secret, so it cannot be given as plain text in 'config'. Send the value in 'secrets' and it is stored in the "
                        "secrets vault, or give the name of an existing vault secret as \"secret://<name>\".".format(label)
                    )
                    continue
                name = secret_name_from_ref(ref=in_config)
                if len(name.strip()) == 0:
                    problems.append("{}: the reference \"{}\" names no secret.".format(label, in_config))
                    continue
                if "#" in name:
                    problems.append("{}: a channel always uses the current version of a secret, so leave out the \"#version\" in \"{}\".".format(label, in_config))
                    continue
                stored[field.name] = in_config
                bound_refs[field.name] = name
                continue
            if field.name in current and field.name not in given:
                stored[field.name] = current[field.name]
                continue
            if field.required is True:
                problems.append("{} is required.".format(label))
            continue

        if field.name in given:
            value = given[field.name]
        elif field.name in current:
            value = current[field.name]
        else:
            value = None
        if value is None or (isinstance(value, str) is True and len(value.strip()) == 0) or (field.field_type == "mapping" and value == {}):
            if field.required is True:
                problems.append("{} is required.".format(label))
            continue
        problem = _value_problem(field=field, label=label, value=value)
        if problem is not None:
            problems.append(problem)
            continue
        stored[field.name] = value.strip() if isinstance(value, str) is True else value

    if len(problems) > 0:
        raise ChannelConfigInvalidError(problems)

    rtnval = PreparedChannelConfig(config=stored, new_secrets=new_secrets, bound_refs=bound_refs)
    return rtnval


def _value_problem(*, field: ChannelConfigField, label: str, value: Any) -> Optional[str]:
    """
        Say what is wrong with a value, or None when it is acceptable.

        :param field: The declared setting.
        :param label: How to name the setting in the message.
        :param value: The value given.

        :returns: A sentence, or None.
    """
    rtnval: Optional[str] = None
    if field.field_type == "bool":
        if isinstance(value, bool) is False:
            rtnval = "{} must be true or false.".format(label)
    elif field.field_type == "number":
        if isinstance(value, int) is False or isinstance(value, bool) is True or value < 1 or value > 65535:
            rtnval = "{} must be a whole number between 1 and 65535.".format(label)
    elif field.field_type == "mapping":
        valid = isinstance(value, dict) is True and all(isinstance(k, str) is True and isinstance(v, str) is True for k, v in value.items())
        if valid is False:
            rtnval = "{} must be an object whose names and values are text.".format(label)
    elif isinstance(value, str) is False:
        rtnval = "{} must be text.".format(label)
    elif field.field_type == "url":
        if is_http_url(text=value) is False:
            rtnval = "{} must be an address starting http:// or https://.".format(label)
    return rtnval


def public_config(
        *,
        fields: Tuple[ChannelConfigField, ...],
        config: Optional[Mapping[str, Any]]
    ) -> Tuple[Dict[str, Any], List[str]]:
    """
        A channel's configuration as it may be shown: a secret setting appears as its ``secret://`` reference and a secret that is stored as
        plain text (a channel made before secrets went to the vault) is masked.

        :param fields: The kind's declared settings.
        :param config: What the channel stores.

        :returns: ``(shown, unprotected)`` where ``unprotected`` names the secret settings still held as plain text.
    """
    stored = dict(config) if config is not None else {}
    secret_names = {field.name for field in fields if field.secret is True}
    shown: Dict[str, Any] = {}
    unprotected: List[str] = []
    for name, value in stored.items():
        if len(fields) > 0:
            is_secret = name in secret_names
        else:
            is_secret = any(marker in name.lower() for marker in _SECRET_LOOKING_MARKERS)
        if is_secret is False or is_secret_ref(value=value) is True:
            shown[name] = value
        else:
            shown[name] = MASKED_VALUE
            if value is not None and value != "":
                unprotected.append(name)
    rtnval = (shown, unprotected)
    return rtnval
