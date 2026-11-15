"""Inventaur Inc. authenticated loopback bridge for one isolated Solid Edge MCP session."""
from __future__ import annotations

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"

import hmac, json, os, queue, shutil, subprocess, sys, tempfile, threading, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

MCP_ROOT = Path(__file__).resolve().parent
ROOT = MCP_ROOT
MCP_EXE = MCP_ROOT / "runtime" / "win-x64" / "control" / "solidedge-mcp.exe"
EVENT_MCP_EXE = MCP_ROOT / "runtime" / "win-x64" / "events" / "solidedge-event-mcp.exe"
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Rhino3DToSolidEdge" / "SolidEdgeMcp"
STATE_FILE = STATE_DIR / "bridge.json"
LOG_FILE = STATE_DIR / "bridge.log"
IDLE_SECONDS = 1800
MAX_BODY = 4 * 1024 * 1024

READ_TOOLS = {
    "se_get_document", "se_batch_read", "se_read_collection", "se_read_geometry", "se_get_selection",
    "se_find_paths", "se_describe_object", "se_get_variables", "se_view_context",
    "se_walk_object", "se_assembly_query", "se_validate_features", "se_snapshot_diff",
    "se_capture_viewport",
}
WRITE_TOOLS = {
    "se_open_document", "se_close_document", "se_new_document", "se_invoke_chain",
    "se_invoke_member", "se_model_build", "se_recipe_run", "se_assembly_build", "se_create_drawing_view",
    "se_snapshot_diff",
}
DENIED_TOOLS = {"se_script_run"}
EVENT_TOOLS = {"se_get_events", "se_wait_event", "se_set_event_filter", "se_event_status"}


