'''Inventaur Inc. | Contract tests for the Inventaur Rhino-to-Solid-Edge supervisor, retry rules and checkpoint reconciliation.'''
from __future__ import annotations

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"


import importlib.util
import json
import os
import tempfile
import urllib.error
from unittest import mock
import unittest
from pathlib import Path

WORKFLOW = next(parent for parent in Path(__file__).resolve().parents
                if (parent / "Scripts" / "inventaur_run_rhino3d_to_solidedge.py").is_file())
RUNNER_PATH = WORKFLOW / "Scripts" / "inventaur_run_rhino3d_to_solidedge.py"
SPEC = importlib.util.spec_from_file_location("rhino_to_solidedge_runner", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


class NativeImportGateTests(unittest.TestCase):
    """Verify complete and partial native import batches are gated by source identity and cleanup evidence."""
    def base(self):
        """Return the canonical project root used to read workflow source in contract tests."""
        return {
            "status": "COMPLETED",
            "eligible_native_import_count": 45,
            "completed_count": 45,
            "failed_count": 0,
        }

    def test_complete_report_requires_explicit_document_cleanup_evidence(self):
        """Verify that complete report requires explicit document cleanup evidence."""
        self.assertFalse(RUNNER.native_import_is_complete(self.base()))
        row=self.base()
        row["document_cleanup"]={"status":"VERIFIED"}
        self.assertTrue(RUNNER.native_import_is_complete(row))

    def test_requires_document_cleanup_when_field_is_present(self):
        """Verify that requires document cleanup when field is present."""
        row = self.base()
        row["document_cleanup"] = {"status": "VERIFIED"}
        self.assertTrue(RUNNER.native_import_is_complete(row))
        row["document_cleanup"] = {"status": "INCOMPLETE"}
        self.assertFalse(RUNNER.native_import_is_complete(row))

    def test_native_import_resume_reuses_only_hash_verified_outputs(self):
        """A complete source-bound batch is reusable only when native and STEP files still match."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Parts").mkdir()
            (root / "STEP").mkdir()
            native = root / "Parts" / "part_a.par"
            step = root / "STEP" / "part_a.stp"
            native.write_bytes(b"verified native PAR")
            step.write_bytes(b"verified STEP")

            report = self.base()
            report.update(eligible_native_import_count=1, completed_count=1, failed_count=0, source_sha256="a" * 64, document_cleanup={"status": "VERIFIED"}, results=[{
                "document_key": "part_a",
                "status": "reused_verified",
                "output": str(native),
                "native_bytes": native.stat().st_size,
                "native_sha256": RUNNER.sha(native),
                "step": str(step),
                "step_sha256": RUNNER.sha(step),
                "reopen_verified": True,
                "validation": {"passed": True},
            }])
            self.assertTrue(RUNNER.native_import_checkpoint_is_current(
                report, "a" * 64, {"part_a"}, root
            ))

            native.write_bytes(b"changed PAR")
            self.assertFalse(RUNNER.native_import_checkpoint_is_current(
                report, "a" * 64, {"part_a"}, root
            ))

    def test_native_import_resume_rejects_wrong_source_or_missing_expected_key(self):
        """A completed native report is not reusable for another source or incomplete key set."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Parts").mkdir()
            (root / "STEP").mkdir()
            native = root / "Parts" / "part_a.par"
            step = root / "STEP" / "part_a.stp"
            native.write_bytes(b"verified native PAR")
            step.write_bytes(b"verified STEP")

            report = self.base()
            report.update(eligible_native_import_count=1, completed_count=1, failed_count=0, source_sha256="a" * 64, document_cleanup={"status": "VERIFIED"}, results=[{
                "document_key": "part_a",
                "status": "imported_verified",
                "output": str(native),
                "native_bytes": native.stat().st_size,
                "native_sha256": RUNNER.sha(native),
                "step": str(step),
                "step_sha256": RUNNER.sha(step),
                "reopen_verified": True,
                "validation": {"passed": True},
            }])
            self.assertFalse(RUNNER.native_import_checkpoint_is_current(
                report, "b" * 64, {"part_a"}, root
            ))
            self.assertFalse(RUNNER.native_import_checkpoint_is_current(
                report, "a" * 64, {"part_a", "part_b"}, root
            ))

    def test_native_import_resume_rejects_unreopened_native_output(self):
        """A hash-matching file is insufficient without the native disk-reopen contract."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Parts").mkdir()
            (root / "STEP").mkdir()
            native = root / "Parts" / "part_a.par"
            step = root / "STEP" / "part_a.stp"
            native.write_bytes(b"verified native PAR")
            step.write_bytes(b"verified STEP")

            report = self.base()
            report.update(eligible_native_import_count=1, completed_count=1, failed_count=0, source_sha256="a" * 64, document_cleanup={"status": "VERIFIED"}, results=[{
                "document_key": "part_a",
                "status": "imported_verified",
                "output": str(native),
                "native_bytes": native.stat().st_size,
                "native_sha256": RUNNER.sha(native),
                "step": str(step),
                "step_sha256": RUNNER.sha(step),
                "reopen_verified": False,
                "validation": {"passed": True},
            }])
            self.assertFalse(RUNNER.native_import_checkpoint_is_current(
                report, "a" * 64, {"part_a"}, root
            ))

    def test_assembly_resume_requires_full_nested_and_root_acceptance(self):
        """Reuse requires every nested assembly complete and the root disk-reopened."""
        report = {
            "status": "COMPLETED",
            "source_sha256": "a" * 64,
            "native_input_signature": "b" * 64,
            "assembly_builder_sha256": "c" * 64,
            "expected_nested_assemblies": 2,
            "completed_nested_assemblies": 2,
            "partial_nested_assemblies": 0,
            "failed_nested_assemblies": 0,
            "acceptance": {
                "all_nested_assembly_documents_exist": True,
                "root_document_exists": True,
                "nested_assemblies_complete": 2,
                "nested_assemblies_partial": 0,
                "nested_assemblies_failed": 0,
                "root_skipped_occurrences": 0,
            },
            "root": {
                "status": "VERIFIED", "verified": True, "disk_reopened": True,
                "reference_files_exist": True, "all_visible": True,
                "expected_direct_occurrences": 3, "actual_direct_occurrences": 3,
                "skipped_top_level_occurrences": [],
            },
        }
        self.assertTrue(RUNNER.assembly_checkpoint_is_current(
            report, "a" * 64, "b" * 64, "c" * 64, 3
        ))
        incomplete = json.loads(json.dumps(report))
        incomplete["status"] = "INCOMPLETE"
        self.assertFalse(RUNNER.assembly_checkpoint_is_current(
            incomplete, "a" * 64, "b" * 64, "c" * 64, 3
        ))
        partial = json.loads(json.dumps(report))
        partial["partial_nested_assemblies"] = 1
        partial["completed_nested_assemblies"] = 1
        partial["acceptance"]["nested_assemblies_partial"] = 1
        partial["acceptance"]["nested_assemblies_complete"] = 1
        self.assertFalse(RUNNER.assembly_checkpoint_is_current(
            partial, "a" * 64, "b" * 64, "c" * 64, 3
        ))

    def test_assembly_resume_rejects_root_without_disk_reopen_or_occurrence_match(self):
        """The root must be independently disk-reopened with every direct occurrence placed."""
        report = {
            "status": "COMPLETED",
            "source_sha256": "a" * 64,
            "native_input_signature": "b" * 64,
            "assembly_builder_sha256": "c" * 64,
            "expected_nested_assemblies": 1,
            "completed_nested_assemblies": 1,
            "partial_nested_assemblies": 0,
            "failed_nested_assemblies": 0,
            "acceptance": {
                "all_nested_assembly_documents_exist": True,
                "root_document_exists": True,
                "nested_assemblies_complete": 1,
                "nested_assemblies_partial": 0,
                "nested_assemblies_failed": 0,
                "root_skipped_occurrences": 0,
            },
            "root": {
                "status": "VERIFIED", "verified": True, "disk_reopened": False,
                "reference_files_exist": True, "all_visible": True,
                "expected_direct_occurrences": 3, "actual_direct_occurrences": 2,
                "skipped_top_level_occurrences": [],
            },
        }
        self.assertFalse(RUNNER.assembly_checkpoint_is_current(
            report, "a" * 64, "b" * 64, "c" * 64, 2
        ))

    def test_partial_native_import_can_build_verified_assembly_branches(self):
        """Verify that partial native import can build verified assembly branches."""
        row = {
            "status": "INCOMPLETE",
            "source_sha256": "a" * 64,
            "eligible_native_import_count": 10,
            "completed_count": 8,
            "failed_count": 2,
            "document_cleanup": {"status": "VERIFIED"},
            "results": [{
                "status": "imported_verified",
                "output": r"C:\run\Parts\part_a.par",
                "native_sha256": "b" * 64,
            }],
        }
        result = RUNNER.native_import_assembly_readiness(row, "a" * 64)
        self.assertTrue(result["ready"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["candidate_count"], 1)

    def test_partial_native_import_requires_cleanup_and_source_identity(self):
        """Verify that partial native import requires cleanup and source identity."""
        row = {
            "status": "INCOMPLETE", "source_sha256": "a" * 64,
            "document_cleanup": {"status": "INCOMPLETE"},
            "results": [{"status": "imported_verified", "output": "part.par", "native_sha256": "b" * 64}],
        }
        self.assertFalse(RUNNER.native_import_assembly_readiness(row, "a" * 64)["ready"])
        row["document_cleanup"] = {"status": "VERIFIED"}
        self.assertFalse(RUNNER.native_import_assembly_readiness(row, "c" * 64)["ready"])


    def test_pipeline_uses_direct_step_import_assembly_sequence(self):
        """Verify that pipeline uses direct step import assembly sequence."""
        source = RUNNER.SCRIPT_DIR / "inventaur_run_rhino3d_to_solidedge.py"
        text = source.read_text(encoding="utf-8-sig")
        self.assertNotIn('stage("join_lowest_block_breps_v2"', text)
        self.assertNotIn('stage("repair_breps_for_step_v1"', text)
        self.assertIn('stage("colorize_rhino_unique_blocks_v2"', text)
        self.assertLess(text.index('stage("colorize_rhino_unique_blocks_v2"'), text.index('stage("build_rhino_inventory"'))
        self.assertIn('stage("build_rhino_inventory"', text)
        self.assertIn('stage("build_identity_manifest"', text)
        self.assertIn('stage("export_named_block_geometry_to_step_rhino"', text)
        self.assertIn('"native_part_import"', text)
        self.assertIn("reuse_if=native_part_import_is_current", text)
        self.assertIn('stage("nested_assembly_tree"', text)
        self.assertIn('d.get("source_sha256")==sha(cfg["source_3dm"])', text)
        self.assertIn('d.get("source_sha256")==sha(cfg["colorized_3dm"])', text)
        self.assertNotIn('sha(cfg["repaired_3dm"])', text)

    def test_step_export_falls_back_to_original_block_instance_without_repair(self):
        """Verify that step export falls back to original block instance without repair."""
        exporter = RUNNER.SCRIPT_DIR / "inventaur_export_named_block_geometry_to_step_rhino.py"
        text = exporter.read_text(encoding="utf-8-sig")
        self.assertIn("AddInstanceObject", text)
        self.assertIn("ORIGINAL_BLOCK_INSTANCE_DIRECT", text)
        self.assertIn("DEFERRED_TO_SOLID_EDGE_NATIVE_IMPORT", text)
        self.assertNotIn("FileStp.Read", text)
        self.assertNotIn("JoinNakedEdges", text)
        self.assertNotIn("CapPlanarHoles", text)

    def test_leaf_step_uses_original_block_instance_and_native_readback(self):
        """Verify that leaf step uses original block instance and native readback."""
        exporter = RUNNER.SCRIPT_DIR / "inventaur_export_named_block_geometry_to_step_rhino.py"
        text = exporter.read_text(encoding="utf-8-sig")
        self.assertIn("AddInstanceObject", text)
        self.assertIn("ORIGINAL_BLOCK_INSTANCE_DIRECT", text)
        self.assertNotIn("FileStp.Read", text)
        self.assertIn("DEFERRED_TO_SOLID_EDGE_NATIVE_IMPORT", text)
        self.assertNotIn("JoinNakedEdges", text)

    def test_step_export_is_batched_and_falls_back_without_readback(self):
        """Verify that step export is batched and falls back without readback."""
        exporter=(RUNNER.SCRIPT_DIR / "inventaur_export_named_block_geometry_to_step_rhino.py").read_text(encoding="utf-8-sig")
        runner=RUNNER_PATH.read_text(encoding="utf-8-sig")
        self.assertIn("batch_start", exporter)
        self.assertIn("batch_size", exporter)
        self.assertIn("DIRECT_GEOMETRY_FALLBACK", exporter)
        self.assertIn("AddInstanceObject", exporter)
        self.assertNotIn("FileStp.Read", exporter)
        self.assertIn("export_steps_in_batches", runner)
        self.assertIn("batch_size=8", runner)

    def test_every_script_using_path_has_an_explicit_pathlib_import(self):
        """Verify that every script using path has an explicit pathlib import."""
        import re
        for path in RUNNER.SCRIPT_DIR.glob("*.py"):
            source = path.read_text(encoding="utf-8-sig")
            if re.search(r"\bPath\s*\(", source):
                self.assertRegex(
                    source,
                    r"(?m)^\s*from\s+pathlib\s+import\s+[^\n]*\bPath\b",
                    msg=f"{path.name} uses Path() without importing pathlib.Path",
                )

    def test_baseline_zip_par_filter_is_case_insensitive_and_ignores_assemblies(self):
        """Verify that baseline zip par filter is case insensitive and ignores assemblies."""
        self.assertTrue(RUNNER.is_baseline_par_candidate("Root/Parts/model.par"))
        self.assertTrue(RUNNER.is_baseline_par_candidate("root/parts/model.PAR"))
        self.assertTrue(RUNNER.is_baseline_par_candidate(r"Root\PARTS\model.par"))
        self.assertFalse(RUNNER.is_baseline_par_candidate("Root/Assemblies/model.asm"))
        self.assertFalse(RUNNER.is_baseline_par_candidate("Root/STEP/model.stp"))
        self.assertFalse(RUNNER.is_baseline_par_candidate("Root/model.par"))

    def test_rejects_partial_native_batch(self):
        """Verify that rejects partial native batch."""
        row = self.base()
        row.update(status="INCOMPLETE", completed_count=41, failed_count=4)
        self.assertFalse(RUNNER.native_import_is_complete(row))

    def test_rejects_success_label_with_count_mismatch(self):
        """Verify that rejects success label with count mismatch."""
        row = self.base()
        row["completed_count"] = 44
        self.assertFalse(RUNNER.native_import_is_complete(row))

    def test_rejects_failed_count_even_when_completed_count_matches(self):
        """Verify that rejects failed count even when completed count matches."""
        row = self.base()
        row["failed_count"] = 1
        self.assertFalse(RUNNER.native_import_is_complete(row))

    def test_requires_explicit_run_config_and_drops_legacy_alias_in_child(self):
        """Verify that requires explicit run config and drops legacy alias in child."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script = root / "emit_env.py"
            log = root / "child.log"
            config = root / "run-config.json"
            config.write_text("{}", encoding="utf-8")
            script.write_text(
                "import os,json\n"
                "print(json.dumps({'config':os.getenv('CAD_WORKFLOW_CONFIG'),"
                "'legacy':os.getenv('RHINO_SE_WORKFLOW_CONFIG'),"
                "'localappdata':os.getenv('LOCALAPPDATA'),"
                "'events':os.getenv('SE_MCP_ENABLE_EVENTS')}))\n",
                encoding="utf-8",
            )
            old_legacy = os.environ.get("RHINO_SE_WORKFLOW_CONFIG")
            os.environ["RHINO_SE_WORKFLOW_CONFIG"] = "stale-shared-config"
            try:
                _, output = RUNNER.run_python(
                    script, root, log, cfg={"config_path": str(config),
                                                "solid_edge_localappdata":str(root/"isolated-profile")}
                )
            finally:
                if old_legacy is None:
                    os.environ.pop("RHINO_SE_WORKFLOW_CONFIG", None)
                else:
                    os.environ["RHINO_SE_WORKFLOW_CONFIG"] = old_legacy
            value = json.loads(output.strip())
            self.assertEqual(value["config"], str(config.resolve()))
            self.assertIsNone(value["legacy"])
            self.assertEqual(value["localappdata"], str((root/"isolated-profile").resolve()))
            self.assertEqual(value["events"], "0")

    def test_http_502_reconciles_before_replaying_side_effect(self):
        """Verify that http 502 reconciles before replaying side effect."""
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "rhino_stage.py"
            script.write_text("print('deterministic stage')\n", encoding="utf-8")
            config = Path(td) / "run-config.json"
            config.write_text("{}", encoding="utf-8")
            error = urllib.error.HTTPError("http://127.0.0.1:10500/", 502, "Bad Gateway", {}, None)
            with mock.patch.object(RUNNER.urllib.request, "urlopen", side_effect=error) as post, \
                 mock.patch.object(RUNNER.time, "sleep") as pause:
                result = RUNNER.call_rhino(
                    script, {"rhino_mcp_url": "http://127.0.0.1:10500/", "config_path": str(config)},
                    reconcile=lambda: True,
                )
            self.assertEqual(result, "RECONCILED_EXISTING_STAGE_REPORT_AFTER_HTTP_502")
            post.assert_called_once()
            pause.assert_called_once_with(5)

    def test_http_502_retries_once_when_reconciliation_finds_no_result(self):
        """Verify that http 502 retries once when reconciliation finds no result."""
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "rhino_stage.py"
            script.write_text("print('deterministic stage')\n", encoding="utf-8")
            config = Path(td) / "run-config.json"
            config.write_text("{}", encoding="utf-8")
            error = urllib.error.HTTPError("http://127.0.0.1:10500/", 502, "Bad Gateway", {}, None)
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({
                "result": {"content": [{"type": "text", "text": json.dumps({"stdout": "OK"})}]}
            }).encode()
            with mock.patch.object(RUNNER.urllib.request, "urlopen", side_effect=[error, response]) as post, \
                 mock.patch.object(RUNNER.time, "sleep") as pause:
                result = RUNNER.call_rhino(
                    script, {"rhino_mcp_url": "http://127.0.0.1:10500/", "config_path": str(config)},
                    reconcile=lambda: False,
                )
            self.assertEqual(result, "OK")
            self.assertEqual(post.call_count, 2)
            pause.assert_called_once_with(5)

    def test_rejects_nonexistent_config_file(self):
        """Verify that rejects nonexistent config file."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script = root / "noop.py"
            script.write_text("print('should-not-run')\n", encoding="utf-8")
            with self.assertRaisesRegex(FileNotFoundError, "config"):
                RUNNER.run_python(
                    script, root, root / "child.log",
                    cfg={"config_path": str(root / "missing.json"), "solid_edge_localappdata": str(root / "profile")},
                )

    def test_rhino_stage_payload_is_transient_and_config_is_not_mutated(self):
        """Verify that rhino stage payload is transient and config is not mutated."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script = root / "scaled_stage.py"
            script.write_text("print('stage')\n", encoding="utf-8")
            config = root / "run-config.json"
            config.write_text(json.dumps({"source": "002"}), encoding="utf-8")
            before = config.read_bytes()
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({
                "result": {"content": [{"type": "text", "text": json.dumps({"stdout": "OK"})}]}
            }).encode()
            with mock.patch.object(RUNNER.urllib.request, "urlopen", return_value=response) as post:
                result = RUNNER.call_rhino(
                    script, {"rhino_mcp_url": "http://127.0.0.1:10500/", "config_path": str(config)},
                    stage_payload={"active_scaled_occurrence": {"definition_name": "leveler"}},
                )
            body = json.loads(post.call_args.args[0].data.decode("utf-8"))
            inner = body["params"]["arguments"]["script"]
            self.assertIn("CAD_WORKFLOW_STAGE_PAYLOAD", inner)
            self.assertIn("active_scaled_occurrence", inner)
            self.assertEqual(config.read_bytes(), before)
            self.assertEqual(result, "OK")

    def test_rejects_missing_config_path(self):
        """Verify that rejects missing config path."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script = root / "noop.py"
            script.write_text("print('should-not-run')\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "config_path"):
                RUNNER.run_python(script, root, root / "child.log", cfg={})



class RhinoMcpAutoloadTests(unittest.TestCase):
    """Verify Rhino MCP startup/discovery and run configuration remain document-scoped."""
    def runtime(self, url="http://127.0.0.1:10501/"):
        """Provide the runtime test fixture or fake behavior."""
        return {"url":url,"server":{},"tool_count":44,"run_python_available":True,
                "pid":2124,"port":10501,"version":"9","marker":"listener.json"}

    def test_discovers_live_rhino_listener_and_ignores_gone_marker(self):
        """Verify that discovers live rhino listener and ignores gone marker."""
        import os
        with tempfile.TemporaryDirectory() as td:
            marker_root=Path(td)/"McNeel"/"Rhinoceros"/"ai"/"listeners"
            marker_root.mkdir(parents=True)
            active=marker_root/"2124-10501.json"
            active.write_text(json.dumps({"pid":2124,"port":10501,"version":"9"}),encoding="utf-8")
            dead=marker_root/"17728-10500.json"
            dead.write_text(json.dumps({"pid":17728,"port":10500,"version":"9"}),encoding="utf-8")
            gone=marker_root/"17728-10500.gone"
            gone.write_text("stopped",encoding="utf-8")
            os.utime(dead,(100,100))
            os.utime(gone,(200,200))
            with mock.patch.dict(os.environ,{"APPDATA":td}), \
                 mock.patch.object(RUNNER,"check_rhino_runtime",
                                   side_effect=lambda cfg,timeout=15: {
                                       "url":cfg["rhino_mcp_url"],"server":{},
                                       "tool_count":44,"run_python_available":True}):
                found=RUNNER.active_rhino_runtimes()
        self.assertEqual([row["port"] for row in found],[10501])
        self.assertEqual(found[0]["version"],"9")

    def test_requires_exact_preopened_saved_path_and_accepts_live_modified_document(self):
        """Verify that requires exact preopened saved path and accepts live modified document."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"selected.3dm"
            source.write_bytes(b"rhino-source")
            runtime=self.runtime()
            info={"path":str(source),"modified":True,"runtime_serial_number":9}
            with mock.patch.object(RUNNER,"active_rhino_runtimes",return_value=[runtime]), \
                 mock.patch.object(RUNNER,"rhino_document_info",return_value=info):
                cfg={}
                result=RUNNER.require_live_rhino_source(source,cfg)
                digest=RUNNER.sha(source)
            self.assertEqual(result["action"],"VERIFIED_PREOPENED_RHINO_DOCUMENT")
            self.assertEqual(cfg["rhino_mcp_url"],runtime["url"])
            self.assertEqual(cfg["rhino_pid"],runtime["pid"])
            self.assertEqual(cfg["rhino_session_requirement"],
                             "PREEXISTING_RHINO_PROCESS_AND_LIVE_MCP_REQUIRED")
            self.assertEqual(result["saved_file_sha256"],digest)
            self.assertEqual(result["document"]["modified"],True)
            self.assertEqual(result["capture_policy"],"SNAPSHOT_CURRENT_IN_MEMORY_DOCUMENT_WITH_WRITE3DMFILE")

    def test_modified_preopened_document_is_accepted_for_non_destructive_snapshot(self):
        """Verify that modified preopened document is accepted for non destructive snapshot."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"selected.3dm"
            original=b"rhino-source"
            source.write_bytes(original)
            runtime=self.runtime()
            info={"path":str(source),"modified":True,"runtime_serial_number":9}
            with mock.patch.object(RUNNER,"active_rhino_runtimes",return_value=[runtime]), \
                 mock.patch.object(RUNNER,"rhino_document_info",return_value=info):
                result=RUNNER.require_live_rhino_source(source,{})
            self.assertTrue(result["document"]["modified"])
            self.assertEqual(result["saved_file_sha256"],RUNNER.sha(source))
            self.assertEqual(source.read_bytes(),original)

    def test_rejects_source_not_already_open_and_does_not_switch_documents(self):
        """Verify that rejects source not already open and does not switch documents."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"selected.3dm"
            other=Path(td)/"other.3dm"
            source.write_bytes(b"source")
            other.write_bytes(b"other")
            runtime=self.runtime()
            info={"path":str(other),"modified":False,"runtime_serial_number":8}
            with mock.patch.object(RUNNER,"active_rhino_runtimes",return_value=[runtime]), \
                 mock.patch.object(RUNNER,"rhino_document_info",return_value=info), \
                 mock.patch.object(RUNNER,"rhino_tool_call") as tool_call:
                with self.assertRaisesRegex(RuntimeError,"not already open"):
                    RUNNER.require_live_rhino_source(source,{})
        tool_call.assert_not_called()

    def test_rejects_absent_live_rhino_mcp_listener(self):
        """Verify that rejects absent live rhino mcp listener."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"selected.3dm"
            source.write_bytes(b"rhino-source")
            with mock.patch.object(RUNNER,"active_rhino_runtimes",return_value=[]):
                with self.assertRaisesRegex(RuntimeError,"must already be running"):
                    RUNNER.require_live_rhino_source(source,{})

    def test_source_inference_accepts_one_saved_mcp_document_with_live_edits(self):
        """Verify that source inference accepts one saved mcp document with live edits."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"only-open.3dm"
            source.write_bytes(b"rhino-source")
            runtime=self.runtime()
            info={"path":str(source),"modified":True,"runtime_serial_number":4}
            with mock.patch.object(RUNNER,"active_rhino_runtimes",return_value=[runtime]), \
                 mock.patch.object(RUNNER,"rhino_document_info",return_value=info):
                self.assertEqual(RUNNER.discover_preopened_rhino_source(),source.resolve())

    def test_source_inference_rejects_ambiguous_live_documents(self):
        """Verify that source inference rejects ambiguous live documents."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            first=Path(td)/"first.3dm"
            second=Path(td)/"second.3dm"
            first.write_bytes(b"one")
            second.write_bytes(b"two")
            runtimes=[self.runtime("http://127.0.0.1:10501/"),
                      self.runtime("http://127.0.0.1:10502/")]
            infos=[{"path":str(first),"modified":False,"runtime_serial_number":1},
                   {"path":str(second),"modified":False,"runtime_serial_number":2}]
            with mock.patch.object(RUNNER,"active_rhino_runtimes",return_value=runtimes), \
                 mock.patch.object(RUNNER,"rhino_document_info",side_effect=infos):
                with self.assertRaisesRegex(RuntimeError,"More than one eligible Rhino document"):
                    RUNNER.discover_preopened_rhino_source()

    def test_only_rhino_step_export_warning_is_classified_as_nonfatal(self):
        """Verify that only rhino step export warning is classified as nonfatal."""
        self.assertTrue(RUNNER.is_nonfatal_rhino_step_warning("Rhino 9  STEP Export Warning"))
        self.assertTrue(RUNNER.is_nonfatal_rhino_step_warning("Rhino 8 STEP Export Warning"))
        self.assertFalse(RUNNER.is_nonfatal_rhino_step_warning("Rhino 9 Error"))
        self.assertFalse(RUNNER.is_nonfatal_rhino_step_warning("Rhino 9 File Save Warning"))
        self.assertFalse(RUNNER.is_nonfatal_rhino_step_warning("Solid Edge STEP Export Warning"))

class LiveRhinoSnapshotTests(unittest.TestCase):
    """Verify snapshot capture preserves the live Rhino document path and modified state."""
    def test_live_snapshot_uses_write3dmfile_and_preserves_live_document(self):
        """Verify that live snapshot uses write3dmfile and preserves live document."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            source=root/"source.3dm"
            snapshot=root/"run"/"Rhino3D"/"source.3dm"
            source.write_bytes(b"saved-source")
            emitted={"status":"VERIFIED","snapshot_path":str(snapshot),
                     "snapshot_bytes":14,"source_path":str(source),
                     "modified_at_capture":True,"runtime_serial_number":9,
                     "modelspace_object_count":22,"definition_count":68,
                     "definition_member_count":392,"semantic_readback":"MATCH",
                     "live_document_path_unchanged":True,
                     "live_document_modified_state_unchanged":True}
            def fake_rhino_call(url,tool,args,timeout=30):
                """Provide the fake rhino call test fixture or fake behavior."""
                self.assertEqual(tool,"run_python")
                script=args["script"]
                self.assertIn("Write3dmFile",script)
                self.assertIn("UpdateDocumentPath=False",script)
                self.assertIn("bool(_doc.Modified)!=_before_modified",script)
                self.assertIn("OpenHeadless(_target_path)",script)
                self.assertNotIn("_doc.Save()",script)
                self.assertNotIn("_doc.SaveAs(",script)
                snapshot.parent.mkdir(parents=True,exist_ok=True)
                snapshot.write_bytes(b"live-model-copy")
                return "RHINO_LIVE_SNAPSHOT "+json.dumps(emitted)
            with mock.patch.object(RUNNER,"rhino_tool_call",side_effect=fake_rhino_call):
                result=RUNNER.write_live_rhino_snapshot(
                    "http://127.0.0.1:10501/",source,snapshot,9
                )
            self.assertEqual(result["status"],"VERIFIED")
            self.assertEqual(result["modified_at_capture"],True)
            self.assertEqual(result["snapshot_sha256"],RUNNER.sha(snapshot))
            self.assertEqual(result["source_disk_sha256_at_capture"],RUNNER.sha(source))
            self.assertEqual(result["snapshot_readback"],"HEADLESS_REOPEN_AND_SEMANTIC_MODEL_MATCH")
            self.assertTrue(result["live_document_modified_state_unchanged"])


