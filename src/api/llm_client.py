import httpx
import os
import json
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator

logger = logging.getLogger("b2bharness.llm")

# Canonical EuroModels Catalog & Role Mappings for B2B SDD Swarm
EUROMODELS_CATALOG = {
    "claude-sonnet-5": "Основной кодинг и архитектура",
    "claude-3.7-sonnet": "Сложные алгоритмы, математика и логика",
    "gemini-3.7-flash": "Мгновенный ресерч, логи, документация",
    "gemini-2.0-flash": "Быстрый чат и универсальные задачи",
    "qwen-3.8-max": "Бэкенд, SQL, базы данных, JSON, парсеры",
    "kimi-k3": "Глубокое код-ревью и аудит безопасности",
    "kimi-k2.6": "Быстрый анализ длинных текстов",
    "gpt-6-astra": "Системное проектирование",
    "claude-opus-5.5": "Тяжелые точечные задачи"
}

ROLE_MODELS = {
    "architect": "gpt-6-astra",
    "coder": "claude-sonnet-5",
    "tester": "gemini-3.7-flash",
    "auditor": "kimi-k3",
    "reviewer": "kimi-k3",
    "backend": "qwen-3.8-max",
    "research": "gemini-3.7-flash",
    "default": "claude-sonnet-5"
}

FALLBACK_MODELS = [
    "claude-sonnet-5",
    "claude-3.7-sonnet",
    "gemini-3.7-flash",
    "gemini-2.0-flash",
    "qwen-3.8-max",
    "kimi-k3",
    "gpt-6-astra",
    "claude-opus-5.5"
]

class LLMClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        # 1. Resolve API Key
        key = api_key or os.getenv("CORP_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        if not key:
            try:
                if os.path.exists("data/keys.json"):
                    with open("data/keys.json", "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if data.get("key"):
                            key = data.get("key")
            except Exception:
                pass

        self.api_key = key.strip()
        
        # 2. Resolve Base URL
        default_url = os.getenv("LLM_BASE_URL", "https://chat.hamaryal.ru/v1")
        self.base_url = (base_url or default_url).rstrip("/")
        
        # 3. Offline/Mock detection for testing
        self.is_mock_key = (
            not self.api_key
            or self.api_key in ("YOUR_API_KEY_HERE", "test-key", "dummy", "mock")
            or self.api_key.startswith("test_")
        )

    def is_configured(self) -> bool:
        return bool(self.api_key) and not self.is_mock_key

    def _get_mock_response(self, role: str, messages: List[Dict[str, str]]) -> str:
        prompt_preview = " ".join([m.get("content", "") for m in messages if m.get("role") == "user"])
        if "Reverse-Engineering SDD Architect" in prompt_preview:
            return (
                "# DISCOVERY & REVERSE-ENGINEERING\n"
                "## 1. Observed Behaviors & Invariants\n"
                "- Core algorithmic logic analyzed.\n\n"
                "## 2. Technical Debt & Anti-Patterns\n"
                "- Hardcoded dependencies and missing type assertions.\n\n"
                "## 3. Extracted Test Scenarios\n"
                "- Happy path assertion and invalid argument handling.\n\n"
                "## 4. Suggested B2B Harness Architecture\n"
                "- Clean decoupled module with zero external dependencies.\n"
            )
        elif "Intent Normalizer" in prompt_preview or "Refine this intent" in prompt_preview:
            return (
                "# CANONICAL INTENT SPECIFICATION\n"
                "## 1. Goals\n"
                "- Implement production-grade functionality satisfying requirements.\n\n"
                "## 2. Non-Goals\n"
                "- Out-of-scope external dependencies.\n\n"
                "## 3. Constraints\n"
                "- Zero unexpected dependencies, OWASP ASVS L2 compliance.\n\n"
                "## 4. Acceptance Criteria\n"
                "- All test assertions pass in isolated sandbox.\n"
            )
        elif "Spec Architect" in prompt_preview:
            return (
                "# TECHNICAL SPECIFICATION\n"
                "## 1. Architecture & Signatures\n"
                "Class: Calculator\nMethods: add(a, b), subtract(a, b)\n\n"
                "## 2. Security Controls [REQ-SEC-01]\n"
                "- Type check operands against CWE-20.\n"
            )
        elif "Implementation Planner" in prompt_preview:
            return (
                "# IMPLEMENTATION PLAN\n"
                "1. [REQ-SEC-01] Initialize module structure.\n"
                "2. [REQ-FUNC-01] Implement pure arithmetic functions.\n"
            )
        elif role == "tester" or "TDD Synthesizer" in prompt_preview:
            return (
                "```python\n"
                "import unittest\n\n"
                "class TestModule(unittest.TestCase):\n"
                "    def test_basic(self):\n"
                "        self.assertTrue(True)\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
                "```"
            )
        elif role == "auditor":
            return '{"verdict": "APPROVED", "score": 95, "issues": [], "recommendations": "Code meets standards."}'
        else:
            return f"Mock response for [{role}]: Processed {len(messages)} messages successfully."

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        role: str = "default",
        model: Optional[str] = None,
        temperature: float = 0.2
    ) -> Dict[str, Any]:
        target_model = model or ROLE_MODELS.get(role, ROLE_MODELS["default"])
        
        # Return mock in offline / unit-test mode
        if self.is_mock_key:
            content = self._get_mock_response(role, messages)
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": content
                    }
                }],
                "model": f"{target_model} (mock)"
            }

        candidate_models = [target_model] + [m for m in FALLBACK_MODELS if m != target_model]
        last_exception = None

        for m_name in candidate_models:
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": m_name,
                            "messages": messages,
                            "temperature": temperature
                        }
                    )
                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 401:
                        # 401 is bad API key
                        response.raise_for_status()
                    else:
                        logger.warning(f"Model {m_name} returned status {response.status_code}: {response.text}")
                        last_exception = Exception(f"HTTP {response.status_code} ({m_name}): {response.text}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise
                logger.warning(f"Model {m_name} failed with status {e.response.status_code}, trying fallback...")
                last_exception = e
            except Exception as e:
                logger.warning(f"Error calling model {m_name}: {str(e)}, trying fallback...")
                last_exception = e

        if last_exception:
            raise last_exception
        raise RuntimeError("All candidate models failed to return a valid completion.")

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        role: str = "default",
        model: Optional[str] = None,
        temperature: float = 0.2
    ) -> AsyncGenerator[str, None]:
        target_model = model or ROLE_MODELS.get(role, ROLE_MODELS["default"])
        
        if self.is_mock_key:
            content = self._get_mock_response(role, messages)
            for chunk in content.split(" "):
                yield chunk + " "
            return

        async with httpx.AsyncClient(timeout=90.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": target_model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True
                }
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            parsed = json.loads(data_str)
                            delta = parsed.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            pass
