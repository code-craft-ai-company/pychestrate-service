"""
.. module:: jobs.cancel.events
    :synopsis: Bus topics emitted by the cancel half.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class CancelEventTopics:
    """
        Cancel-half bus topic constants.
    """
    REQUEST_TRANSMITTED = "entity.run.cancel_request.transmitted"
    ACK_RECEIVED = "entity.run.cancel_ack"
    REQUEST_FAILED = "entity.run.cancel_request.failed"