def log(message: str) -> None:
    """Perform the log operation implemented by this module. Inputs: message. Direct side-effect indicators: may read/write local files. Direct helpers/dependencies: STATE_DIR.mkdir, open, f.write, time.strftime, message.replace('\r', ' ').replace, message.replace."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + message.replace("\r", " ").replace("\n", " ") + "\n")


class McpStdioClient:
    """Route the selected command-line/utility operation. Direct side-effect indicators: may read/write local files. Direct helpers/dependencies: os.environ.copy, open, queue.Queue, threading.Lock, threading.Thread, self.reader.start. Return paths include: self.rpc('tools/call', {'name': name, 'arguments': arguments}, timeout=time; True; False. Explicit failures include: FileNotFoundError(f'Built {name} MCP executable missing: {executable}', RuntimeError('MCP server is not running'), RuntimeError(f'{name} MCP tool inventory mismatch; missing=' + ','.joi, RuntimeError(f'MCP server exited with code {self.proc.poll()}')."""
    def __init__(self, executable: Path = MCP_EXE, expected_tools: set[str] | None = None, name: str = "control", event_server: bool = False, extra_env: dict[str, str] | None = None) -> None:
        """Validate the executable path, initialise protocol queues and prepare the child-process lifecycle."""
        if not executable.is_file():
            raise FileNotFoundError(f"Built {name} MCP executable missing: {executable}")
        env = os.environ.copy()
        # Self-contained MCP executables carry their .NET runtime beside the apphost.
        # Remove global overrides so an unrelated system/per-user DOTNET_ROOT cannot hijack startup.
        env.pop("DOTNET_ROOT", None)
        env.pop("DOTNET_ROOT_X64", None)
        if not event_server:
            env["SE_MCP_MODE"] = "engineer"
            env["SE_MCP_LAUNCH_IF_NEEDED"] = "1"
            env["SE_MCP_FORCE_ISOLATED"] = "1"
            env["SE_MCP_LAUNCH_VISIBLE"] = "0"
            env["SE_MCP_TIMEOUT_SECONDS"] = os.environ.get("SE_MCP_TIMEOUT_SECONDS", "180")
            env["SE_MCP_SCRIPT_ALLOW_FILE"] = "0"
            # Preserve an operator-configured global read-only mode; never override it.
            env.setdefault("SE_MCP_READONLY", "0")
            env.setdefault("SE_RP_MODE", "off")
        if extra_env:
            env.update(extra_env)
        self.log_handle = open(LOG_FILE, "ab")
        try:
            self.proc = subprocess.Popen(
                [str(executable)], cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self.log_handle, text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            self.log_handle.close()
            raise
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.lock = threading.Lock()
        self.next_id = 0
        self.reader = threading.Thread(target=self._read_stdout, name="se-mcp-stdout", daemon=True)
        self.reader.start()
        self.info: dict[str, Any] = {}
        try:
            self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "Rhino3DToSolidEdge-Bridge", "version": "1.0"}}, timeout=60)
            self.notify("notifications/initialized", {})
            result = self.rpc("tools/list", {}, timeout=60)
            tools = result.get("tools", [])
            names = {t.get("name") for t in tools if isinstance(t, dict)}
            expected = expected_tools if expected_tools is not None else (READ_TOOLS | WRITE_TOOLS | DENIED_TOOLS)
            missing = sorted(expected - names)
            if missing:
                raise RuntimeError(f"{name} MCP tool inventory mismatch; missing=" + ",".join(missing))
            self.tools = tools
            self.info = {"tool_count": len(tools), "tool_names": sorted(names), "mcp_pid": self.proc.pid, "mode": env.get("SE_MCP_MODE") if not event_server else "events", "readonly": env.get("SE_MCP_READONLY") == "1"}
            log(f"MCP_READY name={name} pid={self.proc.pid} tool_count={len(tools)} readonly={self.info['readonly']}")
        except Exception:
            self.close()
            raise

    def _read_stdout(self) -> None:
        """Collect complete JSON-RPC messages from the MCP subprocess stdout stream."""
        try:
            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                self.lines.put(line)
        except Exception as exc:
            log(f"MCP_STDOUT_READER_ERROR {type(exc).__name__}: {exc}")
        finally:
            self.lines.put(None)

    def notify(self, method: str, params: dict[str, Any]) -> None:
        """Perform the notify operation implemented by this module. Inputs: method, params. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Direct helpers/dependencies: self.proc.stdin.write, self.proc.stdin.flush, RuntimeError, self.proc.poll, json.dumps. Explicit failures include: RuntimeError('MCP server is not running')."""
        if self.proc.poll() is not None or self.proc.stdin is None:
            raise RuntimeError("MCP server is not running")
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params}, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def rpc(self, method: str, params: dict[str, Any], timeout: float = 90) -> dict[str, Any]:
        """Perform the rpc operation implemented by this module. Inputs: method, params, timeout. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Direct helpers/dependencies: self.proc.stdin.write, self.proc.stdin.flush, RuntimeError, time.monotonic, max, message.get. Return paths include: result if isinstance(result, dict) else {'result': result}; {'isError': True, 'error': message['error']}. Explicit failures include: RuntimeError(f'MCP server exited with code {self.proc.poll()}'), TimeoutError(f'UNKNOWN_OUTCOME: {method} request id {request_id} was s, RuntimeError(f'MCP stdout closed; process_exit={self.proc.poll()}'), TimeoutError(f'UNKNOWN_OUTCOME: {method} request id {request_id} was s."""
        with self.lock:
            if self.proc.poll() is not None or self.proc.stdin is None:
                raise RuntimeError(f"MCP server exited with code {self.proc.poll()}")
            self.next_id += 1
            request_id = self.next_id
            payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            # Once sent, a timeout is UNKNOWN_OUTCOME. Never retry the same mutation automatically.
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            deadline = time.monotonic() + max(1.0, min(float(timeout), 600.0))
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"UNKNOWN_OUTCOME: {method} request id {request_id} was sent but no response arrived before timeout; do not replay automatically")
                try:
                    line = self.lines.get(timeout=remaining)
                except queue.Empty:
                    raise TimeoutError(f"UNKNOWN_OUTCOME: {method} request id {request_id} was sent but no response arrived before timeout; do not replay automatically")
                if line is None:
                    raise RuntimeError(f"MCP stdout closed; process_exit={self.proc.poll()}")
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    log("MCP_NON_JSON_STDOUT " + line[:500])
                    continue
                if message.get("id") == request_id:
                    if "error" in message:
                        return {"isError": True, "error": message["error"]}
                    result = message.get("result", {})
                    return result if isinstance(result, dict) else {"result": result}
                # Notifications and unrelated messages are not replayed; they are only logged.
                if message.get("method"):
                    log("MCP_NOTIFICATION " + str(message.get("method")))

    def call_tool(self, name: str, arguments: dict[str, Any], timeout: float = 210) -> dict[str, Any]:
        """Perform the call tool operation implemented by this module. Inputs: name, arguments, timeout. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Direct helpers/dependencies: self.rpc. Return paths include: self.rpc('tools/call', {'name': name, 'arguments': arguments}, timeout=time."""
        return self.rpc("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)

    def close(self) -> bool:
        """Stop, close, remove or disable the selected resource/workflow. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Direct helpers/dependencies: self.proc.wait, log, self.proc.stdin.close, self.log_handle.close. Return paths include: True; False."""
        try:
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=30)
            log(f"MCP_GRACEFUL_EXIT pid={self.proc.pid} code={self.proc.returncode}")
            try:
                self.log_handle.close()
            except Exception:
                pass
            return True
        except subprocess.TimeoutExpired:
            log(f"MCP_SHUTDOWN_UNVERIFIED pid={self.proc.pid}; process left alive rather than risking unrelated CAD process termination")
            return False


class BridgeState:
    """Perform the BridgeState operation implemented by this module. Direct side-effect indicators: may read/write local files. Direct helpers/dependencies: str, int, McpStdioClient, self._start_event_client_safely, time.monotonic, threading.Event. Return paths include: None; event_clean and control_clean; parsed."""
    def __init__(self, config: dict[str, Any]) -> None:
        """Load the run-scoped token, executable paths, isolation profile and process ownership metadata."""
        self.token = str(config["token"])
        self.port = int(config["port"])
        self.client = McpStdioClient()
        self.event_client: McpStdioClient | None = None
        self.event_target_verified = False
        self.event_probe_path: Path | None = None
        # CAD conversion does not require the event MCP. Keep the background
        # bridge single-purpose and opt-in to events so duplicate event-server
        # instances cannot destabilize the control bridge.
        if os.environ.get("SE_MCP_ENABLE_EVENTS", "0").strip().lower() in {"1", "true", "yes"}:
            self._start_event_client_safely()
        else:
            log("EVENT_MCP_DISABLED reason=CAD_headless_workflow_default")
        self.last_activity = time.monotonic()
        self.shutdown_requested = threading.Event()
        self.server: ThreadingHTTPServer | None = None
        self.timer = threading.Thread(target=self._idle_monitor, name="se-bridge-idle", daemon=True)
        self.timer.start()

    @staticmethod
    def _json_tool_payload(result: dict[str, Any]) -> dict[str, Any] | None:
        """Extract JSON text from an MCP result while ignoring image and other non-text content blocks."""
        for item in result.get("content", []) if isinstance(result, dict) else []:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                try:
                    parsed = json.loads(item["text"])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue
        return None

    def _start_event_client_safely(self) -> None:
        # The event server normally attaches through COM ROT. Before allowing it to
        # subscribe, prove that it sees a unique document opened by our forced-isolated
        # control process; otherwise it stays fenced and cannot observe the operator's app.
        # Event subscription is optional. Prefer an explicit operator override;
        # otherwise discover the probe document under installed Solid Edge versions.
        """Start the optional event MCP client only after validating its target template and process ownership."""
        configured_template = os.environ.get("SE_EVENT_PROBE_TEMPLATE")
        if configured_template:
            template = Path(configured_template).expanduser().resolve()
        else:
            roots = [Path(value) for value in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")) if value]
            candidates = []
            for root in roots:
                candidates.extend(path for path in (root / "Siemens").glob("Solid Edge */Training/bar.par") if path.is_file())
            template = max(candidates, key=lambda path: tuple(int(part) for part in __import__("re").findall(r"\d+", path.parents[1].name))) if candidates else Path()
        if not template.is_file() or not EVENT_MCP_EXE.is_file():
            log("EVENT_MCP_DISABLED reason=missing_event_binary_or_probe_template")
            return
        try:
            fd, name = tempfile.mkstemp(prefix="Rhino3DToSolidEdge_EventProbe_", suffix=".par")
            os.close(fd)
            self.event_probe_path = Path(name)
            shutil.copy2(template, self.event_probe_path)
            opened = self.client.call_tool("se_open_document", {"path": str(self.event_probe_path), "readOnly": True}, timeout=60)
            payload = self._json_tool_payload(opened)
            if not payload or payload.get("status") != "ok" or not payload.get("handle"):
                log("EVENT_MCP_DISABLED reason=isolated_probe_open_not_verified result=" + json.dumps(payload or {"isError": opened.get("isError")}, ensure_ascii=False)[:500])
                # Preserve the exact probe artifact if the open outcome is uncertain.
                if not opened.get("isError") and payload is None:
                    self.event_probe_path = None
                return
            probe_handle = str(payload["handle"])
            self.event_client = McpStdioClient(EVENT_MCP_EXE, EVENT_TOOLS, "events", event_server=True,
                                               extra_env={"SE_EVENT_MCP_EXPECT_DOC": self.event_probe_path.name})
            status_result = self.event_client.call_tool("se_event_status", {}, timeout=20)
            status_payload = self._json_tool_payload(status_result) or {}
            connected_document = Path(str(status_payload.get("document", ""))).name
            self.event_target_verified = bool(status_payload.get("connected")) and connected_document.casefold() == self.event_probe_path.name.casefold()
            if not self.event_target_verified:
                log("EVENT_MCP_FENCED reason=isolated_target_not_proven status=" + json.dumps(status_payload, ensure_ascii=False)[:700])
            else:
                log("EVENT_MCP_TARGET_VERIFIED document=" + self.event_probe_path.name)
            closed = self.client.call_tool("se_close_document", {"target": probe_handle, "confirm": True}, timeout=30)
            close_payload = self._json_tool_payload(closed)
            if close_payload and close_payload.get("status") == "ok":
                self.event_probe_path.unlink(missing_ok=True)
                self.event_probe_path = None
                log("EVENT_MCP_PROBE_CLOSED_AND_REMOVED")
            else:
                log("EVENT_MCP_PROBE_CLEANUP_UNVERIFIED result=" + json.dumps(close_payload or {"isError": closed.get("isError")}, ensure_ascii=False)[:500])
        except Exception as exc:
            log(f"EVENT_MCP_DISABLED {type(exc).__name__}: {exc}; no event calls will be routed until target identity is proven")
            if self.event_client is not None:
                self.event_client.close()
                self.event_client = None
            self.event_target_verified = False

    def touch(self) -> None:
        """Perform the touch operation implemented by this module. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Direct helpers/dependencies: time.monotonic."""
        self.last_activity = time.monotonic()

    def _idle_monitor(self) -> None:
        """Stop this isolated bridge after its idle period without touching unrelated Solid Edge sessions."""
        while not self.shutdown_requested.wait(10):
            if time.monotonic() - self.last_activity >= IDLE_SECONDS:
                log("IDLE_TIMEOUT reached; requesting graceful shutdown")
                self.shutdown_requested.set()
                if self.server is not None:
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                return

    def close(self) -> bool:
        """Stop, close, remove or disable the selected resource/workflow. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Direct helpers/dependencies: self.shutdown_requested.set, self.client.close, self.event_client.close. Return paths include: event_clean and control_clean."""
        self.shutdown_requested.set()
        event_clean = self.event_client.close() if self.event_client is not None else True
        control_clean = self.client.close()
        return event_clean and control_clean


class Handler(BaseHTTPRequestHandler):
    """Perform the Handler operation implemented by this module. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Direct helpers/dependencies: log, self.headers.get, json.dumps(payload, ensure_ascii=False).encode, self.send_response, self.send_header, self.end_headers. Return paths include: self.server.bridge_state; bool(supplied) and hmac.compare_digest(supplied, self.state.token)."""
    server_version = "Rhino3DToSolidEdgeBridge/1.0"

    @property
    def state(self) -> BridgeState:
        """Perform the state operation implemented by this module. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Return paths include: self.server.bridge_state."""
        return self.server.bridge_state  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        """Perform the log message operation implemented by this module. Inputs: fmt. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Direct helpers/dependencies: log."""
        log("HTTP " + (fmt % args))

    def _authorized(self) -> bool:
        "Validate the caller's token using constant-time comparison before serving a bridge request."
        supplied = self.headers.get("X-CAD-Bridge-Token", "")
        return bool(supplied) and hmac.compare_digest(supplied, self.state.token)

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        """Serialize a UTF-8 JSON response with an explicit content type and response length."""
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        """Read or inspect the requested resource/state. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Direct helpers/dependencies: self.state.touch, self._send, self._authorized, os.getpid."""
        if not self._authorized():
            self._send(403, {"ok": False, "code": "AUTH_FAILED", "message": "Invalid local bridge token."})
            return
        if self.path != "/health":
            self._send(404, {"ok": False, "code": "NOT_FOUND"})
            return
        self.state.touch()
        event_info = self.state.event_client.info if self.state.event_client is not None else {"available": False, "reason": "event server did not pass isolated-target verification"}
        self._send(200, {"ok": True, "service": "Inventaur Inc. Rhino3D to Solid Edge MCP bridge", "pid": os.getpid(), **self.state.client.info, "event_server": event_info, "event_target_verified": self.state.event_target_verified})

    def do_POST(self) -> None:
        """Perform the do POST operation implemented by this module. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Direct helpers/dependencies: self._authorized, self._send, int, self.state.touch, body.get, self.state.client.call_tool."""
        if not self._authorized():
            self._send(403, {"ok": False, "code": "AUTH_FAILED", "message": "Invalid local bridge token."})
            return
        if self.path not in {"/tools/call", "/events/call", "/shutdown"}:
            self._send(404, {"ok": False, "code": "NOT_FOUND"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_BODY:
                self._send(413, {"ok": False, "code": "BODY_TOO_LARGE"})
                return
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if not isinstance(body, dict):
                self._send(400, {"ok": False, "code": "INVALID_BODY"})
                return
            self.state.touch()
            if self.path == "/shutdown":
                self._send(200, {"ok": True, "shutdown_requested": True, "mcp_pid": self.state.client.proc.pid})
                self.state.shutdown_requested.set()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            tool = body.get("tool")
            args = body.get("arguments", {})
            if self.path == "/events/call":
                if not isinstance(tool, str) or tool not in EVENT_TOOLS or not isinstance(args, dict):
                    self._send(403, {"ok": False, "code": "EVENT_TOOL_DENIED", "message": "Only the four allowlisted event MCP tools accept an object arguments payload."})
                    return
                if self.state.event_client is None or not self.state.event_target_verified:
                    self._send(503, {"ok": False, "code": "EVENT_TARGET_UNVERIFIED", "message": "Event MCP is fenced because it has not proven attachment to the bridge-owned isolated Solid Edge instance."})
                    return
                result = self.state.event_client.call_tool(tool, args, timeout=90)
                self._send(200, {"ok": True, "tool_result": result})
                return
            access = body.get("access")
            if not isinstance(tool, str) or not isinstance(args, dict):
                self._send(400, {"ok": False, "code": "INVALID_TOOL_REQUEST", "message": "tool must be a string and arguments an object."})
                return
            if tool in DENIED_TOOLS:
                self._send(403, {"ok": False, "code": "TOOL_DENIED", "message": "Arbitrary C# execution is disabled through the Registry bridge."})
                return
            if access == "read" and tool not in READ_TOOLS:
                self._send(403, {"ok": False, "code": "READ_ALLOWLIST_DENIED", "message": f"{tool} is not read-only."})
                return
            if access == "write" and tool not in WRITE_TOOLS:
                self._send(403, {"ok": False, "code": "WRITE_ALLOWLIST_DENIED", "message": f"{tool} is not in the write allowlist."})
                return
            if access not in {"read", "write"}:
                self._send(400, {"ok": False, "code": "INVALID_ACCESS_CLASS"})
                return
            if tool == "se_snapshot_diff":
                action = str(args.get("action", "save")).lower()
                if (access == "read" and action not in {"diff", "list"}) or (access == "write" and action not in {"save", "drop"}):
                    self._send(403, {"ok": False, "code": "ACTION_ALLOWLIST_DENIED", "message": "snapshot diff/list are read; save/drop are write."})
                    return
            result = self.state.client.call_tool(tool, args, timeout=210)
            self._send(200, {"ok": True, "tool_result": result})
        except TimeoutError as exc:
            self._send(200, {"ok": False, "code": "UNKNOWN_OUTCOME", "message": str(exc)})
        except Exception as exc:
            log(f"REQUEST_ERROR {type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}")
            self._send(500, {"ok": False, "code": "BRIDGE_REQUEST_FAILED", "message": f"{type(exc).__name__}: {str(exc)[:500]}"})


def _load_config() -> dict[str, Any]:
    """Read and validate the persisted bridge configuration and run-scoped access token."""
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("token"), str):
        raise ValueError("bridge state file invalid")
    port = int(data.get("port", 0))
    if not 1024 <= port <= 65535:
        raise ValueError("bridge port invalid")
    return {"token": data["token"], "port": port}


def main() -> int:
    """Route the selected command-line/utility operation. Direct side-effect indicators: may read/write local files. Direct helpers/dependencies: STATE_DIR.mkdir, print, _load_config, Server, BridgeState, log. Return paths include: 2; 0; 1."""
    if "--serve" not in sys.argv:
        print("Usage: inventaur_bridge_daemon.py --serve")
        return 2
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        config = _load_config()
        class Server(ThreadingHTTPServer):
            """Own the loopback HTTP server lifecycle and expose only the authenticated Inventaur bridge handler."""
            daemon_threads = True
            allow_reuse_address = False
        # Bind loopback before starting Solid Edge, so a port collision cannot launch CAD.
        server = Server(("127.0.0.1", int(config["port"])), Handler)
        state = None
        try:
            state = BridgeState(config)
            server.bridge_state = state  # type: ignore[attr-defined]
            state.server = server
            event_pid = state.event_client.proc.pid if state.event_client is not None else None
            log(f"BRIDGE_READY pid={os.getpid()} port={state.port} mcp_pid={state.client.proc.pid} event_mcp_pid={event_pid} event_target_verified={state.event_target_verified}")
            server.serve_forever(poll_interval=0.5)
        finally:
            server.server_close()
            if state is not None:
                clean = state.close()
                if not clean:
                    log("BRIDGE_EXIT_WITH_MCP_STILL_RUNNING; inspect process and logs")
        return 0
    except Exception as exc:
        log(f"BRIDGE_FATAL {type(exc).__name__}: {exc}\n{traceback.format_exc()[-3000:]}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
