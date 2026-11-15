"""Inventaur Inc. | Import only source-verified STEP geometry into native Solid Edge PAR documents.

Owner: the Solid Edge native-import stage of the Rhino-to-Solid-Edge workflow.
The launcher supplies the active-run configuration. This script consumes the
normalized-name manifest, Rhino inventory, STEP export report, verified color
report, optional scaled-occurrence variants, and the local SolidEdge-MCP bridge.

Outputs are reusable Parts/*.par files, Reports/native_part_import_e2e.json, and
Logs/native_part_import.log. A prior PAR is reused only when its saved hash and
the exact source STEP hash still match. Unchanged failed imports remain
quarantined; changed source bytes can be attempted again. STEP outputs without
verified readback evidence are blocked before import.

Importing this module reads active_run.json and imports Windows UI automation
bindings; it does not start Solid Edge or modify a document. Running main() in
normal mode may start the pipeline-owned bridge, enumerate dialogs for its exact
Solid Edge process ID, drive only recognized New/Open File dialogs, translate
STEP, save PAR files, close/reopen them read-only, and verify topology. It must
not attach to the user's unrelated interactive Solid Edge session. --dry-run
plans the eligible requests and exits before the import loop, while still writing
the plan report and creating the required output directories.

Requirements: Windows, pywin32, a valid active_run.json, the direct SolidEdge-MCP
executable/bridge, and the source reports for the selected run. Missing config,
failed bridge health, unrecognized dialogs, source-hash drift, or invalid topology
stops promotion and is recorded as a failure or blocked item."""

from __future__ import annotations
__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"
import os

import argparse,json,os,re,subprocess,sys,time,traceback,hashlib,shutil
from pathlib import Path
from datetime import datetime
import win32gui,win32con,pythoncom,win32com.client
_CONFIG_ENV = os.environ.get("CAD_WORKFLOW_CONFIG")
if not _CONFIG_ENV:
    raise RuntimeError("CAD_WORKFLOW_CONFIG is required; refusing shared active_run.json fallback")
CONFIG_PATH = Path(_CONFIG_ENV).resolve()
if not CONFIG_PATH.is_file():
    raise FileNotFoundError("Run-scoped CAD workflow config is missing: " + str(CONFIG_PATH))
with CONFIG_PATH.open("r", encoding="utf-8-sig") as _config_stream:
    CONFIG = json.load(_config_stream)
ROOT=Path(CONFIG["pipeline_root"])  # final output root
REPORTS=Path(CONFIG["reports_root"])
LOGS=Path(CONFIG["logs_root"])
STEP_ROOT=Path(CONFIG["step_root"])
PARTS_ROOT=Path(CONFIG["parts_root"])
MCP_ROOT=Path(CONFIG.get("solid_edge_mcp_root", Path(__file__).resolve().parent / "SOLIDEDGE-MCP")).resolve()
MCP_EXE=MCP_ROOT/'runtime'/'win-x64'/'control'/'solidedge-mcp.exe'
from inventaur_cad_environment import find_iso_metric_part_template

ISO_METRIC_TEMPLATE = find_iso_metric_part_template(CONFIG.get('solid_edge_part_template'))
MANIFEST=REPORTS/'name_identity_manifest.json'
EXPORT_REPORT=REPORTS/'step_export_e2e.json'


def load_expected_faces():
    """Return expected native face counts keyed by normalized STEP stem.

    Values are taken only from this run's STEP end-to-end report and explicitly
    source-bound repair evidence in the same Logs/Reports directory. No legacy
    fixed face-count override is allowed across Rhino source revisions.
    """
    out={}
    if EXPORT_REPORT.exists():
        r=json.loads(EXPORT_REPORT.read_text(encoding='utf-8'))
        for x in r.get('results',[]):
            native=x.get('native_relative_path') or ''
            if native: out[Path(native).stem.casefold()]=int(x.get('readback_brep_face_count') or 0)
    for fn,report in [('c_chanel_back_02.stp','c_chanel_back_02_export_e2e.json'),('lockcam1.stp','lockcam1_repair_e2e.json')]:
        p=REPORTS/report
        if p.exists():
            d=json.loads(p.read_text(encoding='utf-8'));res=d.get('result',d)
            out[Path(fn).stem.casefold()]=int(res.get('readback_face_count') or res.get('source_face_count') or 0)
    return out


def check_result(r,label):
    """Validate a SolidEdge-MCP bridge response and return it unchanged.

    Only ok and dry-run dictionary responses are accepted. A missing, malformed,
    or other status raises RuntimeError with a bounded response excerpt.
    """
    if not isinstance(r,dict) or r.get('status') not in ('ok','dry-run'):
        raise RuntimeError(f'{label}: {json.dumps(r,ensure_ascii=False)[:1800]}')
    return r


def dialogs(owned_process_id: int):
    """Return dialog metadata for one explicitly owned Solid Edge process.

    Requires a positive Application.ProcessID and invokes the MCP dialog probe
    with that exact PID. A returned window belonging to another process is rejected.
    The probe is read-only; it does not click, close, or dismiss windows.
    """
    if not isinstance(owned_process_id, int) or owned_process_id <= 0:
        raise RuntimeError('owned Solid Edge Application.ProcessID is unavailable; refusing an unscoped dialog scan')
    p=subprocess.run([str(MCP_EXE),'--dialogs','--pid',str(owned_process_id)],
                     capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=8)
    if p.returncode: raise RuntimeError('dialog probe failed: '+p.stderr[-500:])
    result=json.loads(p.stdout)
    for row in result.get('dialogs',[]):
        if int(row.get('processId') or 0) != owned_process_id:
            raise RuntimeError('dialog probe returned a foreign process window despite PID filter: '+json.dumps(row,ensure_ascii=False)[:900])
    return result


def click_new_dialog(hwnd):
    """Select and confirm the expected ISO Metric Part template in a verified New dialog.

    The HWND must resolve to a live window titled exactly New. The helper locates
    the template list and OK button, selects row 2, verifies selection state, then
    posts the OK click. Callers must first bind the dialog to the pipeline-owned
    Solid Edge process; unexpected templates or controls raise.
    """
    if not win32gui.IsWindow(hwnd) or win32gui.GetWindowText(hwnd)!='New':
        raise RuntimeError('unexpected New dialog identity')
    lists=[]; oks=[]
    def visit(w,_):
        """Inspect a dialog subtree and collect visible ListView controls for the verified template chooser."""
        if win32gui.GetClassName(w)=='SysListView32': lists.append(w)
        if win32gui.GetClassName(w)=='Button' and win32gui.GetWindowText(w)=='OK': oks.append(w)
    win32gui.EnumChildWindows(hwnd,visit,None)
    if not lists or not oks: raise RuntimeError('New dialog template list/OK missing')
    lv=lists[0]
    win32gui.PostMessage(lv,win32con.WM_LBUTTONDOWN,win32con.MK_LBUTTON,(42<<16)|172)
    win32gui.PostMessage(lv,win32con.WM_LBUTTONUP,0,(42<<16)|172)
    time.sleep(.2)
    state=win32gui.SendMessageTimeout(lv,0x102C,2,0x2,win32con.SMTO_ABORTIFHUNG,700)
    state=state[1] if isinstance(state,tuple) else state
    if not state & 2: raise RuntimeError('ISO Metric Part template selection row 2 did not verify; state='+str(state))
    win32gui.PostMessage(oks[0],win32con.BM_CLICK,0,0)


def fill_open_dialog(hwnd,src):
    """Enter one source STEP path into a verified Open File dialog and submit it.

    The HWND must be a live Open File window with visible/enabled path input and
    Open controls. The entered path is read back before the Open click. The caller
    is responsible for confirming that the dialog belongs to the owned PID.
    """
    if not win32gui.IsWindow(hwnd) or win32gui.GetWindowText(hwnd)!='Open File':
        raise RuntimeError('unexpected Open File dialog identity')
    edits=[]; opens=[]
    'Inspect a dialog subtree and collect visible, enabled Edit controls for the verified file picker.'
    def visit(w,_):
        """Inspect the dialog subtree and collect ListView controls used by the verified template chooser."""
        if win32gui.GetClassName(w)=='Edit' and win32gui.IsWindowVisible(w) and win32gui.IsWindowEnabled(w): edits.append(w)
        if win32gui.GetClassName(w)=='Button' and win32gui.GetWindowText(w) in ('&Open','Open'): opens.append(w)
    win32gui.EnumChildWindows(hwnd,visit,None)
    if not edits or not opens: raise RuntimeError('Open File edit/Open controls missing')
    edit=max(edits,key=lambda w:win32gui.GetWindowRect(w)[1])
    win32gui.SetWindowText(edit,str(src))
    if win32gui.GetWindowText(edit)!=str(src): raise RuntimeError('Open File path entry failed verification')
    win32gui.PostMessage(opens[0],win32con.BM_CLICK,0,0)


def click_no_save_dialog(hwnd):
    """Dismiss a pipeline-owned Solid Edge save prompt without saving.

    The prompt is handled only when its document text identifies a document
    under the active workflow ROOT. This prevents the automation from touching
    unrelated interactive work.
    """
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError('save prompt window is no longer valid')
    'Inspect a dialog subtree and collect Button controls so only the expected dialog action is selected.'
    buttons=[]
    def visit(w,_):
        """Inspect the dialog subtree and collect visible, enabled Edit controls in the verified file picker."""
        if win32gui.GetClassName(w)=='Button':
            buttons.append((w,win32gui.GetWindowText(w)))
    win32gui.EnumChildWindows(hwnd,visit,None)
    candidates=[w for w,t in buttons if t in ('&No','No')]
    if not candidates:
        raise RuntimeError('pipeline save prompt has no No button')
    win32gui.PostMessage(candidates[0],win32con.BM_CLICK,0,0)


def settle_import_dialogs(src,owned_process_id,timeout=55):
    """Handle recognized import and pipeline-owned Solid Edge dialogs.

    Unknown or unrelated modal dialogs remain a hard failure.
    """
    deadline=time.monotonic()+timeout
    handled=[]
    while time.monotonic()<deadline:
        snap=dialogs(owned_process_id)
        modal=[d for d in snap.get('dialogs',[]) if d.get('modal') and int(d.get('processId') or 0)==owned_process_id]
        if not modal:
            progress=[d for d in snap.get('dialogs',[]) if d.get('title')=='Solid Edge' and any('Translating to Parasolid' in str(t) for t in d.get('texts',[]))]
            if progress:
                time.sleep(.5)
                continue
            return {'handled':handled,'snapshot':snap}
        d=modal[0]
        title=d.get('title')
        hwnd=int(d.get('hwnd',0))
        if title=='New':
            click_new_dialog(hwnd)
            handled.append({'title':'New','action':'selected_verified_ISO_Metric_Part_row_2'})
        elif title=='Open File':
            fill_open_dialog(hwnd,src)
            handled.append({'title':'Open File','action':'entered_source_path_and_clicked_Open'})
        elif title=='Solid Edge' and any('Translating to Parasolid' in str(t) for t in d.get('texts',[])):
            time.sleep(.5)
        elif any('Do you want to save changes to the following document?' in str(t) for t in d.get('texts',[])):
            dialog_text=' '.join(str(t) for t in d.get('texts',[]))
            root_text=str(ROOT).replace('\\','/').casefold()
            normalized=dialog_text.replace('\\','/').casefold()
            if root_text not in normalized:
                raise RuntimeError('unrelated Solid Edge save prompt left untouched: '+json.dumps(d,ensure_ascii=False))
            click_no_save_dialog(hwnd)
            handled.append({'title':title,'action':'discarded_unsaved_pipeline_document_changes','document_text':dialog_text[:500]})
        else:
            raise RuntimeError('unrecognized modal dialog left untouched: '+json.dumps(d,ensure_ascii=False))
        time.sleep(.35)
    raise TimeoutError('STEP import dialog workflow exceeded '+str(timeout)+'s; last='+json.dumps(snap.get('dialogs',[]),ensure_ascii=False)[:1200])


def clear_stale_pipeline_modals(owned_process_id):
    """Clear stale save prompts belonging to prior automation runs only.

    Solid Edge is effectively single-instance at the UI/COM level, so an old
    pipeline-generated dirty assembly can block a new isolated bridge session.
    We inspect the global dialog probe but close only modal save prompts whose
    owner/document identifies the workflow's Pipeline\\Assemblies namespace.
    User documents are never targeted.
    """
    exe=MCP_EXE
    if not exe.is_file():
        return []
    try:
        probe=subprocess.run([str(exe),'--dialogs'],capture_output=True,text=True,timeout=5)
        if probe.returncode!=0:
            return []
        data=json.loads(probe.stdout)
    except Exception:
        return []
    actions=[]
    for d in data.get('dialogs',[]):
        if not d.get('modal') or int(d.get('processId') or 0)==int(owned_process_id):
            continue
        raw_texts=[str(x) for x in d.get('texts',[])]
        texts=' '.join(raw_texts)
        owner=str(d.get('ownerTitle') or '')
        if 'Do you want to save changes to the following document?' not in texts:
            continue
        combined=(texts+' '+owner).casefold()
        doc_name=raw_texts[1].strip() if len(raw_texts)>1 else ''
        automation_owned=('pipeline' in combined or '\\\\pipeline\\\\assemblies' in combined)
        if not automation_owned and doc_name:
            try:
                automation_owned=any(x.is_file() for x in WORKFLOW_ROOT.rglob(doc_name))
            except Exception:
                automation_owned=False
        if not automation_owned:
            continue
        hwnd=int(d.get('hwnd') or 0)
        if not hwnd:
            continue
        try:
            close=subprocess.run([str(exe),'--dialogs','--close',str(hwnd),'--confirm'],capture_output=True,text=True,timeout=5)
            actions.append({'hwnd':hwnd,'process_id':int(d.get('processId') or 0),'owner':owner,'action':'closed_stale_pipeline_save_prompt','close_returncode':close.returncode})
        except Exception as exc:
            actions.append({'hwnd':hwnd,'process_id':int(d.get('processId') or 0),'owner':owner,'action':'close_failed','error':str(exc)})
    return actions


