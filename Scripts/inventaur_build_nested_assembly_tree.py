"""Inventaur Inc. | Build the Rhino block-definition hierarchy as reusable native Solid Edge assemblies.

Rules:
- One Rhino definition name maps to one native .par or .asm document.
- Every Rhino instance becomes a distinct occurrence of that shared document.
- Definition geometry remains local; the Rhino instance transform is applied at placement.
- Reflection is supported by AddWithMatrix. Non-unit scale/shear is not silently approximated.
- A part is placeable only when its native import was explicitly verified.
- Every assembly is saved, closed, reopened from disk, and queried before it is marked verified.
- Progress and heartbeat are atomically written after each tool call for external supervision.
"""
from __future__ import annotations
__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"
import json, math, os, sys, time, traceback, unicodedata, hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_CONFIG_ENV=os.environ.get("CAD_WORKFLOW_CONFIG")
if not _CONFIG_ENV:
    raise RuntimeError("CAD_WORKFLOW_CONFIG is required; refusing shared active_run.json fallback")
CONFIG_PATH=os.path.abspath(_CONFIG_ENV)
if not os.path.isfile(CONFIG_PATH):
    raise FileNotFoundError("Run-scoped CAD workflow config is missing: "+CONFIG_PATH)
with open(CONFIG_PATH,"r",encoding="utf-8-sig") as _config_stream:
    CONFIG=json.load(_config_stream)
PIPE = Path(CONFIG["pipeline_root"])  # final output root
REPORTS = Path(CONFIG["reports_root"])
LOGS = Path(CONFIG["logs_root"])
MCP_ROOT = Path(CONFIG["solid_edge_mcp_root"])
MANIFEST_FILE = REPORTS / "name_identity_manifest.json"
INVENTORY_FILE = REPORTS / "rhino_active_inventory.json"
IMPORT_FILE = REPORTS / "native_part_import_e2e.json"
REPORT_FILE = REPORTS / "assembly_build_e2e.json"
LOG_FILE = LOGS / "assembly_build.log"
ROOT_ASM = Path(CONFIG.get("root_assembly_path", PIPE / "Assemblies" / "Root.asm"))

PIPE.joinpath("Assemblies").mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(MCP_ROOT))
import inventaur_bridge_client as bridge

report = {
    "schema_version": 1,
    "status": "STARTING",
    "source_sha256": None,
    "started_at": datetime.now().astimezone().isoformat(),
    "heartbeat_at": datetime.now().astimezone().isoformat(),
    "current_document": None,
    "current_action": "load inputs",
    "expected_nested_assemblies": 0,
    "completed_nested_assemblies": 0,
    "partial_nested_assemblies": 0,
    "failed_nested_assemblies": 0,
    "assemblies": [],
    "root": None,
    "errors": [],
}


def write_report():
    """Atomically update the supervision checkpoint without exposing half-written JSON."""
    report["heartbeat_at"] = datetime.now().astimezone().isoformat()
    tmp = REPORT_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, REPORT_FILE)


def log(message: str):
    """Append a timestamped progress line to the assembly log, flush it, print it and persist the current report. This is local I/O used by the external supervisor; it does not advance a document state by itself."""
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"{stamp} {message}"
    with LOG_FILE.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
        stream.flush()
    print(line, flush=True)
    write_report()


def set_state(document: str | None, action: str):
    """Update the report fields identifying the current native document and action, then persist the report. The state is an operator/supervisor breadcrumb, not proof that the Solid Edge action succeeded."""
    report["current_document"] = document
    report["current_action"] = action
    write_report()


def call_tool(access: str, tool: str, args: dict, document: str | None = None):
    """Call one bounded bridge operation and write a visible before/after heartbeat."""
    set_state(document, tool + " (in progress)")
    result = bridge.write_tool(tool, args) if access == "write" else bridge.read_tool(tool, args)
    if not isinstance(result, dict):
        raise RuntimeError(f"{tool} returned a non-object result: {result!r}")
    if result.get("status") not in ("ok", "dry-run"):
        raise RuntimeError(f"{tool} failed: {json.dumps(result, ensure_ascii=False)[:3000]}")
    set_state(document, tool + " (returned " + str(result.get("status")) + ")")
    return result


