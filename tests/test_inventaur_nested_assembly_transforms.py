'''Inventaur Inc. | Offline tests for Rhino-to-Solid-Edge assembly transforms and native-import evidence reconciliation.'''
from __future__ import annotations

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"


import importlib.util
import os
import sys
import types
import json
import tempfile
import unittest
from pathlib import Path

WORKFLOW = next(parent for parent in Path(__file__).resolve().parents
                if (parent / "Scripts" / "inventaur_build_nested_assembly_tree.py").is_file())
MCP_ROOT = WORKFLOW / "Scripts" / "SOLIDEDGE-MCP"
_TEST_ROOT = Path(tempfile.gettempdir()) / "inventaur_cad_assembly_transform_test"
_TEST_ROOT.mkdir(parents=True, exist_ok=True)
CONFIG = _TEST_ROOT / "workflow_config.json"
CONFIG.write_text(json.dumps({
    "pipeline_root": str(_TEST_ROOT),
    "reports_root": str(_TEST_ROOT / "Logs" / "Reports"),
    "logs_root": str(_TEST_ROOT / "Logs"),
    "solid_edge_mcp_root": str(MCP_ROOT),
    "root_assembly_path": str(_TEST_ROOT / "Assemblies" / "Root.asm"),
}), encoding="utf-8")
os.environ["CAD_WORKFLOW_CONFIG"] = str(CONFIG)
sys.path.insert(0, str(MCP_ROOT))
# Transform tests must not connect to or start the live CAD bridge.
sys.modules.setdefault("inventaur_bridge_client", types.SimpleNamespace())

BUILDER_PATH = WORKFLOW / "Scripts" / "inventaur_build_nested_assembly_tree.py"
SPEC = importlib.util.spec_from_file_location("cad_assembly_builder", BUILDER_PATH)
BUILDER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BUILDER)


class NativeImportAuditTests(unittest.TestCase):
    """Verify native parts are accepted only when their hashes and manifest identities reconcile."""
    def _fixture(self, root):
        """Provide the  fixture test fixture or fake behavior."""
        import hashlib
        pipeline = root / "Pipeline"
        parts = pipeline / "Parts"
        steps = pipeline / "STEP"
        parts.mkdir(parents=True)
        steps.mkdir(parents=True)
        native = parts / "part_a.par"
        step = steps / "part_a.stp"
        native.write_bytes(b"verified-native-par")
        step.write_bytes(b"verified-source-step")
        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        manifest = {"definition_documents": [{
            "document_type": "PAR", "relative_output_path": "Parts/part_a.par",
        }]}
        imported = {
            "status": "INCOMPLETE",
            "results": [{
                "document_key": "block_name:part a", "output": str(native),
                "status": "imported_verified", "native_bytes": native.stat().st_size,
                "native_sha256": sha(native), "step": str(step), "step_sha256": sha(step),
                "topology": {"valid": True, "body_count": 1},
                "close_after_save": {"status": "ok"},
            }],
        }
        return pipeline, native, imported, manifest

    def test_partial_import_only_accepts_manifest_path_with_matching_native_and_step_hashes(self):
        """Verify that partial import only accepts manifest path with matching native and step hashes."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            pipeline, native, imported, manifest = self._fixture(Path(td))
            verified, audit = BUILDER.audit_native_import_outputs(manifest, imported, {"variants": []}, pipeline)
            self.assertEqual(verified, {BUILDER.path_key(native)})
            self.assertEqual(audit["verified_native_output_count"], 1)
            self.assertEqual(audit["rejected_result_count"], 0)

    def test_rejects_native_hash_mismatch_and_non_manifest_output(self):
        """Verify that rejects native hash mismatch and non manifest output."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            pipeline, native, imported, manifest = self._fixture(Path(td))
            imported["results"][0]["native_sha256"] = "0" * 64
            verified, audit = BUILDER.audit_native_import_outputs(manifest, imported, {"variants": []}, pipeline)
            self.assertFalse(verified)
            self.assertEqual(audit["rejected_results"][0]["reason"], "NATIVE_OUTPUT_SHA256_MISMATCH")
            other = pipeline / "Parts" / "unlisted.par"
            other.write_bytes(b"other")
            row = dict(imported["results"][0])
            row.update(output=str(other), native_sha256=__import__("hashlib").sha256(other.read_bytes()).hexdigest(),
                       native_bytes=other.stat().st_size)
            imported["results"] = [row]
            verified, audit = BUILDER.audit_native_import_outputs(manifest, imported, {"variants": []}, pipeline)
            self.assertFalse(verified)
            self.assertEqual(audit["rejected_results"][0]["reason"], "NATIVE_OUTPUT_NOT_IN_SOURCE_MANIFEST")


