# -*- coding: utf-8 -*-
"""Inventaur Inc. | Optional conservative BREP repair utility for a run-owned Rhino model copy.

This utility is deliberately excluded from the default production stage sequence.
It opens the joined_3dm from CAD_WORKFLOW_CONFIG headlessly, inspects Breps owned
directly by leaf definitions, and attempts repair/preparation on duplicated Breps.
The source is never overwritten; an accepted result is written to repaired_3dm
with a machine-readable report and independent reopen verification.

Repair attempts use the source document's ModelAbsoluteTolerance by default,
then test 2x and 5x values. brep_repair_tolerance may explicitly override the
base tolerance. All values use the source document's model units and are recorded.

Acceptance is conservative but not a full geometric-equivalence proof: it checks
validity, solid state, face/edge counts and naked edges, but does not prove bounded
surface deviation, volume preservation or manufacturability. Human inspection
and downstream STEP/native re-import are required before promotion.

This script must never be pointed at the user's original/live Rhino document.
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

SOURCE = CONFIG["joined_3dm"]
OUTPUT = CONFIG.get("repaired_3dm") or os.path.join(
    os.path.dirname(SOURCE), "repaired.3dm"
)
REPORT = os.path.join(CONFIG["reports_root"], "repair_breps_for_step_v1_report.json")
TOLERANCE = 0.005
TOLERANCE_TRIES = [TOLERANCE, TOLERANCE * 2.0, TOLERANCE * 5.0]


def sha256(path):
    """Return a streaming SHA-256 digest for the source and repaired 3DM files."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def now():
    """Return a timezone-aware local timestamp for the repair report."""
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def stats(b):
    """Collect the topology and solid-state metrics used to compare a duplicate repair candidate."""
    naked = sum(1 for e in b.Edges if e.Valence == RG.EdgeAdjacency.Naked)
    return {
        "valid": bool(b.IsValid),
        "solid": bool(b.IsSolid),
        "faces": int(b.Faces.Count),
        "edges": int(b.Edges.Count),
        "naked_edges": int(naked),
    }


def valid_log(b):
    """Return Rhino's detailed Brep validity status and diagnostic text."""
    try:
        ok, log = b.IsValidWithLog()
        return bool(ok), str(log or "")
    except Exception as exc:
        return bool(b.IsValid), "validity probe failed: " + str(exc)


def better(before, after):
    # Primary acceptance: valid is non-negotiable.
    """Compare a candidate against the original using the script's conservative topology acceptance rules."""
    if after["valid"] and not before["valid"]:
        return True
    if not after["valid"]:
        return False
    # If both are valid, do not accept geometry loss. Prefer fewer naked edges.
    if after["faces"] < before["faces"]:
        return False
    if after["naked_edges"] < before["naked_edges"]:
        return True
    # A valid unchanged result is still acceptable as normalization.
    return before == after


def repair_one(original):
    """Try the configured repair/preparation tolerances on a duplicate and retain the original when no candidate is accepted."""
    before = stats(original)
    best = original.Duplicate()
    actions = []

    for tol in TOLERANCE_TRIES:
        candidate = original.Duplicate()
        try:
            repaired = bool(candidate.Repair(tol))
            actions.append({"operation": "Repair", "tolerance": tol, "returned": repaired})
        except Exception as exc:
            actions.append({"operation": "Repair", "tolerance": tol, "error": str(exc)})

        try:
            prepared = bool(candidate.PrepareForBooleans(tol))
            actions.append({
                "operation": "PrepareForBooleans",
                "tolerance": tol,
                "returned": prepared,
            })
        except Exception as exc:
            actions.append({
                "operation": "PrepareForBooleans",
                "tolerance": tol,
                "error": str(exc),
            })

        after = stats(candidate)
        if better(before, after):
            best = candidate
            return best, {
                "status": "REPAIRED",
                "before": before,
                "after": after,
                "actions": actions,
                "validity_log_after": valid_log(candidate)[1],
            }

    final = stats(best)
    return original.Duplicate(), {
        "status": "UNCHANGED_OR_UNRESOLVED",
        "before": before,
        "after": final,
        "actions": actions,
        "validity_log_after": valid_log(best)[1],
    }