def newest_automation_edge_pid(min_create_time=0.0):
    """Find the newest Solid Edge automation process without requiring the MCP COM response to expose its PID."""
    try:
        import psutil
        candidates=[]
        for proc in psutil.process_iter(["pid","name","create_time"]):
            try:
                info=proc.info
                if str(info.get("name") or "").casefold() != "edge.exe":
                    continue
                cmd=" ".join(str(x) for x in (proc.cmdline() or []))
                if "/automation" not in cmd.casefold():
                    continue
                candidates.append((float(info.get("create_time") or 0),int(info["pid"])))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return max(candidates)[1] if candidates else 0
    except Exception:
        return 0


def active_doc(bridge):
    """Read the active Solid Edge document and attach its owning Application.ProcessID.

    Uses the bridge se_get_document read operation. A non-ok response is returned
    unchanged; successful document data is copied and augmented with the process ID
    for later exact-process dialog scoping.
    """
    r=bridge.read_tool('se_get_document',{})
    doc=dict(r.get('document') or {})
    doc['_application_process_id']=int(r.get('applicationProcessId') or 0)
    if r.get('status')!='ok':
        doc['_bridge_status']=r.get('status')
        doc['_bridge_message']=r.get('message')
    return doc



def com_property(obj, name):
    """Read one COM property through IDispatch without generated wrappers."""
    dispid = obj._oleobj_.GetIDsOfNames(name)
    value = obj._oleobj_.Invoke(dispid, 0, pythoncom.DISPATCH_PROPERTYGET, True)
    if hasattr(value, "QueryInterface"):
        return win32com.client.Dispatch(value)
    return value


def bind_owned_application(owned_process_id):
    """Bind only the exact Solid Edge Application PID reported by this bridge."""
    pythoncom.CoInitialize()
    rot = pythoncom.GetRunningObjectTable()
    enum = rot.EnumRunning()
    while True:
        batch = enum.Next(1)
        if not batch:
            break
        try:
            obj = win32com.client.Dispatch(rot.GetObject(batch[0]).QueryInterface(pythoncom.IID_IDispatch))
        except Exception:
            continue
        try:
            app = obj.Parent.Application
        except Exception:
            app = obj
        try:
            if int(app.ProcessID) == int(owned_process_id):
                return app
        except Exception:
            continue
    raise RuntimeError(f"Owned Solid Edge Application PID {owned_process_id} is not registered in the ROT")


def ensure_owned_application(bridge, report):
    """Ensure the hidden bridge-owned application has an active tracked seed document."""
    doc = active_doc(bridge)
    pid = int(doc.get("_application_process_id") or 0)
    if pid <= 0:
        if not ISO_METRIC_TEMPLATE.is_file():
            raise FileNotFoundError(f"Solid Edge ISO Metric Part template missing: {ISO_METRIC_TEMPLATE}")
        opened = check_result(
            bridge.write_tool("se_open_document", {"path": str(ISO_METRIC_TEMPLATE), "readOnly": True}),
            "open ISO Metric seed document"
        )
        report["seed_template_document"] = opened
        doc = active_doc(bridge)
        pid = int(doc.get("_application_process_id") or 0)
    if pid <= 0:
        raise RuntimeError("Could not resolve bridge-owned Solid Edge Application.ProcessID")
    app = bind_owned_application(pid)
    report["solid_edge_application_pid"] = pid
    report["solid_edge_application_version"] = str(getattr(app, "Version", ""))
    report["solid_edge_documents_before_import"] = int(app.Documents.Count)
    report["solid_edge_initial_document"] = doc
    return app, pid


'Read one body COM property through the bridge-safe IDispatch helper.'
def com_body_metrics(body, label):
    """Read one model/construction Body, its topology and its exact range box."""
    def get(name):
        """Read one native Body COM property through the bridge-safe IDispatch helper."""
        return com_property(body, name)

    loops = get("Loops")
    vertices = get("Vertices")
    shells = get("Shells")
    shell_count = int(shells.Count)
    face_count = edge_count = 0
    face_areas_mm2 = []
    shell_rows = []
    for shell_index in range(1, shell_count + 1):
        shell = shells.Item(shell_index)
        faces = com_property(shell, "Faces")
        edges = com_property(shell, "Edges")
        fc, ec = int(faces.Count), int(edges.Count)
        face_count += fc
        edge_count += ec
        shell_face_areas = []
        for face_index in range(1, fc + 1):
            face = faces.Item(face_index)
            # Solid Edge COM face.Area is in m²; report all areas in mm².
            area_mm2 = float(face.Area) * 1e6
            shell_face_areas.append(area_mm2)
            face_areas_mm2.append(area_mm2)
        shell_rows.append({"index": shell_index, "faces": fc, "edges": ec, "face_areas_mm2": sorted(shell_face_areas)})

    min_values = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_R8, [])
    max_values = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_R8, [])
    body._oleobj_.Invoke(body._oleobj_.GetIDsOfNames("GetRange"), 0, pythoncom.DISPATCH_METHOD, True, min_values, max_values)
    bbox = [float(x) * 1000.0 for x in min_values.value] + [float(x) * 1000.0 for x in max_values.value]
    valid = bool(get("Valid"))
    is_solid = bool(get("IsSolid"))
    volume = float(get("Volume") or 0.0)
    result = {
        "name": label, "valid": valid, "is_solid": is_solid, "volume_m3": volume,
        "loops": int(loops.Count), "vertices": int(vertices.Count), "shells": shell_count,
        "faces": face_count, "edges": edge_count, "shell_rows": shell_rows,
        "face_areas_mm2": sorted(face_areas_mm2), "total_surface_area_mm2": sum(face_areas_mm2),
        "bbox_mm": bbox,
    }
    if not result["shells"] or not result["loops"] or not result["vertices"] or not result["faces"] or not result["edges"]:
        raise RuntimeError(f"{label} has empty native topology: {json.dumps(result, ensure_ascii=False)}")
    if is_solid and volume <= 1e-18:
        raise RuntimeError(f"{label} is flagged solid with zero native volume")
    return result


def collect_surface_constructions(doc):
    """Collect non-empty copy-construction bodies; ignore empty translator placeholders."""
    rows = []
    try:
        constructions = com_property(doc, "Constructions")
        copy_constructions = com_property(constructions, "CopyConstructions")
        count = int(copy_constructions.Count)
    except Exception as exc:
        return {"copy_construction_count": 0, "bodies": [], "read_error": str(exc)}
    for index in range(1, count + 1):
        try:
            feature = copy_constructions.Item(index)
            parent = com_property(feature, "Parent")
            body = com_property(parent, "Body")
            metric = com_body_metrics(body, f"CopyConstruction_{index}")
            metric["construction_index"] = index
            metric["construction_name"] = str(getattr(feature, "Name", f"CopyConstruction_{index}"))
            rows.append(metric)
        except Exception:
            # Empty CopyConstruction placeholders have no Body and are not geometry.
            continue
    return {"copy_construction_count": count, "bodies": rows}


def document_identity(document):
    """Return the stable Solid Edge document identity used for exact-session ownership checks."""
    return (
        str(getattr(document, "Name", "") or ""),
        str(getattr(document, "FullName", "") or ""),
        int(getattr(document, "Type", 0)),
    )


def close_owned_import_document(app, owned_process_id, document, preexisting_identities=()):
    """Close only the exact PartDocument returned by this run's one-shot STEP import.

    The import path uses Documents.OpenWithTemplate directly, so the MCP's
    se_close_document tracking table does not own this transient document.
    Ownership is established by the exact bridge Application PID, the COM
    document identity, and the pre-open identity snapshot. DisplayAlerts is
    disabled only for the close call and restored immediately. Dirty transient
    imports are discarded, never saved implicitly.
    """
    if document is None:
        return {"status": "not_open", "reason": "no_document"}
    if int(getattr(app, "ProcessID", 0)) != int(owned_process_id):
        raise RuntimeError("Refusing to close an imported document after the owned Solid Edge PID changed")

    identity = document_identity(document)
    if identity in set(tuple(x) for x in preexisting_identities):
        raise RuntimeError("Refusing to close a document that existed before this STEP import: " + repr(identity))

    matches = []
    for index in range(1, int(app.Documents.Count) + 1):
        current = app.Documents.Item(index)
        if document_identity(current) == identity:
            matches.append(current)
    if not matches:
        return {"status": "not_open", "identity": identity}
    if len(matches) != 1:
        raise RuntimeError("Refusing ambiguous imported-document cleanup; exact identity is not unique: " + repr(identity))

    current = matches[0]
    dirty = bool(getattr(current, "Dirty", False))
    prior_alerts = bool(getattr(app, "DisplayAlerts", True))
    try:
        app.DisplayAlerts = False
        # Close() is the same Solid Edge COM method used after a successful
        # SaveAs. With DisplayAlerts disabled it cannot prompt or save.
        current.Close()
    finally:
        try:
            app.DisplayAlerts = prior_alerts
        except Exception:
            pass

    remaining = [
        document_identity(app.Documents.Item(index))
        for index in range(1, int(app.Documents.Count) + 1)
    ]
    if identity in remaining:
        raise RuntimeError("Solid Edge did not close the exact imported PartDocument: " + repr(identity))
    return {
        "status": "closed",
        "identity": identity,
        "dirty_discarded": dirty,
        "display_alerts_restored": bool(getattr(app, "DisplayAlerts", True)) == prior_alerts,
    }


def open_step_once_with_template(bridge, app, owned_process_id, step):
    """One STEP OpenWithTemplate call, followed by owned-session reconciliation; never replay."""
    if step.suffix.casefold() not in (".step", ".stp"):
        raise ValueError(f"Non-STEP input passed to STEP importer: {step}")
    if not step.is_file() or step.stat().st_size < 100:
        raise FileNotFoundError(f"STEP input missing or too small: {step}")
    if not ISO_METRIC_TEMPLATE.is_file():
        raise FileNotFoundError(f"ISO Metric template missing: {ISO_METRIC_TEMPLATE}")
    pre = dialogs(int(owned_process_id))
    if int(pre.get("modalCount") or 0):
        raise RuntimeError("Owned Solid Edge session already has a modal dialog: " + json.dumps(pre.get("dialogs", []), ensure_ascii=False)[:1200])

    docs = app.Documents
    before_count = int(docs.Count)
    before = set()
    for index in range(1, before_count + 1):
        before.add(document_identity(docs.Item(index)))
    started = time.monotonic()
    returned = None
    call_error = None
    try:
        returned = docs.OpenWithTemplate(str(step.resolve()), str(ISO_METRIC_TEMPLATE.resolve()), False)
    except Exception as exc:
        call_error = f"{type(exc).__name__}: {exc}"

    # Reconcile once after the one mutating call. The function never invokes Open again.
    after_count = int(docs.Count)
    new_parts = []
    for index in range(1, after_count + 1):
        d = docs.Item(index)
        identity = document_identity(d)
        if identity not in before and identity[2] == 1:
            new_parts.append(d)
    if returned is not None:
        returned_identity = document_identity(returned)
        if returned_identity in before:
            raise RuntimeError("OpenWithTemplate returned a pre-existing document; refusing to reuse or close it: " + repr(returned_identity))
        if len(new_parts) != 1 or document_identity(new_parts[0]) != returned_identity:
            raise RuntimeError("OpenWithTemplate returned an ambiguous/unreconciled document set; no replay permitted: " + json.dumps({
                "step": str(step), "pid": owned_process_id, "before_count": before_count,
                "after_count": after_count, "new_part_documents": len(new_parts),
                "returned_identity": returned_identity, "call_error": call_error
            }, ensure_ascii=False))
        imported = returned
    elif len(new_parts) == 1:
        imported = new_parts[0]
    else:
        raise RuntimeError("OpenWithTemplate outcome unresolved after one attempt; no replay permitted: " + json.dumps({
            "step": str(step), "pid": owned_process_id, "before_count": before_count,
            "after_count": after_count, "new_part_documents": len(new_parts), "call_error": call_error
        }, ensure_ascii=False))
    if int(getattr(imported, "Type", 0)) != 1:
        raise RuntimeError("OpenWithTemplate did not return a PartDocument")
    modal_state = dialogs(int(owned_process_id))
    handled = []
    if int(modal_state.get("modalCount") or 0):
        result = settle_import_dialogs(step, int(owned_process_id))
        handled = result.get("handled", [])
        modal_state = dialogs(int(owned_process_id))
    if int(modal_state.get("modalCount") or 0):
        cleanup = None
        try:
            cleanup = close_owned_import_document(app, owned_process_id, imported, before)
        except Exception as cleanup_error:
            cleanup = {"status": "failed", "error": f"{type(cleanup_error).__name__}: {cleanup_error}"}
        raise RuntimeError("STEP import left a modal dialog: " + json.dumps({
            "dialogs": modal_state.get("dialogs", []), "document_identity": document_identity(imported),
            "document_cleanup": cleanup
        }, ensure_ascii=False)[:1800])
    return imported, {
        "method": "Documents.OpenWithTemplate",
        "application_process_id": int(owned_process_id),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "documents_before": before_count, "documents_after": after_count,
        "open_exception_reconciled": bool(call_error), "open_exception": call_error,
        "modal_count_after": 0, "dialogs_handled": handled,
        "document_name": str(getattr(imported, "Name", "")),
        "document_full_name": str(getattr(imported, "FullName", "")),
        "document_type": int(imported.Type),
        "preexisting_document_identities": sorted([list(x) for x in before]),
        "created_by_this_open_call": True,
    }


