"""AST-based SAST Security Scanner, SBOM Generator, and Distribution Sealer.

КОНЦЕПТУАЛЬНАЯ ТРИАДА МОДУЛЯ:
- ЗАЧЕМ: Код, синтезированный LLM или экспертами, может содержать классические уязвимости (SQLi, Command Injection, eval)
  и несовместимые или уязвимые зависимости. Без проверки такой код блокируется безопасниками при релизе.
- ЧТО: Три составляющие безопасной сборки:
  1) `AstSastScanner`: статический синтаксический анализ Python AST (правила SEC-001 ... SEC-006).
  2) `SbomGenerator`: генерация спецификации состава ПО в стандарте CycloneDX 1.5 JSON.
  3) `ModuleSealer`: криптографическая SHA-256 печать всех файлов дистрибутива (seal.json).
- ДЛЯ ЧЕГО: Автоматическое получение подтверждения безопасности (security score, 0 critical findings)
  и подготовка пакета для аудита ИБ без необходимости ручного вычитывания кода.

Strict Standard Library Python 3.8+, Zero External Dependencies.
"""

import os
import ast
import sys
import uuid
import json
import hashlib
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple, Union


# Standard library modules fallback for Python 3.8 / 3.9 compatibility
_FALLBACK_STDLIB_MODULES = frozenset({
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio", "asyncore",
    "atexit", "audioop", "base64", "bdb", "binascii", "binhex", "bisect", "builtins",
    "bz2", "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd", "code", "codecs",
    "codeop", "collections", "colorsys", "compileall", "concurrent", "configparser",
    "contextlib", "contextvars", "copy", "copyreg", "cProfile", "crypt", "csv",
    "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal", "difflib",
    "dis", "distutils", "doctest", "email", "encodings", "ensurepip", "enum",
    "errno", "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch", "formatter",
    "fractions", "ftplib", "functools", "gc", "getopt", "getpass", "gettext",
    "glob", "graphlib", "grp", "gzip", "hashlib", "heapq", "hmac", "html", "http",
    "imaplib", "imghdr", "imp", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "lib2to3", "linecache", "locale", "logging", "lzma", "mailbox",
    "mailcap", "marshal", "math", "mimetypes", "mmap", "modulefinder", "msilib",
    "msvcrt", "multiprocessing", "netrc", "nis", "nntplib", "numbers", "operator",
    "optparse", "os", "ossaudiodev", "parser", "pathlib", "pdb", "pickle", "pickletools",
    "pipes", "pkgutil", "platform", "plistlib", "poplib", "posix", "posixpath",
    "pprint", "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc",
    "queue", "quopri", "random", "re", "readline", "reprlib", "resource", "rlcompleter",
    "runpy", "sched", "secrets", "select", "selectors", "shelve", "shlex", "shutil",
    "signal", "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "spwd",
    "sqlite3", "sre_compile", "sre_constants", "sre_parse", "ssl", "stat", "statistics",
    "string", "stringprep", "struct", "subprocess", "sunau", "symbol", "symtable",
    "sys", "sysconfig", "syslog", "tabnanny", "tarfile", "telnetlib", "tempfile",
    "termios", "test", "textwrap", "threading", "time", "timeit", "tkinter", "token",
    "tokenize", "tomllib", "trace", "traceback", "tracemalloc", "tty", "turtle",
    "turtledemo", "types", "typing", "unicodedata", "unittest", "urllib", "uu",
    "uuid", "venv", "warnings", "wave", "weakref", "webbrowser", "winreg", "winsound",
    "wsgiref", "xdrlib", "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
    "_thread", "_tkinter"
})

def get_stdlib_modules() -> Set[str]:
    """Returns set of Python standard library top-level module names."""
    if hasattr(sys, "stdlib_module_names"):
        return set(sys.stdlib_module_names)
    return set(_FALLBACK_STDLIB_MODULES)


# ============================================================================
# AstSastScanner: AST-based SAST Security Engine
# ============================================================================

