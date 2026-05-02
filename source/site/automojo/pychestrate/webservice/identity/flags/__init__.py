"""
.. module:: identity.flags
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 1-feature-flags feature — runtime toggles for staged rollout.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import register_factory_implementation
from automojo.pychestrate.webservice.identity.flags import cache as flag_cache
from automojo.pychestrate.webservice.identity.flags.factories.local_backend import (
    LocalDatabaseFeatureFlagBackend,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``feature_flag_backend`` reference implementation
        and wire the staleness-window cache invalidator to the bus so updates
        and retirements propagate without explicit caller action.

        :returns: None.
    """
    register_factory_implementation(implementation=LocalDatabaseFeatureFlagBackend)
    flag_cache.subscribe_invalidation_to_bus()
    return
