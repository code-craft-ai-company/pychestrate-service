"""
.. module:: notifications.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exceptions raised by 2-notification-hub service APIs.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re


class ChannelAlreadyExistsError(Exception):
    """
        Raised when a channel name collides within its scope.
    """


class ChannelNotFoundError(Exception):
    """
        Raised when a requested channel cannot be resolved.
    """


class UnsupportedChannelKindError(Exception):
    """
        Raised when no ``notification_channel`` implementation matches a kind.
    """


class TemplateNotFoundError(Exception):
    """
        Raised when no template with the given name is registered.
    """


class NotificationDispatchError(Exception):
    """
        Raised when a channel send fails at the protocol layer.
    """


class ChannelConfigInvalidError(Exception):
    """
        Raised when a channel's configuration is not acceptable: a missing or
        unknown setting, a value of the wrong shape, or a secret given as plain
        text.

        :param problems: One sentence per problem, written for the person who
                         filled in the form.
    """

    def __init__(self, problems: list):
        self.problems = list(problems)
        super().__init__(os.linesep.join(self.problems))

    @property
    def field_problems(self) -> dict:
        """
            The problems that are about one setting, keyed by the setting's name (the first problem for each); the rest are general.
        """
        found = {}
        for problem in self.problems:
            match = re.search(r"\('([A-Za-z0-9_]+)'\)", problem) or re.match(r"'([A-Za-z0-9_]+)' is not a setting", problem)
            if match is not None and match.group(1) not in found:
                found[match.group(1)] = problem
        return found


class ChannelSecretAccessDeniedError(Exception):
    """
        Raised when the acting user may not store a channel's secret in the
        vault, or may not read the vault secret they asked a channel to use.
    """


class ChannelSecretUnavailableError(Exception):
    """
        Raised at send time when a secret a channel points at is missing or has
        expired. The message names the channel and the setting, never the value.
    """


class ChannelInUseError(Exception):
    """
        Raised when a channel is deleted while a routing rule still sends
        through it.
    """


class RoutingRuleInvalidError(Exception):
    """
        Raised when a routing rule's fields would make a rule that could never send, or are not the right shape.

        :param detail: One sentence saying what is wrong, written for the person who filled in the form.
        :param extensions: Optional members to carry on a REST problem document.
    """

    def __init__(self, detail: str, extensions: dict = None):
        self.detail = detail
        self.extensions = extensions
        super().__init__(detail)