def must(result: dict, label: str, allowed=("ok",)):
    """Validate that a bridge response is a dictionary whose status is in the caller-supplied allowed set. Return the original response on success; otherwise raise RuntimeError containing a bounded JSON rendering so an unexpected COM/bridge result cannot be treated as verified."""
    if not isinstance(result, dict) or result.get("status") not in allowed:
        raise RuntimeError(f"{label}: {json.dumps(result, ensure_ascii=False)[:3000]}")
    return result


def name_key(value: str) -> str:
    """Match the source manifest's NFKC + trim + collapsed whitespace + casefold rule."""
    return " ".join(unicodedata.normalize("NFKC", value or "").strip().split()).casefold()


def path_key(value: str | Path) -> str:
    """Normalize a path to an absolute, case-folded platform key for stable comparison of native document paths across manifest and filesystem representations."""
    return os.path.normcase(os.path.abspath(str(value))).casefold()


def transform_matrix(transform: dict) -> list[float]:
    """Convert Rhino's row/column matrix to Solid Edge's 16-value matrix.

    Solid Edge's matrix API stores translation at indices 12..14 (column-major
    flattening). Rhino inventory stores translation in the last column. Rhino
    document units are millimetres; the Solid Edge bridge matrix uses metres.
    Only rigid/reflected transforms are supported. Non-unit scale or shear is
    refused because the tested Solid Edge API silently normalizes scale away.
    """
    rows = transform.get("matrix")
    if not isinstance(rows, list) or len(rows) != 4 or any(not isinstance(row, list) or len(row) != 4 for row in rows):
        raise ValueError("missing or invalid Rhino 4x4 transform")
    if transform.get("singular") or transform.get("has_shear"):
        raise ValueError("singular or sheared transform cannot be placed safely")
    scales = transform.get("axis_scales", [1.0, 1.0, 1.0])
    if len(scales) != 3 or any(abs(float(scale) - 1.0) > 1e-7 for scale in scales):
        raise ValueError("non-unit scale requires a baked geometry variant; occurrence scaling is not supported")
    m = [[float(rows[r][c]) for c in range(4)] for r in range(4)]
    if any(not math.isfinite(value) for row in m for value in row):
        raise ValueError("transform contains a non-finite value")
    m[0][3] /= 1000.0
    m[1][3] /= 1000.0
    m[2][3] /= 1000.0
    # Flatten by columns so that translation occupies Solid Edge matrix [12..14].
    return [m[r][c] for c in range(4) for r in range(4)]


def rigid_transform_matrix(transform: dict) -> list[float]:
    """Strip non-unit axis scale after it has been baked into a variant part."""
    rows = transform.get("matrix")
    if not isinstance(rows, list) or len(rows) != 4:
        raise ValueError("invalid scaled occurrence matrix")
    m = [[float(rows[r][c]) for c in range(4)] for r in range(4)]
    for r in range(3):
        n = math.sqrt(sum(m[r][c] * m[r][c] for c in range(3)))
        if n <= 1e-12:
            raise ValueError("scaled occurrence contains a zero axis")
        for c in range(3):
            m[r][c] /= n
    # Row normalization removes positive axis magnitudes only. Never flip an
    # axis here: doing so changes a reflected placement (determinant < 0) into
    # a non-reflected rotation and mirrors the baked geometry a second time.
    det = (m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1])
           -m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0])
           +m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]))
    if abs(det) <= 1e-10:
        raise ValueError("normalized occurrence transform is singular")
    expected_reflection = bool(transform.get("reflection", float(transform.get("determinant", det)) < 0))
    if (det < 0) != expected_reflection:
        raise ValueError("scaled rigid transform changed reflection parity")
    m[0][3] /= 1000.0; m[1][3] /= 1000.0; m[2][3] /= 1000.0
    return [m[r][c] for c in range(4) for r in range(4)]

def identity_matrix() -> list[float]:
    """Return the row-major 4×4 identity transform used when a Rhino instance has no explicit transform."""
    return [1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0]


def matrix_error(actual, expected) -> float:
    """Return the maximum element-wise absolute difference between two 16-value matrices. Malformed/non-16-value actual matrices return infinity so they cannot pass tolerance checks."""
    if not isinstance(actual, list) or len(actual) != 16:
        return float("inf")
    return max(abs(float(a) - float(e)) for a, e in zip(actual, expected))


