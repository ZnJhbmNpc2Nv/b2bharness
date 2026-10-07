#!/usr/bin/env python3
"""Corporate Spec-Kit Headless Terminal CLI.
Zero external dependencies; uses Python standard library only.
Designed for air-gapped corporate servers, bastion hosts, and CI/CD pipelines.
"""
import sys
import os
import argparse
import difflib
import json
from collections import deque
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

# Ensure current package directory is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Reconfigure stdout/stderr to UTF-8 on Windows to prevent cp1251 charmap errors
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from server.db import SpecDatabase
from server.lineage import LineageEngine
from server.markdown_sync import MarkdownSync
from server.audit_seal import verify_ledger_integrity, GENESIS_HASH


# ------------------ ANSI COLOR FORMATTING ------------------ #

class Colors:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled and sys.stdout.isatty()
        # Enable ANSI colors on Windows 10+ cmd/powershell
        if self.enabled and os.name == "nt":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except Exception:
                pass

    def _c(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else str(text)

    def bold(self, t: str) -> str: return self._c("1", t)
    def dim(self, t: str) -> str: return self._c("2", t)
    def red(self, t: str) -> str: return self._c("31", t)
    def green(self, t: str) -> str: return self._c("32", t)
    def yellow(self, t: str) -> str: return self._c("33", t)
    def blue(self, t: str) -> str: return self._c("34", t)
    def magenta(self, t: str) -> str: return self._c("35", t)
    def cyan(self, t: str) -> str: return self._c("36", t)
    def white(self, t: str) -> str: return self._c("37", t)
    def bg_red(self, t: str) -> str: return self._c("41;97", t)
    def bg_green(self, t: str) -> str: return self._c("42;30", t)


# ------------------ DATABASE RESOLUTION ------------------ #

def get_database(db_arg: Optional[str] = None) -> SpecDatabase:
    """Resolve database path and initialize SpecDatabase."""
    if db_arg:
        db_path = os.path.abspath(db_arg)
    else:
        # Default to specs_storage/speckit.db relative to corporate_speckit root
        db_path = os.path.join(SCRIPT_DIR, "specs_storage", "speckit.db")
    return SpecDatabase(db_path)


def resolve_spec_id(db: SpecDatabase, spec_arg: Optional[str]) -> str:
    """Resolve active spec ID or fallback to default."""
    if spec_arg:
        return spec_arg
    projects = db.list_projects()
    if projects:
        return projects[0]["id"]
    return "proj-airgap-gateway"


# ------------------ CLI COMMAND IMPLEMENTATIONS ------------------ #

def cmd_list(args, colors: Colors):
    """List requirements in tabular format."""
    db = get_database(args.db)
    spec_id = resolve_spec_id(db, args.spec)
    proj = db.get_project(spec_id)
    if not proj:
        print(colors.red(f"Error: Project '{spec_id}' not found in database."))
        sys.exit(1)

    reqs = db.list_requirements(spec_id)
    print(colors.bold(f"\nSpecification Requirements: {proj['title']} [{spec_id}]"))
    print(colors.dim(f"Governance Status: {proj['status']} | Total Requirements: {len(reqs)}\n"))

    if not reqs:
        print(colors.yellow("No requirements registered yet."))
        return

    # Table layout
    headers = ["ID", "Title", "Category", "Status", "Ver", "Author"]
    widths = [13, 38, 12, 12, 5, 24]

    def format_row(cols, is_header=False):
        formatted = []
        for val, w in zip(cols, widths):
            val_str = str(val)[:w].ljust(w)
            formatted.append(val_str)
        sep = " │ " if not is_header else " │ "
        return f"│ {sep.join(formatted)} │"

    def border(char_l, char_m, char_r, char_line="─"):
        parts = [char_line * (w + 2) for w in widths]
        return f"{char_l}{char_m.join(parts)}{char_r}"

    print(border("┌", "┬", "┐"))
    print(colors.bold(format_row(headers, is_header=True)))
    print(border("├", "┼", "┤"))

    for r in reqs:
        status_colored = r["status"]
        if r["status"] == "ACCEPTED":
            status_colored = colors.green(r["status"])
        elif r["status"] == "PROPOSED":
            status_colored = colors.yellow(r["status"])
        elif r["status"] == "AUGMENTED":
            status_colored = colors.cyan(r["status"])

        author_str = f"{r['created_by']}"
        cols = [
            colors.cyan(r["id"]),
            r["title"][:38],
            r["category"][:12],
            status_colored,
            f"v{r['current_version']}",
            author_str[:24],
        ]
        # Pad based on raw text length
        raw_cols = [r["id"], r["title"][:38], r["category"][:12], r["status"], f"v{r['current_version']}", author_str[:24]]
        line = "│ "
        for i, (styled, raw) in enumerate(zip(cols, raw_cols)):
            w = widths[i]
            padding = " " * max(0, w - len(raw))
            line += f"{styled}{padding}"
            if i < len(cols) - 1:
                line += " │ "
        line += " │"
        print(line)

    print(border("└", "┴", "┘"))
    print()


def cmd_provenance(args, colors: Colors):
    """Print ASCII tree showing origins ('Откуда что родилось') and downstream impact."""
    db = get_database(args.db)
    spec_id = resolve_spec_id(db, args.spec)
    target_id = args.target_id.strip()

    lineage = LineageEngine(db)
    graph = lineage.get_graph_data(spec_id)
    nodes = graph["nodes"]
    edges = graph["edges"]

    # Match target node by ID or entity_id
    target_node = None
    for n in nodes:
        if n["id"].lower() == target_id.lower() or n["entity_id"].lower() == target_id.lower():
            target_node = n
            break

    if not target_node:
        print(colors.red(f"Error: Node or Entity '{target_id}' not found in lineage graph for spec '{spec_id}'."))
        print(colors.dim("Available entities in graph:"))
        for n in nodes:
            print(f"  - {n['id']} (entity: {n['entity_id']}, type: {n['node_type']}, label: {n['label']})")
        sys.exit(1)

    node_dict = {n["id"]: n for n in nodes}
    incoming: Dict[str, List[Dict[str, Any]]] = {}
    outgoing: Dict[str, List[Dict[str, Any]]] = {}
    for e in edges:
        outgoing.setdefault(e["from_node_id"], []).append(e)
        incoming.setdefault(e["to_node_id"], []).append(e)

    print(colors.bold(f"\n================================================================================"))
    print(colors.bold(f"   LINEAGE & PROVENANCE TRACE: {target_node['label']}"))
    print(colors.dim(f"   Node ID: {target_node['id']} | Entity ID: {target_node['entity_id']} | Type: {target_node['node_type']}"))
    print(colors.bold(f"================================================================================\n"))

    # 1. ORIGINS (Upstream ancestors: "Откуда что родилось")
    print(colors.cyan(colors.bold("▲ ORIGINS & UPSTREAM CHAIN (\"Откуда что родилось\"):")))
    
    # Trace upstream ancestors recursively
    visited_up: Set[str] = set()

    def print_upstream(curr_id: str, prefix: str = "", is_last: bool = True):
        curr_node = node_dict.get(curr_id)
        if not curr_node:
            return
        branch = "└── " if is_last else "├── "
        node_type_tag = colors.yellow(f"[{curr_node['node_type']}]")
        label = curr_node["label"]
        if curr_id == target_node["id"]:
            print(f"{prefix}{branch}{colors.bold(colors.green(label))} (TARGET)")
        else:
            print(f"{prefix}{branch}{node_type_tag} {label}")

        parents = incoming.get(curr_id, [])
        new_prefix = prefix + ("    " if is_last else "│   ")
        for i, edge in enumerate(parents):
            p_id = edge["from_node_id"]
            if p_id not in visited_up:
                visited_up.add(p_id)
                rel_tag = colors.dim(f"({edge['relation']})")
                print(f"{new_prefix}▲ {rel_tag}")
                print_upstream(p_id, new_prefix, i == len(parents) - 1)

    # Find root ancestors first
    prov_data = lineage.trace_node_provenance(spec_id, target_node["id"])
    ancestors = prov_data["ancestor_nodes"]
    
    if not ancestors:
        print(colors.dim("  (Target is a root node; no upstream origins)"))
    else:
        # Display direct and indirect upstream sources
        print(f"  Target: {colors.bold(target_node['label'])}")
        for a in ancestors:
            meta = json.loads(a.get("meta_json") or "{}")
            extra = f" - {meta}" if meta else ""
            print(f"  ▲ Derived from [{colors.yellow(a['node_type'])}] {colors.bold(a['label'])}{colors.dim(extra)}")

    print()

    # 2. DOWNSTREAM (Descendants / Implementation Tasks / Verifications)
    print(colors.green(colors.bold("▼ DOWNSTREAM IMPACT & EXECUTION (\"Импакт и реализация\"):")))
    visited_down: Set[str] = set([target_node["id"]])

    def print_downstream(curr_id: str, prefix: str = ""):
        children = outgoing.get(curr_id, [])
        for i, edge in enumerate(children):
            c_id = edge["to_node_id"]
            c_node = node_dict.get(c_id)
            if not c_node:
                continue
            is_last = (i == len(children) - 1)
            branch = "└── " if is_last else "├── "
            rel_label = colors.cyan(f"[{edge['relation']}]")
            type_tag = colors.yellow(f"({c_node['node_type']})")
            print(f"{prefix}{branch}{rel_label} {type_tag} {colors.bold(c_node['label'])}")

            if c_id not in visited_down:
                visited_down.add(c_id)
                new_prefix = prefix + ("    " if is_last else "│   ")
                print_downstream(c_id, new_prefix)

    print(f"  Target: {colors.bold(target_node['label'])}")
    print_downstream(target_node["id"], "  ")
    print()


def cmd_diff(args, colors: Colors):
    """Print colored ANSI diff between two requirement versions."""
    db = get_database(args.db)
    req_id = args.req_id.strip()
    try:
        v1_num = int(args.v1)
        v2_num = int(args.v2)
    except ValueError:
        print(colors.red(f"Error: Version numbers must be integers (got '{args.v1}' and '{args.v2}')."))
        sys.exit(1)

    revisions = db.get_requirement_revisions(req_id)
    if not revisions:
        print(colors.red(f"Error: No revisions found for requirement '{req_id}'."))
        sys.exit(1)

    rev_map = {r["version"]: r for r in revisions}
    if v1_num not in rev_map:
        print(colors.red(f"Error: Version {v1_num} not found for {req_id}. Available versions: {list(rev_map.keys())}"))
        sys.exit(1)
    if v2_num not in rev_map:
        print(colors.red(f"Error: Version {v2_num} not found for {req_id}. Available versions: {list(rev_map.keys())}"))
        sys.exit(1)

    r1 = rev_map[v1_num]
    r2 = rev_map[v2_num]

    print(colors.bold(f"\n================================================================================"))
    print(colors.bold(f"   REQUIREMENT AUDIT DIFF: {req_id} (v{v1_num} ➔ v{v2_num})"))
    print(colors.bold(f"================================================================================"))
    print(f"   * Version {v1_num}: {r1['author_name']} ({r1['author_role']}) at {r1['timestamp']}")
    print(f"   * Version {v2_num}: {r2['author_name']} ({r2['author_role']}) at {r2['timestamp']}")
    print(f"   * Change Type: {colors.cyan(r2['change_type'])}")
    print(f"   * Justification: {colors.yellow(r2['justification'])}")
    print(colors.bold(f"================================================================================\n"))

    def make_snapshot(r: Dict[str, Any]) -> str:
        crit_lines = "\n".join(f"- {c}" for c in r.get("acceptance_criteria", []))
        return (
            f"Title: {r['title']}\n"
            f"Category: {r['category']}\n"
            f"Status: {r['status']}\n"
            f"Rationale: {r['rationale']}\n"
            f"Description:\n{r['description']}\n"
            f"Acceptance Criteria:\n{crit_lines}\n"
        )

    snap1 = make_snapshot(r1).splitlines(keepends=True)
    snap2 = make_snapshot(r2).splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(
        snap1, snap2,
        fromfile=f"{req_id} v{v1_num}",
        tofile=f"{req_id} v{v2_num}",
        lineterm=""
    ))

    if not diff_lines:
        print(colors.yellow("No textual differences detected between the two versions."))
        return

    for line in diff_lines:
        if line.startswith("---") or line.startswith("+++"):
            print(colors.bold(colors.cyan(line)))
        elif line.startswith("@@"):
            print(colors.dim(colors.magenta(line)))
        elif line.startswith("-"):
            print(colors.red(line))
        elif line.startswith("+"):
            print(colors.green(line))
        else:
            print(line)
    print()


