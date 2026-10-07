"""Comprehensive Verification Suite for B2B-Harness Security & Sandbox Engine.
Strict Standard Library Python 3.8+, Zero External Dependencies.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add corporate_speckit directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from corporate_speckit.b2b_harness.sandbox import SecretScrubber, IsolatedSandboxRunner
from corporate_speckit.b2b_harness.security_sast import (
    AstSastScanner,
    SbomGenerator,
    ModuleSealer,
)


def test_secret_scrubber():
    print("[1/5] Testing SecretScrubber...")
    scrubber = SecretScrubber()

    # Sample text with multiple secret patterns
    sample = (
        '# Secret configuration test\n'
        'openai_key = "sk-1234567890abcdef1234567890"\n'
        'anthropic_key = "sk-ant-api03-abcdef12345678901234567890"\n'
        'hf_token = "hf_0123456789abcdefghij"\n'
        'aws_key = "AKIAIOSFODNN7EXAMPLE"\n'
        'aws_secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n'
        'gh_pat = "ghp_123456789012345678901234567890123456"\n'
        'priv_key = "-----BEGIN RSA PRIVATE KEY-----\\nMIIEowIBAAKCAQEA0...\\n-----END RSA PRIVATE KEY-----"\n'
        'db_url = "postgres://admin:supersecret@db.internal:5432/production"\n'
        'password = "my_super_secret_password"\n'
    )

    findings = scrubber.scan_text(sample)
    assert len(findings) >= 8, f"Expected at least 8 secrets, got {len(findings)}"
    types_detected = {f["type"] for f in findings}
    print(f"  Detected types: {types_detected}")
    assert "OPENAI_TOKEN" in types_detected or "ANTHROPIC_TOKEN" in types_detected
    assert "AWS_ACCESS_KEY" in types_detected
    assert "AWS_SECRET_KEY" in types_detected
    assert "GITHUB_PAT" in types_detected or "GITHUB_TOKEN" in types_detected
    assert "PRIVATE_KEY" in types_detected
    assert "DATABASE_URI" in types_detected
    assert "PASSWORD" in types_detected

    # Test scrubbing
    scrubbed = scrubber.scrub_text(sample)
    assert "sk-1234567890abcdef1234567890" not in scrubbed
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
    assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in scrubbed
    assert "ghp_123456789012345678901234567890123456" not in scrubbed
    assert "supersecret" not in scrubbed
    assert "my_super_secret_password" not in scrubbed
    assert "***REDACTED_SECRET[" in scrubbed

    # Test directory scrub
    temp_dir = tempfile.mkdtemp(prefix="speckit_scrub_test_")
    try:
        t_file = Path(temp_dir) / "config.py"
        t_file.write_text('api_token = "sk-0123456789abcdef0123456789"\n', encoding="utf-8")
        clean_file = Path(temp_dir) / "clean.py"
        clean_file.write_text('x = 42\n', encoding="utf-8")

        count, dir_findings = scrubber.scan_and_scrub_directory(temp_dir)
        assert count == 1, f"Expected 1 scrubbed file, got {count}"
        assert len(dir_findings) == 1
        assert "sk-0123456789abcdef0123456789" not in t_file.read_text(encoding="utf-8")
        assert "***REDACTED_SECRET[" in t_file.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("  [PASS] SecretScrubber passed successfully.")


def test_isolated_sandbox_runner():
    print("[2/5] Testing IsolatedSandboxRunner...")
    runner = IsolatedSandboxRunner(default_timeout=10)

    # Test 1: Simple script execution
    res = runner.execute_python("print('HELLO_SANDBOX')")
    assert res["exit_code"] == 0
    assert "HELLO_SANDBOX" in res["stdout"]
    assert not res["timed_out"]

    # Test 2: Timeout enforcement
    timeout_script = "import time\ntime.sleep(5)\nprint('DONE')"
    res_timeout = runner.execute_python(timeout_script, timeout=1)
    assert res_timeout["timed_out"] is True
    assert res_timeout["exit_code"] == -1

    # Test 3: Environment stripping & network isolation
    env_script = """
import os
import sys

# Check that sensitive keys are absent
sensitive_keys = [k for k in os.environ if any(w in k.upper() for w in ['KEY', 'SECRET', 'TOKEN', 'PASSWORD'])]
if sensitive_keys:
    print(f"LEAKED: {sensitive_keys}", file=sys.stderr)
    sys.exit(2)

# Check network isolation barrier
try:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print("FAILED: Socket creation did not raise", file=sys.stderr)
    sys.exit(3)
except PermissionError:
    print("NETWORK_BLOCKED_SUCCESS")
