'''Inventaur Inc. | Offline tests for the Inventaur Solid Edge bridge's tool policy, session startup and native import diagnostics.'''

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "Scripts" / "inventaur_import_step_parts_native_v2.py"
_TEMP = tempfile.TemporaryDirectory(prefix="cad-import-tests-")
_ROOT = Path(_TEMP.name)
_CONFIG = _ROOT / "workflow_config.json"
_CONFIG.write_text(json.dumps({
    "pipeline_root": str(_ROOT),
    "reports_root": str(_ROOT / "Reports"),
    "logs_root": str(_ROOT / "Logs"),
    "step_root": str(_ROOT / "STEP"),
    "parts_root": str(_ROOT / "Parts"),
    "solid_edge_mcp_root": str(_ROOT),
}), encoding="utf-8")
_OLD_CONFIG = os.environ.get("CAD_WORKFLOW_CONFIG")
os.environ["CAD_WORKFLOW_CONFIG"] = str(_CONFIG)
_SPEC = importlib.util.spec_from_file_location("cad_native_import_under_test", SCRIPT)
_IMPORTER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_IMPORTER)
if _OLD_CONFIG is None:
    os.environ.pop("CAD_WORKFLOW_CONFIG", None)
else:
    os.environ["CAD_WORKFLOW_CONFIG"] = _OLD_CONFIG


class FakeBridge:
    """Minimal in-memory bridge double for exercising client and tool-registration behavior."""
    def __init__(self):
        """Provide the   init   test fixture or fake behavior."""
        self.descriptions = {
            "body": {
                "status": "ok",
                "properties": [
                    {"name": "Valid", "value": "True", "readable": True},
                    {"name": "IsSolid", "value": "True", "readable": True},
                    {"name": "Volume", "value": "1e-6", "readable": True},
                ],
            },
            "face1": {
                "status": "ok",
                "properties": [{"name": "Area", "value": "0.0001", "readable": True}],
            },
            "face2": {
                "status": "ok",
                "properties": [{"name": "Area", "value": "0.0001", "readable": True}],
            },
        }
        self.counts = {
            "loops": 2, "vertices": 4, "shells": 1, "faces": 2, "edges": 4,
            "models": 1, "copies": 0,
        }
        self.item_handles = {
            ("models", 1): "model1",
            ("shells", 1): "shell1",
            ("faces", 1): "face1",
            ("faces", 2): "face2",
        }
        self.body_range = [0.0, 0.0, 0.0, 0.01, 0.01, 0.01]
        self.collection_values = {"faces": [0.0001, 0.0001]}

    def read_tool(self, tool, args):
        """Provide the read tool test fixture or fake behavior."""
        if tool == "se_read_collection":
            values = self.collection_values.get(args["target"], [])
            start = int(args["startIndex"])
            limit = int(args["maxItems"])
            rows = [
                {"index": index + start, "value": values[index + start - 1]}
                for index in range(max(0, min(limit, len(values) - start + 1)))
            ]
            return {"status": "ok", "startIndex": start, "count": len(rows), "totalCount": len(values), "items": rows}
        if tool == "se_describe_object":
            return self.descriptions[args["objectId"]]
        if tool == "se_batch_read":
            target = args["targets"][0]
            members = args.get("members") or []
            handle_map = {
                ("doc", "Models"): "models",
                ("doc", "Constructions"): "constructions",
                ("constructions", "CopyConstructions"): "copies",
                ("model1", "Body"): "body",
                ("body", "Loops"): "loops",
                ("body", "Vertices"): "vertices",
                ("body", "Shells"): "shells",
                ("shell1", "Faces"): "faces",
                ("shell1", "Edges"): "edges",
            }
            values = {}
            for member in members:
                key = (target, member)
                if key in handle_map:
                    values[member] = {"handle": handle_map[key], "value": None}
                elif member == "Count":
                    values[member] = {"value": str(self.counts[target])}
            return {"status": "ok", "rows": [{"status": "ok", "values": values}]}
        if tool == "se_read_geometry":
            return {"status": "ok", "rangeBox": list(self.body_range)}
        raise AssertionError("Unexpected read tool: " + tool)

    def write_tool(self, tool, args):
        """Provide the write tool test fixture or fake behavior."""
        if tool == "se_invoke_chain":
            target = args["objectId"]
            current = target
            for step in args["steps"]:
                member = step["member"]
                if member == "Models" and current == "doc":
                    current = "models"
                elif member == "Item":
                    index = int(step["args"][0])
                    current = self.item_handles[(current, index)]
                elif member == "Body" and current == "model1":
                    current = "body"
                else:
                    raise AssertionError("Unexpected chain member: " + member)
            return {
                "status": "ok",
                "steps": [{"returnValue": {"handle": current}}],
            }
        raise AssertionError("Unexpected write tool: " + tool)


