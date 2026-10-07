"""Pre-Flight Secret Sanitizer and Isolated Execution Sandbox.

Strict Standard Library Python 3.8+, Zero External Dependencies.
Corporate Spec-Kit B2B-Harness Engine.
"""

import os
import re
import sys
import time
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union, Pattern


# ============================================================================
# SecretScrubber: Pre-Flight Credential & Secret Sanitizer
# ============================================================================

class SecretRule:
    """Represents a secret detection pattern rule."""
    def __init__(self, rule_type: str, pattern: Pattern[str], description: str):
        self.rule_type = rule_type
        self.pattern = pattern
        self.description = description


class SecretScrubber:
    """Scans strings, source files, and directories for exposed credentials,
    API keys, tokens, and private keys. Replaces them with redacted placeholders.
    """

    # Comprehensive detection rules without ReDoS vulnerabilities
    DEFAULT_RULES = [
        # Anthropic tokens
        SecretRule(
            "ANTHROPIC_TOKEN",
            re.compile(r"\b(sk-ant-[a-zA-Z0-9_\-]{20,})\b"),
            "Anthropic API Key",
        ),
        # OpenAI tokens
        SecretRule(
            "OPENAI_TOKEN",
            re.compile(r"\b(sk-[a-zA-Z0-9]{20,})\b"),
            "OpenAI API Key",
        ),
        # HuggingFace tokens
        SecretRule(
            "HUGGINGFACE_TOKEN",
            re.compile(r"\b(hf_[a-zA-Z0-9]{20,})\b"),
            "HuggingFace Access Token",
        ),
        # AWS Access Key IDs
        SecretRule(
            "AWS_ACCESS_KEY",
            re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
            "AWS Access Key ID",
        ),
        # AWS Secret Access Keys
        SecretRule(
            "AWS_SECRET_KEY",
            re.compile(
                r"(?i)\b(?:aws_secret_access_key|aws_secret_key)\s*[:=]\s*['\"]([A-Za-z0-9/+=]{40})['\"]"
            ),
            "AWS Secret Access Key",
        ),
        # GitHub Personal Access Tokens (classic and modern)
        SecretRule(
            "GITHUB_PAT",
            re.compile(r"\b(ghp_[a-zA-Z0-9]{36})\b"),
            "GitHub Personal Access Token (classic)",
        ),
        SecretRule(
            "GITHUB_TOKEN",
            re.compile(r"\b(gh[ousr]_[a-zA-Z0-9]{36,}|github_pat_[a-zA-Z0-9_]{22,})\b"),
            "GitHub Access Token",
        ),
        # Generic Private Keys (Full block or header)
        SecretRule(
            "PRIVATE_KEY",
            re.compile(
                r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----[\s\S]*?-----END (?:RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----"
            ),
            "Cryptographic Private Key Block",
        ),
        SecretRule(
            "PRIVATE_KEY",
            re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH) PRIVATE KEY-----"),
            "Cryptographic Private Key Header",
        ),
        # Database URIs with credentials
        SecretRule(
            "DATABASE_URI",
            re.compile(
                r"(?:postgres(?:ql)?|mysql):\/\/[^\s:@'\"]+:[^\s@'\"]+@[^\s'\"\)]+"
            ),
            "Database Connection URI with Credentials",
        ),
        SecretRule(
            "DATABASE_URI",
            re.compile(r"(?:postgres(?:ql)?|mysql):\/\/[^\s\n]+:[^\s\n]+@"),
            "Database Connection URI Header",
        ),
        # Password / secret assignments in code/configs
        SecretRule(
            "PASSWORD",
            re.compile(r"(?i)\bpassword\s*=\s*['\"][^'\"]+['\"]"),
            "Hardcoded Password Assignment",
        ),
        SecretRule(
            "PASSWORD",
            re.compile(r"(?i)\b(?:passwd|pwd|db_password)\s*=\s*['\"][^'\"]+['\"]"),
            "Hardcoded Credential Assignment",
        ),
    ]

    def __init__(self, custom_rules: Optional[List[SecretRule]] = None):
        self.rules: List[SecretRule] = list(custom_rules or self.DEFAULT_RULES)

    @staticmethod
    def mask_preview(val: str) -> str:
        """Returns a safe, masked preview of the secret value."""
        s = val.strip()
        if len(s) <= 8:
            return "*" * len(s)
        return f"{s[:4]}...{s[-4:]}"

    def scan_text(self, text: str) -> List[Dict[str, Any]]:
        """Scans a text string for secrets and returns findings.

        Returns a list of dicts containing:
            - type: Detected secret type name (e.g. 'OPENAI_TOKEN', 'AWS_ACCESS_KEY')
            - line: 1-indexed line number where the secret was detected
            - preview: Masked preview string
            - start: Start char offset in text
            - end: End char offset in text
            - description: Human-readable rule description
        """
        if not text:
            return []

        raw_matches = []
        for rule in self.rules:
            for m in rule.pattern.finditer(text):
                raw_matches.append((m.start(), m.end(), rule, m.group(0)))

        # Sort matches by start position, then by span length descending to prefer larger blocks
        raw_matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))

        findings: List[Dict[str, Any]] = []
        last_end = -1

        for start, end, rule, matched_str in raw_matches:
            # Skip overlapping matches
            if start < last_end:
                continue
            last_end = end

            # Compute 1-indexed line number
            line_no = text[:start].count("\n") + 1
            preview = self.mask_preview(matched_str)

            findings.append({
                "type": rule.rule_type,
                "line": line_no,
                "preview": preview,
                "start": start,
                "end": end,
                "description": rule.description,
            })

        return findings

    def scrub_text(self, text: str) -> str:
        """Replaces detected secrets in text with '***REDACTED_SECRET[TYPE]***'."""
        if not text:
            return text

        findings = self.scan_text(text)
        if not findings:
            return text

        # Perform replacement right-to-left so earlier string offsets remain stable
        findings_sorted = sorted(findings, key=lambda f: f["start"], reverse=True)
        result = text
        for item in findings_sorted:
            start = item["start"]
            end = item["end"]
            replacement = f"***REDACTED_SECRET[{item['type']}]***"
            result = result[:start] + replacement + result[end:]

        return result

    def scan_file(self, file_path: Union[str, Path]) -> List[Dict[str, Any]]:
        """Scans a single file for secrets without modifying it."""
        path = Path(file_path)
        if not path.is_file():
            return []

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            try:
                content = path.read_text(encoding="latin-1", errors="replace")
            except Exception:
                return []

        findings = self.scan_text(content)
        for f in findings:
            f["file"] = str(path)
            f["file_path"] = str(path)
        return findings

    def scrub_file(self, file_path: Union[str, Path]) -> Tuple[bool, List[Dict[str, Any]]]:
        """Scrubs a single file in-place if secrets are found.
        Returns (modified_bool, findings_list).
        """
        path = Path(file_path)
        findings = self.scan_file(path)
        if not findings:
            return False, []

        content = path.read_text(encoding="utf-8", errors="replace")
        scrubbed = self.scrub_text(content)
        path.write_text(scrubbed, encoding="utf-8")
        return True, findings

    def scan_and_scrub_directory(
        self, dir_path: Union[str, Path]
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """Recursively scans and sanitizes source files in dir_path.
        Skips binary files, VCS directories, and caches.

        Returns (scrubbed_files_count, all_findings).
        """
        base_dir = Path(dir_path)
        if not base_dir.is_dir():
            return 0, []

        skip_dirs = {
            ".git", ".svn", ".hg", "__pycache__", ".venv", "venv",
            "node_modules", ".tox", ".idea", ".vscode", "build", "dist"
        }
        skip_extensions = {
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
            ".pdf", ".exe", ".dll", ".so", ".dylib", ".bin", ".db",
            ".sqlite", ".sqlite3", ".pyc", ".pyd", ".zip", ".tar",
            ".gz", ".7z", ".bz2", ".woff", ".woff2", ".ttf", ".eot"
        }

        all_findings: List[Dict[str, Any]] = []
        scrubbed_files_count = 0

        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]

            for file_name in files:
                file_path = Path(root) / file_name
                if file_path.suffix.lower() in skip_extensions:
                    continue

                # Check for null bytes indicating binary content
                try:
                    with open(file_path, "rb") as f:
                        header = f.read(4096)
                        if b"\x00" in header:
                            continue
                except (OSError, IOError):
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                findings = self.scan_text(content)
                if findings:
                    for item in findings:
                        item["file"] = str(file_path)
                        item["file_path"] = str(file_path)
                        all_findings.append(item)

                    scrubbed = self.scrub_text(content)
                    file_path.write_text(scrubbed, encoding="utf-8")
                    scrubbed_files_count += 1

        return scrubbed_files_count, all_findings


