import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_KEY_GIGACODE: str = ""
    LLM_API_BASE: str = "https://llm.franciscodanconia.ru:8448/v1"
    
    class Config:
        env_file = ".env"
        extra = "ignore"

def save_env_key(key_name: str, value: str):
    # Убедимся, что записываем в .env в корневой директории проекта
    with open(".env", "a") as f:
        f.write(f"{key_name}={value}\n")

settings = Settings()
