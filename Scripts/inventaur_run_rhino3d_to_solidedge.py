#!/usr/bin/env python
"""Inventaur Inc. deterministic Rhino3D-to-Solid-Edge conversion supervisor.

Run:
    .\\Runtime\\Python\\python.exe .\\Scripts\\inventaur_rhino3d_to_solidedge.py --source "C:/Models/model.3dm"

The runner attaches to an already-running Rhino document exposed by a
document-scoped MCP listener with run_python. It validates the exact saved path
and runtime identity, then captures current in-memory state (including unsaved
edits) to an isolated, hashed run snapshot using RhinoDoc.Write3dmFile.

The live Rhino document is never saved, renamed, switched, closed or modified.
The snapshot is reopened headlessly and checked before any conversion stage.

Pipeline:
    snapshot -> colour policy -> definition/occurrence inventory -> identity
    manifest -> STEP export -> native PAR import -> nested/root ASM build
    -> save/close/reopen and final acceptance audit.

A fresh run is the default. Resume is allowed only for the same run ID and
source-bound verified checkpoints. Ambiguous or unverified mutating operations
must be reconciled before retry; the runner never promotes an unverified file.
"""
from __future__ import annotations

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"

import argparse, hashlib, json, os, shutil, subprocess, sys, time, urllib.request, urllib.error, secrets, socket, zipfile, threading, re
from pathlib import Path
from datetime import datetime

WF=Path(__file__).resolve().parents[1]
CAD=WF.parent
SCRIPT_DIR=Path(__file__).resolve().parent
SOLID_EDGE_MCP_ROOT=SCRIPT_DIR/"SOLIDEDGE-MCP"
PY=Path(sys.executable).resolve()


def sha(path: Path) -> str:
    """Return the streaming SHA-256 hex digest for a source or stage artifact. The file is opened read-only; callers use the digest to bind resumable stage evidence to exact bytes."""
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, data: dict) -> None:
    """Persist a JSON report/checkpoint by writing a sibling temporary file and atomically replacing the destination. Creates the parent directory as needed; a failed write/replace propagates to the caller."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
    os.replace(tmp,path)


def _call_rhino_request(script: Path, cfg: dict, reconcile=None, stage_payload: dict | None = None) -> str:
    """Execute one Rhino script with an immutable run config and per-call stage payload.

    The payload is transient input for this one stage; it is never written back
    into the run config or a shared global config.
    """
    config_path = cfg.get("config_path")
    if not config_path or not Path(config_path).is_file():
        raise RuntimeError("Rhino stage requires the exact existing run config_path")
    payload_json = json.dumps(stage_payload or {}, ensure_ascii=False)
    code=("import os\n"
          + f"os.environ['CAD_WORKFLOW_CONFIG']={json.dumps(str(Path(config_path).resolve()))}\n"
          + f"os.environ['CAD_WORKFLOW_STAGE_PAYLOAD']={json.dumps(payload_json)}\n"
          + f"exec(compile(open(r'{script}','rb').read(),r'{script}','exec'))")
    payload={"jsonrpc":"2.0","id":int(time.time()*1000)%100000000,"method":"tools/call",
             "params":{"name":"run_python","arguments":{"script":code}}}
    req=urllib.request.Request(cfg["rhino_mcp_url"],data=json.dumps(payload).encode("utf-8"),
                               headers={"Content-Type":"application/json"},method="POST")
    timeout=int(cfg.get("rhino_call_timeout_seconds",900))
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            envelope=json.loads(response.read().decode("utf-8","replace"))
    except urllib.error.HTTPError as first_error:
        if first_error.code != 502:
            raise
        time.sleep(5)
        if reconcile is not None and reconcile():
            return "RECONCILED_EXISTING_STAGE_REPORT_AFTER_HTTP_502"
        try:
            with urllib.request.urlopen(req,timeout=timeout) as response:
                envelope=json.loads(response.read().decode("utf-8","replace"))
        except urllib.error.HTTPError as retry_error:
            if retry_error.code == 502 and reconcile is not None and reconcile():
                return "RECONCILED_EXISTING_STAGE_REPORT_AFTER_HTTP_502_RETRY"
            raise
    if envelope.get("error") or envelope.get("result",{}).get("isError"):
        raise RuntimeError(json.dumps(envelope,ensure_ascii=False)[:4000])
    output=[]
    for part in envelope.get("result",{}).get("content",[]):
        if part.get("type")!="text":continue
        raw=part.get("text","")
        try:
            inner=json.loads(raw)
            if inner.get("error") or inner.get("stderr"):
                raise RuntimeError(json.dumps(inner,ensure_ascii=False)[:3000])
            output.append(inner.get("stdout",raw))
        except json.JSONDecodeError:
            output.append(raw)
    return "\n".join(output)



def is_nonfatal_rhino_step_warning(title: str) -> bool:
    """Match only Rhino's informational STEP warning window; never dismiss generic Rhino dialogs."""
    return bool(re.fullmatch(r"Rhino\s+\d+(?:\.\d+)?\s+STEP Export Warning",str(title or "").strip()))


def dismiss_rhino_step_warning_windows(rhino_pid: int | None) -> list[dict]:
    """Close only STEP Export Warning dialogs owned by this selected Rhino process."""
    if os.name!="nt" or not rhino_pid:
        return []
    import ctypes
    from ctypes import wintypes
    user32=ctypes.WinDLL("user32",use_last_error=True)
    enum_windows=user32.EnumWindows
    enum_windows.argtypes=[ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM),wintypes.LPARAM]
    get_text=user32.GetWindowTextW
    get_text.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    get_pid=user32.GetWindowThreadProcessId
    get_pid.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    post=user32.PostMessageW
    post.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    found=[]
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    @callback_type
    def visit(hwnd,lparam):
        """Collect a top-level window only when Windows confirms it belongs to the selected Rhino process."""
        process_id=wintypes.DWORD()
        get_pid(hwnd,ctypes.byref(process_id))
        if process_id.value!=int(rhino_pid):
            return True
        title=ctypes.create_unicode_buffer(512)
        get_text(hwnd,title,len(title))
        if is_nonfatal_rhino_step_warning(title.value):
            if post(hwnd,0x0010,0,0):  # WM_CLOSE: this information-only dialog has one OK action
                found.append({"pid":int(rhino_pid),"hwnd":int(hwnd),"title":title.value})
        return True
    enum_windows(visit,0)
    return found


def _watch_rhino_step_warnings(stop_event: threading.Event, cfg: dict) -> None:
    """Dismiss and log informational STEP annotation/mesh notices while a Rhino stage is running."""
    pid=cfg.get("rhino_pid")
    while not stop_event.wait(0.2):
        try:
            dismissed=dismiss_rhino_step_warning_windows(pid)
            for row in dismissed:
                record={"at":datetime.now().astimezone().isoformat(),
                        "action":"AUTO_DISMISSED_NONFATAL_STEP_WARNING",
                        "message":"Rhino STEP writer omitted unsupported mesh/annotation objects; physical geometry export continues.",
                        **row}
                try:
                    log_root=Path(cfg.get("logs_root") or ".")
                    log_root.mkdir(parents=True,exist_ok=True)
                    with (log_root/"rhino_warnings.jsonl").open("a",encoding="utf-8") as stream:
                        stream.write(json.dumps(record,ensure_ascii=False)+"\n")
                except OSError:
                    pass
                print("RHINO_NONFATAL_WARNING_AUTO_DISMISSED "+json.dumps(record,ensure_ascii=False),flush=True)
        except Exception as exc:
            print("RHINO_WARNING_WATCH_ERROR "+str(exc),flush=True)


def call_rhino(script: Path, cfg: dict, reconcile=None, stage_payload: dict | None = None) -> str:
    """Run one Rhino MCP stage while auto-dismissing only the known nonfatal STEP export warning."""
    stop_event=threading.Event()
    watcher=None
    if os.name=="nt" and cfg.get("rhino_pid"):
        watcher=threading.Thread(target=_watch_rhino_step_warnings,args=(stop_event,cfg),
                                 name="rhino-step-warning-watch",daemon=True)
        watcher.start()
    try:
        return _call_rhino_request(script,cfg,reconcile=reconcile,stage_payload=stage_payload)
    finally:
        stop_event.set()
        if watcher is not None:
            watcher.join(timeout=1.0)


