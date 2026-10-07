"""Deterministic A/B Testing Engine and Mock Gateway for Corporate Spec-Kit B2B Harness.

КОНЦЕПТУАЛЬНАЯ ТРИАДА МОДУЛЯ:
- ЗАЧЕМ: Исходный vibe-код ходит в реальные сетевые API и внешние БД. При параллельном тестировании эталона и нового
  модуля возникают конфликты портов, а ответы сторонних API плавают во времени, вызывая ложные сбои (flaky tests).
- ЧТО: Двухкомпонентный движок детерминизма:
  1) `MockGateway`: перехват сетевого I/O в режиме Record & Replay (запись при первом запуске эталона, воспроизведение для модуля).
  2) `AbComparator`: функциональное сравнение JSON-схем, кодов возврата, исключений, времени и памяти.
- ДЛЯ ЧЕГО: Строгое математическое доказательство того, что нормализованный модуль работает полностью эквивалентно
  исходному коду эксперта, а при расхождении — автоматическая генерация `spec_correction.md` для коррекции спеки.

Strict Python 3.8+ standard library implementation; zero external dependencies.
"""
import os
import sys
import json
import time
import io
import difflib
import importlib.util
import subprocess
import tracemalloc
import urllib.request
import urllib.error
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Union


def get_iso_now() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MockGateway:
    """Deterministic I/O mocking with Record & Replay pattern for external services and environments."""

    def __init__(self):
        # Fixtures storage: keyed by f"{service.lower()}::{endpoint.strip('/')}"
        self._fixtures: Dict[str, List[Dict[str, Any]]] = {}
        self._recorded_calls: List[Dict[str, Any]] = []

    def _normalize_key(self, service: str, endpoint: str) -> str:
        srv = (service or "default").strip().lower()
        ep = (endpoint or "").strip().strip("/")
        return f"{srv}::{ep}"

    def _canonical_data(self, data: Any) -> Any:
        """Produce canonical data representation for deterministic comparison."""
        if isinstance(data, (dict, list)):
            return json.loads(json.dumps(data, sort_keys=True))
        if isinstance(data, (bytes, bytearray)):
            try:
                return json.loads(data.decode("utf-8"))
            except Exception:
                return data.decode("utf-8", errors="replace")
        if isinstance(data, str):
            try:
                return json.loads(data)
            except Exception:
                return data
        return data

    def record_call(self, service: str, endpoint: str, request_data: Any, response_data: Any) -> None:
        """Record an external I/O interaction for later replay or verification."""
        key = self._normalize_key(service, endpoint)
        entry = {
            "service": service,
            "endpoint": endpoint,
            "request_data": self._canonical_data(request_data),
            "response_data": response_data,
            "recorded_at": get_iso_now(),
        }
        self._recorded_calls.append(entry)

        if key not in self._fixtures:
            self._fixtures[key] = []
        # Update or append fixture
        self._fixtures[key].append(entry)

    def set_fixture(
        self, service: str, endpoint: str, response_data: Any, request_match: Optional[Any] = None
    ) -> None:
        """Register a static mock fixture for a given service and endpoint."""
        key = self._normalize_key(service, endpoint)
        entry = {
            "service": service,
            "endpoint": endpoint,
            "request_data": self._canonical_data(request_match) if request_match is not None else "*",
            "response_data": response_data,
            "recorded_at": get_iso_now(),
        }
        if key not in self._fixtures:
            self._fixtures[key] = []
        self._fixtures[key].append(entry)

    def get_mock_response(self, service: str, endpoint: str, request_data: Any = None) -> Optional[Any]:
        """Retrieve deterministic mock response for service and endpoint."""
        key = self._normalize_key(service, endpoint)
        fixtures = self._fixtures.get(key, [])
        if not fixtures:
            # Fallback search by endpoint only if service matches generic
            for k, f_list in self._fixtures.items():
                if k.endswith(f"::{endpoint.strip('/')}"):
                    fixtures = f_list
                    break

        if not fixtures:
            return None

        canonical_req = self._canonical_data(request_data) if request_data is not None else None

        # 1. Try exact request match
        if canonical_req is not None:
            for fix in fixtures:
                if fix.get("request_data") == canonical_req:
                    return fix.get("response_data")

        # 2. Try wildcard match
        for fix in fixtures:
            if fix.get("request_data") == "*":
                return fix.get("response_data")

        # 3. Fallback to first fixture recorded
        return fixtures[0].get("response_data")

    def export_fixtures(self, file_path: str) -> None:
        """Export all recorded and configured fixtures to a JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self._fixtures, f, indent=2, ensure_ascii=False)

    def load_fixtures(self, file_path: str) -> None:
        """Load mock fixtures from a JSON file."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                self._fixtures.update(data)

    def clear_fixtures(self) -> None:
        """Reset all in-memory fixtures and recorded calls."""
        self._fixtures.clear()
        self._recorded_calls.clear()

    @contextmanager
    def mock_env(self, env_vars: Dict[str, str]):
        """Temporarily mock environment variables."""
        old_env = {}
        try:
            for k, v in env_vars.items():
                if k in os.environ:
                    old_env[k] = os.environ[k]
                os.environ[k] = str(v)
            yield
        finally:
            for k in env_vars:
                if k in old_env:
                    os.environ[k] = old_env[k]
                else:
                    os.environ.pop(k, None)

    @contextmanager
    def mock_http(self):
        """Context manager intercepting urllib.request.urlopen with mock gateway responses."""
        original_urlopen = urllib.request.urlopen

        gateway = self

        def fake_urlopen(url_or_req, data=None, timeout=None, **kwargs):
            if isinstance(url_or_req, str):
                full_url = url_or_req
                req_data = data
            else:
                full_url = url_or_req.full_url
                req_data = url_or_req.data

            # Parse host and path
            from urllib.parse import urlparse
            parsed = urlparse(full_url)
            service = parsed.netloc or "default"
            endpoint = parsed.path

            mock_resp = gateway.get_mock_response(service, endpoint, req_data)
            if mock_resp is None:
                raise urllib.error.HTTPError(
                    full_url, 404, f"MockGateway: No fixture found for {service}{endpoint}", {}, None
                )

            # Build mock response object
            if isinstance(mock_resp, (dict, list)):
                resp_bytes = json.dumps(mock_resp).encode("utf-8")
                status = 200
            elif isinstance(mock_resp, str):
                resp_bytes = mock_resp.encode("utf-8")
                status = 200
            elif isinstance(mock_resp, bytes):
                resp_bytes = mock_resp
                status = 200
            elif isinstance(mock_resp, tuple) and len(mock_resp) >= 2:
                status = int(mock_resp[0])
                content = mock_resp[1]
                resp_bytes = (
                    json.dumps(content).encode("utf-8")
                    if isinstance(content, (dict, list))
                    else str(content).encode("utf-8")
                )
            else:
                resp_bytes = str(mock_resp).encode("utf-8")
                status = 200

            class MockHttpResponse:
                def __init__(self, raw_bytes: bytes, code: int):
                    self._bio = io.BytesIO(raw_bytes)
                    self.status = code
                    self.code = code
                    self.headers = {"Content-Type": "application/json"}

                def read(self, *a, **kw):
                    return self._bio.read(*a, **kw)

                def getcode(self):
                    return self.status

                def info(self):
                    return self.headers

                def close(self):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.close()

            return MockHttpResponse(resp_bytes, status)

        urllib.request.urlopen = fake_urlopen
        try:
            yield
        finally:
            urllib.request.urlopen = original_urlopen


