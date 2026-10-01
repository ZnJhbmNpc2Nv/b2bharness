import os
import json
import time
import secrets
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

TOKEN_STORE_PATH = "data/ephemeral_keys.json"

class EphemeralTokenManager:
    def __init__(self, store_path: str = TOKEN_STORE_PATH):
        self.store_path = store_path
        os.makedirs(os.path.dirname(self.store_path) or ".", exist_ok=True)
        self._load()

    def _load(self):
        if os.path.exists(self.store_path):
            try:
                with open(self.store_path, "r", encoding="utf-8") as f:
                    self.tokens = json.load(f)
            except Exception:
                self.tokens = {}
        else:
            self.tokens = {}

    def _save(self):
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(self.tokens, f, indent=2)

    def issue_token(self, username: str, hours_valid: int = 24, max_requests: int = 100) -> Dict[str, Any]:
        """Issues a new time-limited and request-limited temporary token."""
        token_id = f"hb2b-temp-{username[:10]}-{secrets.token_hex(6)}"
        now = time.time()
        expires_at = now + (hours_valid * 3600)
        
        record = {
            "token": token_id,
            "username": username,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
            "expires_timestamp": expires_at,
            "max_requests": max_requests,
            "requests_used": 0,
            "is_active": True
        }
        
        self.tokens[token_id] = record
        self._save()
        return record

    def validate_and_consume(self, token: str) -> bool:
        """Validates token expiration and request quota."""
        self._load()
        if token not in self.tokens:
            return False
            
        record = self.tokens[token]
        if not record.get("is_active", True):
            return False
            
        now = time.time()
        if now > record.get("expires_timestamp", 0):
            record["is_active"] = False
            self._save()
            return False
            
        if record.get("requests_used", 0) >= record.get("max_requests", 100):
            record["is_active"] = False
            self._save()
            return False
            
        # Consume 1 request
        record["requests_used"] += 1
        self._save()
        return True

    def revoke_token(self, token: str) -> bool:
        self._load()
        if token in self.tokens:
            self.tokens[token]["is_active"] = False
            self._save()
            return True
        return False

    def list_tokens(self) -> Dict[str, Any]:
        self._load()
        return self.tokens

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ephemeral Token Manager for B2B Harness")
    subparsers = parser.add_subparsers(dest="command")
    
    issue_p = subparsers.add_parser("issue", help="Issue a temporary token")
    issue_p.add_argument("--user", required=True, help="Username or Colleague ID")
    issue_p.add_argument("--hours", type=int, default=24, help="Validity duration in hours (default 24)")
    issue_p.add_argument("--limit", type=int, default=100, help="Max allowed requests (default 100)")
    
    list_p = subparsers.add_parser("list", help="List all issued tokens")
    revoke_p = subparsers.add_parser("revoke", help="Revoke a token")
    revoke_p.add_argument("--token", required=True, help="Token string to revoke")

    args = parser.parse_args()
    mgr = EphemeralTokenManager()

    if args.command == "issue":
        res = mgr.issue_token(args.user, hours_valid=args.hours, max_requests=args.limit)
        print(f"\n✔ Временный токен успешно создан:")
        print(f"  Ключ:      {res['token']}")
        print(f"  Владелец:  {res['username']}")
        print(f"  Годен до:  {res['expires_at']} ({args.hours} часов)")
        print(f"  Лимит:     {res['max_requests']} запросов\n")
    elif args.command == "list":
        tokens = mgr.list_tokens()
        print(f"\nВсего токенов: {len(tokens)}")
        for t, d in tokens.items():
            status_str = "ACTIVE" if d.get("is_active") and time.time() < d.get("expires_timestamp", 0) else "EXPIRED/REVOKED"
            print(f"- {t} ({d['username']}) -> {status_str} (Использовано: {d['requests_used']}/{d['max_requests']})")
        print()
    elif args.command == "revoke":
        ok = mgr.revoke_token(args.token)
        print("✔ Токен отозван" if ok else "❌ Токен не найден")
