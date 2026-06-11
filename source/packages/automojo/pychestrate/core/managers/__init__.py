"""
.. module:: managers
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains manager classes for system configuration operations

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"

from automojo.pychestrate.core.managers.user_manager import UserManager
from automojo.pychestrate.core.managers.global_variable_store import GlobalVariableStore
from automojo.pychestrate.core.managers.resource_manager import ResourceManager
from automojo.pychestrate.core.managers.ip_pool_manager import IPPoolManager
from automojo.pychestrate.core.managers.allocation_manager import AllocationManager
from automojo.pychestrate.core.managers.health_monitor import HealthMonitor
from automojo.pychestrate.core.managers.project_manager import ProjectManager
from automojo.pychestrate.core.managers.repository_manager import RepositoryManager
from automojo.pychestrate.core.managers.build_manager import BuildManager
from automojo.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
from automojo.pychestrate.core.managers.test_manager import TestManager
from automojo.pychestrate.core.managers.release_manager import ReleaseManager
from automojo.pychestrate.core.managers.watch_manager import WatchManager

__all__ = [
    "UserManager",
    "GlobalVariableStore",
    "ResourceManager",
    "IPPoolManager",
    "AllocationManager",
    "HealthMonitor",
    "ProjectManager",
    "RepositoryManager",
    "BuildManager",
    "InfrastructureManager",
    "TestManager",
    "ReleaseManager",
    "WatchManager",
]
