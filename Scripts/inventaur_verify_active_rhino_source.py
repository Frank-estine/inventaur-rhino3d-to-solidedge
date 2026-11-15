# -*- coding: utf-8 -*-
"""Inventaur Inc. | Read-only preflight: prove the live Rhino document is the selected 3DM source.

Runs only inside the connected Rhino Python runtime. It never saves, switches,
or edits the active Rhino document.
"""

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"

import Rhino, os, json, hashlib, datetime

def sha256(path):
    """Return a streaming SHA-256 digest without modifying the source file."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

config_path = os.environ["CAD_WORKFLOW_CONFIG"]
with open(config_path, "r", encoding="utf-8-sig") as stream:
    config = json.load(stream)
doc = globals().get("__rhino_doc__") or Rhino.RhinoDoc.ActiveDoc
if doc is None:
    raise RuntimeError("No active Rhino document is available")
active_path = os.path.normcase(os.path.realpath(str(doc.Path or "")))
expected_path = os.path.normcase(os.path.realpath(str(config["source_original_path"])))
snapshot_path = str(config["source_3dm"])
if not active_path or active_path != expected_path:
    raise RuntimeError("Active Rhino document path does not match selected source: " +
                       json.dumps({"active": doc.Path, "expected": config["source_original_path"]}))
expected_runtime = config.get("rhino_preflight", {}).get("runtime_serial_number")
actual_runtime = int(doc.RuntimeSerialNumber)
if expected_runtime is not None and int(expected_runtime) != actual_runtime:
    raise RuntimeError("The attached Rhino document runtime changed after the immutable snapshot was captured")
if not os.path.isfile(snapshot_path):
    raise FileNotFoundError("Immutable Rhino source snapshot is missing: " + snapshot_path)
snapshot_hash = sha256(snapshot_path)
if snapshot_hash != config.get("source_sha256"):
    raise RuntimeError("Immutable Rhino snapshot hash differs from the run config: " +
                       json.dumps({"snapshot": snapshot_hash, "config": config.get("source_sha256")}))
report = {
    "status": "VERIFIED",
    "checked_at": datetime.datetime.now().astimezone().isoformat(),
    "active_document_path": str(doc.Path),
    "runtime_serial_number": actual_runtime,
    "source_sha256": snapshot_hash,
    "snapshot_path": snapshot_path,
    "snapshot_sha256": snapshot_hash,
    "saved_file_sha256_at_capture": config.get("source_disk_sha256_at_capture"),
    "live_document_modified_at_capture": config.get("rhino_document_modified_at_capture"),
    "live_document_modified_at_preflight": bool(doc.Modified),
    "live_document_modified_since_capture": (
        bool(doc.Modified) != bool(config.get("rhino_document_modified_at_capture", False))
    ),
    "capture_mode": config.get("source_snapshot_mode"),
    "document_units": str(doc.ModelUnitSystem),
    "absolute_tolerance": float(doc.ModelAbsoluteTolerance),
}
os.makedirs(config["reports_root"], exist_ok=True)
report_path = os.path.join(config["reports_root"], "rhino_source_preflight.json")
with open(report_path, "w", encoding="utf-8") as stream:
    json.dump(report, stream, indent=2, ensure_ascii=False)
print("RHINO_SOURCE_PREFLIGHT " + json.dumps(report, ensure_ascii=False))