def combine_bboxes(rows):
    """Combine available body extents into a single native-document bounding box."""
    boxes = [x.get("bbox_mm") for x in rows if x.get("bbox_mm") and len(x["bbox_mm"]) == 6]
    if not boxes:
        return None
    return [min(b[i] for b in boxes) if i < 3 else max(b[i] for b in boxes) for i in range(6)]



def snapshot_existing_output(path):
    """Keep the prior run-local PAR bytes before replacing a file that may be open/dirty."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        raise RuntimeError(f"Refusing to snapshot/replace a PAR outside this run: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    quarantine = LOGS / "Quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    backup = quarantine / f"{path.stem}_pre_promotion_{digest[:12]}{path.suffix}"
    if not backup.exists():
        shutil.copy2(path, backup)
    if hashlib.sha256(backup.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"Quarantine copy hash mismatch for {path}")
    return {"path": str(backup), "sha256": digest, "bytes": backup.stat().st_size}


def close_owned_run_document(bridge, app, owned_process_id, path):
    """Close only an exact document path in the bridge-owned process, snapshotting before discarding dirty state."""
    target = Path(path).resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        raise RuntimeError(f"Refusing to close a document outside this run: {target}")
    if int(app.ProcessID) != int(owned_process_id):
        raise RuntimeError("Solid Edge Application PID changed before closing the run-output document")
    matches = []
    for index in range(1, int(app.Documents.Count) + 1):
        document = app.Documents.Item(index)
        full_name = str(getattr(document, "FullName", "") or "")
        if full_name and Path(full_name).resolve() == target:
            matches.append(document)
    if not matches:
        return {"status": "not_open", "path": str(target)}
    if len(matches) != 1:
        raise RuntimeError(f"Multiple exact-path documents are open in the owned application: {target}")
    document = matches[0]
    dirty = bool(getattr(document, "Dirty", False))
    snapshot = snapshot_existing_output(target) if dirty else None

    current = active_doc(bridge)
    if int(current.get("_application_process_id") or 0) != int(owned_process_id):
        raise RuntimeError("Bridge is attached to a different Solid Edge process than the document owner")
    closed = bridge.write_tool(
        "se_close_document",
        {"target": str(target), "confirm": bool(dirty)}
    )
    if not isinstance(closed, dict) or closed.get("status") != "ok":
        raise RuntimeError("Could not close the exact run-output document: " + json.dumps(closed, ensure_ascii=False))
    remaining = []
    for index in range(1, int(app.Documents.Count) + 1):
        document = app.Documents.Item(index)
        full_name = str(getattr(document, "FullName", "") or "")
        if full_name and Path(full_name).resolve() == target:
            remaining.append(full_name)
    if remaining:
        raise RuntimeError(f"Document remains open after close request: {remaining}")
    return {"status": "closed", "path": str(target), "dirty_was": dirty, "snapshot": snapshot, "bridge_result": closed}


def promote_verified_staging(bridge, app, owned_process_id, staging, target):
    """Promote a reopened+verified staged PAR after releasing exact-path file locks."""
    staging = Path(staging)
    target = Path(target)
    stage_hash = hashlib.sha256(staging.read_bytes()).hexdigest()
    prior_snapshot = snapshot_existing_output(target)
    close_result = close_owned_run_document(bridge, app, owned_process_id, target)
    try:
        os.replace(staging, target)
    except PermissionError as exc:
        raise RuntimeError(
            f"Windows denied atomic replace for {target}. Exact owned document close result: "
            + json.dumps(close_result, ensure_ascii=False)
            + f"; prior snapshot: {prior_snapshot}; error={exc}"
        )
    final_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    if final_hash != stage_hash:
        raise RuntimeError(f"Native PAR hash changed during verified promotion: {target}")
    return {
        "staging_hash": stage_hash,
        "final_hash": final_hash,
        "atomic_replace": True,
        "prior_target_snapshot": prior_snapshot,
        "prior_open_document_close": close_result,
    }

def flatten_report_bbox(value):
    """Normalize a nested report bounding box into the importer comparison format."""
    if not value:
        return None
    if len(value) == 2 and all(isinstance(x, (list, tuple)) and len(x) == 3 for x in value):
        return [float(x) for x in list(value[0]) + list(value[1])]
    if len(value) == 6:
        return [float(x) for x in value]
    return None


def heal_current_body(bridge, body_id):
    """Run the Solid Edge native heal/optimize operation on one imported body.

    This is the deterministic recovery used when STEP translation creates a
    topologically invalid Parasolid body. It never invents geometry; it asks
    Solid Edge's native Parasolid body repair to heal the imported body, then
    callers must re-read and verify topology.
    """
    attempts=[]
    for args in ([True,True],[True],[ ]):
        try:
            result=bridge.write_tool('se_invoke_member',{
                'objectId':body_id,
                'member':'HealAndOptimizeBody',
                'args':args
            })
            attempts.append({'args':args,'result':result})
            if isinstance(result,dict) and result.get('status')=='ok':
                return {'status':'HEALED_OR_OPTIMIZED','attempts':attempts}
        except Exception as exc:
            attempts.append({'args':args,'error':str(exc)})
    return {'status':'HEAL_NOT_CONFIRMED','attempts':attempts}


def body_id_from_topology_error(message):
    """Extract a body identifier from a native topology diagnostic when the message contains one."""
    m=re.search(r'"body_id"\s*:\s*"([^"]+)"',str(message))
    return m.group(1) if m else None



def body_metrics(bridge):
    """Read model bodies and construction surfaces from the exact bridge-owned active PartDocument."""
    active = active_doc(bridge)
    pid = int(active.get("_application_process_id") or 0)
    if pid <= 0 or active.get("typeShort") != "PartDocument":
        raise RuntimeError("Active document is not a bridge-owned PartDocument: " + json.dumps(active, ensure_ascii=False))
    app = bind_owned_application(pid)
    doc = com_property(app, "ActiveDocument")
    if int(getattr(doc, "Type", 0)) != 1:
        raise RuntimeError("Owned active document is not a PartDocument")

    models = com_property(doc, "Models")
    model_count = int(models.Count)
    model_rows = []
    solid_count = 0
    volume_solid_m3 = 0.0
    face_total = 0
    loop_total = 0
    vertex_total = 0
    shell_total = 0
    edge_total = 0
    model_face_area_signature = []
    construction_face_area_signature = []
    construction_face_area_signature_complete = True
    warnings = []

    for index in range(1, model_count + 1):
        model = models.Item(index)
        body = com_property(model, "Body")
        row = com_body_metrics(body, f"Model_{index}")
        row.update({"model_index": index, "kind": "MODEL"})
        model_rows.append(row)
        model_face_area_signature.extend(row.get("face_areas_mm2", []))
        face_total += int(row["faces"])
        loop_total += int(row["loops"])
        vertex_total += int(row["vertices"])
        shell_total += int(row["shells"])
        edge_total += int(row["edges"])
        if row["is_solid"]:
            solid_count += 1
            volume_solid_m3 += float(row["volume_m3"])
        if not row["valid"]:
            warnings.append({"code": "NATIVE_MODEL_VALID_FALSE", "model_index": index, "name": row["name"]})

    construction_data = collect_surface_constructions(doc)
    construction_rows = construction_data["bodies"]
    for row in construction_rows:
        row["kind"] = "CONSTRUCTION_SURFACE"
        # Parasolid may expose two-sided face topology for one source surface.
        # The boundary-loop count is the comparable source-Brep face proxy.
        row["face_proxy"] = int(row["loops"])
        native_surface_areas = sorted(row.get("face_areas_mm2", []))
        proxy_count = int(row["face_proxy"])
        if len(native_surface_areas) == proxy_count:
            construction_face_area_signature.extend(native_surface_areas)
        elif proxy_count > 0 and len(native_surface_areas) == proxy_count * 2:
            # Solid Edge represents a CopyConstruction surface with both sides
            # in the shell face collection. Collapse exact/tolerance-equal pairs
            # to the source surface-face signature, but only when every pair agrees.
            pairs_match = all(
                abs(native_surface_areas[i] - native_surface_areas[i + proxy_count])
                <= max(1e-8, native_surface_areas[i] * 1e-7)
                for i in range(proxy_count)
            )
            if pairs_match:
                construction_face_area_signature.extend(native_surface_areas[:proxy_count])
            else:
                construction_face_area_signature_complete = False
        else:
            construction_face_area_signature_complete = False
        loop_total += int(row["loops"])
        vertex_total += int(row["vertices"])
        shell_total += int(row["shells"])
        edge_total += int(row["edges"])

    bbox = combine_bboxes(model_rows + construction_rows)
    all_rows = model_rows + construction_rows
    if not all_rows:
        raise RuntimeError("PartDocument contains neither model bodies nor construction surface bodies")
    return {
        "document_id": str(active.get("name") or ""),
        "document_full_name": str(active.get("fullName") or ""),
        "application_process_id": pid,
        "models_count": model_count,
        "body_count": len(all_rows),
        "models": model_rows,
        "construction_copy_count": construction_data["copy_construction_count"],
        "construction_surfaces": construction_rows,
        "construction_read_error": construction_data.get("read_error"),
        "construction_surface_count": len(construction_rows),
        "valid": all(bool(x["valid"]) for x in model_rows + construction_rows),
        "is_solid": bool(model_rows) and solid_count == len(model_rows),
        "solid_models_count": solid_count,
        "volume_solid_m3": volume_solid_m3,
        "volume_m3": volume_solid_m3,
        "faces": face_total + sum(int(x["face_proxy"]) for x in construction_rows),
        "model_faces": face_total,
        "face_areas_mm2": sorted(model_face_area_signature + construction_face_area_signature)
            if construction_face_area_signature_complete else sorted(model_face_area_signature),
        "model_face_areas_mm2": sorted(model_face_area_signature),
        "construction_face_areas_mm2": sorted(construction_face_area_signature),
        "construction_face_area_signature_complete": construction_face_area_signature_complete,
        "surface_face_proxy": sum(int(x["face_proxy"]) for x in construction_rows),
        "construction_shell_face_count": sum(int(x["faces"]) for x in construction_rows),
        "loops": loop_total,
        "vertices": vertex_total,
        "shells": shell_total,
        "edges": edge_total,
        "bbox_mm": bbox,
        "warnings": warnings,
    }


def validate_native_against_step(metrics, step_record):
    """Accept a native PartDocument when it contains at least one imported model/body and face.

    Solid Edge's own validity/topology flags are retained as diagnostics; they do not
    prevent saving and assembling a STEP translation. Disk save/close/reopen is the gate.
    """
    body_count=int(metrics.get("body_count") or metrics.get("models_count") or 0)
    model_count=int(metrics.get("models_count") or 0)
    face_count=int(metrics.get("faces") or 0)
    hard=[]
    if body_count<=0:
        hard.append("STEP import produced no native model or construction body")
    warnings=list(metrics.get("warnings",[]))
    if metrics.get("valid") is False:
        warnings.append({"code":"SOLID_EDGE_BODY_VALID_FALSE","action":"retained; geometry validity is diagnostic, not an import/assembly gate"})
    if not metrics.get("is_solid"):
        warnings.append({"code":"NATIVE_MODEL_NOT_SOLID","action":"retained as imported STEP geometry"})
    return {
        "passed":not hard,"hard_failures":hard,"warnings":warnings,
        "acceptance":"native STEP PartDocument imported and contains body geometry; disk save/close/reopen is checked separately",
        "models_count":model_count,"body_count":body_count,"face_count":face_count,
        "native_valid":metrics.get("valid"),"native_is_solid":metrics.get("is_solid"),
    }
def _normalized_full_path(value):
    """Normalize a document path for exact comparison inside one Solid Edge process."""
    return os.path.normcase(os.path.abspath(str(value or ""))).casefold()


def document_is_open_in_application(app, path):
    """Return whether the exact target file is already open in the owned application."""
    wanted = _normalized_full_path(path)
    for index in range(1, int(app.Documents.Count) + 1):
        document = app.Documents.Item(index)
        full_name = str(getattr(document, "FullName", "") or "")
        if full_name and _normalized_full_path(full_name) == wanted:
            return True
    return False


def close_run_verification_document(bridge, path, *, was_preexisting, label):
    """Close only a file this run opened read-only for verification.

    Read-only verification may leave a COM document Dirty because Solid Edge
    resolves translator features on open. Confirm=True discards those transient
    in-memory changes; it is never used for a document that pre-dated this batch.
    """
    if was_preexisting:
        return {"status": "LEFT_OPEN_PREEXISTING", "path": str(path)}
    closed = check_result(
        bridge.write_tool("se_close_document", {"target": str(path), "confirm": True}),
        label
    )
    return {"status": "CLOSED_RUN_VERIFICATION_COPY", "result": closed}


def quarantine_unmatched_part_candidates(parts_dir, expected_relative_paths, logs_dir):
    """Move stale Desktop-cache PARs out of the deliverable Parts folder.

    Only filenames absent from the current manifest are moved. The file bytes
    are preserved under Logs/Quarantine and the move is hash-recorded.
    """
    parts_dir = Path(parts_dir)
    quarantine = Path(logs_dir) / "Quarantine" / "unmatched_baseline_candidates"
    expected = {Path(str(value).replace(chr(92), "/")).name.casefold()
                for value in expected_relative_paths}
    moved = []
    for source in sorted(parts_dir.glob("*.par"), key=lambda item: item.name.casefold()):
        if source.name.casefold() in expected:
            continue
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        quarantine.mkdir(parents=True, exist_ok=True)
        target = quarantine / f"{source.stem}_{digest[:12]}{source.suffix}"
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"Unmatched candidate quarantine collision: {target}")
            source.unlink()
            disposition = "DUPLICATE_BYTES_ALREADY_QUARANTINED"
        else:
            os.replace(source, target)
            disposition = "MOVED_TO_QUARANTINE"
        moved.append({"source_name": source.name, "quarantine_path": str(target),
                      "sha256": digest, "bytes": target.stat().st_size,
                      "disposition": disposition})
    return moved


def verify_native(bridge, path, step_record):
    """Open the saved PAR read-only, assert exact path identity, and compare its full
    model + construction-surface topology against the verified STEP invariants.
    """
    target = Path(path).resolve()
    opened = check_result(
        bridge.write_tool("se_open_document", {"path": str(target), "readOnly": True}),
        "open native PAR for verification"
    )
    doc = active_doc(bridge)
    if doc.get("typeShort") != "PartDocument":
        raise RuntimeError("reopened native file is not a PartDocument: " + json.dumps(doc, ensure_ascii=False))
    actual_path = doc.get("fullName") or doc.get("document", {}).get("fullName")
    if not actual_path or _normalized_full_path(actual_path) != _normalized_full_path(target):
        raise RuntimeError("Solid Edge did not activate the exact requested native PAR: " + json.dumps({
            "requested": str(target), "active": actual_path, "document": doc
        }, ensure_ascii=False))
    metrics = body_metrics(bridge)
    validation = validate_native_against_step(metrics, step_record)
    if not validation["passed"]:
        raise RuntimeError("reopened native PAR failed source-geometry validation: " + json.dumps(validation, ensure_ascii=False)[:3000])
    return {"open": opened, "document": doc, "topology": metrics, "validation": validation}



def _bridge_tool_value(result, label):
    """Call one bridge tool and unwrap its result while rejecting malformed or failed responses."""
    if not isinstance(result, dict) or result.get("status") != "ok":
        raise RuntimeError(label + ": " + json.dumps(result, ensure_ascii=False)[:1800])
    return result


def _bridge_batch_row(bridge, object_id, members, label):
    """Normalize one row returned by the bridge batch API."""
    result = _bridge_tool_value(
        bridge.read_tool("se_batch_read", {"targets": [object_id], "members": list(members)}),
        label,
    )
    rows = result.get("rows") or []
    if len(rows) != 1 or rows[0].get("status") != "ok":
        raise RuntimeError(label + ": expected one successful batch-read row; " + json.dumps(result, ensure_ascii=False)[:1200])
    return rows[0]


def _bridge_com_handle(row, member, label):
    """Resolve a COM handle from a bridge response without guessing the active document."""
    value = (row.get("values") or {}).get(member) or {}
    handle = value.get("handle")
    if not handle:
        raise RuntimeError(label + ": " + member + " did not return a COM handle: " + json.dumps(value, ensure_ascii=False))
    return handle


def _bridge_count(bridge, handle, label):
    """Read a collection count from a typed bridge result."""
    row = _bridge_batch_row(bridge, handle, ["Count"], label)
    value = (row.get("values") or {}).get("Count", {}).get("value")
    if value is None:
        raise RuntimeError(label + ": Count is unavailable")
    return int(float(value))


def _bridge_item_handle(bridge, collection_handle, index, label):
    """Resolve one indexed collection item through the guarded bridge API."""
    result = _bridge_tool_value(
        bridge.write_tool("se_invoke_chain", {
            "objectId": collection_handle,
            "steps": [{"member": "Item", "args": [int(index)]}],
        }),
        label,
    )
    steps = result.get("steps") or []
    handle = (steps[-1].get("returnValue") or {}).get("handle") if steps else None
    if not handle:
        raise RuntimeError(label + ": Item(" + str(index) + ") returned no COM handle: " + json.dumps(result, ensure_ascii=False)[:1200])
    return handle


def _bridge_chain_handle(bridge, object_id, steps, label):
    """Resolve a nested COM object by following an explicit member chain."""
    result = _bridge_tool_value(
        bridge.write_tool("se_invoke_chain", {"objectId": object_id, "steps": steps}),
        label,
    )
    rows = result.get("steps") or []
    handle = (rows[-1].get("returnValue") or {}).get("handle") if rows else None
    if not handle:
        raise RuntimeError(label + ": final chain step returned no COM handle: " + json.dumps(result, ensure_ascii=False)[:1200])
    return handle


def _bridge_description_properties(bridge, object_id, label):
    """Convert a bridge object description into a property lookup map."""
    result = _bridge_tool_value(
        bridge.read_tool("se_describe_object", {"objectId": object_id, "mode": "full"}),
        label,
    )
    props = {}
    for row in result.get("properties") or []:
        if row.get("readable") is False:
            continue
        props[str(row.get("name") or "")] = row.get("value")
    return result, props


def _bridge_bool(value):
    """Normalize a bridge boolean result while preserving explicit unknown/error states."""
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in ("true", "1", "yes")


def _bridge_collection_numeric_values(bridge, collection_id, total_count, member, label, chunk_size=200):
    """Read a collection's numeric property values in bounded in-process batches."""
    total_count = int(total_count)
    values = []
    for start_index in range(1, total_count + 1, int(chunk_size)):
        expected_count = min(int(chunk_size), total_count - start_index + 1)
        result = _bridge_tool_value(
            bridge.read_tool("se_read_collection", {
                "target": collection_id,
                "startIndex": start_index,
                "maxItems": expected_count,
                "member": str(member),
            }),
            label + " collection items " + str(start_index) + "-" + str(start_index + expected_count - 1),
        )
        rows = result.get("items") or []
        if int(result.get("startIndex") or 0) != start_index or int(result.get("count") or -1) != expected_count or len(rows) != expected_count:
            raise RuntimeError(label + ": collection batch was incomplete or out of order: " + json.dumps(result, ensure_ascii=False)[:1600])
        for offset, row in enumerate(rows):
            expected_index = start_index + offset
            if int(row.get("index") or 0) != expected_index or row.get("value") is None:
                raise RuntimeError(label + ": missing/non-numeric " + str(member) + " at collection index " + str(expected_index) + ": " + json.dumps(row, ensure_ascii=False))
            try:
                values.append(float(row["value"]))
            except (TypeError, ValueError) as exc:
                raise RuntimeError(label + ": non-numeric " + str(member) + " at collection index " + str(expected_index)) from exc
    return values


