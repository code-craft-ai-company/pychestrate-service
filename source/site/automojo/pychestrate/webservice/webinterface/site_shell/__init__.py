"""
.. module:: webinterface.site_shell
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Server-side adapter for the ``<pyc-site-shell>``
               unified UI chrome (M1 skeleton, per
               ``specs/9-site-shell``).

.. moduleauthor:: Automation Mojo LLC

This package owns:

* :mod:`shell_document` -- renders the host HTML page that mounts
  ``<pyc-site-shell>`` and imports the feature bundles registered
  for the request's route prefix.

* :mod:`chromeless_routes` -- the canonical list of route prefixes
  that bypass the shell document (``/login``, ``/logout``,
  ``/setup``, ``/__health``, ``/errors``).

* :mod:`bundle_registry` -- maps route prefixes to feature bundle
  names so the shell document can ``<script src=...>`` only the
  bundles relevant to the current request.

* :mod:`nav_manifest` -- the central, authoritative navigation
  manifest. Declares every sidebar group / entry once,
  decoupled from which feature bundle is loaded; the
  ``GET /api/v1/me/navigation`` endpoint permission-filters it
  so the shell renders a complete sidebar on every route.

* :mod:`catchall_route` -- attaches the catch-all webworks handler
  that serves the shell document for every non-chromeless GET.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
