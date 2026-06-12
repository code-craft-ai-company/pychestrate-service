"""
.. module:: ccai.testshared.test_config
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Cross-test configuration knobs (BASE_URL etc.)
               for tests that hit the deployed pychestrate
               instance over real HTTP.

.. moduleauthor:: Code Craft AI LLC

The single knob exposed here is :data:`BASE_URL` -- the root URL
the UI smoke tests + Playwright tests target. Defaults to the
alpha deploy at ``http://tc-app-server/`` so a bare
``testbase testing run ...`` against this checkout exercises the
deployed instance without extra setup.

Override via the environment variable
:data:`ENV_BASE_URL` when pointing at a local dev-up or at a
staging box:

    export PYCHESTRATE_TEST_BASE_URL=http://localhost:8888
    testbase testing run --root source/testroots/ccai ...
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os


ENV_BASE_URL: str = "PYCHESTRATE_TEST_BASE_URL"
DEFAULT_BASE_URL: str = "https://tc-app-server.tailb75ce6.ts.net/"


def _resolve_base_url() -> str:
    """
        Read :data:`ENV_BASE_URL` from the process environment and
        return it with any trailing slash trimmed; fall back to
        :data:`DEFAULT_BASE_URL` when the env var is unset or
        empty.

        :returns: Base URL string (no trailing slash) -- callers
                  concatenate paths starting with ``/``.
    """
    raw = os.environ.get(ENV_BASE_URL, None)
    if raw is None or len(raw) == 0:
        chosen = DEFAULT_BASE_URL
    else:
        chosen = raw
    rtnval = chosen.rstrip("/")
    return rtnval


BASE_URL: str = _resolve_base_url()


__all__ = [
    "BASE_URL",
    "DEFAULT_BASE_URL",
    "ENV_BASE_URL",
]