def _bridge_body_metrics(bridge, body_id, label):
    """Read the minimum body facts needed to report a STEP import."""
    description, props = _bridge_description_properties(bridge, body_id, "describe " + label)
    shells_row = _bridge_batch_row(bridge, body_id, ["Shells"], "body shells " + label)
    shells_handle = _bridge_com_handle(shells_row, "Shells", label)
    shell_count = _bridge_count(bridge, shells_handle, label + " shell count")
    faces = edges = 0
    for shell_index in range(1, shell_count + 1):
        shell = _bridge_item_handle(bridge, shells_handle, shell_index, label + " shell")
        collections = _bridge_batch_row(bridge, shell, ["Faces", "Edges"], label + " shell collections")
        faces_handle = _bridge_com_handle(collections, "Faces", label + " faces")
        edges_handle = _bridge_com_handle(collections, "Edges", label + " edges")
        faces += _bridge_count(bridge, faces_handle, label + " face count")
        edges += _bridge_count(bridge, edges_handle, label + " edge count")
    bbox = None
    try:
        geometry = _bridge_tool_value(bridge.read_tool("se_read_geometry", {"target": body_id}), "read body range " + label)
        values = geometry.get("rangeBox")
        if isinstance(values, list) and len(values) == 6:
            bbox = [float(x) * 1000.0 for x in values]
    except Exception:
        pass
    return {
        "name": label, "valid": _bridge_bool(props.get("Valid")),
        "is_solid": _bridge_bool(props.get("IsSolid")),
        "volume_m3": float(props.get("Volume") or 0.0),
        "shells": shell_count, "faces": faces, "edges": edges, "bbox_mm": bbox,
    }


def _bridge_document_metrics(bridge, document_id, doc_info):
    """Count imported native models/surfaces; body validity is diagnostic only."""
    models_handle = _bridge_chain_handle(bridge, document_id, [{"member": "Models"}], "get imported document Models")
    model_count = _bridge_count(bridge, models_handle, "imported document Models.Count")
    model_rows = []
    for index in range(1, model_count + 1):
        model = _bridge_item_handle(bridge, models_handle, index, "imported Model")
        body = _bridge_chain_handle(bridge, model, [{"member": "Body"}], "get imported Model.Body")
        row = _bridge_body_metrics(bridge, body, "Model_" + str(index))
        row.update({"model_index": index, "kind": "MODEL"})
        model_rows.append(row)
    construction_count = 0
    construction_error = None
    try:
        row = _bridge_batch_row(bridge, document_id, ["Constructions"], "PartDocument.Constructions")
        constructions = _bridge_com_handle(row, "Constructions", "PartDocument")
        row = _bridge_batch_row(bridge, constructions, ["CopyConstructions"], "Constructions.CopyConstructions")
        copies = _bridge_com_handle(row, "CopyConstructions", "Constructions")
        construction_count = _bridge_count(bridge, copies, "CopyConstructions.Count")
    except Exception as exc:
        construction_error = str(exc)
    body_count = model_count + construction_count
    face_count = sum(int(x.get("faces") or 0) for x in model_rows)
    solid_count = sum(1 for x in model_rows if x.get("is_solid"))
    volume = sum(float(x.get("volume_m3") or 0.0) for x in model_rows if x.get("is_solid"))
    boxes = [x.get("bbox_mm") for x in model_rows if x.get("bbox_mm")]
    bbox = None
    if boxes:
        bbox = [min(x[i] for x in boxes) for i in range(3)] + [max(x[i] for x in boxes) for i in range(3)]
    return {
        "document_id": str(doc_info.get("name") or ""),
        "document_full_name": str(doc_info.get("fullName") or ""),
        "models_count": model_count, "body_count": body_count,
        "construction_copy_count": construction_count,
        "construction_read_error": construction_error,
        "models": model_rows,
        "valid": all(bool(x.get("valid")) for x in model_rows) if model_rows else None,
        "is_solid": bool(model_rows) and solid_count == model_count,
        "solid_models_count": solid_count, "faces": face_count,
        "volume_m3": volume, "volume_solid_m3": volume, "bbox_mm": bbox,
    }

def _bridge_document_inventory(bridge):
    """Enumerate exact full paths of open docs and their handles through this bridge session."""
    selection = _bridge_tool_value(bridge.read_tool("se_get_selection", {}), "get active document handle")
    items = selection.get("items") or []
    if not items:
        raise RuntimeError("No active Solid Edge document; cannot inventory the owned bridge session")
    active_id = items[0]["id"]
    doc_app_row = _bridge_batch_row(bridge, active_id, ["Application"], "read ActiveDocument.Application")
    app_handle = _bridge_com_handle(doc_app_row, "Application", "ActiveDocument")
    app_docs_row = _bridge_batch_row(bridge, app_handle, ["Documents"], "read Application.Documents")
    docs_handle = _bridge_com_handle(app_docs_row, "Documents", "Application")
    count = _bridge_count(bridge, docs_handle, "Application.Documents.Count")
    rows = []
    for index in range(1, count + 1):
        handle = _bridge_item_handle(bridge, docs_handle, index, "Application.Documents.Item")
        row = _bridge_batch_row(bridge, handle, ["Name", "FullName", "Type", "Dirty"], "read document identity")
        values = row.get("values") or {}
        name = str(values.get("Name", {}).get("value") or "")
        full_name = str(values.get("FullName", {}).get("value") or "")
        doc_type = int(float(values.get("Type", {}).get("value") or 0))
        dirty = _bridge_bool(values.get("Dirty", {}).get("value"))
        rows.append({
            "handle": handle,
            "name": name,
            "fullName": full_name,
            "type": doc_type,
            "dirty": dirty,
            "identity": (full_name or name, doc_type),
        })
    return rows


def _bridge_active_document(bridge):
    """Read the active document from the workflow-owned Solid Edge bridge."""
    response = bridge.get_active_document()
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise RuntimeError("Solid Edge bridge is not connected: " + json.dumps(response, ensure_ascii=False)[:1200])
    active = response.get("active_document") or {}
    if active.get("status") != "ok":
        raise RuntimeError("Solid Edge bridge has no active document: " + json.dumps(active, ensure_ascii=False)[:1200])
    document = dict(active.get("document") or {})
    document["_application_process_id"] = int(active.get("applicationProcessId") or 0)
    if document["_application_process_id"] <= 0:
        raise RuntimeError("Solid Edge bridge did not expose Application.ProcessID")
    return document


def _bridge_active_document_handle(bridge, expected_pid):
    """Resolve the active document COM handle for the owned Solid Edge process."""
    doc_info = _bridge_active_document(bridge)
    if int(doc_info.get("_application_process_id") or 0) != int(expected_pid):
        raise RuntimeError("Active PartDocument belongs to an unexpected Solid Edge process")
    selection = _bridge_tool_value(bridge.read_tool("se_get_selection", {}), "resolve active PartDocument handle")
    items = selection.get("items") or []
    if len(items) != 1:
        raise RuntimeError("se_get_selection did not resolve exactly one active PartDocument")
    return items[0]["id"], doc_info


