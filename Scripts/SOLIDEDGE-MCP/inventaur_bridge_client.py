"""Inventaur Inc. | the local CAD bridge capabilities for the persistent Solid Edge MCP bridge.

The bridge is opt-in: call start() to create a hidden, MCP-owned Solid Edge instance.
Read/write tool calls never silently restart the service. Mutating calls are separately
registered as confirmation-gated Registry capabilities and are re-guarded by the MCP.
"""
from __future__ import annotations

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"

import json, os, secrets, socket, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path
from inventaur_process_policy import background_python, hidden_subprocess_kwargs
from typing import Any

MCP_ROOT = Path(__file__).resolve().parent
ROOT = MCP_ROOT
DAEMON = MCP_ROOT / "inventaur_bridge_daemon.py"
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Rhino3DToSolidEdge" / "SolidEdgeMcp"
STATE_FILE = STATE_DIR / "bridge.json"
LOCK_FILE = STATE_DIR / "bridge-start.lock"
DEFAULT_PORT = 39742
START_TIMEOUT_SECONDS = 120

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


def _state(create: bool = False) -> dict[str, Any] | None:
    "Read the bridge's per-user state file and optionally initialise its containing directory."
    if not STATE_FILE.exists():
        if not create:
            return None
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        data = {"port": DEFAULT_PORT, "token": secrets.token_urlsafe(32), "schema": 1}
        temp = STATE_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(temp, STATE_FILE)
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("token"), str) or not data.get("token"):
            return None
        port = int(data.get("port", DEFAULT_PORT))
        if not 1024 <= port <= 65535:
            return None
        return {"port": port, "token": data["token"], "schema": int(data.get("schema", 1))}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


'Send one authenticated HTTP request to the loopback bridge and validate the JSON response.'
def _request(method: str, path: str, payload: dict[str, Any] | None = None, timeout: float = 3.0) -> dict[str, Any]:
    """Send one authenticated HTTP request to the loopback bridge and validate its JSON response."""
    state = _state(create=False)
    if state is None:
        return {"ok": False, "code": "BRIDGE_NOT_CONFIGURED", "message": "Bridge has not been initialized. Start the local Solid Edge bridge."}
    url = f"http://127.0.0.1:{state['port']}{path}"
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"X-CAD-Bridge-Token": state["token"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=max(0.5, min(float(timeout), 240.0))) as resp:
            raw = resp.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                return {"ok": False, "code": "BRIDGE_RESPONSE_TOO_LARGE", "message": "Bridge response exceeded 4 MiB."}
            result = json.loads(raw.decode("utf-8")) if raw else {}
            return result if isinstance(result, dict) else {"ok": False, "code": "INVALID_BRIDGE_RESPONSE", "message": "Bridge returned a non-object response."}
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            return {"ok": False, "code": "BRIDGE_PORT_CONFLICT", "message": "The configured local port is occupied by a service that did not authenticate as Rhino3D to Solid Edge bridge; refusing to connect or replace it."}
        try:
            detail = exc.read(2048).decode("utf-8", "replace")
        except Exception:
            detail = ""
        return {"ok": False, "code": "BRIDGE_HTTP_ERROR", "http_status": exc.code, "message": detail or str(exc)}
    except (TimeoutError, socket.timeout) as exc:
        if method == "POST" and path in {"/tools/call", "/events/call"}:
            return {"ok": False, "code": "UNKNOWN_OUTCOME", "message": f"The tool request may have reached Solid Edge but no response arrived ({type(exc).__name__}); do not replay automatically."}
        return {"ok": False, "code": "BRIDGE_TIMEOUT", "message": f"Bridge request timed out ({type(exc).__name__})."}
    except urllib.error.URLError as exc:
        if method == "POST" and path == "/tools/call" and not isinstance(getattr(exc, "reason", None), ConnectionRefusedError):
            return {"ok": False, "code": "UNKNOWN_OUTCOME", "message": f"The bridge connection failed after a tool request may have been sent ({type(exc.reason).__name__}); reconcile state before retrying."}
        return {"ok": False, "code": "BRIDGE_NOT_RUNNING", "message": f"Solid Edge bridge is not responding ({type(exc).__name__}). Start the local Solid Edge bridge; no tool request was replayed."}
    except (ConnectionError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "code": "BRIDGE_NOT_RUNNING", "message": f"Solid Edge bridge is not responding ({type(exc).__name__}). Start the local Solid Edge bridge; no tool request was replayed."}

'Start the local bridge daemon with a detached, hidden Python process and wait for health.'