def match_expected(occurrences: list, expected: list, tolerance=1e-7):
    """Multiset reconcile by exact referenced document and full placement matrix."""
    remaining = list(occurrences)
    matches, missing = [], []
    for item in expected:
        wanted_path = path_key(item["file"])
        best_index, best_error = None, float("inf")
        for index, actual in enumerate(remaining):
            if path_key(actual.get("file", "")) != wanted_path:
                continue
            error = matrix_error(actual.get("matrix"), item["matrix"])
            if error < best_error:
                best_index, best_error = index, error
        if best_index is None or best_error > tolerance:
            missing.append({**item, "best_matrix_error": best_error if best_index is not None else None})
        else:
            actual = remaining.pop(best_index)
            matches.append({"file": item["file"], "matrix_error": best_error,
                            "visible": bool(actual.get("visible", False)),
                            "occurrence_name": actual.get("name")})
    extras = [{"file": x.get("file"), "name": x.get("name"), "matrix": x.get("matrix")} for x in remaining]
    return matches, missing, extras


def file_sha256(path: Path) -> str:
    """Stream the SHA-256 of one native CAD artifact without loading it all into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_native_import_outputs(manifest: dict, imported: dict, scaled_map: dict, pipeline_root: Path):
    """Accept only import rows whose status, expected manifest path, file size and native SHA-256 all reconcile. Also validate any supplied STEP/SAT source hash and reopened topology evidence. Failed/unmatched rows remain explicit evidence and are never placeable."""
    accepted_statuses = {
        "imported_verified", "reused_verified",
        "imported_verified_with_warnings", "reused_verified_with_warnings",
    }
    root = Path(pipeline_root).resolve()
    expected_paths = set()
    for document in manifest.get("definition_documents", []):
        if document.get("document_type") == "PAR" and document.get("relative_output_path"):
            expected_paths.add(path_key(root / Path(document["relative_output_path"])))
        companion = document.get("local_geometry_companion_par")
        if companion:
            expected_paths.add(path_key(root / Path(companion)))
    for variant in scaled_map.get("variants", []):
        relative = variant.get("relative")
        if not relative and variant.get("par_file"):
            relative = "Parts/" + str(variant["par_file"])
        if relative:
            expected_paths.add(path_key(root / Path(relative)))
    verified_paths, rejected = set(), []
    for row in imported.get("results", []):
        reason = None
        output_value = row.get("output")
        if row.get("status") not in accepted_statuses:
            reason = "IMPORT_STATUS_NOT_VERIFIED"
        elif not output_value:
            reason = "NATIVE_OUTPUT_PATH_MISSING"
        else:
            output = Path(output_value).resolve()
            try:
                output.relative_to(root)
            except ValueError:
                reason = "NATIVE_OUTPUT_OUTSIDE_PIPELINE_ROOT"
            output_key = path_key(output)
            if reason is None and output_key not in expected_paths:
                reason = "NATIVE_OUTPUT_NOT_IN_SOURCE_MANIFEST"
            if reason is None and (not output.is_file() or output.stat().st_size <= 0):
                reason = "NATIVE_OUTPUT_MISSING_OR_EMPTY"
            if reason is None and row.get("native_bytes") is not None and int(row["native_bytes"]) != output.stat().st_size:
                reason = "NATIVE_OUTPUT_SIZE_MISMATCH"
            if reason is None and (not row.get("native_sha256") or file_sha256(output) != row.get("native_sha256")):
                reason = "NATIVE_OUTPUT_SHA256_MISMATCH"
            step_value = row.get("step")
            step_hash = row.get("step_sha256")
            if reason is None and step_value and step_hash:
                step = Path(step_value).resolve()
                if not step.is_file() or file_sha256(step) != step_hash:
                    reason = "SOURCE_STEP_HASH_MISMATCH"
            sat_value = row.get("source_sat")
            sat_hash = row.get("source_sat_sha256")
            if reason is None and sat_value and sat_hash:
                sat = Path(sat_value).resolve()
                if not sat.is_file() or file_sha256(sat) != sat_hash:
                    reason = "SOURCE_SAT_HASH_MISMATCH"
            topology = row.get("topology") or row.get("imported_topology")
            if reason is None and isinstance(topology, dict):
                if int(topology.get("body_count", topology.get("models_count", 0)) or 0) <= 0 and row.get("native_import_contract") != "SAVE_REOPEN":
                    reason = "NATIVE_DOCUMENT_HAS_NO_REOPENED_BODY"
            cleanup = row.get("close_after_save") or row.get("document_cleanup")
            if reason is None and isinstance(cleanup, dict) and cleanup.get("status") not in ("ok", "VERIFIED"):
                reason = "NATIVE_DOCUMENT_CLOSE_NOT_VERIFIED"
            if reason is None and row.get("reopen_verified") is False:
                reason = "NATIVE_REOPEN_NOT_VERIFIED"
            if reason is None:
                verified_paths.add(output_key)
        if reason:
            rejected.append({
                "document_key": row.get("document_key"), "output": output_value,
                "status": row.get("status"), "reason": reason,
            })
    return verified_paths, {
        "expected_native_output_path_count": len(expected_paths),
        "reported_result_count": len(imported.get("results", [])),
        "verified_native_output_count": len(verified_paths),
        "rejected_result_count": len(rejected),
        "rejected_results": rejected,
        "partial_import_allowed": bool(verified_paths) and imported.get("status") == "INCOMPLETE",
        "source_sha256": imported.get("source_sha256"),
        "document_cleanup": imported.get("document_cleanup"),
    }


def load_inputs():
    """Read source manifest, inventory and native-import evidence; permit a partial import only when batch-level document cleanup is verified and each placed PAR independently matches its manifest path, bytes and SHA-256. Also verify the source identity and acyclic block graph."""
    for file in (MANIFEST_FILE, INVENTORY_FILE, IMPORT_FILE):
        if not file.is_file():
            raise FileNotFoundError(file)
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8-sig"))
    inventory = json.loads(INVENTORY_FILE.read_text(encoding="utf-8-sig"))
    imported = json.loads(IMPORT_FILE.read_text(encoding="utf-8-sig"))
    if manifest.get("source_sha256") != inventory.get("source_sha256") or manifest.get("source_sha256") != imported.get("source_sha256"):
        raise RuntimeError("source SHA-256 mismatch between manifest, Rhino inventory and native import report")
    if manifest.get("duplicate_name_collision_count") != 0 or inventory.get("duplicate_normalized_names"):
        raise RuntimeError("duplicate normalized block names are present; identity mapping is not safe")
    if inventory.get("cycle_count") != 0:
        raise RuntimeError("cyclic Rhino block graph found")
    cleanup = imported.get("document_cleanup")
    if not isinstance(cleanup, dict) or cleanup.get("status") != "VERIFIED":
        raise RuntimeError("native importer did not verify that all run-owned transient documents were closed")
    scaled_file = REPORTS / "scaled_occurrence_variants.json"
    scaled_map = json.loads(scaled_file.read_text(encoding="utf-8-sig")) if scaled_file.is_file() else {"variants": []}
    doc_by_name = {d["normalized_name"]: d for d in manifest["definition_documents"]}
    def_by_guid = {d["definition_guid"]: d for d in inventory["definitions"]}
    verified_paths, native_audit = audit_native_import_outputs(manifest, imported, scaled_map, PIPE)
    report["native_input_audit"] = native_audit
    if not verified_paths:
        raise RuntimeError("no native .par output passed independent manifest/path/hash verification")
    return manifest, inventory, doc_by_name, def_by_guid, verified_paths


def get_document_path(doc_record: dict) -> Path:
    """Resolve a manifest document record to its expected path under the workflow output directory. The path is derived from relative_output_path and is not created by this helper."""
    return PIPE / Path(doc_record["relative_output_path"])


def document_is_verified_part(doc_record: dict, verified_paths: set[str]) -> bool:
    """Return true only when the expected native part exists on disk and its normalized path appears in the import report verified set. File existence alone is not sufficient evidence for placement."""
    path = get_document_path(doc_record)
    return path.is_file() and path_key(path) in verified_paths


def build_dependency_order(def_by_guid: dict, doc_by_name: dict):
    """Return all nested assembly definitions in bottom-up dependency order."""
    order, done, active = [], set(), set()
    def visit(guid):
        """Visit each nested block definition once and preserve dependency order for assembly construction."""
        if guid in done:
            return
        if guid in active:
            raise RuntimeError("assembly dependency cycle at " + guid)
        source = def_by_guid.get(guid)
        if source is None:
            raise RuntimeError("missing Rhino definition GUID " + guid)
        doc = doc_by_name.get(name_key(source["name"]))
        if doc is None:
            raise RuntimeError("definition name missing from identity manifest: " + source["name"])
        if doc["document_type"] == "ASM":
            active.add(guid)
            for child in source.get("children", []):
                visit(child["definition_guid"])
            active.remove(guid)
            order.append(guid)
        done.add(guid)
    for guid, source in def_by_guid.items():
        doc = doc_by_name.get(name_key(source["name"]))
        if doc and doc["document_type"] == "ASM":
            visit(guid)
    return order


def add_placement(expected: list, doc_path: Path, matrix: list[float], source: str, name: str):
    """Append one expected occurrence record (native document path, 4×4 transform, source instance and display name) to the assembly verification plan. Does not create or place a Solid Edge occurrence."""
    expected.append({"file": str(doc_path), "matrix": matrix, "source": source, "name": name})


def place_for_definition(definition: dict, doc_by_name: dict, def_by_guid: dict,
                         verified_paths: set[str], built_by_guid: dict):
    """Resolve direct child instances and any direct Brep companion part."""
    expected, skipped, dependency_partial = [], [], []
    for occurrence in definition.get("children", []):
        child_def = def_by_guid.get(occurrence.get("definition_guid"))
        if child_def is None:
            skipped.append({"name": occurrence.get("definition_name"), "reason": "definition GUID not found"})
            continue
        child_doc = doc_by_name.get(name_key(child_def["name"]))
        if child_doc is None:
            skipped.append({"name": child_def["name"], "reason": "identity mapping not found"})
            continue
        try:
            matrix = transform_matrix(occurrence.get("transform", {}))
        except Exception as exc:
            skipped.append({"name": child_def["name"], "reason": str(exc), "instance_guid": occurrence.get("instance_guid")})
            continue
        child_path = get_document_path(child_doc)
        if child_doc["document_type"] == "PAR":
            if not document_is_verified_part(child_doc, verified_paths):
                skipped.append({"name": child_def["name"], "reason": "native .par is absent or did not pass import verification", "path": str(child_path)})
                continue
        else:
            child_status = built_by_guid.get(occurrence["definition_guid"])
            if not child_path.is_file() or not child_status:
                skipped.append({"name": child_def["name"], "reason": "nested .asm is not yet built", "path": str(child_path)})
                continue
            if not child_status.get("complete"):
                dependency_partial.append(child_def["name"])
        add_placement(expected, child_path, matrix, "child_block_occurrence", child_def["name"])

    # Rhino definitions can contain Breps directly as well as child blocks.
    # Their one verified companion .par is placed at identity and remains a
    # single local-geometry occurrence; faces are never exploded into parts.
    local_relative = None
    for d in doc_by_name.values():
        if d["rhino_definition_guid_provenance"] == definition["definition_guid"]:
            local_relative = d.get("local_geometry_companion_par")
            break
    if local_relative:
        local_path = PIPE / Path(local_relative)
        if local_path.is_file() and path_key(local_path) in verified_paths:
            add_placement(expected, local_path, identity_matrix(), "direct_local_geometry", definition["name"] + " [local geometry]")
        else:
            skipped.append({"name": definition["name"] + " [local geometry]", "reason": "local-geometry companion .par absent or not verified", "path": str(local_path)})
    return expected, skipped, dependency_partial


def build_and_verify_assembly(label: str, output_path: Path, expected: list):
    """Create/reconcile one assembly, save it, reopen it, and verify path + transform multiset."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle = None
    created_new = not output_path.is_file()
    record = {"name": label, "path": str(output_path), "created_new": created_new,
              "expected_direct_occurrences": len(expected), "status": "RUNNING"}
    try:
        if created_new:
            created = call_tool("write", "se_new_document", {"docType": "assembly"}, label)
            handle = created.get("handle")
            if not handle:
                raise RuntimeError("se_new_document did not return a tracked document handle")
            call_tool("write", "se_invoke_member", {"objectId": handle, "member": "SaveAs", "args": [str(output_path)]}, label)
        else:
            opened = call_tool("write", "se_open_document", {"path": str(output_path), "readOnly": False}, label)
            handle = opened.get("handle")
            if not handle:
                raise RuntimeError("se_open_document did not return a tracked handle")

        before = call_tool("read", "se_assembly_query", {"objectId": handle, "mode": "occurrences"}, label)
        current = before.get("occurrences", [])
        matches_before, missing_before, extras_before = match_expected(current, expected)
        if extras_before:
            raise RuntimeError("existing assembly contains unexpected occurrences; refusing to delete or overwrite them: " + json.dumps(extras_before, ensure_ascii=False)[:1500])
        ops = [{"op": "place", "file": item["file"], "matrix": item["matrix"]} for item in missing_before]
        record["existing_occurrences"] = len(current)
        record["planned_placements"] = len(ops)
        record["placements_before"] = len(matches_before)
        write_report()

        if ops:
            dry = bridge.write_tool("se_assembly_build", {"ops": ops, "objectId": handle, "dryRun": True})
            if dry.get("status") != "dry-run" or dry.get("validate", {}).get("HasError"):
                raise RuntimeError("assembly dry-run rejected: " + json.dumps(dry, ensure_ascii=False)[:2500])
            set_state(label, f"se_assembly_build executing {len(ops)} placements")
            built = bridge.write_tool("se_assembly_build", {"ops": ops, "objectId": handle, "dryRun": False, "confirm": False})
            record["build_result"] = built
            if built.get("status") != "ok" or built.get("aborted") or built.get("ok") != len(ops):
                # Tool calls can finish despite a partial response; query before any retry.
                reconciled = bridge.read_tool("se_assembly_query", {"objectId": handle, "mode": "occurrences"})
                actual = reconciled.get("occurrences", []) if reconciled.get("status") == "ok" else []
                found, missing, extras = match_expected(actual, expected)
                if missing or extras:
                    raise RuntimeError("placement incomplete; not replayed. build=" + json.dumps(built, ensure_ascii=False)[:1400] + " reconcile_missing=" + str(len(missing)) + " extras=" + str(len(extras)))

        call_tool("write", "se_invoke_member", {"objectId": handle, "member": "Save", "args": []}, label)
        call_tool("write", "se_close_document", {"target": handle, "confirm": False}, label)
        handle = None
        # Reopening from disk is mandatory; live in-memory state alone is not acceptance.
        reopened = call_tool("write", "se_open_document", {"path": str(output_path), "readOnly": False}, label)
        handle = reopened.get("handle")
        if not handle:
            raise RuntimeError("reopen did not return a tracked handle")
        final_query = call_tool("read", "se_assembly_query", {"objectId": handle, "mode": "occurrences"}, label)
        actual = final_query.get("occurrences", [])
        matches, missing, extras = match_expected(actual, expected)
        record.update({"actual_direct_occurrences": len(actual), "matched_occurrences": len(matches),
                       "missing_after_reopen": missing, "unexpected_after_reopen": extras,
                       "reference_files_exist": all(Path(x.get("file", "")).is_file() for x in actual),
                       "all_visible": all(bool(x.get("visible")) for x in actual),
                       "disk_reopened": True,
                       "verified": output_path.is_file() and len(matches) == len(expected) and not missing and not extras and
                                   all(Path(x.get("file", "")).is_file() for x in actual) and
                                   all(bool(x.get("visible")) for x in actual)})
        record["status"] = "VERIFIED" if record["verified"] else "FAILED_VERIFICATION"
        return record
    finally:
        if handle:
            try:
                bridge.write_tool("se_close_document", {"target": handle, "confirm": False})
            except Exception:
                pass


