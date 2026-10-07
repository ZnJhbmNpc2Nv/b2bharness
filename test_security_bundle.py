"""Unit and integration test suite for Corporate Spec-Kit Security, CLI, and Air-Gap Packager.
Standard library only (unittest).
"""
import unittest
import os
import sys
import tempfile
import zipfile
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from server.db import SpecDatabase
from server.audit_seal import (
    compute_entry_hash,
    seal_audit_entry,
    verify_ledger_integrity,
    GENESIS_HASH,
)
from pack_offline_bundle import build_offline_bundle, ZIP_OUTPUT_PATH, DIST_DIR


class TestAuditSeal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = SpecDatabase(self.tmp.name)

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            try:
                os.remove(self.tmp.name)
            except Exception:
                pass

    def test_seeded_chain_integrity(self):
        res = verify_ledger_integrity(self.db)
        self.assertTrue(res.is_valid)
        self.assertEqual(len(res.tampered_entries), 0)
        self.assertGreaterEqual(res.total_entries, 5)

    def test_tamper_detection_payload(self):
        # Tamper with an actor name directly in sqlite
        conn = self.db.get_connection()
        conn.execute("UPDATE audit_ledger SET actor_name = 'Intruder' WHERE id = 1")
        conn.commit()
        conn.close()

        res = verify_ledger_integrity(self.db)
        self.assertFalse(res.is_valid)
        self.assertGreaterEqual(len(res.tampered_entries), 1)
        self.assertIn("Payload altered", res.tampered_entries[0]["reason"])

    def test_tamper_detection_broken_chain(self):
        # Tamper with prev_hash
        conn = self.db.get_connection()
        conn.execute("UPDATE audit_ledger SET prev_hash = 'badhash' WHERE id = 3")
        conn.commit()
        conn.close()

        res = verify_ledger_integrity(self.db)
        self.assertFalse(res.is_valid)
        self.assertGreaterEqual(len(res.tampered_entries), 1)
        self.assertIn("Broken chain link", res.tampered_entries[0]["reason"])


class TestCommandLineInterface(unittest.TestCase):
    def setUp(self):
        self.cli_py = os.path.join(SCRIPT_DIR, "cli.py")

    def run_cli(self, *cmd_args):
        cmd = [sys.executable, self.cli_py] + list(cmd_args)
        return subprocess.run(cmd, cwd=SCRIPT_DIR, capture_output=True, text=True, encoding="utf-8")

    def test_cli_list(self):
        res = self.run_cli("list")
        self.assertEqual(res.returncode, 0)
        self.assertIn("REQ-SEC-001", res.stdout)
        self.assertIn("Specification Requirements", res.stdout)

    def test_cli_matrix(self):
        res = self.run_cli("matrix")
        self.assertEqual(res.returncode, 0)
        self.assertIn("REQUIREMENTS TRACEABILITY MATRIX", res.stdout)
        self.assertIn("Overall Coverage", res.stdout)

    def test_cli_audit_verify(self):
        res = self.run_cli("audit-verify")
        self.assertEqual(res.returncode, 0)
        self.assertIn("CRYPTOGRAPHIC AUDIT SEAL INTEGRITY CHECK", res.stdout)
        self.assertIn("INTEGRITY AUDIT: 100% VERIFIED", res.stdout)

    def test_cli_provenance(self):
        res = self.run_cli("provenance", "REQ-SEC-001")
        self.assertEqual(res.returncode, 0)
        self.assertIn("LINEAGE & PROVENANCE TRACE", res.stdout)
        self.assertIn("ORIGINS", res.stdout)

    def test_cli_diff(self):
        res = self.run_cli("diff", "REQ-SEC-001", "1", "2")
        self.assertEqual(res.returncode, 0)
        self.assertIn("REQUIREMENT AUDIT DIFF", res.stdout)

    def test_cli_clarify(self):
        res = self.run_cli("clarify")
        self.assertEqual(res.returncode, 0)
        self.assertIn("CLAR-001", res.stdout)

    def test_cli_export_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            res = self.run_cli("export-md", "--output", tmpdir)
            self.assertEqual(res.returncode, 0)
            self.assertIn("Exporting Spec-Kit Markdown Bundle", res.stdout)


class TestOfflinePackaging(unittest.TestCase):
    def test_package_bundle_and_verify(self):
        build_offline_bundle()
        self.assertTrue(os.path.exists(ZIP_OUTPUT_PATH))
        self.assertGreater(os.path.getsize(ZIP_OUTPUT_PATH), 10000)

        # Extract and verify integrity
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(ZIP_OUTPUT_PATH, "r") as zf:
                zf.extractall(tmpdir)

            verify_script = os.path.join(tmpdir, "VERIFY_CHECKSUMS.py")
            self.assertTrue(os.path.exists(verify_script))

            res = subprocess.run([sys.executable, verify_script], cwd=tmpdir, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(res.returncode, 0, f"Verifier failed: {res.stdout}\n{res.stderr}")
            self.assertIn("INTEGRITY AUDIT PASSED", res.stdout)


if __name__ == "__main__":
    unittest.main()