def _launch_daemon() -> dict[str, Any]:
    """Start the local bridge daemon as a detached hidden process and wait for its health check."""
    state = _state(create=True)
    if state is None:
        return {"ok": False, "code": "BRIDGE_CONFIG_ERROR", "message": "Unable to create or read bridge state."}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    acquired = False
    lock_fd = None
    while time.monotonic() < deadline:
        current = _request("GET", "/health", timeout=1.0)
        if current.get("ok"):
            return current
        if current.get("code") == "BRIDGE_PORT_CONFLICT":
            return current
        try:
            lock_fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(lock_fd, str(os.getpid()).encode("ascii"))
            acquired = True
            break
        except FileExistsError:
            try:
                if time.time() - LOCK_FILE.stat().st_mtime > 120:
                    LOCK_FILE.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            time.sleep(0.25)
    if not acquired:
        return {"ok": False, "code": "BRIDGE_START_LOCK_TIMEOUT", "message": "Another start attempt did not finish within the bounded startup window."}
    try:
        current = _request("GET", "/health", timeout=1.0)
        if current.get("ok"):
            return current
        if current.get("code") == "BRIDGE_PORT_CONFLICT":
            return current
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        launch_kwargs = hidden_subprocess_kwargs()
        launch_kwargs["creationflags"] = flags | launch_kwargs.get("creationflags", 0)
        log_path = STATE_DIR / "bridge-launch.log"
        with open(log_path, "ab") as log:
            subprocess.Popen(
                [str(background_python()), str(DAEMON), "--serve"], cwd=str(ROOT),
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                close_fds=True, **launch_kwargs,
            )
        while time.monotonic() < deadline:
            current = _request("GET", "/health", timeout=1.0)
            if current.get("ok"):
                return current
            if current.get("code") == "BRIDGE_PORT_CONFLICT":
                return current
            time.sleep(0.5)
        return {"ok": False, "code": "BRIDGE_START_TIMEOUT", "message": f"Bridge startup exceeded {START_TIMEOUT_SECONDS} seconds. Inspect bridge-launch.log; no automatic second launch was attempted."}
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except OSError:
            pass


def status() -> dict[str, Any]:
    """Read bridge health without launching Solid Edge or creating a process."""
    result = _request("GET", "/health", timeout=2.0)
    if result.get("ok"):
        return result
    return {"ok": True, "bridge_running": False, "code": result.get("code", "BRIDGE_NOT_RUNNING"), "message": result.get("message", "Start the local Solid Edge bridge to start the isolated MCP session.")}


def start() -> dict[str, Any]:
    """Start the persistent MCP session and its hidden, owned Solid Edge instance."""
    result = _launch_daemon()
    if not result.get("ok"):
        return result
    return {**result, "started_or_reused": True, "message": "Persistent Solid Edge MCP session is ready. It owns only the isolated instance it launched; the user's existing Edge.exe window is not taken over."}


def stop() -> dict[str, Any]:
    """Gracefully stop the bridge; its MCP server closes only its own isolated instance."""
    result = _request("POST", "/shutdown", {}, timeout=5.0)
    if not result.get("ok"):
        return result
    state = _state(create=False)
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        time.sleep(0.5)
        probe = _request("GET", "/health", timeout=1.0)
        if probe.get("code") in {"BRIDGE_NOT_RUNNING", "BRIDGE_CONFIG_NOT_FOUND"}:
            return {"ok": True, "stopped": True, "message": "Bridge stopped; MCP received EOF and completed its graceful shutdown."}
    return {"ok": False, "code": "BRIDGE_STOP_UNVERIFIED", "message": "Shutdown was requested but the service did not disappear within 35 seconds. Inspect bridge logs and process ownership; do not blindly replay stop."}
'Enforce the client-side allow/deny policy before a mutating or UI-affecting MCP call.'


def _check_action(access: str, tool: str, arguments: dict[str, Any]) -> str | None:
    """Enforce the client-side allow/deny policy before a mutating or UI-affecting MCP call."""
    if tool in DENIED_TOOLS:
        return "se_script_run is intentionally not exposed through this bridge; arbitrary C# execution remains disabled."
    if access == "read" and tool not in READ_TOOLS:
        return f"{tool} is not in the read-only allowlist; use the confirmation-gated write capability if appropriate."
    if access == "write" and tool not in WRITE_TOOLS:
        return f"{tool} is not in the write allowlist."
    if tool == "se_snapshot_diff":
        action = str(arguments.get("action", "save")).lower()
        if access == "read" and action not in {"diff", "list"}:
            return "Read capability permits only se_snapshot_diff action=diff|list; save/drop require the write capability."
        if access == "write" and action not in {"save", "drop"}:
            return "Write capability permits only se_snapshot_diff action=save|drop; diff/list belong to the read capability."
    'Issue one MCP tool request through the local bridge using the supplied timeout.'
    return None