class _SastVisitor(ast.NodeVisitor):
    """AST NodeVisitor implementing corporate SAST security rules."""

    def __init__(self, lines: List[str], filename: str):
        self.lines = lines
        self.filename = filename
        self.findings: List[Dict[str, Any]] = []

    def _get_snippet(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1].strip()
        return ""

    def add_finding(
        self,
        rule_id: str,
        severity: str,
        node: ast.AST,
        message: str,
    ) -> None:
        lineno = getattr(node, "lineno", 1)
        col_offset = getattr(node, "col_offset", 0)
        self.findings.append({
            "rule_id": rule_id,
            "severity": severity,
            "line": lineno,
            "col": col_offset,
            "message": message,
            "snippet": self._get_snippet(lineno),
            "filename": self.filename,
        })

    def visit_Call(self, node: ast.Call) -> None:
        caller_name = ""
        func_name = ""

        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
            if isinstance(node.func.value, ast.Name):
                caller_name = node.func.value.id
            elif isinstance(node.func.value, ast.Attribute):
                caller_name = node.func.value.attr

        # --------------------------------------------------------------------
        # SEC-001 (SQL Injection):
        # Raw string formatting / f-strings / % concatenation inside
        # .execute(...) or .raw(...) calls.
        # --------------------------------------------------------------------
        if func_name in ("execute", "raw", "executemany") and node.args:
            arg0 = node.args[0]
            is_unsafe_sql = False
            # Check for f-string (JoinedStr)
            if isinstance(arg0, ast.JoinedStr):
                is_unsafe_sql = True
            # Check for string % formatting or + concatenation
            elif isinstance(arg0, ast.BinOp) and isinstance(arg0.op, (ast.Mod, ast.Add)):
                is_unsafe_sql = True
            # Check for .format(...) call
            elif (
                isinstance(arg0, ast.Call)
                and isinstance(arg0.func, ast.Attribute)
                and arg0.func.attr == "format"
            ):
                is_unsafe_sql = True

            if is_unsafe_sql:
                self.add_finding(
                    rule_id="SEC-001",
                    severity="HIGH",
                    node=node,
                    message=f"Potential SQL Injection: dynamic SQL formatting or concatenation detected in {func_name}() query argument.",
                )

        # --------------------------------------------------------------------
        # SEC-002 (Command Injection):
        # subprocess.Popen/call/run with shell=True or unescaped arguments,
        # os.system(...), os.popen(...).
        # --------------------------------------------------------------------
        if caller_name == "os" and func_name in ("system", "popen"):
            self.add_finding(
                rule_id="SEC-002",
                severity="CRITICAL",
                node=node,
                message=f"Potential Command Injection: use of os.{func_name}() executes unescaped shell commands.",
            )
        elif not caller_name and func_name in ("system", "popen"):
            self.add_finding(
                rule_id="SEC-002",
                severity="CRITICAL",
                node=node,
                message=f"Potential Command Injection: use of {func_name}() executes unescaped shell commands.",
            )

        subprocess_names = {"Popen", "call", "run", "check_call", "check_output"}
        if (caller_name == "subprocess" and func_name in subprocess_names) or (
            not caller_name and func_name in subprocess_names
        ):
            has_shell_true = False
            for kw in node.keywords:
                if kw.arg == "shell":
                    if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        has_shell_true = True
                    elif not (isinstance(kw.value, ast.Constant) and kw.value.value is False):
                        has_shell_true = True

            has_dynamic_cmd = False
            if node.args:
                cmd_arg = node.args[0]
                if isinstance(cmd_arg, (ast.JoinedStr, ast.BinOp)):
                    has_dynamic_cmd = True
                elif (
                    isinstance(cmd_arg, ast.Call)
                    and isinstance(cmd_arg.func, ast.Attribute)
                    and cmd_arg.func.attr == "format"
                ):
                    has_dynamic_cmd = True

            if has_shell_true:
                self.add_finding(
                    rule_id="SEC-002",
                    severity="HIGH",
                    node=node,
                    message=f"Potential Command Injection: subprocess.{func_name}() invoked with shell=True.",
                )
            elif has_dynamic_cmd:
                self.add_finding(
                    rule_id="SEC-002",
                    severity="HIGH",
                    node=node,
                    message=f"Potential Command Injection: subprocess.{func_name}() invoked with dynamically constructed command string.",
                )

        # --------------------------------------------------------------------
        # SEC-003 (Insecure Deserialization):
        # pickle.loads(...), pickle.load(...), yaml.load(...) without SafeLoader.
        # --------------------------------------------------------------------
        if caller_name in ("pickle", "_pickle") and func_name in ("load", "loads"):
            self.add_finding(
                rule_id="SEC-003",
                severity="CRITICAL",
                node=node,
                message=f"Insecure Deserialization: {caller_name}.{func_name}() allows arbitrary code execution from untrusted input.",
            )
        elif caller_name == "yaml" and func_name == "load":
            has_safe_loader = False
            for kw in node.keywords:
                if kw.arg == "Loader":
                    if isinstance(kw.value, ast.Name) and "Safe" in kw.value.id:
                        has_safe_loader = True
                    elif isinstance(kw.value, ast.Attribute) and "Safe" in kw.value.attr:
                        has_safe_loader = True
            if not has_safe_loader:
                self.add_finding(
                    rule_id="SEC-003",
                    severity="HIGH",
                    node=node,
                    message="Insecure Deserialization: yaml.load() called without SafeLoader allows arbitrary code execution.",
                )

        # --------------------------------------------------------------------
        # SEC-004 (Unsafe Dynamic Code):
        # eval(...), exec(...).
        # --------------------------------------------------------------------
        if (caller_name in ("", "builtins")) and func_name in ("eval", "exec"):
            self.add_finding(
                rule_id="SEC-004",
                severity="CRITICAL",
                node=node,
                message=f"Unsafe Dynamic Code: direct invocation of {func_name}() enables arbitrary Python code execution.",
            )

        # --------------------------------------------------------------------
        # SEC-005 (Path Traversal):
        # open(...) directly using unsanitized string addition.
        # --------------------------------------------------------------------
        is_open = (caller_name in ("", "io", "os", "builtins")) and func_name == "open"
        if is_open and node.args:
            path_arg = node.args[0]
            has_path_concat = False
            if isinstance(path_arg, ast.BinOp) and isinstance(path_arg.op, ast.Add):
                has_path_concat = True
            elif isinstance(path_arg, ast.JoinedStr):
                has_path_concat = True
            elif (
                isinstance(path_arg, ast.Call)
                and isinstance(path_arg.func, ast.Attribute)
                and path_arg.func.attr == "format"
            ):
                has_path_concat = True

            if has_path_concat:
                self.add_finding(
                    rule_id="SEC-005",
                    severity="MEDIUM",
                    node=node,
                    message="Potential Path Traversal: open() called with raw string concatenation or dynamic formatting on path argument.",
                )

        # --------------------------------------------------------------------
        # SEC-006 (Weak Cryptography):
        # hashlib.md5(...) or hashlib.sha1(...) used for security without usedforsecurity=False.
        # --------------------------------------------------------------------
        is_weak_crypto = False
        crypto_algo = ""
        if caller_name == "hashlib":
            if func_name in ("md5", "sha1"):
                is_weak_crypto = True
                crypto_algo = f"hashlib.{func_name}"
            elif func_name == "new" and node.args:
                first_arg = node.args[0]
                if (
                    isinstance(first_arg, ast.Constant)
                    and str(first_arg.value).lower() in ("md5", "sha1")
                ):
                    is_weak_crypto = True
                    crypto_algo = f"hashlib.new('{first_arg.value}')"

        if is_weak_crypto:
            has_usedforsecurity_false = False
            for kw in node.keywords:
                if kw.arg == "usedforsecurity":
                    if isinstance(kw.value, ast.Constant) and kw.value.value is False:
                        has_usedforsecurity_false = True

            if not has_usedforsecurity_false:
                self.add_finding(
                    rule_id="SEC-006",
                    severity="MEDIUM",
                    node=node,
                    message=f"Weak Cryptography: Insecure hash algorithm {crypto_algo}() used without usedforsecurity=False.",
                )

        # Recurse into children
        self.generic_visit(node)


