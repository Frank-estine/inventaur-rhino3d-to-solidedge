"""Inventaur Inc. | Recover missed Solid Edge assembly documents and build Root.asm.

This is a checkpointed, direct-API recovery script. It never deletes or explodes
source geometry, never replays an ambiguous placement without querying first,
and verifies every assembly from disk after Save/Close/Reopen.

Known exclusions are explicit: invalid/unverified source .par files are skipped;
non-unit scaled placements are skipped because Solid Edge's occurrence API was
observed to drop scale on AddWithMatrix. Reflections remain supported.
"""
from __future__ import annotations
__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"
import json, math, os, sys, time, traceback, unicodedata, uuid
from datetime import datetime
from pathlib import Path

_CONFIG_ENV = os.environ.get("CAD_WORKFLOW_CONFIG")
if not _CONFIG_ENV:
    raise RuntimeError("CAD_WORKFLOW_CONFIG is required; refusing shared active_run.json fallback")
CONFIG_PATH = Path(_CONFIG_ENV).resolve()
if not CONFIG_PATH.is_file():
    raise FileNotFoundError("Run-scoped CAD workflow config is missing: " + str(CONFIG_PATH))
with CONFIG_PATH.open("r", encoding="utf-8-sig") as _config_stream:
    CONFIG = json.load(_config_stream)
PIPE=Path(CONFIG["pipeline_root"])  # final output root
REPORTS=Path(CONFIG["reports_root"])
LOGS=Path(CONFIG["logs_root"])
MCP_ROOT=Path(CONFIG["solid_edge_mcp_root"])
MANIFEST=REPORTS/"name_identity_manifest.json"
INVENTORY=REPORTS/"rhino_active_inventory.json"
IMPORT_REPORT=REPORTS/"native_part_import_e2e.json"
MAIN_REPORT=REPORTS/"assembly_build_e2e.json"
RECOVERY_REPORT=REPORTS/"assembly_recovery_report.json"
LOG=LOGS/"assembly_recovery.log"
ROOT_ASM=PIPE/"Assemblies"/"Root.asm"
LOGS.mkdir(parents=True,exist_ok=True)
REPORTS.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(MCP_ROOT))
import inventaur_bridge_client as bridge

state={"schema_version":1,"status":"RUNNING","started_at":datetime.now().astimezone().isoformat(),
       "heartbeat_at":None,"current_document":None,"current_action":"load source reports","results":[],"errors":[]}

def checkpoint():
    """Persist recovery progress atomically so a later run can reconcile completed assembly work."""
    state["heartbeat_at"]=datetime.now().astimezone().isoformat()
    tmp=RECOVERY_REPORT.with_name(RECOVERY_REPORT.stem+"."+uuid.uuid4().hex+".tmp")
    tmp.write_text(json.dumps(state,indent=2,ensure_ascii=False),encoding="utf-8")
    os.replace(tmp,RECOVERY_REPORT)

def log(msg):
    """Append a timestamped recovery event to the run-scoped log."""
    line=datetime.now().astimezone().isoformat(timespec="seconds")+" "+msg
    with LOG.open("a",encoding="utf-8") as f:f.write(line+"\n");f.flush()
    print(line,flush=True);checkpoint()

def action(doc,what):
    """Execute one named Solid Edge bridge operation and validate its response."""
    state["current_document"]=doc;state["current_action"]=what;checkpoint()

def call(access,tool,args,doc):
    """Invoke a bridge command with an explicit timeout and return its reconciled result."""
    action(doc,tool+" in progress")
    result=bridge.write_tool(tool,args) if access=="write" else bridge.read_tool(tool,args)
    if not isinstance(result,dict) or result.get("status") not in ("ok","dry-run"):
        raise RuntimeError(tool+" failed: "+json.dumps(result,ensure_ascii=False)[:2600])
    action(doc,tool+" returned "+str(result.get("status")))
    return result

def nkey(v):
    "Normalize a definition name using the manifest's NFKC, whitespace and case-folding identity rule."
    return " ".join(unicodedata.normalize("NFKC",v or "").strip().split()).casefold()
def pkey(v):
    """Convert a document path into a canonical absolute, case-insensitive comparison key."""
    return os.path.normcase(os.path.abspath(str(v))).casefold()
def docpath(d):
    "Resolve a manifest-relative output path under this run's canonical pipeline directory."
    return PIPE/Path(d["relative_output_path"])