class FakeSessionBridge:
    """Bridge double that records isolated-session startup and active-document operations."""
    def __init__(self):
        """Provide the   init   test fixture or fake behavior."""
        self.running = False
        self.active = None
        self.started = 0
        self.opened = []

    def status(self):
        """Provide the status test fixture or fake behavior."""
        return {"ok": True, "bridge_running": self.running, "readonly": False, "service": "fake"}

    def start(self):
        """Provide the start test fixture or fake behavior."""
        self.started += 1
        self.running = True
        return {"ok": True, "service": "fake", "pid": 1234}

    def get_active_document(self):
        """Provide the get active document test fixture or fake behavior."""
        if self.active is None:
            return {"ok": True, "active_document": {"status": "error", "message": "no active document"}}
        return {"ok": True, "active_document": {"status": "ok", "applicationProcessId": 5678, "document": self.active}}

    def write_tool(self, tool, args):
        """Provide the write tool test fixture or fake behavior."""
        if tool != "se_open_document":
            raise AssertionError("Unexpected tool: " + tool)
        path = str(Path(args["path"]).resolve())
        self.opened.append(path)
        self.active = {
            "type": "SolidEdgePart.PartDocument", "typeShort": "PartDocument",
            "name": Path(path).name, "fullName": path, "environment": "Part",
        }
        return {"status": "ok", "handle": "obj-template", "fullName": path}


class BridgeToolRiskRegistrationTests(unittest.TestCase):
    """Verify the first-party bridge keeps its read/write tool guard declarations."""
    def test_collection_reader_is_registered_read_only_in_bridge_guard_layers(self):
        """Verify the bridge retains the collection reader in both local read allowlists."""
        mcp_root = Path(__file__).resolve().parents[1] / "Scripts" / "SOLIDEDGE-MCP"
        client = (mcp_root / "inventaur_bridge_client.py").read_text(encoding="utf-8")
        daemon = (mcp_root / "inventaur_bridge_daemon.py").read_text(encoding="utf-8")
        self.assertIn('"se_read_collection"', client.split("READ_TOOLS = {", 1)[1].split("}", 1)[0])
        self.assertIn('"se_read_collection"', daemon.split("READ_TOOLS = {", 1)[1].split("}", 1)[0])


class BridgeSessionBootstrapTests(unittest.TestCase):
    """Verify bridge startup reuses or creates only the intended isolated Solid Edge session."""
    def test_starts_isolated_bridge_and_activates_metric_template(self):
        """Verify that starts isolated bridge and activates metric template."""
        bridge = FakeSessionBridge()
        template = _ROOT / "ISO Metric Part.par"
        template.write_bytes(b"template")
        status, active, started, bootstrap = _IMPORTER._bridge_ensure_session_ready(bridge, template)
        self.assertEqual(bridge.started, 1)
        self.assertTrue(status["ok"])
        self.assertEqual(active["typeShort"], "PartDocument")
        self.assertEqual(active["_application_process_id"], 5678)
        self.assertEqual(bridge.opened, [str(template.resolve())])
        self.assertEqual(bootstrap["status"], "VERIFIED")
        self.assertTrue(started["ok"])

    def test_existing_part_session_is_reused_without_restart_or_template_open(self):
        """Verify that existing part session is reused without restart or template open."""
        bridge = FakeSessionBridge()
        bridge.running = True
        bridge.active = {
            "type": "SolidEdgePart.PartDocument", "typeShort": "PartDocument",
            "name": "already_active.par", "fullName": str(_ROOT / "already_active.par"),
            "environment": "Part",
        }
        status, active, started, bootstrap = _IMPORTER._bridge_ensure_session_ready(bridge)
        self.assertTrue(status["ok"])
        self.assertEqual(bridge.started, 0)
        self.assertIsNone(started)
        self.assertIsNone(bootstrap)
        self.assertEqual(bridge.opened, [])
        self.assertEqual(active["typeShort"], "PartDocument")


class BridgeNativeMetricsTests(unittest.TestCase):
    """Verify native import acceptance uses the intended body and topology evidence."""
    def test_imported_native_body_is_accepted_without_face_signature_gate(self):
        """Verify that imported native body is accepted without face signature gate."""
        bridge = FakeBridge()
        metrics = _IMPORTER._bridge_document_metrics(
            bridge, "doc", {"name": "test_part", "fullName": str(_ROOT / "Parts" / "test_part.par")},
        )
        self.assertEqual(metrics["body_count"], 1)
        self.assertEqual(metrics["models_count"], 1)
        self.assertEqual(metrics["faces"], 2)
        validation = _IMPORTER.validate_native_against_step(metrics, {})
        self.assertTrue(validation["passed"], validation["hard_failures"])

    def test_invalid_body_flag_is_warning_not_import_blocker(self):
        """Verify that invalid body flag is warning not import blocker."""
        metrics = {"body_count": 1, "models_count": 1, "faces": 41, "valid": False, "is_solid": True}
        validation = _IMPORTER.validate_native_against_step(metrics, {})
        self.assertTrue(validation["passed"], validation["hard_failures"])
        self.assertIn("SOLID_EDGE_BODY_VALID_FALSE", [x["code"] for x in validation["warnings"]])

    def test_empty_native_document_still_fails_import(self):
        """Verify that empty native document still fails import."""
        metrics = {"body_count": 0, "models_count": 0, "faces": 0, "valid": False, "is_solid": False}
        validation = _IMPORTER.validate_native_against_step(metrics, {})
        self.assertFalse(validation["passed"])


if __name__ == "__main__":
    unittest.main()