class AbComparator:
    """Executes functional equivalence tests between reference vibe-code and normalized module."""

    def __init__(self, mock_gateway: Optional[MockGateway] = None):
        self.mock_gateway = mock_gateway or MockGateway()

    def compare_implementations(
        self,
        ref_dir: str,
        dist_dir: str,
        test_scenarios: List[Dict[str, Any]],
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute scenarios against both reference and distribution modules, comparing invariants.

        Args:
            ref_dir: Directory containing reference vibe-code prototype.
            dist_dir: Directory containing normalized distribution module.
            test_scenarios: List of test scenarios to execute and compare.
            output_dir: Optional directory to save test_log.md and spec_correction.md.

        Returns:
            Dictionary with overall pass/fail status, detailed matrices, and report contents.
        """
        ref_dir = os.path.abspath(ref_dir)
        dist_dir = os.path.abspath(dist_dir)
        out_dir = os.path.abspath(output_dir or dist_dir)
        os.makedirs(out_dir, exist_ok=True)

        scenarios_results: List[Dict[str, Any]] = []
        passed_count = 0
        failed_count = 0

        for idx, scenario in enumerate(test_scenarios, start=1):
            res = self._execute_scenario_comparison(ref_dir, dist_dir, scenario, idx)
            scenarios_results.append(res)
            if res["passed"]:
                passed_count += 1
            else:
                failed_count += 1

        all_passed = failed_count == 0
        status = "PASS" if all_passed else "DRIFT_DETECTED"
        equivalence_rate = (
            (passed_count / len(test_scenarios) * 100.0) if test_scenarios else 100.0
        )

        # Generate markdown reports
        test_log_md = self._generate_test_log(
            ref_dir, dist_dir, scenarios_results, passed_count, failed_count, equivalence_rate
        )
        test_log_path = os.path.join(out_dir, "test_log.md")
        with open(test_log_path, "w", encoding="utf-8") as f:
            f.write(test_log_md)

        spec_correction_md = None
        spec_correction_path = None
        if not all_passed:
            spec_correction_md = self._generate_spec_correction(scenarios_results)
            spec_correction_path = os.path.join(out_dir, "spec_correction.md")
            with open(spec_correction_path, "w", encoding="utf-8") as f:
                f.write(spec_correction_md)

        return {
            "status": status,
            "total_scenarios": len(test_scenarios),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "equivalence_rate": f"{equivalence_rate:.1f}%",
            "scenarios": scenarios_results,
            "test_log_path": test_log_path,
            "test_log_content": test_log_md,
            "spec_correction_path": spec_correction_path,
            "spec_correction_content": spec_correction_md,
        }

    def _execute_scenario_comparison(
        self, ref_dir: str, dist_dir: str, scenario: Dict[str, Any], index: int
    ) -> Dict[str, Any]:
        """Execute a single scenario against both ref and dist, comparing results."""
        scenario_name = scenario.get("name", f"Scenario_{index}")
        env_vars = scenario.get("env", {})
        fixtures = scenario.get("mock_fixtures", [])

        # Configure fixtures in mock gateway if provided
        for fix in fixtures:
            self.mock_gateway.set_fixture(
                service=fix.get("service", "default"),
                endpoint=fix.get("endpoint", "/"),
                response_data=fix.get("response", {}),
                request_match=fix.get("request"),
            )

        # 1. Execute Reference
        ref_run = self._run_target(ref_dir, scenario, env_vars)

        # 2. Execute Distribution
        dist_run = self._run_target(dist_dir, scenario, env_vars)

        # 3. Compare Results
        comparison = self._compare_outputs(ref_run, dist_run, scenario)

        return {
            "index": index,
            "name": scenario_name,
            "description": scenario.get("description", ""),
            "input": scenario.get("input"),
            "ref_run": ref_run,
            "dist_run": dist_run,
            "passed": comparison["passed"],
            "failure_reasons": comparison["reasons"],
            "schema_match": comparison["schema_match"],
            "value_match": comparison["value_match"],
            "code_match": comparison["code_match"],
            "error_invariant_match": comparison["error_invariant_match"],
            "latency_delta_ms": round(dist_run["duration_ms"] - ref_run["duration_ms"], 2),
            "speedup_ratio": (
                round(ref_run["duration_ms"] / dist_run["duration_ms"], 2)
                if dist_run["duration_ms"] > 0
                else 1.0
            ),
            "output_diff": comparison["diff"],
        }

    def _run_target(
        self, base_dir: str, scenario: Dict[str, Any], env_vars: Dict[str, str]
    ) -> Dict[str, Any]:
        """Run scenario target (in-process callable or subprocess script)."""
        function_name = scenario.get("function")
        module_name = scenario.get("module")
        script_file = scenario.get("script") or scenario.get("entrypoint")
        scenario_input = scenario.get("input")

        # Mode A: In-process module function execution
        if function_name and (module_name or script_file):
            target_file = (
                os.path.join(base_dir, script_file)
                if script_file
                else os.path.join(base_dir, f"{module_name}.py" if not module_name.endswith(".py") else module_name)
            )

            if os.path.exists(target_file):
                return self._run_inprocess_function(
                    target_file, function_name, scenario_input, scenario, env_vars
                )

        # Mode B: Subprocess script execution
        candidate_scripts = [
            script_file,
            "run_module.py",
            "main.py",
            "app.py",
            "cli.py",
        ]
        target_script = None
        for cand in candidate_scripts:
            if cand and os.path.exists(os.path.join(base_dir, cand)):
                target_script = os.path.join(base_dir, cand)
                break

        if target_script:
            return self._run_subprocess(target_script, scenario_input, scenario, env_vars, base_dir)

        # Fallback if no runnable found
        return {
            "status_code": -1,
            "output": None,
            "error": f"No executable target found in {base_dir}",
            "duration_ms": 0.0,
            "peak_memory_bytes": 0,
        }

    def _run_inprocess_function(
        self,
        file_path: str,
        function_name: str,
        scenario_input: Any,
        scenario: Dict[str, Any],
        env_vars: Dict[str, str],
    ) -> Dict[str, Any]:
        """Dynamically load module and execute target function while measuring timing and memory."""
        mod_dir = os.path.dirname(file_path)
        sys_path_modified = False
        if mod_dir not in sys.path:
            sys.path.insert(0, mod_dir)
            sys_path_modified = True

        status_code = 200
        output = None
        error_msg = None
        duration_ms = 0.0
        peak_memory = 0

        with self.mock_gateway.mock_env(env_vars):
            with self.mock_gateway.mock_http():
                tracemalloc.start()
                start_time = time.perf_counter()
                try:
                    module_name = f"ab_mod_{int(time.time() * 1000)}"
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    if spec is None or spec.loader is None:
                        raise ImportError(f"Cannot load spec from {file_path}")
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)

                    func = getattr(mod, function_name, None)
                    if func is None:
                        raise AttributeError(f"Function {function_name} not found in {file_path}")

                    # Invoke function with appropriate argument signature
                    args = scenario.get("args", [])
                    kwargs = scenario.get("kwargs", {})
                    if scenario_input is not None and not args and not kwargs:
                        if isinstance(scenario_input, dict):
                            # Try passing as single arg or kwargs
                            try:
                                output = func(scenario_input)
                            except TypeError:
                                output = func(**scenario_input)
                        else:
                            output = func(scenario_input)
                    else:
                        output = func(*args, **kwargs)

                except Exception as exc:
                    status_code = 500
                    error_msg = f"{type(exc).__name__}: {str(exc)}"
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    current_mem, peak_memory = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    if sys_path_modified and mod_dir in sys.path:
                        sys.path.remove(mod_dir)

        # Allow output tuple of (status_code, body)
        if isinstance(output, tuple) and len(output) == 2 and isinstance(output[0], int):
            status_code, output = output

        return {
            "status_code": status_code,
            "output": output,
            "error": error_msg,
            "duration_ms": round(duration_ms, 3),
            "peak_memory_bytes": peak_memory,
        }

    def _run_subprocess(
        self,
        script_path: str,
        scenario_input: Any,
        scenario: Dict[str, Any],
        env_vars: Dict[str, str],
        cwd: str,
    ) -> Dict[str, Any]:
        """Execute script via subprocess with timing and I/O capture."""
        cmd = [sys.executable, script_path]
        extra_args = scenario.get("args", [])
        if extra_args:
            cmd.extend([str(a) for a in extra_args])

        stdin_data = None
        if scenario_input is not None:
            if isinstance(scenario_input, (dict, list)):
                stdin_data = json.dumps(scenario_input)
            else:
                stdin_data = str(scenario_input)

        run_env = os.environ.copy()
        run_env.update(env_vars)
        run_env["PYTHONUNBUFFERED"] = "1"

        start_time = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                input=stdin_data,
                text=True,
                capture_output=True,
                env=run_env,
                cwd=cwd,
                timeout=scenario.get("timeout_sec", 15.0),
            )
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            status_code = proc.returncode

            stdout_parsed = proc.stdout.strip()
            try:
                stdout_data = json.loads(stdout_parsed)
            except Exception:
                stdout_data = stdout_parsed

            error_msg = proc.stderr.strip() if proc.stderr else None

            return {
                "status_code": status_code,
                "output": stdout_data,
                "error": error_msg,
                "duration_ms": round(duration_ms, 3),
                "peak_memory_bytes": 0,  # subprocess external
            }
        except subprocess.TimeoutExpired:
            return {
                "status_code": -1,
                "output": None,
                "error": "Execution timed out",
                "duration_ms": scenario.get("timeout_sec", 15.0) * 1000.0,
                "peak_memory_bytes": 0,
            }
        except Exception as exc:
            return {
                "status_code": -1,
                "output": None,
                "error": str(exc),
                "duration_ms": 0.0,
                "peak_memory_bytes": 0,
            }

    def _compare_outputs(
        self, ref_run: Dict[str, Any], dist_run: Dict[str, Any], scenario: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Deep comparison of ref and dist results."""
        reasons = []
        schema_match = True
        value_match = True
        code_match = True
        error_invariant_match = True

        # 1. Status Code Equivalence
        ref_code = ref_run.get("status_code")
        dist_code = dist_run.get("status_code")
        if ref_code != dist_code:
            code_match = False
            reasons.append(f"Status code mismatch: ref={ref_code}, dist={dist_code}")

        # 2. Error Invariants
        ref_err = ref_run.get("error")
        dist_err = dist_run.get("error")
        if bool(ref_err) != bool(dist_err):
            # One had error, one did not
            error_invariant_match = False
            reasons.append(
                f"Error invariant mismatch: ref_error='{ref_err}', dist_error='{dist_err}'"
            )

        # 3. Output Schema & Value Equivalence
        ref_out = ref_run.get("output")
        dist_out = dist_run.get("output")

        ref_is_json = isinstance(ref_out, (dict, list))
        dist_is_json = isinstance(dist_out, (dict, list))

        if ref_is_json and dist_is_json:
            schema_ok, schema_err = self._check_json_schema_equivalence(ref_out, dist_out)
            if not schema_ok:
                schema_match = False
                reasons.append(f"Schema drift: {schema_err}")

            if ref_out != dist_out:
                value_match = False
                reasons.append("Output dictionary value inequality")
        elif ref_out != dist_out:
            value_match = False
            schema_match = False
            reasons.append("Output text inequality")

        # 4. Generate Diff if unequal
        diff_str = ""
        if not value_match or not code_match or not error_invariant_match:
            ref_repr = (
                json.dumps(ref_out, indent=2, sort_keys=True)
                if ref_is_json
                else str(ref_out or "")
            )
            dist_repr = (
                json.dumps(dist_out, indent=2, sort_keys=True)
                if dist_is_json
                else str(dist_out or "")
            )
            ref_lines = ref_repr.splitlines()
            dist_lines = dist_repr.splitlines()
            diff_lines = list(
                difflib.unified_diff(
                    ref_lines, dist_lines, fromfile="reference_vibe", tofile="normalized_dist", lineterm=""
                )
            )
            diff_str = "\n".join(diff_lines)

        passed = code_match and error_invariant_match and schema_match and value_match

        return {
            "passed": passed,
            "reasons": reasons,
            "schema_match": schema_match,
            "value_match": value_match,
            "code_match": code_match,
            "error_invariant_match": error_invariant_match,
            "diff": diff_str,
        }

    def _check_json_schema_equivalence(self, a: Any, b: Any) -> Tuple[bool, str]:
        """Recursively verify structural schema equivalence between two JSON-compatible objects."""
        if type(a) != type(b):
            return False, f"Type mismatch: expected {type(a).__name__}, got {type(b).__name__}"

        if isinstance(a, dict):
            a_keys = set(a.keys())
            b_keys = set(b.keys())
            if a_keys != b_keys:
                missing = a_keys - b_keys
                extra = b_keys - a_keys
                return False, f"Key mismatch (missing: {missing}, unexpected: {extra})"
            for k in a_keys:
                ok, err = self._check_json_schema_equivalence(a[k], b[k])
                if not ok:
                    return False, f"At key '{k}': {err}"

        elif isinstance(a, list):
            if len(a) > 0 and len(b) > 0:
                # Check sample element type
                ok, err = self._check_json_schema_equivalence(a[0], b[0])
                if not ok:
                    return False, f"List element drift: {err}"

        return True, ""

    def _generate_test_log(
        self,
        ref_dir: str,
        dist_dir: str,
        results: List[Dict[str, Any]],
        passed: int,
        failed: int,
        rate: float,
    ) -> str:
        """Generate markdown test log report."""
        lines = [
            "# A/B Deterministic Equivalence Test Report",
            "",
            f"- **Execution Timestamp**: `{get_iso_now()}`",
            f"- **Reference Vibe Directory**: `{ref_dir}`",
            f"- **Normalized Dist Directory**: `{dist_dir}`",
            f"- **Equivalence Rate**: **{rate:.1f}%**",
            f"- **Total Scenarios**: `{len(results)}` | **Passed**: `{passed}` | **Failed/Drift**: `{failed}`",
            "",
            "## 1. Comparative Matrix",
            "",
            "| # | Scenario | Status | Ref Code | Dist Code | Ref Latency | Dist Latency | Speedup | Memory Ref/Dist |",
            "|---|---|---|---|---|---|---|---|---|",
        ]

        for r in results:
            idx = r["index"]
            name = r["name"]
            status_badge = "✅ PASS" if r["passed"] else "❌ DRIFT"
            ref_c = r["ref_run"]["status_code"]
            dist_c = r["dist_run"]["status_code"]
            ref_lat = f"{r['ref_run']['duration_ms']}ms"
            dist_lat = f"{r['dist_run']['duration_ms']}ms"
            speedup = f"{r['speedup_ratio']}x"
            ref_mem = f"{r['ref_run']['peak_memory_bytes']} B"
            dist_mem = f"{r['dist_run']['peak_memory_bytes']} B"
            lines.append(
                f"| {idx} | {name} | {status_badge} | `{ref_c}` | `{dist_c}` | {ref_lat} | {dist_lat} | {speedup} | {ref_mem} / {dist_mem} |"
            )

        lines.extend(["", "## 2. Detailed Scenario Analysis", ""])

        for r in results:
            lines.append(f"### Scenario {r['index']}: {r['name']}")
            lines.append(f"- **Verdict**: {'PASS' if r['passed'] else 'DRIFT DETECTED'}")
            lines.append(f"- **Schema Match**: {r['schema_match']} | **Value Match**: {r['value_match']}")
            lines.append(f"- **Code Match**: {r['code_match']} | **Error Invariant**: {r['error_invariant_match']}")
            if r["failure_reasons"]:
                lines.append("- **Discrepancies**:")
                for reason in r["failure_reasons"]:
                    lines.append(f"  - ⚠️ {reason}")

            if r.get("output_diff"):
                lines.append("")
                lines.append("```diff")
                lines.append(r["output_diff"])
                lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def _generate_spec_correction(self, results: List[Dict[str, Any]]) -> str:
        """Generate structured SDD-SPEC feedback for discovered drift or missing invariants."""
        drifted = [r for r in results if not r["passed"]]
        lines = [
            "# SDD-SPEC Drift Feedback & Hardening Directives",
            "",
            "> [!IMPORTANT]",
            f"> Post-SDD A/B Testing detected functional drift across {len(drifted)} scenario(s).",
            "> The following corrective specifications must be ingested into `01_spec.md`.",
            "",
            "## 1. Discovered Drift Inventory",
            "",
        ]

        for d in drifted:
            s_name = d["name"]
            lines.append(f"### Drift in: `{s_name}`")
            lines.append(f"- **Input Tested**: `{json.dumps(d['input'])}`")
            lines.append(f"- **Ref Outcome**: Code `{d['ref_run']['status_code']}`, Output: `{d['ref_run']['output']}`")
            lines.append(f"- **Dist Outcome**: Code `{d['dist_run']['status_code']}`, Output: `{d['dist_run']['output']}`")
            lines.append("- **Identified Causes**:")
            for reason in d["failure_reasons"]:
                lines.append(f"  - {reason}")

            if d.get("output_diff"):
                lines.append("```diff")
                lines.append(d["output_diff"])
                lines.append("```")
            lines.append("")

        lines.extend([
            "## 2. Proposed Hardening Requirements (Candidate Norms)",
            "",
        ])

        for idx, d in enumerate(drifted, start=1):
            req_id = f"REQ-DRIFT-{idx:03d}"
            title = f"Hardening invariant for {d['name']}"
            lines.extend([
                f"### {req_id}: {title}",
                "- **Domain**: `RELIABILITY`",
                "- **Rationale**: Reference prototype exhibited specific edge-case invariant that was altered or dropped during normalization.",
                "- **Acceptance Criteria**:",
                f"  - Given input `{json.dumps(d['input'])}`, when executed,",
                f"  - Then output status must be `{d['ref_run']['status_code']}` and schema must preserve expected payload.",
                "",
            ])

        return "\n".join(lines)
