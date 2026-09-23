"""
.. module:: pychestrate.cli
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc`` CLI consuming Pychestrate's REST API.

.. moduleauthor:: Code Craft AI LLC

The CLI lives under ``source/site/ccai/pychestrate/cli/`` and talks to
the service only through ``/api/v1``:

* :mod:`entry` -- the dispatcher and console script
  (:func:`entry.console_main`);
* :mod:`commands` -- ``login`` / ``logout`` / ``whoami``, ``config``,
  the commands generated from the server's OpenAPI document, and
  ``runs wait``;
* :mod:`credentials` / :mod:`paths` / :mod:`context` -- profiles in
  ``$XDG_CONFIG_HOME/pychestrate/credentials`` (mode ``0600``) and the
  ``PYC_SERVER_URL`` / ``PYC_TOKEN`` environment overrides;
* :mod:`transport` -- HTTP with the profile's API token as a bearer
  token, no redirect following, and one exception per exit-code
  category;
* :mod:`parser` / :mod:`command_names` / :mod:`openapi_cache` /
  :mod:`builtin_operations` -- the command tree built from
  ``/api/v1/_meta/openapi.json`` (explicit command names, cached, with
  a built-in fallback);
* :mod:`extensions` -- the ``CLISubcommandExtension`` surface behind
  ``pyc ext <ext-name> <verb>``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"
