"""
.. module:: resources.usage_history
    :synopsis: 4-usage-history — append-only timeline of resource events.

Public surface:

* :class:`ResourceTimelineEvent`, :class:`UsageEventType` —
  persistence row + enum.
* :class:`TimelineEventView` — caller-facing read-model.
* :func:`append_event`, :func:`list_timeline`,
  :func:`get_event`.
* :class:`UsageHistoryEventTopics`.
* Errors: :class:`UsageHistoryError`,
  :class:`TimelineEventNotFoundError`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.resources.usage_history.errors import (
    TimelineEventNotFoundError,
    UsageHistoryError,
)
from automojo.pychestrate.webservice.resources.usage_history.events import (
    UsageHistoryEventTopics,
)
from automojo.pychestrate.webservice.resources.usage_history.models import (
    ResourceTimelineEvent,
    UsageEventType,
)
from automojo.pychestrate.webservice.resources.usage_history.service import (
    TimelineEventView,
    append_event,
    get_event,
    list_timeline,
)
