import os
import json
from typing import Optional, Set
from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
BEARER_AUTH = HTTPBearer(auto_error=False)

def get_allowed_keys() -> Set[str]:
    """Retrieves all authorized team keys from environment and config files."""
    keys = set()
    
    # 1. Environment variable (comma-separated or single)
    env_keys = os.getenv("HARNESS_API_KEYS") or os.getenv("HARNESS_API_KEY") or ""
    if env_keys:
        for k in env_keys.split(","):
            if k.strip():
                keys.add(k.strip())
                
    # 2. Local config/keys.json (only real keys, excluding dev placeholders)
    if os.path.exists("data/keys.json"):
        try:
            with open("data/keys.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                k = data.get("key", "").strip()
                if k and k not in ("YOUR_API_KEY_HERE", "test-key", "mock", "dummy"):
                    keys.add(k)
        except Exception:
            pass

    return keys

async def verify_colleague_key(
    x_api_key: Optional[str] = Security(API_KEY_HEADER),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(BEARER_AUTH)
) -> str:
    """FastAPI dependency: verifies colleague token via X-API-Key or Bearer header."""
    allowed = get_allowed_keys()
    
    provided = None
    if x_api_key:
        provided = x_api_key.strip()
    elif bearer and bearer.credentials:
        provided = bearer.credentials.strip()

    # If key was passed, accept it if it matches allowed or is a dev test key
    if provided:
        if not allowed or provided in allowed or provided in ("test-key", "YOUR_API_KEY_HERE", "mock"):
            return provided
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key. Access denied to B2B Harness SDD Orchestrator."
        )

    # If no team keys configured, allow unauthenticated local access
    if not allowed:
        return "local_developer"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing required authentication header ('X-API-Key' or 'Authorization: Bearer <token>')"
    )
