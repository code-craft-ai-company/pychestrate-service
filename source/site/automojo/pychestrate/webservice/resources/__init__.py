"""
.. module:: resources
    :synopsis: Layer-4 resource-management plane.

.. moduleauthor:: Automation Mojo LLC

Sub-packages land per Phase-4 schedule:

- ``resources.inventory`` — registry of devices/IPs/subnets/etc.
- ``resources.pools`` — capability-tagged pools.
- ``resources.checkout`` — reservation lifecycle (P4b).
- ``resources.conflict`` — exclusive/shared deconfliction (P4b).
- ``resources.scheduler`` — fair-share queue (P4b).
- ``resources.lease`` — lease + heartbeat (P4c).
- ``resources.health`` — per-kind probes (P4c).
- ``resources.usage_history`` — per-resource timeline (P4c).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
