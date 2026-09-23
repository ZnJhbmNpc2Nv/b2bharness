import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_full_pipeline_flow():
    # 1. Save Token
    res = client.post("/config/keys", json={"value": "YOUR_API_KEY_HERE"})
    assert res.status_code == 200

    # 2. Check Status
    res = client.get("/config/status")
    assert res.status_code == 200
    assert res.json()["active"] is True

    # 3. Refine Intent via LLM
    res = client.post("/pipeline/refine-intent", json={"text": "Create a user authentication module"})
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

    print("Full pipeline flow test passed successfully!")