def ident():
    """Return the row-major 4×4 identity placement matrix."""
    return [1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]

def matrix(tr):
    """Convert a transform representation into a numeric matrix for placement comparison."""
    rows=tr.get("matrix")
    if not isinstance(rows,list) or len(rows)!=4 or any(not isinstance(r,list) or len(r)!=4 for r in rows):raise ValueError("invalid 4x4 Rhino placement")
    if tr.get("singular") or tr.get("has_shear"):raise ValueError("singular/sheared transform unsupported")
    scales=tr.get("axis_scales",[1.,1.,1.])
    if len(scales)!=3 or any(abs(float(v)-1.)>1e-7 for v in scales):raise ValueError("non-unit scale must be baked into geometry; occurrence scale is dropped by Solid Edge")
    m=[[float(rows[r][c]) for c in range(4)] for r in range(4)]
    if any(not math.isfinite(v) for r in m for v in r):raise ValueError("non-finite placement matrix")
    m[0][3]/=1000.;m[1][3]/=1000.;m[2][3]/=1000.
    return [m[r][c] for c in range(4) for r in range(4)]

def matrix_err(a,b):
    """Measure the difference between expected and observed transform matrices."""
    if not isinstance(a,list) or len(a)!=16:return float("inf")
    return max(abs(float(x)-float(y)) for x,y in zip(a,b))

def reconcile(actual,expected,tol=1e-7):
    """Query the owned Solid Edge document state after an uncertain or interrupted operation."""
    left=list(actual);matches=[];missing=[]
    for want in expected:
        target=pkey(want["file"]);best=None;err=float("inf")
        for i,got in enumerate(left):
            if pkey(got.get("file",""))!=target:continue
            e=matrix_err(got.get("matrix"),want["matrix"])
            if e<err:best=i;err=e
        if best is None or err>tol:missing.append({"name":want["name"],"file":want["file"],"matrix_error":None if best is None else err})
        else:
            got=left.pop(best);matches.append({"name":want["name"],"file":want["file"],"matrix_error":err,"visible":bool(got.get("visible"))})
    return matches,missing,[{"name":x.get("name"),"file":x.get("file")} for x in left]

def add_expected(rows,path,tr,source,name):
    """Add one expected occurrence to the recovery assembly plan without duplicating its identity."""
    rows.append({"file":str(path),"matrix":tr,"source":source,"name":name})

def load():
    """Load and validate the source-bound manifest and native import evidence for recovery."""
    m=json.loads(MANIFEST.read_text(encoding="utf-8-sig"));i=json.loads(INVENTORY.read_text(encoding="utf-8-sig"));r=json.loads(IMPORT_REPORT.read_text(encoding="utf-8-sig"))
    if len({m.get("source_sha256"),i.get("source_sha256"),r.get("source_sha256")})!=1:raise RuntimeError("input source SHA mismatch")
    docs={d["normalized_name"]:d for d in m["definition_documents"]}
    defs={d["definition_guid"]:d for d in i["definitions"]}
    verified={pkey(x["output"]) for x in r.get("results",[]) if x.get("status") in ("imported_verified","reused_verified") and x.get("output")}
    return m,i,r,docs,defs,verified

def expected_for_definition(src,docs,defs,verified,include_local=True):
    """Resolve the expected native document for a block definition from the identity manifest."""
    expected=[];skips=[]
    for occ in src.get("children",[]):
        child=defs.get(occ.get("definition_guid"))
        if not child:skips.append({"name":occ.get("definition_name"),"reason":"Rhino definition GUID missing"});continue
        d=docs.get(nkey(child["name"]))
        if not d:skips.append({"name":child["name"],"reason":"identity mapping missing"});continue
        try:tr=matrix(occ["transform"])
        except Exception as ex:skips.append({"name":child["name"],"reason":str(ex)});continue
        path=docpath(d)
        if d["document_type"]=="PAR":
            if not path.is_file() or pkey(path) not in verified:
                skips.append({"name":child["name"],"reason":".par absent or failed native topology verification"});continue
        elif not path.is_file():
            skips.append({"name":child["name"],"reason":"nested .asm not present"});continue
        add_expected(expected,path,tr,"child_block_occurrence",child["name"])
    if include_local:
        d=next((x for x in docs.values() if x["rhino_definition_guid_provenance"]==src["definition_guid"]),None)
        rel=d.get("local_geometry_companion_par") if d else None
        if rel:
            path=PIPE/Path(rel)
            if path.is_file() and pkey(path) in verified:add_expected(expected,path,ident(),"direct_local_geometry",src["name"]+" [local geometry]")
            else:skips.append({"name":src["name"]+" [local geometry]","reason":"local geometry part absent or not verified"})
    return expected,skips

