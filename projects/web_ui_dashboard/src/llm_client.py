import httpx
import os

class LLMClient:
    def __init__(self):
        # Используем переменную окружения или значение по умолчанию
        self.api_key = os.getenv("LLM_API_KEY", "ваш-ключ-здесь")
        self.base_url = "https://llm.franciscodanconia.ru/v1"

    async def chat_completion(self, messages: list):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": "gpt-4o", # Можно менять
                    "messages": messages
                },
                timeout=60.0
            )
            response.raise_for_status()
            return response.json()
