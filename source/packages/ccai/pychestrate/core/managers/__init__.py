"""
.. module:: managers
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains manager classes for system configuration operations

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"

from ccai.pychestrate.core.managers.user_manager import UserManager
from ccai.pychestrate.core.managers.resource_manager import ResourceManager
from ccai.pychestrate.core.managers.ip_pool_manager import IPPoolManager
from ccai.pychestrate.core.managers.allocation_manager import AllocationManager
from ccai.pychestrate.core.managers.health_monitor import HealthMonitor
from ccai.pychestrate.core.managers.project_manager import ProjectManager
from ccai.pychestrate.core.managers.repository_manager import RepositoryManager
from ccai.pychestrate.core.managers.build_manager import BuildManager
from ccai.pychestrate.core.managers.infrastructure_manager import InfrastructureManager
from ccai.pychestrate.core.managers.test_manager import TestManager
from ccai.pychestrate.core.managers.release_manager import ReleaseManager
from ccai.pychestrate.core.managers.watch_manager import WatchManager

__all__ = [
    "UserManager",
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
