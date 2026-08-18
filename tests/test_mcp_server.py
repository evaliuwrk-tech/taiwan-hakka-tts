from __future__ import annotations

import unittest

from hakka_tts.mcp_server import handle


class MCPServerTests(unittest.TestCase):
    def test_initialize_and_tool_listing(self):
        initialized = handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "taiwan-hakka-tts")
        listed = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertEqual(
            names, {"hakka_tts_status", "hakka_tts_catalog", "hakka_tts_synthesize"}
        )
        synthesize = next(
            tool for tool in listed["result"]["tools"] if tool["name"] == "hakka_tts_synthesize"
        )
        self.assertIn("tone", synthesize["inputSchema"]["properties"])
        self.assertIn("pitch_semitones", synthesize["inputSchema"]["properties"])
        self.assertIn("child", synthesize["inputSchema"]["properties"]["tone"]["enum"])
        self.assertIn("human", synthesize["inputSchema"]["properties"]["rhythm"]["enum"])

    def test_catalog_is_available_offline(self):
        response = handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "hakka_tts_catalog", "arguments": {}},
            }
        )
        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(len(response["result"]["structuredContent"]["voices"]), 5)
        self.assertEqual(len(response["result"]["structuredContent"]["tonePresets"]), 7)


if __name__ == "__main__":
    unittest.main()
