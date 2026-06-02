"""
.. module:: tests.singlehost.pychestrate.webservice.mcp.test_mcp_service_endpoint_m1
    :synopsis: Unit tests for the MCP server endpoint protocol layer.

.. moduleauthor:: Automation Mojo LLC

Exercises the Model Context Protocol JSON-RPC dispatch in
:mod:`automojo.pychestrate.webservice.mcp.service_endpoint` in isolation:
the ``initialize`` handshake, ``tools/list`` discovery, ``ping``,
notification handling, method/param errors, and the authentication gate
on ``tools/call``. Each test verifies a single aspect.
"""

import json

from typing import Any, Optional

from automojo import testbase

from automojo.pychestrate.webservice.mcp import service_endpoint


class _FakeRequest:
    """
        Minimal stand-in for a webworks ``Request`` carrying the
        attributes the MCP tool handlers read off the request.
    """

    def __init__(
            self,
            *,
            db_session: Optional[Any] = None,
            auth_principal: Optional[Any] = None,
            actor_user_id: Optional[str] = None
        ) -> None:
        self.db_session = db_session
        self.auth_principal = auth_principal
        self.actor_user_id = actor_user_id
        self.path = service_endpoint.MCP_SERVICE_PATH
        return


def test_initialize_advertises_protocol_version():
    request = _FakeRequest()
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18"},
    }
    response = service_endpoint._dispatch_message(request=request, message=message)
    actual = response["result"]["protocolVersion"]
    testbase.assert_equal(actual, service_endpoint.MCP_PROTOCOL_VERSION)
    return


def test_initialize_advertises_tools_capability():
    request = _FakeRequest()
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    }
    response = service_endpoint._dispatch_message(request=request, message=message)
    capabilities = response["result"]["capabilities"]
    has_tools = "tools" in capabilities
    testbase.assert_equal(has_tools, True)
    return


def test_tools_list_includes_list_projects_tool():
    request = _FakeRequest()
    message = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    response = service_endpoint._dispatch_message(request=request, message=message)
    tools = response["result"]["tools"]
    names = [tool["name"] for tool in tools]
    has_list_projects = "list_projects" in names
    testbase.assert_equal(has_list_projects, True)
    return


def test_tools_list_exposes_input_schema_for_each_tool():
    request = _FakeRequest()
    message = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    response = service_endpoint._dispatch_message(request=request, message=message)
    tools = response["result"]["tools"]
    every_tool_has_schema = True
    for tool in tools:
        if "inputSchema" not in tool:
            every_tool_has_schema = False
    testbase.assert_equal(every_tool_has_schema, True)
    return


def test_ping_returns_empty_result():
    request = _FakeRequest()
    message = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "ping",
        "params": {},
    }
    response = service_endpoint._dispatch_message(request=request, message=message)
    testbase.assert_equal(response["result"], {})
    return


def test_unknown_method_returns_method_not_found():
    request = _FakeRequest()
    message = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "does/not/exist",
        "params": {},
    }
    response = service_endpoint._dispatch_message(request=request, message=message)
    actual_code = response["error"]["code"]
    testbase.assert_equal(actual_code, service_endpoint.JSONRPC_METHOD_NOT_FOUND)
    return


def test_notification_yields_no_response():
    request = _FakeRequest()
    message = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }
    response = service_endpoint._dispatch_message(request=request, message=message)
    testbase.assert_equal(response, None)
    return


def test_tools_call_unknown_tool_returns_invalid_params():
    request = _FakeRequest()
    message = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "no_such_tool", "arguments": {}},
    }
    response = service_endpoint._dispatch_message(request=request, message=message)
    actual_code = response["error"]["code"]
    testbase.assert_equal(actual_code, service_endpoint.JSONRPC_INVALID_PARAMS)
    return


def test_tools_call_without_session_returns_session_unavailable_iserror():
    request = _FakeRequest(db_session=None)
    message = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {"name": "list_projects", "arguments": {}},
    }
    response = service_endpoint._dispatch_message(request=request, message=message)
    is_error = response["result"]["isError"]
    testbase.assert_equal(is_error, True)
    return


def test_tools_call_without_principal_returns_auth_required_iserror():
    # db_session present but anonymous principal -> the tool must
    # report an authentication-required error result.
    request = _FakeRequest(db_session=object(), auth_principal=None)
    message = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": "list_projects", "arguments": {}},
    }
    response = service_endpoint._dispatch_message(request=request, message=message)
    is_error = response["result"]["isError"]
    testbase.assert_equal(is_error, True)
    return


def test_tools_call_auth_required_message_mentions_authentication():
    request = _FakeRequest(db_session=object(), auth_principal=None)
    message = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {"name": "list_projects", "arguments": {}},
    }
    response = service_endpoint._dispatch_message(request=request, message=message)
    text = response["result"]["content"][0]["text"]
    mentions_auth = "Authentication required" in text
    testbase.assert_equal(mentions_auth, True)
    return


def test_descriptor_advertises_service_path():
    descriptor = service_endpoint.handle_mcp_service_descriptor(_FakeRequest())
    body = json.loads(descriptor.body.decode("utf-8"))
    testbase.assert_equal(body["endpoint"], service_endpoint.MCP_SERVICE_PATH)
    return


if __name__ == "__main__":
    from automojo.testbase.entrypoints import generic_test_entrypoint

    generic_test_entrypoint()
