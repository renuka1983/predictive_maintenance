"""FastAPI application: REST + WebSocket front door to the warehouse twin."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select

from . import config
from . import models as m
from .persistence import Persistence
from .sim.engine import Simulation

log = logging.getLogger("twin")


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def send(self, ws: WebSocket, msg: dict):
        await ws.send_text(json.dumps(msg, separators=(",", ":")))

    async def broadcast(self, msg: dict):
        if not self.clients:
            return
        data = json.dumps(msg, separators=(",", ":"))
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


db = Persistence(config.DATABASE_URL, enabled=config.PERSISTENCE_ENABLED)
sim = Simulation(seed=config.SIM_SEED, persistence=db, speed=config.DEFAULT_SPEED)
hub = Hub()


async def sim_loop():
    tick = 1.0 / config.SIM_TICK_HZ
    bcast = 1.0 / config.BROADCAST_HZ
    last = time.perf_counter()
    last_b = 0.0
    last_ops = 0.0
    inv_sent = -1
    while True:
        await asyncio.sleep(tick)
        now = time.perf_counter()
        try:
            sim.step(now - last)
        except Exception:  # keep the demo alive; surface the failure in the log
            log.exception("simulation step failed")
        last = now
        if now - last_b >= bcast:
            last_b = now
            await hub.broadcast(sim.state_msg())
            if sim.inv_version != inv_sent:
                inv_sent = sim.inv_version
                await hub.broadcast(sim.inventory_msg())
            if sim.new_events:
                evs, sim.new_events = sim.new_events, []
                await hub.broadcast({"type": "events", "events": evs})
        if now - last_ops >= 1.0:
            last_ops = now
            await hub.broadcast(sim.ops_msg())


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(sim_loop())
    yield
    task.cancel()
    db.stop()


app = FastAPI(title="Warehouse Digital Twin – Bundle Tracking & Dispatch Assurance PoC", version="0.1.0",
              lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def bad(e: Exception):
    raise HTTPException(status_code=409, detail=str(e))


# ------------------------------------------------------------------ meta
@app.get("/api/health")
async def health():
    return {"status": "ok", "sim_clock": sim.ts(), "db": config.DATABASE_URL.split("://")[0],
            "db_writes": db.writes, "db_errors": db.errors, "clients": len(hub.clients)}


@app.get("/api/layout")
async def get_layout():
    return sim.layout.to_dict()


@app.get("/api/state")
async def get_state():
    return {**sim.state_msg(), "inventory": sim.inventory_msg()["bundles"], "ops": sim.ops_msg(),
            "events": sim.events[-80:]}


# ------------------------------------------------------------- simulation
@app.post("/api/sim/{action}")
async def sim_action(action: str, body: dict = Body(default={})):
    if action == "start":
        sim.running = True
    elif action == "pause":
        sim.running = False
    elif action == "reset":
        sim.reset()
        await hub.broadcast(sim.inventory_msg())
    elif action == "speed":
        sim.speed = max(0.25, min(20.0, float(body.get("speed", 1))))
    elif action == "autopilot":
        sim.autopilot = bool(body.get("on", not sim.autopilot))
        sim.emit("AUTOPILOT", f"Autopilot {'ON' if sim.autopilot else 'OFF'}", "info")
    elif action == "auto-putaway":
        sim.auto_putaway = bool(body.get("on", not sim.auto_putaway))
        sim.emit("AUTO_PUTAWAY", f"Automatic production putaway {'ON' if sim.auto_putaway else 'OFF'}", "info")
    elif action == "auto-gate":
        sim.auto_gate = bool(body.get("on", not sim.auto_gate))
    else:
        raise HTTPException(404, "unknown action")
    return sim.state_msg()


@app.post("/api/ops/receive")
async def op_receive():
    b = sim.produce()
    if b is None:
        raise HTTPException(409, "Receiving area is full")
    return sim.bundle_detail(b["id"])


@app.post("/api/ops/order")
async def op_order(body: dict = Body(default={})):
    try:
        return sim.order_dict(sim.release_order(body.get("order")), detail=True)
    except ValueError as e:
        bad(e)


@app.post("/api/ops/pick")
async def op_pick(body: dict = Body(default={})):
    try:
        return sim.order_dict(sim.start_picking(body.get("order")), detail=True)
    except ValueError as e:
        bad(e)


@app.post("/api/ops/dispatch")
async def op_dispatch(body: dict = Body(default={})):
    try:
        return sim.truck_dict(sim.dispatch_order(body.get("order")))
    except ValueError as e:
        bad(e)


@app.post("/api/ops/gate")
async def op_gate(body: dict = Body(default={})):
    try:
        return sim.truck_dict(sim.send_to_gate(body.get("truck")))
    except ValueError as e:
        bad(e)


@app.post("/api/ops/inject")
async def op_inject(body: dict = Body(...)):
    try:
        return sim.order_dict(sim.inject(body.get("kind", "")))
    except ValueError as e:
        bad(e)


@app.post("/api/ops/resolve")
async def op_resolve(body: dict = Body(default={})):
    try:
        return sim.resolve_exception(body.get("exception"))
    except ValueError as e:
        bad(e)


@app.post("/api/scenario/{sid}")
async def scenario(sid: int, body: dict = Body(default={})):
    try:
        sim.running = True
        return sim.start_scenario(sid, body.get("inject"))
    except ValueError as e:
        bad(e)


@app.delete("/api/scenario")
async def scenario_stop():
    sim.stop_scenario()
    return {"ok": True}


# ------------------------------------------------------------ live reads
@app.get("/api/forklifts")
async def forklifts():
    return [sim.forklift_dict(f, detail=True) for f in sim.forklifts.values()]


@app.get("/api/forklifts/{fid}")
async def forklift(fid: str):
    f = sim.forklifts.get(fid)
    if f is None:
        raise HTTPException(404, "forklift not found")
    return sim.forklift_dict(f, detail=True)


@app.get("/api/bundles/{bid}/live")
async def bundle_live(bid: str):
    d = sim.bundle_detail(bid)
    if d is None:
        raise HTTPException(404, "bundle not found")
    return d


@app.get("/api/stacks/{sid}")
async def stack(sid: str):
    d = sim.stack_detail(sid)
    if d is None:
        raise HTTPException(404, "stack not found")
    return d


@app.get("/api/orders")
async def orders(status: Optional[str] = None):
    out = [sim.order_dict(o) for o in sorted(sim.orders.values(), key=lambda o: o["order_number"])]
    if status:
        out = [o for o in out if o["status"] == status]
    return out


@app.get("/api/orders/{number}")
async def order(number: str):
    o = sim.orders.get(number)
    if o is None:
        raise HTTPException(404, "order not found")
    return sim.order_dict(o, detail=True)


@app.get("/api/tasks")
async def tasks():
    return sim.ops_msg()


@app.get("/api/analytics")
async def analytics():
    return sim.analytics()


@app.get("/api/oracle/log")
async def oracle_log(limit: int = 60):
    return list(reversed(sim.oracle.log[-limit:]))


@app.get("/api/exceptions")
async def exceptions():
    return list(reversed(sim.exceptions))


@app.get("/api/replay")
async def replay(task: Optional[str] = None):
    r = sim.replay(task)
    if r is None:
        raise HTTPException(404, "no completed movement to replay yet")
    return r


# --------------------------------------------- system-of-record reads (DB)
@app.get("/api/inventory/bundles")
def inventory(q: str = "", warehouse: str = "", status: str = "", limit: int = Query(200, le=1000)):
    with db.Session() as s:
        stmt = (select(m.Bundle, m.BundleLocation, m.RfidTag)
                .join(m.BundleLocation, m.BundleLocation.bundle_id == m.Bundle.id, isouter=True)
                .join(m.RfidTag, m.RfidTag.bundle_id == m.Bundle.id, isouter=True))
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(m.Bundle.barcode.ilike(like), m.Bundle.sales_order.ilike(like),
                                  m.Bundle.customer.ilike(like), m.Bundle.product_code.ilike(like),
                                  m.Bundle.product_name.ilike(like), m.RfidTag.epc.ilike(like),
                                  m.BundleLocation.location_code.ilike(like)))
        if warehouse:
            stmt = stmt.where(m.BundleLocation.warehouse_id == warehouse)
        if status:
            stmt = stmt.where(m.Bundle.status == status)
        stmt = stmt.order_by(m.Bundle.sales_order, m.Bundle.barcode).limit(limit)
        rows = s.execute(stmt).all()
        total = s.scalar(select(func.count()).select_from(m.Bundle))
        return {"total": total, "rows": [{
            "id": b.id, "barcode": b.barcode, "epc": t.epc if t else None, "customer": b.customer,
            "sales_order": b.sales_order, "product_code": b.product_code, "product_name": b.product_name,
            "alloy": b.alloy, "finish": b.finish, "length_mm": b.length_mm, "pieces": b.pieces,
            "weight_kg": b.weight_kg, "status": b.status,
            "warehouse": loc.warehouse_id if loc else None, "location_code": loc.location_code if loc else None,
            "level": loc.level if loc else None, "updated_at": loc.updated_at.isoformat() if loc and loc.updated_at else None,
        } for b, loc, t in rows]}


@app.get("/api/bundles/{bid}/history")
def bundle_history(bid: str):
    with db.Session() as s:
        moves = s.scalars(select(m.MovementEvent).where(m.MovementEvent.bundle_id == bid)
                          .order_by(m.MovementEvent.id.desc()).limit(50)).all()
        tasks_ = s.scalars(select(m.MovementTask).where(m.MovementTask.bundle_id == bid)
                           .order_by(m.MovementTask.created_at.desc()).limit(20)).all()
        return {
            "movements": [{"ts": x.ts.isoformat(), "type": x.event_type, "forklift": x.forklift_id, "task": x.task_id,
                           "location": x.location_code} for x in moves],
            "tasks": [{"id": t.id, "type": t.type, "status": t.status, "forklift": t.forklift_id, "from": t.from_code,
                       "to": t.to_code, "distance_m": t.distance_m,
                       "finished_at": t.finished_at.isoformat() if t.finished_at else None} for t in tasks_],
        }


@app.get("/api/db/stats")
def db_stats():
    with db.Session() as s:
        counts = {}
        for model in m.Base.__subclasses__():
            counts[model.__tablename__] = s.scalar(select(func.count()).select_from(model))
        return {"engine": config.DATABASE_URL.split("://")[0], "tables": counts, "writes": db.writes,
                "pending": db.q.qsize()}


@app.get("/api/db/movements")
def db_movements(limit: int = Query(100, le=500)):
    with db.Session() as s:
        rows = s.scalars(select(m.MovementEvent).order_by(m.MovementEvent.id.desc()).limit(limit)).all()
        return [{"ts": x.ts.isoformat(), "type": x.event_type, "bundle": x.bundle_id, "forklift": x.forklift_id,
                 "task": x.task_id, "location": x.location_code} for x in rows]


@app.get("/api/db/dispatch-events")
def db_dispatch(limit: int = Query(100, le=500)):
    with db.Session() as s:
        rows = s.scalars(select(m.DispatchEvent).order_by(m.DispatchEvent.id.desc()).limit(limit)).all()
        return [{"ts": x.ts.isoformat(), "manifest": x.manifest_id, "type": x.event_type, "epc": x.epc,
                 "bundle": x.bundle_id, "detail": x.detail} for x in rows]


# ----------------------------------------------------------------- socket
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    hub.clients.add(websocket)
    try:
        await hub.send(websocket, sim.state_msg())
        await hub.send(websocket, sim.inventory_msg())
        await hub.send(websocket, {"type": "events", "events": sim.events[-80:], "replace": True})
        await hub.send(websocket, sim.ops_msg())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(websocket)
