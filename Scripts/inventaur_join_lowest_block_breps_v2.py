# -*- coding: utf-8 -*-
"""Inventaur Inc. | Optional RhinoCommon JoinBreps preparation for leaf block definitions.

This utility is NOT part of the default production supervisor sequence.
It operates only on the run-scoped source 3DM named by CAD_WORKFLOW_CONFIG and
writes a separate joined_3dm plus a JSON report. The original model is preserved.

A leaf definition has no nested InstanceReferenceGeometry. Directly-owned Breps
are passed to RhinoCommon Brep.JoinBreps; this is not Boolean union. Curves,
meshes, SubD and nested references are retained. A definition is changed only
when the joined result is considered an improvement.

The join tolerance defaults to the source document's ModelAbsoluteTolerance,
in the source model's units. geometry_join_tolerance may explicitly override it.
The report records both units and the source document tolerance.

Run inside Rhino's Python host or through the Rhino MCP run_python integration.
The source must be a run-owned copy; do not use the operator's live document.
"""
from __future__ import print_function
__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"
from pathlib import Path
import os, json, hashlib, datetime, traceback
import Rhino
import Rhino.Geometry as RG

_CONFIG_ENV = os.environ.get("CAD_WORKFLOW_CONFIG")
if not _CONFIG_ENV:
    raise RuntimeError("CAD_WORKFLOW_CONFIG is required; refusing shared active_run.json fallback")
CONFIG_PATH = Path(_CONFIG_ENV).resolve()
if not CONFIG_PATH.is_file():
    raise FileNotFoundError("Run-scoped CAD workflow config is missing: " + str(CONFIG_PATH))
with CONFIG_PATH.open("r", encoding="utf-8-sig") as _config_stream:
    CONFIG = json.load(_config_stream)
SOURCE = CONFIG["source_3dm"]
OUTPUT = CONFIG["joined_3dm"]
REPORT = os.path.join(CONFIG["reports_root"], "join_lowest_block_breps_v2_report.json")
TOLERANCE = 0.005
ANGLE_TOLERANCE = 0.017453292519943295


def sha256(path):
    """Return a streaming SHA-256 digest for the input and derived Rhino 3DM files."""
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def now():
    """Return an offset-aware local timestamp for stage reports."""
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


def is_leaf(idef, doc):
    """Return true when a block definition has no nested instance-reference members."""
    for oid in idef.GetObjectIds():
        ro=doc.Objects.FindId(oid)
        if ro and isinstance(ro.Geometry, RG.InstanceReferenceGeometry):
            return False
    return True


def brep_stats(geos):
    """Collect validity, solid state, face/edge counts and naked-edge diagnostics for a Brep."""
    return {
        'brep_count':sum(1 for g in geos if isinstance(g,RG.Brep)),
        'face_count':sum(g.Faces.Count for g in geos if isinstance(g,RG.Brep)),
        'edge_count':sum(g.Edges.Count for g in geos if isinstance(g,RG.Brep)),
        'valid_count':sum(1 for g in geos if isinstance(g,RG.Brep) and g.IsValid),
        'solid_count':sum(1 for g in geos if isinstance(g,RG.Brep) and g.IsSolid),
        'naked_edge_count':sum(sum(1 for e in g.Edges if e.Valence==RG.EdgeAdjacency.Naked) for g in geos if isinstance(g,RG.Brep)),
    }