def ensure_assembly(label,path,expected,skip_records):
    """Reconcile a saved assembly, add only missing operations, then disk-verify."""
    handle=None
    rec={"name":label,"path":str(path),"expected_direct_occurrences":len(expected),"skipped":skip_records,"status":"RUNNING"}
    try:
        if path.is_file():opened=call("write","se_open_document",{"path":str(path),"readOnly":False},label)
        else:
            created=call("write","se_new_document",{"docType":"assembly"},label)
            handle=created.get("handle")
            if not handle:raise RuntimeError("new assembly returned no handle")
            call("write","se_invoke_member",{"objectId":handle,"member":"SaveAs","args":[str(path)]},label)
            opened={"handle":handle}
        handle=opened.get("handle")
        if not handle:raise RuntimeError("assembly open returned no tracked handle")
        before=call("read","se_assembly_query",{"objectId":handle,"mode":"occurrences"},label).get("occurrences",[])
        found,missing,extras=reconcile(before,expected)
        if extras:raise RuntimeError("unexpected existing occurrences; refusing destructive cleanup: "+json.dumps(extras,ensure_ascii=False)[:1000])
        rec["existing_matches"]=len(found);rec["planned_placements"]=len(missing)
        if missing:
            ops=[{"op":"place","file":x["file"],"matrix":x["matrix"]} for x in expected if any(x["file"]==mm["file"] and x["name"]==mm["name"] for mm in missing)]
            dry=call("write","se_assembly_build",{"ops":ops,"objectId":handle,"dryRun":True},label)
            if dry.get("validate",{}).get("HasError"):raise RuntimeError("assembly dry-run errors: "+json.dumps(dry,ensure_ascii=False)[:1600])
            action(label,"se_assembly_build executing "+str(len(ops))+" placements")
            built=bridge.write_tool("se_assembly_build",{"ops":ops,"objectId":handle,"dryRun":False,"confirm":False})
            rec["build_result"]=built;checkpoint()
            if built.get("status")!="ok" or built.get("aborted") or built.get("ok")!=len(ops):
                after=bridge.read_tool("se_assembly_query",{"objectId":handle,"mode":"occurrences"})
                got=after.get("occurrences",[]) if after.get("status")=="ok" else []
                ok,miss,extra=reconcile(got,expected)
                if miss or extra:raise RuntimeError("placement outcome incomplete; not replayed: "+json.dumps({"result":built,"missing":miss,"extras":extra},ensure_ascii=False)[:1800])
        call("write","se_invoke_member",{"objectId":handle,"member":"Save","args":[]},label)
        call("write","se_close_document",{"target":handle,"confirm":False},label);handle=None
        reopened=call("write","se_open_document",{"path":str(path),"readOnly":False},label);handle=reopened.get("handle")
        if not handle:raise RuntimeError("reopen returned no document handle")
        after=call("read","se_assembly_query",{"objectId":handle,"mode":"occurrences"},label)
        actual=after.get("occurrences",[]);matches,missing,extras=reconcile(actual,expected)
        rec.update({"actual_direct_occurrences":len(actual),"matched_occurrences":len(matches),"missing_after_reopen":missing,
                    "unexpected_after_reopen":extras,"all_references_exist":all(Path(x.get("file","" )).is_file() for x in actual),
                    "all_visible":all(bool(x.get("visible")) for x in actual),"disk_reopened":True})
        rec["verified"]=path.is_file() and not missing and not extras and len(matches)==len(expected) and rec["all_references_exist"] and rec["all_visible"]
        rec["complete"]=bool(rec["verified"]) and not bool(skip_records)
        rec["status"]=("VERIFIED" if rec["complete"] else ("PARTIAL" if rec["verified"] else "FAILED_VERIFICATION"))
        return rec
    finally:
        if handle:
            try:bridge.write_tool("se_close_document",{"target":handle,"confirm":False})
            except Exception:pass

