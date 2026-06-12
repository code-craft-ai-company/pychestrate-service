"""
.. module:: identity.setup
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Jenkins-style first-run setup wizard.

.. moduleauthor:: Code Craft AI LLC

The setup package implements the one-time bootstrap flow that runs
the very first time the webservice boots into an empty database.

* On first boot, :mod:`setup_service` writes a high-entropy initial
  admin token to ``<presence-dir>/initial-admin-token`` and records
  its sha256 in :class:`InitialSetup`. The presence-dir is the
  persona presence directory resolved by
  :mod:`pychestrate_presence` (CLI flag / env var / pychestrate
  default ``~/pychestrate``).
* The :mod:`middleware_setup_gate` intercepts every non-setup
  request and redirects to ``/setup/unlock`` while
  ``InitialSetup.completed_at`` is NULL.
* The setup blueprint serves ``/setup/unlock`` (paste the token)
  and ``/setup/admin`` (create the first administrator).
* On successful admin creation, ``completed_at`` is stamped, the
  token file is deleted, and the gate becomes a no-op forever.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"