def run():
    """Inspect leaf-definition Breps, repair only duplicate candidates, and write a separate output model/report."""
    if not os.path.isfile(SOURCE):
        raise IOError("SOURCE missing: " + SOURCE)
    if os.path.exists(OUTPUT):
        raise IOError("Refusing to overwrite existing output: " + OUTPUT)

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)

    source_hash = sha256(SOURCE)
    doc = Rhino.RhinoDoc.OpenHeadless(SOURCE)
    if doc is None:
        raise RuntimeError("RhinoDoc.OpenHeadless failed")

    # Repair tolerances are model-unit values. Default to document tolerance;
    # an explicit run-config override must be deliberate.
    global TOLERANCE, TOLERANCE_TRIES
    TOLERANCE = float(CONFIG.get("brep_repair_tolerance") or doc.ModelAbsoluteTolerance)
    if TOLERANCE <= 0:
        raise ValueError("BREP repair tolerance must be positive")
    TOLERANCE_TRIES = [TOLERANCE, TOLERANCE * 2.0, TOLERANCE * 5.0]

    report = {
        "schema_version": 1,
        "script": "inventaur_repair_breps_for_step_v1.py",
        "stage": "RHINO_STAGE_2_BREP_REPAIR",
        "status": "RUNNING",
        "source": SOURCE,
        "source_sha256": source_hash,
        "output": OUTPUT,
        "tolerance": TOLERANCE,
        "tolerance_tries": TOLERANCE_TRIES,
        "model_units": str(doc.ModelUnitSystem),
        "model_absolute_tolerance": float(doc.ModelAbsoluteTolerance),
        "started_at": now(),
        "definitions": [],
        "repaired_brep_count": 0,
        "unchanged_brep_count": 0,
        "unresolved_brep_count": 0,
    }

    try:
        for i in range(doc.InstanceDefinitions.Count):
            idef = doc.InstanceDefinitions[i]
            if not idef or idef.IsDeleted:
                continue

            has_nested = False
            for oid in idef.GetObjectIds():
                ro = doc.Objects.FindId(oid)
                if ro and isinstance(ro.Geometry, RG.InstanceReferenceGeometry):
                    has_nested = True
                    break
            if has_nested:
                continue

            definition_result = {
                "definition_guid": str(idef.Id),
                "name": idef.Name,
                "breps": [],
            }
            changed = False

            for oid in idef.GetObjectIds():
                ro = doc.Objects.FindId(oid)
                if not ro or not isinstance(ro.Geometry, RG.Brep):
                    continue

                original = ro.Geometry.Duplicate()
                repaired, result = repair_one(original)
                result["object_id"] = str(oid)
                definition_result["breps"].append(result)

                if result["status"] == "REPAIRED":
                    # Replace the geometry in the block definition while preserving
                    # the original object attributes and definition hierarchy.
                    # ModifyGeometry requires all definition members, so rebuild the
                    # definition member list in-place below.
                    changed = True
                    result["_replacement_geometry"] = repaired
                    report["repaired_brep_count"] += 1
                else:
                    report["unchanged_brep_count"] += 1
                    if not result["after"]["valid"]:
                        report["unresolved_brep_count"] += 1

            if changed:
                geometries = []
                attributes = []
                replacement_by_id = {
                    x["object_id"]: x["_replacement_geometry"]
                    for x in definition_result["breps"]
                    if x.get("_replacement_geometry") is not None
                }
                for oid in idef.GetObjectIds():
                    ro = doc.Objects.FindId(oid)
                    if not ro:
                        continue
                    geometries.append(replacement_by_id.get(str(oid), ro.Geometry.Duplicate()))
                    attributes.append(ro.Attributes.Duplicate())
                if not doc.InstanceDefinitions.ModifyGeometry(idef.Index, geometries, attributes):
                    raise RuntimeError("ModifyGeometry failed for definition " + idef.Name)

            # Remove internal geometry objects from the report before serialization.
            for item in definition_result["breps"]:
                item.pop("_replacement_geometry", None)

            definition_result["status"] = "REPAIRED" if changed else "UNCHANGED"
            report["definitions"].append(definition_result)

        if not doc.SaveAs(OUTPUT):
            raise RuntimeError("RhinoDoc.SaveAs failed")
    finally:
        try:
            doc.Dispose()
        except Exception:
            pass

    # Independent reopen verification.
    check = Rhino.RhinoDoc.OpenHeadless(OUTPUT)
    if check is None:
        raise RuntimeError("Repaired output reopen failed")
    try:
        invalid_after = []
        for i in range(check.InstanceDefinitions.Count):
            idef = check.InstanceDefinitions[i]
            if not idef or idef.IsDeleted:
                continue
            for oid in idef.GetObjectIds():
                ro = check.Objects.FindId(oid)
                if ro and isinstance(ro.Geometry, RG.Brep) and not ro.Geometry.IsValid:
                    invalid_after.append({
                        "definition": idef.Name,
                        "object_id": str(oid),
                        "log": valid_log(ro.Geometry)[1],
                    })
        report["verification"] = {
            "reopened": True,
            "invalid_breps_after_reopen": invalid_after,
            "output_exists": os.path.isfile(OUTPUT),
        }
    finally:
        try:
            check.Dispose()
        except Exception:
            pass

    report.update({
        "status": "VERIFIED" if not report["verification"]["invalid_breps_after_reopen"] else "VERIFIED_WITH_UNRESOLVED",
        "finished_at": now(),
        "output_sha256": sha256(OUTPUT),
        "source_unchanged": sha256(SOURCE) == source_hash,
    })

    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(json.dumps({
        "status": report["status"],
        "repaired_brep_count": report["repaired_brep_count"],
        "unchanged_brep_count": report["unchanged_brep_count"],
        "unresolved_brep_count": report["unresolved_brep_count"],
        "output": OUTPUT,
    }, indent=2))


if __name__ == "__main__":
    run()