def cmd_matrix(args, colors: Colors):
    """Print ASCII Traceability Matrix with coverage percentage and orphan warnings."""
    db = get_database(args.db)
    spec_id = resolve_spec_id(db, args.spec)
    proj = db.get_project(spec_id)
    if not proj:
        print(colors.red(f"Error: Project '{spec_id}' not found."))
        sys.exit(1)

    lineage = LineageEngine(db)
    data = lineage.generate_traceability_matrix(spec_id)
    matrix = data["matrix"]
    coverage = data["overall_coverage_pct"]
    orphans = data["orphan_requirements"]

    print(colors.bold(f"\n================================================================================"))
    print(colors.bold(f"   REQUIREMENTS TRACEABILITY MATRIX (RTM): {proj['title']}"))
    print(colors.dim(f"   Spec ID: {spec_id} | Total Reqs: {data['total_requirements']} | Total Tasks: {data['total_tasks']}"))
    print(colors.bold(f"================================================================================\n"))

    # ASCII Progress Bar
    bar_width = 30
    filled = int(bar_width * (coverage / 100.0))
    bar = "█" * filled + "░" * (bar_width - filled)
    coverage_color = colors.green if coverage >= 80 else (colors.yellow if coverage >= 50 else colors.red)
    print(f"Overall Coverage: [{coverage_color(bar)}] {colors.bold(str(coverage) + '%')}\n")

    if orphans:
        print(colors.bg_red(f" ⚠ WARNING: {len(orphans)} ORPHAN REQUIREMENT(S) DETECTED! "))
        print(colors.red(f"   Unmapped requirements with zero execution tasks: {', '.join(orphans)}\n"))
    else:
        print(colors.green(" ✓ Zero orphan requirements. Full decomposition coverage intact.\n"))

    # Table layout
    headers = ["Req ID", "Title", "Ver", "Tasks", "Tests", "Code Target", "Coverage", "State"]
    widths = [13, 26, 4, 11, 13, 22, 9, 10]

    def border(char_l, char_m, char_r, char_line="─"):
        parts = [char_line * (w + 2) for w in widths]
        return f"{char_l}{char_m.join(parts)}{char_r}"

    print(border("┌", "┬", "┐"))
    print(colors.bold("│ " + " │ ".join(h.ljust(w) for h, w in zip(headers, widths)) + " │"))
    print(border("├", "┼", "┤"))

    for m in matrix:
        tasks_str = ", ".join(t["id"] for t in m["tasks"]) or "-"
        tests_str = ", ".join(m["tests"]) or "-"
        code_str = ", ".join(m["code_targets"]) or "-"
        state_str = colors.green("COMPLETE") if m["is_complete"] else colors.yellow("PARTIAL")
        raw_state = "COMPLETE" if m["is_complete"] else "PARTIAL"

        cov_str = f"{m['coverage_pct']}%"

        cols = [
            colors.cyan(m["req_id"]),
            m["title"][:26],
            f"v{m['version']}",
            tasks_str[:11],
            tests_str[:13],
            code_str[:22],
            cov_str,
            state_str,
        ]
        raw_cols = [m["req_id"], m["title"][:26], f"v{m['version']}", tasks_str[:11], tests_str[:13], code_str[:22], cov_str, raw_state]

        line = "│ "
        for i, (styled, raw) in enumerate(zip(cols, raw_cols)):
            w = widths[i]
            padding = " " * max(0, w - len(raw))
            line += f"{styled}{padding}"
            if i < len(cols) - 1:
                line += " │ "
        line += " │"
        print(line)

    print(border("└", "┴", "┘"))
    print()


