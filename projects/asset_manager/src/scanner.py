import os
from pathlib import Path

class AssetScanner:
    def __init__(self, root_path: str, forbidden_paths: list[str] | None = None):
        self.root_path = Path(root_path).resolve()
        self.forbidden_paths = [Path(p).resolve() for p in (forbidden_paths or [])]

    def is_safe(self, path: Path) -> bool:
        try:
            resolved_path = path.resolve()
            # Проверка, что путь внутри root_path
            if not str(resolved_path).startswith(str(self.root_path)):
                return False
            # Проверка на запрещенные директории
            for forbidden in self.forbidden_paths:
                if str(resolved_path).startswith(str(forbidden)):
                    return False
            return True
        except Exception:
            return False

    def scan(self):
        assets = []
        for root, dirs, files in os.walk(self.root_path):
            for file in files:
                file_path = Path(root) / file
                if self.is_safe(file_path):
                    assets.append(str(file_path))
        return assets
