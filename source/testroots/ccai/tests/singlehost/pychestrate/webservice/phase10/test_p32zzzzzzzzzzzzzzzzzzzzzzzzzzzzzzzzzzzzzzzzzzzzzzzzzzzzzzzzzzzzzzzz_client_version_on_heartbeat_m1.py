"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_client_version_on_heartbeat_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A pod's client version reaches the Clients page through its heartbeat (E2E-18).

.. moduleauthor:: Code Craft AI LLC

The Clients page shows a runtime version for every client, and showed a dash for every live one: the heartbeat recorded no version (it passed None) and nothing else did after enrolment. The client now
sends ``X-Pychestrate-Client-Version`` and the heartbeat records it when it is a plausible version string.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.clients.restapi.v1 import client_dispatch_routes


CLIENT_ID = "7f6abf9d-8f46-4455-9811-3a7a5fd84383"


class _Request:
    def __init__(self, headers: Optional[Dict[str, str]]) -> None:
        self.path = "/api/v1/clients/{}/heartbeat".format(CLIENT_ID)
        self.path_params = {"client_id": CLIENT_ID}
        self.query_params: Dict[str, Any] = {}
        self.mtls_client_cn = CLIENT_ID
        self.db_session = object()
        if headers is not None:
            self.headers = headers


def _recorded_version(headers: Optional[Dict[str, str]]) -> Any:
    captured: Dict[str, Any] = {}
    patch = create_module_patch(client_dispatch_routes.client_registry_service, "record_heartbeat")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: captured.update(kwargs))
    try:
        response = client_dispatch_routes.handle_client_heartbeat(_Request(headers))
    finally:
        patch.deactivate()
    return (response.status_code, captured.get("agent_version", "not called"))


def test_the_heartbeat_records_a_plausible_client_version_and_nothing_else():
    """
    **Feature: client runtime version (E2E-18)**
    **Property: the version in X-Pychestrate-Client-Version is recorded as the client's agent version when it is letters, digits and ". _ + -" (at most 64, starting with a letter or digit);
    a missing header, an empty one, one with spaces, markup or control characters, one over 64 characters and a request with no headers at all record None; the answer is 204 each time.**
    """
    header = client_dispatch_routes.CLIENT_VERSION_HEADER
    results = {
        "plain": _recorded_version({header: "0.0.1"}),
        "padded": _recorded_version({header: "  1.2.3-rc.1+build.5 "}),
        "missing": _recorded_version({}),
        "no headers": _recorded_version(None),
        "empty": _recorded_version({header: ""}),
        "spaces": _recorded_version({header: "1.0 beta"}),
        "markup": _recorded_version({header: "<script>1</script>"}),
        "newline": _recorded_version({header: "1.0\nX-Evil: 1"}),
        "too long": _recorded_version({header: "1" * 65}),
        "longest": _recorded_version({header: "1" * 64}),
    }

    testbase.assert_equal(
        results,
        {
            "plain": (204, "0.0.1"), "padded": (204, "1.2.3-rc.1+build.5"), "missing": (204, None), "no headers": (204, None), "empty": (204, None), "spaces": (204, None),
            "markup": (204, None), "newline": (204, None), "too long": (204, None), "longest": (204, "1" * 64),
        },
    )
    return