# ============================================================================
# IsolatedSandboxRunner: Safe Subprocess Execution Controller
# ============================================================================

class IsolatedSandboxRunner:
    """Pure Python subprocess controller for executing vibe-code safely.

    Features:
      - Clean environment variables (strips system credentials, PATH restricted)
      - Strict execution timeout (default 30s)
      - Output size truncation (prevents runaway stdout/stderr flooding RAM)
      - Working directory isolation (runs in designated scratch/temp folder)
      - Simulates network isolation (sets dummy proxy & socket block prelude)
    """

    DEFAULT_TIMEOUT_SEC = 30
    DEFAULT_MAX_OUTPUT_BYTES = 100 * 1024  # 100 KB

    def __init__(
        self,
        default_timeout: int = DEFAULT_TIMEOUT_SEC,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ):
        self.default_timeout = default_timeout
        self.max_output_bytes = max_output_bytes

    def get_clean_env(
        self,
        allow_network: bool = False,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Generates a sanitized environment dictionary stripped of sensitive tokens."""
        clean_env: Dict[str, str] = {}

        # Safe system variables to retain
        safe_keys = {
            # Windows
            "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP",
            "USERPROFILE", "USERNAME", "APPDATA", "LOCALAPPDATA",
            # POSIX
            "HOME", "USER", "LANG", "LC_ALL", "TERM", "TMPDIR", "TZ",
        }

        # Build clean environment from safe keys
        for key, val in os.environ.items():
            if key.upper() in safe_keys:
                clean_env[key] = val

        # Explicitly ensure sensitive patterns are wiped out
        sensitive_keywords = (
            "KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "AUTH",
            "CREDENTIAL", "DATABASE", "DB_", "API_", "PRIVATE"
        )
        for key in list(clean_env.keys()):
            upper_key = key.upper()
            if any(kw in upper_key for kw in sensitive_keywords):
                clean_env.pop(key, None)

        # Restricted PATH: retain only the Python directory and system root
        python_dir = os.path.dirname(sys.executable)
        python_scripts = os.path.join(python_dir, "Scripts")

        restricted_path_parts = [python_dir]
        if os.path.isdir(python_scripts):
            restricted_path_parts.append(python_scripts)

        if sys.platform == "win32":
            win_dir = os.environ.get("SystemRoot", r"C:\Windows")
            sys32 = os.path.join(win_dir, "System32")
            restricted_path_parts.extend([sys32, win_dir])
            clean_env["PATH"] = ";".join(restricted_path_parts)
        else:
            restricted_path_parts.extend(["/usr/bin", "/bin", "/usr/local/bin"])
            clean_env["PATH"] = ":".join(restricted_path_parts)

        # Python execution isolation flags
        clean_env["PYTHONNOUSERSITE"] = "1"
        clean_env["PYTHONDONTWRITEBYTECODE"] = "1"
        clean_env["PYTHONUNBUFFERED"] = "1"

        # Network isolation proxies
        if not allow_network:
            dummy_proxy = "http://127.0.0.1:0"
            clean_env["HTTP_PROXY"] = dummy_proxy
            clean_env["HTTPS_PROXY"] = dummy_proxy
            clean_env["ALL_PROXY"] = "socks5://127.0.0.1:0"
            clean_env["NO_PROXY"] = ""
            clean_env["http_proxy"] = dummy_proxy
            clean_env["https_proxy"] = dummy_proxy

        # Apply any explicit extra environment variables
        if extra_env:
            clean_env.update(extra_env)

        return clean_env

    def _truncate_output(self, text: str) -> str:
        """Truncates output to avoid memory saturation."""
        if len(text) <= self.max_output_bytes:
            return text
        truncated = text[:self.max_output_bytes]
        return truncated + f"\n...[OUTPUT TRUNCATED: exceeded limit of {self.max_output_bytes} bytes]..."

    def execute_python(
        self,
        script_content: str,
        args: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        allow_network: bool = False,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Executes Python code in a secure, isolated subprocess.

        Returns:
            {
                "stdout": str,
                "stderr": str,
                "exit_code": int,
                "duration_sec": float,
                "timed_out": bool,
                "sandbox_dir": str,
            }
        """
        timeout_val = timeout if timeout is not None else self.default_timeout

        # Determine sandbox working directory
        created_temp_dir = False
        if cwd is None:
            sandbox_dir = tempfile.mkdtemp(prefix="speckit_sandbox_")
            created_temp_dir = True
        else:
            sandbox_dir = os.path.abspath(cwd)
            os.makedirs(sandbox_dir, exist_ok=True)

        script_file = os.path.join(sandbox_dir, "_sandbox_entry.py")

        # Network blocker prelude injected if allow_network=False
        final_script = script_content
        if not allow_network:
            network_prelude = (
                "# === Speckit Network Isolation Barrier ===\n"
                "import socket as _sb_socket\n"
                "def _sb_block_net(*args, **kwargs):\n"
                "    raise PermissionError('Network access is disabled in IsolatedSandboxRunner')\n"
                "_sb_socket.socket = _sb_block_net\n"
                "_sb_socket.create_connection = _sb_block_net\n"
                "_sb_socket.getaddrinfo = _sb_block_net\n"
                "# ==========================================\n"
            )
            final_script = network_prelude + script_content

        try:
            with open(script_file, "w", encoding="utf-8") as f:
                f.write(final_script)

            clean_env = self.get_clean_env(allow_network=allow_network, extra_env=env)
            cmd = [sys.executable, script_file] + (args or [])

            start_time = time.perf_counter()
            timed_out = False
            stdout = ""
            stderr = ""
            exit_code = -1

            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=sandbox_dir,
                    env=clean_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                stdout, stderr = proc.communicate(timeout=timeout_val)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                try:
                    stdout, stderr = proc.communicate(timeout=2)
                except Exception:
                    pass
                exit_code = -1
            except Exception as e:
                stderr = f"Sandbox execution error: {str(e)}"
                exit_code = -1

            duration = round(time.perf_counter() - start_time, 4)

            return {
                "stdout": self._truncate_output(stdout or ""),
                "stderr": self._truncate_output(stderr or ""),
                "exit_code": exit_code,
                "duration_sec": duration,
                "timed_out": timed_out,
                "sandbox_dir": sandbox_dir,
            }

        finally:
            # Clean up temp folder if created by runner
            if created_temp_dir and os.path.isdir(sandbox_dir):
                shutil.rmtree(sandbox_dir, ignore_errors=True)

    def execute_pytest_simulation(
        self,
        test_script_content: str,
        target_module_dir: str,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Runs a pure standard-library simulation of pytest test execution.
        Discovers test_* functions and Test* classes, executes them in isolation,
        and aggregates structured results.

        Returns:
            {
                "passed": int,
                "failed": int,
                "errors": int,
                "total": int,
                "success": bool,
                "tests": List[Dict[str, Any]],
                "stdout": str,
                "stderr": str,
                "exit_code": int,
                "duration_sec": float,
                "timed_out": bool,
            }
        """
        abs_module_dir = os.path.abspath(target_module_dir).replace("\\", "\\\\")

        # Harness that discovers and runs tests, printing structured summary
        runner_harness = f"""
import sys
import os
import time
import json
import inspect
import traceback

sys.path.insert(0, r"{abs_module_dir}")

test_globals = {{"__name__": "__test_sandbox__", "__file__": "test_script.py"}}
raw_code = {repr(test_script_content)}

results = []
passed = 0
failed = 0
errors = 0

print("=== SPECKIT PYTEST SIMULATION RUNNER ===")

try:
    exec(raw_code, test_globals)
except Exception as e:
    tb = traceback.format_exc()
    print("FATAL: Error during test module execution:")
    print(tb)
    results.append({{
        "name": "module_load",
        "status": "ERROR",
        "duration_sec": 0.0,
        "message": str(e),
        "traceback": tb,
    }})
    errors += 1
else:
    # Discover standalone functions starting with test_
    discovered_tests = []
    for name, obj in list(test_globals.items()):
        if name.startswith("test_") and callable(obj) and not inspect.isclass(obj):
            discovered_tests.append((name, obj, None))
        elif inspect.isclass(obj) and name.startswith("Test"):
            for m_name in dir(obj):
                if m_name.startswith("test_"):
                    method = getattr(obj, m_name)
                    if callable(method):
                        discovered_tests.append((f"{{name}}.{{m_name}}", method, obj))

    # Sort tests by discovery order
    discovered_tests.sort(key=lambda t: t[0])

    for test_name, test_func, test_cls in discovered_tests:
        t0 = time.perf_counter()
        try:
            if test_cls is not None:
                instance = test_cls()
                test_func(instance)
            else:
                test_func()
            dur = round(time.perf_counter() - t0, 4)
            passed += 1
            results.append({{
                "name": test_name,
                "status": "PASSED",
                "duration_sec": dur,
                "message": "",
            }})
            print(f"{{test_name}} ... PASSED ({{dur}}s)")
        except AssertionError as e:
            dur = round(time.perf_counter() - t0, 4)
            failed += 1
            msg = str(e) or "AssertionError"
            tb = traceback.format_exc()
            results.append({{
                "name": test_name,
                "status": "FAILED",
                "duration_sec": dur,
                "message": msg,
                "traceback": tb,
            }})
            print(f"{{test_name}} ... FAILED ({{dur}}s): {{msg}}")
        except Exception as e:
            dur = round(time.perf_counter() - t0, 4)
            errors += 1
            msg = str(e)
            tb = traceback.format_exc()
            results.append({{
                "name": test_name,
                "status": "ERROR",
                "duration_sec": dur,
                "message": msg,
                "traceback": tb,
            }})
            print(f"{{test_name}} ... ERROR ({{dur}}s): {{msg}}")

total = passed + failed + errors
print(f"\\n=== SUMMARY: {{passed}} passed, {{failed}} failed, {{errors}} errors (total {{total}}) ===")

summary_data = {{
    "passed": passed,
    "failed": failed,
    "errors": errors,
    "total": total,
    "tests": results,
    "success": (failed == 0 and errors == 0),
}}

print("\\n--SPECKIT_TEST_JSON_START--")
print(json.dumps(summary_data))
print("--SPECKIT_TEST_JSON_END--")

if failed > 0 or errors > 0:
    sys.exit(1)
else:
    sys.exit(0)
"""

        exec_res = self.execute_python(
            script_content=runner_harness,
            timeout=timeout,
            allow_network=False,
        )

        stdout = exec_res["stdout"]
        parsed_summary: Dict[str, Any] = {
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "total": 0,
            "tests": [],
            "success": False,
        }

        # Extract structured test JSON from stdout
        start_tag = "--SPECKIT_TEST_JSON_START--"
        end_tag = "--SPECKIT_TEST_JSON_END--"
        if start_tag in stdout and end_tag in stdout:
            try:
                json_part = stdout.split(start_tag, 1)[1].split(end_tag, 1)[0].strip()
                import json
                loaded = json.loads(json_part)
                parsed_summary.update(loaded)
            except Exception:
                pass
        else:
            # If runner failed before outputting JSON (e.g. fatal timeout or syntax error)
            if exec_res["timed_out"]:
                parsed_summary["errors"] = 1
                parsed_summary["total"] = 1
                parsed_summary["tests"] = [{
                    "name": "timeout",
                    "status": "ERROR",
                    "duration_sec": exec_res["duration_sec"],
                    "message": "Execution timed out",
                }]
            elif exec_res["exit_code"] != 0:
                parsed_summary["errors"] = 1
                parsed_summary["total"] = 1
                parsed_summary["tests"] = [{
                    "name": "execution_failure",
                    "status": "ERROR",
                    "duration_sec": exec_res["duration_sec"],
                    "message": exec_res["stderr"] or "Process exited with non-zero status",
                }]

        return {
            "passed": parsed_summary.get("passed", 0),
            "failed": parsed_summary.get("failed", 0),
            "errors": parsed_summary.get("errors", 0),
            "total": parsed_summary.get("total", 0),
            "success": parsed_summary.get("success", False),
            "tests": parsed_summary.get("tests", []),
            "stdout": stdout,
            "stderr": exec_res["stderr"],
            "exit_code": exec_res["exit_code"],
            "duration_sec": exec_res["duration_sec"],
            "timed_out": exec_res["timed_out"],
        }