def cmd_clarify(args, colors: Colors):
    """List open and resolved clarification questions."""
    db = get_database(args.db)
    spec_id = resolve_spec_id(db, args.spec)
    clars = db.list_clarifications(spec_id)

    print(colors.bold(f"\nClarification Interview Ledger [{spec_id}]"))
    open_count = sum(1 for c in clars if c["status"] == "OPEN")
    resolved_count = sum(1 for c in clars if c["status"] == "RESOLVED")
    print(colors.dim(f"Total: {len(clars)} | Resolved: {resolved_count} | Open: {open_count}\n"))

    if not clars:
        print(colors.yellow("No clarification items registered."))
        return

    for c in clars:
        status_tag = colors.green("[RESOLVED]") if c["status"] == "RESOLVED" else colors.yellow("[OPEN]")
        req_ref = f"(Linked: {c['req_id']})" if c.get("req_id") else "(General Spec)"
        print(f"{colors.bold(c['id'])} {status_tag} {colors.cyan(req_ref)}")
        print(f"  {colors.bold('Question:')} {c['question']}")
        print(f"  {colors.dim('Asked by:')} {c['asked_by']} ({c['asked_role']}) at {c['created_at']}")
        if c.get("answer"):
            print(f"  {colors.bold('Answer:')}   {c['answer']}")
            print(f"  {colors.dim('Resolved by:')} {c.get('answered_by', '-')} ({c.get('answered_role', '-')}) at {c.get('resolved_at', '-')}")
        else:
            print(f"  {colors.yellow('Answer:   Pending architectural clarification.')}")
        print()


