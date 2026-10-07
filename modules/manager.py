"""ModuleManager for Corporate Spec-Kit.
Discovers, initializes, and routes pluggable extensions.
Zero external dependencies; pure Python standard library.
"""
import os
import sys
import importlib
import sqlite3
from typing import Dict, Any, List, Optional, Tuple, Callable
from pathlib import Path

from .base import BaseModule


class ModuleManager:
    def __init__(self, db, modules_dir: Optional[str] = None):
        self.db = db
        self.modules_dir = modules_dir or os.path.dirname(os.path.abspath(__file__))
        self.modules: Dict[str, BaseModule] = {}
        self._routes_map: Dict[Tuple[str, str], Callable] = {}
        self._discover_and_register_modules()

    def register_module(self, module: BaseModule):
        """Register a module instance."""
        self.modules[module.slug] = module
        
        # Initialize DB tables for the module
        with self.db.get_connection() as conn:
            module.init_db(conn)

        # Register API routes
        for method, path, handler in module.get_routes():
            self._routes_map[(method.upper(), path)] = handler

    def _discover_and_register_modules(self):
        """Dynamically load built-in and custom modules."""
        # Ensure modules directory is in sys.path
        parent_dir = os.path.dirname(self.modules_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        # Check subdirectories
        for item in os.listdir(self.modules_dir):
            item_path = os.path.join(self.modules_dir, item)
            if os.path.isdir(item_path) and not item.startswith("__") and not item.startswith("."):
                module_file = os.path.join(item_path, "module.py")
                if os.path.exists(module_file):
                    try:
                        pkg_name = f"modules.{item}.module"
                        mod = importlib.import_module(pkg_name)
                        # Look for factory or subclass
                        for attr_name in dir(mod):
                            attr = getattr(mod, attr_name)
                            if (isinstance(attr, type) and 
                                issubclass(attr, BaseModule) and 
                                attr is not BaseModule):
                                instance = attr(self.db)
                                self.register_module(instance)
                                break
                    except Exception as e:
                        print(f"[!] Warning: Failed to load module '{item}': {e}")

    def dispatch_route(self, method: str, path: str, req_handler) -> bool:
        """
        Check if an API request matches any registered module route.
        Returns True if handled, False otherwise.
        """
        key = (method.upper(), path)
        if key in self._routes_map:
            handler = self._routes_map[key]
            handler(req_handler)
            return True
        return False

    def get_modules_manifest(self) -> List[Dict[str, Any]]:
        """Return list of active modules and their UI metadata."""
        return [mod.get_ui_manifest() for mod in self.modules.values()]

    def collect_lineage_contributions(self, spec_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Aggregate extra nodes and edges contributed by all active modules."""
        all_nodes = []
        all_edges = []
        with self.db.get_connection() as conn:
            for mod in self.modules.values():
                contrib = mod.get_lineage_contributions(conn, spec_id)
                all_nodes.extend(contrib.get("nodes", []))
                all_edges.extend(contrib.get("edges", []))
        return {"nodes": all_nodes, "edges": all_edges}
