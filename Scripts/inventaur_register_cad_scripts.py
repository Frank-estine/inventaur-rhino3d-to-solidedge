"""Inventaur Inc. | Optional developer-only synchronizer for the existing local CAD SQLite registry.

This script mutates the separate workspace CAD_AUTOMATION_REGISTRY.sqlite database.
It is excluded from recipient bootstrap packages and is not required to run conversion.
"""
__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"
from pathlib import Path
import sqlite3, hashlib, datetime, json

SCRIPT_ROOT = Path(__file__).resolve().parent
OWNER = SCRIPT_ROOT.parent
CAD = OWNER.parent
DB = CAD / "CAD_AUTOMATION_REGISTRY.sqlite"
now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

# Registry script IDs are persistent database keys. Keep them stable while the
# source filenames are branded; changing a key requires a separately reviewed
# SQLite migration that preserves workflow foreign-key relationships.
CANONICAL = {
    "inventaur_build_identity_manifest.py": "se.build_identity_manifest",
    "inventaur_build_nested_assembly_tree.py": "se.build_nested_assemblies",
    "inventaur_build_rhino_inventory.py": "rhino.inventory_blocks",
    "inventaur_colorize_rhino_unique_blocks_v2.py": "rhino.colorize_unique_blocks.v2",
    "inventaur_export_named_block_geometry_to_step_rhino.py": "rhino.export_blocks_step",
    "inventaur_export_scaled_occurrence_variant_rhino.py": "rhino.export_scaled_occurrence_variant",
    "inventaur_import_step_parts_native_v2.py": "se.import_native_parts.v2",
    "inventaur_join_lowest_block_breps_v2.py": "rhino.join_leaf_breps.v2",
    "inventaur_recover_assembly_build.py": "se.recover_assembly_tree",
    "inventaur_repair_breps_for_step_v1.py": "rhino.repair_breps_for_step",
    "inventaur_run_rhino3d_to_solidedge.py": "workflow.run_e2e",
    "inventaur_verify_active_rhino_source.py": "rhino.verify_active_source",
}
def sha256(path: Path) -> str:
    """Return a streaming SHA-256 digest for a registered automation script."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

con = sqlite3.connect(DB)
con.execute("PRAGMA foreign_keys=ON")
with con:
    for filename, sid in CANONICAL.items():
        path = SCRIPT_ROOT / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        row = con.execute("SELECT script_id FROM cad_scripts WHERE script_id=?", (sid,)).fetchone()
        if not row:
            raise RuntimeError("Canonical script is missing from the curated registry: " + sid)
        con.execute("""UPDATE cad_scripts SET script_path=?, owner_workflow='Rhino3D_to_SolidEdge_Workflow',
            owner_folder='Rhino3D_to_SolidEdge_Workflow/Scripts', sha256=?, updated_at=?, active=1
            WHERE script_id=?""", (str(path), sha256(path), now, sid))
    # No per-application code roots may be active.
    con.execute("UPDATE cad_scripts SET active=0 WHERE owner_workflow IN ('Rhino3D','SolidEdge','Cross-CAD') AND owner_folder<>'Rhino3D_to_SolidEdge_Workflow/Scripts'")
    con.execute("UPDATE cad_scripts SET script_path=?, owner_workflow='CAD Registry', owner_folder='Rhino3D_to_SolidEdge_Workflow/Scripts', runtime='Python 3 + SQLite', sha256=?, updated_at=?, active=1 WHERE script_id='cad.registry.sync'",
                (str(Path(__file__).resolve()), sha256(Path(__file__).resolve()), now))
    con.execute("UPDATE cad_workflows SET entry_script_id='workflow.run_e2e', config_path='run-local:Logs/workflow_config.json', updated_at=? WHERE workflow_id='rhino3d-to-solidedge-assembly'", (now,))
con.close()
verify = sqlite3.connect(DB)
result = {
    "active_scripts": verify.execute("SELECT COUNT(*) FROM cad_scripts WHERE active=1").fetchone()[0],
    "canonical_workflow_scripts": verify.execute("SELECT COUNT(*) FROM cad_scripts WHERE active=1 AND owner_folder='Rhino3D_to_SolidEdge_Workflow/Scripts' AND script_id<>'cad.registry.sync'").fetchone()[0],
    "active_outside_canonical": verify.execute("SELECT script_id, script_path FROM cad_scripts WHERE active=1 AND script_id<>'cad.registry.sync' AND owner_folder<>'Rhino3D_to_SolidEdge_Workflow/Scripts'").fetchall(),
    "foreign_key_violations": verify.execute("PRAGMA foreign_key_check").fetchall(),
}
verify.close()
print(json.dumps(result, indent=2))
if result["canonical_workflow_scripts"] != len(CANONICAL) or result["active_outside_canonical"] or result["foreign_key_violations"]:
    raise SystemExit("CAD registry ownership verification failed")
