"""Pure standard-library HTTP Server for Corporate Spec-Kit.
Zero external dependencies; uses http.server.ThreadingHTTPServer.
Handles REST JSON API and static file serving.
"""
import os
import json
import time
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from typing import Dict, Any, Optional

from .db import SpecDatabase
from .diff_engine import diff_requirement_payload, compute_unified_diff
from .lineage import LineageEngine
from .markdown_sync import MarkdownSync
from .ai_bridge import AIBridge
from modules.manager import ModuleManager


class SpecKitRequestHandler(SimpleHTTPRequestHandler):
    # Class-level engine references injected at startup
    db: SpecDatabase = None
    lineage: LineageEngine = None
    sync: MarkdownSync = None
    ai: AIBridge = None
    modules: ModuleManager = None
    harness: Any = None
    static_dir: str = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=self.static_dir, **kwargs)

    def _send_json(self, status_code: int, data: Any):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. API Endpoints
        if path.startswith("/api/"):
            try:
                self._handle_api_get(path, query)
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        # 2. Static Root Routing
        if path == "/" or path == "/index.html":
            index_path = os.path.join(self.static_dir, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        # Fallback to standard static file serving
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            self._handle_api_post(path)
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            self._handle_api_put(path)
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    # ---------------- API DISPATCHERS ---------------- #

    def _handle_api_get(self, path: str, query: Dict[str, list]):
        spec_id = query.get("spec_id", ["proj-airgap-gateway"])[0]

        if path == "/api/modules":
            manifest = self.modules.get_modules_manifest() if self.modules else []
            self._send_json(200, {"modules": manifest})
            return

        if self.modules and self.modules.dispatch_route("GET", path, self):
            return

        if path == "/api/projects":
            projects = self.db.list_projects()
            self._send_json(200, {"projects": projects})
            return

        if path.startswith("/api/projects/"):
            proj_id = path.split("/")[3]
            proj = self.db.get_project(proj_id)
            if proj:
                self._send_json(200, proj)
            else:
                self._send_json(404, {"error": "Project not found"})
            return

        if path == "/api/requirements":
            reqs = self.db.list_requirements(spec_id)
            self._send_json(200, {"requirements": reqs})
            return

        if path.startswith("/api/requirements/") and path.endswith("/revisions"):
            req_id = path.split("/")[3]
            revs = self.db.get_requirement_revisions(req_id)
            self._send_json(200, {"revisions": revs})
            return

        if path.startswith("/api/requirements/"):
            req_id = path.split("/")[3]
            req = self.db.get_requirement(req_id)
            if req:
                self._send_json(200, req)
            else:
                self._send_json(404, {"error": "Requirement not found"})
            return

        if path == "/api/clarifications":
            clars = self.db.list_clarifications(spec_id)
            self._send_json(200, {"clarifications": clars})
            return

        if path == "/api/tasks":
            tasks = self.db.list_tasks(spec_id)
            self._send_json(200, {"tasks": tasks})
            return

        if path == "/api/lineage":
            data = self.lineage.get_graph_data(spec_id)
            self._send_json(200, data)
            return

        if path == "/api/lineage/trace":
            node_id = query.get("node_id", [""])[0]
            if not node_id:
                self._send_json(400, {"error": "node_id required"})
                return
            provenance = self.lineage.trace_node_provenance(spec_id, node_id)
            self._send_json(200, provenance)
            return

        if path == "/api/matrix":
            matrix = self.lineage.generate_traceability_matrix(spec_id)
            self._send_json(200, matrix)
            return

        if path == "/api/audit":
            audits = self.db.list_audit(spec_id)
            self._send_json(200, {"audit_log": audits})
            return

        if path == "/api/audit/verify":
            verification = self.db.verify_audit_integrity(spec_id)
            self._send_json(200, verification.to_dict())
            return

        if path == "/api/export/markdown":
            written = self.sync.export_speckit_bundle(spec_id)
            self._send_json(200, {"status": "ok", "files": list(written.keys()), "directory": f"specs_storage/{spec_id}"})
            return

        if path == "/api/export/html":
            html_content = self.sync.export_standalone_html(spec_id)
            body = html_content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="speckit_{spec_id}_dossier.html"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/settings":
            cfg = self.ai.get_config()
            self._send_json(200, cfg)
            return

        # Harness Pipeline Endpoints
        if path == "/api/harness/pipelines":
            if not self.harness:
                self._send_json(503, {"error": "B2B Harness engine is not initialized"})
                return
            runs = self.harness.list_pipelines()
            self._send_json(200, {"pipelines": runs})
            return

        if path.startswith("/api/harness/pipeline/"):
            if not self.harness:
                self._send_json(503, {"error": "B2B Harness engine is not initialized"})
                return
            parts = path.strip("/").split("/")
            # parts: ['api', 'harness', 'pipeline', '{pipeline_id}', '{sub_action}?']
            if len(parts) >= 4:
                pipe_id = parts[3]
                sub_action = parts[4] if len(parts) > 4 else "state"

                if sub_action == "state":
                    try:
                        state = self.harness.get_pipeline_state(pipe_id)
                        self._send_json(200, state)
                    except ValueError as e:
                        self._send_json(404, {"error": str(e)})
                    return

                if sub_action == "messages":
                    msgs = self.harness.get_a2a_messages(pipe_id)
                    self._send_json(200, {"messages": msgs})
                    return

                if sub_action == "artifacts":
                    arts = self.harness.list_artifacts(pipe_id)
                    self._send_json(200, {"artifacts": arts})
                    return

                if sub_action == "artifact":
                    art_name = query.get("name", [""])[0]
                    if not art_name:
                        self._send_json(400, {"error": "Artifact name required via ?name=..."})
                        return
                    content = self.harness.get_artifact(pipe_id, art_name)
                    if content is None:
                        self._send_json(404, {"error": f"Artifact {art_name} not found"})
                        return
                    self._send_json(200, {"name": art_name, "content": content})
                    return

        self._send_json(404, {"error": f"Endpoint not found: {path}"})

    def _handle_api_post(self, path: str):
        payload = self._read_json_body()

        if self.modules and self.modules.dispatch_route("POST", path, self):
            return

        if path == "/api/projects":
            pid = payload.get("id") or f"proj-{int(time.time())}"
            title = payload.get("title", "New Specification")
            intent = payload.get("intent", "")
            constitution = payload.get("constitution", "")
            created = self.db.create_project(pid, title, intent, constitution)
            self._send_json(201, created)
            return

        if path == "/api/requirements":
            spec_id = payload.get("spec_id", "proj-airgap-gateway")
            req_id = payload.get("id")
            if not req_id:
                # Auto-generate next REQ ID
                existing = self.db.list_requirements(spec_id)
                num = len(existing) + 1
                req_id = f"REQ-GEN-{num:03d}"
            
            created = self.db.create_requirement(
                spec_id=spec_id,
                req_id=req_id,
                category=payload.get("category", "FUNCTIONAL"),
                title=payload.get("title", ""),
                description=payload.get("description", ""),
                rationale=payload.get("rationale", ""),
                acceptance_criteria=payload.get("acceptance_criteria", []),
                author_name=payload.get("author_name", "Corporate Contributor"),
                author_role=payload.get("author_role", "Analyst"),
                justification=payload.get("justification", "Initial requirement draft")
            )
            self._send_json(201, created)
            return

        if path == "/api/clarifications":
            spec_id = payload.get("spec_id", "proj-airgap-gateway")
            existing = self.db.list_clarifications(spec_id)
            cid = f"CLAR-{len(existing)+1:03d}"
            res = self.db.add_clarification(
                spec_id=spec_id,
                clar_id=cid,
                req_id=payload.get("req_id"),
                question=payload.get("question", ""),
                asked_by=payload.get("asked_by", "Engineer"),
                asked_role=payload.get("asked_role", "Developer")
            )
            self._send_json(201, res)
            return

        if path.startswith("/api/clarifications/") and path.endswith("/resolve"):
            cid = path.split("/")[3]
            res = self.db.resolve_clarification(
                clar_id=cid,
                answer=payload.get("answer", ""),
                answered_by=payload.get("answered_by", "Architect"),
                answered_role=payload.get("answered_role", "Lead")
            )
            self._send_json(200, res)
            return

        if path == "/api/tasks":
            spec_id = payload.get("spec_id", "proj-airgap-gateway")
            existing = self.db.list_tasks(spec_id)
            tid = f"TASK-{len(existing)+1:03d}"
            res = self.db.create_task(
                spec_id=spec_id,
                task_id=tid,
                req_id=payload.get("req_id", ""),
                title=payload.get("title", ""),
                description=payload.get("description", ""),
                assignee=payload.get("assignee", "Unassigned"),
                test_case_id=payload.get("test_case_id", ""),
                code_targets=payload.get("code_targets", "")
            )
            self._send_json(201, res)
            return

        if path.startswith("/api/tasks/") and path.endswith("/status"):
            tid = path.split("/")[3]
            status = payload.get("status", "DONE")
            res = self.db.update_task_status(tid, status, payload.get("actor_name", "Dev"), payload.get("actor_role", "Dev"))
            self._send_json(200, res)
            return

        if path == "/api/ai/clarify":
            questions = self.ai.suggest_clarifications(
                req_title=payload.get("title", ""),
                req_desc=payload.get("description", ""),
                req_rationale=payload.get("rationale", "")
            )
            self._send_json(200, {"suggestions": questions})
            return

        if path == "/api/ai/tasks":
            tasks = self.ai.decompose_tasks(
                req_id=payload.get("req_id", "REQ-001"),
                req_title=payload.get("title", ""),
                req_desc=payload.get("description", "")
            )
            self._send_json(200, {"tasks": tasks})
            return

        if path == "/api/settings":
            for k in ["ai_endpoint", "ai_api_key", "ai_model"]:
                if k in payload:
                    self.db.set_setting(k, payload[k])
            self._send_json(200, {"status": "updated"})
            return

        # Harness Pipeline Actions
        if path == "/api/harness/pipeline/start":
            if not self.harness:
                self._send_json(503, {"error": "B2B Harness engine is not initialized"})
                return
            project_name = payload.get("project_name", "PoC Normalization Project")
            input_path = payload.get("input_path", "workspace")
            initial_idea = payload.get("initial_idea", "")
            pipe_id = self.harness.init_pipeline(project_name, input_path, initial_idea)
            state = self.harness.get_pipeline_state(pipe_id)
            self._send_json(201, {"status": "ok", "pipeline_id": pipe_id, "state": state})
            return

        if path.startswith("/api/harness/pipeline/"):
            if not self.harness:
                self._send_json(503, {"error": "B2B Harness engine is not initialized"})
                return
            parts = path.strip("/").split("/")
            # parts: ['api', 'harness', 'pipeline', '{pipeline_id}', '{sub_action}']
            if len(parts) >= 5:
                pipe_id = parts[3]
                sub_action = parts[4]

                if sub_action == "step":
                    try:
                        res = self.harness.step(pipe_id)
                        state = self.harness.get_pipeline_state(pipe_id)
                        self._send_json(200, {"result": res, "state": state})
                    except Exception as e:
                        self._send_json(400, {"error": str(e)})
                    return

                if sub_action == "run":
                    try:
                        final_state = self.harness.run_until_pause(pipe_id)
                        self._send_json(200, {"status": "paused_or_completed", "state": final_state})
                    except Exception as e:
                        self._send_json(400, {"error": str(e)})
                    return

                if sub_action == "resolve_gate":
                    try:
                        res = self.harness.resume_pipeline(pipe_id, payload)
                        state = self.harness.get_pipeline_state(pipe_id)
                        self._send_json(200, {"result": res, "state": state})
                    except Exception as e:
                        self._send_json(400, {"error": str(e)})
                    return

        self._send_json(404, {"error": f"Endpoint not found: {path}"})

    def _handle_api_put(self, path: str):
        payload = self._read_json_body()

        if path.startswith("/api/requirements/"):
            req_id = path.split("/")[3]
            old_req = self.db.get_requirement(req_id)
            if not old_req:
                self._send_json(404, {"error": "Requirement not found"})
                return

            # Compute unified diff between old and new state
            old_snapshot = f"Title: {old_req['title']}\nCategory: {old_req['category']}\nDesc: {old_req['description']}\nRationale: {old_req['rationale']}\nCriteria:\n" + "\n".join(f"- {c}" for c in old_req.get("acceptance_criteria", []))
            
            new_crit = payload.get("acceptance_criteria", old_req.get("acceptance_criteria", []))
            new_title = payload.get("title", old_req["title"])
            new_cat = payload.get("category", old_req["category"])
            new_desc = payload.get("description", old_req["description"])
            new_rat = payload.get("rationale", old_req["rationale"])
            new_stat = payload.get("status", old_req["status"])
            
            new_snapshot = f"Title: {new_title}\nCategory: {new_cat}\nDesc: {new_desc}\nRationale: {new_rat}\nCriteria:\n" + "\n".join(f"- {c}" for c in new_crit)

            diff_str = compute_unified_diff(old_snapshot, new_snapshot, old_label=f"v{old_req['current_version']}", new_label=f"v{old_req['current_version']+1}")

            updated = self.db.update_requirement(
                req_id=req_id,
                category=new_cat,
                title=new_title,
                description=new_desc,
                rationale=new_rat,
                acceptance_criteria=new_crit,
                status=new_stat,
                author_name=payload.get("author_name", "Anonymous Contributor"),
                author_role=payload.get("author_role", "Reviewer"),
                justification=payload.get("justification", "Requirement refinement"),
                diff_unified=diff_str
            )
            self._send_json(200, updated)
            return

        self._send_json(404, {"error": f"Endpoint not found: {path}"})