def main():
    """Build and verify the native Solid Edge assembly hierarchy from the hash-matched Rhino inventory and verified part imports. It checks bridge health, orders nested definitions, applies occurrence transforms and records per-document progress/readback. It rejects unsupported non-unit scale without a baked geometry variant and returns 0 only when the report reaches COMPLETED; performs local report/log I/O and delegated Rhino/Solid Edge bridge operations."""
    report["assembly_builder_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest, inventory, doc_by_name, def_by_guid, verified_paths = load_inputs()
    scaled_map_path = REPORTS/"scaled_occurrence_variants.json"
    scaled_map = json.loads(scaled_map_path.read_text(encoding="utf-8-sig")) if scaled_map_path.is_file() else {"variants": []}
    scaled_variants = {x["instance_guid"]: x for x in scaled_map.get("variants", []) if x.get("instance_guid")}
    report["source_sha256"] = manifest["source_sha256"]
    report["rhino_counts"] = {"definitions": manifest["rhino_definition_count"],
                              "top_level_occurrences": manifest["top_level_rhino_occurrence_count"],
                              "expanded_occurrences": manifest["expanded_rhino_occurrence_total"]}
    report["verified_part_document_count"] = len(verified_paths)
    health = bridge.status()
    report["bridge"] = health
    if not health.get("ok") or health.get("readonly"):
        raise RuntimeError("Solid Edge bridge is not writable: " + json.dumps(health, ensure_ascii=False))

    order = build_dependency_order(def_by_guid, doc_by_name)
    report["expected_nested_assemblies"] = len(order)
    if not order:
        raise RuntimeError("Rhino inventory contains no nested assembly definitions")
    report["status"] = "RUNNING"
    write_report()
    built_by_guid = {}

    for index, guid in enumerate(order, 1):
        definition = def_by_guid[guid]
        doc_record = doc_by_name[name_key(definition["name"])]
        out_path = get_document_path(doc_record)
        expected, skipped, dependency_partial = place_for_definition(definition, doc_by_name, def_by_guid, verified_paths, built_by_guid)
        log(f"ASSEMBLY {index}/{len(order)} START {definition['name']} expected={len(expected)} skipped={len(skipped)} dependency_partial={len(dependency_partial)}")
        try:
            record = build_and_verify_assembly(definition["name"], out_path, expected)
            record["definition_guid"] = guid
            record["skipped_source_occurrences"] = skipped
            record["partial_child_assemblies"] = dependency_partial
            record["complete"] = bool(record.get("verified")) and not skipped and not dependency_partial
            record["status"] = "VERIFIED" if record["complete"] else ("PARTIAL" if record.get("verified") else "FAILED")
            built_by_guid[guid] = record
            report["assemblies"].append(record)
            if record["complete"]:
                report["completed_nested_assemblies"] += 1
            elif record["verified"]:
                report["partial_nested_assemblies"] += 1
            else:
                report["failed_nested_assemblies"] += 1
            log(f"ASSEMBLY {index}/{len(order)} {record['status']} {definition['name']} placed={record.get('matched_occurrences',0)}/{len(expected)}")
        except Exception as exc:
            failed = {"name": definition["name"], "definition_guid": guid, "path": str(out_path),
                      "status": "FAILED", "complete": False, "expected_direct_occurrences": len(expected),
                      "skipped_source_occurrences": skipped, "partial_child_assemblies": dependency_partial,
                      "error": str(exc), "traceback": traceback.format_exc()}
            report["assemblies"].append(failed)
            built_by_guid[guid] = failed
            report["failed_nested_assemblies"] += 1
            report["errors"].append({"document": definition["name"], "error": str(exc)})
            log(f"ASSEMBLY {index}/{len(order)} FAILED {definition['name']}: {exc}")
        report["current_document"] = None
        report["current_action"] = f"completed nested assembly {index}/{len(order)}"
        write_report()

    # Build Root.asm from every modelspace instance. Occurrence-specific non-unit
    # scale is represented through a baked-geometry variant when one is recorded.
    root_expected, root_skipped, root_partial = [], [], []
    for occurrence in inventory.get("top_level_occurrences", []):
        definition = def_by_guid.get(occurrence.get("definition_guid"))
        if definition is None:
            root_skipped.append({"name": occurrence.get("definition_name"), "reason": "top-level definition GUID missing"})
            continue
        doc_record = doc_by_name.get(name_key(definition["name"]))
        if doc_record is None:
            root_skipped.append({"name": definition["name"], "reason": "identity mapping missing"})
            continue
        try:
            occ_transform = occurrence.get("transform", {})
            nonunit = any(abs(float(scale) - 1.0) > 1e-7 for scale in occ_transform.get("axis_scales", [1.0, 1.0, 1.0]))
            if nonunit:
                variant = scaled_variants.get(occurrence.get("instance_guid"))
                if not variant:
                    raise ValueError("non-unit scale has no baked geometry variant")
                matrix = rigid_transform_matrix(occ_transform)
                child_path = PIPE / Path(variant["relative"])
            else:
                matrix = transform_matrix(occ_transform)
                child_path = get_document_path(doc_record)
        except Exception as exc:
            root_skipped.append({"name": definition["name"], "reason": str(exc), "instance_guid": occurrence.get("instance_guid")})
            continue
        if doc_record["document_type"] == "PAR":
            if not document_is_verified_part(doc_record, verified_paths):
                root_skipped.append({"name": definition["name"], "reason": "native .par absent or failed verification", "path": str(child_path)})
                continue
        else:
            child_status = built_by_guid.get(occurrence["definition_guid"])
            if not child_path.is_file() or not child_status:
                root_skipped.append({"name": definition["name"], "reason": "nested .asm not built", "path": str(child_path)})
                continue
            if not child_status.get("complete"):
                root_partial.append(definition["name"])
        add_placement(root_expected, child_path, matrix, "top_level_rhino_occurrence", definition["name"])

    log(f"ROOT START Root.asm expected={len(root_expected)} skipped={len(root_skipped)} partial_dependencies={len(root_partial)}")
    root_record = build_and_verify_assembly("Root.asm", ROOT_ASM, root_expected)
    root_record["skipped_top_level_occurrences"] = root_skipped
    root_record["partial_child_assemblies"] = root_partial
    root_record["complete"] = bool(root_record.get("verified")) and not root_skipped and not root_partial
    root_record["status"] = "VERIFIED" if root_record["complete"] else ("PARTIAL" if root_record.get("verified") else "FAILED")
    report["root"] = root_record

    all_asm_docs_exist = all((PIPE / Path(doc_by_name[name_key(d["name"])] ["relative_output_path"])).is_file()
                              for d in inventory["definitions"] if doc_by_name[name_key(d["name"])] ["document_type"] == "ASM")
    report["acceptance"] = {
        "expected_nested_assembly_documents": len(order),
        "nested_assembly_documents_on_disk": sum(1 for d in inventory["definitions"]
            if doc_by_name[name_key(d["name"])] ["document_type"] == "ASM" and get_document_path(doc_by_name[name_key(d["name"])]).is_file()),
        "all_nested_assembly_documents_exist": all_asm_docs_exist,
        "root_document_exists": ROOT_ASM.is_file(),
        "rhino_top_level_occurrences": len(inventory.get("top_level_occurrences", [])),
        "solid_edge_root_occurrences": root_record.get("actual_direct_occurrences", 0),
        "root_skipped_occurrences": len(root_skipped),
        "nested_assemblies_complete": report["completed_nested_assemblies"],
        "nested_assemblies_partial": report["partial_nested_assemblies"],
        "nested_assemblies_failed": report["failed_nested_assemblies"],
    }
    report["status"] = "COMPLETED" if (all_asm_docs_exist and root_record.get("complete") and
        report["completed_nested_assemblies"] == len(order) and report["failed_nested_assemblies"] == 0) else "INCOMPLETE"
    report["finished_at"] = datetime.now().astimezone().isoformat()
    report["current_document"] = None
    report["current_action"] = "finished"
    write_report()
    log("FINAL " + json.dumps({"status": report["status"], "nested_asm": report["acceptance"],
                               "root": {"path": str(ROOT_ASM), "status": root_record["status"],
                                        "occurrences": root_record.get("actual_direct_occurrences"),
                                        "skipped": root_skipped}}, ensure_ascii=False))
    return 0 if report["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        report["status"] = "FAILED"
        report["fatal_error"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        report["finished_at"] = datetime.now().astimezone().isoformat()
        try:
            log("FATAL " + str(exc))
        except Exception:
            pass
        write_report()
        raise
    raise SystemExit(code)
