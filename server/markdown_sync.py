"""Spec-Kit Markdown synchronizer and Air-Gapped Standalone HTML dossier generator.
Uses standard Python library to produce spec-kit compliant documentation bundles.
"""
import os
import json
import html
from pathlib import Path
from typing import Dict, Any, List


class MarkdownSync:
    def __init__(self, db, output_base_dir: str = "specs_storage"):
        self.db = db
        self.output_base_dir = output_base_dir

    def export_speckit_bundle(self, spec_id: str) -> Dict[str, str]:
        """Generate full spec-kit folder structure and write Markdown files."""
        proj = self.db.get_project(spec_id)
        if not proj:
            raise ValueError(f"Project {spec_id} not found")

        reqs = self.db.list_requirements(spec_id)
        clars = self.db.list_clarifications(spec_id)
        tasks = self.db.list_tasks(spec_id)
        audits = self.db.list_audit(spec_id)

        target_dir = os.path.join(self.output_base_dir, spec_id)
        os.makedirs(target_dir, exist_ok=True)
        files_written = {}

        # 1. 00_constitution.md
        const_md = f"# Project Constitution: {proj['title']}\n\n"
        const_md += f"**Spec ID**: `{spec_id}` | **Status**: `{proj['status']}`\n\n"
        const_md += f"## Core Principles & Governance Rules\n\n{proj['constitution']}\n"
        files_written["00_constitution.md"] = const_md

        # 2. 01_spec.md
        spec_md = f"# Formal Specification: {proj['title']}\n\n"
        spec_md += f"## Business Intent & Background\n\n{proj['intent']}\n\n"
        spec_md += f"## Requirements Ledger\n\n"
        for r in reqs:
            spec_md += f"### [{r['id']}] {r['title']} (v{r['current_version']})\n"
            spec_md += f"- **Category**: `{r['category']}` | **Status**: `{r['status']}`\n"
            spec_md += f"- **Author**: {r['created_by']} (*{r['created_role']}*) | **Updated**: {r['updated_at']}\n\n"
            spec_md += f"**Description**:\n{r['description']}\n\n"
            spec_md += f"**Rationale**:\n{r['rationale']}\n\n"
            spec_md += f"**Acceptance Criteria**:\n"
            for crit in r.get("acceptance_criteria", []):
                spec_md += f"- {crit}\n"
            spec_md += "\n---\n\n"
        files_written["01_spec.md"] = spec_md

        # 3. 02_clarifications.md
        clar_md = f"# Clarification Interview Loop: {proj['title']}\n\n"
        clar_md += f"Spec-Kit Clarification questions and architectural resolutions:\n\n"
        for c in clars:
            clar_md += f"### [{c['id']}] {c['question']}\n"
            clar_md += f"- **Linked Requirement**: `{c['req_id'] or 'General Specification'}`\n"
            clar_md += f"- **Asked By**: {c['asked_by']} (*{c['asked_role']}*) at {c['created_at']}\n"
            clar_md += f"- **Status**: `{c['status']}`\n"
            if c.get("answer"):
                clar_md += f"- **Answer**: {c['answer']}\n"
                clar_md += f"- **Answered By**: {c['answered_by']} (*{c['answered_role']}*) at {c.get('resolved_at', '')}\n"
            else:
                clar_md += f"- **Answer**: *Pending resolution*\n"
            clar_md += "\n"
        files_written["02_clarifications.md"] = clar_md

        # 4. 03_plan.md
        plan_md = f"# Architectural Plan & Technical Blueprint: {proj['title']}\n\n"
        plan_md += f"## Architectural Overview\n\n"
        plan_md += f"High-level system design derived from business intent and governance guardrails.\n\n"
        plan_md += f"- **Target System**: `{proj['title']}`\n"
        plan_md += f"- **Governance Status**: `{proj['status']}`\n"
        plan_md += f"- **Total Requirements**: {len(reqs)}\n"
        plan_md += f"- **Decomposed Tasks**: {len(tasks)}\n\n"
        plan_md += f"## Phase Breakdown & Component Mapping\n\n"
        for r in reqs:
            r_tasks = [t for t in tasks if t.get("req_id") == r["id"]]
            plan_md += f"### Phase: Implementation for [{r['id']}] {r['title']}\n"
            plan_md += f"- **Category**: `{r['category']}`\n"
            plan_md += f"- **Architectural Rationale**: {r['rationale']}\n"
            if r_tasks:
                plan_md += f"- **Associated Execution Tasks**:\n"
                for t in r_tasks:
                    plan_md += f"  - `{t['id']}`: {t['title']} (Status: `{t['status']}`, Tests: `{t.get('test_case_id', '-')}`)\n"
            else:
                plan_md += f"- **Associated Execution Tasks**: *Pending decomposition*\n"
            plan_md += "\n"
        files_written["03_plan.md"] = plan_md

        # 5. 04_tasks.md
        task_md = f"# Engineering Tasks: {proj['title']}\n\n"
        task_md += f"| Task ID | Linked Req | Title | Assignee | Status | Test Case | Target Code |\n"
        task_md += f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
        for t in tasks:
            task_md += f"| `{t['id']}` | `{t['req_id']}` | {t['title']} | {t['assignee']} | `{t['status']}` | `{t.get('test_case_id', '-')}` | `{t.get('code_targets', '-')}` |\n"
        files_written["04_tasks.md"] = task_md

        # 6. 05_traceability_matrix.md
        from .lineage import LineageEngine
        engine = LineageEngine(self.db)
        matrix_data = engine.generate_traceability_matrix(spec_id)
        rtm_md = f"# Requirement Traceability Matrix (RTM): {proj['title']}\n\n"
        rtm_md += f"- **Overall Coverage**: **{matrix_data['overall_coverage_pct']}%**\n"
        rtm_md += f"- **Total Requirements**: {matrix_data['total_requirements']}\n"
        rtm_md += f"- **Total Tasks**: {matrix_data['total_tasks']}\n"
        if matrix_data["orphan_requirements"]:
            rtm_md += f"- **Warning - Orphan Requirements**: {', '.join(matrix_data['orphan_requirements'])}\n\n"
        rtm_md += f"| Req ID | Title | Cat | Ver | Clarifications | Tasks | Tests | Code Artifacts | Coverage |\n"
        rtm_md += f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
        for m in matrix_data["matrix"]:
            clars_str = ", ".join(c["id"] for c in m["clarifications"]) or "-"
            tasks_str = ", ".join(t["id"] for t in m["tasks"]) or "-"
            tests_str = ", ".join(m["tests"]) or "-"
            code_str = ", ".join(m["code_targets"]) or "-"
            rtm_md += f"| `{m['req_id']}` | {m['title']} | `{m['category']}` | v{m['version']} | {clars_str} | {tasks_str} | {tests_str} | {code_str} | {m['coverage_pct']}% |\n"
        files_written["05_traceability_matrix.md"] = rtm_md

        # 7. 06_revisions_ledger.md
        rev_md = f"# Requirement Revision Ledger & Change History: {proj['title']}\n\n"
        for r in reqs:
            revs = self.db.get_requirement_revisions(r["id"])
            rev_md += f"## History for {r['id']}: {r['title']}\n\n"
            for rev in revs:
                rev_md += f"### Version {rev['version']} - `{rev['change_type']}` by {rev['author_name']} (*{rev['author_role']}*)\n"
                rev_md += f"- **Timestamp**: `{rev['timestamp']}`\n"
                rev_md += f"- **Justification**: {rev['justification']}\n"
                if rev.get("diff_unified"):
                    rev_md += f"\n```diff\n{rev['diff_unified']}\n```\n"
                rev_md += "\n"
        files_written["06_revisions_ledger.md"] = rev_md

        # Write all files to disk
        for filename, content in files_written.items():
            filepath = os.path.join(target_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

        return files_written

    def export_standalone_html(self, spec_id: str) -> str:
        """
        Generate a single, completely self-contained offline HTML dossier.
        Can be opened directly from a flash drive on an air-gapped machine.
        """
        proj = self.db.get_project(spec_id)
        reqs = self.db.list_requirements(spec_id)
        clars = self.db.list_clarifications(spec_id)
        tasks = self.db.list_tasks(spec_id)
        audits = self.db.list_audit(spec_id)
        from .lineage import LineageEngine
        engine = LineageEngine(self.db)
        matrix = engine.generate_traceability_matrix(spec_id)
        graph = self.db.list_lineage(spec_id)

        req_revisions = {}
        for r in reqs:
            req_revisions[r["id"]] = self.db.get_requirement_revisions(r["id"])

        bundle_json = json.dumps({
            "project": proj,
            "requirements": reqs,
            "revisions": req_revisions,
            "clarifications": clars,
            "tasks": tasks,
            "matrix": matrix,
            "graph": graph,
            "audits": audits
        }, indent=2)

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Spec-Kit Dossier: {html.escape(proj['title'])}</title>
<style>
:root {{
  --bg-main: #0b0f19;
  --bg-card: #131b2e;
  --bg-input: #1b2640;
  --text-main: #e2e8f0;
  --text-muted: #94a3b8;
  --accent-cyan: #06b6d4;
  --accent-blue: #3b82f6;
  --accent-green: #10b981;
  --accent-amber: #f59e0b;
  --accent-rose: #f43f5e;
  --border-line: #1e293b;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg-main);
  color: var(--text-main);
  padding: 24px;
  line-height: 1.5;
}}
.container {{ max-width: 1400px; margin: 0 auto; }}
.header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border-line);
  padding-bottom: 20px;
  margin-bottom: 24px;
}}
.title {{ font-size: 24px; font-weight: 700; color: #fff; }}
.badge {{
  padding: 4px 10px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 600;
  background: rgba(6, 182, 212, 0.15);
  color: var(--accent-cyan);
  border: 1px solid rgba(6, 182, 212, 0.3);
}}
.kpi-row {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}}
.kpi-card {{
  background: var(--bg-card);
  border: 1px solid var(--border-line);
  border-radius: 8px;
  padding: 16px;
}}
.kpi-num {{ font-size: 28px; font-weight: 700; color: var(--accent-cyan); }}
.kpi-label {{ font-size: 13px; color: var(--text-muted); }}
.section {{
  background: var(--bg-card);
  border: 1px solid var(--border-line);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 24px;
}}
.section-title {{
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border-line);
  padding-bottom: 8px;
  color: #fff;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  margin-top: 12px;
}}
th, td {{
  padding: 10px 14px;
  text-align: left;
  border-bottom: 1px solid var(--border-line);
  font-size: 13px;
}}
th {{ background: #0f172a; color: var(--text-muted); font-weight: 600; }}
pre, code {{ font-family: var(--font-mono); }}
.diff-container {{
  background: #090d16;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 10px;
  font-family: var(--font-mono);
  font-size: 12px;
  overflow-x: auto;
  margin-top: 8px;
}}
.diff-delete {{ background: rgba(244, 63, 94, 0.2); color: #fda4af; }}
.diff-insert {{ background: rgba(16, 185, 129, 0.2); color: #6ee7b7; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1 class="title">{html.escape(proj['title'])}</h1>
      <p style="color:var(--text-muted); font-size: 14px; margin-top: 4px;">Self-Contained Spec-Kit Air-Gapped Dossier | ID: <code>{html.escape(spec_id)}</code></p>
    </div>
    <span class="badge">{html.escape(proj['status'])}</span>
  </div>

  <div class="kpi-row">
    <div class="kpi-card">
      <div class="kpi-num">{matrix['overall_coverage_pct']}%</div>
      <div class="kpi-label">Traceability Coverage</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-num">{len(reqs)}</div>
      <div class="kpi-label">Requirements</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-num">{len(clars)}</div>
      <div class="kpi-label">Clarifications</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-num">{len(tasks)}</div>
      <div class="kpi-label">Engineering Tasks</div>
    </div>
  </div>

  <div class="section">
    <h2 class="section-title">1. Business Intent & Background</h2>
    <p style="font-size:14px; line-height:1.6;">{html.escape(proj['intent'])}</p>
  </div>

  <div class="section">
    <h2 class="section-title">2. Enterprise Security Constitution</h2>
    <pre style="white-space:pre-wrap; font-size:13px; color:#cbd5e1;">{html.escape(proj['constitution'])}</pre>
  </div>

  <div class="section">
    <h2 class="section-title">3. Traceability Matrix (RTM)</h2>
    <table>
      <thead>
        <tr>
          <th>Requirement</th>
          <th>Category</th>
          <th>Version</th>
          <th>Author</th>
          <th>Tasks</th>
          <th>Tests</th>
          <th>Coverage</th>
        </tr>
      </thead>
      <tbody>
"""
        for m in matrix["matrix"]:
            tasks_cnt = len(m["tasks"])
            tests_cnt = len(m["tests"])
            html_template += f"""
        <tr>
          <td><strong>{html.escape(m['req_id'])}</strong>: {html.escape(m['title'])}</td>
          <td><span class="badge">{html.escape(m['category'])}</span></td>
          <td>v{m['version']}</td>
          <td>{html.escape(m['author'])}</td>
          <td>{tasks_cnt} tasks</td>
          <td>{tests_cnt} tests</td>
          <td><strong>{m['coverage_pct']}%</strong></td>
        </tr>
"""
        html_template += f"""
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2 class="section-title">4. Requirements Ledger & Revision Attribution</h2>
"""
        for r in reqs:
            html_template += f"""
    <div style="margin-bottom: 24px; border:1px solid #1e293b; border-radius:6px; padding:16px; background:#0f172a;">
      <h3 style="color:#38bdf8;">[{html.escape(r['id'])}] {html.escape(r['title'])} <span class="badge">v{r['current_version']}</span></h3>
      <p style="color:var(--text-muted); font-size:12px; margin:4px 0 12px 0;">Author: {html.escape(r['created_by'])} ({html.escape(r['created_role'])}) | Status: {html.escape(r['status'])}</p>
      <p style="margin-bottom:8px;"><strong>Description:</strong> {html.escape(r['description'])}</p>
      <p style="margin-bottom:8px;"><strong>Rationale:</strong> {html.escape(r['rationale'])}</p>
      <div style="margin-top:12px;">
        <strong>Acceptance Criteria:</strong>
        <ul style="margin-left:20px; margin-top:4px;">
"""
            for crit in r.get("acceptance_criteria", []):
                html_template += f"<li>{html.escape(crit)}</li>"
            html_template += f"""
        </ul>
      </div>
      <div style="margin-top:16px;">
        <strong>Revision History & Audit Trail:</strong>
"""
            for rev in req_revisions.get(r["id"], []):
                html_template += f"""
        <div style="background:#131c31; border-left:3px solid var(--accent-cyan); padding:8px 12px; margin-top:8px; border-radius:4px; font-size:12px;">
          <div><strong>v{rev['version']} [{rev['change_type']}]</strong> by {html.escape(rev['author_name'])} ({html.escape(rev['author_role'])}) at {rev['timestamp']}</div>
          <div style="color:var(--text-muted); margin-top:2px;">Justification: {html.escape(rev['justification'])}</div>
          {f'<pre class="diff-container">{html.escape(rev["diff_unified"])}</pre>' if rev.get("diff_unified") else ''}
        </div>
"""
            html_template += """
      </div>
    </div>
"""
        html_template += f"""
  </div>

  <div class="section">
    <h2 class="section-title">5. Clarification Q&A Loop</h2>
    <table>
      <thead>
        <tr><th>ID</th><th>Linked Req</th><th>Question</th><th>Asked By</th><th>Status</th><th>Resolution / Answer</th></tr>
      </thead>
      <tbody>
"""
        for c in clars:
            html_template += f"""
        <tr>
          <td><strong>{html.escape(c['id'])}</strong></td>
          <td>{html.escape(c['req_id'] or '-')}</td>
          <td>{html.escape(c['question'])}</td>
          <td>{html.escape(c['asked_by'])} ({html.escape(c['asked_role'])})</td>
          <td><span class="badge">{html.escape(c['status'])}</span></td>
          <td>{html.escape(c['answer'] or 'Pending')}</td>
        </tr>
"""
        html_template += f"""
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2 class="section-title">6. Activity Audit Ledger</h2>
    <table>
      <thead>
        <tr><th>Timestamp</th><th>Action</th><th>Target</th><th>Actor</th><th>Details</th></tr>
      </thead>
      <tbody>
"""
        for a in audits[:30]:
            html_template += f"""
        <tr>
          <td style="font-family:var(--font-mono); font-size:11px;">{html.escape(a['timestamp'])}</td>
          <td><span class="badge">{html.escape(a['action'])}</span></td>
          <td>{html.escape(a['entity_id'])}</td>
          <td>{html.escape(a['actor_name'])} ({html.escape(a['actor_role'])})</td>
          <td>{html.escape(a['details'])}</td>
        </tr>
"""
        html_template += f"""
      </tbody>
    </table>
  </div>
</div>

<script>
// Embedded Project Data
window.__SPECKIT_DATA__ = {bundle_json};
</script>
</body>
</html>"""
        return html_template
