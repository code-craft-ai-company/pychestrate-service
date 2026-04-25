"""
.. module:: resources.pools
    :synopsis: 4-resource-pools — capability-tagged grouping.

Public surface:

* :class:`ResourcePool`, :class:`ResourcePoolMember` rows.
* :class:`PoolView`, :class:`PoolCandidate`,
  :class:`AllocationAspects`.
* :func:`create_pool`, :func:`get_pool`, :func:`list_pools`,
  :func:`add_member`, :func:`remove_member`,
  :func:`pick_candidate`.
* :class:`PoolError`, :class:`PoolNotFoundError`,
  :class:`PoolMemberConflictError`,
  :class:`PoolEmptyError`.
* :class:`PoolEventTopics`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.resources.pools.errors import (
    PoolEmptyError,
    PoolError,
    PoolMemberConflictError,
    PoolNotFoundError,
)
from automojo.pychestrate.webservice.resources.pools.events import (
    PoolEventTopics,
)
from automojo.pychestrate.webservice.resources.pools.models import (
    ResourcePool,
    ResourcePoolMember,
)
from automojo.pychestrate.webservice.resources.pools.service import (
    AllocationAspects,
    PoolCandidate,
    PoolView,
    add_member,
    create_pool,
    get_pool,
    list_pools,
    pick_candidate,
    remove_member,
)
