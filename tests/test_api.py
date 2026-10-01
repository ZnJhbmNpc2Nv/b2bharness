import pytest
import os
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_full_pipeline_flow():
    test_key = "test_team_access_key"
    
    # 1. Save Token
    res = client.post("/config/keys", json={"value": test_key})
    assert res.status_code == 200

    # 2. Check Status
    res = client.get("/config/status")
    assert res.status_code == 200
    assert res.json()["active"] is True

    # 3. Refine Intent via pipeline with authorized header
    res = client.post(
        "/pipeline/refine-intent",
        headers={"X-API-Key": test_key},
        json={"text": "Create a user authentication module"}
    )
    assert res.status_code == 200
    assert "refined_text" in res.json()

    # 4. Get Pipeline Graph
    res = client.get("/pipeline/graph")
    assert res.status_code == 200
    data = res.json()
    assert "PRE_SDD" in data["nodes"]

    # 5. Approve current stage
    res = client.post("/pipeline/approve")
    assert res.status_code == 200

    # 6. Advance pipeline
    res = client.post("/pipeline/advance", headers={"session-id": "session_001", "user-id": "admin"})
    assert res.status_code == 200
    assert res.json()["state"] == "INTENT"

    # 7. Check /report route
    res = client.get("/report")
    assert res.status_code == 200
    assert "B2B-Harness SDD" in res.text

    # Cleanup test keys
    client.delete("/config/keys")