def _bridge_modal_state(owned_pid):
    """Read modal-dialog state for the exact workflow-owned Solid Edge process."""
    state = dialogs(int(owned_pid))
    if int(state.get("modalCount") or 0):
        raise RuntimeError("Unresolved modal remains in the pipeline-owned Solid Edge session: " + json.dumps(state.get("dialogs", []), ensure_ascii=False)[:1800])
    return state


def _bridge_open_document(bridge, path, owned_pid, allow_step_template_dialog=False):
    """Open one requested document through the guarded bridge and return its reconciled identity."""
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    before_modal = dialogs(int(owned_pid))
    if int(before_modal.get("modalCount") or 0):
        raise RuntimeError("Solid Edge already has a modal before opening " + str(path) + ": " + json.dumps(before_modal.get("dialogs", []), ensure_ascii=False)[:1200])
    result = bridge.write_tool("se_open_document", {"path": str(path), "readOnly": False})
    handled = []
    if not isinstance(result, dict) or result.get("status") != "ok":
        after = dialogs(int(owned_pid))
        if int(after.get("modalCount") or 0):
            if not allow_step_template_dialog:
                raise RuntimeError("Unexpected modal opening native PAR " + str(path) + ": " + json.dumps(after.get("dialogs", []), ensure_ascii=False)[:1200])
            dialog_result = settle_import_dialogs(path, int(owned_pid), timeout=55)
            handled = dialog_result.get("handled", [])
        elif allow_step_template_dialog:
            # A STEP Open may return a transport error while its one COM call is
            # still completing. Reconcile the active document before deciding.
            time.sleep(0.75)
    elif allow_step_template_dialog:
        after = dialogs(int(owned_pid))
        if int(after.get("modalCount") or 0):
            dialog_result = settle_import_dialogs(path, int(owned_pid), timeout=55)
            handled = dialog_result.get("handled", [])
    active = _bridge_active_document(bridge)
    if int(active.get("_application_process_id") or 0) != int(owned_pid) or active.get("typeShort") != "PartDocument":
        raise RuntimeError("Open did not activate a PartDocument in the owned Solid Edge session: " + json.dumps(active, ensure_ascii=False)[:1800])
    active_name = Path(str(active.get("name") or "")).stem.casefold()
    expected_name = path.stem.casefold()
    if active_name != expected_name:
        raise RuntimeError("Open activated an unexpected document: expected=" + expected_name + " actual=" + active_name + " path=" + str(path))
    handle = result.get("handle") if isinstance(result, dict) else None
    if not handle:
        handle, active = _bridge_active_document_handle(bridge, owned_pid)
    else:
        active = _bridge_active_document(bridge)
    if allow_step_template_dialog and result.get("status") != "ok":
        # A second read confirms the dialog handler/previous one-shot Open completed.
        _bridge_modal_state(owned_pid)
    return handle, active, {
        "status": "ok",
        "path": str(path),
        "already_open": bool(result.get("alreadyOpen", False)) if isinstance(result, dict) else False,
        "tracked": bool(result.get("tracked", True)) if isinstance(result, dict) else True,
        "open_response": result,
        "dialogs_handled": handled,
    }


def _bridge_save_as(bridge, document_id, staging):
    """Save the current owned document to the exact run-scoped destination."""
    staging = Path(staging).resolve()
    if staging.exists():
        raise FileExistsError("Staging PAR unexpectedly exists: " + str(staging))
    result = _bridge_tool_value(
        bridge.write_tool("se_invoke_member", {
            "objectId": document_id, "member": "SaveAs", "args": [str(staging)],
            "propertySet": False, "confirm": True, "verify": True,
        }),
        "SaveAs staged native PAR",
    )
    post = _bridge_batch_row(bridge, document_id, ["FullName", "Dirty", "ReadOnly"], "verify SaveAs")
    values = post.get("values") or {}
    full_name = str(values.get("FullName", {}).get("value") or "")
    if Path(full_name).resolve() != staging:
        raise RuntimeError("SaveAs path did not read back exactly: " + full_name)
    dirty = _bridge_bool(values.get("Dirty", {}).get("value"))
    if dirty:
        _bridge_tool_value(
            bridge.write_tool("se_invoke_member", {"objectId": document_id, "member": "Save", "args": [], "propertySet": False, "confirm": True, "verify": True}),
            "save staged native PAR",
        )
        post = _bridge_batch_row(bridge, document_id, ["FullName", "Dirty"], "verify staged native save")
        values = post.get("values") or {}
        if _bridge_bool(values.get("Dirty", {}).get("value")):
            raise RuntimeError("Staged native PartDocument remains dirty after Save")
    if not staging.is_file() or staging.stat().st_size < 1000:
        raise RuntimeError("Staged native PAR is missing or implausibly small: " + str(staging))
    return {"save_as": result, "staging_bytes": staging.stat().st_size, "full_name": full_name}


def _bridge_close_document(bridge, document_id, confirm=False, label="close native document"):
    """Close one explicitly identified workflow-owned document and verify its closure."""
    result = _bridge_tool_value(
        bridge.write_tool("se_close_document", {"target": document_id, "confirm": bool(confirm)}),
        label,
    )
    return {"status": "ok", "bridge_result": result}


def _bridge_quarantine_output(target, label):
    """Move a failed or unverified native output into run quarantine without promoting it as accepted."""
    target = Path(target)
    if not target.is_file():
        return None
    snapshot = snapshot_existing_output(target)
    return snapshot


def _bridge_ensure_session_ready(bridge, template_path=None):
    """Start only the run-scoped bridge and activate its ISO Metric Part template."""
    bridge_status = bridge.status()
    if isinstance(bridge_status, dict) and bridge_status.get("readonly") is True:
        raise RuntimeError("Pipeline-owned Solid Edge bridge is read-only; refusing to change bridge mode")

    bridge_start = None
    healthy = (
        isinstance(bridge_status, dict)
        and bridge_status.get("ok") is True
        and bridge_status.get("bridge_running") is not False
        and bridge_status.get("readonly") is not True
    )
    if not healthy:
        bridge_start = bridge.start()
        if not isinstance(bridge_start, dict) or bridge_start.get("ok") is not True:
            raise RuntimeError("Could not start the isolated Solid Edge bridge: " + json.dumps(bridge_start, ensure_ascii=False)[:1600])
        bridge_status = bridge.status()
        healthy = (
            isinstance(bridge_status, dict)
            and bridge_status.get("ok") is True
            and bridge_status.get("bridge_running") is not False
            and bridge_status.get("readonly") is not True
        )
        if not healthy:
            raise RuntimeError("Solid Edge bridge did not pass its post-start health check: " + json.dumps(bridge_status, ensure_ascii=False)[:1600])

    active_response = bridge.get_active_document()
    active_payload = (active_response or {}).get("active_document") or {}
    active_document = active_payload.get("document") or {}
    template_bootstrap = None
    if active_payload.get("status") != "ok" or active_document.get("typeShort") != "PartDocument":
        template = Path(template_path or ISO_METRIC_TEMPLATE).resolve()
        if not template.is_file():
            raise FileNotFoundError("ISO Metric Part template required to initialize the isolated bridge is missing: " + str(template))
        opened = _bridge_tool_value(
            bridge.write_tool("se_open_document", {"path": str(template), "readOnly": False}),
            "open isolated ISO Metric Part template",
        )
        active = _bridge_active_document(bridge)
        if active.get("typeShort") != "PartDocument" or Path(str(active.get("fullName") or "")).resolve() != template:
            raise RuntimeError("ISO Metric template open did not activate the expected PartDocument: " + json.dumps(active, ensure_ascii=False)[:1600])
        template_bootstrap = {
            "status": "VERIFIED", "path": str(template),
            "open_handle": opened.get("handle"), "application_process_id": active.get("_application_process_id"),
        }
    else:
        active = _bridge_active_document(bridge)
        if active.get("typeShort") != "PartDocument":
            raise RuntimeError("The isolated bridge active document is not a PartDocument: " + json.dumps(active, ensure_ascii=False)[:1600])

    return bridge_status, active, bridge_start, template_bootstrap