if __name__ == "__main__":
    unittest.main()

class OutputPackageContractTests(unittest.TestCase):
    """Verify output package paths, manifests and safe reuse rules remain deterministic."""
    def test_default_output_root_is_desktop_name_timestamp_without_dialog(self):
        """Verify that default output root is desktop name timestamp without dialog."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            desktop = root / "Desktop"
            desktop.mkdir()
            source = root / "models" / "sample_model.3dm"
            output = RUNNER.default_desktop_output_root(
                source, "cad_20261114_140000", desktop=desktop
            )
            self.assertEqual(output, desktop / "sample_model_20261114_140000")
            self.assertNotEqual(output.parent, source.parent)
            self.assertIn("never opens a folder dialog", RUNNER.default_desktop_output_root.__doc__)

    def test_default_output_root_uses_custom_run_id_as_safe_leaf(self):
        """Verify that default output root uses custom run id as safe leaf."""
        with tempfile.TemporaryDirectory() as td:
            desktop = Path(td) / "Desktop"
            desktop.mkdir()
            output = RUNNER.default_desktop_output_root(
                Path("Model.3dm"), "cad_trial:02", desktop=desktop
            )
            self.assertEqual(output, desktop / "Model_trial_02")


    def test_readme_and_output_inventory_use_only_the_six_requested_root_entries(self):
        """Verify that readme and output inventory use only the six requested root entries."""
        with tempfile.TemporaryDirectory() as td:
            run=Path(td)
            for name in ["Rhino3D","STEP","Parts","Assemblies","Logs"]:
                (run/name).mkdir()
            (run/"Logs"/"Reports").mkdir()
            (run/"Logs"/"Reports"/"step_export_e2e.json").write_text(
                json.dumps({"status":"VERIFIED","requested_exports":2,"verified_exports":2,"failed_exports":0}),
                encoding="utf-8")
            (run/"Logs"/"Reports"/"native_part_import_e2e.json").write_text(
                json.dumps({"status":"COMPLETED","planned_count":2,"eligible_native_import_count":2,"completed_count":2,"failed_count":0}),
                encoding="utf-8")
            (run/"Logs"/"Reports"/"assembly_build_e2e.json").write_text(
                json.dumps({"status":"COMPLETED","completed_nested_assemblies":1,"partial_nested_assemblies":0,"failed_nested_assemblies":0,
                            "root":{"status":"VERIFIED"}}),encoding="utf-8")
            RUNNER.write_output_readme(run,"COMPLETED","model.3dm","a"*64)
            self.assertEqual({p.name for p in run.iterdir()},
                             {"Rhino3D","STEP","Parts","Assemblies","Logs","README.md"})
            text=(run/"README.md").read_text(encoding="utf-8")
            self.assertIn("No AI calls are part of the conversion pipeline",text)
            self.assertIn("2/2 verified",text)
            self.assertIn("1 complete, 0 partial, 0 failed",text)

    def test_output_inventory_counts_only_the_expected_artifact_roots(self):
        """Verify that output inventory counts only the expected artifact roots."""
        with tempfile.TemporaryDirectory() as td:
            run=Path(td)
            for name in ["Rhino3D","STEP","Parts","Assemblies","Logs"]:
                (run/name).mkdir()
            (run/"STEP"/"x.stp").write_bytes(b"step")
            (run/"Parts"/"x.par").write_bytes(b"par")
            inventory=RUNNER.output_inventory(run)
            self.assertEqual(inventory["STEP"],{"files":1,"bytes":4})
            self.assertEqual(inventory["Parts"],{"files":1,"bytes":3})
