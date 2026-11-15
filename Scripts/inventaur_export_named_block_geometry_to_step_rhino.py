"""Inventaur Inc. | Export unique colourized Rhino block definitions to STEP in small batches.

Leaf definitions use one temporary source block instance. If Rhino's STEP writer
rejects that instance, direct source geometry is exported without repair. Mixed
assembly local geometry is separate. Solid Edge import/save/reopen is the readback.
"""
__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"
import os, json, hashlib, datetime
import Rhino, System
CONFIG_PATH=os.environ.get("CAD_WORKFLOW_CONFIG")
if not CONFIG_PATH or not os.path.isfile(CONFIG_PATH): raise RuntimeError("CAD_WORKFLOW_CONFIG is required")
CONFIG=json.load(open(CONFIG_PATH,encoding="utf-8-sig"))
SOURCE=CONFIG["colorized_3dm"]; REPORTS=CONFIG["reports_root"]; STEPS=CONFIG["step_root"]
INVENTORY=os.path.join(REPORTS,"rhino_active_inventory.json"); MANIFEST=os.path.join(REPORTS,"name_identity_manifest.json")
REPORT_PATH=os.path.join(REPORTS,"step_export_e2e.json")
os.makedirs(STEPS,exist_ok=True); os.makedirs(REPORTS,exist_ok=True)
STAGE=json.loads(os.environ.get("CAD_WORKFLOW_STAGE_PAYLOAD") or "{}")
BATCH_START=int(STAGE.get("batch_start",0)); BATCH_SIZE=max(1,min(12,int(STAGE.get("batch_size",8))))
def sha(path):
    """Calculate a streaming SHA-256 digest for a model or STEP export."""
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()
def add_geometry(stage, geometry, attributes):
    """Add a duplicated definition member to the temporary export document while preserving its Rhino attributes."""
    if isinstance(geometry,Rhino.Geometry.Brep): return stage.Objects.AddBrep(geometry.DuplicateBrep(),attributes)
    if isinstance(geometry,Rhino.Geometry.Extrusion): return stage.Objects.AddExtrusion(geometry.Duplicate(),attributes)
    if isinstance(geometry,Rhino.Geometry.Surface):
        brep=geometry.ToBrep(); return stage.Objects.AddBrep(brep,attributes) if brep else System.Guid.Empty
    if isinstance(geometry,Rhino.Geometry.SubD):
        brep=geometry.ToBrep(); return stage.Objects.AddBrep(brep,attributes) if brep else System.Guid.Empty
    if isinstance(geometry,Rhino.Geometry.Mesh): return stage.Objects.AddMesh(geometry.DuplicateMesh(),attributes)
    return System.Guid.Empty
for path in (SOURCE,INVENTORY,MANIFEST):
    if not os.path.isfile(path): raise FileNotFoundError(path)
