"""Spec-Kit AI Assistant Bridge.
Zero external dependencies; uses Python standard library urllib.request.
Works with any OpenAI-compatible API (Ollama, vLLM, corporate proxy, OpenAI, Claude, Gemini).
Includes intelligent rule-based fallback for 100% offline / air-gapped environments.
"""
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional


class AIBridge:
    def __init__(self, db):
        self.db = db

    def get_config(self) -> Dict[str, str]:
        return {
            "endpoint": self.db.get_setting("ai_endpoint", "http://localhost:11434/v1"),
            "api_key": self.db.get_setting("ai_api_key", ""),
            "model": self.db.get_setting("ai_model", "llama3")
        }

    def _call_llm(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        cfg = self.get_config()
        endpoint = cfg["endpoint"].rstrip("/") + "/chat/completions"
        api_key = cfg["api_key"]
        model = cfg["model"]

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt or "You are a senior Spec-Kit Software Architect and Specification Engineer."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "CorporateSpecKit/1.0"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                if resp.status == 200:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    return res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception:
            return None
        return None

    def suggest_clarifications(self, req_title: str, req_desc: str, req_rationale: str) -> List[Dict[str, str]]:
        """Identify potential ambiguities and propose clarification questions."""
        prompt = (
            f"Analyze the following requirement from a Spec-Driven Development perspective. "
            f"Identify 3 subtle edge cases or ambiguities that must be clarified before writing code.\n\n"
            f"Requirement: {req_title}\nDescription: {req_desc}\nRationale: {req_rationale}\n\n"
            f"Return a clean JSON array with 3 objects: [{{\"question\": \"...\", \"rationale\": \"...\"}}]. Return ONLY JSON."
        )
        llm_resp = self._call_llm(prompt)
        if llm_resp:
            try:
                # Strip markdown codeblocks if present
                clean = llm_resp.strip()
                if clean.startswith("```"):
                    clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                parsed = json.loads(clean)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass

        # Air-gapped intelligent rule-based suggestions fallback
        return [
            {
                "question": f"What is the expected failure mode and timeout threshold when {req_title} encounters downstream unavailability?",
                "rationale": "Spec-Kit requires non-blocking resilient failure modes and circuit breaker definitions."
            },
            {
                "question": f"Are there specific corporate security / audit log retention requirements for operations governed by {req_title}?",
                "rationale": "Compliance guardrail verification for ISO-27001."
            },
            {
                "question": f"What are the rate-limiting and maximum concurrency thresholds for {req_title} under peak load?",
                "rationale": "Non-functional capacity and resource isolation specification."
            }
        ]

    def decompose_tasks(self, req_id: str, req_title: str, req_desc: str) -> List[Dict[str, str]]:
        """Decompose a requirement into atomic engineering tasks with test cases."""
        prompt = (
            f"Decompose requirement [{req_id}] '{req_title}' into 2-3 atomic engineering implementation tasks.\n"
            f"Description: {req_desc}\n\n"
            f"Return a clean JSON array: [{{\"title\": \"...\", \"description\": \"...\", \"test_case_id\": \"TEST-...\", \"code_targets\": \"...\"}}]. Return ONLY JSON."
        )
        llm_resp = self._call_llm(prompt)
        if llm_resp:
            try:
                clean = llm_resp.strip()
                if clean.startswith("```"):
                    clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                parsed = json.loads(clean)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass

        # Air-gapped fallback tasks
        short_id = req_id.replace("REQ-", "")
        return [
            {
                "title": f"Implement core domain logic and data contracts for {req_title}",
                "description": f"Draft schemas and core logic satisfying {req_id} invariants.",
                "test_case_id": f"TEST-{short_id}-UNIT-01",
                "code_targets": f"internal/core/{short_id.lower()}.py"
            },
            {
                "title": f"Add integration test suite and error handling boundary for {req_title}",
                "description": f"Verify negative scenarios and circuit breaking for {req_id}.",
                "test_case_id": f"TEST-{short_id}-INT-02",
                "code_targets": f"tests/test_{short_id.lower()}.py"
            }
        ]
