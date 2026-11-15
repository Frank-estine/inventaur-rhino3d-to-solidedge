"""Inventaur Inc. | Build the name-stable Rhino-to-Solid-Edge identity manifest.

Inputs: active-run configuration, Rhino inventory, and verified source-color report.
Output: name_identity_manifest.json. The module fails closed on duplicate normalized
names, filename collisions, missing verification evidence, or geometry/color
inconsistency; it does not create Solid Edge documents itself.
"""

from __future__ import annotations
__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"
import os
import json,os,re,unicodedata,hashlib
from collections import Counter
from datetime import datetime
from pathlib import Path

_CONFIG_ENV=os.environ.get("CAD_WORKFLOW_CONFIG")
if not _CONFIG_ENV:
    raise RuntimeError("CAD_WORKFLOW_CONFIG is required; refusing shared active_run.json fallback")
CONFIG_PATH=os.path.abspath(_CONFIG_ENV)
if not os.path.isfile(CONFIG_PATH):
    raise FileNotFoundError("Run-scoped CAD workflow config is missing: "+CONFIG_PATH)
with open(CONFIG_PATH,"r",encoding="utf-8-sig") as _config_stream:
    CONFIG=json.load(_config_stream)
RUN=Path(CONFIG["run_root"]);PIPE=Path(CONFIG["pipeline_root"]);REPORTS=Path(CONFIG["reports_root"])
INV=REPORTS/'rhino_active_inventory.json';COLOR=REPORTS/'colorize_rhino_unique_blocks_v2_report.json';OUT=REPORTS/'name_identity_manifest.json'
PHYSICAL={'Brep','Extrusion','Mesh','SubD','Surface'}

def name_key(value):
    """Return the canonical case-insensitive identity key for a Rhino block name."""
    return ' '.join(unicodedata.normalize('NFKC',value or '').strip().split()).casefold()

def slug(value):
    """Convert a Rhino definition name into a filesystem-safe stable output slug."""
    text=unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode('ascii').lower()
    text=text.replace('&',' and ').replace('+',' ')
    text=re.sub(r'[^a-z0-9]+','_',text).strip('_')
    return text or 'unnamed_block'

