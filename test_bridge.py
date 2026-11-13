import base64
import json
import os
import unittest
from unittest import mock

import bridge


def _jwt(exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"header.{payload}.sig"


class BridgeTest(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("LEARNGRAPH_MCP_URL", None)

    def test_default_url_is_production(self) -> None:
        self.assertEqual(bridge.mcp_url(), "https://app.learngraph.org/service-mcp/v1/public/mcp")
        self.assertEqual(bridge.token_command(), ["learngraph", "--environment", "prod", "auth", "token"])

    def test_override_uses_existing_cli_login(self) -> None:
        os.environ["LEARNGRAPH_MCP_URL"] = "http://localhost:8095/service-mcp/v1/public/mcp"
        self.assertEqual(bridge.mcp_url(), "http://localhost:8095/service-mcp/v1/public/mcp")
        self.assertEqual(bridge.token_command(), ["learngraph", "auth", "token"])

    def test_worker_door_is_rejected(self) -> None:
        os.environ["LEARNGRAPH_MCP_URL"] = "https://app.learngraph.org/service-mcp/v1/mcp"
        with self.assertRaises(SystemExit):
            bridge.mcp_url()

    def test_sse_response_becomes_jsonrpc_messages(self) -> None:
        raw = "event: message\ndata: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}\n\n"
        messages = bridge.response_messages("text/event-stream", raw)
        self.assertEqual(messages, [{"jsonrpc": "2.0", "id": 1, "result": {}}])

    def test_token_cache_skips_refresh_until_near_expiry(self) -> None:
        cache = bridge.TokenCache()
        with mock.patch.object(bridge, "fetch_token", return_value=_jwt(10_000_000_000)) as fetch:
            self.assertTrue(cache.bearer())
            self.assertTrue(cache.bearer())
            fetch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
