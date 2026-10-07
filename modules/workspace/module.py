"""Workspace and File Drop Module for Corporate Spec-Kit.

КОНЦЕПТУАЛЬНАЯ ТРИАДА МОДУЛЯ:
- ЗАЧЕМ: Эксперту или разработчику неудобно настраивать пути в консоли, переносить файлы по SSH или редактировать конфиги.
  Нужна простая точка входа в файловой системе и интерфейсе.
- ЧТО: Локальная директория `workspace/` с автоматическим обнаружением проектов:
  1) `_handle_list_files`: сканирование дерева каталогов и списка проектов.
  2) `_handle_upload`: прием файлов и `.zip` архивов через Web UI (Drag & Drop) с безопасной распаковкой.
  3) Защита от Path Traversal и Zip Slip атак.
- ДЛЯ ЧЕГО: Пользователь за секунды закидывает свой PoC (файлами или zip-архивом) и отправляет его в пайплайн в 1 клик.

Pure standard library Python 3.8+; zero external dependencies.
"""
import base64
import os
import shutil
import zipfile
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Callable
import sqlite3

from ..base import BaseModule


class WorkspaceModule(BaseModule):
    """Manages local workspace folder for user uploads and vibe-code projects."""

    def __init__(self, db, workspace_dir: str = None):
        self.db = db
        # Root workspace folder inside corporate_speckit or custom
        if workspace_dir:
            self.workspace_dir = os.path.abspath(workspace_dir)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.workspace_dir = os.path.join(base_dir, "workspace")
        os.makedirs(self.workspace_dir, exist_ok=True)

    @property
    def slug(self) -> str:
        return "workspace"

    @property
    def name(self) -> str:
        return "Рабочая папка (Workspace & File Drop)"

    @property
    def description(self) -> str:
        return "Локальная папка проекта для загрузки файлов, распаковки zip-архивов и запуска нормализации."

    @property
    def icon(self) -> str:
        return "📂"

    @property
    def version(self) -> str:
        return "1.0.0"

    def init_db(self, conn: sqlite3.Connection):
        conn.execute("""
        CREATE TABLE IF NOT EXISTS workspace_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            item_path TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'User',
            timestamp TEXT NOT NULL
        )
        """)

    def get_routes(self) -> List[Tuple[str, str, Callable]]:
        return [
            ("GET", "/api/modules/workspace/files", self._handle_list_files),
            ("POST", "/api/modules/workspace/upload", self._handle_upload),
            ("POST", "/api/modules/workspace/create_folder", self._handle_create_folder),
            ("POST", "/api/modules/workspace/delete", self._handle_delete),
        ]

    def _safe_path(self, rel_path: str) -> str:
        """Resolve path ensuring it does not escape workspace directory (Path Traversal defense)."""
        clean_rel = os.path.normpath(rel_path.strip().lstrip("/\\"))
        target = os.path.abspath(os.path.join(self.workspace_dir, clean_rel))
        if not target.startswith(self.workspace_dir):
            raise PermissionError("Path traversal outside workspace directory is prohibited.")
        return target

    def _handle_list_files(self, handler):
        """List all items in the workspace."""
        query = getattr(handler, "query", {})
        subfolder = ""
        if isinstance(query, dict) and "folder" in query:
            vals = query["folder"]
            subfolder = vals[0] if isinstance(vals, list) and vals else str(vals)

        try:
            target_dir = self._safe_path(subfolder)
        except Exception as e:
            handler._send_json(400, {"error": str(e)})
            return

        if not os.path.exists(target_dir):
            handler._send_json(404, {"error": "Folder not found"})
            return

        items = []
        projects = []

        try:
            for entry in os.scandir(target_dir):
                stat = entry.stat()
                mod_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                rel = os.path.relpath(entry.path, self.workspace_dir).replace("\\", "/")
                
                is_dir = entry.is_dir()
                item_info = {
                    "name": entry.name,
                    "relative_path": rel,
                    "is_dir": is_dir,
                    "size_bytes": stat.st_size if not is_dir else 0,
                    "modified": mod_iso,
                    "extension": os.path.splitext(entry.name)[1].lower() if not is_dir else ""
                }
                items.append(item_info)

                if is_dir and target_dir == self.workspace_dir:
                    projects.append(entry.name)

            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            projects.sort()

            handler._send_json(200, {
                "workspace_root": self.workspace_dir,
                "current_subfolder": subfolder,
                "items": items,
                "detected_projects": projects
            })
        except Exception as e:
            handler._send_json(500, {"error": str(e)})

    def _handle_upload(self, handler):
        """Upload file or unpack zip archive into workspace."""
        data = handler._read_json_body()
        filename = data.get("filename", "")
        content_b64 = data.get("content_base64", "")
        target_folder = data.get("target_folder", "")
        unzip = data.get("unzip", False)

        if not filename or not content_b64:
            handler._send_json(400, {"error": "filename and content_base64 are required"})
            return

        try:
            dest_folder = self._safe_path(target_folder)
            os.makedirs(dest_folder, exist_ok=True)
            target_file = os.path.join(dest_folder, os.path.basename(filename))

            file_bytes = base64.b64decode(content_b64)
            with open(target_file, "wb") as f:
                f.write(file_bytes)

            unpacked_files = []
            if unzip and filename.lower().endswith(".zip"):
                extract_dir = os.path.splitext(target_file)[0]
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(target_file, "r") as zf:
                    for member in zf.namelist():
                        # Protect against Zip Slip
                        member_path = os.path.abspath(os.path.join(extract_dir, member))
                        if member_path.startswith(extract_dir):
                            zf.extract(member, extract_dir)
                            unpacked_files.append(member)

            with self.db.get_connection() as conn:
                conn.execute(
                    "INSERT INTO workspace_activity (action, item_path, timestamp) VALUES (?, ?, ?)",
                    ("upload", target_file, datetime.now(timezone.utc).isoformat())
                )

            handler._send_json(201, {
                "status": "success",
                "saved_path": target_file,
                "size_bytes": len(file_bytes),
                "unpacked": len(unpacked_files) > 0,
                "unpacked_count": len(unpacked_files)
            })
        except Exception as e:
            handler._send_json(500, {"error": f"Upload failed: {str(e)}"})

    def _handle_create_folder(self, handler):
        data = handler._read_json_body()
        folder_name = data.get("folder_name", "").strip()
        parent_folder = data.get("parent_folder", "").strip()

        if not folder_name:
            handler._send_json(400, {"error": "folder_name required"})
            return

        try:
            target = self._safe_path(os.path.join(parent_folder, folder_name))
            os.makedirs(target, exist_ok=True)
            handler._send_json(201, {"status": "created", "path": target})
        except Exception as e:
            handler._send_json(500, {"error": str(e)})

    def _handle_delete(self, handler):
        data = handler._read_json_body()
        rel_path = data.get("relative_path", "")

        if not rel_path:
            handler._send_json(400, {"error": "relative_path required"})
            return

        try:
            target = self._safe_path(rel_path)
            if not os.path.exists(target):
                handler._send_json(404, {"error": "Item not found"})
                return

            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)

            handler._send_json(200, {"status": "deleted", "path": rel_path})
        except Exception as e:
            handler._send_json(500, {"error": str(e)})

    def get_ui_manifest(self) -> Dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "icon": self.icon,
            "has_tab": True,
            "tab_id": f"tab-mod-{self.slug}",
            "tab_label": f"{self.icon} {self.name}",
        }