"""
    res_env = runner.execute_python(env_script, allow_network=False)
    assert res_env["exit_code"] == 0, f"Failed with: {res_env['stderr']}"
    assert "NETWORK_BLOCKED_SUCCESS" in res_env["stdout"]

    # Test 4: Output truncation
    runner_small = IsolatedSandboxRunner(max_output_bytes=50)
    res_trunc = runner_small.execute_python("print('X' * 500)")
    assert len(res_trunc["stdout"]) < 500
    assert "OUTPUT TRUNCATED" in res_trunc["stdout"]

    # Test 5: Command-line args passing
    res_args = runner.execute_python(
        "import sys\nprint('ARGS:' + ','.join(sys.argv[1:]))",
        args=["alpha", "beta", "gamma"],
    )
    assert res_args["exit_code"] == 0
    assert "ARGS:alpha,beta,gamma" in res_args["stdout"]

    # Test 6: Working directory isolation with custom cwd
    temp_custom_cwd = tempfile.mkdtemp(prefix="speckit_custom_cwd_")
    try:
        res_cwd = runner.execute_python(
            "import os\nwith open('file.txt', 'w') as f: f.write('sandbox_ok')",
            cwd=temp_custom_cwd,
        )
        assert res_cwd["exit_code"] == 0
        assert (Path(temp_custom_cwd) / "file.txt").read_text() == "sandbox_ok"
    finally:
        shutil.rmtree(temp_custom_cwd, ignore_errors=True)

    # Test 7: Pytest simulation execution
    test_script = """
def test_ok():
    assert 1 + 1 == 2

def test_string():
    assert "abc".upper() == "ABC"

def test_failure():
    assert 2 + 2 == 5, "Math failed"

class TestClass:
    def test_method(self):
        assert True
"""
    sim_res = runner.execute_pytest_simulation(test_script, target_module_dir=str(BASE_DIR))
    assert sim_res["total"] == 4, f"Expected 4 tests, got {sim_res['total']}"
    assert sim_res["passed"] == 3, f"Expected 3 passed, got {sim_res['passed']}"
    assert sim_res["failed"] == 1, f"Expected 1 failed, got {sim_res['failed']}"
    assert sim_res["exit_code"] == 1
    assert not sim_res["success"]

    print("  [PASS] IsolatedSandboxRunner passed successfully.")


def test_ast_sast_scanner():
    print("[3/5] Testing AstSastScanner...")
    scanner = AstSastScanner()

    # SEC-001: SQL Injection
    code_sql = """
cursor.execute(f"SELECT * FROM users WHERE name = '{name}'")
db.raw("SELECT * FROM orders WHERE id = " + order_id)
cursor.execute("SELECT * FROM logs WHERE tag = %s" % tag)
cursor.execute("SELECT * FROM items WHERE id = {}".format(item_id))
cursor.execute("SELECT * FROM users WHERE id = ?", (safe_id,))
"""
    findings_sql = scanner.scan_code(code_sql)
    sec_001 = [f for f in findings_sql if f["rule_id"] == "SEC-001"]
    assert len(sec_001) == 4, f"Expected 4 SQLi findings, got {len(sec_001)}"

    # SEC-002: Command Injection
    code_cmd = """
import os
import subprocess

os.system("ls " + path)
os.popen("cat " + file)
subprocess.run("rm -rf " + folder, shell=True)
subprocess.Popen(["ls", "-la"], shell=False)
"""
    findings_cmd = scanner.scan_code(code_cmd)
    sec_002 = [f for f in findings_cmd if f["rule_id"] == "SEC-002"]
    assert len(sec_002) == 3, f"Expected 3 Command Injection findings, got {len(sec_002)}"

    # SEC-003: Insecure Deserialization
    code_deser = """
import pickle
import yaml

data = pickle.loads(raw_input)
conf = yaml.load(user_stream)
safe_conf = yaml.load(user_stream, Loader=yaml.SafeLoader)
"""
    findings_deser = scanner.scan_code(code_deser)
    sec_003 = [f for f in findings_deser if f["rule_id"] == "SEC-003"]
    assert len(sec_003) == 2, f"Expected 2 Deserialization findings, got {len(sec_003)}"

    # SEC-004: Unsafe Dynamic Code
    code_eval = """
eval("2 + 2")
exec("import os")
"""
    findings_eval = scanner.scan_code(code_eval)
    sec_004 = [f for f in findings_eval if f["rule_id"] == "SEC-004"]
    assert len(sec_004) == 2, f"Expected 2 eval/exec findings, got {len(sec_004)}"

    # SEC-005: Path Traversal
    code_path = """
open("data/" + user_filename)
open(f"/etc/{conf_name}")
open("safe_constant.txt")
"""
    findings_path = scanner.scan_code(code_path)
    sec_005 = [f for f in findings_path if f["rule_id"] == "SEC-005"]
    assert len(sec_005) == 2, f"Expected 2 Path Traversal findings, got {len(sec_005)}"

    # SEC-006: Weak Cryptography
    code_crypto = """
import hashlib

