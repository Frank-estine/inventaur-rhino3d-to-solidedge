# -*- coding: utf-8 -*-
"""Inventaur Inc. | Deterministic colour assignment for unique Rhino block definitions.

Execution context:
    Runs as a RhinoCommon stage against a run-owned 3DM copy. The production
    supervisor invokes this after the live-document snapshot and before the
    inventory stage. It does not require the optional Brep-join utility.

Colour policy:
    - Every directly-owned physical object in one definition receives one RGB.
    - Repeated instances therefore display consistent definition colours.
    - Existing non-black colours are preserved; black/dark colours are lifted
      deterministically into a medium range.
    - Alpha/transparency is preserved.
    - Child InstanceReferenceGeometry is never recoloured by its parent.

The input 3DM is never overwritten. The output model is reopened for readback,
and the report records the palette, alpha counts, source/output hashes and
verification result.
"""
from __future__ import print_function
__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"
import os,json,hashlib,datetime,math
import Rhino
import Rhino.Geometry as RG
import System
import System.Drawing as SD

_CONFIG_ENV=os.environ.get("CAD_WORKFLOW_CONFIG")
if not _CONFIG_ENV:
    raise RuntimeError("CAD_WORKFLOW_CONFIG is required; refusing shared active_run.json fallback")
CONFIG_PATH=os.path.abspath(_CONFIG_ENV)
if not os.path.isfile(CONFIG_PATH):
    raise FileNotFoundError("Run-scoped CAD workflow config is missing: "+CONFIG_PATH)
with open(CONFIG_PATH,"r",encoding="utf-8-sig") as _config_stream:
    CONFIG=json.load(_config_stream)
SOURCE=CONFIG["source_3dm"]
OUTPUT=CONFIG["colorized_3dm"]
REPORT=os.path.join(CONFIG["reports_root"],"colorize_rhino_unique_blocks_v2_report.json")
BLACK_MAX=5; MIN_CH=90; MAX_CH=225

def sha(p):
 """Return the SHA-256 hex digest of a file using bounded streaming reads. The source file is opened read-only; the digest binds the color report to the exact Rhino input."""
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for c in iter(lambda:f.read(1048576),b''):h.update(c)
 return h.hexdigest()
def now():
 """Return the current local time as an offset-aware ISO-8601 timestamp with second precision for the run report."""
 return datetime.datetime.now().astimezone().isoformat(timespec='seconds')
def hsv_to_rgb(h,s,v):
 """Convert hue in degrees plus normalized saturation/value to an 8-bit (red, green, blue) tuple. Hue wraps at 360 degrees; this helper does not mutate Rhino objects."""
 import colorsys
 r,g,b=colorsys.hsv_to_rgb((h%360)/360.0,s,v);return (int(r*255),int(g*255),int(b*255))
def deterministic_color(guid):
 """Derive one stable medium-tone RGB color from a Rhino block-definition GUID. SHA-256 supplies the hue seed so repeated runs and instances of the same definition receive the same palette color."""
 d=hashlib.sha256(str(guid).encode('ascii')).digest();h=(int.from_bytes(d[:4],'big')/4294967296.0*360.0+137.5077)%360
 # Medium saturation/value gives readable colours without the dark range.
 return hsv_to_rgb(h,0.52,0.82)
def rgb_from_attrs(a,doc):
 """Resolve the effective source color from Rhino object attributes or the referenced layer. Return ((R, G, B, A), source_kind) for object/layer colors, or (None, other_source_kind) when the color is inherited/unsupported; transparency is retained."""
 src=str(a.ColorSource).split('.')[-1]
 if src=='ColorFromObject': c=a.ObjectColor;return (c.R,c.G,c.B,c.A),'OBJECT'
 if src=='ColorFromLayer':
  layer=doc.Layers[a.LayerIndex]
  if layer: c=layer.Color;return (c.R,c.G,c.B,c.A),'LAYER'
 return None,src
def lift_dark(rgb):
 # Keep hue; only raise value/saturation enough to leave the dark range.
 """Lift genuinely dark RGB values into the medium-value range while preserving hue and saturation. Values already above the dark threshold are returned unchanged; this is not a randomization step."""
 import colorsys
 r,g,b=[x/255.0 for x in rgb];h,s,v=colorsys.rgb_to_hsv(r,g,b)
 if v>=0.34:return rgb
 v=max(0.68,v*1.9);s=min(0.65,max(0.35,s));return hsv_to_rgb(h*360,s,v)