class AssemblyTransformTests(unittest.TestCase):
    """Verify unit conversion, orientation, reflection and scaled-occurrence transform rules."""
    def test_identity_matrix_is_stable(self):
        """Verify that identity matrix is stable."""
        value = BUILDER.transform_matrix({
            "matrix": [
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ],
            "axis_scales": [1, 1, 1],
        })
        self.assertEqual(value, BUILDER.identity_matrix())

    def test_translation_converts_rhino_millimetres_to_solid_edge_metres(self):
        """Verify that translation converts rhino millimetres to solid edge metres."""
        value = BUILDER.transform_matrix({
            "matrix": [
                [1, 0, 0, 1250],
                [0, 1, 0, -250],
                [0, 0, 1, 3050],
                [0, 0, 0, 1],
            ],
            "axis_scales": [1, 1, 1],
        })
        self.assertEqual(value[12:15], [1.25, -0.25, 3.05])

    def test_rotation_and_reflection_parity_are_preserved(self):
        """Verify that rotation and reflection parity are preserved."""
        rotation = BUILDER.transform_matrix({
            "matrix": [
                [0, -1, 0, 0],
                [1, 0, 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ],
            "axis_scales": [1, 1, 1],
        })
        self.assertEqual(rotation[:12], [0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0])

        reflection = BUILDER.transform_matrix({
            "matrix": [
                [-1, 0, 0, 10],
                [0, 1, 0, 20],
                [0, 0, 1, 30],
                [0, 0, 0, 1],
            ],
            "axis_scales": [1, 1, 1],
            "reflection": True,
        })
        self.assertEqual(reflection[0], -1.0)
        self.assertEqual(reflection[12:15], [0.01, 0.02, 0.03])

    def test_unbaked_scale_and_shear_are_rejected(self):
        """Verify that unbaked scale and shear are rejected."""
        scaled = {
            "matrix": [
                [2, 0, 0, 0],
                [0, 3, 0, 0],
                [0, 0, 4, 0],
                [0, 0, 0, 1],
            ],
            "axis_scales": [2, 3, 4],
        }
        with self.assertRaisesRegex(ValueError, "baked geometry variant"):
            BUILDER.transform_matrix(scaled)

        sheared = {
            "matrix": [
                [1, 0.2, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ],
            "axis_scales": [1, 1, 1],
            "has_shear": True,
        }
        with self.assertRaisesRegex(ValueError, "sheared"):
            BUILDER.transform_matrix(sheared)

    def test_baked_scaled_variant_strips_magnitudes_but_preserves_reflection(self):
        """Verify that baked scaled variant strips magnitudes but preserves reflection."""
        value = BUILDER.rigid_transform_matrix({
            "matrix": [
                [-2, 0, 0, 1250],
                [0, 3, 0, -250],
                [0, 0, 4, 3050],
                [0, 0, 0, 1],
            ],
            "axis_scales": [2, 3, 4],
            "reflection": True,
            "determinant": -24,
        })
        self.assertEqual(value[0], -1.0)
        self.assertEqual(value[5], 1.0)
        self.assertEqual(value[10], 1.0)
        self.assertEqual(value[12:15], [1.25, -0.25, 3.05])
        self.assertLess(value[0] * value[5] * value[10], 0)

    def test_scaled_variant_rejects_reflection_parity_change_and_zero_axis(self):
        """Verify that scaled variant rejects reflection parity change and zero axis."""
        with self.assertRaisesRegex(ValueError, "reflection parity"):
            BUILDER.rigid_transform_matrix({
                "matrix": [
                    [-2, 0, 0, 0],
                    [0, 3, 0, 0],
                    [0, 0, 4, 0],
                    [0, 0, 0, 1],
                ],
                "reflection": False,
            })
        with self.assertRaisesRegex(ValueError, "zero axis"):
            BUILDER.rigid_transform_matrix({
                "matrix": [
                    [0, 0, 0, 0],
                    [0, 1, 0, 0],
                    [0, 0, 1, 0],
                    [0, 0, 0, 1],
                ],
            })

    def test_invalid_nonfinite_and_malformed_matrices_fail_closed(self):
        """Verify that invalid nonfinite and malformed matrices fail closed."""
        with self.assertRaisesRegex(ValueError, "invalid Rhino 4x4"):
            BUILDER.transform_matrix({"matrix": [[1, 0], [0, 1]]})
        with self.assertRaisesRegex(ValueError, "non-finite"):
            BUILDER.transform_matrix({
                "matrix": [
                    [1, 0, 0, float("nan")],
                    [0, 1, 0, 0],
                    [0, 0, 1, 0],
                    [0, 0, 0, 1],
                ],
            })
        self.assertEqual(BUILDER.matrix_error([], BUILDER.identity_matrix()), float("inf"))


if __name__ == "__main__":
    unittest.main()