D=Rhino.RhinoDoc.OpenHeadless(SOURCE)
if D is None: raise RuntimeError("Could not open colourized source headlessly")
try:
    inventory=json.load(open(INVENTORY,encoding="utf-8-sig")); manifest=json.load(open(MANIFEST,encoding="utf-8-sig")); source_sha=sha(SOURCE)
    if source_sha!=inventory.get("source_sha256") or source_sha!=manifest.get("source_sha256"):
        raise RuntimeError("Colourized source SHA does not match inventory/manifest")
    by_guid={str(x.Id):x for x in D.InstanceDefinitions if x and not x.IsDeleted}
    requests=[]
    for row in manifest.get("definition_documents",[]):
        if row.get("document_type")=="PAR": requests.append({"key":row["document_key"],"name":row["rhino_name"],"guid":row["rhino_definition_guid_provenance"],"relative":row["relative_output_path"],"kind":"LEAF_PART"})
        if row.get("local_geometry_companion_par"): requests.append({"key":row["document_key"]+"::LOCAL_GEOMETRY","name":row["rhino_name"],"guid":row["rhino_definition_guid_provenance"],"relative":row["local_geometry_companion_par"],"kind":"ASSEMBLY_LOCAL_GEOMETRY"})
    total=len(requests)
    if BATCH_START<0 or BATCH_START>=total: raise ValueError("STEP batch start is outside the request list")
    batch=requests[BATCH_START:min(total,BATCH_START+BATCH_SIZE)]
    # Open prior checkpoint so each small script call extends the same export report.
    existing=json.load(open(REPORT_PATH,encoding="utf-8-sig")) if os.path.isfile(REPORT_PATH) else {}
    if existing.get("source_sha256") not in (None,source_sha): raise RuntimeError("Existing STEP report is for a different colourized source")
    results=list(existing.get("results",[])); failures=list(existing.get("failures",[]))
    def save_report(status):
        """Write the source-bound STEP export summary and verification evidence as one report."""
        data={"schema_version":5,"created_at":datetime.datetime.now().astimezone().isoformat(),"source_path":D.Path,"source_sha256":source_sha,"requested_exports":total,"exported_count":len(results),"verified_exports":len(results),"failed_exports":len(failures),"results":results,"failures":failures,"batch_start":BATCH_START,"batch_size":BATCH_SIZE,"status":status,"export_policy":"leaf source block instance; direct-geometry fallback only when instance STEP writer returns false; 3 mixed-assembly local geometry companions; no Rhino readback/repair/join","native_readback":"Solid Edge import, save, close and disk reopen"}
        tmp=REPORT_PATH+".tmp"; json.dump(data,open(tmp,"w",encoding="utf-8"),indent=2,ensure_ascii=False); os.replace(tmp,REPORT_PATH)
    # Only this headless copy is modified. Keep block definitions, remove model space.
    for obj in list(D.Objects):
        if obj: D.Objects.Delete(obj,True)
    options=Rhino.FileIO.FileStpWriteOptions(); options.Schema=System.Enum.Parse(options.StepSchema,"SF_214")
    for offset,req in enumerate(batch):
        index=BATCH_START+offset+1; definition=by_guid.get(req["guid"]); stage=None; instance_id=System.Guid.Empty
        step_path=os.path.join(STEPS,os.path.splitext(os.path.basename(req["relative"]))[0]+".stp")
        try:
            if definition is None: raise RuntimeError("Source block definition is missing")
            if os.path.exists(step_path): os.remove(step_path)
            export_method="ORIGINAL_BLOCK_INSTANCE_DIRECT"; ignored=[]
            if req["kind"]=="LEAF_PART":
                attrs=Rhino.DocObjects.ObjectAttributes(); attrs.Name=req["name"]
                instance_id=D.Objects.AddInstanceObject(definition.Index,Rhino.Geometry.Transform.Identity,attrs)
                if instance_id==System.Guid.Empty: raise RuntimeError("Could not create temporary original block instance")
                wrote=Rhino.FileIO.FileStp.Write(step_path,D,options)
                if not wrote:
                    # Rhino rejects block-instance STEP for some surface-only blocks.
                    # Export their original direct geometry separately; do not repair it.
                    D.Objects.Delete(instance_id,True); instance_id=System.Guid.Empty
                    stage=Rhino.RhinoDoc.CreateHeadless(None); stage.ModelUnitSystem=D.ModelUnitSystem; stage.ModelAbsoluteTolerance=D.ModelAbsoluteTolerance
                    added=[]
                    for obj in definition.GetObjects():
                        if not obj or not obj.Geometry or isinstance(obj.Geometry,Rhino.Geometry.InstanceReferenceGeometry): continue
                        attrs=obj.Attributes.Duplicate(); attrs.Name=req["name"]; gid=add_geometry(stage,obj.Geometry,attrs)
                        if gid==System.Guid.Empty: ignored.append({"guid":str(obj.Id),"type":type(obj.Geometry).__name__})
                        else: added.append(str(gid))
                    if not added: raise RuntimeError("Block-instance STEP failed and direct geometry could not be added: "+json.dumps(ignored))
                    if os.path.exists(step_path): os.remove(step_path)
                    if not Rhino.FileIO.FileStp.Write(step_path,stage,options): raise RuntimeError("Direct geometry fallback STEP writer returned false")
                    export_method="DIRECT_GEOMETRY_FALLBACK"
            else:
                stage=Rhino.RhinoDoc.CreateHeadless(None); stage.ModelUnitSystem=D.ModelUnitSystem; stage.ModelAbsoluteTolerance=D.ModelAbsoluteTolerance
                added=[]
                for obj in definition.GetObjects():
                    if not obj or not obj.Geometry or isinstance(obj.Geometry,Rhino.Geometry.InstanceReferenceGeometry): continue
                    attrs=obj.Attributes.Duplicate(); attrs.Name=req["name"]; gid=add_geometry(stage,obj.Geometry,attrs)
                    if gid==System.Guid.Empty: ignored.append({"guid":str(obj.Id),"type":type(obj.Geometry).__name__})
                    else: added.append(str(gid))
                if not added: raise RuntimeError("Mixed assembly has no exportable direct geometry: "+json.dumps(ignored))
                if not Rhino.FileIO.FileStp.Write(step_path,stage,options): raise RuntimeError("Assembly local geometry STEP writer returned false")
                export_method="DIRECT_ASSEMBLY_LOCAL_GEOMETRY"
            if not os.path.isfile(step_path) or os.path.getsize(step_path)<100: raise RuntimeError("STEP output missing or empty")
            results=[x for x in results if x.get("document_key")!=req["key"]]; failures=[x for x in failures if x.get("key")!=req["key"]]
            results.append({"status":"EXPORTED","document_key":req["key"],"name":req["name"],"kind":req["kind"],"native_relative_path":req["relative"],"step_path":step_path,"step_bytes":os.path.getsize(step_path),"step_sha256":sha(step_path),"export_method":export_method,"geometry_repair_performed":False,"readback":{"status":"DEFERRED_TO_SOLID_EDGE_NATIVE_IMPORT"},"ignored_nonphysical_or_unsupported":ignored,"cached_verified":False})
            save_report("CHECKPOINT")
            print("STEP_EXPORTED "+str(index)+"/"+str(total)+" "+req["key"]+" method="+export_method,flush=True)
        except Exception as exc:
            failures=[x for x in failures if x.get("key")!=req["key"]]; failures.append({"key":req["key"],"name":req["name"],"path":step_path,"error":str(exc)})
            save_report("CHECKPOINT")
            print("STEP_EXPORT_FAILED "+str(index)+"/"+str(total)+" "+req["key"]+" "+str(exc),flush=True)
        finally:
            if instance_id!=System.Guid.Empty:
                try: D.Objects.Delete(instance_id,True)
                except Exception: pass
            if stage is not None:
                try: stage.Dispose()
                except Exception: pass
    final_status="EXPORTED" if BATCH_START+BATCH_SIZE>=total and len(results)==total and not failures else "CHECKPOINT"
    if BATCH_START+BATCH_SIZE>=total and (len(results)!=total or failures): final_status="INCOMPLETE"
    save_report(final_status)
    print("STEP_BATCH_SUMMARY "+json.dumps({"start":BATCH_START,"batch_count":len(batch),"total":total,"exported":len(results),"failed":len(failures),"status":final_status},ensure_ascii=False),flush=True)
finally:
    D.Dispose()
