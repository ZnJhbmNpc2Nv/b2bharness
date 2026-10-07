#!/usr/bin/env python3
"""Corporate Spec-Kit: Comprehensive Standalone Test Suite.

Standard-library `unittest` execution.
ZERO external dependencies; runs on standard Python 3.8+ on any corporate air-gapped machine.
Covers:
  - TestSuite 1: Database Operations & Schema Integrity (TestDatabase)
  - TestSuite 2: Unified & HTML Diff Engine (TestDiffEngine)
  - TestSuite 3: Provenance Graph & Lineage Engine (TestLineageEngine)
  - TestSuite 4: Spec-Kit Markdown Sync & Standalone HTML Exporter (TestMarkdownSync)
  - TestSuite 5: App HTTP Server Handler & REST API Simulation (TestHttpServer)
"""
import os
import sys
import json
import time
import shutil
import tempfile
import unittest
import threading
import urllib.request
import urllib.parse
import urllib.error
from http.server import ThreadingHTTPServer

# Ensure server module is importable
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from server.db import SpecDatabase, get_iso_now
from server.diff_engine import compute_unified_diff, compute_html_diff, diff_requirement_payload
from server.lineage import LineageEngine
from server.markdown_sync import MarkdownSync
from server.ai_bridge import AIBridge
from server.app import SpecKitRequestHandler


