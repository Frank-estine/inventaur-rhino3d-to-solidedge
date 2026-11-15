'''Inventaur Inc. | Offline tests for safe cleanup of only the exact Solid Edge document opened by an import run.'''
from __future__ import annotations

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"


import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Scripts"))

# The importer reads a run config at module import; use a test-only isolated config.
_TEST_ROOT = Path(tempfile.gettempdir()) / "inventaur_cad_importer_unit_test"
_TEST_ROOT.mkdir(parents=True, exist_ok=True)
_TEST_CONFIG = _TEST_ROOT / "workflow_config.json"
_TEST_CONFIG.write_text(json.dumps({
    "pipeline_root": str(_TEST_ROOT),
    "reports_root": str(_TEST_ROOT / "Logs" / "Reports"),
    "logs_root": str(_TEST_ROOT / "Logs"),
    "step_root": str(_TEST_ROOT / "STEP"),
    "parts_root": str(_TEST_ROOT / "Parts"),
    "solid_edge_mcp_root": str(Path(__file__).resolve().parents[1] / "Scripts" / "SOLIDEDGE-MCP"),
}), encoding="utf-8")
os.environ["CAD_WORKFLOW_CONFIG"] = str(_TEST_CONFIG)

from inventaur_import_step_parts_native_v2 import close_owned_import_document, quarantine_unmatched_part_candidates  # noqa: E402


class FakeDocument:
    """Fake Solid Edge document that records close operations for ownership tests."""
    def __init__(self, name="Part5", full_name="Part5", doc_type=1, dirty=True):
        """Provide the   init   test fixture or fake behavior."""
        self.Name = name
        self.FullName = full_name
        self.Type = doc_type
        self.Dirty = dirty
        self.closed = False

    def Close(self):
        """Provide the Close test fixture or fake behavior."""
        self.closed = True
        self._collection.remove(self)


class FakeDocuments:
    """Collection double exposing the COM-style count and indexed document accessors."""
    def __init__(self, *documents):
        """Provide the   init   test fixture or fake behavior."""
        self._items = list(documents)
        for document in self._items:
            document._collection = self

    @property
    def Count(self):
        """Provide the Count test fixture or fake behavior."""
        return len(self._items)

    def Item(self, index):
        """Provide the Item test fixture or fake behavior."""
        return self._items[index - 1]

    def remove(self, document):
        """Provide the remove test fixture or fake behavior."""
        self._items.remove(document)


class FakeApplication:
    """Application double exposing process identity, documents and alert state."""
    def __init__(self, pid, *documents):
        """Provide the   init   test fixture or fake behavior."""
        self.ProcessID = pid
        self.Documents = FakeDocuments(*documents)
        self.DisplayAlerts = True


class ImportedDocumentCleanupTests(unittest.TestCase):
    """Verify imported-document cleanup never closes a pre-existing or ambiguously owned document."""
    def test_closes_only_imported_document_and_restores_alert_setting(self):
        """Verify that closes only imported document and restores alert setting."""
        imported = FakeDocument()
        app = FakeApplication(1234, imported)

        result = close_owned_import_document(app, 1234, imported, [])

        self.assertEqual(result["status"], "closed")
        self.assertTrue(result["dirty_discarded"])
        self.assertTrue(imported.closed)
        self.assertEqual(app.Documents.Count, 0)
        self.assertTrue(app.DisplayAlerts)

    def test_refuses_preexisting_document(self):
        """Verify that refuses preexisting document."""
        existing = FakeDocument()
        app = FakeApplication(1234, existing)

        with self.assertRaisesRegex(RuntimeError, "existed before"):
            close_owned_import_document(app, 1234, existing, [("Part5", "Part5", 1)])

        self.assertFalse(existing.closed)
        self.assertEqual(app.Documents.Count, 1)

    def test_refuses_wrong_application_pid(self):
        """Verify that refuses wrong application pid."""
        imported = FakeDocument()
        app = FakeApplication(1234, imported)

        with self.assertRaisesRegex(RuntimeError, "PID changed"):
            close_owned_import_document(app, 9999, imported, [])

        self.assertFalse(imported.closed)

    def test_refuses_ambiguous_document_identity(self):
        """Verify that refuses ambiguous document identity."""
        first = FakeDocument()
        second = FakeDocument()
        app = FakeApplication(1234, first, second)

        with self.assertRaisesRegex(RuntimeError, "not unique"):
            close_owned_import_document(app, 1234, first, [])

        self.assertFalse(first.closed)
        self.assertFalse(second.closed)


    def test_unmatched_prior_native_candidates_move_to_logs_quarantine(self):
        """Verify that unmatched prior native candidates move to logs quarantine."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parts = root / "Parts"
            logs = root / "Logs"
            parts.mkdir()
            keep = parts / "current_part.par"
            stale = parts / "stale_001_only.par"
            keep.write_bytes(b"verified-for-this-source")
            stale.write_bytes(b"old-source-candidate")
            rows = quarantine_unmatched_part_candidates(
                parts, ["Parts/current_part.par"], logs
            )
            self.assertTrue(keep.is_file())
            self.assertFalse(stale.exists())
            self.assertEqual(len(rows), 1)
            quarantined = Path(rows[0]["quarantine_path"])
            self.assertTrue(quarantined.is_file())
            self.assertEqual(quarantined.read_bytes(), b"old-source-candidate")
            self.assertEqual(rows[0]["disposition"], "MOVED_TO_QUARANTINE")

    def test_already_closed_document_is_idempotent(self):
        """Verify that already closed document is idempotent."""
        imported = FakeDocument()
        app = FakeApplication(1234)

        result = close_owned_import_document(app, 1234, imported, [])

        self.assertEqual(result["status"], "not_open")
        self.assertEqual(app.Documents.Count, 0)


if __name__ == "__main__":
    unittest.main()
