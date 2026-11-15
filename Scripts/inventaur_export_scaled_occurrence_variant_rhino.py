# -*- coding: utf-8 -*-
"""Inventaur Inc. | Export and independently verify one baked-scale Rhino occurrence variant.

The source definition remains untouched. Only the non-unit scale is baked into
duplicate geometry; the Solid Edge assembly builder applies the rigid/reflection
rotation+translation matrix to this dedicated native part.
"""
from __future__ import annotations
__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"

import os
import json
from pathlib import Path
import hashlib
import datetime
import System
import Rhino
import Rhino.Geometry as RG
import Rhino.FileIO as RF


_CONFIG_ENV = os.environ.get("CAD_WORKFLOW_CONFIG")
if not _CONFIG_ENV:
    raise RuntimeError("CAD_WORKFLOW_CONFIG is required; refusing shared active_run.json fallback")
CONFIG_PATH = Path(_CONFIG_ENV).resolve()
if not CONFIG_PATH.is_file():
    raise FileNotFoundError("Run-scoped CAD workflow config is missing: " + str(CONFIG_PATH))
with CONFIG_PATH.open("r", encoding="utf-8-sig") as _config_stream:
    CONFIG = json.load(_config_stream)
_STAGE_PAYLOAD=json.loads(os.environ.get("CAD_WORKFLOW_STAGE_PAYLOAD","{}"))
VARIANT=_STAGE_PAYLOAD.get("active_scaled_occurrence")
if not isinstance(VARIANT,dict):
    raise RuntimeError("CAD_WORKFLOW_STAGE_PAYLOAD.active_scaled_occurrence is required")
SOURCE = CONFIG["colorized_3dm"]
DEFINITION_NAME = VARIANT["definition_name"]
INSTANCE_GUID = VARIANT["instance_guid"]
SCALE = tuple(float(x) for x in VARIANT["axis_scales"])
OUTPUT = os.path.join(CONFIG["step_root"], VARIANT["step_file"])
STAGING = os.path.splitext(OUTPUT)[0] + ".__staging__.stp"
REPORT = os.path.join(
    CONFIG["reports_root"],
    "scaled_occurrence_variant_" + INSTANCE_GUID.replace("-", "")[:8] + ".json",
)
BBOX_TOLERANCE_MM = 0.02
VOLUME_RELATIVE_TOLERANCE = 1e-6


def sha256(path: str) -> str:
    """Calculate a streaming SHA-256 digest for an input or output file."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bbox_flat(geometry) -> list[float]:
    """Flatten a Rhino bounding box into a stable JSON-friendly coordinate list."""
    bounds = geometry.GetBoundingBox(True)
    return [
        float(bounds.Min.X), float(bounds.Min.Y), float(bounds.Min.Z),
        float(bounds.Max.X), float(bounds.Max.Y), float(bounds.Max.Z),
    ]


def brep_for_geometry(geometry):
    """Return a temporary Brep for valid solid/surface source geometry."""
    if isinstance(geometry, RG.Brep):
        return geometry
    if isinstance(geometry, RG.Extrusion):
        return geometry.ToBrep(True)
    if isinstance(geometry, RG.Surface):
        return geometry.ToBrep()
    return None


def geometry_metrics(geometry, label: str) -> dict:
    """Collect geometry counts and geometric measurements for the selected definition members."""
    brep = brep_for_geometry(geometry)
    if brep is None:
        return {"label": label, "has_brep": False}
    volume_properties = RG.VolumeMassProperties.Compute(brep)
    area_properties = RG.AreaMassProperties.Compute(brep)
    return {
        "label": label,
        "has_brep": True,
        "valid": bool(brep.IsValid),
        "solid": bool(brep.IsSolid),
        "faces": int(brep.Faces.Count),
        "edges": int(brep.Edges.Count),
        "naked_edges": sum(1 for edge in brep.Edges if str(edge.Valence).endswith("Naked")),
        "volume_mm3": float(volume_properties.Volume) if volume_properties else 0.0,
        "area_mm2": float(area_properties.Area) if area_properties else 0.0,
        "bbox_mm": bbox_flat(brep),
    }


def combine_bboxes(rows: list[dict]) -> list[float] | None:
    """Combine valid bounding boxes into one world-space extent."""
    boxes = [row["bbox_mm"] for row in rows if row.get("bbox_mm") and len(row["bbox_mm"]) == 6]
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes), min(box[1] for box in boxes), min(box[2] for box in boxes),
        max(box[3] for box in boxes), max(box[4] for box in boxes), max(box[5] for box in boxes),
    ]


def atomic_json(path: str, data: dict) -> None:
    """Write a stage report through a temporary file and atomic replace."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
    os.replace(temporary, path)


