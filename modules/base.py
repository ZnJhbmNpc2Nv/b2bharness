"""Base Module Contract for Corporate Spec-Kit.
Zero external dependencies; pure Python standard library.
Enables pluggable extensions for Knowledge Base, Requirements Bank, File Attachments, etc.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Callable
import sqlite3


class BaseModule(ABC):
    """Abstract contract for pluggable Spec-Kit extensions."""

    @property
    @abstractmethod
    def slug(self) -> str:
        """Unique slug identifier (e.g. 'knowledge_base', 'req_bank')."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Display name (e.g. 'База знаний (Knowledge Vault)')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what this module provides."""
        pass

    @property
    def icon(self) -> str:
        """Icon representing the module (e.g. '📚', '🏦', '📎')."""
        return "📦"

    @property
    def version(self) -> str:
        return "1.0.0"

    def init_db(self, conn: sqlite3.Connection):
        """Initialize tables, indices, and seed data for this module."""
        pass

    def get_routes(self) -> List[Tuple[str, str, Callable]]:
        """
        Return list of API routes to register.
        Format: [('GET', '/api/modules/<slug>/items', handler_callable), ...]
        """
        return []

    def get_ui_manifest(self) -> Dict[str, Any]:
        """
        Return UI metadata for mounting tabs, buttons, or modals into the frontend.
        """
        return {
            "slug": self.slug,
            "name": self.name,
            "icon": self.icon,
            "has_tab": True,
            "tab_id": f"tab-mod-{self.slug}",
            "tab_label": f"{self.icon} {self.name}",
        }

    def get_lineage_contributions(self, conn: sqlite3.Connection, spec_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Optional: Return extra lineage nodes and edges to inject into the visual DAG.
        Returns: {'nodes': [...], 'edges': [...]}
        """
        return {"nodes": [], "edges": []}