def cmd_export_md(args, colors: Colors):
    """Generate Markdown specification bundle in specs_storage/."""
    db = get_database(args.db)
    spec_id = resolve_spec_id(db, args.spec)
    output_dir = args.output or os.path.join(SCRIPT_DIR, "specs_storage")

    sync = MarkdownSync(db, output_base_dir=output_dir)
    print(colors.bold(f"\nExporting Spec-Kit Markdown Bundle for '{spec_id}'..."))
    files = sync.export_speckit_bundle(spec_id)

    target_dir = os.path.join(output_dir, spec_id)
    print(colors.green(f"✓ Generated {len(files)} Spec-Kit markdown files in: {target_dir}\n"))
    for fname in sorted(files.keys()):
        fpath = os.path.join(target_dir, fname)
        size = os.path.getsize(fpath) if os.path.exists(fpath) else len(files[fname].encode("utf-8"))
        print(f"  - {colors.cyan(fname)} ({size:,} bytes)")
    print()


def cmd_export_html(args, colors: Colors):
    """Generate single-file self-contained HTML report."""
    db = get_database(args.db)
    spec_id = resolve_spec_id(db, args.spec)

    sync = MarkdownSync(db)
    print(colors.bold(f"\nGenerating Air-Gapped Standalone HTML Dossier for '{spec_id}'..."))
    html_content = sync.export_standalone_html(spec_id)

    out_path = args.output
    if not out_path:
        out_dir = os.path.join(SCRIPT_DIR, "specs_storage", spec_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"speckit_{spec_id}_dossier.html")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    size = os.path.getsize(out_path)
    print(colors.green(f"✓ Standalone HTML dossier generated successfully!"))
    print(f"  Location: {colors.cyan(os.path.abspath(out_path))}")
    print(f"  Size:     {size:,} bytes")
    print(colors.dim("  100% self-contained: CSS, fonts, and data embedded for offline/air-gapped use.\n"))