class AstSastScanner:
    """Uses Python standard library ast.NodeVisitor to perform static AST
    security analysis on Python files without external dependencies.
    """

    def scan_code(self, code: str, filename: str = "source.py") -> List[Dict[str, Any]]:
        """Scans Python code using AST visitor.
        Catches syntax errors gracefully without crashing.

        Returns findings list:
            [{"rule_id": str, "severity": str, "line": int, "col": int,
              "message": str, "snippet": str, "filename": str}, ...]
        """
        try:
            tree = ast.parse(code, filename=filename)
        except SyntaxError as e:
            return [{
                "rule_id": "SYNTAX_ERROR",
                "severity": "CRITICAL",
                "line": e.lineno or 1,
                "col": e.offset or 0,
                "message": f"Syntax error in Python code: {e.msg}",
                "snippet": (e.text or "").strip(),
                "filename": filename,
            }]
        except Exception as e:
            return [{
                "rule_id": "PARSER_ERROR",
                "severity": "HIGH",
                "line": 1,
                "col": 0,
                "message": f"Failed to parse source file: {str(e)}",
                "snippet": "",
                "filename": filename,
            }]

        lines = code.splitlines()
        visitor = _SastVisitor(lines=lines, filename=filename)
        visitor.visit(tree)

        # Return findings sorted by line number and column
        return sorted(visitor.findings, key=lambda f: (f["line"], f.get("col", 0)))

    def scan_project(self, project_dir: Union[str, Path]) -> Dict[str, Any]:
        """Scans all .py files in project_dir recursively, computing
        a security score and summary statistics.
        """
        base_dir = Path(project_dir)
        if not base_dir.is_dir():
            return {
                "project_dir": str(base_dir),
                "total_files_scanned": 0,
                "total_findings": 0,
                "security_score": 100,
                "severity_counts": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
                "rule_counts": {},
                "findings": [],
            }

        skip_dirs = {
            ".git", ".svn", ".hg", "__pycache__", ".venv", "venv",
            "node_modules", ".tox", ".idea", ".vscode", "build", "dist"
        }

        all_findings: List[Dict[str, Any]] = []
        files_scanned = 0

        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]

            for file_name in files:
                if file_name.endswith(".py"):
                    file_path = Path(root) / file_name
                    files_scanned += 1
                    rel_name = str(file_path.relative_to(base_dir)).replace("\\", "/")

                    try:
                        code = file_path.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        continue

                    findings = self.scan_code(code, filename=rel_name)
                    all_findings.extend(findings)

        # Compute summary stats & severity counts
        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        rule_counts: Dict[str, int] = {}

        # Security Score calculation:
        # Starts at 100.
        # CRITICAL: -25 pts
        # HIGH:     -15 pts
        # MEDIUM:   -5  pts
        # LOW:      -2  pts
        penalty = 0
        for f in all_findings:
            sev = f.get("severity", "LOW").upper()
            rule = f.get("rule_id", "UNKNOWN")

            if sev in severity_counts:
                severity_counts[sev] += 1
            else:
                severity_counts["LOW"] += 1

            rule_counts[rule] = rule_counts.get(rule, 0) + 1

            if sev == "CRITICAL":
                penalty += 25
            elif sev == "HIGH":
                penalty += 15
            elif sev == "MEDIUM":
                penalty += 5
            else:
                penalty += 2

        score = max(0, min(100, 100 - penalty))

        return {
            "project_dir": str(base_dir),
            "total_files_scanned": files_scanned,
            "total_findings": len(all_findings),
            "security_score": score,
            "severity_counts": severity_counts,
            "rule_counts": rule_counts,
            "findings": all_findings,
        }


