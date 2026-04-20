"""
.. module:: messaging
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Minimal in-process message bus and transactional outbox stub.

.. moduleauthor:: Automation Mojo LLC

This package is the Phase 0 ``0-message-bus`` stub used by the Layer 1
features. It provides an in-process pub/sub implementation plus a simple
transactional outbox helper. When the full ``0-message-bus`` feature
lands, the interfaces here (publish, subscribe, enqueue_event) remain
stable and the transport is swapped underneath.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
