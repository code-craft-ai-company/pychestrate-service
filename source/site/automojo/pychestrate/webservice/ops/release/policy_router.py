"""
.. module:: ops.release.policy_router
    :synopsis: Resolve the registered release_channel_policy for a channel.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import List, Type

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.ops.release.factories.release_channel_policy import (
    ReleaseChannelPolicyProtocol,
)
from automojo.pychestrate.webservice.ops.release.models import ReleaseChannel


def resolve_policy(
        *,
        channel: ReleaseChannel
    ) -> Type[ReleaseChannelPolicyProtocol]:
    """
        Return the registered policy with the lowest
        PRECEDENCE that claims ``channel``.

        :raises: ConfigurationError when no policy claims the
                 channel (the in-tree default
                 :class:`HashRingChannelPolicy` always claims
                 every channel) or when two policies tie at
                 the lowest PRECEDENCE — the design.md decision
                 is to fail closed at startup rather than pick
                 arbitrarily.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=ReleaseChannelPolicyProtocol.factory_protocol_name,
    )
    if candidates is None or len(candidates) == 0:
        err_lines = ["No release_channel_policy implementations registered."]
        err_lines.append("CHANNEL: {}".format(channel.value))
        err_msg = os.linesep.join(err_lines)
        raise ConfigurationError(err_msg) from None

    matched: List[Type[ReleaseChannelPolicyProtocol]] = []
    for impl in candidates:
        try:
            claimed = impl.channel_set()
        except NotImplementedError:
            continue
        if channel in claimed:
            matched.append(impl)

    if len(matched) == 0:
        err_lines = ["No release_channel_policy claimed the channel."]
        err_lines.append("CHANNEL: {}".format(channel.value))
        err_msg = os.linesep.join(err_lines)
        raise ConfigurationError(err_msg) from None

    matched.sort(key=lambda impl: getattr(impl, "PRECEDENCE", 1000))
    top = matched[0]
    if len(matched) > 1:
        runner_up = matched[1]
        if (
            getattr(top, "PRECEDENCE", 1000)
            == getattr(runner_up, "PRECEDENCE", 1000)
        ):
            err_lines = [
                "Two release_channel_policy implementations tied at "
                "PRECEDENCE for the same channel.",
            ]
            err_lines.append("CHANNEL: {}".format(channel.value))
            err_lines.append("CANDIDATE_A: {}".format(top.__qualname__))
            err_lines.append("CANDIDATE_B: {}".format(runner_up.__qualname__))
            err_msg = os.linesep.join(err_lines)
            raise ConfigurationError(err_msg) from None
    rtnval = top
    return rtnval
