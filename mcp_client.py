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

import asyncio
import json
import os
import re
import sys
import urllib.request
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path

_MEDIA_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
              ".mp4", ".mov", ".webm", ".mp3", ".wav", ".m4a")


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _config_path() -> Path:
    return _base_dir() / "config" / "mcp_servers.json"


def _oauth_path(server_name: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", server_name)
    return _base_dir() / "config" / f"mcp_oauth_{safe}.json"


# --- OAuth support (browser "log in once" for hosted servers) ----------------

_OAUTH_PORT = 8765
_OAUTH_REDIRECT = f"http://localhost:{_OAUTH_PORT}/callback"


class _FileTokenStorage:
    """Persists OAuth tokens + client registration to disk so the browser
    login only happens once (not every startup)."""

    def __init__(self, path: Path):
        self.path = path
        self._tokens = None
        self._client = None
        self._load()

    def _load(self):
        try:
            from mcp.shared.auth import OAuthToken, OAuthClientInformationFull
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("tokens"):
                    self._tokens = OAuthToken.model_validate(data["tokens"])
                if data.get("client"):
                    self._client = OAuthClientInformationFull.model_validate(data["client"])
        except Exception:
            pass

    def _save(self):
        try:
            data = {
                "tokens": self._tokens.model_dump(mode="json") if self._tokens else None,
                "client": self._client.model_dump(mode="json") if self._client else None,
            }
            self.path.write_text(json.dumps(data), encoding="utf-8")
        except Exception as e:
            print(f"[MCP] token save error: {e}")

    async def get_tokens(self):
        return self._tokens

    async def set_tokens(self, tokens):
        self._tokens = tokens
        self._save()

    async def get_client_info(self):
        return self._client

    async def set_client_info(self, client_info):
        self._client = client_info
        self._save()


class _CallbackServer:
    """Tiny local HTTP server that captures the OAuth redirect (?code=&state=)."""

    def __init__(self, port: int = _OAUTH_PORT):
        self.port = port
        self._code = None
        self._state = None
        self._httpd = None
        self._thread = None

    def start(self):
        import http.server
        import threading
        import urllib.parse as _up
        outer = self

        class _H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                params = _up.parse_qs(_up.urlparse(self.path).query)
                # Only capture the real OAuth callback (has ?code=). Ignore
                # follow-up requests like /favicon.ico that would otherwise
                # clobber the captured code/state back to None.
                if "code" in params and outer._code is None:
                    outer._code = params.get("code", [None])[0]
                    outer._state = params.get("state", [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body style='font-family:sans-serif;background:#0c0a05;"
                    b"color:#ffd9a0;text-align:center;padding-top:80px'>"
                    b"<h2>Authorized.</h2><p>You can close this tab and return to JARVIS.</p>"
                    b"</body></html>"
                )

            def log_message(self, *a):
                pass

        self._httpd = http.server.HTTPServer(("localhost", self.port), _H)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def wait(self, timeout: float = 300.0):
        import time as _t
        deadline = _t.time() + timeout
        while self._code is None and _t.time() < deadline:
            _t.sleep(0.2)
        return self._code, self._state

    def stop(self):
        try:
            if self._httpd:
                self._httpd.shutdown()
                self._httpd.server_close()   # release the port for the next server
                self._httpd = None
        except Exception:
            pass


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
        out["description"] = str(s["description"])
    if s.get("enum"):
        # Gemini requires enum values to be STRINGS; some MCP schemas use
        # booleans/numbers. Coerce them and force the type to STRING.
        out["enum"] = [str(e) for e in s["enum"]]
        out["type"] = "STRING"

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

    def _build_oauth(self, sname: str, url: str, spec: dict):
        """Build an OAuthClientProvider that does a one-time browser login and
        persists tokens to disk for subsequent startups."""
        import asyncio
        import webbrowser
        from mcp.client.auth import OAuthClientProvider
        from mcp.shared.auth import OAuthClientMetadata

        cb = _CallbackServer()
        cb.start()

        async def _redirect(auth_url: str) -> None:
            print(f"[MCP] Authorize '{sname}' in your browser. If it doesn't open:\n   {auth_url}")
            try:
                webbrowser.open(auth_url)
            except Exception:
                pass

        async def _callback():
            loop = asyncio.get_event_loop()
            code, state = await loop.run_in_executor(None, cb.wait, 300.0)
            cb.stop()
            return code, state

        meta = OAuthClientMetadata.model_validate({
            "client_name": "JARVIS",
            "redirect_uris": [_OAUTH_REDIRECT],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            **({"scope": spec["scope"]} if spec.get("scope") else {}),
        })

        return OAuthClientProvider(
            server_url=url,
            client_metadata=meta,
            storage=_FileTokenStorage(_oauth_path(sname)),
            redirect_handler=_redirect,
            callback_handler=_callback,
        )

    async def _open_streams(self, stack, sname: str, spec: dict):
        """Open (read, write) streams for a server — local (stdio) OR remote (http/sse).
        Contexts are entered into the given `stack` (a per-server stack), so a
        failed server can be torn down in isolation without affecting others.
        """
        if spec.get("url"):
            url = spec["url"]
            from mcp.client.streamable_http import streamablehttp_client

            if str(spec.get("auth", "")).lower() == "oauth":
                # Browser "log in once" flow (Notion, Higgsfield, etc.)
                provider = self._build_oauth(sname, url, spec)
                streams = await stack.enter_async_context(
                    streamablehttp_client(url, auth=provider))
            else:
                headers = dict(spec.get("headers", {}))
                tok = spec.get("token")
                if tok and "Authorization" not in headers:
                    headers["Authorization"] = f"Bearer {tok}"
                if (spec.get("transport") or "http").lower() == "sse":
                    from mcp.client.sse import sse_client
                    streams = await stack.enter_async_context(
                        sse_client(url, headers=headers))
                else:
                    streams = await stack.enter_async_context(
                        streamablehttp_client(url, headers=headers))
        else:
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(
                command=spec["command"],
                args=spec.get("args", []),
                env={**os.environ, **spec.get("env", {})},
            )
            streams = await stack.enter_async_context(stdio_client(params))
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
            # A single server must never hang JARVIS startup — bound each connect.
            # OAuth needs time for the browser login; token/local connects should
            # be quick, so fail fast if a server is slow/down (keeps startup snappy).
            timeout = 180.0 if str(spec.get("auth", "")).lower() == "oauth" else 20.0
            try:
                await asyncio.wait_for(
                    self._connect_one(sname, spec, ClientSession), timeout=timeout)
            except asyncio.TimeoutError:
                print(f"[MCP] ⚠️  '{sname}' timed out after {timeout:.0f}s — "
                      f"skipping it; JARVIS will start without it.")
            except Exception as e:
                print(f"[MCP] ⚠️  Failed to start server '{sname}': {str(e)[:150]}")

        self.connected = bool(self._tool_map)
        if self.connected:
            print(f"[MCP] Total MCP tools available: {len(self._tool_map)}")

    async def _connect_one(self, sname, spec, ClientSession):
        # Each server gets its own stack so a failure tears down in isolation
        # (a broken OAuth/HTTP context can't cascade into the other servers).
        local = AsyncExitStack()
        try:
            read, write = await self._open_streams(local, sname, spec)
            session = await local.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools = (await session.list_tools()).tools

            # Optional per-server tool filter (keeps the total tool count sane):
            #   "include": [...]  -> only register these tool names
            #   "exclude": [...]  -> register all except these
            include = set(spec.get("include") or [])
            exclude = set(spec.get("exclude") or [])
            registered = 0
            for t in tools:
                if include and t.name not in include:
                    continue
                if t.name in exclude:
                    continue
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
                self._tool_map[gname] = (session, t.name, sname)
                registered += 1
            extra = f" (filtered from {len(tools)})" if registered != len(tools) else ""
            print(f"[MCP] ✅ '{sname}' connected — {registered} tool(s){extra}.")
            # Success — keep this server's contexts alive until app shutdown.
            self._stack.push_async_callback(local.aclose)
        except BaseException:
            # Tear down the broken contexts right here, in this task.
            try:
                await local.aclose()
            except Exception:
                pass
            raise

    def has_tool(self, name: str) -> bool:
        return name in self._tool_map

    async def call(self, name: str, args: dict) -> str:
        """Invoke an MCP tool by its Gemini-side name; return text output.
        If the result contains an image/video URL, download it to generated/
        and return a clean 'saved' message (no raw URL / task IDs to read aloud)."""
        if name not in self._tool_map:
            return f"Unknown MCP tool: {name}"
        session, real, sname = self._tool_map[name]
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

        # If a media URL came back, save it to disk and report the file instead.
        saved = await self._maybe_save_media(out, sname)
        if saved:
            return saved
        return out[:6000]

    async def _maybe_save_media(self, text: str, sname: str) -> str | None:
        """Find an image/video URL in the result, download it to
        generated/<server>/, and return a clean message. None if no media URL."""
        media_url = None
        for u in re.findall(r"https?://\S+", text or ""):
            clean = u.rstrip(').,\'"]}')
            path = clean.split("?")[0].lower()
            if path.endswith(_MEDIA_EXT):
                media_url = clean
        if not media_url:
            return None

        d = self._save_dir(sname)
        ext = Path(media_url.split("?")[0]).suffix or ".bin"
        fname = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        dest = d / fname

        def _dl():
            req = urllib.request.Request(media_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
                f.write(r.read())

        try:
            await asyncio.to_thread(_dl)
            print(f"[MCP] Saved media: generated/{sname}/{fname}  ({media_url})")
            return (f"Done — the result is ready and saved in the {sname} folder "
                    f"as {fname}.")
        except Exception as e:
            print(f"[MCP] media download failed: {e}")
            return None  # fall back to the raw text

    def _save_dir(self, sname: str) -> Path:
        d = _base_dir() / "generated" / re.sub(r"[^a-zA-Z0-9._-]", "_", sname)
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def close(self):
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:
                pass
            self._stack = None
