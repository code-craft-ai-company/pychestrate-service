pychestrate-cli
===============

``pyc`` is the command line for the Pychestrate service. Every command
of the service's REST API (``/api/v1``) is a ``pyc <noun> <verb>``
command, generated from the OpenAPI document the server publishes, plus
``login``, ``whoami``, ``config``, ``runs wait`` and ``version``.

This package holds only the CLI: it uses the Python standard library
alone and installs anywhere Python 3.10 or later runs.

Install
-------

From a checkout of ``pychestrate-service``::

    pipx install ./packages/pychestrate-cli

or build a wheel to hand around::

    python3 -m pip wheel --no-deps -w dist ./packages/pychestrate-cli
    pipx install dist/pychestrate_cli-*.whl

Then::

    pyc login --server-url https://pychestrate.example.com
    pyc projects list
    pyc --help

The user manual chapter "The pyc Command Line"
(``userguide/14-00-pyc-command-line.rst``) describes every option,
output format and exit code.
