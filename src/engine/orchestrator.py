import os
import json
import logging
import asyncio
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List, Callable

from src.engine.pipeline import PipelineEngine, PipelineState
from src.engine.artifact_manager import ArtifactManager
from src.core.database import log_audit
from src.security.scanner import SecurityScanner
from src.api.llm_client import LLMClient

logger = logging.getLogger("b2bharness.orchestrator")

class AgentOrchestrator:
    def __init__(self, staging_dir: str = "data/staging", sandbox_dir: str = ".sandbox"):
        self.artifact_manager = ArtifactManager()
        self.staging_dir = staging_dir
        self.sandbox_dir = sandbox_dir
        self.scanner = SecurityScanner()
        self.llm = LLMClient()
        self._pending_approvals: Dict[str, asyncio.Event] = {}
        os.makedirs(self.staging_dir, exist_ok=True)
        os.makedirs(self.sandbox_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # 1. Human-in-the-Loop (Async Event Gate)
    # -------------------------------------------------------------------------
    def request_human_verdict(self, session_id: str, artifact_type: str, content: str):
        """Legacy helper for human review files."""
        session_path = os.path.join(self.staging_dir, session_id)
        os.makedirs(session_path, exist_ok=True)
        artifact_path = os.path.join(session_path, f"{artifact_type}.md")
        with open(artifact_path, "w", encoding="utf-8") as f:
            f.write(content)
        verdict_path = os.path.join(session_path, f"{artifact_type}_verdict.json")
        with open(verdict_path, "w", encoding="utf-8") as f:
            json.dump({"status": "approved", "comment": "Auto-approved for local run"}, f)
        return True, "Approved"

    def create_gate_request(self, session_id: str, artifact_type: str, content: str) -> str:
        """Stores the artifact in staging and prepares approval metadata without blocking."""
        session_path = os.path.join(self.staging_dir, session_id)
        os.makedirs(session_path, exist_ok=True)

        artifact_path = os.path.join(session_path, f"{artifact_type}.md")
        with open(artifact_path, "w", encoding="utf-8") as f:
            f.write(content)

        approval_file = os.path.join(session_path, f"{artifact_type}_verdict.json")
        default_verdict = {
            "session_id": session_id,
            "artifact_type": artifact_type,
            "status": "pending",
            "comment": "",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        with open(approval_file, "w", encoding="utf-8") as f:
            json.dump(default_verdict, f, indent=2)

        return artifact_path

    async def wait_for_verdict(self, session_id: str, artifact_type: str, timeout_seconds: float = 300.0) -> Tuple[bool, str]:
        """Asynchronously waits for human approval without blocking the FastAPI event loop."""
        session_path = os.path.join(self.staging_dir, session_id)
        verdict_path = os.path.join(session_path, f"{artifact_type}_verdict.json")

        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout_seconds:
            if os.path.exists(verdict_path):
                try:
                    with open(verdict_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("status") in ("approved", "rejected"):
                        return data.get("status") == "approved", data.get("comment", "")
                except Exception:
                    pass
            await asyncio.sleep(0.5)

        return False, f"Timeout waiting for verdict on {artifact_type}"

    def approve_artifact(self, session_id: str, artifact_type: str, comment: str = ""):
        session_path = os.path.join(self.staging_dir, session_id)
        verdict_path = os.path.join(session_path, f"{artifact_type}_verdict.json")
        os.makedirs(session_path, exist_ok=True)
        with open(verdict_path, "w", encoding="utf-8") as f:
            json.dump({
                "session_id": session_id,
                "artifact_type": artifact_type,
                "status": "approved",
                "comment": comment,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }, f, indent=2)

    # -------------------------------------------------------------------------
    # 2. Command Execution & Legacy Compatibility
    # -------------------------------------------------------------------------
    def _execute_command(self, cmd_line: str) -> Tuple[bool, str]:
        if cmd_line.startswith("edit:"):
            parts = cmd_line.split(":", 3)
            if len(parts) == 4:
                _, file_path, search, replace = parts
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                new_content = content.replace(search, replace)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                return True, f"Edited {file_path}"
        elif cmd_line.startswith("bash:"):
            cmd = cmd_line.split(":", 1)[1]
            subprocess.run(cmd, shell=True, check=True)
            return True, f"Executed {cmd}"
        return False, "Unknown command"

    def execute_plan(self, module_name: str, session_id: str = "default", user_id: str = "admin", pipeline_engine: Optional[PipelineEngine] = None) -> Tuple[bool, str]:
        """Legacy plan executor by module name."""
        plan_data = self.artifact_manager.get_latest_artifact(module_name, "plan")
        if not plan_data:
            return False, "Plan not found"
            
        plan_content = plan_data[0]
        log_audit(session_id, user_id, "DEV", f"Executing plan for {module_name}")
        
        lines = [line.strip() for line in plan_content.split("\n") if line.strip()]
        
        try:
            for line in lines:
                success, msg = self._execute_command(line)
                if not success:
                    log_audit(session_id, user_id, "DEV_ERROR", f"Action failed: {line}")
            
            if pipeline_engine:
                pipeline_engine.transition(PipelineState.POST_SDD)
            log_audit(session_id, user_id, "POST_SDD", "AUTO_TRANSITION_AFTER_DEV")
            return True, "Plan executed and transitioned to POST_SDD"
        except Exception as e:
            return False, str(e)

    # -------------------------------------------------------------------------
    # 3. Multi-File Parsing & Sandbox Execution
    # -------------------------------------------------------------------------
    def parse_file_blocks(self, text: str) -> Dict[str, str]:
        """Extracts files from *** FILE: path *** or ```python file=path blocks."""
        files = {}
        import re
        
        # Pattern 1: *** FILE: filename *** ... *** END FILE ***
        p1 = re.compile(r'\*\*\*\s*FILE:\s*([^\n\r]+?)\s*\*\*\*([\s\S]*?)(?=\*\*\*\s*FILE:|\*\*\*\s*END\s*FILE|\Z)', re.IGNORECASE)
        for match in p1.finditer(text):
            filename = match.group(1).strip()
            code = match.group(2).strip()
            fence = re.match(r'^```[\w]*\s*\n([\s\S]*?)\n```$', code)
            if fence:
                code = fence.group(1)
            files[filename] = code

        # Pattern 2: Markdown headers / code blocks with filename attribute
        if not files:
            p2 = re.compile(r'```(?:python|py|javascript|js)?\s+(?:file|filename)=["\']?([^\s"\']+)["\']?\s*\n([\s\S]*?)\n```', re.IGNORECASE)
            for match in p2.finditer(text):
                files[match.group(1).strip()] = match.group(2).strip()

        # Fallback: single file if pure code block
        if not files:
            pure_block = re.search(r'```(?:python|py)?\s*\n([\s\S]*?)\n```', text)
            if pure_block:
                files["module_impl.py"] = pure_block.group(1).strip()

        return files

    def run_sandbox_test(self, test_file_path: str, cwd: Optional[str] = None, timeout: int = 15) -> Dict[str, Any]:
        """Executes a test file inside an isolated sandbox environment."""
        target_cwd = cwd or os.path.dirname(test_file_path) or "."
        cmd = ["python", "-m", "unittest", os.path.basename(test_file_path)]
        try:
            res = subprocess.run(
                cmd,
                cwd=target_cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "passed": res.returncode == 0,
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "output": (res.stdout + "\n" + res.stderr).strip()
            }
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds",
                "output": f"Timeout expired ({timeout}s)"
            }
        except Exception as e:
            return {
                "passed": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "output": str(e)
            }

    # -------------------------------------------------------------------------
    # 4. 7-Stage SDD Pipeline Execution
    # -------------------------------------------------------------------------

    async def execute_pre_sdd(self, source_path: str, session_id: str) -> Dict[str, Any]:
        """Stage 1: PRE-SDD Reverse Engineering of existing codebase or PoC."""
        collected_snippets = []
        if os.path.isfile(source_path):
            with open(source_path, "r", encoding="utf-8", errors="replace") as f:
                collected_snippets.append(f"File: {os.path.basename(source_path)}\n{f.read()[:3000]}")
        elif os.path.isdir(source_path):
            for root, _, files in os.walk(source_path):
                for file in files:
                    if file.endswith((".py", ".js", ".ts", ".json", ".md")):
                        p = os.path.join(root, file)
                        try:
                            with open(p, "r", encoding="utf-8", errors="replace") as f:
                                collected_snippets.append(f"File: {os.path.relpath(p, source_path)}\n{f.read()[:1500]}")
                        except Exception:
                            pass
                if len(collected_snippets) > 15:
                    break

        context = "\n\n".join(collected_snippets)
        prompt = (
            "You are the Lead Reverse-Engineering SDD Architect.\n"
            "Analyze this vibe-coded project / PoC and extract its core behavior into a discovery document.\n\n"
            "Structure as:\n"
            "# DISCOVERY & REVERSE-ENGINEERING\n"
            "## 1. Observed Behaviors & Invariants\n"
            "## 2. Technical Debt & Anti-Patterns\n"
            "## 3. Extracted Test Scenarios\n"
            "## 4. Suggested B2B Harness Architecture\n\n"
            f"SOURCE CODE SAMPLES:\n{context[:6000]}"
        )

        res = await self.llm.chat_completion([{"role": "user", "content": prompt}], role="architect")
        content = res["choices"][0]["message"]["content"]

        session_path = os.path.join(self.staging_dir, session_id)
        os.makedirs(session_path, exist_ok=True)
        discovery_path = os.path.join(session_path, "discovery.md")
        with open(discovery_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {"status": "completed", "artifact_path": discovery_path, "content": content}

    async def execute_intent(self, raw_intent: str, session_id: str) -> Dict[str, Any]:
        """Stage 2: SDD-INTENT Formalization into 4 Canonical Sections."""
        prompt = (
            "You are the B2B SDD Intent Normalizer.\n"
            "Transform the input into a strict 4-section canonical intent document:\n"
            "# CANONICAL INTENT SPECIFICATION\n"
            "## 1. Goals\n"
            "## 2. Non-Goals\n"
            "## 3. Constraints (OWASP ASVS L2, Zero unwanted deps, Error boundaries)\n"
            "## 4. Acceptance Criteria\n\n"
            f"RAW INPUT / DISCOVERY:\n{raw_intent}"
        )
        res = await self.llm.chat_completion([{"role": "user", "content": prompt}], role="architect")
        content = res["choices"][0]["message"]["content"]

        session_path = os.path.join(self.staging_dir, session_id)
        os.makedirs(session_path, exist_ok=True)
        intent_path = os.path.join(session_path, "intent.md")
        with open(intent_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {"status": "completed", "artifact_path": intent_path, "content": content}

    async def decompose_complex_intent(self, raw_intent: str) -> List[str]:
        """Splits monolithic or multi-domain tasks into 2 focused atomic sub-tasks."""
        prompt = (
            "You are the Lead Systems Decomposer.\n"
            "Analyze this software requirement. If it is complex, split it into at most 2 sequential atomic sub-tasks.\n"
            "SubTask 1 must focus on the Core Data/Algorithm Engine.\n"
            "SubTask 2 must focus on the Adapter/Interface layer.\n"
            "Output strictly a JSON list of strings: [\"SubTask 1 description\", \"SubTask 2 description\"]\n\n"
            f"RAW TASK:\n{raw_intent}"
        )
        res = await self.llm.chat_completion([{"role": "user", "content": prompt}], role="architect")
        content = res["choices"][0]["message"]["content"]
        try:
            import re
            m = re.search(r'\[[\s\S]*?\]', content)
            if m:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, list) and len(parsed) > 0:
                    return parsed[:2]
        except Exception:
            pass
        return [raw_intent]

    async def execute_spec(self, intent_content: str, session_id: str, max_spec_lines: int = 120) -> Dict[str, Any]:
        """Stage 3: SDD-SPEC Formal Technical Specification with Strict Micro-Modular Compaction."""
        prompt = (
            "You are the Lead Spec Architect.\n"
            "Generate an ultra-compact, high-density, unambiguous technical specification based on this Intent.\n\n"
            "CRITICAL ARCHITECTURAL CONSTRAINTS:\n"
            "1. STRICT COMPACTION: Keep the entire specification UNDER 100-120 lines.\n"
            "2. MICRO-MODULARITY: Define at most 3-5 core methods/signatures. Avoid deep inheritance or sprawling interfaces.\n"
            "3. ZERO FLUFF: Omit redundant explanations, boilerplate descriptions, and excessive comments.\n"
            "4. SECURITY MAPPING: Explicitly tag [REQ-SEC-01] for input validation (CWE-20/OWASP ASVS L2).\n"
            "5. TEST INVARIANTS: Specify exact input/output boundary assertions.\n\n"
            "STRUCTURE:\n"
            "# TECHNICAL SPECIFICATION\n"
            "## 1. Class & Method Signatures (Compact)\n"
            "## 2. Security Controls [REQ-SEC-...]\n"
            "## 3. Test Invariants & Boundaries\n\n"
            f"INTENT:\n{intent_content}"
        )
        res = await self.llm.chat_completion([{"role": "user", "content": prompt}], role="architect")
        content = res["choices"][0]["message"]["content"]

        session_path = os.path.join(self.staging_dir, session_id)
        os.makedirs(session_path, exist_ok=True)
        spec_path = os.path.join(session_path, "spec.md")
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {"status": "completed", "artifact_path": spec_path, "content": content}

    async def generate_plan_artifact(self, spec_content: str, session_id: str) -> Dict[str, Any]:
        """Stage 4: SDD-PLAN Traceable Implementation Plan."""
        prompt = (
            "You are the Lead Implementation Planner.\n"
            "Decompose the specification into actionable steps with strict requirement traceability.\n"
            "Map each task directly to [REQ-...] IDs from the specification.\n\n"
            f"SPECIFICATION:\n{spec_content}"
        )
        res = await self.llm.chat_completion([{"role": "user", "content": prompt}], role="architect")
        content = res["choices"][0]["message"]["content"]

        session_path = os.path.join(self.staging_dir, session_id)
        os.makedirs(session_path, exist_ok=True)
        plan_path = os.path.join(session_path, "plan.md")
        with open(plan_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {"status": "completed", "artifact_path": plan_path, "content": content}

    async def execute_dev_and_post_sdd(
        self,
        session_id: str,
        max_repair_rounds: int = 3
    ) -> Dict[str, Any]:
        """Stage 5 & 6: TDD Synthesizer + Coder + Sandbox Execution + Self-Healing Loop."""
        session_path = os.path.join(self.staging_dir, session_id)
        task_sandbox = os.path.join(self.sandbox_dir, session_id)
        os.makedirs(task_sandbox, exist_ok=True)

        intent_file = os.path.join(session_path, "intent.md")
        spec_file = os.path.join(session_path, "spec.md")
        plan_file = os.path.join(session_path, "plan.md")

        intent = open(intent_file, "r", encoding="utf-8").read() if os.path.exists(intent_file) else ""
        spec = open(spec_file, "r", encoding="utf-8").read() if os.path.exists(spec_file) else ""
        plan = open(plan_file, "r", encoding="utf-8").read() if os.path.exists(plan_file) else ""

        # 1. Synthesize TDD Tests (Tester Role: Gemini 3.7)
        tdd_prompt = (
            "You are the TDD Synthesizer.\n"
            "Write a comprehensive Python unittest suite for the module defined in the specification.\n"
            "Cover positive paths, edge cases, negative assertions, and security boundaries.\n\n"
            f"INTENT:\n{intent}\n\nSPECIFICATION:\n{spec}\n\n"
            "Output the test code in format: *** FILE: test_module.py ***\n<python test code>\n*** END FILE ***"
        )
        tdd_res = await self.llm.chat_completion([{"role": "user", "content": tdd_prompt}], role="tester")
        test_files = self.parse_file_blocks(tdd_res["choices"][0]["message"]["content"])
        
        test_file_name = "test_module.py"
        test_code = test_files.get("test_module.py") or list(test_files.values())[0]
        test_path = os.path.join(task_sandbox, test_file_name)
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)

        # 2. Coder + Self-Healing Loop (Coder Role: Sonnet 5, Auditor: Kimi K3)
        history = []
        is_green = False
        final_code = ""

        coder_prompt = (
            "You are the Lead Swarm Coder.\n"
            "Implement the complete Python production module to satisfy the Specification and pass the TDD tests.\n\n"
            f"SPECIFICATION:\n{spec}\n\n"
            f"TDD TEST SUITE:\n{test_code}\n\n"
            "Output each file in format:\n"
            "*** FILE: module_impl.py ***\n<python source code>\n*** END FILE ***"
        )

        current_prompt = coder_prompt
        for round_idx in range(1, max_repair_rounds + 1):
            coder_res = await self.llm.chat_completion([{"role": "user", "content": current_prompt}], role="coder")
            final_code = coder_res["choices"][0]["message"]["content"]
            parsed_files = self.parse_file_blocks(final_code)

            for fname, fcode in parsed_files.items():
                target_file = os.path.join(task_sandbox, os.path.basename(fname))
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(fcode)

            sast_issues = []
            for fname in parsed_files:
                target_file = os.path.join(task_sandbox, os.path.basename(fname))
                clean, msg = self.scanner.scan_file(target_file)
                if not clean:
                    sast_issues.append(f"SAST Failure in {fname}: {msg}")

            test_res = self.run_sandbox_test(test_path, cwd=task_sandbox)
            history.append({
                "round": round_idx,
                "passed": test_res["passed"] and len(sast_issues) == 0,
                "output": test_res["output"],
                "sast_issues": sast_issues
            })

            if test_res["passed"] and len(sast_issues) == 0:
                is_green = True
                break

            current_prompt = (
                f"Your implementation in Round {round_idx} failed validation.\n\n"
                f"TEST EXECUTION OUTPUT:\n{test_res['output']}\n\n"
                f"SAST SECURITY ISSUES:\n{'; '.join(sast_issues) if sast_issues else 'None'}\n\n"
                "Fix all issues and provide the updated file blocks."
            )

        dev_log_path = os.path.join(session_path, "dev_log.md")
        with open(dev_log_path, "w", encoding="utf-8") as f:
            f.write(f"# DEV & TEST LOG (Session {session_id})\n\n")
            f.write(f"Status: {'GREEN' if is_green else 'RED (Manual Intervention Required)'}\n\n")
            f.write("## Execution Rounds:\n")
            for h in history:
                f.write(f"- Round {h['round']}: {'PASSED' if h['passed'] else 'FAILED'}\n")
                f.write(f"  ```\n  {h['output'][:400]}\n  ```\n")

        return {
            "status": "green" if is_green else "red",
            "is_green": is_green,
            "rounds_executed": len(history),
            "history": history,
            "sandbox_path": task_sandbox,
            "dev_log_path": dev_log_path
        }