def cmd_audit_verify(args, colors: Colors):
    """Verifies SHA-256 tamper-evident audit chain."""
    db = get_database(args.db)
    spec_id = args.spec  # None verifies all specs in ledger

    print(colors.bold("\n================================================================================"))
    print(colors.bold("   CRYPTOGRAPHIC AUDIT SEAL INTEGRITY CHECK (SHA-256 Chained Ledger)"))
    print(colors.dim(f"   Target Spec: {spec_id or 'ALL SPECIFICATIONS'} | Genesis Hash: {GENESIS_HASH[:16]}..."))
    print(colors.bold("================================================================================\n"))

    res = verify_ledger_integrity(db, spec_id=spec_id)

    # Print block-by-block trace
    for detail in res.entries_detail:
        block_id = f"#{detail['id']:03d}"
        ts = detail["timestamp"]
        act = f"[{detail['action']}]".ljust(18)
        tgt = detail["entity_id"].ljust(15)
        prev_sub = detail["prev_hash"][:10] + "..."
        curr_sub = detail["entry_hash"][:10] + "..."

        if detail["valid"]:
            status_symbol = colors.green("[✓ PASS]")
            print(f"  {status_symbol} Block {block_id} │ {ts} │ {act} │ {tgt} │ Prev: {prev_sub} ➔ Hash: {curr_sub}")
        else:
            status_symbol = colors.bg_red("[✗ TAMPERED]")
            print(f"  {status_symbol} Block {block_id} │ {ts} │ {act} │ {tgt}")
            print(colors.red(f"      Expected Prev: {detail['expected_prev']}"))
            print(colors.red(f"      Stored Prev:   {detail['prev_hash']}"))
            print(colors.red(f"      Computed Hash: {detail['computed_hash']}"))
            print(colors.red(f"      Stored Hash:   {detail['entry_hash']}"))

    print()
    print(colors.bold("================================================================================"))

    if res.is_valid:
        print(colors.green(colors.bold(f"   [✓] INTEGRITY AUDIT: 100% VERIFIED")))
        print(f"   * Total Chained Entries Checked: {colors.bold(str(res.total_entries))}")
        print(f"   * Broken Linkages / Tampering:   {colors.bold('0')}")
        print(f"   * Status:                        {colors.green('UNCOMPROMISED (ISO-27001 Compliant)')}")
        print(colors.bold("================================================================================\n"))
        sys.exit(0)
    else:
        print(colors.bg_red(colors.bold(f"   [✗] INTEGRITY BREACH DETECTED!")))
        print(f"   * Total Entries Checked: {res.total_entries}")
        print(f"   * Tampered Entries:      {colors.red(str(len(res.tampered_entries)))}")
        for t in res.tampered_entries:
            print(colors.red(f"     - Block #{t['id']} ({t['entity_id']}): {t['reason']}"))
        print(colors.bold("================================================================================\n"))
        sys.exit(1)


