"""
.. module:: cli.version
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The one place the ``pyc`` version is defined.

.. moduleauthor:: Code Craft AI LLC

``pyc --version``, ``pyc version``, the ``User-Agent`` header and the
standalone ``pychestrate-cli`` package metadata
(``packages/pychestrate-cli/pyproject.toml`` reads
:data:`PYC_VERSION` from here) all use this value. The per-module
``__version__`` strings elsewhere in the package are source-file
revision markers, not the CLI's version.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import platform


#: The version of the pyc command line (and of the pychestrate-cli
#: package).
PYC_VERSION: str = "0.3.0"

#: Product token in the ``User-Agent`` header.
USER_AGENT_PRODUCT: str = "pyc"


def user_agent() -> str:
    """
        The ``User-Agent`` pyc sends: ``pyc/<version> python/<version>``.

        :returns: Header value.
    """
    rtnval = "{}/{} python/{}".format(USER_AGENT_PRODUCT, PYC_VERSION, platform.python_version())
    return rtnval


__all__ = [
    "PYC_VERSION",
    "USER_AGENT_PRODUCT",
    "user_agent",
]