def run_bridge_tools_import_backend(
    bridge, report, report_path, log_path, requests, all_requests,
    prior_results, prior_failures, manifest, export_blocked, parts_dir,
    steps_dir, step_results_by_stem, native_fallbacks,
):
    """Bridge-only native importer. It never requires pywin32, ROT discovery or a second Solid Edge session."""
    started_at = datetime.now().astimezone().isoformat()
    bridge_status, active, bridge_start, template_bootstrap = _bridge_ensure_session_ready(bridge)
    owned_pid = int(active["_application_process_id"])
    baseline_docs = _bridge_document_inventory(bridge)
    baseline_identities = {tuple(x["identity"]) for x in baseline_docs}
    baseline_paths = {str(Path(x["fullName"]).resolve()).casefold() for x in baseline_docs if x.get("fullName") and Path(x["fullName"]).is_absolute()}
    report["solid_edge_bridge_process_id"] = bridge_status.get("pid")
    report["solid_edge_mcp_process_id"] = bridge_status.get("mcp_pid")
    report["solid_edge_application_pid"] = owned_pid
    report["solid_edge_initial_document"] = active
    report["solid_edge_documents_before_batch"] = len(baseline_docs)
    report["preexisting_document_identities"] = [list(x) for x in sorted(baseline_identities)]
    report["backend"] = "bridge_tools_no_rot"
    if bridge_start:
        report["bridge_start_recovery"] = bridge_start
    if template_bootstrap:
        report["template_bootstrap"] = template_bootstrap
    results = {str(x.get("document_key") or ""): dict(x) for x in report.get("results", [])}
    failures = {str(x.get("document_key") or ""): dict(x) for x in report.get("failures", [])}
    total = len(requests)
    report["batch_count"] = total
    'Persist the current per-document import results and aggregate counters atomically.'
    report["results"] = sorted(results.values(), key=lambda x: x.get("document_key", ""))
    report["failures"] = sorted(failures.values(), key=lambda x: x.get("document_key", ""))

    def save_checkpoint():
        """Persist completed import rows and aggregate counters as an atomic run checkpoint."""
        report["results"] = sorted(results.values(), key=lambda x: x.get("document_key", ""))
        report["failures"] = sorted(failures.values(), key=lambda x: x.get("document_key", ""))
        report["completed_count"] = sum(1 for x in results.values() if x.get("status") in (
            "imported_verified", "reused_verified", "imported_verified_with_warnings", "reused_verified_with_warnings",
        ))
        report["failed_count"] = len(failures)
        report["updated_at"] = datetime.now().astimezone().isoformat()
        tmp = report_path.with_suffix(report_path.suffix + ".tmp")
        tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, report_path)

    with log_path.open("a", encoding="utf-8") as log:
        for index, req in enumerate(requests, 1):
            key = str(req["key"])
            target = (Path(parts_dir) / Path(req["relative"]).name).resolve()
            try:
                target.relative_to(Path(parts_dir).resolve())
            except ValueError:
                raise RuntimeError("Refusing a native PAR output outside the run Parts folder: " + str(target))
            staging = target.with_name(target.stem + ".__staging__.par")
            step = Path(steps_dir) / (req["step_stem"] + ".stp")
            fallback = native_fallbacks.get(key.casefold())
            if fallback:
                step_record = fallback["step_record"]
                step_path = Path(fallback["asset_path"])
                step_hash = str(fallback["asset_sha256"])
            else:
                step_path = step.resolve()
                step_record = step_results_by_stem.get(req["step_stem"].casefold()) or {}
                if not step_record and not step_path.is_file():
                    raise RuntimeError("STEP export report and file are missing for " + key)
                if not step_path.is_file() or step_path.stat().st_size < 100:
                    raise FileNotFoundError("Canonical STEP missing or too small: " + str(step_path))
                step_hash = hashlib.sha256(step_path.read_bytes()).hexdigest()
                recorded_step_path = str(step_record.get("step_path") or "")
                recorded_step_hash = None
                for row in step_results_by_stem.values():
                    if str(row.get("step_path") or "").casefold() == str(step_path).casefold():
                        recorded_step_hash = row.get("step_sha256")
                        break
                if recorded_step_hash and recorded_step_hash != step_hash:
                    raise RuntimeError("STEP hash drift for " + key)
            row = {
                "document_key": key, "name": req.get("name"), "kind": req.get("kind"),
                "step": str(step_path), "step_sha256": step_hash, "output": str(target),
                "geometry_input_kind": "VERIFIED_NATIVE_FALLBACK_PAR" if fallback else "VERIFIED_STEP",
                "index": index,
            }
            if key in results:
                old = results[key]
                old_hash = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
                if old_hash and old_hash == old.get("native_sha256") and old.get("step_sha256") == step_hash:
                    continue
                results.pop(key, None)
            if key in failures and failures[key].get("step_sha256") == step_hash:
                # Explicit resume: do not blindly replay an unchanged failed import.
                row.update({"status": "quarantined_unchanged", "error": failures[key].get("error"), "resume_reused": True})
                results.pop(key, None)
                failures[key] = row
                save_checkpoint()
                continue
            import_handle = None
            stage_handle = None
            candidate_accepted = False
            try:
                # A target open before this batch is user/session-owned; never close, overwrite or silently claim it.
                if str(target).casefold() in baseline_paths:
                    row.update({
                        "status": "blocked_preexisting_open_document",
                        "error": "Target PAR was already open before this batch; left open and untouched.",
                    })
                    failures[key] = row
                    save_checkpoint()
                    continue

                # Treat an archive-seeded/native pre-existing PAR as a candidate, not proof.
                if target.is_file():
                    try:
                        opened, candidate_doc, open_meta = _bridge_open_document(bridge, target, owned_pid, allow_step_template_dialog=False)
                        import_handle = opened
                        metrics = _bridge_document_metrics(bridge, opened, candidate_doc)
                        validation = validate_native_against_step(metrics, step_record)
                        if validation.get("passed"):
                            closed = _bridge_close_document(bridge, opened, confirm=False, label="close verified candidate PAR")
                            native_hash = hashlib.sha256(target.read_bytes()).hexdigest()
                            row.update({
                                "status": "reused_verified_with_warnings" if validation.get("warnings") else "reused_verified",
                                "native_bytes": target.stat().st_size,
                                "native_sha256": native_hash,
                                "topology": {
                                    "valid": metrics.get("valid"), "body_count": metrics.get("body_count"),
                                    "models_count": metrics.get("models_count"), "is_solid": metrics.get("is_solid"),
                                    "solid_models_count": metrics.get("solid_models_count"), "faces": metrics.get("faces"),
                                    "volume_m3": metrics.get("volume_m3"), "bbox_mm": metrics.get("bbox_mm"),
                                },
                                "validation": validation,
                                "close_after_save": closed,
                                "reopen_verified": True,
                                "candidate_source": "existing_run_local_PAR_reopened",
                                "open": open_meta,
                            })
                            results[key] = row
                            failures.pop(key, None)
                            candidate_accepted = True
                            import_handle = None
                        else:
                            row["candidate_rejected"] = validation
                            _bridge_close_document(bridge, opened, confirm=False, label="close rejected candidate PAR")
                            import_handle = None
                    except Exception as candidate_error:
                        row["candidate_open_or_validation_error"] = str(candidate_error)
                        if import_handle:
                            try:
                                _bridge_close_document(bridge, import_handle, confirm=True, label="close failed untrusted PAR candidate")
                            except Exception as close_error:
                                raise RuntimeError("Candidate verification failed and exact tracked document could not be closed: " + str(close_error)) from close_error
                            import_handle = None
                    if candidate_accepted:
                        log.write(f"REUSE_VERIFIED {index}/{total} {key} native_sha256={row['native_sha256']}\n")
                        log.flush()
                        save_checkpoint()
                        continue

                if staging.exists():
                    _bridge_quarantine_output(staging, "stale_staging")
                    staging.unlink()
                if target.exists():
                    row["prior_target_snapshot"] = _bridge_quarantine_output(target, "pre_import_target")

                if fallback:
                    # Only source-bound fallback PARs that already passed current 002 identity filtering reach here.
                    shutil.copy2(step_path, staging)
                    import_handle, native_doc, open_meta = _bridge_open_document(bridge, staging, owned_pid, allow_step_template_dialog=False)
                else:
                    try:
                        opened_result = bridge.write_tool("se_open_document", {"path": str(step_path.resolve()), "readOnly": False})
                    except Exception as open_exc:
                        opened_result = {"status": "error", "message": str(open_exc)}
                    modal_state = dialogs(int(owned_pid))
                    handled = []
                    if int(modal_state.get("modalCount") or 0):
                        settled = settle_import_dialogs(step_path, int(owned_pid), timeout=55)
                        handled = settled.get("handled", [])
                    import_handle, native_doc = _bridge_active_document_handle(bridge, owned_pid)
                    active_name = Path(str(native_doc.get("name") or "")).stem.casefold()
                    if native_doc.get("typeShort") != "PartDocument" or active_name != Path(step_path).stem.casefold():
                        raise RuntimeError("STEP open did not reconcile to the expected new PartDocument: " + json.dumps({
                            "step": str(step_path), "active_document": native_doc, "open_response": opened_result,
                        }, ensure_ascii=False)[:1800])
                    if int(dialogs(int(owned_pid)).get("modalCount") or 0):
                        raise RuntimeError("A modal remained after STEP translator dialog settlement")
                    open_meta = {
                        "status": "ok", "path": str(step_path), "open_response": opened_result,
                        "dialogs_handled": handled, "application_process_id": owned_pid,
                    }

                metrics = _bridge_document_metrics(bridge, import_handle, native_doc)
                validation = validate_native_against_step(metrics, step_record)
                row["imported_topology"] = metrics
                row["validation"] = validation
                if not validation.get("passed"):
                    raise RuntimeError("translated native geometry failed STEP invariants: " + json.dumps(validation, ensure_ascii=False)[:3000])

                save_data = _bridge_save_as(bridge, import_handle, staging)
                row["save_as"] = save_data
                row["staging_path"] = str(staging)
                close_import = _bridge_close_document(bridge, import_handle, confirm=False, label="close saved STEP import before reopen")
                row["imported_document_close"] = close_import
                import_handle = None

                stage_handle, stage_doc, stage_open = _bridge_open_document(bridge, staging, owned_pid, allow_step_template_dialog=False)
                row["staging_reopen"] = stage_open
                stage_metrics = _bridge_document_metrics(bridge, stage_handle, stage_doc)
                stage_validation = validate_native_against_step(stage_metrics, step_record)
                row["staged_reopen_verification"] = {
                    "topology": stage_metrics, "validation": stage_validation,
                }
                if not stage_validation.get("passed"):
                    raise RuntimeError("saved native PAR failed disk reopen invariants: " + json.dumps(stage_validation, ensure_ascii=False)[:3000])
                close_stage = _bridge_close_document(bridge, stage_handle, confirm=False, label="close verified staging PAR after reopen")
                row["staging_document_cleanup"] = close_stage
                stage_handle = None

                if not staging.is_file():
                    raise FileNotFoundError("Staged PAR disappeared after close: " + str(staging))
                stage_sha = hashlib.sha256(staging.read_bytes()).hexdigest()
                prior_snapshot = row.get("prior_target_snapshot")
                os.replace(staging, target)
                final_sha = hashlib.sha256(target.read_bytes()).hexdigest()
                if stage_sha != final_sha:
                    raise RuntimeError("Native PAR SHA-256 changed during atomic promotion")
                row.update({
                    "status": "imported_verified_with_warnings" if stage_validation.get("warnings") else "imported_verified",
                    "native_bytes": target.stat().st_size,
                    "native_sha256": final_sha,
                    "topology": {
                        "valid": stage_metrics.get("valid"), "body_count": stage_metrics.get("body_count"),
                        "models_count": stage_metrics.get("models_count"), "is_solid": stage_metrics.get("is_solid"),
                        "solid_models_count": stage_metrics.get("solid_models_count"), "faces": stage_metrics.get("faces"),
                        "volume_m3": stage_metrics.get("volume_m3"), "bbox_mm": stage_metrics.get("bbox_mm"),
                    },
                    "validation": stage_validation,
                    "close_after_save": {"status": "ok", "bridge_close": close_stage},
                    "reopen_verified": True,
                    "promotion": {
                        "source": "fresh_STEP_translation" if not fallback else "source_bound_fallback_PAR",
                        "staging_sha256": stage_sha, "final_sha256": final_sha, "atomic_replace": True,
                        "prior_target_snapshot": prior_snapshot,
                    },
                    "open": open_meta,
                })
                results[key] = row
                failures.pop(key, None)
                log.write(f"VERIFIED {index}/{total} {key} faces={stage_metrics.get('faces')} sha256={final_sha}\n")
                log.flush()
            except Exception as exc:
                if import_handle:
                    try:
                        _bridge_close_document(bridge, import_handle, confirm=True, label="cleanup failed run-owned imported PartDocument")
                    except Exception as close_error:
                        row["failed_import_document_cleanup"] = {"status": "failed", "error": str(close_error)}
                if stage_handle:
                    try:
                        _bridge_close_document(bridge, stage_handle, confirm=True, label="cleanup failed run-owned staging PAR")
                    except Exception as close_error:
                        row["staging_document_cleanup"] = {"status": "failed", "error": str(close_error)}
                row.update({
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                })
                failures[key] = row
                log.write(f"FAILED {index}/{total} {key} {type(exc).__name__}: {exc}\n")
                log.flush()
            save_checkpoint()
            print(json.dumps({
                "index": index, "batch_total": total, "key": key,
                "status": row.get("status"), "error": row.get("error"),
                "completed": report.get("completed_count"), "failed": report.get("failed_count"),
            }, ensure_ascii=False), flush=True)

    final_docs = _bridge_document_inventory(bridge)
    final_identities = {tuple(x["identity"]) for x in final_docs}
    new_docs = [x for x in final_docs if tuple(x["identity"]) not in baseline_identities]
    report["solid_edge_documents_after_batch"] = len(final_docs)
    report["document_cleanup"] = {
        "status": "VERIFIED" if not new_docs else "INCOMPLETE",
        "baseline_document_count": len(baseline_docs),
        "final_document_count": len(final_docs),
        "new_documents_remaining": [
            {"name": x["name"], "fullName": x["fullName"], "type": x["type"], "dirty": x["dirty"]}
            for x in new_docs
        ],
        "preexisting_documents_left_untouched": len(baseline_docs),
    }
    report["finished_at"] = datetime.now().astimezone().isoformat()
    expected_eligible_count = int(report.get("eligible_native_import_count") or (len(all_requests) - len(export_blocked)))
    report["status"] = (
        "COMPLETED"
        if len(results) == expected_eligible_count
        and not failures and not new_docs
        else "INCOMPLETE"
    )
    report["geometry_export_exceptions_are_blocked"] = bool(export_blocked)
    save_checkpoint()
    print(json.dumps({
        "status": report["status"], "planned": len(all_requests), "eligible": len(requests),
        "completed": report.get("completed_count", 0), "failed": report.get("failed_count", 0),
        "document_cleanup": report["document_cleanup"], "report": str(report_path),
    }, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "COMPLETED" else 2


def main():
    """Run the manifest-driven STEP-to-native-PAR import batch.

    CLI options: --limit bounds the eligible batch, repeated --key selects exact
    document keys, and --dry-run writes a plan without entering the import loop.
    Inputs include active_run.json, manifest/inventory source hashes, verified STEP
    export and color reports, optional scaled-variant evidence, and the bridge.

    Normal execution may start the pipeline-owned bridge, bind dialogs to its reported
    Application.ProcessID, import eligible STEP files, save PAR outputs, and close/
    reopen each output for read-only topology verification. It writes the native import
    report and progress log. Verified prior outputs are reused only when both native
    and STEP hashes match; unchanged failures stay quarantined.

    Returns 0 for a fully verified batch or planned dry-run, and 2 when the report
    remains incomplete. Configuration, source-contract, bridge, and workflow errors
    propagate to the script entry point after a bounded fatal message.
    """
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--limit',type=int,default=0,help='Maximum number of planned STEP imports to process; 0 processes the full plan.')
    ap.add_argument('--key',action='append',default=[],help='Limit the import to a manifest document key; repeat to select multiple keys.')
    ap.add_argument('--dry-run',action='store_true',help='Write a non-mutating import plan without opening or changing Solid Edge documents.')
    args=ap.parse_args()
    sys.path.insert(0,str(MCP_ROOT))
    import inventaur_bridge_client as bridge
    importer_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    if manifest.get('source_sha256') != json.loads((REPORTS/'rhino_active_inventory.json').read_text(encoding='utf-8-sig')).get('source_sha256'): raise RuntimeError('manifest/inventory source hash mismatch')
    step_export=json.loads(EXPORT_REPORT.read_text(encoding='utf-8-sig'))
    steps_dir=STEP_ROOT
    step_results_by_stem = {
        Path(x.get('step_path') or '').stem.casefold(): x
        for x in step_export.get('results', [])
        if x.get('step_path')
    }

    # Native fallback assets are tied to one exact Rhino source hash and definition/object identity.
    # A fallback is eligible only after the current inventory proves the same source geometry.
    inventory_data=json.loads((REPORTS/'rhino_active_inventory.json').read_text(encoding='utf-8-sig'))
    source_snapshot=Path(CONFIG.get('source_3dm',''))
    source_snapshot_sha=hashlib.sha256(source_snapshot.read_bytes()).hexdigest() if source_snapshot.is_file() else None
    # Resolve the fallback store from the run package first, then from the
    # canonical CAD source tree. A copied run snapshot lives under Pipeline/Scripts,
    # so relying only on __file__.parents[1] loses access to source-bound assets.
    fallback_candidates = [
        Path(CONFIG.get('fallback_geometry_dir', str(Path(__file__).resolve().parents[1] / 'FallbackGeometry'))) / 'native_fallbacks.json',
    ]
    fallback_manifest_path = next((candidate for candidate in fallback_candidates if candidate.is_file()), fallback_candidates[0])
    native_fallbacks={}
    if fallback_manifest_path.is_file():
        fallback_manifest=json.loads(fallback_manifest_path.read_text(encoding='utf-8-sig'))
        inventory_defs={str(x.get('definition_guid','')).casefold():x for x in inventory_data.get('definitions',[])}
        manifest_defs={str(x.get('rhino_definition_guid_provenance','')).casefold():x for x in manifest.get('definition_documents',[])}
        for fallback in fallback_manifest.get('fallbacks',[]):
            asset=fallback_manifest_path.parent/str(fallback.get('asset_file',''))
            source_sha=fallback.get('source_3dm_sha256')
            key=str(fallback.get('document_key','')).casefold()
            guid=str(fallback.get('source_definition_guid','')).casefold()
            object_guid=str(fallback.get('source_object_guid','')).casefold()
            inv=inventory_defs.get(guid,{})
            mdoc=manifest_defs.get(guid,{})
            breps=inv.get('direct_breps',[])
            source_brep=next((x for x in breps if str(x.get('object_guid','')).casefold()==object_guid),None)
            expected=fallback.get('expected',{})
            source_box=(source_brep or {}).get('bbox_mm')
            source_box_flat=(list(source_box[0])+list(source_box[1])) if source_box and len(source_box)==2 else None
            expected_box=expected.get('bbox_mm')
            if source_sha!=source_snapshot_sha or not asset.is_file():
                continue
            # Bind the fallback not only to the original user-selected 3DM but
            # also to the exact processed/colorized inventory consumed by this run.
            processed_sha = fallback.get('processed_inventory_sha256')
            if processed_sha and processed_sha != inventory_data.get('source_sha256'):
                continue
            if hashlib.sha256(asset.read_bytes()).hexdigest()!=fallback.get('asset_sha256'):
                continue
            if not mdoc or str(mdoc.get('document_key','')).casefold()!=key:
                continue
            if not source_brep or source_box_flat is None or not expected_box:
                continue
            if int(source_brep.get('faces') or 0)!=int(expected.get('face_count') or -1):
                continue
            if bool(source_brep.get('is_solid'))!=bool(expected.get('is_solid')):
                continue
            if max(abs(float(a)-float(b)) for a,b in zip(source_box_flat,expected_box))>0.001:
                continue
            step_record={
                'step_path':str(asset),
                'readback_brep_body_count':int(expected.get('body_count') or 1),
                'readback_brep_face_count':int(expected.get('face_count') or 0),
                'readback_solid_count':int(expected.get('solid_count') or 0),
                'readback_bbox_mm':expected_box,
                'readback_volume_mm3':float(expected.get('volume_m3') or 0.0)*1e9,
                'body_audits':[{'final_solid':bool(expected.get('is_solid')),'final_faces':int(expected.get('face_count') or 0),'source_bbox_mm':expected_box,'export_bbox_mm':expected_box}],
            }
            native_fallbacks[key]={**fallback,'asset_path':asset,'step_record':step_record,'source_inventory_brep':source_brep}
    expected_faces=load_expected_faces()
    requests=[]
    for x in manifest.get('definition_documents',[]):
        if x.get('document_type')=='PAR':
            requests.append({'key':x['document_key'],'name':x['rhino_name'],'relative':x['relative_output_path'],'step_stem':Path(x['relative_output_path']).stem,'kind':'LEAF_PART'})
        if x.get('local_geometry_companion_par'):
            rel=x['local_geometry_companion_par']
            requests.append({'key':x['document_key']+'::LOCAL_GEOMETRY','name':x['rhino_name']+' [local geometry]','relative':rel,'step_stem':Path(rel).stem,'kind':'ASSEMBLY_LOCAL_GEOMETRY'})
    requests.sort(key=lambda x:(x['relative'].casefold(),x['key'].casefold()))
    all_requests=list(requests)
    # Explicit baked-scale variants are generated only for occurrences whose
    # Rhino transform cannot be represented by the verified Solid Edge matrix API.
    variants_file=REPORTS/'scaled_occurrence_variants.json'
    scaled_variants=json.loads(variants_file.read_text(encoding='utf-8-sig')).get('variants',[]) if variants_file.exists() else []
    for variant in scaled_variants:
        stem=Path(variant['step']).stem.casefold()
        variant_report_file=REPORTS/('scaled_occurrence_variant_'+str(variant.get('instance_guid','')).replace('-','')[:8]+'.json')
        variant_data=json.loads(variant_report_file.read_text(encoding='utf-8-sig')) if variant_report_file.is_file() else {}
        source_record=variant_data.get('result',variant_data)
        step_results_by_stem.setdefault(stem,{
            'step_path':str(steps_dir/Path(variant['step']).name),
            'readback_brep_body_count':source_record.get('readback_brep_body_count'),
            'readback_brep_face_count':source_record.get('readback_brep_face_count'),
            'readback_solid_count':source_record.get('readback_solid_count'),
            'readback_volume_mm3':source_record.get('readback_volume_mm3'),
            'readback_bbox_mm':source_record.get('readback_bbox_mm'),
            'body_audits':source_record.get('body_audits',[]),
        })
    all_requests.extend([{'key':v['key'],'name':v.get('name') or v.get('definition_name') or v['key'],'relative':v['relative'],'step_stem':Path(v['step']).stem,'kind':'SCALED_OCCURRENCE_VARIANT'} for v in scaled_variants])

    # A STEP file written from this source definition is eligible for native import.
    # Rhino readback topology is diagnostic only; Solid Edge save/reopen is the practical gate.
    exported_step_paths=set()
    failed_step_keys={str(x.get("key"," ")).casefold() for x in step_export.get("failures",[])}
    for exported in step_export.get("results",[]):
        relative=str(exported.get("native_relative_path") or "").replace("\\","/").casefold()
        path=Path(exported.get("step_path") or "")
        digest=exported.get("step_sha256")
        if relative and path.is_file() and path.stat().st_size>100 and digest and hashlib.sha256(path.read_bytes()).hexdigest()==digest:
            exported_step_paths.add(relative)
    for variant in scaled_variants:
        variant_report_file=REPORTS/("scaled_occurrence_variant_"+str(variant.get("instance_guid"," ")).replace("-","")[:8]+".json")
        variant_report=json.loads(variant_report_file.read_text(encoding="utf-8-sig")) if variant_report_file.is_file() else {}
        variant_step=STEP_ROOT/Path(variant["step"]).name
        if variant_step.is_file() and variant_step.stat().st_size>100:
            exported_step_paths.add(variant["relative"].replace("\\","/").casefold())
    export_blocked=[]
    for request in all_requests:
        failed_by_key=str(request.get("key","")).casefold() in failed_step_keys
        relative=request["relative"].replace("\\","/").casefold()
        missing=relative not in exported_step_paths
        if failed_by_key or missing:
            blocked=dict(request); blocked["blocked_reason"]="STEP_EXPORT_FAILED" if failed_by_key else "STEP_FILE_MISSING"
            export_blocked.append(blocked)
    # Compare stable request keys, not full dictionaries: each blocked row also
    # carries diagnostic metadata, so dictionary equality would fail to exclude it.
    blocked_keys={str(x.get('key','')).casefold() for x in export_blocked}
    requests=[x for x in all_requests if str(x.get('key','')).casefold() not in blocked_keys]

    all_export_blocked = list(export_blocked)
    if args.key:
        wanted={x.casefold() for x in args.key}
        known={x['key'].casefold() for x in all_requests}
        absent=wanted-known
        if absent:raise ValueError('unknown document keys: '+','.join(sorted(absent)))
        requests=[x for x in requests if x['key'].casefold() in wanted]
        export_blocked=[x for x in export_blocked if x['key'].casefold() in wanted]
    if args.limit>0: requests=requests[:args.limit]
    parts_dir=PARTS_ROOT;steps_dir=STEP_ROOT;parts_dir.mkdir(parents=True,exist_ok=True)
    unmatched_part_candidates=quarantine_unmatched_part_candidates(parts_dir,[x.get('relative','') for x in all_requests],LOGS)
    report_path=REPORTS/'native_part_import_e2e.json';log_path=LOGS/'native_part_import.log';LOGS.mkdir(parents=True,exist_ok=True);REPORTS.mkdir(parents=True,exist_ok=True)
    selected_keys={x['key'] for x in requests}
    request_by_key={x['key']:x for x in requests}
    prior_results={}
    prior_failures={}
    if report_path.exists():
        try:
            previous=json.loads(report_path.read_text(encoding='utf-8'))
            if previous.get('source_sha256')==manifest['source_sha256']:
                previous_code=previous.get('importer_script_sha256')
                same_code=(previous_code==importer_script_sha256)
                all_request_by_key={x['key']:x for x in all_requests}
                previous_results=previous.get('results',[])
                previous_failures=previous.get('failures',[])
                for old in previous_results:
                    key=str(old.get('document_key') or '')
                    target_path=Path(old.get('output',''))
                    expected_hash=old.get('native_sha256')
                    request=all_request_by_key.get(key)
                    fallback=native_fallbacks.get(key.casefold())
                    current_step=(steps_dir/(request['step_stem']+'.stp')) if request and not fallback else None
                    current_step_hash=(fallback.get('asset_sha256') if fallback else
                        (hashlib.sha256(current_step.read_bytes()).hexdigest() if current_step and current_step.is_file() else None))
                    old_step_hash=old.get('step_sha256')
                    file_hash=(hashlib.sha256(target_path.read_bytes()).hexdigest()
                               if target_path.is_file() else None)
                    if (key and request and expected_hash and file_hash==expected_hash and
                            old_step_hash and current_step_hash==old_step_hash):
                        # Selected keys are reopened and revalidated below when code
                        # changed. Unselected keys remain carried forward in a subset
                        # run, bound to the unchanged STEP/PAR hashes.
                        if key not in selected_keys or same_code:
                            prior_results[key]=dict(old)
                for old in previous_failures:
                    key=str(old.get('document_key') or '')
                    request=all_request_by_key.get(key)
                    fallback=native_fallbacks.get(key.casefold())
                    current_step=(steps_dir/(request['step_stem']+'.stp')) if request and not fallback else None
                    current_step_hash=(fallback.get('asset_sha256') if fallback else
                        (hashlib.sha256(current_step.read_bytes()).hexdigest() if current_step and current_step.is_file() else None))
                    if key and request and key not in selected_keys and old.get('step_sha256') and current_step_hash==old.get('step_sha256'):
                        prior_failures[key]=dict(old)
        except Exception as exc:
            # Never silently destroy a prior checkpoint because it is malformed.
            raise RuntimeError(f"Could not reconcile existing native import checkpoint {report_path}: {exc}") from exc
    report={
        'schema_version':1,'status':'RUNNING','started_at':datetime.now().astimezone().isoformat(),
        'source_sha256':manifest['source_sha256'],'identity_policy':manifest['identity_policy'],
        'importer_script_sha256':importer_script_sha256,'planned_count':len(all_requests),
        'eligible_native_import_count':len(all_requests)-len(all_export_blocked),'batch_count':len(requests),
        'export_blocked':all_export_blocked,'unmatched_part_candidates':unmatched_part_candidates,
        'Atomically write the import report so an interrupted run cannot leave truncated JSON.'
        'results':sorted(prior_results.values(),key=lambda x:x.get('document_key','')),
        'failures':sorted(prior_failures.values(),key=lambda x:x.get('document_key','')),
        'bridge':bridge.status()
    }
    def save():
        """Atomically persist the import report so interruptions cannot leave truncated JSON."""
        tmp=report_path.with_suffix(report_path.suffix+'.tmp')
        tmp.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        os.replace(tmp,report_path)
    if args.dry_run:
        plan_path=REPORTS/'native_part_import_plan.json'
        plan={
            'status':'PLANNED','created_at':datetime.now().astimezone().isoformat(),
            'source_sha256':manifest['source_sha256'],'importer_script_sha256':importer_script_sha256,
            'planned_count':len(all_requests),'eligible_count':len(requests),
            'export_blocked':export_blocked,'requests':requests,
        }
        tmp=plan_path.with_suffix(plan_path.suffix+'.tmp')
        tmp.write_text(json.dumps(plan,indent=2,ensure_ascii=False),encoding='utf-8')
        os.replace(tmp,plan_path)
        print(json.dumps({'status':'PLANNED','count':len(requests),'export_blocked':len(export_blocked),'plan':str(plan_path),'result_report_unchanged':str(report_path)},ensure_ascii=False));return 0
    save()
    # The current workflow backend uses only the pipeline-owned Solid Edge MCP
    # bridge; it does not discover the application through the Windows ROT.
    return run_bridge_tools_import_backend(
        bridge=bridge, report=report, report_path=report_path, log_path=log_path,
        requests=requests, all_requests=all_requests, prior_results=prior_results,
        prior_failures=prior_failures, manifest=manifest, export_blocked=export_blocked,
        parts_dir=parts_dir, steps_dir=steps_dir, step_results_by_stem=step_results_by_stem,
        native_fallbacks=native_fallbacks,
    )
    # Legacy COM/ROT backend retained below as a historical reference; it is unreachable.
    # The CAD workflow owns its isolated Solid Edge bridge. Start it from the
    'Return true only when the bridge state is a valid healthy response.'
    # deterministic script when absent; never attach to or commandeer the user's
    # interactive Edge.exe session.
    def bridge_is_healthy(state):
        # Bridge status schema differs between the legacy daemon endpoint and
        # the current service endpoint. bridge_running is authoritative when
        # present; otherwise a writable service with a tool set is healthy.
        """Return true only when the bridge state is a well-formed healthy response."""
        if not isinstance(state,dict) or not state.get('ok'):
            return False
        if state.get('readonly') is True:
            return False
        if 'bridge_running' in state and state.get('bridge_running') is False:
            return False
        return bool(state.get('service') or state.get('bridge_running') or state.get('tool_count'))

    if not bridge_is_healthy(report['bridge']):
        # Startup can be asynchronous: the launcher may return while the local
        # daemon is still binding its port. Poll the actual health state rather
        # than treating the launch response itself as proof of readiness.
        bridge_starts=[]
        health=None
        for attempt in range(1,6):
            start_result=bridge.start()
            bridge_starts.append({'attempt':attempt,'result':start_result})
            time.sleep(1.0)
            health=bridge.status()
            if bridge_is_healthy(health):
                break
        report['bridge_start']=bridge_starts
        report['bridge']=health or bridge.status()
        if not bridge_is_healthy(report['bridge']):
            report['status']='FAILED'
            report['error']='Solid Edge bridge did not become healthy after startup: '+json.dumps({'starts':bridge_starts,'health':report['bridge']},ensure_ascii=False)
            save()
            raise RuntimeError(report['error'])
        save()
    if not bridge_is_healthy(report['bridge']):
        report['status']='FAILED';report['error']='Solid Edge bridge is not healthy after startup: '+json.dumps(report['bridge'],ensure_ascii=False)
        save()
        raise RuntimeError(report['error'])
    app,owned_process_id=ensure_owned_application(bridge,report)
    owned_document=active_doc(bridge)
    report['solid_edge_application_pid']=owned_process_id
    report['solid_edge_initial_document']=owned_document
    report['solid_edge_documents_count_at_start']=int(app.Documents.Count)
    save()
    with log_path.open('a',encoding='utf-8') as log:
        baseline_document_identities = {
            document_identity(app.Documents.Item(index))
            for index in range(1, int(app.Documents.Count) + 1)
        }
        report["solid_edge_documents_before_batch"] = int(app.Documents.Count)
        report["preexisting_document_identities"] = sorted([list(x) for x in baseline_document_identities])
        for i,req in enumerate(requests,1):
            step=steps_dir/(req['step_stem']+'.stp');target=parts_dir/Path(req['relative']).name
            staging=target.with_name(target.stem+'.__staging__.par')
            imported_doc=None
            open_info=None
            row={'index':i,'document_key':req['key'],'name':req['name'],'kind':req['kind'],'step':str(step),'output':str(target),'expected_faces':expected_faces.get(req['step_stem'].casefold(),0)}
            # Reuse a prior native result only if both source STEP and saved PAR
            # hashes still match their last verified values. Unchanged failures
            # remain quarantined until their source STEP hash changes.
            if req['key'] in prior_results:
                reused=dict(prior_results[req['key']]);reused.update({'status':'reused_verified_with_warnings' if reused.get('validation',{}).get('warnings') else 'reused_verified','resume_reused':True,'index':i})
                log.write(f"REUSE {i}/{len(requests)} {req['key']} native_sha256={reused.get('native_sha256')}\n");log.flush()
                report['results']=sorted(prior_results.values(),key=lambda x:x.get('document_key',''))
                report['failures']=sorted(prior_failures.values(),key=lambda x:x.get('document_key',''))
                report['completed_count']=len(prior_results);report['failed_count']=len(prior_failures)
                report['current_index']=i;report['updated_at']=datetime.now().astimezone().isoformat();save()
                print(json.dumps({'index':i,'batch_total':len(requests),'mission_total':len(all_requests),'key':req['key'],'status':'reused_verified','completed':report['completed_count'],'failed':report['failed_count']},ensure_ascii=False),flush=True)
                continue
            if req['key'] in prior_failures:
                failed=dict(prior_failures[req['key']]);failed['status']='quarantined_unchanged';failed['resume_reused']=True
                log.write(f"QUARANTINE {i}/{len(requests)} {req['key']} unchanged_step_hash\n");log.flush()
                report['results']=sorted(prior_results.values(),key=lambda x:x.get('document_key',''))
                report['failures']=sorted(prior_failures.values(),key=lambda x:x.get('document_key',''))
                report['completed_count']=len(prior_results);report['failed_count']=len(prior_failures)
                report['current_index']=i;report['updated_at']=datetime.now().astimezone().isoformat();save()
                print(json.dumps({'index':i,'batch_total':len(requests),'mission_total':len(all_requests),'key':req['key'],'status':'quarantined_unchanged','completed':report['completed_count'],'failed':report['failed_count']},ensure_ascii=False),flush=True)
                continue
            try:
                fallback=native_fallbacks.get(str(req['key']).casefold())
                if fallback:
                    fallback_asset=Path(fallback['asset_path'])
                    step_hash=fallback['asset_sha256']
                    step_record=fallback['step_record']
                    row['geometry_input_kind']='VERIFIED_NATIVE_FALLBACK_PAR'
                    row['native_fallback']={k:fallback.get(k) for k in ('asset_name','asset_file','asset_sha256','source_3dm_sha256','source_definition_guid','source_object_guid','provenance','expected','measured')}
                else:
                    if not step.is_file() or step.stat().st_size<100:
                        raise FileNotFoundError('canonical STEP missing/too small: '+str(step))
                    step_hash=hashlib.sha256(step.read_bytes()).hexdigest()
                    step_record=step_results_by_stem.get(req['step_stem'].casefold()) or {'step_path':str(step)}
                    row['geometry_input_kind']='VERIFIED_STEP'
                row['step_sha256']=step_hash

                validation_result=None
                reused=False
                if target.exists():
                    target_preexisting = document_is_open_in_application(app, target)
                    try:
                        verified=verify_native(bridge,target,step_record)
                        validation_result=verified.get('validation',{})
                        reused=True
                        row.update({
                            'status':'reused_verified_with_warnings' if validation_result.get('warnings') else 'reused_verified',
                            'native_bytes':target.stat().st_size,
                            'native_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                            'verification_document_close':close_run_verification_document(
                                bridge,target,was_preexisting=target_preexisting,
                                label='close reused native PAR after read-only verification'
                            ),
                            **verified
                        })
                    except Exception as existing_error:
                        row['existing_native_rejected']=str(existing_error)[:1600]
                        if target_preexisting:
                            # Do not close, replace, or overwrite a document that was
                            # already open before the batch. Leave a clear failure row.
                            raise RuntimeError(
                                "Existing native target was already open before verification and failed "
                                "current-policy checks; refusing to close or replace it: " + str(existing_error)
                            ) from existing_error
                        try:
                            current=active_doc(bridge)
                            if _normalized_full_path(current.get('fullName') or '') == _normalized_full_path(target):
                                bridge.write_tool('se_close_document',{'target':str(target),'confirm':True})
                        except Exception:
                            pass
                        reused=False

                if not reused:
                    if staging.exists():
                        # A stale staging file is removed only after proving it is not open in the owned app.
                        open_staging=[]
                        for di in range(1,int(app.Documents.Count)+1):
                            dd=app.Documents.Item(di)
                            if str(getattr(dd,'FullName','')).casefold()==str(staging).casefold():
                                open_staging.append(dd)
                        if open_staging:
                            raise RuntimeError('staging PAR is already open in the owned Solid Edge session: '+str(staging))
                        staging.unlink()

                    if fallback:
                        # This source-bound native fallback is a previously reopened and verified PAR.
                        # Copy to the run-local staging path, reopen, measure and validate before promotion.
                        shutil.copy2(fallback_asset,staging)
                        staged_verification=verify_native(bridge,staging,step_record)
                        row['staged_reopen_verification']=staged_verification
                        check_result(
                            bridge.write_tool('se_close_document',{'target':str(staging),'confirm':True}),
                            'close read-only verified native fallback PAR'
                        )
                        stage_hash=hashlib.sha256(staging.read_bytes()).hexdigest()
                        if stage_hash!=fallback['asset_sha256']:
                            raise RuntimeError('native fallback PAR hash changed during staging')
                        promotion=promote_verified_staging(bridge,app,owned_process_id,staging,target)
                        final_hash=promotion['final_hash']
                        validation_result=staged_verification.get('validation',{})
                        row.update({
                            'status':'imported_verified_with_warnings' if validation_result.get('warnings') else 'imported_verified',
                            'native_bytes':target.stat().st_size,
                            'native_sha256':final_hash,
                            'topology':staged_verification.get('topology'),
                            'validation':validation_result,
                            'promotion':{**promotion,'source':'native_fallback_asset'}
                        })
                    else:
                        imported_doc,open_info=open_step_once_with_template(
                            bridge,app,owned_process_id,step
                        )
                        row['open_response']=open_info
                        live=active_doc(bridge)
                        if live.get('typeShort')!='PartDocument' or int(live.get('_application_process_id') or 0)!=owned_process_id:
                            raise RuntimeError('OpenWithTemplate did not activate a PartDocument in the owned Solid Edge process: '+json.dumps(live,ensure_ascii=False))
                        metrics=body_metrics(bridge)
                        validation=validate_native_against_step(metrics,step_record)
                        row['imported_topology']=metrics
                        row['validation']=validation
                        if not validation.get('passed'):
                            raise RuntimeError('translated native geometry failed STEP invariants: '+json.dumps(validation,ensure_ascii=False)[:2600])

                        selection=check_result(bridge.read_tool('se_get_selection',{}),'resolve imported PartDocument for SaveAs')
                        if not selection.get('items'):
                            raise RuntimeError('active imported PartDocument handle missing before SaveAs')
                        doc_id=selection['items'][0]['id']
                        saved=check_result(
                            bridge.write_tool('se_invoke_member',{'objectId':doc_id,'member':'SaveAs','args':[str(staging)]}),
                            'SaveAs staged native PAR'
                        )
                        check_result(
                            bridge.write_tool('se_invoke_member',{'objectId':doc_id,'member':'Save','args':[]}),
                            'save staged native PAR'
                        )
                        if not staging.is_file() or staging.stat().st_size<1000:
                            raise RuntimeError('staged PAR missing or implausibly small after SaveAs')
                        row['save_as']=saved
                        row['staging_path']=str(staging)
                        row['staging_bytes']=staging.stat().st_size
                        if bool(getattr(imported_doc,'Dirty',False)):
                            raise RuntimeError('imported document remains dirty after Save; refusing to close or promote')
                        row['imported_document_close'] = close_owned_import_document(
                            app, owned_process_id, imported_doc,
                            open_info.get('preexisting_document_identities', [])
                        )
                        imported_doc = None
                        if int(dialogs(owned_process_id).get('modalCount') or 0):
                            raise RuntimeError('unexpected modal appeared after closing saved staged PAR')

                        staged_verification=verify_native(bridge,staging,step_record)
                        row['staged_reopen_verification']=staged_verification
                        check_result(
                            bridge.write_tool('se_close_document',{'target':str(staging),'confirm':True}),
                            'close read-only reopened staged native PAR'
                        )
                        promotion=promote_verified_staging(bridge,app,owned_process_id,staging,target)
                        stage_hash=promotion['staging_hash']
                        final_hash=promotion['final_hash']
                        validation_result=staged_verification.get('validation',{})
                        row.update({
                            'status':'imported_verified_with_warnings' if validation_result.get('warnings') else 'imported_verified',
                            'native_bytes':target.stat().st_size,
                            'native_sha256':final_hash,
                            'promotion':promotion,
                            'topology':staged_verification.get('topology'),
                            'validation':validation_result
                        })

                log.write(f"OK {i}/{len(requests)} {req['key']} faces={row.get('topology',{}).get('faces',row.get('imported_topology',{}).get('faces'))} status={row['status']} output={target}\n")
                log.flush()
            except Exception as e:
                # Every newly opened STEP PartDocument is ours, even when its
                # geometry fails acceptance before SaveAs. Close by exact COM
                # identity and owned PID; never enumerate-and-close arbitrary
                # PartN documents or a pre-existing user document.
                if imported_doc is not None and open_info and open_info.get('created_by_this_open_call'):
                    try:
                        row['failed_import_document_cleanup'] = close_owned_import_document(
                            app, owned_process_id, imported_doc,
                            open_info.get('preexisting_document_identities', [])
                        )
                    except Exception as cleanup_error:
                        row['failed_import_document_cleanup'] = {
                            'status': 'failed', 'error': f'{type(cleanup_error).__name__}: {cleanup_error}'
                        }
                try:
                    if staging.is_file():
                        row['staging_document_cleanup'] = close_owned_run_document(
                            bridge, app, owned_process_id, staging
                        )
                except Exception as cleanup_error:
                    row['staging_document_cleanup'] = {
                        'status': 'failed', 'error': f'{type(cleanup_error).__name__}: {cleanup_error}'
                    }
                row.update({'status':'failed','error_type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc()})
                log.write(f"FAIL {i}/{len(requests)} {req['key']} {type(e).__name__}: {e}\n");log.flush()
            if row.get('status') in ('imported_verified','reused_verified','imported_verified_with_warnings','reused_verified_with_warnings'):
                prior_results[req['key']]=row
                prior_failures.pop(req['key'],None)
            else:
                prior_results.pop(req['key'],None)
                prior_failures[req['key']]=row
            report['results']=sorted(prior_results.values(),key=lambda x:x.get('document_key',''))
            report['failures']=sorted(prior_failures.values(),key=lambda x:x.get('document_key',''))
            report['completed_count']=len(prior_results)
            report['failed_count']=len(prior_failures)
            report['current_index']=i
            report['updated_at']=datetime.now().astimezone().isoformat()
            save()
            print(json.dumps({'index':i,'batch_total':len(requests),'mission_total':len(all_requests),'key':req['key'],'status':row['status'],'error':row.get('error'),'completed':report['completed_count'],'failed':report['failed_count']},ensure_ascii=False),flush=True)
    remaining_documents = []
    for index in range(1, int(app.Documents.Count) + 1):
        doc_identity = document_identity(app.Documents.Item(index))
        if doc_identity not in baseline_document_identities:
            remaining_documents.append(list(doc_identity))
    report['solid_edge_documents_after_batch'] = int(app.Documents.Count)
    report['document_cleanup'] = {
        'status': 'VERIFIED' if not remaining_documents else 'INCOMPLETE',
        'baseline_document_count': len(baseline_document_identities),
        'final_document_count': int(app.Documents.Count),
        'new_documents_remaining': remaining_documents,
        'preexisting_documents_left_untouched': len(baseline_document_identities),
    }
    report['finished_at']=datetime.now().astimezone().isoformat()
    report['status']='COMPLETED' if (len(prior_results)==(len(all_requests)-len(export_blocked)) and
        not prior_failures and not remaining_documents) else 'INCOMPLETE'
    report['geometry_export_exceptions_are_blocked']=bool(export_blocked)
    save()
    print(json.dumps({'status':report['status'],'planned':len(all_requests),'batch_processed':len(requests),'completed':report.get('completed_count',0),'failed':report.get('failed_count',0),'report':str(report_path)},ensure_ascii=False),flush=True)
    return 0 if report['status']=='COMPLETED' else 2

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as e:
        print('FATAL '+type(e).__name__+': '+str(e),file=sys.stderr);raise
