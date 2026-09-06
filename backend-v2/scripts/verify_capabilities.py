"""Isolated release QA for model capabilities, media, budgets and MCP web services.

Run with the repository venv (MCP SDK, uvicorn and keyring must be installed)::

    .venv/Scripts/python.exe scripts/verify_capabilities.py dist/zhishi-backend.exe --report report.json
    .venv/Scripts/python.exe scripts/verify_capabilities.py --source .venv/Scripts/python.exe --report report.json

Both modes launch the real backend CLI with a fresh temporary data directory.
Only loopback OpenAI Chat and MCP services are configured; the public reader URL
is an argument to the local mock, never fetched by the fixture. No Tavily key is
created. Cleanup stops owned processes/servers and verifies deletion of only the
disposable credential references in this run's database. Failed cleanup retains
the temporary directory for diagnosis. Exit 0 requires every check and cleanup.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import random
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PUBLIC_URL = "https://93.184.216.34/page"
VISION_REPORT = "MOCK_READ_REPORT: fixture image contains a blue QA marker."
WEB_REPORT = "MOCK_WEB_REPORT: local MCP supplied the requested page."
FAKE_KEY = "capabilities-disposable-placeholder-not-a-real-key"


def require(condition, message):
    # Do not let python -O silently turn release checks off.
    if not condition:
        raise AssertionError(message)


def png_fixture():
    """Valid 768x512 RGB PNG, ~1.1 MiB: catches raw-base64 token estimation."""
    width, height = 768, 512
    rng = random.Random(290)
    pixels = b"".join(b"\0" + rng.randbytes(width * 3) for _ in range(height))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def message_text(request):
    texts = []
    for message in request["messages"]:
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            texts.extend(p.get("text", "") for p in content if p.get("type") == "text")
    return "\n".join(texts)


def image_urls(request):
    return [p["image_url"]["url"] for m in request["messages"]
            if isinstance(m.get("content"), list) for p in m["content"]
            if p.get("type") == "image_url"]


def require_text_only(request):
    for message in request["messages"]:
        content = message.get("content")
        require(content is None or isinstance(content, str)
                or (isinstance(content, list) and all(p.get("type") == "text" for p in content)),
                "Provider received non-text content for a text-only model")
    require("data:image/" not in json.dumps(request["messages"]),
            "Image data leaked into text-only provider messages")


class Provider(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), ProviderHandler)
        self.requests = []
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)


class ProviderHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append({"path": self.path, "body": request,
                                     "auth_ok": self.headers.get("Authorization") == f"Bearer {FAKE_KEY}"})
        if self.path != "/v1/chat/completions":
            self.send_error(404, "Only the loopback Chat completion fixture is supported")
            return
        incoming = message_text(request)
        # The fixture repeats only evidence actually supplied in the request.
        if VISION_REPORT in incoming:
            answer = VISION_REPORT
        elif "附件内容未读取" in incoming:
            answer = "附件内容未读取：请配置视觉 MCP 或提供文字描述。"
        else:
            answer = "CAPABILITIES_MOCK_OK"

        def chunk(delta, reason=None):
            return {"id": "chatcmpl-capabilities", "object": "chat.completion.chunk", "created": 0,
                    "model": request["model"],
                    "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}

        frames = [chunk({"role": "assistant", "content": answer[:len(answer) // 2]}),
                  chunk({"content": answer[len(answer) // 2:]}), chunk({}, "stop")]
        payload = ("".join("data: " + json.dumps(c) + "\n\n" for c in frames)
                   + "data: [DONE]\n\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()


class MCPFixture:
    def __init__(self):
        import uvicorn
        from mcp.types import ToolAnnotations
        # SDK v2 renamed its FastMCP server to MCPServer, as used in test_mcp.py.
        try:
            from mcp.server.mcpserver import MCPServer
            server = MCPServer(name="capabilities-local-fixture")
            self.implementation = "mcp.server.mcpserver.MCPServer"
            app_factory = lambda: server.streamable_http_app(stateless_http=True)
        except ImportError:
            from mcp.server.fastmcp import FastMCP
            server = FastMCP(name="capabilities-local-fixture", stateless_http=True)
            self.implementation = "mcp.server.fastmcp.FastMCP"
            app_factory = server.streamable_http_app
        self.calls = []

        def describe_image(image: str, prompt: str) -> str:
            """Read the supplied fixture image and return a deterministic report."""
            self.calls.append({"tool": "describe_image", "image": image, "prompt": prompt})
            return VISION_REPORT

        def mapped_search(needle: str, count: int) -> str:
            """Search fixture documents using deliberately nondefault field names."""
            self.calls.append({"tool": "mapped_search", "needle": needle, "count": count})
            return json.dumps({"payload": {"hits": [
                {"heading": "Fixture guide", "link": PUBLIC_URL, "summary": "Mock search summary"},
                {"heading": "Fixture appendix", "link": PUBLIC_URL + "?appendix=1",
                 "summary": "Second mock result"}]}})

        def mapped_read(targets: list[str]) -> str:
            """Return local fixture text; never make a network request to targets."""
            self.calls.append({"tool": "mapped_read", "targets": targets})
            return json.dumps({"pages": [{"body": WEB_REPORT}]})

        annotation_fields = ToolAnnotations.model_fields
        annotations = ToolAnnotations(**{
            "read_only_hint" if "read_only_hint" in annotation_fields else "readOnlyHint": True})
        for tool in (describe_image, mapped_search, mapped_read):
            server.add_tool(tool, annotations=annotations)
        self.socket = socket.socket()
        try:
            self.socket.bind(("127.0.0.1", 0))
            self.socket.listen(128)
            self.port = self.socket.getsockname()[1]
            self.server = uvicorn.Server(uvicorn.Config(
                app_factory(), host="127.0.0.1", port=self.port, log_level="error",
                access_log=False, timeout_graceful_shutdown=5))
            self.thread = threading.Thread(
                target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True)
        except BaseException:
            self.socket.close()
            raise

    def start(self):
        self.thread.start()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.server.started:
                return
            require(self.thread.is_alive(), "MCP fixture exited during startup")
            time.sleep(.05)
        raise TimeoutError("MCP fixture did not start within 20 seconds")

    def close(self):
        self.server.should_exit = True
        if self.thread.ident is not None:
            self.thread.join(8)
            if self.thread.is_alive():
                self.server.force_exit = True
                self.thread.join(3)
        self.socket.close()
        require(not self.thread.is_alive(), "Owned MCP fixture thread failed to stop")


class Harness:
    def __init__(self, args, report):
        self.args, self.report = args, report
        self.root = Path(tempfile.mkdtemp(prefix="zhishi-capabilities-"))
        self.name = "capabilities-disposable-" + uuid.uuid4().hex
        self.process = self.provider = self.mcp = self.log = None
        self.port = None
        self.config_id = None
        self.config = None
        self.key_refs = set()
        self.restart_count = 0
        self.image = png_fixture()
        report.update(temporary_root=str(self.root), checks=[], cleanup={},
                      image={"width": 768, "height": 512, "bytes": len(self.image)})

    def call(self, method, path, body=None, *, headers=None, timeout=45):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        if body is not None and not isinstance(body, bytes):
            body = json.dumps(body).encode()
        try:
            connection.request(method, path, body, headers or {"Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, response.read().decode(), response.getheader("Content-Type", "")
        finally:
            connection.close()

    def api(self, method, path, body=None, **kwargs):
        status, raw, _ = self.call(method, path, body, **kwargs)
        require(200 <= status < 300, f"{method} {path}: HTTP {status}: {raw[:1200]}")
        return json.loads(raw) if raw else None

    def start_backend(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        env = dict(os.environ, ZHISHI_DATA_DIR=str(self.root), PYTHONUTF8="1")
        env.pop("ZHISHI_FRONTEND_DIR", None)
        for key in list(env):
            if key.lower().endswith("_proxy"):
                env.pop(key)
        env["NO_PROXY"] = "127.0.0.1,localhost,::1"
        if self.args.source:
            env["PYTHONPATH"] = str(REPO / "src")
            command = [str(self.args.source.resolve()), "-m", "zhishi.server.app"]
        else:
            command = [str(self.args.backendexe.resolve())]
        self.log = (self.root / "backend.log").open("ab")
        self.process = subprocess.Popen(
            [*command, "--port", str(self.port)], cwd=self.root, env=env,
            stdout=self.log, stderr=self.log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + self.args.startup_timeout
        while time.monotonic() < deadline:
            require(self.process.poll() is None,
                    f"Backend exited during startup ({self.process.returncode})")
            try:
                health = self.api("GET", "/health", timeout=1)
                if health.get("ok"):
                    self.report["health"] = health
                    return
            except (OSError, AssertionError, ValueError):
                pass
            time.sleep(.2)
        raise TimeoutError("Backend startup timed out; see backend.log")

    def stop_backend(self):
        process = self.process
        if process is not None:
            try:
                if process.poll() is None:
                    try:
                        self.call("POST", "/shutdown", timeout=2)
                        process.wait(timeout=15)
                    except (OSError, subprocess.TimeoutExpired):
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                require(process.poll() is not None, "Owned backend process is still alive")
                self.report.setdefault("backend_exits", []).append(process.returncode)
            finally:
                if process.poll() is not None:
                    self.process = None
        if self.log:
            self.log.close()
            self.log = None

    def checkpoint_refs(self):
        database = self.root / "v2" / "backend.db"
        if not database.exists():
            return
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='ai_configs'").fetchone():
                return
            self.key_refs.update(ref for (ref,) in db.execute(
                "SELECT api_key_ref FROM ai_configs WHERE name = ?", (self.name,)) if ref)

    def setup(self):
        self.provider = Provider()
        self.provider.thread.start()
        self.mcp = MCPFixture()
        self.mcp.start()
        self.report["mcp_fixture"] = self.mcp.implementation
        self.start_backend()
        self.config = {"name": self.name, "provider_kind": "openai_compat", "model": "capabilities-qa",
                       "base_url": f"http://127.0.0.1:{self.provider.server_port}/v1",
                       "api_key": FAKE_KEY, "reasoning_effort": None}
        self.config_id = self.api("POST", "/ai/configs", self.config)["id"]
        self.checkpoint_refs()
        require(len(self.key_refs) == 1, "Disposable credential reference missing from fresh DB")
        self.api("POST", f"/ai/configs/{self.config_id}/enable")
        self.config["api_key"] = ""  # PUT must retain the existing key.
        self.edit(context_window=128000, max_output_tokens=777, input_modalities=["text", "image"])
        self.api("PUT", "/api/settings", {"settings": {"agent_autonomy": "careful"}})
        boundary = "capabilities-" + uuid.uuid4().hex
        multipart = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                     'filename="typical.png"\r\nContent-Type: image/png\r\n\r\n').encode()
        uploaded = self.api("POST", "/ai/attachments",
                            multipart + self.image + f"\r\n--{boundary}--\r\n".encode(),
                            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        require(uploaded["kind"] == "image", f"Upload did not classify PNG as image: {uploaded}")
        self.attachment_id = uploaded["file_id"]
        self.server_id = self.api("POST", "/ai/mcp/servers", {
            "name": self.name + "-mcp", "transport": "http",
            "url": f"http://127.0.0.1:{self.mcp.port}/mcp", "enabled": True,
            "auto_approve_readonly": True})["id"]
        tested = self.api("POST", f"/ai/mcp/servers/{self.server_id}/test")
        require(tested.get("ok") and tested.get("tool_count") == 3, f"MCP connection failed: {tested}")
        tools = self.api("GET", f"/ai/mcp/servers/{self.server_id}/tools")
        require(len(tools) == 3 and all(t.get("read_only") for t in tools),
                "MCP read_only_hint metadata did not survive the real transport")
        self.vision_config = {"enabled": True, "server_id": self.server_id,
                              "tool_name": "describe_image",
                              "arguments": {"image": "{{image_data_url}}", "prompt": "{{prompt}}"}}
        self.web_config = {"search_provider": "mcp", "fetch_provider": "mcp",
            "mcp_search": {"server_id": self.server_id, "tool_name": "mapped_search",
                           "query_argument": "needle", "limit_argument": "count",
                           "results_path": "payload.hits", "title_field": "heading",
                           "url_field": "link", "description_field": "summary"},
            "mcp_fetch": {"server_id": self.server_id, "tool_name": "mapped_read",
                          "url_argument": "targets", "url_as_list": True,
                          "content_path": "pages.0.body"}}
        self.api("PUT", "/ai/vision", self.vision_config)
        self.saved_web = self.api("PUT", "/ai/web-services", self.web_config)
        require(self.mcp.calls == [], "Saving/listing bindings executed a fixture tool")
        return {"config_id": self.config_id, "attachment_id": self.attachment_id,
                "mcp_tools": [t["name"] for t in tools]}

    def edit(self, **changes):
        self.config.update(changes)
        saved = self.api("PUT", f"/ai/configs/{self.config_id}", self.config)
        require(saved["enabled"] and saved["has_api_key"], "PUT lost enabled state or credential")
        for key in ("context_window", "max_output_tokens", "input_modalities", "reasoning_effort"):
            require(saved[key] == self.config[key], f"PUT did not persist {key}")
        require(FAKE_KEY not in json.dumps(saved), "Config API exposed disposable credential")
        return saved

    def chat(self, message="Inspect this fixture.", attachment=True, expect_error=False):
        before = len(self.provider.requests)
        status, raw, media_type = self.call("POST", "/ai/chat/stream", {
            "message": message, "attachment_ids": [self.attachment_id] if attachment else []})
        require(status == 200 and media_type.startswith("text/event-stream"),
                f"Chat must return SSE: {status} {raw[:1000]}")
        events = [json.loads(line[5:].strip()) for line in raw.splitlines()
                  if line.startswith("data:") and line[5:].strip() != "[DONE]"]
        require(events and events[0]["type"] == "run_started" and events[-1]["type"] == "done",
                f"Incomplete SSE lifecycle: {[e.get('type') for e in events]}")
        errors = [e for e in events if e["type"] == "run_error"]
        require(bool(errors) == expect_error, f"Unexpected SSE errors: {errors}")
        require(not any(e["type"] == "tool_approval_requested" for e in events),
                "Readonly fixture unexpectedly required approval")
        captured = self.provider.requests[before:]
        if not expect_error:
            require(len(captured) == 1, f"Expected one provider request, got {len(captured)}")
            wire = captured[0]
            require(wire["auth_ok"], "Provider did not receive the retained disposable key")
            require(wire["path"] == "/v1/chat/completions" and wire["body"].get("stream") is True,
                    "Provider request was not OpenAI Chat streaming")
            body = wire["body"]
            require(body.get("max_tokens", body.get("max_completion_tokens")) == self.config["max_output_tokens"],
                    "Configured maximum output tokens missing or wrong on actual provider wire")
            require(body.get("model") == self.config["model"], "Wrong provider model")
            require(body.get("reasoning_effort") == self.config["reasoning_effort"],
                    "Configured thinking effort missing or wrong on provider wire")
            if self.config["reasoning_effort"] is None:
                require("reasoning_effort" not in body, "Default thinking should omit the parameter")
        return events, [c["body"] for c in captured]

    def native_image(self):
        self.edit(context_window=128000, max_output_tokens=777, input_modalities=["text", "image"], reasoning_effort='high')
        before = len(self.mcp.calls)
        _, requests = self.chat()
        urls = image_urls(requests[0])
        require(len(urls) == 1 and urls[0].startswith("data:image/png;base64,"),
                "Native image did not reach provider as one image_url")
        require(base64.b64decode(urls[0].split(",", 1)[1], validate=True) == self.image,
                "Provider image differs from multipart upload")
        require(len(self.mcp.calls) == before, "Native image unnecessarily invoked vision MCP")
        require(bool(requests[0].get("tools")), "Budget test did not include actual tool schemas")
        return {"context_window": 128000, "wire_max_output_tokens": 777,
                "image_bytes": len(self.image), "image_sha256": hashlib.sha256(self.image).hexdigest(),
                "wire_tools": len(requests[0]["tools"]), "provider_calls": 1, "vision_calls": 0}

    def vision_image(self):
        self.edit(context_window=128000, max_output_tokens=555, input_modalities=["text"])
        self.api("PUT", "/ai/vision", self.vision_config)
        before = len(self.mcp.calls)
        prompt = "Describe the attachment via the configured vision reader."
        events, requests = self.chat(prompt)
        called = self.mcp.calls[before:]
        require(len(called) == 1 and called[0]["tool"] == "describe_image",
                f"Vision MCP must execute exactly once, got {len(called)} calls")
        require(called[0]["prompt"] == prompt, "Vision prompt template mapping was not applied")
        require(base64.b64decode(called[0]["image"].split(",", 1)[1], validate=True) == self.image,
                "Vision MCP received a different attachment")
        require_text_only(requests[0])
        require(VISION_REPORT in message_text(requests[0]), "Provider text omitted mock read report")
        return {"vision_calls": 1, "provider_calls": 1, "provider_text_only": True,
                "event_types": sorted({e["type"] for e in events})}

    def missing_vision(self):
        self.edit(context_window=128000, max_output_tokens=555, input_modalities=["text"])
        self.api("DELETE", "/ai/vision")
        try:
            before = len(self.mcp.calls)
            events, requests = self.chat()
            require(len(self.mcp.calls) == before, "Missing vision binding still invoked MCP")
            require_text_only(requests[0])
            text = message_text(requests[0])
            require("附件内容未读取" in text and "未启用视觉 MCP" in text,
                    "Provider was not given a clear unread-image limitation")
            require(VISION_REPORT not in text, "Missing vision binding reused an unrelated report")
            # Verify the real UI API exposes unread media metadata, independently of fake model wording.
            cid = events[0]["conversation_id"]
            messages = self.api("GET", f"/ai/conversations/{cid}")
            display = json.dumps([m["display"] for m in messages], ensure_ascii=False)
            require("未读取" in display, "Conversation API omitted the unread limitation")
            return {"vision_calls": 0, "provider_text_only": True, "unread_notice": True}
        finally:
            self.api("PUT", "/ai/vision", self.vision_config)

    def web_routes(self):
        before = len(self.mcp.calls)
        provider_before = len(self.provider.requests)
        result = self.api("POST", "/ai/web-services/search", {"query": "fixture search", "max_results": 1})
        require(result == [{"title": "Fixture guide", "url": PUBLIC_URL,
                            "description": "Mock search summary"}],
                f"Search field mapping/normalization/limit failed: {result}")
        fetched = self.api("POST", "/ai/web-services/fetch", {"url": PUBLIC_URL})
        require(fetched == {"ok": True, "url": PUBLIC_URL, "content": WEB_REPORT},
                f"Reader mapping/normalization failed: {fetched}")
        require(self.mcp.calls[before:] == [
            {"tool": "mapped_search", "needle": "fixture search", "count": 1},
            {"tool": "mapped_read", "targets": [PUBLIC_URL]}],
            "Web API did not route exactly once per operation with configured arguments")
        require(len(self.provider.requests) == provider_before, "Web API unnecessarily invoked provider")
        require(self.api("GET", "/ai/web-services") == self.saved_web,
                "Web requests mutated the saved provider/bindings")
        return {"search_calls": 1, "read_calls": 1, "normalized": True, "url": PUBLIC_URL}

    def restart(self):
        self.edit(context_window=128000, max_output_tokens=555, input_modalities=["text"])
        refs = set(self.key_refs)
        self.stop_backend()
        self.start_backend()
        self.restart_count += 1
        configs = self.api("GET", "/ai/configs")
        require(len(configs) == 1, "Fresh database configuration count changed after restart")
        saved = configs[0]
        for key in ("name", "model", "base_url", "provider_kind", "context_window",
                    "max_output_tokens", "input_modalities", "reasoning_effort"):
            require(saved[key] == self.config[key], f"Restart lost config field: {key}")
        require(saved["id"] == self.config_id and saved["enabled"] and saved["has_api_key"],
                "Restart lost active configuration or credential")
        self.checkpoint_refs()
        require(self.key_refs == refs, "Blank-key PUT/restart changed the credential reference")
        require(self.api("GET", "/ai/vision") == self.vision_config, "Restart lost vision binding")
        require(self.api("GET", "/ai/web-services") == self.saved_web, "Restart lost web binding")
        servers = self.api("GET", "/ai/mcp/servers")
        require(len(servers) == 1 and servers[0]["enabled"] and servers[0]["auto_approve_readonly"],
                "Restart lost active MCP server/readonly consent")
        # Exercise retained consent before re-saving anything (fingerprint persistence).
        before = len(self.mcp.calls)
        _, requests = self.chat()
        require_text_only(requests[0])
        require(VISION_REPORT in message_text(requests[0]), "Retained vision binding was not usable")
        require(len(self.mcp.calls[before:]) == 1
                and self.mcp.calls[before]["tool"] == "describe_image", "Retained vision call count != 1")
        self.web_routes()
        return {"restart_count": self.restart_count, "active_config_retained": True,
                "credential_ref_retained": True, "vision_and_web_called_without_resave": True}

    def tiny_context(self):
        self.edit(context_window=1024, max_output_tokens=128, input_modalities=["text"])
        try:
            before = len(self.mcp.calls)
            events, requests = self.chat("Hi.", attachment=False, expect_error=True)
            require(requests == [], "Tiny context reached provider before budget rejection")
            require(len(self.mcp.calls) == before, "Tiny context executed a tool")
            error = "\n".join(e.get("message", "") for e in events if e["type"] == "run_error")
            require("上下文超限" in error and "tokens" in error
                    and "缩短" in error and "更大的模型" in error,
                    f"Context SSE error lacks actionable budget guidance: {error}")
            return {"context_window": 1024, "wire_provider_calls": 0,
                    "short_prompt": "Hi.", "error": error}
        finally:
            self.edit(context_window=128000, max_output_tokens=555, input_modalities=["text"])

    def check(self, name, operation):
        started = time.monotonic()
        record = {"name": name}
        self.report["checks"].append(record)
        try:
            record["evidence"] = operation()
            record["status"] = "pass"
        except Exception as exc:  # noqa: BLE001 -- record each QA failure and still clean up
            record.update(status="fail", error=f"{type(exc).__name__}: {exc}")
        record["seconds"] = round(time.monotonic() - started, 3)
        print(f"{record['status'].upper()} {name}", flush=True)
        if record["status"] == "fail":
            print(record["error"][:1800], flush=True)
        return record["status"] == "pass"

    def cleanup(self):
        errors = []

        def attempt(label, operation):
            try:
                operation()
            except Exception as exc:  # noqa: BLE001 -- attempt every independent cleanup action
                errors.append(f"{label}: {type(exc).__name__}: {exc}")

        attempt("backend", self.stop_backend)
        if self.mcp is not None:
            attempt("mcp", self.mcp.close)
        if self.provider is not None:
            def close_provider():
                if self.provider.thread.ident is not None:
                    self.provider.shutdown()
                    self.provider.thread.join(3)
                self.provider.server_close()
                require(not self.provider.thread.is_alive(), "Provider thread did not stop")
            attempt("provider", close_provider)
        attempt("credential references", self.checkpoint_refs)
        # These refs originate exclusively from the random-named config in this temp DB.
        # Use keyring directly because production delete_api_key intentionally hides errors.
        deleted = []
        for ref in sorted(self.key_refs):
            def delete_owned_key(ref=ref):
                import keyring
                sys.path.insert(0, str(REPO / "src"))
                from zhishi.infra.secrets import _SERVICE
                value = keyring.get_password(_SERVICE, ref)
                require(value in (None, FAKE_KEY), "Ref points to a non-fixture key; refusing deletion")
                if value is not None:
                    keyring.delete_password(_SERVICE, ref)
                require(keyring.get_password(_SERVICE, ref) is None, "Disposable key still exists")
                deleted.append(ref)
            attempt("disposable credential", delete_owned_key)
        failed = any(c["status"] == "fail" for c in self.report["checks"])
        if failed or errors:
            log = self.root / "backend.log"
            if log.exists():
                with log.open("rb") as stream:
                    stream.seek(max(0, log.stat().st_size - 12000))
                    self.report["backend_log_tail"] = stream.read().decode("utf-8", errors="replace")
        # Root was produced by mkdtemp; resolve and check containment before recursive removal.
        def remove_temp():
            resolved = self.root.resolve(strict=True)
            require(resolved.parent == Path(tempfile.gettempdir()).resolve()
                    and resolved.name.startswith("zhishi-capabilities-"), "Unexpected cleanup target")
            shutil.rmtree(resolved)
        if not errors:
            attempt("temporary data", remove_temp)
        self.report["cleanup"] = {"ok": not errors, "errors": errors,
            "credentials_found": len(self.key_refs), "credentials_deleted_verified": len(deleted),
            "temporary_data_removed": not self.root.exists()}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("backendexe", type=Path, nargs="?", help="Frozen backend executable")
    parser.add_argument("--source", type=Path, metavar="PYTHON", help="Run source backend CLI with this Python")
    parser.add_argument("--report", type=Path, help="Write machine-readable JSON, including cleanup results")
    parser.add_argument("--startup-timeout", type=float, default=60)
    args = parser.parse_args()
    if bool(args.backendexe) == bool(args.source):
        parser.error("Supply either backendexe or --source PYTHON")
    if not (args.backendexe or args.source).is_file():
        parser.error("Backend executable / source Python does not exist")
    if args.startup_timeout <= 0:
        parser.error("--startup-timeout must be positive")
    report = {"schema_version": 1, "mode": "source" if args.source else "frozen",
              "target": str((args.source or args.backendexe).resolve()),
              "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    harness = Harness(args, report)
    started = time.monotonic()
    try:
        if harness.check("setup_real_api_and_readonly_mcp", harness.setup):
            for name, operation in (
                ("native_image_128k_and_output_wire", harness.native_image),
                ("text_only_vision_mcp_exactly_once", harness.vision_image),
                ("text_only_without_vision_clear_unread", harness.missing_vision),
                ("web_mcp_mapping_normalization", harness.web_routes),
                ("put_persist_restart_retained_active", harness.restart),
                ("tiny_context_tool_overhead_preprovider_sse", harness.tiny_context),
            ):
                harness.check(name, operation)
    except KeyboardInterrupt:
        report["interrupted"] = True
    finally:
        harness.cleanup()
        report["seconds"] = round(time.monotonic() - started, 3)
        report["ok"] = (not report.get("interrupted") and len(report["checks"]) == 7
                        and all(c["status"] == "pass" for c in report["checks"])
                        and report["cleanup"]["ok"])
        if args.report:
            args.report.resolve().parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("CAPABILITIES_QA_" + ("PASS" if report["ok"] else "FAIL")
              + f" mode={report['mode']} cleanup={report['cleanup']['ok']}", flush=True)
        if not report["cleanup"]["ok"]:
            print(json.dumps(report["cleanup"], ensure_ascii=False), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
