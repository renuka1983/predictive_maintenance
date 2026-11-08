import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, db, sim, sim_lock  # noqa: E402


def test_api_round_trip():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        lay = c.get("/api/layout").json()
        assert len([s for s in lay["stacks"] if s["kind"] == "STORAGE"]) == 72
        db.flush()
        inv = c.get("/api/inventory/bundles", params={"q": "SO-45892"}).json()
        assert len(inv["rows"]) == 3 and all(r["epc"] for r in inv["rows"])
        assert c.post("/api/ops/order", json={"order": "SO-45892"}).json()["status"] == "RELEASED"
        assert c.post("/api/ops/pick", json={}).json()["status"] == "PICKING"
        assert c.post("/api/ops/gate", json={}).status_code == 409
        with sim_lock:  # keep the app's own simulation loop out while we fast-forward
            for _ in range(4000):
                sim.step(0.25)
        db.flush()
        stats = c.get("/api/db/stats").json()["tables"]
        assert stats["movement_event"] > 0 and stats["simulation_event"] > 0
        assert c.get("/api/replay").status_code == 200
        bid = sim.orders["SO-45892"]["bundles"][0]
        assert c.get(f"/api/bundles/{bid}/history").json()["movements"]
        with c.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "state"
            assert ws.receive_json()["type"] == "inventory"