# ------------------ MAIN DISPATCHER ------------------ #

def main():
    parser = argparse.ArgumentParser(
        prog="speckit-cli",
        description="Corporate Spec-Kit: Standalone Specification-Driven Development CLI (Zero-Dependency)",
    )
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite database (default: specs_storage/speckit.db)")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI terminal colors")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # list
    p_list = subparsers.add_parser("list", help="Tabular list of requirements with status, version, author")
    p_list.add_argument("--spec", type=str, default=None, help="Specification ID (e.g. proj-airgap-gateway)")

    # provenance
    p_prov = subparsers.add_parser("provenance", help="ASCII tree showing origins ('Откуда что родилось') and downstream tasks")
    p_prov.add_argument("target_id", type=str, help="Requirement ID or Lineage Node ID (e.g. REQ-SEC-001)")
    p_prov.add_argument("--spec", type=str, default=None, help="Specification ID")

    # diff
    p_diff = subparsers.add_parser("diff", help="Colored ANSI diff between requirement versions")
    p_diff.add_argument("req_id", type=str, help="Requirement ID (e.g. REQ-SEC-001)")
    p_diff.add_argument("v1", type=str, help="Starting version (e.g. 1)")
    p_diff.add_argument("v2", type=str, help="Ending version (e.g. 2)")

    # matrix
    p_mat = subparsers.add_parser("matrix", help="ASCII Traceability Matrix with coverage percentage and orphan warnings")
    p_mat.add_argument("--spec", type=str, default=None, help="Specification ID")

    # clarify
    p_clar = subparsers.add_parser("clarify", help="List open/resolved clarification questions")
    p_clar.add_argument("--spec", type=str, default=None, help="Specification ID")

    # export-md
    p_ex_md = subparsers.add_parser("export-md", help="Generate Spec-Kit markdown files in specs_storage/")
    p_ex_md.add_argument("--spec", type=str, default=None, help="Specification ID")
    p_ex_md.add_argument("--output", type=str, default=None, help="Target directory for markdown files")

    # export-html
    p_ex_html = subparsers.add_parser("export-html", help="Generate single-file self-contained HTML report")
    p_ex_html.add_argument("--spec", type=str, default=None, help="Specification ID")
    p_ex_html.add_argument("--output", type=str, default=None, help="Target HTML file path")

    # audit-verify
    p_audit = subparsers.add_parser("audit-verify", help="Verify SHA-256 tamper-evident audit chain")
    p_audit.add_argument("--spec", type=str, default=None, help="Specification ID (optional; checks all if omitted)")

    args = parser.parse_args()

    colors = Colors(enabled=not args.no_color)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "list": cmd_list,
        "provenance": cmd_provenance,
        "diff": cmd_diff,
        "matrix": cmd_matrix,
        "clarify": cmd_clarify,
        "export-md": cmd_export_md,
        "export-html": cmd_export_html,
        "audit-verify": cmd_audit_verify,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args, colors)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