def _call(access: str, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Issue one MCP tool request through the local bridge using the supplied timeout."""
    if not isinstance(tool, str) or not tool:
        return {"ok": False, "code": "INVALID_TOOL", "message": "tool must be a non-empty string."}
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return {"ok": False, "code": "INVALID_ARGUMENTS", "message": "arguments must be a JSON object."}
    problem = _check_action(access, tool, arguments)
    if problem:
        return {"ok": False, "code": "TOOL_NOT_ALLOWED", "tool": tool, "message": problem}
    result = _request("POST", "/tools/call", {"access": access, "tool": tool, "arguments": arguments}, timeout=210.0)
    if not result.get("ok"):
        'Extract the structured MCP result and surface protocol-level errors consistently.'
        return result
    return _unwrap_mcp_result(result.get("tool_result", result), tool)


def _unwrap_mcp_result(result: Any, tool: str) -> dict[str, Any]:
    """Extract the structured MCP result and surface protocol-level errors consistently."""
    if not isinstance(result, dict):
        return {"ok": True, "tool": tool, "result": result}
    is_error = bool(result.get("isError")) or "error" in result
    content_items = result.get("content")
    # Preserve MCP image blocks instead of dropping the actual PNG payload.
    if isinstance(content_items, list) and any(isinstance(item, dict) and item.get("type") == "image" for item in content_items):
        return {"ok": not is_error, "tool": tool, "content": content_items, **({"code": "MCP_TOOL_ERROR"} if is_error else {})}
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        if is_error and structured.get("ok") is not False:
            return {"ok": False, "tool": tool, "code": "MCP_TOOL_ERROR", "result": structured}
        return structured
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                continue
            raw = item["text"]
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    if is_error and parsed.get("ok") is not False:
                        parsed = {"ok": False, "tool": tool, "code": "MCP_TOOL_ERROR", "result": parsed}
                    return parsed
            except json.JSONDecodeError:
                return {"ok": not is_error, "tool": tool, "text": raw, "code": "MCP_TOOL_ERROR" if is_error else None}
    return {"ok": not is_error, "tool": tool, "result": result, "code": "MCP_TOOL_ERROR" if is_error else None}


def read_tool(tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a bounded JSON read tool; native viewport image blocks use capture_viewport."""
    if tool == "se_capture_viewport":
        return {"ok": False, "code": "VIEWPORT_REQUIRES_NATIVE_MCP", "message": "Viewport images are native MCP image blocks and exceed the Registry API response bound. Use the configured Solid Edge MCP client/proxy for se_capture_viewport; this Registry capability intentionally returns no base64 image."}
    return _call("read", tool, arguments)


def capture_viewport(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Capture viewport through native MCP and preserve the image content block."""
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return {"ok": False, "code": "INVALID_ARGUMENTS", "message": "arguments must be a JSON object."}
    problem = _check_action("read", "se_capture_viewport", arguments)
    if problem:
        return {"ok": False, "code": "TOOL_NOT_ALLOWED", "tool": "se_capture_viewport", "message": problem}
    result = _request("POST", "/tools/call", {"access": "read", "tool": "se_capture_viewport", "arguments": arguments}, timeout=210.0)
    if not result.get("ok"):
        return result
    return _unwrap_mcp_result(result.get("tool_result", result), "se_capture_viewport")


def write_tool(tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a mutating/UI-side-effect tool; Registry requires explicit confirmation."""
    return _call("write", tool, arguments)


def event_tool(tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call one allowlisted live-event tool in the persistent event MCP session."""
    if not isinstance(tool, str) or tool not in EVENT_TOOLS:
        return {"ok": False, "code": "TOOL_NOT_ALLOWED", "tool": tool, "message": "tool must be one of the four upstream event MCP tools."}
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return {"ok": False, "code": "INVALID_ARGUMENTS", "message": "arguments must be a JSON object."}
    result = _request("POST", "/events/call", {"tool": tool, "arguments": arguments}, timeout=210.0)
    if not result.get("ok"):
        return result
    return _unwrap_mcp_result(result.get("tool_result", result), tool)


def get_active_document() -> dict[str, Any]:
    """Read or inspect the requested resource/state. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Direct helpers/dependencies: read_tool, result.get. Return paths include: {'ok': True, 'connected': True, 'active_document': result}; result."""
    result = read_tool("se_get_document", {})
    if result.get("ok") is False:
        return result
    return {"ok": True, "connected": True, "active_document": result}


def list_documents() -> dict[str, Any]:
    """Read or inspect the requested resource/state. Direct side-effect indicators: no direct network or filesystem mutation helper is visible; inspect delegated helpers before assuming purity. Direct helpers/dependencies: read_tool, result.get. Return paths include: {'ok': True, 'documents': result, 'note': "Read-only object-model enumerati; result."""
    result = read_tool("se_walk_object", {"path": "Application.Documents", "maxItems": 50})
    if result.get("ok") is False:
        return result
    return {"ok": True, "documents": result, "note": "Read-only object-model enumeration; the server's tracked document set may differ from documents opened manually."}