def read_step_metrics(step_path: str) -> list[dict]:
    """Import the staged STEP into a separate headless Rhino document and measure its bodies."""
    read_doc = Rhino.RhinoDoc.CreateHeadless(None)
    if read_doc is None:
        raise RuntimeError("Rhino could not create the STEP readback document")
    try:
        options = RF.FileStpReadOptions()
        if not RF.FileStp.Read(step_path, read_doc, options):
            raise RuntimeError("RhinoCommon STEP readback returned False")
        rows = []
        for obj in read_doc.Objects:
            if obj is None or obj.Geometry is None:
                continue
            geometry = obj.Geometry
            row = geometry_metrics(geometry, str(obj.Id))
            if row.get("has_brep"):
                rows.append(row)
        return rows
    finally:
        read_doc.Dispose()


def validate_readback(source_rows: list[dict], native_rows: list[dict]) -> dict:
    """Reopen the exported variant and compare its geometry signature with the expected source payload."""
    source_bodies = [row for row in source_rows if row.get("has_brep")]
    source_solids = [row for row in source_bodies if row.get("solid")]
    native_solids = [row for row in native_rows if row.get("solid")]
    hard_failures = []
    if len(native_rows) != len(source_bodies):
        hard_failures.append(
            f"body count mismatch: source={len(source_bodies)} STEP={len(native_rows)}"
        )
    if len(native_solids) != len(source_solids):
        hard_failures.append(
            f"solid count mismatch: source={len(source_solids)} STEP={len(native_solids)}"
        )
    if not source_solids or not native_solids:
        hard_failures.append("scaled variant has no source or STEP solid body")

    source_faces = sum(int(row.get("faces") or 0) for row in source_bodies)
    native_faces = sum(int(row.get("faces") or 0) for row in native_rows)
    source_volume = sum(float(row.get("volume_mm3") or 0.0) for row in source_solids)
    native_volume = sum(float(row.get("volume_mm3") or 0.0) for row in native_solids)
    source_bbox = combine_bboxes(source_bodies)
    native_bbox = combine_bboxes(native_rows)
    bbox_error = None
    volume_error = None

    if source_faces != native_faces:
        hard_failures.append(f"face count mismatch: source={source_faces} STEP={native_faces}")
    if source_bbox and native_bbox:
        bbox_error = max(abs(a - b) for a, b in zip(source_bbox, native_bbox))
        if bbox_error > BBOX_TOLERANCE_MM:
            hard_failures.append(
                f"bbox mismatch: max error={bbox_error:.9f} mm "
                f"(tolerance={BBOX_TOLERANCE_MM:.9f} mm)"
            )
    else:
        hard_failures.append("source or STEP bounding box unavailable")

    if source_volume > 0:
        volume_error = abs(native_volume - source_volume) / source_volume
        if volume_error > VOLUME_RELATIVE_TOLERANCE:
            hard_failures.append(
                f"volume mismatch: relative error={volume_error:.12g} "
                f"(tolerance={VOLUME_RELATIVE_TOLERANCE:.12g})"
            )
    else:
        hard_failures.append("source solid volume is not positive")

    return {
        "passed": not hard_failures,
        "hard_failures": hard_failures,
        "source_body_count": len(source_bodies),
        "readback_brep_body_count": len(native_rows),
        "source_solid_count": len(source_solids),
        "readback_solid_count": len(native_solids),
        "source_brep_face_count": source_faces,
        "readback_brep_face_count": native_faces,
        "readback_volume_mm3": native_volume,
        "source_volume_mm3": source_volume,
        "volume_relative_error": volume_error,
        "source_bbox_mm": source_bbox,
        "readback_bbox_mm": native_bbox,
        "max_bbox_error_mm": bbox_error,
        "bbox_tolerance_mm": BBOX_TOLERANCE_MM,
        "volume_relative_tolerance": VOLUME_RELATIVE_TOLERANCE,
    }


