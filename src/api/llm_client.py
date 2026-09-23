import httpx
import os
import json

class LLMClient:
    def __init__(self):
        key = "YOUR_API_KEY_HERE"
        try:
            if os.path.exists("data/keys.json"):
                with open("data/keys.json", "r") as f:
                    data = json.load(f)
                    if data.get("key"):
                        key = data.get("key")
        except Exception:
            pass
            
        self.api_key = key.strip()
        self.base_url = "https://llm.franciscodanconia.ru/v1"

    async def chat_completion(self, messages: list):
        if self.api_key == "YOUR_API_KEY_HERE" or not self.api_key:
            # Return mock response for testing/offline mode if API key is not configured
            return {
                "choices": [{
                    "message": {
                        "content": "Refined Intent: " + " ".join([m.get("content", "") for m in messages])
                    }
                }]
            }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "em-gpt-4o",
                    "messages": messages
                },
                timeout=60.0
            )
            response.raise_for_status()
            return response.json()
