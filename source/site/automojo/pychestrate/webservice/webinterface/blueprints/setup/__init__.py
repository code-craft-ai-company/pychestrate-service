"""
.. module:: webinterface.blueprints.setup
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Webworks blueprint for the first-run setup wizard.

.. moduleauthor:: Automation Mojo LLC

The setup blueprint serves the two pages of the wizard:

* ``GET/POST /setup/unlock`` -- paste the token from
  ``${PYCHESTRATE_RUNTIME_DIR}/initial-admin-token``.
* ``GET/POST /setup/admin`` -- choose login + email + password for
  the first administrator.

After admin creation, the wizard redirects to ``/config/login`` and
the gate middleware (installed at ``position="start"``) becomes a
no-op forever. Returning to ``/setup/*`` after completion 404s.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