def rhino_tool_call(url: str, tool_name: str, arguments: dict, timeout: int = 30) -> str:
    """Call one tool on a document-scoped local Rhino MCP HTTP listener."""
    payload={"jsonrpc":"2.0","id":int(time.time()*1000)%100000000,
             "method":"tools/call","params":{"name":tool_name,"arguments":arguments}}
    req=urllib.request.Request(url,data=json.dumps(payload).encode("utf-8"),
                               headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=timeout) as response:
        envelope=json.loads(response.read().decode("utf-8","replace"))
    if envelope.get("error"):
        raise RuntimeError("Rhino MCP "+tool_name+" failed: "+json.dumps(envelope["error"],ensure_ascii=False)[:2000])
    result=envelope.get("result",{})
    if result.get("isError"):
        raise RuntimeError("Rhino MCP "+tool_name+" returned an error: "+str(result.get("content",[]))[:2000])
    output=[]
    for part in result.get("content",[]):
        if part.get("type")!="text":
            continue
        raw=part.get("text","")
        try:
            inner=json.loads(raw)
        except (TypeError,ValueError):
            output.append(raw)
            continue
        if inner.get("error") or inner.get("stderr"):
            raise RuntimeError("Rhino MCP "+tool_name+" script failed: "+json.dumps(inner,ensure_ascii=False)[:2500])
        output.append(str(inner.get("stdout",raw)))
    return "\n".join(output)


