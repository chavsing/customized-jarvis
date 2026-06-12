"""
MCP bridge for JARVIS.

JARVIS uses the Gemini Live API with manual function declarations, so we
"bridge" MCP rather than relying on SDK auto-calling:

1. Connect to each MCP server listed in config/mcp_servers.json
2. list_tools() on each, convert every MCP tool -> a Gemini function declaration
3. Expose those declarations to the Live session (merged with the built-in tools)
4. Route any tool call whose name we own back to the right MCP session

Config format (same shape as Claude Desktop's mcpServers):

    {
      "mcpServers": {
        "filesystem": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\\\Users\\\\me\\\\Desktop"],
          "env": {},
          "disabled": false
        }
      }
    }

Everything here is best-effort: if the `mcp` package isn't installed, the
config is missing, or a server fails to start, JARVIS runs normally without it.
"""

import json
import os
import re
import sys
from contextlib import AsyncExitStack
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _config_path() -> Path:
    return _base_dir() / "config" / "mcp_servers.json"


# --- JSON Schema (MCP) -> Gemini function-declaration schema -----------------

_TYPE_MAP = {
    "string": "STRING", "number": "NUMBER", "integer": "INTEGER",
    "boolean": "BOOLEAN", "object": "OBJECT", "array": "ARRAY",
}


def _convert_schema(s: dict) -> dict:
    """Convert an MCP inputSchema (JSON Schema) to Gemini's OpenAPI-subset dict."""
    if not isinstance(s, dict):
        return {"type": "STRING"}

    t = s.get("type", "object")
    if isinstance(t, list):                       # e.g. ["string", "null"]
        t = next((x for x in t if x != "null"), "string")
    out = {"type": _TYPE_MAP.get(str(t).lower(), "STRING")}

    if s.get("description"):
        out["description"] = s["description"]
    if s.get("enum"):
        out["enum"] = s["enum"]

    if out["type"] == "OBJECT":
        props = s.get("properties") or {}
        out["properties"] = {k: _convert_schema(v) for k, v in props.items()}
        req = [r for r in (s.get("required") or []) if r in out["properties"]]
        if req:
            out["required"] = req
    elif out["type"] == "ARRAY":
        out["items"] = _convert_schema(s.get("items") or {"type": "string"})

    return out


def _sanitize_name(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if not name or not (name[0].isalpha() or name[0] == "_"):
        name = "mcp_" + name
    return name[:60]


class MCPManager:
    def __init__(self):
        self._stack: AsyncExitStack | None = None
        self.declarations: list[dict] = []        # Gemini function declarations
        self._tool_map: dict = {}                 # gemini_name -> (session, real_tool_name)
        self.connected = False

    def _load_config(self) -> dict:
        p = _config_path()
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("mcpServers", {})
        except Exception as e:
            print(f"[MCP] Config error: {e}")
            return {}

    async def _open_streams(self, sname: str, spec: dict):
        """Open (read, write) streams for a server — local (stdio) OR remote (http/sse).
        - Remote: spec has 'url' (+ optional 'headers' / 'token' / 'transport': 'sse')
        - Local:  spec has 'command' (+ 'args' / 'env')
        """
        if spec.get("url"):
            url = spec["url"]
            headers = dict(spec.get("headers", {}))
            tok = spec.get("token")
            if tok and "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {tok}"
            if (spec.get("transport") or "http").lower() == "sse":
                from mcp.client.sse import sse_client
                streams = await self._stack.enter_async_context(
                    sse_client(url, headers=headers))
            else:
                from mcp.client.streamable_http import streamablehttp_client
                streams = await self._stack.enter_async_context(
                    streamablehttp_client(url, headers=headers))
        else:
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(
                command=spec["command"],
                args=spec.get("args", []),
                env={**os.environ, **spec.get("env", {})},
            )
            streams = await self._stack.enter_async_context(stdio_client(params))
        # stdio yields (read, write); http/sse yield (read, write, ...) — take first two
        return streams[0], streams[1]

    async def connect_all(self):
        """Connect to all configured MCP servers and build tool declarations.
        Safe to call once at startup; never raises."""
        servers = self._load_config()
        if not servers:
            print("[MCP] No MCP servers configured (config/mcp_servers.json).")
            return

        try:
            from mcp import ClientSession
        except Exception:
            print("[MCP] 'mcp' package not installed — run: pip install mcp. Skipping.")
            return

        self._stack = AsyncExitStack()
        for sname, spec in servers.items():
            if spec.get("disabled"):
                continue
            try:
                read, write = await self._open_streams(sname, spec)
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                tools = (await session.list_tools()).tools
                for t in tools:
                    gname = _sanitize_name(f"mcp_{sname}_{t.name}")
                    while gname in self._tool_map:
                        gname = gname[:57] + "_x"
                    self.declarations.append({
                        "name": gname,
                        "description": (t.description or t.name)[:1000],
                        "parameters": _convert_schema(
                            t.inputSchema or {"type": "object", "properties": {}}
                        ),
                    })
                    self._tool_map[gname] = (session, t.name)
                print(f"[MCP] ✅ '{sname}' connected — {len(tools)} tool(s).")
            except Exception as e:
                print(f"[MCP] ⚠️  Failed to start server '{sname}': {str(e)[:150]}")

        self.connected = bool(self._tool_map)
        if self.connected:
            print(f"[MCP] Total MCP tools available: {len(self._tool_map)}")

    def has_tool(self, name: str) -> bool:
        return name in self._tool_map

    async def call(self, name: str, args: dict) -> str:
        """Invoke an MCP tool by its Gemini-side name; return text output."""
        if name not in self._tool_map:
            return f"Unknown MCP tool: {name}"
        session, real = self._tool_map[name]
        try:
            res = await session.call_tool(real, args or {})
        except Exception as e:
            return f"MCP tool '{real}' error: {str(e)[:200]}"

        parts = []
        for c in (getattr(res, "content", None) or []):
            txt = getattr(c, "text", None)
            parts.append(txt if txt is not None else str(c))
        out = "\n".join(parts) if parts else "(no output)"
        if getattr(res, "isError", False):
            out = "Error: " + out
        return out[:6000]

    async def close(self):
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:
                pass
            self._stack = None
