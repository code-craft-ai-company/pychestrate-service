"""
.. module:: scripts.serve
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Launch the pychestrate service via the built-in WSGI server.

.. moduleauthor:: Automation Mojo LLC

Convenience CLI that wraps the webworks built-in WSGI server. Reads
``PYCHESTRATE_DATABASE_URL`` from the environment (required) plus
optional ``PYCHESTRATE_DEBUG`` and ``PYCHESTRATE_CREATE_SCHEMA``.

Usage::

    PYCHESTRATE_DATABASE_URL=sqlite:///./pychestrate.db \\
        PYCHESTRATE_CREATE_SCHEMA=true \\
        python scripts/serve.py --host 0.0.0.0 --port 8080

For production deployments, prefer a real WSGI server such as
gunicorn::

    gunicorn -b 0.0.0.0:8080 \\
        'automojo.pychestrate.webservice.wsgientry:application'
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import os
import sys

from typing import Optional

from automojo.pychestrate.webservice.wsgientry import application


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


def main(*, argv: Optional[list] = None) -> int:
    """
        CLI entry point. Imports the configured
        :class:`PychestrateApplication`, instantiates a webworks
        WSGI server, and serves until interrupted.
    """
    parser = argparse.ArgumentParser(
        description="Run the pychestrate service via the webworks WSGI server.",
    )
    parser.add_argument(
        "--host",
        dest="host",
        default=DEFAULT_HOST,
        help="Bind host (default: {0}).".format(DEFAULT_HOST),
    )
    parser.add_argument(
        "--port",
        dest="port",
        type=int,
        default=DEFAULT_PORT,
        help="Bind port (default: {0}).".format(DEFAULT_PORT),
    )
    args = parser.parse_args(argv)

    if application is None:
        sys.stderr.write(
            "ERROR: could not build the application — is "
            "PYCHESTRATE_DATABASE_URL set?{0}".format(os.linesep),
        )
        return 2

    sys.stdout.write(
        "pychestrate-service: {0} routes registered{1}".format(
            len(application.router._routes),
            os.linesep,
        ),
    )
    sys.stdout.write(
        "Listening on http://{0}:{1}{2}".format(
            args.host, args.port, os.linesep,
        ),
    )

    # The webworks built-in WSGI server lives at
    # automojo.webworks.wsgi.server. We import lazily to avoid pulling
    # the server stack in for non-server invocations of the script.
    from automojo.webworks.wsgi.server import WSGIServer

    server = WSGIServer(
        host=args.host,
        port=args.port,
        application=application,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stdout.write(
            "Shutting down on Ctrl-C.{0}".format(os.linesep),
        )

    rtnval = 0
    return rtnval


if __name__ == "__main__":
    raise SystemExit(main())
