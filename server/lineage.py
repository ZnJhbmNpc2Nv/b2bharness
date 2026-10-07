"""Provenance & Lineage Graph Engine for Corporate Spec-Kit.
Calculates upstream ancestors ("Откуда что родилось"), downstream descendants ("Импакт / Наследники"),
and Requirement Traceability Matrices (RTM) without external dependencies.
"""
from typing import Dict, Any, List, Set
from collections import deque


class LineageEngine:
    def __init__(self, db, module_manager=None):
        self.db = db
        self.module_manager = module_manager

    def get_graph_data(self, spec_id: str) -> Dict[str, Any]:
        """Fetch all nodes and edges for the spec, including active module contributions."""
        base_data = self.db.list_lineage(spec_id)
        if self.module_manager:
            contrib = self.module_manager.collect_lineage_contributions(spec_id)
            existing_node_ids = {n["id"] for n in base_data["nodes"]}
            for node in contrib.get("nodes", []):
                if node["id"] not in existing_node_ids:
                    base_data["nodes"].append(node)
                    existing_node_ids.add(node["id"])
            base_data["edges"].extend(contrib.get("edges", []))
        return base_data

    def trace_node_provenance(self, spec_id: str, target_node_id: str) -> Dict[str, Any]:
        """
        Traverse backwards to discover the exact origin chain ("Откуда что родилось").
        Also traverses forward to discover all downstream artifacts.
        """
        graph = self.get_graph_data(spec_id)
        nodes_by_id = {n["id"]: n for n in graph["nodes"]}
        
        # Build incoming and outgoing adjacency lists
        incoming: Dict[str, List[Dict[str, Any]]] = {}
        outgoing: Dict[str, List[Dict[str, Any]]] = {}
        for edge in graph["edges"]:
            f = edge["from_node_id"]
            t = edge["to_node_id"]
            outgoing.setdefault(f, []).append(edge)
            incoming.setdefault(t, []).append(edge)

        # 1. Backwards BFS (Ancestors / Origins)
        ancestor_node_ids: Set[str] = set()
        ancestor_edge_ids: Set[int] = set()
        queue = deque([target_node_id])
        visited = {target_node_id}

        while queue:
            curr = queue.popleft()
            for edge in incoming.get(curr, []):
                parent = edge["from_node_id"]
                ancestor_edge_ids.add(edge["id"])
                if parent not in visited:
                    visited.add(parent)
                    ancestor_node_ids.add(parent)
                    queue.append(parent)

        # 2. Forwards BFS (Descendants / Children)
        descendant_node_ids: Set[str] = set()
        descendant_edge_ids: Set[int] = set()
        queue = deque([target_node_id])
        visited = {target_node_id}

        while queue:
            curr = queue.popleft()
            for edge in outgoing.get(curr, []):
                child = edge["to_node_id"]
                descendant_edge_ids.add(edge["id"])
                if child not in visited:
                    visited.add(child)
                    descendant_node_ids.add(child)
                    queue.append(child)

        return {
            "target_node": nodes_by_id.get(target_node_id),
            "ancestor_nodes": [nodes_by_id[nid] for nid in ancestor_node_ids if nid in nodes_by_id],
            "ancestor_edge_ids": list(ancestor_edge_ids),
            "descendant_nodes": [nodes_by_id[nid] for nid in descendant_node_ids if nid in nodes_by_id],
            "descendant_edge_ids": list(descendant_edge_ids)
        }

    def generate_traceability_matrix(self, spec_id: str) -> Dict[str, Any]:
        """
        Build full Requirements Traceability Matrix (RTM).
        Maps: Requirement -> Clarifications -> Tasks -> Tests -> Code Symbols -> Coverage Status.
        """
        reqs = self.db.list_requirements(spec_id)
        clars = self.db.list_clarifications(spec_id)
        tasks = self.db.list_tasks(spec_id)

        clars_by_req: Dict[str, List[Dict[str, Any]]] = {}
        for c in clars:
            if c.get("req_id"):
                clars_by_req.setdefault(c["req_id"], []).append(c)

        tasks_by_req: Dict[str, List[Dict[str, Any]]] = {}
        for t in tasks:
            tasks_by_req.setdefault(t["req_id"], []).append(t)

        matrix = []
        orphan_reqs = []
        total_coverage_points = 0
        max_possible_points = len(reqs) * 3 if reqs else 1

        for r in reqs:
            rid = r["id"]
            r_clars = clars_by_req.get(rid, [])
            r_tasks = tasks_by_req.get(rid, [])
            
            has_tasks = len(r_tasks) > 0
            has_tests = any(t.get("test_case_id") for t in r_tasks)
            has_code = any(t.get("code_targets") for t in r_tasks)

            # Score: 1 pt for task, 1 pt for test, 1 pt for code
            points = (1 if has_tasks else 0) + (1 if has_tests else 0) + (1 if has_code else 0)
            total_coverage_points += points
            coverage_pct = int((points / 3.0) * 100)

            if not has_tasks:
                orphan_reqs.append(rid)

            matrix.append({
                "req_id": rid,
                "title": r["title"],
                "category": r["category"],
                "version": r["current_version"],
                "status": r["status"],
                "author": f"{r['created_by']} ({r['created_role']})",
                "clarifications": [{"id": c["id"], "question": c["question"], "status": c["status"]} for c in r_clars],
                "tasks": [{"id": t["id"], "title": t["title"], "status": t["status"], "assignee": t["assignee"]} for t in r_tasks],
                "tests": [t["test_case_id"] for t in r_tasks if t.get("test_case_id")],
                "code_targets": [t["code_targets"] for t in r_tasks if t.get("code_targets")],
                "coverage_pct": coverage_pct,
                "is_complete": coverage_pct == 100
            })

        overall_coverage = int((total_coverage_points / max_possible_points) * 100) if reqs else 0

        return {
            "matrix": matrix,
            "total_requirements": len(reqs),
            "total_tasks": len(tasks),
            "orphan_requirements": orphan_reqs,
            "overall_coverage_pct": overall_coverage
        }