h1 = hashlib.md5(b"password")
h2 = hashlib.sha1(b"token")
h_safe = hashlib.md5(b"cache_key", usedforsecurity=False)
h_sha256 = hashlib.sha256(b"secure_hash")
"""
    findings_crypto = scanner.scan_code(code_crypto)
    sec_006 = [f for f in findings_crypto if f["rule_id"] == "SEC-006"]
    assert len(sec_006) == 2, f"Expected 2 Weak Crypto findings, got {len(sec_006)}"

    # Syntax error graceful handling
    bad_code = "def syntax_broken(:"
    findings_syntax = scanner.scan_code(bad_code)
    assert len(findings_syntax) == 1
    assert findings_syntax[0]["rule_id"] == "SYNTAX_ERROR"

    # Project scan test
    temp_proj = tempfile.mkdtemp(prefix="speckit_sast_proj_")
    try:
        p1 = Path(temp_proj) / "vuln.py"
        p1.write_text("import os\nos.system('whoami')\n", encoding="utf-8")
        p2 = Path(temp_proj) / "safe.py"
        p2.write_text("def add(a, b): return a + b\n", encoding="utf-8")

        summary = scanner.scan_project(temp_proj)
        assert summary["total_files_scanned"] == 2
        assert summary["total_findings"] == 1
        assert summary["security_score"] < 100
        assert summary["severity_counts"]["CRITICAL"] == 1
    finally:
        shutil.rmtree(temp_proj, ignore_errors=True)

    print("  [PASS] AstSastScanner passed successfully.")


def test_sbom_generator():
    print("[4/5] Testing SbomGenerator...")
    gen = SbomGenerator()

    temp_proj = tempfile.mkdtemp(prefix="speckit_sbom_")
    try:
        # Create requirements.txt
        (Path(temp_proj) / "requirements.txt").write_text(
            "fastapi==0.100.0\npydantic>=2.0.0\nuvicorn~=0.22.0\n",
            encoding="utf-8",
        )
        # Create python file with third-party imports
        (Path(temp_proj) / "main.py").write_text(
            "import fastapi\nimport httpx\nfrom pydantic import BaseModel\nimport sys\n",
            encoding="utf-8",
        )

        sbom = gen.generate_sbom(temp_proj, module_name="corporate_speckit", version="2.0.0")

        assert sbom["bomFormat"] == "CycloneDX"
        assert sbom["specVersion"] == "1.5"
        assert sbom["metadata"]["component"]["name"] == "corporate_speckit"
        assert sbom["metadata"]["component"]["version"] == "2.0.0"

        comp_names = {c["name"] for c in sbom["components"]}
        print(f"  SBOM Components: {comp_names}")
        assert "fastapi" in comp_names
        assert "pydantic" in comp_names
        assert "uvicorn" in comp_names
        assert "httpx" in comp_names  # AST discovered import
        assert "sys" not in comp_names  # stdlib excluded
    finally:
        shutil.rmtree(temp_proj, ignore_errors=True)

    print("  [PASS] SbomGenerator passed successfully.")


def test_module_sealer():
    print("[5/5] Testing ModuleSealer...")
    sealer = ModuleSealer()

    temp_dist = tempfile.mkdtemp(prefix="speckit_sealer_")
    try:
        (Path(temp_dist) / "app.py").write_text("print('HELLO')", encoding="utf-8")
        (Path(temp_dist) / "config.json").write_text('{"version": 1}', encoding="utf-8")
        sub_dir = Path(temp_dist) / "sub"
        sub_dir.mkdir()
        (sub_dir / "helper.py").write_text("def help(): pass", encoding="utf-8")

        # Create seal
        seal = sealer.create_seal(temp_dist)
        assert seal["algorithm"] == "sha256"
        assert seal["file_count"] == 3
        assert len(seal["root_hash"]) == 64
        assert "app.py" in seal["manifest"]
        assert "sub/helper.py" in seal["manifest"]
        assert (Path(temp_dist) / "seal.json").is_file()

        # Verify intact seal
        is_valid, errors = sealer.verify_seal(temp_dist)
        assert is_valid is True, f"Expected seal to be valid, got errors: {errors}"

        # Tamper with file
        (Path(temp_dist) / "app.py").write_text("print('TAMPERED')", encoding="utf-8")
        is_valid_tampered, errors_tampered = sealer.verify_seal(temp_dist)
        assert is_valid_tampered is False
        assert any("Checksum mismatch" in e for e in errors_tampered)

        # Delete file
        (Path(temp_dist) / "app.py").unlink()
        is_valid_del, errors_del = sealer.verify_seal(temp_dist)
        assert is_valid_del is False
        assert any("Missing file" in e for e in errors_del)
    finally:
        shutil.rmtree(temp_dist, ignore_errors=True)

    print("  [PASS] ModuleSealer passed successfully.")


if __name__ == "__main__":
    print("=" * 60)
    print("Starting B2B-Harness Verification Suite")
    print("=" * 60)
    test_secret_scrubber()
    test_isolated_sandbox_runner()
    test_ast_sast_scanner()
    test_sbom_generator()
    test_module_sealer()
    print("=" * 60)
    print("ALL TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 60)
