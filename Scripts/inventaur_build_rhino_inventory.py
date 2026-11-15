"""Inventaur Inc. | inventaur_build_rhino_inventory.py - Rhino 3DM structure and transform inventory.

Execution context:
    Runs inside Rhino's Python host through the document-scoped Rhino MCP
    integration. Reads the run-scoped colourized 3DM headlessly via RhinoCommon.

Inputs:
    CAD_WORKFLOW_CONFIG, especially colorized_3dm and reports_root.

Outputs:
    rhino_active_inventory.json containing definition identities, nested
    references, member geometry counts, object attributes, model units,
    top-level/expanded occurrences and full 4x4 occurrence transforms.

This inventory is the transform source for native assembly construction.
Do not infer occurrence placement from STEP geometry or from viewport position.
The script does not edit the live Rhino document or source 3DM.
"""
__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"
import os
import Rhino, os, json, hashlib, datetime, math, unicodedata, collections
_CONFIG_ENV=os.environ.get("CAD_WORKFLOW_CONFIG")
if not _CONFIG_ENV:
    raise RuntimeError("CAD_WORKFLOW_CONFIG is required; refusing shared active_run.json fallback")
CONFIG_PATH=os.path.abspath(_CONFIG_ENV)
if not os.path.isfile(CONFIG_PATH):
    raise FileNotFoundError("Run-scoped CAD workflow config is missing: "+CONFIG_PATH)
with open(CONFIG_PATH,"r",encoding="utf-8-sig") as _config_stream:
    CONFIG=json.load(_config_stream)
SOURCE=CONFIG["colorized_3dm"]
OUTPUT=os.path.join(CONFIG["reports_root"],"rhino_active_inventory.json")

def sha(path):
    """Return a streaming SHA-256 digest for the source model or inventory artifact."""
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def name_key(value):
    """Normalize a Rhino definition/object name for stable, case-insensitive matching."""
    return ' '.join(unicodedata.normalize('NFKC',value or '').strip().split()).casefold()

def matrix_of(transform):
    """Convert a RhinoCommon transform into a JSON-safe 4-by-4 numeric matrix."""
    return [[float(getattr(transform,'M'+str(i)+str(j))) for j in range(4)] for i in range(4)]

def transform_info(transform):
    """Describe an instance transform, including its matrix and scale/reflection properties."""
    m=matrix_of(transform)
    axes=[[m[i][j] for j in range(3)] for i in range(3)]
    scales=[math.sqrt(sum(v*v for v in row)) for row in axes]
    pairs=[(0,1),(0,2),(1,2)]
    dots=[sum(axes[i][k]*axes[j][k] for k in range(3))/(scales[i]*scales[j]) if scales[i]*scales[j] else 1.0 for i,j in pairs]
    det=(m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1])-m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0])+m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]))
    max_dot=max(abs(x) for x in dots) if dots else 0.0
    uniform=(max(scales)-min(scales))<1e-8
    shear=max_dot>1e-8
    return {'matrix':m,'translation':[m[0][3],m[1][3],m[2][3]],'axis_scales':scales,'determinant':det,
        'reflection':det<0,'singular':abs(det)<1e-10,'has_shear':shear,'max_axis_dot':max_dot,'uniform_scale':uniform}

def bbox(g):
    """Return a JSON-safe bounding box for a Rhino geometry object when one is available."""
    b=g.GetBoundingBox(True)
    return [[float(b.Min.X),float(b.Min.Y),float(b.Min.Z)],[float(b.Max.X),float(b.Max.Y),float(b.Max.Z)]]

def naked_count(b):
    """Count naked Brep edges without changing the source geometry."""
    return sum(1 for e in b.Edges if str(e.Valence).endswith('Naked'))