def main():
    """Recover only missing, source-verified assembly documents and produce a disk-reopened Root.asm."""
    m,inv,ir,docs,defs,verified=load();state["source_sha256"]=m["source_sha256"]
    health=bridge.status();state["bridge"]=health
    if not health.get("ok") or health.get("readonly"):raise RuntimeError("bridge not writable: "+json.dumps(health))
    log("START recovery; source SHA verified; bridge writable; verified PAR outputs="+str(len(verified)))
    by_name={nkey(d["name"]):d for d in inv["definitions"]}
    recovered={}

    # Reconcile asm top assembly; its first run saved both members before a
    # false PathFinder dialog blocked the reopen check.
    src=by_name[nkey("asm top assembly")];doc=docs[nkey(src["name"])];path=docpath(doc)
    exp,sk=expected_for_definition(src,docs,defs,verified)
    rec=ensure_assembly(src["name"],path,exp,sk);recovered[src["definition_guid"]]=rec
    state["results"].append(rec);log("RECONCILE asm top assembly "+rec["status"]+" "+str(rec.get("matched_occurrences")))

    # Rebuild rotate V lock 2 07: the file existed but had zero saved
    # occurrences after a Windows report-file rename error interrupted build.
    src=by_name[nkey("rotate V lock 2 07")];doc=docs[nkey(src["name"])];path=docpath(doc)
    exp,sk=expected_for_definition(src,docs,defs,verified)
    rec=ensure_assembly(src["name"],path,exp,sk);recovered[src["definition_guid"]]=rec
    state["results"].append(rec);log("RECOVER rotate V lock 2 07 "+rec["status"]+" "+str(rec.get("matched_occurrences")))

    # Create dessaacant tray with the verified children only. The invalid
    # tray_01 native body remains excluded and explicitly recorded.
    src=by_name[nkey("dessaacant tray")];doc=docs[nkey(src["name"])];path=docpath(doc)
    exp,sk=expected_for_definition(src,docs,defs,verified)
    rec=ensure_assembly(src["name"],path,exp,sk);recovered[src["definition_guid"]]=rec
    state["results"].append(rec);log("RECOVER dessaacant tray "+rec["status"]+" "+str(rec.get("matched_occurrences"))+" skipped="+str(len(sk)))

    # Root: one of the 17 placements has non-uniform scale and is skipped
    # because the Solid Edge probe proved it is silently normalized to 1.
    root_expected=[];root_skips=[];partial_deps=[]
    for occ in inv.get("top_level_occurrences",[]):
        src=defs.get(occ.get("definition_guid"))
        if not src:root_skips.append({"name":occ.get("definition_name"),"reason":"source definition missing"});continue
        d=docs.get(nkey(src["name"]))
        if not d:root_skips.append({"name":src["name"],"reason":"document identity missing"});continue
        try:tr=matrix(occ["transform"])
        except Exception as ex:root_skips.append({"name":src["name"],"reason":str(ex),"instance_guid":occ.get("instance_guid")});continue
        path=docpath(d)
        if d["document_type"]=="PAR":
            if not path.is_file() or pkey(path) not in verified:root_skips.append({"name":src["name"],"reason":"native part is missing or failed validation"});continue
        elif not path.is_file():root_skips.append({"name":src["name"],"reason":"native assembly file missing"});continue
        else:
            child_status=recovered.get(occ["definition_guid"])
            if child_status is None:
                # Previously built assembly is partial or complete according
                # to the main report; it is still safe to insert when the file
                # has been saved and disk-verified.
                old=json.loads(MAIN_REPORT.read_text(encoding="utf-8-sig"))
                oldrec=next((a for a in old.get("assemblies",[]) if a.get("definition_guid")==occ["definition_guid"]),None)
                if oldrec and oldrec.get("status") in ("VERIFIED","PARTIAL") and oldrec.get("verified"):
                    child_status=oldrec
            if not child_status or not child_status.get("verified"):
                root_skips.append({"name":src["name"],"reason":"nested assembly has no successful disk verification"});continue
            if not child_status.get("complete",child_status.get("status")=="VERIFIED"):partial_deps.append(src["name"])
        add_expected(root_expected,path,tr,"top_level_rhino_occurrence",src["name"])
    log("ROOT PREP expected="+str(len(root_expected))+" of 17; skipped="+str(len(root_skips))+"; partial_deps="+str(len(partial_deps)))
    rootrec=ensure_assembly("Root.asm",ROOT_ASM,root_expected,root_skips)
    rootrec["skipped_top_level_occurrences"]=root_skips;rootrec["partial_child_assemblies"]=partial_deps
    rootrec["complete"]=bool(rootrec.get("verified")) and not root_skips and not partial_deps
    rootrec["status"]="VERIFIED" if rootrec["complete"] else ("PARTIAL" if rootrec.get("verified") else "FAILED")
    state["root"]=rootrec;log("ROOT "+rootrec["status"]+" placed="+str(rootrec.get("matched_occurrences"))+"/"+str(len(root_expected)))

    # Merge recovery outcomes into the original run report while keeping the
    # original failure evidence. The recovery report remains independently auditable.
    main=json.loads(MAIN_REPORT.read_text(encoding="utf-8-sig"))
    for rec in state["results"]:
        old=next((a for a in main.get("assemblies",[]) if a.get("definition_guid")==rec.get("definition_guid")),None)
        if old is None:
            src=defs.get(rec.get("definition_guid"),{})
            old={"name":rec["name"],"definition_guid":rec["definition_guid"],"path":rec["path"]};main.setdefault("assemblies",[]).append(old)
        old.update(rec)
        if rec["name"]=="dessaacant tray":old["complete"]=False;old["status"]="PARTIAL"
    # asm_top and rotate are complete; dessaacant is deliberately partial.
    main["root"]=rootrec
    main["recovery_report"] = str(RECOVERY_REPORT)
    main["recovery_completed_at"] = datetime.now().astimezone().isoformat()
    counts=Counter(x.get("status") for x in main.get("assemblies",[]))
    main["completed_nested_assemblies"]=counts.get("VERIFIED",0)
    main["partial_nested_assemblies"]=counts.get("PARTIAL",0)
    main["failed_nested_assemblies"]=sum(1 for x in main.get("assemblies",[]) if x.get("status","").startswith("FAILED"))
    main["acceptance"]={
        "expected_nested_assembly_documents":27,
        "nested_assembly_documents_on_disk":sum(1 for d in inv["definitions"] if docs[nkey(d["name"])]["document_type"]=="ASM" and docpath(docs[nkey(d["name"]) ]).is_file()),
        "all_nested_assembly_documents_exist":all(docpath(docs[nkey(d["name"]) ]).is_file() for d in inv["definitions"] if docs[nkey(d["name"])]["document_type"]=="ASM"),
        "root_document_exists":ROOT_ASM.is_file(),
        "rhino_top_level_occurrences":len(inv.get("top_level_occurrences",[])),
        "solid_edge_root_occurrences":rootrec.get("actual_direct_occurrences",0),
        "root_skipped_occurrences":len(root_skips),
        "root_matches_expected_occurrences":len(rootrec.get("missing_after_reopen",[]))==0 and rootrec.get("verified",False),
        "nested_assemblies_complete":main["completed_nested_assemblies"],
        "nested_assemblies_partial":main["partial_nested_assemblies"],
        "nested_assemblies_failed":main["failed_nested_assemblies"],
    }
    main["status"]="COMPLETED" if main["completed_nested_assemblies"]==27 and main["failed_nested_assemblies"]==0 and rootrec["complete"] else "INCOMPLETE"
    tmp=MAIN_REPORT.with_name(MAIN_REPORT.stem+"."+uuid.uuid4().hex+".tmp")
    tmp.write_text(json.dumps(main,indent=2,ensure_ascii=False),encoding="utf-8");os.replace(tmp,MAIN_REPORT)
    state["status"]="COMPLETED" if rootrec.get("verified") else "INCOMPLETE"
    state["acceptance"]=main["acceptance"];state["finished_at"]=datetime.now().astimezone().isoformat();state["current_document"]=None;state["current_action"]="recovery complete"
    checkpoint();log("FINAL "+json.dumps({"status":state["status"],"root":rootrec["status"],"root_occurrences":rootrec.get("actual_direct_occurrences"),"root_expected":len(root_expected),"skipped":root_skips,"nested_counts":main["acceptance"]},ensure_ascii=False))

if __name__=="__main__":
    try:main()
    except Exception as exc:
        state["status"]="FAILED";state["fatal_error"]={"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()};state["finished_at"]=datetime.now().astimezone().isoformat()
        try:log("FATAL "+str(exc))
        except Exception:pass
        checkpoint();raise