# ==============================================================================
# TestSuite 1: Database Operations (TestDatabase)
# ==============================================================================
class TestDatabase(unittest.TestCase):
    """Verifies SQLite WAL initialization, seeding, CRUD operations, revisions, and audit ledger."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="speckit_test_db_")
        self.db_path = os.path.join(self.temp_dir, "test_speckit.db")
        self.db = SpecDatabase(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_database_initialization_and_wal_mode(self):
        """Verify database creation, WAL journal mode, foreign key enforcement, and tables."""
        with self.db.get_connection() as conn:
            # Check journal mode
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(journal.lower(), "wal")

            # Check foreign keys
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            self.assertEqual(fk, 1)

            # Check all required tables exist
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            required_tables = [
                "projects",
                "requirements",
                "requirement_revisions",
                "clarifications",
                "tasks",
                "lineage_nodes",
                "lineage_edges",
                "audit_ledger",
                "settings"
            ]
            for t in required_tables:
                self.assertIn(t, tables, f"Expected table '{t}' to be created in database")

    def test_default_project_seeding(self):
        """Verify default seeded project (Corporate Air-Gapped Secure Gateway) and its artifacts."""
        projects = self.db.list_projects()
        self.assertEqual(len(projects), 1)

        proj = projects[0]
        self.assertEqual(proj["id"], "proj-airgap-gateway")
        self.assertEqual(proj["title"], "Corporate Air-Gapped Secure Gateway")
        self.assertEqual(proj["status"], "APPROVED")
        self.assertIn("Enterprise Security Constitution", proj["constitution"])
        self.assertIn("Zero External Egress", proj["constitution"])

        # Check seeded requirements
        reqs = self.db.list_requirements("proj-airgap-gateway")
        self.assertGreaterEqual(len(reqs), 3)
        req_ids = [r["id"] for r in reqs]
        self.assertIn("REQ-SEC-001", req_ids)
        self.assertIn("REQ-LOG-002", req_ids)
        self.assertIn("REQ-RT-003", req_ids)

        # Check acceptance criteria parsing
        sec_req = self.db.get_requirement("REQ-SEC-001")
        self.assertIsNotNone(sec_req)
        self.assertIsInstance(sec_req["acceptance_criteria"], list)
        self.assertGreater(len(sec_req["acceptance_criteria"]), 0)

        # Check requirement revisions (REQ-SEC-001 has v1 and v2)
        revs = self.db.get_requirement_revisions("REQ-SEC-001")
        self.assertEqual(len(revs), 2)
        self.assertEqual(revs[0]["version"], 1)
        self.assertEqual(revs[0]["change_type"], "CREATED")
        self.assertEqual(revs[1]["version"], 2)
        self.assertEqual(revs[1]["change_type"], "MODIFIED")
        self.assertIsNotNone(revs[1]["diff_unified"])

        # Check clarifications seeded
        clars = self.db.list_clarifications("proj-airgap-gateway")
        self.assertGreaterEqual(len(clars), 1)
        self.assertEqual(clars[0]["id"], "CLAR-001")
        self.assertEqual(clars[0]["status"], "RESOLVED")

        # Check tasks seeded
        tasks = self.db.list_tasks("proj-airgap-gateway")
        self.assertGreaterEqual(len(tasks), 3)

        # Check lineage nodes and edges seeded
        lineage = self.db.list_lineage("proj-airgap-gateway")
        self.assertGreater(len(lineage["nodes"]), 5)
        self.assertGreater(len(lineage["edges"]), 5)

        # Check audit ledger
        audits = self.db.list_audit("proj-airgap-gateway")
        self.assertGreater(len(audits), 0)

    def test_requirement_creation_and_version_bumping(self):
        """Test requirement creation, version increment, revision ledger persistence, and audit logging."""
        spec_id = "proj-airgap-gateway"
        req_id = "REQ-CRYPTO-010"

        created = self.db.create_requirement(
            spec_id=spec_id,
            req_id=req_id,
            category="SECURITY",
            title="Hardware Security Module Token Storage",
            description="All symmetric keys must reside strictly within a FIPS 140-3 Level 3 HSM.",
            rationale="Protects against memory-dump key extraction attacks on corporate host servers.",
            acceptance_criteria=[
                "Given a request to sign payload, when key is referenced, then signing occurs inside HSM boundary.",
                "Key export operations in plaintext are hardware-rejected."
            ],
            author_name="Alice Vance",
            author_role="Cryptographic Architect",
            justification="Mandated by Corporate Security Policy section 4.2"
        )

        self.assertIsNotNone(created)
        self.assertEqual(created["id"], req_id)
        self.assertEqual(created["current_version"], 1)
        self.assertEqual(created["status"], "PROPOSED")

        # Verify revision ledger
        revs = self.db.get_requirement_revisions(req_id)
        self.assertEqual(len(revs), 1)
        self.assertEqual(revs[0]["version"], 1)
        self.assertEqual(revs[0]["author_name"], "Alice Vance")
        self.assertEqual(revs[0]["change_type"], "CREATED")

        # Verify audit ledger recorded creation
        audits = self.db.list_audit(spec_id)
        created_events = [a for a in audits if a["entity_id"] == req_id and a["action"] == "CREATED"]
        self.assertEqual(len(created_events), 1)
        self.assertEqual(created_events[0]["actor_name"], "Alice Vance")

        # Now update requirement (bump version to 2)
        diff_str = "--- v1\n+++ v2\n@@ -1 +1 @@\n-FIPS 140-3 Level 3 HSM\n+FIPS 140-3 Level 4 HSM with PKCS#11 v3.0"
        updated = self.db.update_requirement(
            req_id=req_id,
            category="SECURITY",
            title="Hardware Security Module Token Storage (Level 4)",
            description="All symmetric keys must reside strictly within a FIPS 140-3 Level 4 HSM with PKCS#11 v3.0.",
            rationale="Updated to Level 4 physical tamper envelope per internal pentest results.",
            acceptance_criteria=[
                "Given a request to sign payload, when key is referenced, then signing occurs inside HSM boundary.",
                "Key export operations in plaintext are hardware-rejected.",
                "Zeroize all keys on physical chassis enclosure opening."
            ],
            status="ACCEPTED",
            author_name="Bob Thorne",
            author_role="Lead Auditor",
            justification="Upgraded physical enclosure tamper requirement after pentest report.",
            diff_unified=diff_str
        )

        self.assertEqual(updated["current_version"], 2)
        self.assertEqual(updated["status"], "ACCEPTED")

        # Verify revision ledger has 2 versions
        revs_after = self.db.get_requirement_revisions(req_id)
        self.assertEqual(len(revs_after), 2)
        self.assertEqual(revs_after[1]["version"], 2)
        self.assertEqual(revs_after[1]["author_name"], "Bob Thorne")
        self.assertEqual(revs_after[1]["change_type"], "MODIFIED")
        self.assertEqual(revs_after[1]["diff_unified"], diff_str)

        # Verify audit ledger recorded modification
        audits_after = self.db.list_audit(spec_id)
        mod_events = [a for a in audits_after if a["entity_id"] == req_id and a["action"] == "MODIFIED"]
        self.assertEqual(len(mod_events), 1)

    def test_clarification_lifecycle(self):
        """Test clarification creation, status, and resolution."""
        spec_id = "proj-airgap-gateway"
        clar_id = "CLAR-050"

        # Create clarification
        clar = self.db.add_clarification(
            spec_id=spec_id,
            clar_id=clar_id,
            req_id="REQ-SEC-001",
            question="What is the certificate revocation list (CRL) timeout in offline mode?",
            asked_by="Dev Engineer",
            asked_role="Backend Developer"
        )
        self.assertEqual(clar["id"], clar_id)
        self.assertEqual(clar["status"], "OPEN")
        self.assertIsNone(clar.get("answer"))

        # Verify audit log recorded question
        audits = self.db.list_audit(spec_id)
        q_events = [a for a in audits if a["entity_id"] == clar_id and a["action"] == "QUESTION_ASKED"]
        self.assertEqual(len(q_events), 1)

        # Resolve clarification
        resolved = self.db.resolve_clarification(
            clar_id=clar_id,
            answer="Offline CRL validity window is 72 hours before fallback warning.",
            answered_by="Elena Voronova",
            answered_role="Chief Security Architect"
        )
        self.assertEqual(resolved["status"], "RESOLVED")
        self.assertEqual(resolved["answered_by"], "Elena Voronova")
        self.assertIsNotNone(resolved["resolved_at"])

        # Verify audit log recorded resolution
        audits_res = self.db.list_audit(spec_id)
        r_events = [a for a in audits_res if a["entity_id"] == clar_id and a["action"] == "RESOLVED"]
        self.assertEqual(len(r_events), 1)

    def test_task_creation_and_status_transition(self):
        """Test task creation, lineage edge synthesis, and status transition."""
        spec_id = "proj-airgap-gateway"
        task_id = "TASK-099"

        task = self.db.create_task(
            spec_id=spec_id,
            task_id=task_id,
            req_id="REQ-RT-003",
            title="Implement Trie route matcher",
            description="Build O(k) prefix matching lookup table in Python standard library.",
            assignee="Alex Lead",
            test_case_id="TEST-RT-001",
            code_targets="sec_gateway/router.py:TrieRouter"
        )
        self.assertEqual(task["id"], task_id)
        self.assertEqual(task["status"], "TODO")

        # Verify lineage links created
        lineage = self.db.list_lineage(spec_id)
        task_nodes = [n for n in lineage["nodes"] if n["entity_id"] == task_id]
        self.assertEqual(len(task_nodes), 1)
        self.assertEqual(task_nodes[0]["node_type"], "TASK")

        # Check edge: REQ-RT-003 -> TASK-099
        implements_edges = [e for e in lineage["edges"] if e["relation"] == "IMPLEMENTS" and e["to_node_id"] == f"node-{task_id}"]
        self.assertEqual(len(implements_edges), 1)

        # Transition task status to DONE
        updated_task = self.db.update_task_status(task_id, "DONE", actor_name="Alex Lead", actor_role="Developer")
        self.assertEqual(updated_task["status"], "DONE")

        # Check audit ledger
        audits = self.db.list_audit(spec_id)
        status_events = [a for a in audits if a["entity_id"] == task_id and a["action"] == "STATUS_CHANGED"]
        self.assertEqual(len(status_events), 1)

    def test_settings_storage(self):
        """Test KV settings retrieval and update."""
        self.assertEqual(self.db.get_setting("non_existent", "default_val"), "default_val")
        self.db.set_setting("ai_endpoint", "http://10.20.30.40:11434/v1")
        self.assertEqual(self.db.get_setting("ai_endpoint"), "http://10.20.30.40:11434/v1")


# ==============================================================================
# TestSuite 2: Diff Engine (TestDiffEngine)
# ==============================================================================
class TestDiffEngine(unittest.TestCase):
    """Verifies difflib-based unified and HTML diff computation and field-level requirement change analysis."""

    def test_unified_diff_generation(self):
        """Verify unified diff generation with difflib."""
        old_text = "Line 1: Zero External Egress\nLine 2: TLS 1.2 allowed\nLine 3: Disk log"
        new_text = "Line 1: Zero External Egress\nLine 2: TLS 1.3 strictly required\nLine 3: Disk log"

        diff = compute_unified_diff(old_text, new_text, old_label="v1", new_label="v2")
        self.assertIn("--- v1", diff)
        self.assertIn("+++ v2", diff)
        self.assertIn("-Line 2: TLS 1.2 allowed", diff)
        self.assertIn("+Line 2: TLS 1.3 strictly required", diff)

        # Identical text yields no diff lines
        identical_diff = compute_unified_diff("Constant Text", "Constant Text")
        self.assertEqual(identical_diff, "")

    def test_html_diff_markup_generation(self):
        """Verify color-coded HTML diff markup generation with additions, deletions, and escaping."""
        old_text = "Rule A: Allowed\nRule B: Deprecated <script>\nRule C: Keep"
        new_text = "Rule A: Allowed\nRule B: Replaced with <b>Strict</b>\nRule C: Keep"

        html_diff = compute_html_diff(old_text, new_text)
        self.assertIn('<div class="diff-container">', html_diff)
        self.assertIn('<div class="diff-line diff-equal">', html_diff)
        self.assertIn('<div class="diff-line diff-delete">', html_diff)
        self.assertIn('<div class="diff-line diff-insert">', html_diff)
        self.assertTrue(html_diff.endswith('</div>'))

        # Verify HTML escaping prevents XSS injection in diff viewing
        self.assertIn("&lt;script&gt;", html_diff)
        self.assertNotIn("<script>", html_diff)
        self.assertIn("&lt;b&gt;Strict&lt;/b&gt;", html_diff)

    def test_field_level_requirement_diff_detection(self):
        """Verify field-level requirement payload difference detection."""
        old_req = {
            "version": 1,
            "title": "Basic Gateway Routing",
            "description": "Routes requests by path prefix.",
            "rationale": "Microservice dispatching.",
            "acceptance_criteria": ["Given path /api/v1, routed to v1 upstream."],
            "category": "FUNCTIONAL",
            "status": "PROPOSED"
        }

        new_req = {
            "version": 2,
            "title": "Dynamic Gateway Routing with Circuit Breaker",
            "description": "Routes requests by path prefix and opens breaker on 5xx failures.",
            "rationale": "Microservice dispatching with high availability resilience.",
            "acceptance_criteria": [
                "Given path /api/v1, routed to v1 upstream.",
                "Given 3 consecutive 502 errors, circuit breaker trips."
            ],
            "category": "FUNCTIONAL",
            "status": "ACCEPTED"
        }

        changes = diff_requirement_payload(old_req, new_req)

        # Title, description, rationale, acceptance_criteria, and status changed
        self.assertIn("title", changes)
        self.assertIn("description", changes)
        self.assertIn("rationale", changes)
        self.assertIn("acceptance_criteria", changes)
        self.assertIn("status", changes)
        # Category was identical
        self.assertNotIn("category", changes)

        # Check each change dictionary format
        for field, detail in changes.items():
            self.assertIn("before", detail)
            self.assertIn("after", detail)
            self.assertIn("unified", detail)
            self.assertIn("html", detail)

        self.assertIn("Circuit Breaker", changes["title"]["after"])
        self.assertIn("- Given 3 consecutive", changes["acceptance_criteria"]["after"])

        # Identical payload yields empty changes
        no_changes = diff_requirement_payload(new_req, new_req)
        self.assertEqual(no_changes, {})


# ==============================================================================
# TestSuite 3: Lineage & Provenance Engine (TestLineageEngine)
# ==============================================================================
class TestLineageEngine(unittest.TestCase):
    """Verifies graph loading, backwards BFS provenance traversal, descendant traversal, and RTM."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="speckit_test_lineage_")
        self.db_path = os.path.join(self.temp_dir, "test_speckit.db")
        self.db = SpecDatabase(self.db_path)
        self.engine = LineageEngine(self.db)
        self.spec_id = "proj-airgap-gateway"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_graph_loading(self):
        """Verify full graph data loading for the spec."""
        graph = self.engine.get_graph_data(self.spec_id)
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertGreaterEqual(len(graph["nodes"]), 9)
        self.assertGreaterEqual(len(graph["edges"]), 9)

        node_ids = {n["id"] for n in graph["nodes"]}
        self.assertIn("node-intent", node_ids)
        self.assertIn("node-const", node_ids)
        self.assertIn("node-req-sec", node_ids)
        self.assertIn("node-task-01", node_ids)
        self.assertIn("node-test-01", node_ids)
        self.assertIn("node-code-01", node_ids)

    def test_backwards_provenance_traversal(self):
        """Verify backwards BFS provenance traversal ('Откуда что родилось')."""
        # Trace origin of CODE artifact: node-code-01 (sec_gateway/tls.py)
        result = self.engine.trace_node_provenance(self.spec_id, "node-code-01")

        self.assertIsNotNone(result["target_node"])
        self.assertEqual(result["target_node"]["id"], "node-code-01")

        ancestor_ids = {n["id"] for n in result["ancestor_nodes"]}
        # In seeded graph:
        # node-intent -> node-req-sec
        # node-const  -> node-req-sec
        # node-req-sec -> node-task-01 -> node-code-01
        self.assertIn("node-task-01", ancestor_ids, "Code must trace up to its implementing task")
        self.assertIn("node-req-sec", ancestor_ids, "Code must trace up to its root requirement")
        self.assertIn("node-intent", ancestor_ids, "Code must trace up to the business intent")
        self.assertIn("node-const", ancestor_ids, "Code must trace up to the corporate constitution")

        # Verify edge IDs collected
        self.assertGreaterEqual(len(result["ancestor_edge_ids"]), 3)

        # Trace origin of TEST artifact: node-test-01
        test_prov = self.engine.trace_node_provenance(self.spec_id, "node-test-01")
        test_ancestor_ids = {n["id"] for n in test_prov["ancestor_nodes"]}
        self.assertIn("node-task-01", test_ancestor_ids)
        self.assertIn("node-req-sec", test_ancestor_ids)

    def test_forward_descendant_traversal(self):
        """Verify forward descendant traversal to find all downstream impacts."""
        # Trace impact of requirement: node-req-sec
        result = self.engine.trace_node_provenance(self.spec_id, "node-req-sec")
        descendant_ids = {n["id"] for n in result["descendant_nodes"]}

        self.assertIn("node-clar-01", descendant_ids, "Requirement has clarification child")
        self.assertIn("node-task-01", descendant_ids, "Requirement has task child")
        self.assertIn("node-test-01", descendant_ids, "Requirement transitively has test child")
        self.assertIn("node-code-01", descendant_ids, "Requirement transitively has code child")

        # Trace impact of root intent
        intent_res = self.engine.trace_node_provenance(self.spec_id, "node-intent")
        intent_desc_ids = {n["id"] for n in intent_res["descendant_nodes"]}
        self.assertIn("node-req-sec", intent_desc_ids)
        self.assertIn("node-req-log", intent_desc_ids)
        self.assertIn("node-req-rt", intent_desc_ids)
        self.assertIn("node-code-01", intent_desc_ids)

    def test_traceability_matrix_and_orphan_detection(self):
        """Verify RTM calculation, coverage percentage score, and orphan requirement detection."""
        matrix_data = self.engine.generate_traceability_matrix(self.spec_id)

        self.assertEqual(matrix_data["total_requirements"], 3)
        self.assertEqual(matrix_data["total_tasks"], 3)
        self.assertEqual(len(matrix_data["orphan_requirements"]), 0)
        self.assertGreater(matrix_data["overall_coverage_pct"], 0)

        # REQ-SEC-001 has TASK-001 which has both test_case_id and code_targets (3/3 pts = 100%)
        sec_entry = next((m for m in matrix_data["matrix"] if m["req_id"] == "REQ-SEC-001"), None)
        self.assertIsNotNone(sec_entry)
        self.assertEqual(sec_entry["coverage_pct"], 100)
        self.assertTrue(sec_entry["is_complete"])

        # Add an ORPHAN requirement with NO tasks
        orphan_id = "REQ-ORPHAN-999"
        self.db.create_requirement(
            spec_id=self.spec_id,
            req_id=orphan_id,
            category="SECURITY",
            title="Unallocated Air-Gapped Firewall Filter",
            description="Filter raw ethernet packets.",
            rationale="DDoS defense",
            acceptance_criteria=["Drops malformed ARP frames."],
            author_name="Alice",
            author_role="Sec"
        )

        matrix_with_orphan = self.engine.generate_traceability_matrix(self.spec_id)
        self.assertEqual(matrix_with_orphan["total_requirements"], 4)
        self.assertIn(orphan_id, matrix_with_orphan["orphan_requirements"])

        orphan_entry = next((m for m in matrix_with_orphan["matrix"] if m["req_id"] == orphan_id), None)
        self.assertIsNotNone(orphan_entry)
        self.assertEqual(orphan_entry["coverage_pct"], 0)
        self.assertFalse(orphan_entry["is_complete"])

        # Now allocate a task for this orphan requirement
        self.db.create_task(
            spec_id=self.spec_id,
            task_id="TASK-FIREWALL-01",
            req_id=orphan_id,
            title="Implement ARP filter",
            description="Ethernet frame parser",
            assignee="Net Team",
            test_case_id="TEST-ARP-01",
            code_targets="sec_gateway/arp.py"
        )

        matrix_resolved = self.engine.generate_traceability_matrix(self.spec_id)
        self.assertNotIn(orphan_id, matrix_resolved["orphan_requirements"])
        resolved_entry = next((m for m in matrix_resolved["matrix"] if m["req_id"] == orphan_id), None)
        self.assertEqual(resolved_entry["coverage_pct"], 100)
        self.assertTrue(resolved_entry["is_complete"])


