"""
.. module:: webservice.api
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Framework-agnostic helpers shared across REST controllers.

.. moduleauthor:: Automation Mojo LLC

This package houses utilities that the REST surface needs but that
should not depend on a specific HTTP framework — RFC 7807 problem
envelopes, future versioning helpers, content-negotiation routines,
and so on. Keeping the helpers here means tests, the CLI, and any
future ASGI / stdlib HTTP target can consume them without pulling in
``flask`` or ``flask_restx``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BASE_URL,
    ProblemDocument,
    ProblemResponse,
    build_problem_document,
    build_problem_response,
    problem_for_http_status,
)


__all__ = [
    "PROBLEM_JSON_MEDIA_TYPE",
    "PROBLEM_TYPE_BASE_URL",
    "ProblemDocument",
    "ProblemResponse",
    "build_problem_document",
    "build_problem_response",
    "problem_for_http_status",
]