def atomic_json(path, data):
    """Atomically write a JSON report, preventing partial manifest files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)

def main():
    """Validate upstream reports, construct identity rows, and write the verified manifest.

    Raises FileNotFoundError for missing upstream reports and RuntimeError when verification or identity invariants fail.
    """
    for required in (INV,COLOR):
        if not required.is_file():raise FileNotFoundError(required)
    inv=json.loads(INV.read_text(encoding='utf-8-sig'))
    color=json.loads(COLOR.read_text(encoding='utf-8-sig'))
    if color.get('status')!='VERIFIED' or color.get('alpha30_preserved') is not True:
        raise RuntimeError('Source block colour/alpha pass is not VERIFIED')
    source_sha=inv['source_sha256']
    if inv.get('duplicate_normalized_names') or inv.get('cycle_count'):
        raise RuntimeError('Duplicate normalized names or block-reference cycles detected')
    palette={str(x.get("guid")):x for x in color.get("definitions",[]) if x.get("guid")}
    rows=[];filenames=set();namekeys=set()
    for d in inv['definitions']:
        guid=d['definition_guid'];nk=name_key(d['name']);children=d.get('children',[])
        counts={k:int(v) for k,v in d.get('type_counts',{}).items() if k in PHYSICAL and int(v)>0}
        physical_count=sum(counts.values());is_asm=bool(children)
        document_type='ASM' if is_asm else 'PAR'
        base=slug(d['name'])
        rel=(f'Assemblies/{base}.asm' if is_asm else f'Parts/{base}.par')
        if rel.casefold() in filenames:raise RuntimeError('Filename collision after slug normalization: '+rel)
        filenames.add(rel.casefold())
        local=f'Parts/{base}__local_geometry.par' if is_asm and physical_count else None
        if local:
            if local.casefold() in filenames:raise RuntimeError('Local geometry companion filename collision: '+local)
            filenames.add(local.casefold())
        p=palette.get(guid,{})
        if physical_count and not p.get('rgb'):
            raise RuntimeError('Missing verified source block colour: '+d['name'])
        rows.append({
            'document_key':'block_name:'+nk,
            'normalized_name':nk,
            'rhino_name':d['name'],
            'rhino_definition_guid_provenance':guid,
            'document_type':document_type,
            'relative_output_path':rel,
            'local_geometry_companion_par':local,
            'expanded_occurrence_count':int(inv.get('expanded_occurrences_by_guid',{}).get(guid,0)),
            'direct_physical_geometry_counts':counts,
            'direct_brep_count':len(d.get('direct_breps',[])),
            'child_block_occurrence_count':len(children),
            'child_name_keys':[name_key(x.get('definition_name') or '') for x in children],
            'geometry_signature_for_audit':{
                'kind':'ASSEMBLY' if is_asm else 'PART',
                'physical_geometry_counts':counts,
                'physical_object_count':physical_count,
                'physical_brep_count':len(d.get('direct_breps',[])),
                'physical_brep_faces':[int(x['faces']) for x in d.get('direct_breps',[])],
                'physical_brep_solids':[bool(x['is_solid']) for x in d.get('direct_breps',[])],
                'child_name_keys':sorted(name_key(x.get('definition_name') or '') for x in children),
                'child_count':len(children),
            },
            'color_rgb':p.get('rgb'),'color_hex':p.get('hex'),'color_action':p.get('action'),
            'color_source':'RHINO_SOURCE_PRESERVING_BLOCK_PALETTE' if physical_count else 'CHILD_DEFINITION_COLORS',
            'status':'NAME_UNIQUE_IN_SOURCE',
        })
        if nk in namekeys:raise RuntimeError('Duplicate normalized block identity: '+nk)
        namekeys.add(nk)
    counts=Counter(x['document_type'] for x in rows);local_count=sum(bool(x['local_geometry_companion_par']) for x in rows)
    if len(rows) != int(inv['definition_count']) or len(namekeys) != len(rows):
        raise RuntimeError('Manifest definition/name count does not match the Rhino inventory')
    manifest={
        'schema_version':2,'status':'VERIFIED','identity_policy':'NORMALIZED_RHINO_BLOCK_NAME',
        'normalization':'Unicode NFKC; trim; collapse whitespace; casefold',
        'guid_policy':'provenance and source occurrence locator only; never a native document identity or filename discriminator',
        'repeat_policy':'one reusable native document per normalized definition name; each Rhino instance is a separate Solid Edge occurrence of that exact file path',
        'collision_policy':'same normalized name resolves to one document; duplicate name or filename collision is a hard stop',
        'transform_policy':'definition geometry remains local; parent-child transforms are applied to occurrences; reflections supported; non-unit scale/shear require verified baked variants',
        'source_path':inv['source_path'],'source_sha256':source_sha,'source_units':inv['units'],
        'rhino_definition_count':inv['definition_count'],'unique_normalized_name_count':len(namekeys),
        'duplicate_name_collision_count':len(inv.get('duplicate_normalized_names',[])),
        'top_level_rhino_occurrence_count':inv['top_level_occurrence_count'],
        'expanded_rhino_occurrence_total':inv['expanded_occurrence_total'],
        'expected_top_level_document':'Root.asm','physical_geometry_types':sorted(PHYSICAL),
        'blocked_name_collisions':[],'transform_flags':inv['transform_flags'],'build_ready':True,
        'color_policy_report':str(COLOR),
        'color_policy':'required: preserve source non-black RGB, randomise only black, lift dark non-black, preserve object alpha',
        'definition_documents':rows,
        'expected_counts':{'reusable_leaf_par_definitions':counts['PAR'],'reusable_nested_asm_definitions':counts['ASM'],'mixed_assembly_local_geometry_pars':local_count,'root_assembly_documents':1},
        'created_at':datetime.now().astimezone().isoformat(timespec='seconds'),
    }
    atomic_json(OUT,manifest)
    print(json.dumps({'status':'VERIFIED','manifest':str(OUT),'definitions':len(rows),'leaf_PAR':counts['PAR'],'nested_ASM':counts['ASM'],'local_geometry_PAR':local_count,'root_occurrences':inv['top_level_occurrence_count'],'expanded_occurrences':inv['expanded_occurrence_total'],'source_sha256':source_sha},indent=2,ensure_ascii=False))
if __name__=='__main__':main()
