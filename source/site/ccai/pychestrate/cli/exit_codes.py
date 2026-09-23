"""
.. module:: cli.exit_codes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Enumerated exit codes the ``pyc`` command emits.

.. moduleauthor:: Code Craft AI LLC

The mapping is shared between the entry-point dispatcher and the
exception translation layer so every code path returns a documented
number. Tests assert on these codes by name.

========  ==============================================================
Code      Meaning
========  ==============================================================
0         Success.
2         Usage error: bad arguments, or the server answered 400 / 422.
3         Authentication / authorization: 401 or 403.
4         Not found: 404.
5         Conflict: 409.
6         Rate limited: 429.
7         Server error: 5xx, or a response that is not the API's (a
          redirect, an HTML page).
8         Cannot reach the server: refused, DNS failure, TLS failure,
          timeout, or a malformed URL.
10        ``--wait``: the run finished without succeeding.
11        ``--wait``: gave up waiting before the run finished.
13        Credentials / configuration: no configuration, an unreadable
          or corrupt credentials file, or a file readable by others.
========  ==============================================================
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


EXIT_OK: int = 0
EXIT_USAGE_ERROR: int = 2
EXIT_AUTHENTICATION_ERROR: int = 3
EXIT_NOT_FOUND: int = 4
EXIT_CONFLICT: int = 5
EXIT_RATE_LIMITED: int = 6
EXIT_SERVER_ERROR: int = 7
EXIT_CONNECTION_ERROR: int = 8
EXIT_RUN_FAILED: int = 10
EXIT_WAIT_TIMEOUT: int = 11
EXIT_CREDENTIALS_ERROR: int = 13

#: Historical name of :data:`EXIT_CREDENTIALS_ERROR` (the code covers
#: a missing or corrupt credentials file too, not only its mode).
EXIT_CREDENTIALS_PERMISSIONS_ERROR: int = EXIT_CREDENTIALS_ERROR