if not os.path.isfile(SOURCE):raise FileNotFoundError(SOURCE)
source_sha=sha(SOURCE)
doc=Rhino.RhinoDoc.OpenHeadless(SOURCE)
if doc is None:raise RuntimeError('OpenHeadless failed')
try:
    definitions=[x for x in doc.InstanceDefinitions if x and not x.IsDeleted]
    by_guid={str(x.Id):x for x in definitions}
    rows=[]
    all_transform_records=[]
    for definition in definitions:
        members=list(definition.GetObjects())
        type_counts=collections.Counter(type(o.Geometry).__name__ for o in members if o and o.Geometry)
        children=[]
        direct_breps=[]
        for obj in members:
            if not obj or not obj.Geometry:continue
            geometry=obj.Geometry
            if isinstance(geometry,Rhino.Geometry.InstanceReferenceGeometry):
                child_guid=str(geometry.ParentIdefId)
                child_def=by_guid.get(child_guid)
                tr=transform_info(geometry.Xform)
                children.append({'instance_guid':str(obj.Id),'definition_guid':child_guid,
                    'definition_name':child_def.Name if child_def else None,'transform':tr})
                all_transform_records.append({'where':'BLOCK:'+definition.Name,'child_name':child_def.Name if child_def else None,'transform':tr})
            elif isinstance(geometry,Rhino.Geometry.Brep):
                direct_breps.append({'object_guid':str(obj.Id),'type':'Brep','bbox_mm':bbox(geometry),
                    'faces':geometry.Faces.Count,'edges':geometry.Edges.Count,'is_solid':bool(geometry.IsSolid),
                    'is_valid':bool(geometry.IsValid),'naked_edges':naked_count(geometry)})
        rows.append({'definition_guid':str(definition.Id),'index':definition.Index,'name':definition.Name,
            'name_key':name_key(definition.Name),'kind':'ASSEMBLY' if children else 'PART','member_count':len(members),
            'type_counts':dict(type_counts),'direct_breps':direct_breps,'children':children})
    top=[]
    model_types=collections.Counter()
    for obj in doc.Objects:
        if not obj or not obj.Geometry:continue
        model_types[type(obj.Geometry).__name__]+=1
        if isinstance(obj.Geometry,Rhino.Geometry.InstanceReferenceGeometry):
            guid=str(obj.Geometry.ParentIdefId);d=by_guid.get(guid);tr=transform_info(obj.Geometry.Xform)
            top.append({'instance_guid':str(obj.Id),'definition_guid':guid,'definition_name':d.Name if d else None,'transform':tr})
            all_transform_records.append({'where':'MODELSPACE','child_name':d.Name if d else None,'transform':tr})
    # Recursive occurrence expansion: count each inserted block definition in the full hierarchy.
    expanded={str(x.Id):0 for x in definitions};cycles=[];max_depth=0
    def walk(guid,trail,depth):
        """Recursively inspect nested block references and update the observed hierarchy depth."""
        global max_depth
        if guid in trail:
            cycles.append(trail+[guid]);return
        if guid not in expanded:return
        expanded[guid]+=1
        max_depth=max(max_depth,depth)
        row=next(x for x in rows if x['definition_guid']==guid)
        for child in row['children']:
            walk(child['definition_guid'],trail+[guid],depth+1)
    for occurrence in top:walk(occurrence['definition_guid'],[],1)
    expanded_names={}
    for row in rows:expanded_names[row['name']]=expanded.get(row['definition_guid'],0)
    groups={}
    for row in rows:groups.setdefault(row['name_key'],[]).append(row)
    duplicates=[{'name_key':k,'definition_guids':[x['definition_guid'] for x in v],'names':[x['name'] for x in v]} for k,v in groups.items() if len(v)>1]
    flag_records={'reflection':[],'nonuniform_scale':[],'shear':[]}
    for entry in all_transform_records:
        tr=entry['transform']
        if tr['reflection']:flag_records['reflection'].append(entry)
        if not tr['uniform_scale']:flag_records['nonuniform_scale'].append(entry)
        if tr['has_shear']:flag_records['shear'].append(entry)
    result={'schema_version':2,'status':'VERIFIED','created_at':datetime.datetime.now().astimezone().isoformat(),'source_path':doc.Path,
        'source_sha256':source_sha,'units':str(doc.ModelUnitSystem),'absolute_tolerance':float(doc.ModelAbsoluteTolerance),
        'modified':bool(doc.Modified),'modelspace_object_count':doc.Objects.Count,'modelspace_type_counts':dict(model_types),
        'definition_count':len(definitions),'top_level_occurrence_count':len(top),'expanded_occurrence_total':sum(expanded.values()),
        'max_nesting_depth':max_depth,'definitions':rows,'top_level_occurrences':top,
        'expanded_occurrences_by_guid':expanded,'expanded_occurrences_by_name':expanded_names,
        'duplicate_normalized_names':duplicates,'cycle_count':len(cycles),'cycles':cycles,
        'transform_flags':{k:len(v) for k,v in flag_records.items()},'transform_flag_details':flag_records,
        'geometry_totals':{'direct_brep_count':sum(len(x['direct_breps']) for x in rows),
            'direct_brep_valid_count':sum(1 for x in rows for b in x['direct_breps'] if b['is_valid']),
            'direct_brep_invalid_count':sum(1 for x in rows for b in x['direct_breps'] if not b['is_valid']),
            'direct_brep_face_count':sum(b['faces'] for x in rows for b in x['direct_breps'])}}
    with open(OUTPUT,'w',encoding='utf-8') as f:json.dump(result,f,indent=2,ensure_ascii=False)
    print('INVENTORY_SUMMARY '+json.dumps({'status':'VERIFIED','source':doc.Path,'sha256':source_sha,
        'definitions':len(definitions),'unique_names':len(groups),'duplicate_names':len(duplicates),
        'top_level_occurrences':len(top),'expanded_occurrences':sum(expanded.values()),'max_depth':max_depth,
        'cycles':len(cycles),'breps':result['geometry_totals'],'transform_flags':result['transform_flags'],
        'report':OUTPUT},ensure_ascii=False))
finally:
    doc.Dispose()