def check_rhino_runtime(cfg: dict, timeout: int = 15) -> dict:
    """Fail early unless the selected document's Rhino Python 3 MCP host is reachable."""
    payload={"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
    req=urllib.request.Request(cfg["rhino_mcp_url"],data=json.dumps(payload).encode("utf-8"),
                               headers={"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            envelope=json.loads(response.read().decode("utf-8","replace"))
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        raise RuntimeError("Rhino MCP is offline at "+str(cfg["rhino_mcp_url"])+": "+str(exc)) from exc
    tools=envelope.get("result",{}).get("tools",[])
    if envelope.get("error") or not any(x.get("name")=="run_python" for x in tools):
        raise RuntimeError("Local Rhino runtime is reachable but does not expose run_python")
    return {"url":cfg["rhino_mcp_url"],"server":envelope.get("result",{}).get("serverInfo",{}),
            "tool_count":len(tools),"run_python_available":True}


def active_rhino_runtimes() -> list[dict]:
    """Discover live Rhino MCP listeners from McNeel's PID/port marker files, never a hard-coded port."""
    roaming=Path(os.environ.get("APPDATA",str(Path.home()/"AppData"/"Roaming")))
    marker_root=roaming/"McNeel"/"Rhinoceros"/"ai"/"listeners"
    if not marker_root.is_dir():
        return []
    runtimes=[]
    markers=sorted(marker_root.glob("*.json"),key=lambda p:p.stat().st_mtime,reverse=True)
    for marker in markers:
        try:
            record=json.loads(marker.read_text(encoding="utf-8"))
            pid=int(record.get("pid",0));port=int(record.get("port",0))
            if pid<=0 or not 1<=port<=65535:
                continue
            gone=marker.with_suffix(".gone")
            if gone.exists() and gone.stat().st_mtime>=marker.stat().st_mtime:
                continue
            url=f"http://127.0.0.1:{port}/"
            runtime=check_rhino_runtime({"rhino_mcp_url":url},timeout=2)
            runtime.update({"pid":pid,"port":port,"version":str(record.get("version","")),"marker":str(marker)})
            runtimes.append(runtime)
        except (OSError,ValueError,TypeError,json.JSONDecodeError,RuntimeError,urllib.error.URLError):
            continue
    return runtimes


def rhino_document_info(url: str) -> dict:
    """Read the document attached to this MCP slot, not the app-global ActiveDoc."""
    script=("import json\n"
            "_doc=__rhino_doc__\n"
            "print(json.dumps({'path':str(_doc.Path or ''),"
            "'modified':bool(_doc.Modified),"
            "'runtime_serial_number':int(_doc.RuntimeSerialNumber)}))")
    output=rhino_tool_call(url,"run_python",{"script":script},timeout=30)
    for line in reversed([line.strip() for line in output.splitlines() if line.strip()]):
        try:
            value=json.loads(line)
            if isinstance(value,dict) and "path" in value:
                return value
        except json.JSONDecodeError:
            continue
    raise RuntimeError("Rhino MCP did not return the active document path: "+output[:1200])


def normalized_path(path: str | Path) -> str:
    """Normalize Windows paths for exact document identity comparison."""
    return os.path.normcase(os.path.realpath(os.path.abspath(str(path))))


def _live_rhino_documents() -> tuple[list[tuple[dict,dict]], list[str]]:
    """Return reachable MCP/document pairs and diagnostics without changing Rhino state."""
    documents=[]
    diagnostics=[]
    runtimes=active_rhino_runtimes()
    if not runtimes:
        raise RuntimeError(
            "Rhino live-session requirement failed: Rhino must already be running with "
            "the Rhino MCP Platform online and exposing run_python. Open the required "
            ".3dm in Rhino and enable MCP before starting this workflow."
        )
    for runtime in runtimes:
        try:
            info=rhino_document_info(runtime["url"])
            documents.append((runtime,info))
        except Exception as exc:
            diagnostics.append({"url":runtime.get("url"),"pid":runtime.get("pid"),
                                "error":f"{type(exc).__name__}: {exc}"})
    if not documents:
        raise RuntimeError("Rhino MCP is reachable but no document-scoped session could be read: "
                           +json.dumps(diagnostics,ensure_ascii=False))
    return documents,diagnostics


def discover_preopened_rhino_source() -> Path:
    """Infer source when exactly one saved .3dm path is attached to a live Rhino MCP document."""
    documents,diagnostics=_live_rhino_documents()
    eligible=[]
    for runtime,info in documents:
        raw_path=str(info.get("path") or "").strip()
        if not raw_path:
            continue
        path=Path(raw_path)
        if path.is_file():
            eligible.append((normalized_path(path),path,runtime,info))
    by_path={}
    for row in eligible:
        by_path.setdefault(row[0],row)
    if len(by_path)!=1:
        observed=[{"url":runtime.get("url"),"pid":runtime.get("pid"),
                   "path":info.get("path"),"modified":info.get("modified")}
                  for runtime,info in documents]
        if not by_path:
            raise RuntimeError("Cannot infer a source: no saved .3dm path is attached to a live Rhino MCP session. "
                               "Open the required file and ensure MCP is online. "
                               "Observed: "+json.dumps(observed,ensure_ascii=False))
        raise RuntimeError("More than one eligible Rhino document is connected. Pass --source with the exact "
                           "already-open .3dm path. Observed: "+json.dumps(observed,ensure_ascii=False))
    return next(iter(by_path.values()))[1].resolve()


def require_live_rhino_source(source: Path, cfg: dict | None = None) -> dict:
    """Require the exact saved path to be attached to live Rhino MCP; in-memory edits are snapshotted, never saved."""
    source=Path(source).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("Required Rhino source file does not exist: "+str(source))
    documents,diagnostics=_live_rhino_documents()
    matches=[]
    for runtime,info in documents:
        raw_path=str(info.get("path") or "").strip()
        if raw_path and normalized_path(raw_path)==normalized_path(source):
            matches.append((runtime,info))
    if not matches:
        observed=[{"url":runtime.get("url"),"pid":runtime.get("pid"),
                   "path":info.get("path"),"modified":info.get("modified")}
                  for runtime,info in documents]
        raise RuntimeError("Required source is not already open in a live Rhino MCP document. "
                           "Open this exact file in Rhino and keep MCP online; the workflow will not open it "
                           "or launch Rhino. Required: "+str(source)+"; observed: "
                           +json.dumps(observed,ensure_ascii=False)
                           +("; listener diagnostics: "+json.dumps(diagnostics,ensure_ascii=False) if diagnostics else ""))
    runtime,info=matches[0]
    if cfg is not None:
        expected=cfg.get("rhino_preflight",{}).get("runtime_serial_number")
        actual=info.get("runtime_serial_number")
        if expected is not None and actual is not None and int(expected)!=int(actual):
            raise RuntimeError("The Rhino MCP document session changed after the run snapshot was captured: "
                               +json.dumps({"expected_runtime_serial_number":expected,
                                            "actual_runtime_serial_number":actual},ensure_ascii=False))
        expected_url=cfg.get("rhino_preflight",{}).get("url")
        if expected_url and expected_url!=runtime.get("url"):
            raise RuntimeError("The Rhino MCP listener changed after the run snapshot was captured.")
    record={
        "action":"VERIFIED_PREOPENED_RHINO_DOCUMENT",
        "session_requirement":"PREEXISTING_RHINO_PROCESS_AND_LIVE_MCP_REQUIRED",
        "url":runtime["url"],"pid":runtime.get("pid"),"port":runtime.get("port"),
        "version":runtime.get("version"),"document":info,
        "saved_file_sha256":sha(source),
        "capture_policy":"SNAPSHOT_CURRENT_IN_MEMORY_DOCUMENT_WITH_WRITE3DMFILE",
    }
    if cfg is not None:
        cfg["rhino_mcp_url"]=runtime["url"]
        cfg["rhino_pid"]=runtime.get("pid")
        cfg["rhino_session_requirement"]="PREEXISTING_RHINO_PROCESS_AND_LIVE_MCP_REQUIRED"
        cfg["rhino_document_current_check"]={
            "url":runtime["url"],"pid":runtime.get("pid"),"port":runtime.get("port"),
            "version":runtime.get("version"),"document_path":str(source),
            "runtime_serial_number":info.get("runtime_serial_number"),
            "modified":bool(info.get("modified",False)),
        }
    return record


def write_live_rhino_snapshot(url: str, source: Path, snapshot: Path,
                              expected_runtime_serial_number: int | None = None) -> dict:
    """Write the attached live Rhino document to an isolated .3dm without changing its path or dirty state."""
    source=Path(source).expanduser().resolve()
    snapshot=Path(snapshot).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("The Rhino document's saved source path is missing: "+str(source))
    if snapshot.exists():
        raise FileExistsError("Refusing to overwrite an existing live-document snapshot: "+str(snapshot))
    snapshot.parent.mkdir(parents=True,exist_ok=True)
    expected_serial=(int(expected_runtime_serial_number)
                     if expected_runtime_serial_number is not None else None)
    script="\n".join([
        "import os, json, Rhino, System",
        "_expected_path="+json.dumps(str(source)),
        "_target_path="+json.dumps(str(snapshot)),
        "_expected_serial="+repr(expected_serial),
        "def _norm(value): return os.path.normcase(os.path.realpath(str(value or '')))",
        "_doc=__rhino_doc__",
        "if _norm(_doc.Path)!=_norm(_expected_path): raise RuntimeError('Attached Rhino document path changed before snapshot')",
        "_before_path=str(_doc.Path or '')",
        "_before_modified=bool(_doc.Modified)",
        "_before_serial=int(_doc.RuntimeSerialNumber)",
        "if _expected_serial is not None and _before_serial!=_expected_serial: raise RuntimeError('Attached Rhino document runtime serial changed before snapshot')",
        "if os.path.exists(_target_path): raise RuntimeError('Snapshot target already exists')",
        "os.makedirs(os.path.dirname(_target_path),exist_ok=True)",
        "_options=Rhino.FileIO.FileWriteOptions()",
        "_options.UpdateDocumentPath=False",
        "_options.SuppressDialogBoxes=True",
        "_options.SuppressAllInput=True",
        "if not _doc.Write3dmFile(_target_path,_options): raise RuntimeError('RhinoDoc.Write3dmFile returned False')",
        "if _norm(_doc.Path)!=_norm(_before_path): raise RuntimeError('Snapshot changed the live Rhino document path')",
        "if int(_doc.RuntimeSerialNumber)!=_before_serial: raise RuntimeError('Snapshot changed the live Rhino runtime serial')",
        "if bool(_doc.Modified)!=_before_modified: raise RuntimeError('Snapshot changed the live Rhino dirty state')",
        "def _obj_sig(_obj):",
        "    if _obj is None: return None",
        "    _g=_obj.Geometry; _a=_obj.Attributes; _box=None",
        "    if _g is not None:",
        "        try:",
        "            _bb=_g.GetBoundingBox(True)",
        "            _box=[round(float(_bb.Min.X),9),round(float(_bb.Min.Y),9),round(float(_bb.Min.Z),9),round(float(_bb.Max.X),9),round(float(_bb.Max.Y),9),round(float(_bb.Max.Z),9)]",
        "        except Exception: _box=None",
        "    _c=_a.ObjectColor",
        "    return {'id':str(_obj.Id),'type':type(_g).__name__ if _g is not None else None,'name':str(_a.Name or ''),'layer':int(_a.LayerIndex),'color_source':str(_a.ColorSource),'rgba':[int(_c.R),int(_c.G),int(_c.B),int(_c.A)],'bbox':_box}",
        "def _doc_sig(_d):",
        "    _model=sorted([_obj_sig(_o) for _o in _d.Objects if _o is not None],key=lambda _x:_x['id'])",
        "    _defs=[]",
        "    for _idef in _d.InstanceDefinitions:",
        "        if _idef is None or _idef.IsDeleted: continue",
        "        _members=[]",
        "        for _oid in _idef.GetObjectIds():",
        "            _member=_d.Objects.FindId(System.Guid(str(_oid)))",
        "            _members.append(_obj_sig(_member) if _member is not None else {'id':str(_oid),'missing':True})",
        "        _defs.append({'id':str(_idef.Id),'name':str(_idef.Name),'members':sorted(_members,key=lambda _x:_x['id'])})",
        "    return {'modelspace':_model,'definitions':sorted(_defs,key=lambda _x:_x['id']),'units':str(_d.ModelUnitSystem),'absolute_tolerance':float(_d.ModelAbsoluteTolerance)}",
        "_copy=Rhino.RhinoDoc.OpenHeadless(_target_path)",
        "if _copy is None: raise RuntimeError('Written live-document snapshot could not reopen headlessly')",
        "try:",
        "    _live_sig=_doc_sig(_doc); _copy_sig=_doc_sig(_copy)",
        "    if _live_sig!=_copy_sig: raise RuntimeError('Snapshot readback semantic comparison failed')",
        "    _result={'status':'VERIFIED','snapshot_path':_target_path,'snapshot_bytes':os.path.getsize(_target_path),'source_path':_before_path,'modified_at_capture':_before_modified,'runtime_serial_number':_before_serial,'modelspace_object_count':len(_live_sig['modelspace']),'definition_count':len(_live_sig['definitions']),'definition_member_count':sum(len(_x['members']) for _x in _live_sig['definitions']),'semantic_readback':'MATCH','live_document_path_unchanged':True,'live_document_modified_state_unchanged':True}",
        "    print('RHINO_LIVE_SNAPSHOT '+json.dumps(_result,ensure_ascii=False))",
        "finally:",
        "    _copy.Dispose()",
    ])
    output=rhino_tool_call(url,"run_python",{"script":script},timeout=180)
    result=None
    for line in reversed([line.strip() for line in output.splitlines() if line.strip()]):
        if not line.startswith("RHINO_LIVE_SNAPSHOT "):
            continue
        try:
            result=json.loads(line[len("RHINO_LIVE_SNAPSHOT "):])
            break
        except json.JSONDecodeError:
            continue
    if not isinstance(result,dict) or result.get("status")!="VERIFIED":
        raise RuntimeError("Rhino did not return a verified live-document snapshot report: "+output[:2000])
    if normalized_path(result.get("snapshot_path",""))!=normalized_path(snapshot):
        raise RuntimeError("Rhino snapshot report refers to a different output path: "+json.dumps(result,ensure_ascii=False))
    if not snapshot.is_file():
        raise FileNotFoundError("Rhino reported a verified snapshot but the file is missing: "+str(snapshot))
    result["source_original_path"]=str(source)
    result["source_disk_sha256_at_capture"]=sha(source)
    result["snapshot_sha256"]=sha(snapshot)
    result["capture_method"]="RhinoDoc.Write3dmFile(FileWriteOptions.UpdateDocumentPath=False)"
    result["snapshot_readback"]="HEADLESS_REOPEN_AND_SEMANTIC_MODEL_MATCH"
    result["captured_at"]=datetime.now().astimezone().isoformat()
    return result


def run_python(script: Path, cwd: Path, log_path: Path, allow_nonzero=False, cfg: dict | None = None) -> tuple[int,str]:
    """Run one deterministic child with the immutable active-run config explicitly passed in its environment."""
    cmd=[str(PY),"-u",str(script)]
    child_env=os.environ.copy()
    if cfg is not None:
        config_path=cfg.get("config_path")
        if not config_path:
            raise RuntimeError("Child stage config is missing config_path")
        config_path = Path(config_path).resolve()
        if not config_path.is_file():
            raise FileNotFoundError("Run-scoped CAD workflow config is missing: " + str(config_path))
        child_env["CAD_WORKFLOW_CONFIG"]=str(config_path)
        # One config contract only; stale legacy aliases must not win in children.
        child_env.pop("RHINO_SE_WORKFLOW_CONFIG", None)
        child_env["LOCALAPPDATA"]=str(Path(cfg["solid_edge_localappdata"]).resolve())
        child_env["SE_MCP_ENABLE_EVENTS"]="0"
    proc=subprocess.Popen(cmd,cwd=str(cwd),env=child_env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,encoding="utf-8",errors="replace",bufsize=1)
    captured=[]
    log_path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with log_path.open("a",encoding="utf-8") as log:
            with proc.stdout:
                while True:
                    line=proc.stdout.readline()
                    if line:
                        captured.append(line.rstrip());print(line.rstrip(),flush=True);log.write(line);log.flush()
                    if proc.poll() is not None and not line:break
                    time.sleep(0.1)
    finally:
        if proc.poll() is None:
            proc.wait()
    if proc.returncode and not allow_nonzero:
        raise RuntimeError(f"{script.name} exited {proc.returncode}")
    return proc.returncode,"\n".join(captured)


def native_import_is_complete(report: dict) -> bool:
    """Return true only for a complete, fully reconciled native-part batch."""
    if not isinstance(report, dict) or report.get("status") != "COMPLETED":
        return False
    eligible = int(report.get("eligible_native_import_count", report.get("planned_count", -1)))
    completed = int(report.get("completed_count", -1))
    failed = int(report.get("failed_count", 0))
    if eligible < 0 or completed != eligible or failed != 0:
        return False
    cleanup = report.get("document_cleanup")
    # A success label is insufficient: every run-owned transient document must
    # be closed and the baseline document set reconciled before assembly starts.
    return isinstance(cleanup, dict) and cleanup.get("status") == "VERIFIED"



def native_import_expected_document_keys(manifest: dict, scaled_variants: dict) -> set[str]:
    """Return the exact PAR import keys derived from the identity manifest and scaled occurrences."""
    expected = set()
    for row in manifest.get("definition_documents", []):
        key = str(row.get("document_key") or "").strip()
        if not key:
            continue
        if row.get("document_type") == "PAR":
            expected.add(key)
        if row.get("local_geometry_companion_par"):
            expected.add(key + "::LOCAL_GEOMETRY")
    for row in scaled_variants.get("variants", []):
        key = str(row.get("key") or "").strip()
        if key:
            expected.add(key)
    return expected


def native_import_checkpoint_is_current(
    report: dict,
    manifest_source_sha256: str,
    expected_document_keys: set[str],
    run_root: str | Path,
) -> bool:
    """Reuse a completed native import only when every expected PAR and STEP still matches its recorded hash."""
    if not native_import_is_complete(report):
        return False
    if not manifest_source_sha256 or report.get("source_sha256") != manifest_source_sha256:
        return False

    rows = report.get("results")
    eligible = int(report.get("eligible_native_import_count", report.get("planned_count", -1)))
    if not isinstance(rows, list) or eligible <= 0 or len(rows) != eligible:
        return False
    if not expected_document_keys:
        return False

    root = Path(run_root).resolve()
    parts_root = root / "Parts"
    step_root = root / "STEP"
    accepted = {
        "imported_verified",
        "reused_verified",
        "imported_verified_with_warnings",
        "reused_verified_with_warnings",
    }
    observed_keys = set()
    observed_outputs = set()

    def inside(path: Path, parent: Path) -> bool:
        """Contain a recorded output within its run-owned artifact folder."""
        try:
            resolved = os.path.normcase(os.path.abspath(str(path)))
            base = os.path.normcase(os.path.abspath(str(parent)))
            return os.path.commonpath([resolved, base]) == base
        except (OSError, ValueError):
            return False

    for row in rows:
        key = str(row.get("document_key") or "").strip()
        if not key or key in observed_keys or row.get("status") not in accepted:
            return False
        observed_keys.add(key)

        if row.get("reopen_verified") is not True:
            return False
        if not isinstance(row.get("validation"), dict) or row["validation"].get("passed") is not True:
            return False

        native_path = Path(str(row.get("output") or ""))
        step_path = Path(str(row.get("step") or ""))
        if not native_path.is_file() or not step_path.is_file():
            return False
        if not inside(native_path, parts_root) or not inside(step_path, step_root):
            return False

        native_hash = str(row.get("native_sha256") or "")
        step_hash = str(row.get("step_sha256") or "")
        if len(native_hash) != 64 or len(step_hash) != 64:
            return False
        try:
            if sha(native_path) != native_hash or sha(step_path) != step_hash:
                return False
        except OSError:
            return False

        output_key = os.path.normcase(os.path.abspath(str(native_path)))
        if output_key in observed_outputs:
            return False
        observed_outputs.add(output_key)

        native_bytes = row.get("native_bytes")
        if native_bytes is not None and int(native_bytes) != native_path.stat().st_size:
            return False

    return observed_keys == set(expected_document_keys)


def assembly_checkpoint_is_current(
    report: dict,
    manifest_source_sha256: str,
    current_native_signature: str,
    current_builder_sha256: str,
    assembly_file_count: int,
) -> bool:
    """Reuse assemblies only when the report is complete and all nested/root acceptance gates pass."""
    if not isinstance(report, dict) or report.get("status") != "COMPLETED":
        return False
    if not manifest_source_sha256 or report.get("source_sha256") != manifest_source_sha256:
        return False
    if not current_native_signature or report.get("native_input_signature") != current_native_signature:
        return False
    if not current_builder_sha256 or report.get("assembly_builder_sha256") != current_builder_sha256:
        return False

    try:
        expected = int(report.get("expected_nested_assemblies", 0))
        completed = int(report.get("completed_nested_assemblies", -1))
        partial = int(report.get("partial_nested_assemblies", -1))
        failed = int(report.get("failed_nested_assemblies", -1))
        if expected <= 0 or completed != expected or partial != 0 or failed != 0:
            return False
        if int(assembly_file_count) != expected + 1:
            return False

        acceptance = report.get("acceptance") or {}
        root = report.get("root") or {}
        if acceptance.get("all_nested_assembly_documents_exist") is not True:
            return False
        if acceptance.get("root_document_exists") is not True:
            return False
        if int(acceptance.get("nested_assemblies_complete", -1)) != expected:
            return False
        if int(acceptance.get("nested_assemblies_partial", -1)) != 0:
            return False
        if int(acceptance.get("nested_assemblies_failed", -1)) != 0:
            return False
        if int(acceptance.get("root_skipped_occurrences", -1)) != 0:
            return False

        root_expected = int(root.get("expected_direct_occurrences", -1))
        root_actual = int(root.get("actual_direct_occurrences", -2))
        return (
            root.get("status") == "VERIFIED"
            and root.get("verified") is True
            and root.get("disk_reopened") is True
            and root.get("reference_files_exist") is True
            and root.get("all_visible") is True
            and root_expected >= 0
            and root_actual == root_expected
            and len(root.get("skipped_top_level_occurrences", [])) == 0
        )
    except (TypeError, ValueError):
        return False


def native_import_assembly_readiness(report: dict, manifest_source_sha256: str) -> dict:
    """Decide whether it is safe to build any assembly branches from a native import batch. Partial imports are allowed only with matching source identity, verified batch cleanup and at least one explicitly verified native output; the assembly builder independently rechecks every native file path and hash."""
    if not isinstance(report, dict) or report.get("status") not in ("COMPLETED", "INCOMPLETE"):
        return {"ready": False, "reason": "native import report is not a finished COMPLETED/INCOMPLETE batch"}
    if not manifest_source_sha256 or report.get("source_sha256") != manifest_source_sha256:
        return {"ready": False, "reason": "native import source SHA-256 does not match the current identity manifest"}
    cleanup = report.get("document_cleanup")
    if not isinstance(cleanup, dict) or cleanup.get("status") != "VERIFIED":
        return {"ready": False, "reason": "run-owned Solid Edge documents were not all closed and reconciled"}
    accepted = {"imported_verified", "reused_verified", "imported_verified_with_warnings", "reused_verified_with_warnings"}
    candidates = [row for row in report.get("results", [])
                  if row.get("status") in accepted and row.get("output") and row.get("native_sha256")]
    if not candidates:
        return {"ready": False, "reason": "no explicitly verified native PAR candidates are available"}
    return {
        "ready": True,
        "reason": "full import verified" if native_import_is_complete(report) else "partial import accepted; builder will independently hash-check each native PAR",
        "partial": not native_import_is_complete(report),
        "candidate_count": len(candidates),
        "document_cleanup": cleanup,
        "source_sha256": report.get("source_sha256"),
    }


def scaled_records(inventory: dict) -> list[dict]:
    """Build explicit variant requests from non-unit top-level Rhino placements."""
    import re, unicodedata
    def slug(s):
        """Convert a stage or output label into a stable, filesystem-safe lowercase slug."""
        s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+","_",s).strip("_") or "unnamed"
    out=[]
    for occ in inventory.get("top_level_occurrences",[]):
        tr=occ.get("transform",{});scales=tr.get("axis_scales",[1,1,1])
        if not any(abs(float(x)-1.0)>1e-7 for x in scales):continue
        name=occ.get("definition_name") or "block"
        guid=occ.get("instance_guid") or "unknown"
        suffix=guid.replace("-","")[:8]
        base=f"{slug(name)}__scaled_{suffix}"
        out.append({"definition_name":name,"name":name,"instance_guid":guid,"definition_guid":occ.get("definition_guid"),
                    "axis_scales":[float(x) for x in scales],"step_file":base+".stp","par_file":base+".par",
                    "step":"STEP/"+base+".stp","relative":"Parts/"+base+".par",
                    "key":"block_name:"+" ".join(name.split()).casefold()+"::SCALED_INSTANCE_"+suffix})
    return out


def performance_snapshot():
    """Capture a bounded system/runner baseline; no CAD document state is changed."""
    try:
        import psutil
        proc=psutil.Process(os.getpid())
        mem=psutil.virtual_memory()
        cpu=psutil.cpu_percent(interval=0.2)
        io=proc.io_counters() if hasattr(proc,"io_counters") else None
        return {"captured_at":datetime.now().astimezone().isoformat(),
                "system_cpu_percent":cpu,"system_memory_total_bytes":int(mem.total),
                "system_memory_available_bytes":int(mem.available),
                "runner_rss_bytes":int(proc.memory_info().rss),
                "runner_cpu_user_seconds":float(proc.cpu_times().user),
                "runner_cpu_system_seconds":float(proc.cpu_times().system),
                "runner_io_read_bytes":int(io.read_bytes) if io else None,
                "runner_io_write_bytes":int(io.write_bytes) if io else None}
    except Exception as exc:
        return {"captured_at":datetime.now().astimezone().isoformat(),"measurement":"UNAVAILABLE","reason":str(exc)}

def output_inventory(run):
    """Count output artifacts and bytes by deliverable folder."""
    result={}
    for folder in ["Rhino3D","STEP","Parts","Assemblies","Logs"]:
        root=Path(run)/folder
        files=[p for p in root.rglob("*") if p.is_file()] if root.exists() else []
        result[folder]={"files":len(files),"bytes":sum(p.stat().st_size for p in files)}
    return result

def write_output_readme(run, status, source, source_hash, native=None, assembly=None, error=None):
    """Write the self-contained operator handoff into the one permitted root README."""
    run=Path(run)
    reports=run/"Logs"/"Reports"
    try:step=json.loads((reports/"step_export_e2e.json").read_text(encoding="utf-8-sig"))
    except Exception:step={}
    try:native=native or json.loads((reports/"native_part_import_e2e.json").read_text(encoding="utf-8-sig"))
    except Exception:native=native or {}
    try:assembly=assembly or json.loads((reports/"assembly_build_e2e.json").read_text(encoding="utf-8-sig"))
    except Exception:assembly=assembly or {}
    lines=[
        "# Inventaur Inc. | Rhino3D to Solid Edge conversion", "",
        f"**Status:** {status}", "",
        f"**Source:** {source}",
        f"**Source SHA-256:** {source_hash}", "",
        "## Output structure",
        "- Rhino3D/: immutable source snapshot and required colourised working model (no geometry repair).",
        "- STEP/: one verified STEP export per unique definition/required scaled occurrence",
        "- Parts/: reusable native Solid Edge .par files",
        "- Assemblies/: reusable nested .asm files and the root assembly",
        "- Logs/: execution logs, configuration, script manifest, reports and quarantine evidence",
        "- README.md: this handoff", "",
        "## Acceptance snapshot",
        f"- STEP: {step.get('verified_exports',0)}/{step.get('requested_exports',0)} verified; {step.get('failed_exports',0)} failed; status {step.get('status','NOT_RUN')}.",
        f"- Native parts: {native.get('completed_count',0)}/{native.get('eligible_native_import_count',native.get('planned_count',0))} verified; {native.get('failed_count',0)} failed; status {native.get('status','NOT_RUN')}.",
        f"- Nested assemblies: {assembly.get('completed_nested_assemblies',0)} complete, {assembly.get('partial_nested_assemblies',0)} partial, {assembly.get('failed_nested_assemblies',0)} failed; status {assembly.get('status','NOT_RUN')}.",
        f"- Root assembly status: {assembly.get('root',{}).get('status','NOT_RUN')}.",
        f"- Artifact inventory: {json.dumps(output_inventory(run),ensure_ascii=False)}.",
        "", "## Reports and logs",
        "- Logs/Reports/live_document_snapshot.json",
        "- Logs/Reports/supervisor.json",
        "- Logs/Reports/rhino_source_preflight.json",
        "- Logs/Reports/final_acceptance_audit.json",
        "- Logs/Reports/colorize_rhino_unique_blocks_v2_report.json",
        "- Logs/Reports/rhino_active_inventory.json",
        "- Logs/Reports/name_identity_manifest.json",
        "- Logs/Reports/step_export_e2e.json",
        "- Logs/Reports/native_part_import_e2e.json",
        "- Logs/Reports/assembly_build_e2e.json",
        "- Logs/script_manifest.json and Logs/workflow_config.json",
        "", "## Deterministic operating rules",
        "- No AI calls are part of the conversion pipeline. RhinoCommon and Solid Edge APIs perform execution.",
        "- Repeated Rhino block definitions reuse the same part/subassembly document; each occurrence keeps its own transform.",
        "- Prior Desktop .par files are candidates only. Reuse requires native reopen validation against this run STEP.",
        "- Rhino and MCP must already be running with the exact saved source path open; unsaved in-memory edits are captured to an isolated run snapshot with Write3dmFile and are not saved back to the live document.",
        "- The Rhino source is never saved or mutated by this pipeline.",
        "- New run output defaults to a Desktop folder named <source-name>_<timestamp>; no output-folder dialog is shown.",
        "- Rejected geometry remains an explicit incomplete acceptance item; tolerances are not loosened to force success.",
    ]
    if error:lines.extend(["","## Current blocker",str(error)])
    (run/"README.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def is_baseline_par_candidate(archive_path: str) -> bool:
    """Return true only for a PAR member inside a Parts directory, independent of path casing or slash style."""
    normalized = str(archive_path).replace("\\", "/")
    parts = [part.casefold() for part in normalized.split("/") if part]
    return bool(parts and parts[-1].endswith(".par") and "parts" in parts[:-1])


def stop_run_bridge(cfg):
    """Stop only this run-scoped local bridge profile after fully verified completion."""
    env=os.environ.copy()
    env["LOCALAPPDATA"]=str(Path(cfg["solid_edge_localappdata"]).resolve())
    env["CAD_WORKFLOW_CONFIG"]=str(Path(cfg["config_path"]).resolve())
    env.pop("RHINO_SE_WORKFLOW_CONFIG", None)
    code=("import sys,json;sys.path.insert(0,"+repr(str(Path(cfg["solid_edge_mcp_root"]).resolve()))+");"
          "import inventaur_bridge_client;print(json.dumps(inventaur_bridge_client.stop(),ensure_ascii=False))")
    result=subprocess.run([str(PY),"-c",code],cwd=str(SCRIPT_DIR),env=env,capture_output=True,
                          text=True,encoding="utf-8",errors="replace",timeout=50)
    payload=None
    for line in reversed((result.stdout or "").splitlines()):
        try:payload=json.loads(line);break
        except Exception:continue
    return {"returncode":result.returncode,"result":payload,"stdout":(result.stdout or "")[-2000:],
            "stderr":(result.stderr or "")[-2000:],"stopped":bool(result.returncode==0 and payload and payload.get("stopped"))}

def default_desktop_output_root(source: Path, run_id: str, desktop: Path | None = None) -> Path:
    """Return Desktop/<source-name>_<timestamp-or-run-id>; never opens a folder dialog."""
    desktop = Path(desktop) if desktop is not None else Path.home() / "Desktop"
    if not desktop.is_dir():
        raise FileNotFoundError("Windows Desktop folder is unavailable: " + str(desktop))
    suffix = str(run_id).strip()
    if suffix.startswith("cad_"):
        suffix = suffix[4:]
    if not suffix:
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Keep the generated leaf name valid on Windows, including custom --run-id values.
    for character in '<>:"/\\\\|?*':
        suffix = suffix.replace(character, "_")
    return desktop / (Path(source).stem + "_" + suffix)


def main() -> int:
    """Parse the source/run/resume CLI, snapshot the supplied .3dm into an isolated run directory, and orchestrate the Rhino-to-Solid-Edge stages through the configured MCP and bridge adapters. Resume reuses only verified outputs whose recorded source hashes still match. Writes manifests, reports and logs; returns 0 only for COMPLETED and raises for missing or mismatched source/run state. It does not silently overwrite an existing run."""
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=None,
                    help="Exact saved .3dm path already open and MCP-attached in Rhino; current in-memory edits are captured to a separate run snapshot")
    ap.add_argument("--output-root", default=None,
                    help="Optional explicit output package root; default is created on Desktop as <source-name>_<timestamp> (no folder dialog)")
    ap.add_argument("--run-id", default=datetime.now().strftime("cad_%Y%m%d_%H%M%S"),
                    help="Stable identifier for this conversion run; reused only with --resume and matching source-bound checkpoints.")
    ap.add_argument("--resume",action="store_true",help="Resume only verified checkpoints for this exact run id")
    ap.add_argument("--baseline-parts-zip",default=None,help="Prior Desktop conversion ZIP; only .par files are candidates and all are reopened against this run STEP before reuse.")
    args=ap.parse_args()
    if args.source:
        source=Path(args.source).expanduser().resolve()
    else:
        source=discover_preopened_rhino_source()
    if not source.is_file():
        raise FileNotFoundError("Required source .3dm does not exist: "+str(source))
    # Hard precondition is checked before creating a run folder or starting Solid Edge.
    initial_rhino=require_live_rhino_source(source,{})
    print("RHINO_PREOPENED_SESSION_REQUIRED_VERIFIED "+json.dumps(initial_rhino,ensure_ascii=False),flush=True)
    run=Path(args.output_root).expanduser().resolve() if args.output_root else default_desktop_output_root(source,args.run_id)
    if run.exists() and any(run.iterdir()) and not args.resume:
        raise FileExistsError(f"Output root is not empty; use a new root or --resume: {run}")
    for part in ["Rhino3D","STEP","Parts","Assemblies","Logs"]:
        (run/part).mkdir(parents=True,exist_ok=True)
    pipe=run  # final output root; deliverable root has exactly the requested folders
    reports_dir=run/"Logs"/"Reports"
    logs_dir=run/"Logs"
    reports_dir.mkdir(parents=True,exist_ok=True)
    snapshot=run/"Rhino3D"/source.name
    snapshot_report=reports_dir/"live_document_snapshot.json"
    if args.resume:
        if not snapshot.is_file():
            raise FileNotFoundError("Cannot resume: the immutable Rhino3D source snapshot is missing: "+str(snapshot))
        snapshot_info={"status":"REUSED_IMMUTABLE_RUN_SNAPSHOT","snapshot_path":str(snapshot),
                       "snapshot_sha256":sha(snapshot),"source_original_path":str(source),
                       "capture_method":"EXISTING_RUN_SNAPSHOT","modified_at_capture":None}
    else:
        snapshot_info=write_live_rhino_snapshot(
            initial_rhino["url"],source,snapshot,
            initial_rhino.get("document",{}).get("runtime_serial_number"))
        atomic_json(snapshot_report,snapshot_info)
    source_snapshot_sha=sha(snapshot)
    run_config=logs_dir/"workflow_config.json"
    if args.resume:
        if not run_config.is_file():raise FileNotFoundError("Cannot resume: Logs/workflow_config.json is missing")
        cfg=json.loads(run_config.read_text(encoding="utf-8-sig"))
        if Path(cfg.get("source_3dm","")).resolve()!=snapshot.resolve() or cfg.get("source_sha256")!=sha(snapshot):
            raise RuntimeError("Resume source does not match the immutable run snapshot")
        bridge_profile=Path(cfg["solid_edge_localappdata"])
        bridge_state=bridge_profile/"Rhino3DToSolidEdge"/"SolidEdgeMcp"/"bridge.json"
        if not bridge_state.is_file():raise FileNotFoundError("Dedicated Solid Edge bridge state missing; resume cannot safely attach to another session")
        bridge_port=int(json.loads(bridge_state.read_text(encoding="utf-8"))["port"])
    else:
        bridge_profile=logs_dir/"BridgeProfile"
        bridge_state=bridge_profile/"Rhino3DToSolidEdge"/"SolidEdgeMcp"/"bridge.json"
        bridge_profile.mkdir(parents=True,exist_ok=True)
        bridge_port=None
        for candidate in range(39743,39840):
            probe=socket.socket()
            try:
                probe.bind(("127.0.0.1",candidate))
                bridge_port=candidate
                break
            except OSError:
                continue
            finally:
                probe.close()
        if bridge_port is None:raise RuntimeError("No free loopback port for this run Solid Edge bridge")
        bridge_state.parent.mkdir(parents=True,exist_ok=True)
        atomic_json(bridge_state,{"port":bridge_port,"token":secrets.token_urlsafe(32),"schema":1})
        cfg={"schema_version":1,"workflow_id":"rhino3d-to-solidedge-assembly","run_id":args.run_id,
             "cad_root":str(CAD),"workflow_root":str(WF),"run_root":str(run),"pipeline_root":str(pipe),
             "source_original_path":str(source),"source_3dm":str(snapshot),"source_sha256":source_snapshot_sha,
             "source_snapshot_mode":"LIVE_RHINO_DOCUMENT_WRITE3DMFILE",
             "source_disk_sha256_at_capture":snapshot_info.get("source_disk_sha256_at_capture"),
             "rhino_document_modified_at_capture":snapshot_info.get("modified_at_capture"),
             "rhino_document_snapshot_report":str(snapshot_report),
             "rhino_preflight":{"url":initial_rhino["url"],"pid":initial_rhino.get("pid"),
                 "port":initial_rhino.get("port"),"version":initial_rhino.get("version"),
                 "document_path":str(source),
                 "runtime_serial_number":initial_rhino.get("document",{}).get("runtime_serial_number"),
                 "modified":bool(snapshot_info.get("modified_at_capture",False)),
                 "saved_file_sha256_at_capture":snapshot_info.get("source_disk_sha256_at_capture"),
                 "snapshot_sha256":source_snapshot_sha},
             "joined_3dm":str(run/"Rhino3D"/"joined.3dm"),"repaired_3dm":str(run/"Rhino3D"/"repaired.3dm"),
             "colorized_3dm":str(run/"Rhino3D"/"joined_colorized.3dm"),"reports_root":str(reports_dir),
             "parts_root":str(run/"Parts"),"assemblies_root":str(run/"Assemblies"),"step_root":str(run/"STEP"),
             "logs_root":str(logs_dir),"python_executable":str(PY),
             "rhino_mcp_url":initial_rhino["url"],"rhino_pid":initial_rhino.get("pid"),
             "rhino_session_requirement":"PREEXISTING_RHINO_PROCESS_AND_LIVE_MCP_REQUIRED",
             "rhino_call_timeout_seconds":1800,
             "solid_edge_mcp_root":str(SOLID_EDGE_MCP_ROOT),
              "solid_edge_part_template":os.environ.get("CAD_SOLID_EDGE_PART_TEMPLATE"),
             "solid_edge_localappdata":str(bridge_profile),"solid_edge_bridge_port":bridge_port,
             "fallback_geometry_dir":str(WF/"FallbackGeometry"),"root_assembly_path":str(run/"Assemblies"/"Root.asm"),
             "scaled_occurrences":[],"policy":{"preserve_nonblack_source_rgb":True,
             "randomize_only_black_definition":True,"preserve_object_alpha":True,
             "one_PAR_per_leaf_definition":True,"one_ASM_per_nested_definition":True,
             "repeated_instances_reuse_document":True,"do_not_explode_breps":True,
             "reuse_baseline_parts_only_after_step_reopen_verification":True}}
        cfg["config_path"]=str(run_config)
        atomic_json(run_config,cfg)
    os.environ["CAD_WORKFLOW_CONFIG"]=str(run_config)
    os.environ.pop("RHINO_SE_WORKFLOW_CONFIG", None)
    os.environ["LOCALAPPDATA"]=str(bridge_profile)
    # Seed only prior native PAR files. STEP and assembly documents are always regenerated
    # for this source; every seeded PAR is independently reopened against the fresh STEP.
    baseline_seed={"status":"NOT_REQUESTED","candidate_count":0,"candidates":[],"collisions":[]}
    if args.baseline_parts_zip and not args.resume:
        baseline=Path(args.baseline_parts_zip).expanduser().resolve()
        if not baseline.is_file():raise FileNotFoundError(baseline)
        baseline_seed={"status":"SEEDED_CANDIDATES_ONLY","archive":str(baseline),"archive_sha256":sha(baseline),
                       "candidate_count":0,"candidates":[],"collisions":[],
                       "note":"These prior-run PARs are candidates, not trusted outputs. The native importer reopens and verifies every reused PAR against this run STEP."}
        seen={}
        with zipfile.ZipFile(baseline,"r") as z:
            for info in z.infolist():
                if info.is_dir() or not is_baseline_par_candidate(info.filename):continue
                filename=Path(info.filename.replace("\\","/")).name
                if not filename or filename in {".",".."}:continue
                key=filename.casefold();payload=z.read(info);digest=hashlib.sha256(payload).hexdigest()
                if key in seen:
                    if seen[key]!=digest:baseline_seed["collisions"].append(filename)
                    continue
                target=run/"Parts"/filename
                if target.exists():baseline_seed["collisions"].append(filename);continue
                target.write_bytes(payload);seen[key]=digest
                baseline_seed["candidates"].append({"file":filename,"sha256":digest,"bytes":len(payload)})
        baseline_seed["candidate_count"]=len(baseline_seed["candidates"])
    atomic_json(logs_dir/"baseline_parts_seed.json",baseline_seed)
    script_rows=[{"file":script.name,"sha256":sha(script),"bytes":script.stat().st_size}
                 for script in sorted(SCRIPT_DIR.glob("*.py"))]
    atomic_json(logs_dir/"script_manifest.json",{"canonical_script_root":str(SCRIPT_DIR),"scripts":script_rows})
    report={"schema_version":1,"run_id":args.run_id,"status":"RUNNING","source":str(snapshot),
            "source_original_path":str(source),"source_sha256":source_snapshot_sha,
            "rhino_document_snapshot":snapshot_info,
            "baseline_candidate_count":baseline_seed.get("candidate_count",0),
            "solid_edge_bridge":{"state_directory":str(bridge_profile),"port":bridge_port,"isolated":True},
            "started_at":datetime.now().astimezone().isoformat(),"current_stage":None,"stages":[]}
    status_path=reports_dir/"supervisor.json";atomic_json(status_path,report)
    log_path=logs_dir/"supervisor.log"
    performance_baseline=performance_snapshot()
    atomic_json(reports_dir/"performance_baseline.json",performance_baseline)
    try:
        rhino_open=require_live_rhino_source(source,cfg)
        atomic_json(run_config,cfg)
        report["rhino_document"]=rhino_open
        rhino_runtime=check_rhino_runtime(cfg)
        report["rhino_runtime"]=rhino_runtime
        atomic_json(status_path,report)
        print("RHINO_RUNTIME_READY "+json.dumps(rhino_runtime),flush=True)
        # Read-only preflight pins the active Rhino doc/session to the snapshot's original path.
        preflight_text=call_rhino(SCRIPT_DIR/"inventaur_verify_active_rhino_source.py",cfg)
        preflight_report=reports_dir/"rhino_source_preflight.json"
        if not preflight_report.is_file():raise RuntimeError("Rhino source preflight did not write its report: "+preflight_text[:1200])
        preflight_data=json.loads(preflight_report.read_text(encoding="utf-8-sig"))
        if preflight_data.get("status")!="VERIFIED" or preflight_data.get("source_sha256")!=sha(snapshot):
            raise RuntimeError("Active Rhino document is not the selected source: "+json.dumps(preflight_data,ensure_ascii=False))
        report["rhino_source_preflight"]=str(preflight_report)
        atomic_json(status_path,report)
    except Exception as exc:
        report["status"]="INCOMPLETE";report["error"]=str(exc);report["finished_at"]=datetime.now().astimezone().isoformat()
        atomic_json(status_path,report)
        write_output_readme(run,"INCOMPLETE",source,sha(snapshot),error=str(exc))
        raise
    def stage(name, fn, report_file=None, allow_partial=False, reuse_if=None):
        # Resume only when the owning stage report and output hashes prove the
        # exact same inputs produced the existing outputs. Otherwise execute.
        """Execute one workflow stage and reuse only a checkpoint whose inputs and output hashes still match."""
        if args.resume and reuse_if is not None and reuse_if():
            data=json.loads(Path(report_file).read_text(encoding="utf-8-sig")) if report_file else {}
            stage_status=data.get("status","VERIFIED")
            report["stages"].append({"name":name,"status":"REUSED_VERIFIED","original_status":stage_status,
                                     "started_at":datetime.now().astimezone().isoformat(),
                                     "finished_at":datetime.now().astimezone().isoformat(),
                                     "report":str(report_file) if report_file else None})
            atomic_json(status_path,report);print("STAGE REUSED_VERIFIED "+name,flush=True);return None
        report["current_stage"]=name;atomic_json(status_path,report);print("STAGE START "+name,flush=True)
        start=datetime.now().astimezone().isoformat();perf_start=time.perf_counter();value=fn()
        stage_status="VERIFIED"
        if report_file:
            report_path=Path(report_file)
            if not report_path.is_file():
                raise FileNotFoundError(f"{name} did not produce its required report: {report_path}")
            data=json.loads(report_path.read_text(encoding="utf-8-sig"))
            stage_status=data.get("status")
            success_status=stage_status in ("VERIFIED","COMPLETED","COMPLETED_WITH_EXCEPTIONS","EXPORTED")
            partial_status=allow_partial and stage_status in ("INCOMPLETE","VERIFIED_WITH_UNRESOLVED","PARTIAL","CHECKPOINT")
            if not (success_status or partial_status):
                raise RuntimeError(f"{name} report status is missing or not acceptable: {stage_status}")
            if isinstance(value, tuple) and value and int(value[0]) != 0 and success_status:
                raise RuntimeError(f"{name} exited with code {value[0]} but wrote success status {stage_status}")
        report["stages"].append({"name":name,"status":stage_status,"started_at":start,
                                 "finished_at":datetime.now().astimezone().isoformat(),"duration_seconds":round(time.perf_counter()-perf_start,3),"report":str(report_file) if report_file else None})
        report["current_stage"]=None;atomic_json(status_path,report)
        print("STAGE "+stage_status+" "+name,flush=True);return value
    try:
        join_report=reports_dir/"join_lowest_block_breps_v2_report.json"
        repair_report=reports_dir/"repair_breps_for_step_v1_report.json"
        color_report=reports_dir/"colorize_rhino_unique_blocks_v2_report.json"
        inventory_report=reports_dir/"rhino_active_inventory.json"
        manifest_report=reports_dir/"name_identity_manifest.json"
        step_report=reports_dir/"step_export_e2e.json"
        native_report=reports_dir/"native_part_import_e2e.json"
        assembly_report=reports_dir/"assembly_build_e2e.json"
        def report_data(path):
            """Load a JSON stage report; return an empty mapping when it is missing or malformed."""
            try:return json.loads(Path(path).read_text(encoding="utf-8-sig"))
            except Exception:return {}
        def output_hash_matches(path, expected):
            """Check whether an output exists and matches the expected SHA-256 digest."""
            path=Path(path)
            return bool(expected and path.is_file() and sha(path)==expected)
        def join_is_current():
            """Verify the optional joined Rhino model against its recorded input and output hashes."""
            d=report_data(join_report);out=Path(cfg["joined_3dm"])
            return d.get("status")=="VERIFIED" and d.get("source_sha256")==sha(snapshot) and output_hash_matches(out,d.get("output_sha256"))
        def repair_is_current():
            """Verify the optional repaired Rhino model is current for the captured source snapshot."""
            d=report_data(repair_report);out=Path(cfg["repaired_3dm"])
            return d.get("status") in ("VERIFIED","VERIFIED_WITH_UNRESOLVED") and d.get("source_sha256")==sha(cfg["joined_3dm"]) and output_hash_matches(out,d.get("output_sha256"))
        def color_is_current():
            """Verify the derived colourized model and its source-bound report are current."""
            d=report_data(color_report);out=Path(cfg["colorized_3dm"])
            return d.get("status")=="VERIFIED" and d.get("source_sha256")==sha(cfg["source_3dm"]) and d.get("alpha30_preserved") is not False and output_hash_matches(out,d.get("output_sha256"))
        def inventory_is_current():
            """Verify the inventory report belongs to the current model and its expected output exists."""
            d=report_data(inventory_report)
            return d.get("source_sha256")==sha(cfg["colorized_3dm"]) and int(d.get("definition_count",0))>0 and int(d.get("cycle_count",0))==0 and not d.get("duplicate_normalized_names")
        def manifest_is_current():
            """Verify the identity manifest is bound to the current inventory and colour report."""
            d=report_data(manifest_report);i=report_data(inventory_report)
            return bool(d.get("build_ready")) and d.get("source_sha256")==i.get("source_sha256")
        def step_is_current():
            """Verify the STEP export report and required files match the current identity manifest."""
            d=report_data(step_report)
            # A partial/checkpoint report is resumable evidence, never a completed
            # stage. Re-run the exporter so it can reuse verified rows and retry
            # failed/missing definitions.
            requested=int(d.get("requested_exports",0))
            verified=int(d.get("verified_exports",0))
            failed=int(d.get("failed_exports",0))
            if d.get("status") not in ("EXPORTED","VERIFIED") or requested<=0 or verified!=requested or failed!=0:
                return False
            if d.get("source_sha256")!=sha(cfg["colorized_3dm"]):return False
            return all(output_hash_matches(x.get("step_path",""),x.get("step_sha256")) for x in d.get("results",[]))
        def scaled_report_path(item):
            """Return the deterministic report path for one scaled-occurrence STEP variant."""
            return reports_dir/("scaled_occurrence_variant_"+item["instance_guid"].replace("-","")[:8]+".json")
        def scaled_is_current(item):
            """Verify a scaled-occurrence variant against its exact instance identity and source hashes."""
            d=report_data(scaled_report_path(item))
            return (d.get("status")=="VERIFIED" and d.get("instance_guid")==item.get("instance_guid") and
                    d.get("source_sha256")==sha(cfg["colorized_3dm"]) and output_hash_matches(d.get("output",""),d.get("output_sha256")))
        def native_signature():
            """Return the stable native-import signature used for checkpoint reconciliation."""
            d=report_data(native_report)
            rows=[]
            for x in d.get("results",[]):rows.append((x.get("document_key"),x.get("native_sha256"),x.get("step_sha256"),x.get("status")))
            for x in d.get("failures",[]):rows.append((x.get("document_key"),None,x.get("step_sha256"),x.get("status")))
            return hashlib.sha256(json.dumps(sorted(rows),ensure_ascii=False).encode("utf-8")).hexdigest()
        def assembly_is_current():
            """Verify nested and root assembly outputs against the current native-import signature."""
            d=report_data(assembly_report)
            paths=list((pipe/"Assemblies").glob("*.asm"))
            builder_hash=sha(SCRIPT_DIR/"inventaur_build_nested_assembly_tree.py")
            manifest_hash=report_data(manifest_report).get("source_sha256")
            return assembly_checkpoint_is_current(
                d,
                manifest_hash,
                native_signature(),
                builder_hash,
                len(paths),
            )
        def rhino_stage(name, report_file, reconcile=None, stage_payload=None):
            """Run one named Rhino-side stage through the selected document-scoped MCP runtime."""
            script=SCRIPT_DIR/name
            return call_rhino(script,cfg,reconcile=reconcile,stage_payload=stage_payload)
        # Required colour pass; geometry is not joined or repaired.
        stage("colorize_rhino_unique_blocks_v2",lambda:rhino_stage("inventaur_colorize_rhino_unique_blocks_v2.py",color_report,color_is_current),color_report,reuse_if=color_is_current)
        # Direct reusable-definition flow: colourized source -> inventory -> manifest -> STEP -> PAR -> ASM.
        stage("build_rhino_inventory",lambda:rhino_stage("inventaur_build_rhino_inventory.py",inventory_report,inventory_is_current),inventory_report,reuse_if=inventory_is_current)
        stage("build_identity_manifest",lambda:run_python(SCRIPT_DIR/"inventaur_build_identity_manifest.py",run,log_path,cfg=cfg),manifest_report,reuse_if=manifest_is_current)
        # Non-unit variants are stage-local payloads; the immutable run config is never rewritten.
        inv=json.loads(inventory_report.read_text(encoding="utf-8-sig"))
        scaled_occurrences=scaled_records(inv)
        atomic_json(reports_dir/"scaled_occurrence_variants.json",{"schema_version":1,"variants":scaled_occurrences})
        for item in scaled_occurrences:
            variant_report=scaled_report_path(item)
            stage(
                "export_scaled_variant_"+item["instance_guid"][:8],
                lambda item=item,variant_report=variant_report:rhino_stage(
                    "inventaur_export_scaled_occurrence_variant_rhino.py",variant_report,
                    stage_payload={"active_scaled_occurrence":item}),
                variant_report,
                reuse_if=lambda item=item:scaled_is_current(item),
            )
        def export_steps_in_batches():
            """Export requested definitions in bounded batches and reconcile every batch result."""
            manifest=json.loads(manifest_report.read_text(encoding="utf-8-sig"))
            requests=[]
            for row in manifest.get("definition_documents",[]):
                if row.get("document_type")=="PAR": requests.append(row)
                if row.get("local_geometry_companion_par"): requests.append(row)
            batch_size=8
            for start_index in range(0,len(requests),batch_size):
                rhino_stage("inventaur_export_named_block_geometry_to_step_rhino.py",step_report,stage_payload={"batch_start":start_index,"batch_size":batch_size})
            return report_data(step_report)
        stage("export_named_block_geometry_to_step_rhino",export_steps_in_batches,step_report,allow_partial=True,reuse_if=step_is_current)
        def native_part_import_is_current():
            """Reuse native PARs only when source identity, expected keys, reopen evidence and artifact hashes all match."""
            native_data = report_data(native_report)
            manifest_data = report_data(manifest_report)
            variants_data = report_data(reports_dir/"scaled_occurrence_variants.json")
            expected_keys = native_import_expected_document_keys(manifest_data, variants_data)
            return native_import_checkpoint_is_current(
                native_data,
                manifest_data.get("source_sha256"),
                expected_keys,
                run,
            )
        stage(
            "native_part_import",
            lambda:run_python(SCRIPT_DIR/"inventaur_import_step_parts_native_v2.py",run,log_path,allow_nonzero=True,cfg=cfg),
            native_report,
            allow_partial=True,
            reuse_if=native_part_import_is_current,
        )
        native_data=json.loads(native_report.read_text(encoding="utf-8-sig"))
        report["native_import_status"]=native_data.get("status")
        manifest_data=report_data(manifest_report)
        assembly_gate=native_import_assembly_readiness(native_data,manifest_data.get("source_sha256"))
        report["assembly_readiness"]=assembly_gate
        assembly_data={}
        if assembly_gate.get("ready"):
            stage("nested_assembly_tree",lambda:run_python(SCRIPT_DIR/"inventaur_build_nested_assembly_tree.py",run,log_path,allow_nonzero=True,cfg=cfg),assembly_report,allow_partial=True,reuse_if=assembly_is_current)
            assembly_data=json.loads(assembly_report.read_text(encoding="utf-8-sig"))
            assembly_data["native_input_signature"]=native_signature()
            assembly_data["native_import_status"]=native_data.get("status")
            assembly_data["assembly_builder_sha256"]=sha(SCRIPT_DIR/"inventaur_build_nested_assembly_tree.py")
            assembly_data["native_input_signature_created_at"]=datetime.now().astimezone().isoformat()
            atomic_json(assembly_report,assembly_data)
            report["assembly_status"]=assembly_data.get("status")
        else:
            # A stale assembly report is historical evidence only; never relabel it current.
            stale_assembly=report_data(assembly_report)
            skipped_at=datetime.now().astimezone().isoformat()
            report["stages"].append({
                "name":"nested_assembly_tree",
                "status":"SKIPPED_NATIVE_IMPORT_NOT_SAFE",
                "started_at":skipped_at,
                "finished_at":skipped_at,
                "report":str(assembly_report) if assembly_report.is_file() else None,
                "reason":assembly_gate.get("reason")
            })
            report["assembly_status"]="SKIPPED_NATIVE_IMPORT_NOT_SAFE"
            if stale_assembly:
                report["stale_assembly_report"]={
                    "path":str(assembly_report),
                    "source_sha256":stale_assembly.get("source_sha256"),
                    "native_input_signature":stale_assembly.get("native_input_signature"),
                    "not_current_for_native_report":True
                }
        report["status"]="COMPLETED" if native_import_is_complete(native_data) and assembly_data.get("status")=="COMPLETED" else "INCOMPLETE"
        report["finished_at"]=datetime.now().astimezone().isoformat()
        report["source_sha256"]=sha(snapshot)
        # Gracefully close only the isolated bridge for this run after a complete build.
        if report["status"]=="COMPLETED":
            report["bridge_shutdown"]=stop_run_bridge(cfg)
            if not report["bridge_shutdown"].get("stopped"):
                report["status"]="INCOMPLETE"
                report["bridge_shutdown_warning"]="Graceful shutdown was not verified; retain the isolated BridgeProfile for recovery."
        performance_after=performance_snapshot()
        baseline_path=reports_dir/"performance_baseline.json"
        baseline_data=json.loads(baseline_path.read_text(encoding="utf-8-sig")) if baseline_path.is_file() else {}
        performance_report={"baseline":baseline_data,"after":performance_after,
                            "output_inventory":output_inventory(run),
                            "stage_durations_seconds":{row.get("name"):row.get("duration_seconds",0) for row in report.get("stages",[])},
                            "scope_note":"CPU/RAM are system/runner snapshots; other processes may contribute. CAD artifact counts/bytes and stage durations are run-scoped."}
        atomic_json(reports_dir/"performance_report.json",performance_report)
        report["performance_report"]=str(reports_dir/"performance_report.json")
        write_output_readme(run,report["status"],source,report["source_sha256"],native_data,assembly_data)
        allowed={"Rhino3D","STEP","Parts","Assemblies","Logs","README.md"}
        actual={item.name for item in run.iterdir()}
        if actual!=allowed:
            raise RuntimeError("Output root structure mismatch; unexpected="+repr(sorted(actual-allowed))+" missing="+repr(sorted(allowed-actual)))
        atomic_json(status_path,report)
        write_output_readme(run,report["status"],source,report["source_sha256"],native_data,assembly_data)
        print(json.dumps({"status":report["status"],"run_root":str(run),"output_root":str(run),"config":str(run_config),"source_sha256":report["source_sha256"],
                          "native_import":native_data.get("status"),
                          "assembly":report.get("assembly_status"),"root":assembly_data.get("root",{}).get("status")},indent=2),flush=True)
        return 0 if report["status"]=="COMPLETED" else 2
    except Exception as exc:
        report["status"]="INCOMPLETE";report["error"]=str(exc);report["finished_at"]=datetime.now().astimezone().isoformat()
        try:
            atomic_json(status_path,report)
            write_output_readme(run,"INCOMPLETE",source,sha(snapshot) if snapshot.is_file() else "UNAVAILABLE",error=str(exc))
        except Exception:
            pass
        raise

if __name__=="__main__":raise SystemExit(main())