# ============================================================================
# SbomGenerator: CycloneDX 1.5 JSON SBOM Generator
# ============================================================================

class SbomGenerator:
    """Parses imports from AST and requirements.txt / pyproject.toml to generate
    a valid CycloneDX 1.5 JSON Software Bill of Materials (SBOM).
    """

    def _parse_requirements_txt(self, file_path: Path) -> Dict[str, str]:
        """Parses requirements.txt into a dict of {pkg_name: version}."""
        deps: Dict[str, str] = {}
        if not file_path.is_file():
            return deps

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return deps

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue

            # Strip comments
            line = line.split("#")[0].strip()
            if not line:
                continue

            # Parse package and version: requests>=2.31.0, fastapi==0.100.0, etc.
            import re
            m = re.match(r"^([a-zA-Z0-9_\-\.]+)(?:([=><~!^]+)(.+))?", line)
            if m:
                pkg = m.group(1).lower().replace("_", "-")
                ver = m.group(3).strip() if m.group(3) else "*"
                deps[pkg] = ver

        return deps

    def _parse_pyproject_toml(self, file_path: Path) -> Dict[str, str]:
        """Simple pure standard library parser for pyproject.toml dependencies."""
        deps: Dict[str, str] = {}
        if not file_path.is_file():
            return deps

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return deps

        in_deps_section = False
        import re
        for line in content.splitlines():
            raw_line = line.strip()
            if not raw_line or raw_line.startswith("#"):
                continue

            if raw_line.startswith("["):
                section = raw_line.strip("[]").strip()
                in_deps_section = "dependencies" in section.lower()
                continue

            if in_deps_section:
                # Format: "requests>=2.28.0" or package = "^1.0.0"
                m_str = re.match(r'^["\']([a-zA-Z0-9_\-\.]+)(?:([=><~!^]+)(.+))?["\']', raw_line)
                if m_str:
                    pkg = m_str.group(1).lower().replace("_", "-")
                    ver = m_str.group(3).strip() if m_str.group(3) else "*"
                    deps[pkg] = ver
                    continue

                m_kv = re.match(r'^([a-zA-Z0-9_\-\.]+)\s*=\s*["\']([^"\']+)["\']', raw_line)
                if m_kv:
                    pkg = m_kv.group(1).lower().replace("_", "-")
                    ver = m_kv.group(2).strip()
                    deps[pkg] = ver

        return deps

    def _extract_ast_imports(self, project_dir: Path) -> Set[str]:
        """Extracts all top-level imported package names from .py files via AST."""
        stdlib = get_stdlib_modules()
        builtins_set = set(sys.builtin_module_names)
        imported_pkgs: Set[str] = set()

        # Identify internal package/module names to exclude local code
        local_modules = {p.stem for p in project_dir.glob("*.py")}
        local_packages = {p.name for p in project_dir.iterdir() if p.is_dir()}
        excluded = stdlib | builtins_set | local_modules | local_packages

        for root, _, files in os.walk(project_dir):
            for f in files:
                if f.endswith(".py"):
                    file_path = Path(root) / f
                    try:
                        tree = ast.parse(file_path.read_text(encoding="utf-8", errors="replace"))
                    except Exception:
                        continue

                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                top = alias.name.split(".")[0]
                                if top and top not in excluded and not top.startswith("_"):
                                    imported_pkgs.add(top.lower().replace("_", "-"))
                        elif isinstance(node, ast.ImportFrom):
                            if node.level == 0 and node.module:
                                top = node.module.split(".")[0]
                                if top and top not in excluded and not top.startswith("_"):
                                    imported_pkgs.add(top.lower().replace("_", "-"))

        return imported_pkgs

    def generate_sbom(
        self,
        project_dir: Union[str, Path],
        module_name: str,
        version: str = "1.0.0",
    ) -> Dict[str, Any]:
        """Generates a valid CycloneDX 1.5 JSON SBOM dictionary."""
        base_dir = Path(project_dir)

        # 1. Parse dependencies from manifest files
        req_file = base_dir / "requirements.txt"
        pyproject_file = base_dir / "pyproject.toml"

        deps_map: Dict[str, str] = {}
        deps_map.update(self._parse_requirements_txt(req_file))
        deps_map.update(self._parse_pyproject_toml(pyproject_file))

        # 2. Extract AST imports from code
        ast_deps = self._extract_ast_imports(base_dir)
        for dep in ast_deps:
            if dep not in deps_map:
                deps_map[dep] = "*"

        # 3. Construct CycloneDX 1.5 JSON components
        components: List[Dict[str, Any]] = []
        for pkg_name in sorted(deps_map.keys()):
            pkg_ver = deps_map[pkg_name]
            purl = f"pkg:pypi/{pkg_name}"
            if pkg_ver and pkg_ver != "*":
                purl = f"pkg:pypi/{pkg_name}@{pkg_ver}"

            components.append({
                "type": "library",
                "name": pkg_name,
                "version": pkg_ver,
                "purl": purl,
                "scope": "required",
            })

        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        bom_serial = f"urn:uuid:{uuid.uuid4()}"

        sbom: Dict[str, Any] = {
            "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "serialNumber": bom_serial,
            "version": 1,
            "metadata": {
                "timestamp": timestamp,
                "tools": [
                    {
                        "vendor": "Corporate Spec-Kit",
                        "name": "B2B-Harness SbomGenerator",
                        "version": "1.0.0",
                    }
                ],
                "component": {
                    "type": "application",
                    "name": module_name,
                    "version": version,
                },
            },
            "components": components,
            "dependencies": [
                {
                    "ref": module_name,
                    "dependsOn": [c["name"] for c in components],
                }
            ],
        }

        return sbom