def run():
    """Join directly owned Breps in eligible leaf definitions and write a separate derived 3DM/report."""
    if not os.path.isfile(SOURCE): raise IOError('SOURCE missing: '+SOURCE)
    if os.path.exists(OUTPUT): raise IOError('Refusing to overwrite existing output: '+OUTPUT)
    if not os.path.isdir(os.path.dirname(OUTPUT)): os.makedirs(os.path.dirname(OUTPUT))
    if not os.path.isdir(os.path.dirname(REPORT)): os.makedirs(os.path.dirname(REPORT))

    source_hash=sha256(SOURCE)
    doc=Rhino.RhinoDoc.OpenHeadless(SOURCE)
    if doc is None: raise RuntimeError('RhinoDoc.OpenHeadless failed')
    # Use source document units/tolerance unless the run explicitly overrides it.
    global TOLERANCE
    TOLERANCE=float(CONFIG.get("geometry_join_tolerance") or doc.ModelAbsoluteTolerance)
    if TOLERANCE <= 0: raise ValueError("Geometry join tolerance must be positive")
    report={'schema_version':2,'script':'inventaur_join_lowest_block_breps_v2.py','status':'RUNNING','started_at':now(),
            'source':SOURCE,'source_sha256':source_hash,'output':OUTPUT,'tolerance':TOLERANCE,
            'angle_tolerance':ANGLE_TOLERANCE,'definitions_total':doc.InstanceDefinitions.Count,'model_units':str(doc.ModelUnitSystem),'model_absolute_tolerance':float(doc.ModelAbsoluteTolerance),'results':[]}
    try:
        defs=[doc.InstanceDefinitions[i] for i in range(doc.InstanceDefinitions.Count) if doc.InstanceDefinitions[i] and not doc.InstanceDefinitions[i].IsDeleted]
        for idx,idef in enumerate(defs):
            if not is_leaf(idef, doc): continue
            geos=[];attrs=[];brep_indices=[]
            for oid in idef.GetObjectIds():
                ro=doc.Objects.FindId(oid)
                if not ro: continue
                geos.append(ro.Geometry.Duplicate());attrs.append(ro.Attributes.Duplicate())
                if isinstance(ro.Geometry,RG.Brep): brep_indices.append(len(geos)-1)
            if len(brep_indices)<2:
                report['results'].append({'definition_guid':str(idef.Id),'name':idef.Name,'status':'UNCHANGED','reason':'less_than_two_breps','before':brep_stats(geos),'after':brep_stats(geos)})
                continue
            before=brep_stats(geos)
            breps=[geos[i] for i in brep_indices]
            try:
                joined=RG.Brep.JoinBreps(breps,TOLERANCE,ANGLE_TOLERANCE)
            except Exception as ex:
                joined=None
                join_error=str(ex)
            if not joined:
                report['results'].append({'definition_guid':str(idef.Id),'name':idef.Name,'status':'FAILED_JOIN_RETAINED','before':before,'after':before,'error':locals().get('join_error','JoinBreps returned None')})
                continue
            # Replace only the Brep slots. Non-Brep members retain their original
            # order and geometry. This keeps nested/curve members untouched.
            new_geos=[];new_attrs=[]
            for i,(g,a) in enumerate(zip(geos,attrs)):
                if i==brep_indices[0]:
                    for j,b in enumerate(joined):
                        new_geos.append(b);na=a.Duplicate();new_attrs.append(na)
                elif i in brep_indices:
                    continue
                else:
                    new_geos.append(g);new_attrs.append(a)
            after=brep_stats(new_geos)
            # JoinBreps is accepted only if it did not lose Brep face count and
            # reduced the Brep object count. This is the key regression guard.
            if after['face_count'] < before['face_count'] or after['brep_count'] >= before['brep_count']:
                report['results'].append({'definition_guid':str(idef.Id),'name':idef.Name,'status':'REJECTED_NO_IMPROVEMENT','before':before,'candidate':after})
                continue
            if not doc.InstanceDefinitions.ModifyGeometry(idef.Index,new_geos,new_attrs):
                raise RuntimeError('ModifyGeometry failed for '+idef.Name)
            report['results'].append({'definition_guid':str(idef.Id),'name':idef.Name,'status':'JOINED','before':before,'after':after,'breps_reduced_by':before['brep_count']-after['brep_count'],'faces_delta':after['face_count']-before['face_count']})
        if not doc.SaveAs(OUTPUT): raise RuntimeError('RhinoDoc.SaveAs failed')
    finally:
        try: doc.Dispose()
        except: pass
    out_hash=sha256(OUTPUT)
    joined=sum(1 for x in report['results'] if x['status']=='JOINED')
    report.update({'status':'VERIFIED','finished_at':now(),'output_sha256':out_hash,'joined_definitions':joined,
                   'unchanged_definitions':sum(1 for x in report['results'] if x['status']=='UNCHANGED'),
                   'failed_join_definitions':sum(1 for x in report['results'] if x['status']=='FAILED_JOIN_RETAINED'),
                   'rejected_definitions':sum(1 for x in report['results'] if x['status']=='REJECTED_NO_IMPROVEMENT'),
                   'source_unchanged':sha256(SOURCE)==source_hash})
    with open(REPORT,'w',encoding='utf-8') as f: json.dump(report,f,indent=2,ensure_ascii=False)
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))

if __name__=='__main__': run()
