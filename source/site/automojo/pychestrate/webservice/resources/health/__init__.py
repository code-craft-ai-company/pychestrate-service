"""
.. module:: resources.health
    :synopsis: 4-resource-health — periodic probe results per resource.

Public surface:

* :class:`ResourceHealth`, :class:`ProbeOutcome` — persistence
  row + outcome enum.
* :class:`ProbeResult`, :class:`HealthView` — IO shapes.
* :func:`seed_health_record`, :func:`record_probe_outcome`,
  :func:`get_health_record`, :func:`list_due_for_probe`,
  :func:`drop_health_record`.
* :class:`HealthEventTopics`.
* Errors: :class:`HealthError`,
  :class:`HealthRecordNotFoundError`,
  :class:`HealthRecordConflictError`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.resources.health.errors import (
    HealthError,
    HealthRecordConflictError,
    HealthRecordNotFoundError,
)
from automojo.pychestrate.webservice.resources.health.events import (
    HealthEventTopics,
)
from automojo.pychestrate.webservice.resources.health.models import (
    ProbeOutcome,
    ResourceHealth,
)
from automojo.pychestrate.webservice.resources.health.service import (
    HealthView,
    ProbeResult,
    drop_health_record,
    get_health_record,
    list_due_for_probe,
    record_probe_outcome,
    seed_health_record,
)