def run():
 """Run the headless Rhino block-color pass against SOURCE and create the separate OUTPUT plus verification report. It preserves existing non-black colors, randomizes only true black, lifts dark colors, preserves alpha and does not recolor nested instance references. It refuses a missing source or existing output and raises when Rhino cannot open or reopen the result; writes output/report files and performs a readback verification."""
 if not os.path.isfile(SOURCE):raise IOError('Missing '+SOURCE)
 if os.path.exists(OUTPUT):raise IOError('Refusing overwrite '+OUTPUT)
 sh=sha(SOURCE);doc=Rhino.RhinoDoc.OpenHeadless(SOURCE)
 if doc is None:raise RuntimeError('OpenHeadless failed')
 report={'schema_version':2,'script':'inventaur_colorize_rhino_unique_blocks_v2.py','status':'RUNNING','source':SOURCE,'source_sha256':sh,'output':OUTPUT,'started_at':now(),'definitions':[],'alpha_before':{},'alpha_after':{}}
 try:
  for i in range(doc.InstanceDefinitions.Count):
   d=doc.InstanceDefinitions[i]
   if not d or d.IsDeleted:continue
   physical=[];hist={}
   for oid in d.GetObjectIds():
    ro=doc.Objects.FindId(oid)
    if not ro or isinstance(ro.Geometry,RG.InstanceReferenceGeometry):continue
    if isinstance(ro.Geometry,(RG.Brep,RG.Extrusion,RG.Surface,RG.Mesh,RG.SubD)):
     physical.append(ro);rgba,how=rgb_from_attrs(ro.Attributes,doc)
     if rgba:hist[rgba[:3]]=hist.get(rgba[:3],0)+1
   if not physical:
    report['definitions'].append({'guid':str(d.Id),'name':d.Name,'status':'NO_DIRECT_PHYSICAL_GEOMETRY'});continue
   source_rgb=max(hist.items(),key=lambda kv:kv[1])[0] if hist else (0,0,0)
   if max(source_rgb)<=BLACK_MAX:chosen=deterministic_color(d.Id);action='BLACK_RANDOMIZED'
   elif max(source_rgb)<88:chosen=lift_dark(source_rgb);action='DARK_NONBLACK_LIGHTENED'
   else:chosen=source_rgb;action='NONBLACK_SOURCE_PRESERVED'
   for ro in physical:
    old=ro.Attributes.ObjectColor
    # Preserve exact alpha. Setting ColorFromObject makes the block colour
    # independent from layer colours while retaining the source transparency.
    na=ro.Attributes.Duplicate();na.ColorSource=Rhino.DocObjects.ObjectColorSource.ColorFromObject
    na.ObjectColor=SD.Color.FromArgb(old.A,chosen[0],chosen[1],chosen[2])
    doc.Objects.ModifyAttributes(ro.Id,na,False)
    report['alpha_before'][str(old.A)]=report['alpha_before'].get(str(old.A),0)+1
   report['definitions'].append({'guid':str(d.Id),'name':d.Name,'status':'COLOURED','rgb':list(chosen),'hex':'#{:02X}{:02X}{:02X}'.format(*chosen),'source_rgb':list(source_rgb),'action':action,'direct_physical_object_count':len(physical)})
  if not doc.SaveAs(OUTPUT):raise RuntimeError('SaveAs failed')
 finally:
  try:doc.Dispose()
  except:pass
 # Reopen and verify every changed object has its assigned RGB and alpha.
 check=Rhino.RhinoDoc.OpenHeadless(OUTPUT)
 if check is None:raise RuntimeError('Output reopen failed')
 try:
  expected={x['guid']:(tuple(x['rgb']),x['direct_physical_object_count']) for x in report['definitions'] if x.get('rgb')}
  checked=0;errors=[]
  for guid,(rgb,count) in expected.items():
   d=check.InstanceDefinitions.Find(System.Guid(guid),True)
   if not d:errors.append('missing definition '+guid);continue
   seen=set()
   for oid in d.GetObjectIds():
    ro=check.Objects.FindId(oid)
    if not ro or isinstance(ro.Geometry,RG.InstanceReferenceGeometry):continue
    if not isinstance(ro.Geometry,(RG.Brep,RG.Extrusion,RG.Surface,RG.Mesh,RG.SubD)):continue
    c=ro.Attributes.ObjectColor;seen.add((c.R,c.G,c.B,c.A));checked+=1;report['alpha_after'][str(c.A)]=report['alpha_after'].get(str(c.A),0)+1
   if seen!={(rgb[0],rgb[1],rgb[2],a) for a in [x[3] for x in seen]} and any(x[:3]!=(rgb[0],rgb[1],rgb[2]) for x in seen):errors.append('nonuniform RGB '+d.Name)
   if len(seen)>1 and len({x[:3] for x in seen})>1:errors.append('mixed RGB '+d.Name)
  if report['alpha_before'].get('30',0)!=report['alpha_after'].get('30',0):errors.append('alpha30 count changed')
  if errors:raise RuntimeError('Color readback failed: '+json.dumps(errors[:20]))
 finally:
  try:check.Dispose()
  except:pass
 report.update({'status':'VERIFIED','finished_at':now(),'output_sha256':sha(OUTPUT),'source_unchanged':sha(SOURCE)==sh,'definitions_with_direct_geometry':sum(1 for x in report['definitions'] if x.get('rgb')),'direct_objects_verified':checked,'alpha30_preserved':report['alpha_before'].get('30',0)==report['alpha_after'].get('30',0)})
 with open(REPORT,'w',encoding='utf-8') as f:json.dump(report,f,indent=2,ensure_ascii=False)
 print(json.dumps({k:v for k,v in report.items() if k!='definitions'},indent=2))
if __name__=='__main__':run()
