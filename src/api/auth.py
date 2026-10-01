import os
import json
from typing import Optional, Set
from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from src.api.token_manager import EphemeralTokenManager

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
BEARER_AUTH = HTTPBearer(auto_error=False)

def get_allowed_keys() -> Set[str]:
    """Retrieves all authorized team keys strictly from environment variables and .env file."""
    keys = set()
    
    # 1. Environment variable (comma-separated or single)
    env_keys = os.getenv("HARNESS_API_KEYS") or os.getenv("HARNESS_API_KEY") or ""
    if env_keys:
        for k in env_keys.split(","):
            if k.strip():
                keys.add(k.strip())
                
    # 2. Local data/keys.json (if set locally by admin)
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
    """FastAPI dependency: verifies colleague token via X-API-Key or Bearer header against static & ephemeral keys."""
    allowed = get_allowed_keys()
    
    provided = None
    if x_api_key:
        provided = x_api_key.strip()
    elif bearer and bearer.credentials:
        provided = bearer.credentials.strip()

    # 1. Check if valid ephemeral/temporary token
    if provided and provided.startswith("hb2b-temp-"):
        token_mgr = EphemeralTokenManager()
        if token_mgr.validate_and_consume(provided):
            return provided
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Temporary token expired, exceeded request quota, or revoked."
        )

    # 2. Check static allowed keys
    if allowed:
        if not provided:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please provide a valid API key via 'X-API-Key' or 'Authorization: Bearer <token>' header."
            )
        if provided not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Invalid or revoked API key."
            )
        return provided

    # 3. If no keys configured yet, allow local dev / test keys
    if provided in ("test-key", "YOUR_API_KEY_HERE", "mock") or not provided:
        return provided or "local_developer"

    return provided