# ==============================================================================
# TestSuite 4: Markdown Synchronizer & HTML Exporter (TestMarkdownSync)
# ==============================================================================
class TestMarkdownSync(unittest.TestCase):
    """Verifies generation of all 7 Spec-Kit markdown documents and standalone HTML dossier."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="speckit_test_sync_")
        self.db_path = os.path.join(self.temp_dir, "test_speckit.db")
        self.db = SpecDatabase(self.db_path)
        self.sync = MarkdownSync(self.db, output_base_dir=self.temp_dir)
        self.spec_id = "proj-airgap-gateway"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_export_speckit_bundle_all_7_files(self):
        """Verify generation of all 7 Spec-Kit markdown files (00_constitution.md to 06_revisions_ledger.md)."""
        files = self.sync.export_speckit_bundle(self.spec_id)

        expected_files = [
            "00_constitution.md",
            "01_spec.md",
            "02_clarifications.md",
            "03_plan.md",
            "04_tasks.md",
            "05_traceability_matrix.md",
            "06_revisions_ledger.md"
        ]

        # Verify all 7 files in dictionary
        self.assertEqual(len(files), 7, f"Expected 7 files, got {list(files.keys())}")
        for filename in expected_files:
            self.assertIn(filename, files, f"Missing expected Spec-Kit file: {filename}")

        # Verify physical disk files
        bundle_dir = os.path.join(self.temp_dir, self.spec_id)
        for filename in expected_files:
            disk_path = os.path.join(bundle_dir, filename)
            self.assertTrue(os.path.isfile(disk_path), f"File {disk_path} was not written to disk")
            with open(disk_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertGreater(len(content), 20, f"File {filename} is suspiciously empty")

        # Specific file content assertions:
        # 1. 00_constitution.md
        self.assertIn("# Project Constitution: Corporate Air-Gapped Secure Gateway", files["00_constitution.md"])
        self.assertIn("Zero External Egress", files["00_constitution.md"])

        # 2. 01_spec.md
        self.assertIn("# Formal Specification: Corporate Air-Gapped Secure Gateway", files["01_spec.md"])
        self.assertIn("REQ-SEC-001", files["01_spec.md"])
        self.assertIn("Acceptance Criteria", files["01_spec.md"])

        # 3. 02_clarifications.md
        self.assertIn("# Clarification Interview Loop", files["02_clarifications.md"])
        self.assertIn("CLAR-001", files["02_clarifications.md"])

        # 4. 03_plan.md
        self.assertIn("# Architectural Plan & Technical Blueprint", files["03_plan.md"])
        self.assertIn("Phase Breakdown & Component Mapping", files["03_plan.md"])

        # 5. 04_tasks.md
        self.assertIn("# Engineering Tasks", files["04_tasks.md"])
        self.assertIn("TASK-001", files["04_tasks.md"])

        # 6. 05_traceability_matrix.md
        self.assertIn("# Requirement Traceability Matrix (RTM)", files["05_traceability_matrix.md"])
        self.assertIn("Overall Coverage", files["05_traceability_matrix.md"])

        # 7. 06_revisions_ledger.md
        self.assertIn("# Requirement Revision Ledger & Change History", files["06_revisions_ledger.md"])
        self.assertIn("```diff", files["06_revisions_ledger.md"])
        self.assertIn("Dmitry Petrov", files["06_revisions_ledger.md"])

    def test_export_standalone_html(self):
        """Verify generation of standalone, offline single-file HTML dossier."""
        html_content = self.sync.export_standalone_html(self.spec_id)

        self.assertIsInstance(html_content, str)
        self.assertTrue(html_content.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Spec-Kit Dossier: Corporate Air-Gapped Secure Gateway</title>", html_content)
        self.assertIn("window.__SPECKIT_DATA__ =", html_content)
        self.assertIn("1. Business Intent & Background", html_content)
        self.assertIn("2. Enterprise Security Constitution", html_content)
        self.assertIn("3. Traceability Matrix (RTM)", html_content)
        self.assertIn("4. Requirements Ledger & Revision Attribution", html_content)
        self.assertIn("5. Clarification Q&A Loop", html_content)
        self.assertIn("6. Activity Audit Ledger", html_content)

        # Verify completely offline: no remote CDNs or external web fonts
        self.assertNotIn("http://", html_content)
        self.assertNotIn("https://", html_content)


# ==============================================================================
# TestSuite 5: App HTTP Server Handler Simulation (TestHttpServer)
# ==============================================================================
class TestHttpServer(unittest.TestCase):
    """Verifies standard-library HTTP server request routing, JSON payloads, and REST API behavior."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="speckit_test_http_")
        cls.db_path = os.path.join(cls.temp_dir, "test_speckit.db")
        cls.static_dir = os.path.join(cls.temp_dir, "static")
        os.makedirs(cls.static_dir, exist_ok=True)

        cls.db = SpecDatabase(cls.db_path)
        cls.lineage = LineageEngine(cls.db)
        cls.sync = MarkdownSync(cls.db, output_base_dir=cls.temp_dir)
        cls.ai = AIBridge(cls.db)

        # Inject into SpecKitRequestHandler
        SpecKitRequestHandler.db = cls.db
        SpecKitRequestHandler.lineage = cls.lineage
        SpecKitRequestHandler.sync = cls.sync
        SpecKitRequestHandler.ai = cls.ai
        SpecKitRequestHandler.static_dir = cls.static_dir

        # Bind to ephemeral port 0
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), SpecKitRequestHandler)
        cls.port = cls.httpd.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        # Run server loop in background daemon thread
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def _http_request(self, method: str, path: str, payload: dict = None) -> tuple:
        """Helper to make HTTP requests using standard library urllib."""
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                status = resp.status
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read()
                if "application/json" in content_type:
                    data = json.loads(raw.decode("utf-8"))
                else:
                    data = raw.decode("utf-8", errors="replace")
                return status, data
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                err_data = json.loads(raw.decode("utf-8"))
            except Exception:
                err_data = raw.decode("utf-8", errors="replace")
            return e.code, err_data

    def test_get_projects(self):
        """Verify GET /api/projects returns seeded project."""
        status, data = self._http_request("GET", "/api/projects")
        self.assertEqual(status, 200)
        self.assertIn("projects", data)
        self.assertGreaterEqual(len(data["projects"]), 1)
        self.assertEqual(data["projects"][0]["id"], "proj-airgap-gateway")

    def test_get_requirements(self):
        """Verify GET /api/requirements returns all requirements for spec."""
        status, data = self._http_request("GET", "/api/requirements?spec_id=proj-airgap-gateway")
        self.assertEqual(status, 200)
        self.assertIn("requirements", data)
        req_ids = [r["id"] for r in data["requirements"]]
        self.assertIn("REQ-SEC-001", req_ids)
        self.assertIn("REQ-LOG-002", req_ids)

    def test_get_single_requirement_and_revisions(self):
        """Verify GET /api/requirements/<id> and GET /api/requirements/<id>/revisions."""
        status, req = self._http_request("GET", "/api/requirements/REQ-SEC-001")
        self.assertEqual(status, 200)
        self.assertEqual(req["id"], "REQ-SEC-001")
        self.assertEqual(req["current_version"], 2)

        status, rev_data = self._http_request("GET", "/api/requirements/REQ-SEC-001/revisions")
        self.assertEqual(status, 200)
        self.assertIn("revisions", rev_data)
        self.assertEqual(len(rev_data["revisions"]), 2)

    def test_get_lineage_and_trace(self):
        """Verify GET /api/lineage and GET /api/lineage/trace."""
        status, data = self._http_request("GET", "/api/lineage?spec_id=proj-airgap-gateway")
        self.assertEqual(status, 200)
        self.assertIn("nodes", data)
        self.assertIn("edges", data)

        # Test trace endpoint for provenance traversal
        status, trace = self._http_request("GET", "/api/lineage/trace?spec_id=proj-airgap-gateway&node_id=node-code-01")
        self.assertEqual(status, 200)
        self.assertIn("ancestor_nodes", trace)
        ancestor_ids = [n["id"] for n in trace["ancestor_nodes"]]
        self.assertIn("node-task-01", ancestor_ids)

    def test_get_matrix(self):
        """Verify GET /api/matrix returns RTM and coverage score."""
        status, data = self._http_request("GET", "/api/matrix?spec_id=proj-airgap-gateway")
        self.assertEqual(status, 200)
        self.assertIn("matrix", data)
        self.assertIn("overall_coverage_pct", data)
        self.assertIn("orphan_requirements", data)
        self.assertIsInstance(data["overall_coverage_pct"], int)

    def test_get_audit(self):
        """Verify GET /api/audit returns audit events."""
        status, data = self._http_request("GET", "/api/audit?spec_id=proj-airgap-gateway")
        self.assertEqual(status, 200)
        self.assertIn("audit_log", data)
        self.assertGreater(len(data["audit_log"]), 0)

    def test_post_and_put_requirement(self):
        """Verify POST /api/requirements (create) and PUT /api/requirements/<id> (update/diff/version bump)."""
        req_id = "REQ-HTTP-API-TEST"
        post_payload = {
            "spec_id": "proj-airgap-gateway",
            "id": req_id,
            "category": "FUNCTIONAL",
            "title": "Air-Gapped Health & Status Endpoint",
            "description": "Provide /status HTTP GET endpoint returning local subsystem status without network egress.",
            "rationale": "Internal watchdog monitoring.",
            "acceptance_criteria": [
                "Endpoint returns 200 OK within 10ms.",
                "Response JSON contains subsystem check statuses."
            ],
            "author_name": "Integration Tester",
            "author_role": "QA Engineer",
            "justification": "Initial requirement specification via REST API"
        }

        # 1. POST (Create)
        status, created = self._http_request("POST", "/api/requirements", post_payload)
        self.assertEqual(status, 201)
        self.assertEqual(created["id"], req_id)
        self.assertEqual(created["current_version"], 1)

        # 2. PUT (Update)
        put_payload = {
            "title": "Air-Gapped Health, Status & Metrics Endpoint",
            "category": "FUNCTIONAL",
            "description": "Provide /status and /metrics endpoints returning subsystem status and memory statistics.",
            "rationale": "Internal watchdog monitoring and capacity surveillance.",
            "acceptance_criteria": [
                "Endpoint returns 200 OK within 10ms.",
                "Response JSON contains subsystem check statuses.",
                "Memory statistics must report RSS and heap allocation."
            ],
            "status": "ACCEPTED",
            "author_name": "Senior Architect",
            "author_role": "Tech Lead",
            "justification": "Augmented requirement with memory stats per capacity review."
        }

        status, updated = self._http_request("PUT", f"/api/requirements/{req_id}", put_payload)
        self.assertEqual(status, 200)
        self.assertEqual(updated["id"], req_id)
        self.assertEqual(updated["current_version"], 2)
        self.assertEqual(updated["status"], "ACCEPTED")

        # 3. Verify revisions via API
        status, rev_data = self._http_request("GET", f"/api/requirements/{req_id}/revisions")
        self.assertEqual(status, 200)
        self.assertEqual(len(rev_data["revisions"]), 2)
        self.assertIn("diff_unified", rev_data["revisions"][1])
        self.assertIn("Memory statistics", rev_data["revisions"][1]["diff_unified"])

    def test_post_clarification_and_resolve(self):
        """Verify POST /api/clarifications and POST /api/clarifications/<id>/resolve."""
        post_payload = {
            "spec_id": "proj-airgap-gateway",
            "req_id": "REQ-SEC-001",
            "question": "What is the maximum allowed cipher suite count supported?",
            "asked_by": "Crypto Dev",
            "asked_role": "Dev"
        }
        status, clar = self._http_request("POST", "/api/clarifications", post_payload)
        self.assertEqual(status, 201)
        cid = clar["id"]
        self.assertEqual(clar["status"], "OPEN")

        # Resolve
        resolve_payload = {
            "answer": "Only 3 TLS 1.3 ciphers: AES-256-GCM, CHACHA20-POLY1305, AES-128-GCM.",
            "answered_by": "Sec Architect",
            "answered_role": "Architect"
        }
        status, res = self._http_request("POST", f"/api/clarifications/{cid}/resolve", resolve_payload)
        self.assertEqual(status, 200)
        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(res["answer"], resolve_payload["answer"])

    def test_post_task_and_status_update(self):
        """Verify POST /api/tasks and POST /api/tasks/<id>/status."""
        task_payload = {
            "spec_id": "proj-airgap-gateway",
            "req_id": "REQ-SEC-001",
            "title": "Configure strict TLS 1.3 cipher suites",
            "description": "Set context ciphersuite string",
            "assignee": "Alex",
            "test_case_id": "TEST-CIPHER-01",
            "code_targets": "sec_gateway/tls.py:configure_ciphers"
        }
        status, task = self._http_request("POST", "/api/tasks", task_payload)
        self.assertEqual(status, 201)
        tid = task["id"]
        self.assertEqual(task["status"], "TODO")

        # Update status
        status, updated = self._http_request("POST", f"/api/tasks/{tid}/status", {"status": "DONE"})
        self.assertEqual(status, 200)
        self.assertEqual(updated["status"], "DONE")

    def test_export_api_endpoints(self):
        """Verify GET /api/export/markdown and GET /api/export/html."""
        # Markdown export
        status, md_res = self._http_request("GET", "/api/export/markdown?spec_id=proj-airgap-gateway")
        self.assertEqual(status, 200)
        self.assertEqual(md_res["status"], "ok")
        self.assertEqual(len(md_res["files"]), 7)

        # HTML export
        status, html_res = self._http_request("GET", "/api/export/html?spec_id=proj-airgap-gateway")
        self.assertEqual(status, 200)
        self.assertIn("<!DOCTYPE html>", html_res)
        self.assertIn("Spec-Kit Dossier:", html_res)

    def test_ai_fallback_endpoints(self):
        """Verify rule-based offline AI fallback endpoints (/api/ai/clarify and /api/ai/tasks)."""
        status, clarify_res = self._http_request("POST", "/api/ai/clarify", {
            "title": "Air-Gapped NTP Time Sync",
            "description": "Synchronize time against local atomic clock",
            "rationale": "Audit timestamp accuracy"
        })
        self.assertEqual(status, 200)
        self.assertIn("suggestions", clarify_res)
        self.assertGreaterEqual(len(clarify_res["suggestions"]), 2)

        status, tasks_res = self._http_request("POST", "/api/ai/tasks", {
            "req_id": "REQ-TIME-001",
            "title": "Air-Gapped NTP Time Sync",
            "description": "Synchronize time against local atomic clock"
        })
        self.assertEqual(status, 200)
        self.assertIn("tasks", tasks_res)
        self.assertGreaterEqual(len(tasks_res["tasks"]), 2)


# ==============================================================================
# Main Runner
# ==============================================================================
def main():
    print("=" * 80)
    print(" Running Corporate Spec-Kit Standalone Verification Test Suite")
    print(" Zero-Dependency Standard Library `unittest` (Python 3.8+)")
    print("=" * 80)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestDatabase))
    suite.addTests(loader.loadTestsFromTestCase(TestDiffEngine))
    suite.addTests(loader.loadTestsFromTestCase(TestLineageEngine))
    suite.addTests(loader.loadTestsFromTestCase(TestMarkdownSync))
    suite.addTests(loader.loadTestsFromTestCase(TestHttpServer))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 80)
    print(f" Summary: Ran {result.testsRun} tests.")
    if result.wasSuccessful():
        print(" [PASS] 100% of test suites passed successfully!")
        print(" Corporate Spec-Kit is certified for air-gapped production deployment.")
        print("=" * 80)
        return 0
    else:
        print(f" [FAIL] Failures: {len(result.failures)}, Errors: {len(result.errors)}")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())
