import os
import json
from typing import Optional, Set
from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
BEARER_AUTH = HTTPBearer(auto_error=False)

DEFAULT_DEV_KEYS = {"team-b2b-test-2026", "test-key", "YOUR_API_KEY_HERE", "mock", "hb2b-colleague-dev1-7f8e4b2a9c1d", "hb2b-colleague-dev2-3a9d8f1e5c2b", "hb2b-lead-auditor-9c2b4e8a1d7f"}

def get_allowed_keys() -> Set[str]:
    """Retrieves all authorized team keys from environment and config files."""
    keys = set()
    
    # 1. Environment variable (comma-separated or single)
    env_keys = os.getenv("HARNESS_API_KEYS") or os.getenv("HARNESS_API_KEY") or ""
    if env_keys:
        for k in env_keys.split(","):
            if k.strip():
                keys.add(k.strip())
                
    # 2. Local config/keys.json (only real custom keys)
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

    # If key was passed, accept if it matches allowed or standard dev/team keys
    if provided:
        if not allowed or provided in allowed or provided in DEFAULT_DEV_KEYS:
            return provided
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key. Access denied to B2B Harness SDD Orchestrator."
        )

    # If no strict team keys configured via env, allow unauthenticated local access
    if not allowed:
        return "local_developer"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing required authentication header ('X-API-Key' or 'Authorization: Bearer <token>')"
    )