def run() -> dict:
    """Create the explicit baked-scale occurrence variant, export it, and write source-bound verification evidence."""
    if not os.path.isfile(SOURCE):
        raise FileNotFoundError(SOURCE)
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    if os.path.exists(STAGING):
        os.remove(STAGING)

    source_doc = Rhino.RhinoDoc.OpenHeadless(SOURCE)
    if source_doc is None:
        raise RuntimeError("Rhino OpenHeadless failed for scaled variant source")

    source_geometry = []
    non_brep_geometry = []
    definition_guid = None
    out_doc = None
    try:
        definition = source_doc.InstanceDefinitions.Find(DEFINITION_NAME)
        if definition is None:
            raise RuntimeError("Definition not found: " + DEFINITION_NAME)
        definition_guid = str(definition.Id)
        out_doc = Rhino.RhinoDoc.CreateHeadless(None)
        if out_doc is None:
            raise RuntimeError("Rhino CreateHeadless failed for scaled variant export")

        scale_transform = RG.Transform.Scale(
            RG.Plane.WorldXY, SCALE[0], SCALE[1], SCALE[2]
        )
        for obj_id in definition.GetObjectIds():
            source_object = source_doc.Objects.FindId(obj_id)
            if source_object is None or isinstance(source_object.Geometry, RG.InstanceReferenceGeometry):
                continue
            source_geometry_object = source_object.Geometry
            if not isinstance(
                source_geometry_object,
                (RG.Brep, RG.Extrusion, RG.Surface, RG.Mesh, RG.SubD, RG.Curve),
            ):
                continue
            geometry = source_geometry_object.Duplicate()
            if not geometry.Transform(scale_transform):
                raise RuntimeError("Could not apply baked scale to " + str(obj_id))
            metrics = geometry_metrics(geometry, str(obj_id))
            metrics["source_object_guid"] = str(obj_id)
            metrics["source_geometry_type"] = type(source_geometry_object).__name__
            source_geometry.append(metrics)
            if metrics.get("has_brep"):
                if not metrics.get("valid"):
                    raise RuntimeError("Scaled source Brep is invalid: " + json.dumps(metrics))
                if metrics.get("solid") and metrics.get("volume_mm3", 0.0) <= 0:
                    raise RuntimeError("Scaled source solid has zero volume: " + json.dumps(metrics))
            else:
                non_brep_geometry.append({"source_object_guid": str(obj_id), "geometry_type": type(geometry).__name__})
            attributes = source_object.Attributes.Duplicate()
            if out_doc.Objects.Add(geometry, attributes) == System.Guid.Empty:
                raise RuntimeError("Failed to add scaled geometry " + str(obj_id))

        source_bodies = [row for row in source_geometry if row.get("has_brep")]
        if not source_bodies:
            raise RuntimeError("No Brep/Extrusion/Surface source bodies found in " + DEFINITION_NAME)
        write_options = RF.FileStpWriteOptions()
        write_options.ExportBlack = False
        if not RF.FileStp.Write(STAGING, out_doc, write_options):
            raise RuntimeError("RhinoCommon STEP variant write failed")

    finally:
        if out_doc is not None:
            out_doc.Dispose()
        source_doc.Dispose()

    native_rows = read_step_metrics(STAGING)
    validation = validate_readback(source_geometry, native_rows)
    if not validation["passed"]:
        failed = {
            "schema_version": 2,
            "status": "FAILED",
            "source": SOURCE,
            "source_sha256": sha256(SOURCE),
            "definition_name": DEFINITION_NAME,
            "instance_guid": INSTANCE_GUID,
            "baked_scale": list(SCALE),
            "staging_output": STAGING,
            "source_geometry": source_geometry,
            "step_readback": native_rows,
            "validation": validation,
            "created_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        atomic_json(REPORT, failed)
        raise RuntimeError("Scaled occurrence STEP failed source/readback validation: " + json.dumps(validation))

    # Preserve the previous output before replacing it; only verified staging is promoted.
    previous_output = None
    if os.path.isfile(OUTPUT):
        old_hash = sha256(OUTPUT)
        quarantine = os.path.join(CONFIG["logs_root"], "Quarantine")
        os.makedirs(quarantine, exist_ok=True)
        previous_output = os.path.join(
            quarantine,
            os.path.basename(OUTPUT).replace(".stp", "_pre_promotion_" + old_hash[:12] + ".stp"),
        )
        if not os.path.exists(previous_output):
            import shutil
            shutil.copy2(OUTPUT, previous_output)
        if sha256(previous_output) != old_hash:
            raise RuntimeError("Previous STEP quarantine copy hash mismatch")
    os.replace(STAGING, OUTPUT)
    output_hash = sha256(OUTPUT)

    report = {
        "schema_version": 2,
        "status": "VERIFIED",
        "source": SOURCE,
        "source_sha256": sha256(SOURCE),
        "definition_name": DEFINITION_NAME,
        "definition_guid": definition_guid,
        "instance_guid": INSTANCE_GUID,
        "baked_scale": list(SCALE),
        "output": OUTPUT,
        "output_sha256": output_hash,
        "direct_geometry_object_count": len(source_geometry),
        "direct_brep_body_count_after_scale": len([row for row in source_geometry if row.get("has_brep")]),
        "non_brep_geometry": non_brep_geometry,
        "source_geometry": source_geometry,
        "step_readback": native_rows,
        "readback_brep_body_count": validation["readback_brep_body_count"],
        "readback_solid_count": validation["readback_solid_count"],
        "readback_brep_face_count": validation["readback_brep_face_count"],
        "readback_volume_mm3": validation["readback_volume_mm3"],
        "readback_bbox_mm": validation["readback_bbox_mm"],
        "body_audits": [
            {
                "source_object_guid": source_row.get("source_object_guid"),
                "final_solid": bool(source_row.get("solid")),
                "final_faces": int(source_row.get("faces") or 0),
                "source_bbox_mm": source_row.get("bbox_mm"),
                "export_bbox_mm": (
                    native_rows[index].get("bbox_mm")
                    if index < len(native_rows) else None
                ),
            }
            for index, source_row in enumerate([row for row in source_geometry if row.get("has_brep")])
        ],
        "validation": validation,
        "previous_output_quarantine": previous_output,
        "placement_policy": "variant geometry carries non-unit scale; Solid Edge occurrence receives rigid rotation/reflection+translation only",
        "created_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    atomic_json(REPORT, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


if __name__ == "__main__":
    run()