# ============================================================================
# ModuleSealer: Cryptographic Distribution SHA-256 Sealer
# ============================================================================

class ModuleSealer:
    """Generates and verifies SHA-256 seal manifests over all files in
    an output distribution directory.
    """

    def __init__(self, chunk_size: int = 64 * 1024):
        self.chunk_size = chunk_size

    def _hash_file(self, file_path: Path) -> Tuple[str, int]:
        """Computes SHA-256 digest and size of a file in bytes."""
        hasher = hashlib.sha256()
        total_size = 0
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
                total_size += len(chunk)
        return hasher.hexdigest(), total_size

    def create_seal(self, dist_dir: Union[str, Path]) -> Dict[str, Any]:
        """Generates SHA-256 seal manifest over all files in dist_dir.
        Returns the seal dictionary and saves seal.json to dist_dir.
        """
        base_dir = Path(dist_dir)
        if not base_dir.is_dir():
            raise FileNotFoundError(f"Distribution directory does not exist: {dist_dir}")

        skip_dirs = {".git", ".svn", "__pycache__", ".venv", "venv", ".idea"}
        skip_files = {"seal.json", ".DS_Store"}

        manifest: Dict[str, Dict[str, Any]] = {}
        total_bytes = 0

        # Collect and hash all files
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]

            for file_name in files:
                if file_name in skip_files:
                    continue

                full_path = Path(root) / file_name
                rel_path = str(full_path.relative_to(base_dir)).replace("\\", "/")

                file_hash, file_size = self._hash_file(full_path)
                total_bytes += file_size
                manifest[rel_path] = {
                    "sha256": file_hash,
                    "size_bytes": file_size,
                }

        # Deterministic cumulative root hash over sorted relative paths
        root_hasher = hashlib.sha256()
        for rel_path in sorted(manifest.keys()):
            entry = manifest[rel_path]
            line = f"{rel_path}:{entry['sha256']}:{entry['size_bytes']}\n"
            root_hasher.update(line.encode("utf-8"))

        root_hash = root_hasher.hexdigest()
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        seal_data = {
            "root_hash": root_hash,
            "algorithm": "sha256",
            "file_count": len(manifest),
            "total_size_bytes": total_bytes,
            "timestamp": timestamp,
            "manifest": manifest,
        }

        # Write seal.json manifest to distribution folder
        seal_file = base_dir / "seal.json"
        try:
            seal_file.write_text(json.dumps(seal_data, indent=2), encoding="utf-8")
        except OSError:
            pass  # Read-only filesystem

        return seal_data

    def verify_seal(
        self,
        dist_dir: Union[str, Path],
        seal_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        """Verifies integrity of distribution files against seal manifest.
        Returns (is_valid, list_of_errors).
        """
        base_dir = Path(dist_dir)
        if not base_dir.is_dir():
            return False, [f"Distribution directory does not exist: {dist_dir}"]

        if seal_data is None:
            seal_file = base_dir / "seal.json"
            if not seal_file.is_file():
                return False, ["Missing seal.json manifest file"]
            try:
                seal_data = json.loads(seal_file.read_text(encoding="utf-8"))
            except Exception as e:
                return False, [f"Failed to read seal.json: {str(e)}"]

        manifest = seal_data.get("manifest", {})
        errors: List[str] = []

        # Check existing files against manifest
        for rel_path, expected in manifest.items():
            file_path = base_dir / rel_path
            if not file_path.is_file():
                errors.append(f"Missing file: {rel_path}")
                continue

            current_hash, current_size = self._hash_file(file_path)
            if current_size != expected.get("size_bytes"):
                errors.append(
                    f"Size mismatch in {rel_path}: expected {expected.get('size_bytes')}, got {current_size}"
                )
            if current_hash != expected.get("sha256"):
                errors.append(
                    f"Checksum mismatch in {rel_path}: expected {expected.get('sha256')}, got {current_hash}"
                )

        return len(errors) == 0, errors
