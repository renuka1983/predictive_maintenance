"""Discrete-time warehouse simulation.

The engine owns the live state of the twin: bundles, floor stacks, forklifts,
trucks, orders and the RFID gate. It is stepped by the API server's asyncio
loop and pushes every state change to :class:`Persistence`.

Main pieces
-----------
* Putaway engine   - allocates floor-stack locations for new bundles.
* Picking engine   - picks released order bundles, relocating any bundles
                     stacked on top of them first (stack dependency).
* Dispatch engine  - truck arrival, loading, RFID gate reconciliation and
                     exception handling.
* Forklift sim     - action queues (travel / turn / lift / attach / detach)
                     executed over a routed aisle graph.
"""
from __future__ import annotations

import math
import random
from collections import deque
from datetime import datetime, timedelta

from .. import layout as L
from ..oracle_mock import CUSTOMERS, PRODUCT_BY_CODE, PRODUCTS, MockOracle, iso

SIM_START = datetime(2026, 11, 9, 7, 30, 0)
CARRY_H = 0.35
LOW_H = 0.12
SPEED_EMPTY = 3.2
SPEED_LOADED = 2.3
SPEED_APPROACH = 1.0
FORK_SPEED = 0.7
TURN_RATE = 1.9
TRUCK_SPEED = 6.0

ROLE_LABEL = {"PUTAWAY": "Inbound / Putaway", "PICKING": "Outbound / Picking & Dispatch"}
ACTIVE_TRUCK_STATES = {"ARRIVING", "AT_DOCK", "LOADED", "TO_GATE", "READING", "EXCEPTION", "RETURNING", "AUTHORIZED"}


def angdiff(a: float, b: float) -> float:
    return (a - b + math.pi) % (2 * math.pi) - math.pi


class Forklift:
    def __init__(self, fid: str, role: str, park: dict, battery: float):
        self.id = fid
        self.name = f"{'Putaway' if role == 'PUTAWAY' else 'Picking'} forklift {fid}"
        self.role = role
        self.park = park
        self.x, self.z = park["x"], park["z"]
        self.heading = park["heading"]
        self.fork = LOW_H
        self.node = park["node"]
        self.next_node: str | None = None
        self.state = "IDLE"
        self.load: str | None = None
        self.job: deque | None = None
        self.job_id: str | None = None
        self.task: dict | None = None
        self.actions: deque = deque()
        self.busy_time = 0.0
        self.distance = 0.0
        self.tasks_done = 0
        self.history: deque = deque(maxlen=25)
        self.idle_since = 0.0
        self.battery = battery
        self.at_park = True
        self.track: list = []
        self.dest: dict | None = None


class Simulation:
    def __init__(self, seed: int = 42, persistence=None, speed: float = 3.0):
        self.seed = seed
        self.db = persistence
        self.default_speed = speed
        self.layout = L.build_layout()
        self.reset()

    # ================================================================ basics
    def now(self) -> datetime:
        return SIM_START + timedelta(seconds=self.t)

    def ts(self) -> str:
        return iso(self.now())

    def reset(self):
        self.rng = random.Random(self.seed)
        self.oracle = MockOracle(self.rng)
        self.t = 0.0
        self.running = True
        self.speed = self.default_speed
        self.autopilot = False
        self.auto_putaway = True
        self.auto_gate = False
        self.prod_interval = 32.0
        self._next_prod = 6.0
        self._seq = {"bundle": 4100, "task": 0, "event": 0, "truck": 0, "job": 0, "exc": 0, "manifest": 0}
        self.bundles: dict[str, dict] = {}
        self.stack_bundles: dict[str, list] = {sid: [] for sid in self.layout.stacks}
        self.incoming: dict[str, int] = {sid: 0 for sid in self.layout.stacks}
        self.locks: dict[str, str] = {}
        self.forklifts: dict[str, Forklift] = {}
        self.trucks: dict[str, dict] = {}
        self.orders: dict[str, dict] = {}
        self.manifests: dict[str, dict] = {}
        self.exceptions: list[dict] = []
        self.tasks: dict[str, dict] = {}
        self.queue: list[dict] = []
        self.events: list[dict] = []
        self.new_events: list[dict] = []
        self.gate = {"state": "IDLE", "truck": None, "reads": [], "t": 0.0, "result": None}
        self.lane_owner: dict[str, str | None] = {lane: None for lane in self.layout.lanes}
        self.inv_version = 1
        self.prod_so: dict | None = None
        self.scenario: dict | None = None
        self._scn_match: list = []
        self._timers: list = []
        self._last_auto = {"order": -999.0, "tick": 0.0}
        self._last_pos_persist = 0.0
        self._last_dispatch = 0.0
        self.kpi = {"putaways": 0, "picks": 0, "relocations": 0, "loads": 0, "unloads": 0, "trucks_dispatched": 0,
                    "bundles_dispatched": 0, "gate_validations": 0, "first_pass_ok": 0, "exceptions": 0,
                    "exceptions_resolved": 0, "rfid_reads": 0, "orders_released": 0, "orders_staged": 0,
                    "produced": 0}
        self.cycle = {"PUTAWAY": [], "PICK": [], "ORDER": [], "TRUCK": []}
        self.series: list[dict] = []
        self._next_sample = 0.0
        self.auto_gate_once = False
        self._awaiting_location: list[str] = []
        self._seed_world()
        if self.db is not None:
            self.db.reset(self._seed_rows())
        self.emit("SIM_RESET", "Simulation reset — warehouse twin loaded from Oracle mock and bundle registry", "info")
        self._sample()

    def _id(self, kind: str, prefix: str, width: int = 4) -> str:
        self._seq[kind] += 1
        return f"{prefix}{self._seq[kind]:0{width}d}"

    # ================================================================ events
    def emit(self, etype: str, message: str, severity: str = "info", **refs) -> dict:
        self._seq["event"] += 1
        ev = {"id": self._seq["event"], "t": round(self.t, 2), "ts": self.ts(), "type": etype, "severity": severity,
              "message": message, "refs": {k: v for k, v in refs.items() if v is not None}}
        self.events.append(ev)
        if len(self.events) > 600:
            self.events = self.events[-500:]
        self.new_events.append(ev)
        if self.db is not None:
            self.db.sim_event(ev)
        self._scenario_check(ev)
        return ev

    def after(self, delay: float, fn):
        self._timers.append((self.t + delay, fn))

    # ============================================================== seeding
    def _new_bundle(self, order: dict, produced: datetime) -> dict:
        prod = PRODUCT_BY_CODE[order["lines"][0]["product"]]
        n = self._seq["bundle"] = self._seq["bundle"] + 1
        bid = f"B{n:06d}"
        length = self.rng.choice([6000, 6000, 6000, 6500, 5800])
        pieces = self.rng.randint(24, 96)
        b = {
            "id": bid, "barcode": f"BND{produced:%y%m}-{n:06d}",
            "epc": "3034" + "".join(self.rng.choice("0123456789ABCDEF") for _ in range(20)),
            "so": order["order_number"], "customer": order["customer"],
            "product": prod["code"], "product_name": prod["name"], "alloy": f"{prod['alloy']}-{prod['temper']}",
            "finish": prod["finish"], "wrap": prod["wrap"], "length_mm": length, "pieces": pieces,
            "weight_kg": round(pieces * length / 1000 * self.rng.uniform(0.9, 2.4), 1),
            "dims": f"{prod['name'].split()[-1]} · L{length} mm · {pieces} pcs",
            "status": "PRODUCED", "produced_at": iso(produced), "loc": {"kind": "incoming"},
            "last_move": None, "reserved": None, "left_behind": False,
        }
        self.bundles[bid] = b
        order["bundles"].append(bid)
        return b

    def _place_initial(self, b: dict, sid: str, status: str = "STORED"):
        self.stack_bundles[sid].append(b["id"])
        b["loc"] = {"kind": "stack", "stack": sid, "level": len(self.stack_bundles[sid])}
        b["status"] = status

    def _seed_world(self):
        rng = self.rng
        lay = self.layout
        for fid, park in lay.parking.items():
            role = "PUTAWAY" if int(fid[-1]) <= 4 else "PICKING"
            self.forklifts[fid] = Forklift(fid, role, park, rng.uniform(72, 98))

        storage = [s for s in lay.stacks.values() if s.kind == "STORAGE"]
        indoor = [s for s in storage if s.warehouse_id == "WH01"]
        yard = [s for s in storage if s.warehouse_id == "WH02"]

        def room(s, need=1):
            return len(self.stack_bundles[s.id]) + need <= s.max_levels

        # SO-45890: dispatched before the demo started
        o = self.oracle.book_order(PRODUCT_BY_CODE["AP-60402"], 4, self.now() - timedelta(days=6), CUSTOMERS[1])
        o.update(status="DISPATCHED", released_at=iso(self.now() - timedelta(hours=20)),
                 staged_at=iso(self.now() - timedelta(hours=19)), dispatched_at=iso(self.now() - timedelta(hours=18)))
        self.orders[o["order_number"]] = o
        # SO-45891: picked and waiting in staging lane 1
        o = self.oracle.book_order(PRODUCT_BY_CODE["AP-12050"], 4, self.now() - timedelta(days=4), CUSTOMERS[4])
        o.update(status="STAGED", released_at=iso(self.now() - timedelta(hours=2)),
                 staged_at=iso(self.now() - timedelta(minutes=40)), lane="LANE-1")
        self.orders[o["order_number"]] = o
        self.lane_owner["LANE-1"] = o["order_number"]
        for i in range(4):
            b = self._new_bundle(o, self.now() - timedelta(days=3, hours=i))
            self._place_initial(b, lay.lanes["LANE-1"][i % 2], "STAGED")
            b["reserved"] = o["order_number"]
        hist_manifest = {"id": "DM-45890-1", "order_number": "SO-45890", "truck_id": "TRK-00", "truck_plate": "MH-12-QX-2207",
                         "delivery_id": "WSH-7712904", "expected_epcs": [], "expected_barcodes": [], "status": "VALIDATED",
                         "created_at": iso(self.now() - timedelta(hours=18, minutes=30)),
                         "validated_at": iso(self.now() - timedelta(hours=18)), "result": {"ok": True, "missing": [], "unexpected": []}}
        self.manifests[hist_manifest["id"]] = hist_manifest

        # SO-45892: the scripted picking order (one bundle buried -> rehandle)
        so92 = self.oracle.book_order(PRODUCT_BY_CODE["AP-15060"], 3, self.now() - timedelta(days=3), CUSTOMERS[5])
        self.orders[so92["order_number"]] = so92
        so92_bundles = [self._new_bundle(so92, self.now() - timedelta(days=2, hours=h)) for h in (6, 5, 4)]

        # Booked backlog with bundles in stock
        backlog = []
        for _ in range(40):
            prod = rng.choice(PRODUCTS)
            o = self.oracle.book_order(prod, rng.randint(3, 5), self.now() - timedelta(days=rng.uniform(1, 9)))
            self.orders[o["order_number"]] = o
            backlog.append(o)
        for o in backlog:
            prod = PRODUCT_BY_CODE[o["lines"][0]["product"]]
            pool = (yard if rng.random() < 0.6 else indoor) if prod["outdoor"] else indoor
            homes = [s for s in pool if room(s, 2)] or [s for s in storage if room(s)]
            home = rng.choice(homes)
            for i in range(o["lines"][0]["qty_bundles"]):
                b = self._new_bundle(o, self.now() - timedelta(days=rng.uniform(0.5, 5)))
                target = home if (room(home) and rng.random() < 0.75) else None
                if target is None:
                    opts = [s for s in pool if room(s)] or [s for s in storage if room(s)]
                    target = rng.choice(opts)
                self._place_initial(b, target.id)

        # place SO-45892 deliberately: indoor top, indoor buried, yard top
        def low(pool, cond):
            ok = [s for s in pool if cond(s)]
            return min(ok, key=lambda s: len(self.stack_bundles[s.id]))
        a = low(indoor, lambda s: s.z < 0 and len(self.stack_bundles[s.id]) <= 3)
        bstack = low(indoor, lambda s: s.z > 0 and s.id != a.id)
        c = low(yard, lambda s: True)
        self._place_initial(so92_bundles[0], a.id)
        self._place_initial(so92_bundles[1], bstack.id)
        self._place_initial(so92_bundles[2], c.id)
        filler_order = backlog[-1]
        filler = self._new_bundle(filler_order, self.now() - timedelta(hours=10))
        filler_order["lines"][0]["qty_bundles"] += 1
        self._place_initial(filler, bstack.id)

    def _seed_rows(self) -> dict:
        lay = self.layout
        stacks = [{"id": s.id, "bay_id": s.bay_id, "zone_id": s.zone_id, "warehouse_id": s.warehouse_id, "code": s.code,
                   "kind": s.kind, "x": s.x, "z": s.z, "yaw": s.yaw, "max_levels": s.max_levels, "length_m": L.BUNDLE_L,
                   "width_m": L.BUNDLE_W, "current_height": len(self.stack_bundles[s.id])} for s in lay.stacks.values()]
        levels = []
        for s in lay.stacks.values():
            sb = self.stack_bundles[s.id]
            for lv in range(1, s.max_levels + 1):
                levels.append({"id": f"{s.id}-L{lv:02d}", "stack_id": s.id, "level": lv,
                               "location_code": s.location_code(lv), "bundle_id": sb[lv - 1] if lv <= len(sb) else None})
        return {
            "warehouses": [{"id": w.id, "plant": L.PLANT, "name": w.name, "kind": w.kind, "bounds": list(w.bounds)}
                           for w in lay.warehouses.values()],
            "zones": [{"id": z.id, "warehouse_id": z.warehouse_id, "code": z.code, "name": z.name, "kind": z.kind,
                       "rect": list(z.rect)} for z in lay.zones.values()],
            "bays": [{"id": b.id, "zone_id": b.zone_id, "warehouse_id": b.warehouse_id, "code": b.code,
                      "rect": list(b.rect)} for b in lay.bays.values()],
            "stacks": stacks, "levels": levels,
            "bundles": [self._bundle_row(b) for b in self.bundles.values()],
            "tags": [{"epc": b["epc"], "bundle_id": b["id"], "associated_at": b["produced_at"]} for b in self.bundles.values()],
            "locations": [self._location_row(b) for b in self.bundles.values()],
            "forklifts": [{"id": f.id, "name": f.name, "role": f.role, "model": "Multi-directional LPG forklift 5.0 t",
                           "rfid_reader": "Fork-mounted UHF reader, 2 antennas", "uwb_tag": f"UWB-TAG-{f.id}"}
                          for f in self.forklifts.values()],
            "positions": [self._position_row(f) for f in self.forklifts.values()],
            "orders": list(self.orders.values()),
            "manifests": list(self.manifests.values()),
        }

    @staticmethod
    def _bundle_row(b: dict) -> dict:
        return {"id": b["id"], "barcode": b["barcode"], "product_code": b["product"], "product_name": b["product_name"],
                "alloy": b["alloy"], "finish": b["finish"], "length_mm": b["length_mm"], "pieces": b["pieces"],
                "weight_kg": b["weight_kg"], "customer": b["customer"], "sales_order": b["so"], "status": b["status"],
                "produced_at": b["produced_at"], "wrap": b["wrap"]}

    def _position_row(self, f: Forklift) -> dict:
        return {"forklift_id": f.id, "x": round(f.x, 2), "z": round(f.z, 2), "heading": round(f.heading, 3),
                "fork_height": round(f.fork, 2), "state": f.state, "load_bundle_id": f.load, "updated_at": self.ts()}

    # ============================================================ locations
    def loc_info(self, b: dict) -> dict:
        loc = b["loc"]
        k = loc["kind"]
        if k == "stack":
            st = self.layout.stacks[loc["stack"]]
            zone = self.layout.zones[st.zone_id]
            return {"kind": "STACK", "code": st.location_code(loc["level"]), "warehouse": st.warehouse_id,
                    "warehouse_name": self.layout.warehouses[st.warehouse_id].name, "zone": zone.code,
                    "zone_name": zone.name, "bay": self.layout.bays[st.bay_id].code, "stack": st.code,
                    "stack_id": st.id, "level": loc["level"], "x": st.x, "z": st.z,
                    "y": L.level_bottom(loc["level"]) + L.BUNDLE_H / 2}
        if k == "forklift":
            f = self.forklifts[loc["forklift"]]
            return {"kind": "FORKLIFT", "code": f"IN TRANSIT · {f.id}", "warehouse": self._wh_at(f.x),
                    "forklift": f.id, "x": f.x, "z": f.z, "y": f.fork}
        if k == "truck":
            tr = self.trucks.get(loc["truck"], {})
            return {"kind": "TRUCK", "code": f"{L.PLANT}-WH02-Z04-DOCK1-{loc['truck']}-C{loc['col'] + 1}-L{loc['level']:02d}",
                    "warehouse": "WH02", "zone": "Z04", "zone_name": "Truck Loading & RFID Gate", "truck": loc["truck"],
                    "plate": tr.get("plate"), "x": tr.get("x", L.DOCK["x"]), "z": tr.get("z", 0), "y": L.TRUCK_BED}
        if k == "dispatched":
            return {"kind": "DISPATCHED", "code": f"DISPATCHED · {loc.get('truck', '')}", "warehouse": None}
        return {"kind": "INCOMING", "code": "PRODUCTION", "warehouse": None}

    @staticmethod
    def _wh_at(x: float) -> str:
        return "WH01" if x < 2 else "WH02"

    def _location_row(self, b: dict) -> dict:
        li = self.loc_info(b)
        st = self.layout.stacks.get(li.get("stack_id", ""))
        return {"bundle_id": b["id"], "location_kind": li["kind"], "warehouse_id": li.get("warehouse"),
                "zone_id": st.zone_id if st else None, "bay_id": st.bay_id if st else None,
                "stack_id": st.id if st else None, "level": li.get("level"), "location_code": li["code"],
                "x": li.get("x"), "y": li.get("y"), "z": li.get("z"), "updated_at": self.ts()}

    def _persist_bundle_loc(self, b: dict):
        if self.db is not None:
            self.db.location(self._location_row(b))
            self.db.status(b["id"], b["status"])

    # ------------------------------------------------------------- endpoints
    def ep_list(self, ep: tuple) -> list:
        if ep[0] == "S":
            return self.stack_bundles[ep[1]]
        return self.trucks[ep[1]]["slots"][ep[2]]

    def ep_max(self, ep: tuple) -> int:
        return self.layout.stacks[ep[1]].max_levels if ep[0] == "S" else L.TRUCK_LEVELS

    def ep_geom(self, ep: tuple) -> dict:
        if ep[0] == "S":
            s = self.layout.stacks[ep[1]]
            return {"node": s.node, "pre": s.pre, "app": s.app, "heading": s.heading, "base": 0.0}
        x, z = L.truck_slot_world(ep[2])
        return {"node": self.layout.node(L.YD_E, 0.0), "pre": (x - L.PRE_D, z), "app": (x - L.APP_D, z),
                "heading": 0.0, "base": L.TRUCK_BED}

    def ep_code(self, ep: tuple, level: int | None = None) -> str:
        if level is None:
            level = len(self.ep_list(ep)) + 1
        if ep[0] == "S":
            return self.layout.stacks[ep[1]].location_code(level)
        return f"{L.PLANT}-WH02-Z04-DOCK1-{ep[1]}-C{ep[2] + 1}-L{level:02d}"

    def ep_label(self, ep: tuple) -> str:
        if ep[0] == "S":
            s = self.layout.stacks[ep[1]]
            return f"{s.id}"
        return f"Truck {ep[1]} · column {ep[2] + 1}"

    def lock_key(self, ep: tuple) -> str:
        return f"S:{ep[1]}" if ep[0] == "S" else f"T:{ep[1]}:{ep[2]}"

    def locked(self, ep: tuple) -> bool:
        return self.lock_key(ep) in self.locks

    def released_orders(self) -> set:
        return {n for n, o in self.orders.items() if o["status"] in ("RELEASED", "PICKING")}

    def _bury_cost(self, sid: str, so: str) -> int:
        """Bundles in the stack that belong to orders likely to ship before ``so`` (FIFO by order number)."""
        return sum(1 for x in self.stack_bundles[sid] if self.bundles[x]["so"] < so)

    def _stack_has_reserved(self, sid: str) -> bool:
        return any(self.bundles[b]["reserved"] for b in self.stack_bundles[sid])

    # ============================================================ putaway engine
    def choose_putaway_stack(self, b: dict) -> str | None:
        prod = PRODUCT_BY_CODE[b["product"]]
        best, best_score = None, 1e9
        for s in self.layout.stacks.values():
            if s.kind != "STORAGE" or self.locked(("S", s.id)):
                continue
            if s.warehouse_id == "WH02" and not prod["outdoor"]:
                continue
            sb = self.stack_bundles[s.id]
            if len(sb) + self.incoming[s.id] >= s.max_levels:
                continue
            buried = self._bury_cost(s.id, b["so"])
            if not sb:
                score = 1.0
            elif all(self.bundles[x]["so"] == b["so"] for x in sb):
                score = 0.0
            else:
                score = 3.0 + 4.0 * buried + (0 if self.bundles[sb[-1]]["product"] == b["product"] else 0.5)
            if self._stack_has_reserved(s.id):
                score += 50
            score += self.incoming[s.id] * 1.5
            score += math.hypot(s.x - L.RECEIVING_X, s.z) / 45.0
            if prod["outdoor"] and s.warehouse_id == "WH02":
                score -= 1.5
            if score < best_score:
                best, best_score = s.id, score
        return best

    def choose_relocation_stack(self, src: str, exclude: dict, so: str = "") -> str | None:
        srcs = self.layout.stacks[src]
        best, best_d = None, 1e9
        for s in self.layout.stacks.values():
            if s.kind != "STORAGE" or s.id == src or s.warehouse_id != srcs.warehouse_id:
                continue
            if self.locked(("S", s.id)) or self._stack_has_reserved(s.id):
                continue
            if len(self.stack_bundles[s.id]) + self.incoming[s.id] + exclude.get(s.id, 0) >= s.max_levels:
                continue
            d = abs(s.x - srcs.x) + abs(s.z - srcs.z) * 0.6 + 25.0 * self._bury_cost(s.id, so)
            if d < best_d:
                best, best_d = s.id, d
        return best

    def produce(self, scenario: bool = False) -> dict | None:
        free = [s for s in self.layout.stacks.values()
                if s.kind == "RECEIVING" and not self.stack_bundles[s.id] and not self.incoming[s.id]
                and not self.locked(("S", s.id))]
        if not free:
            if not scenario:
                self.emit("RECEIVING_FULL", "Receiving area full — production transfer waiting for putaway", "warning")
            return None
        if self.prod_so is None or len(self.prod_so["bundles"]) >= self.prod_so["lines"][0]["qty_bundles"]:
            prod = self.rng.choice(PRODUCTS)
            self.prod_so = self.oracle.book_order(prod, self.rng.randint(3, 5), self.now())
            self.orders[self.prod_so["order_number"]] = self.prod_so
            if self.db is not None:
                self.db.order(self.prod_so)
        st = min(free, key=lambda s: abs(s.z))
        b = self._new_bundle(self.prod_so, self.now())
        self.stack_bundles[st.id].append(b["id"])
        b["loc"] = {"kind": "stack", "stack": st.id, "level": 1}
        b["status"] = "RECEIVED"
        b["last_move"] = {"type": "PRODUCED", "ts": self.ts(), "to": st.location_code(1), "forklift": None}
        self.inv_version += 1
        self.kpi["produced"] += 1
        if self.db is not None:
            self.db.bundle(self._bundle_row(b))
            self.db.tag({"epc": b["epc"], "bundle_id": b["id"], "associated_at": self.ts()})
            self.db.location(self._location_row(b))
            self.db.level(st.id, 1, b["id"], 1)
            self.db.order(self.prod_so)
        self.emit("BUNDLE_PRODUCED", f"Finished bundle {b['barcode']} arrived from extrusion line ({b['product_name']}, "
                  f"{b['so']})", "info", bundle=b["id"], order=b["so"], x=st.x, z=st.z)
        self.emit("RFID_ASSOCIATED", f"Barcode {b['barcode']} ↔ RFID EPC {b['epc']} associated at packing station",
                  "info", bundle=b["id"], epc=b["epc"], x=st.x, z=st.z, rfid=True)
        self.request_putaway(b)
        return b

    def request_putaway(self, b: dict, prefer: str | None = None, strict: bool = False, src_ep=None) -> dict | None:
        dst = self.choose_putaway_stack(b)
        if dst is None:
            if b["id"] not in self._awaiting_location:
                self._awaiting_location.append(b["id"])
                self.emit("NO_LOCATION", f"No storage location available for {b['barcode']} — will retry", "warning",
                          bundle=b["id"])
            return None
        self.incoming[dst] += 1
        level = len(self.stack_bundles[dst]) + self.incoming[dst]
        code = self.layout.stacks[dst].location_code(level)
        req = {"id": self._id("task", "RQ"), "type": "PUTAWAY", "bundle": b["id"], "dst": dst, "order": None,
               "prefer": prefer, "strict": strict, "created": self.t, "prio": 2, "src_ep": src_ep}
        self.queue.append(req)
        self.emit("LOCATION_ASSIGNED", f"Putaway engine assigned {code} to {b['barcode']}", "info",
                  bundle=b["id"], location=code, stack=dst)
        return req

    # ============================================================ orders & picking
    def eligible_orders(self) -> list[dict]:
        out = []
        for o in self.orders.values():
            if o["status"] != "BOOKED" or not o["bundles"]:
                continue
            if len(o["bundles"]) < o["lines"][0]["qty_bundles"]:
                continue
            if all(self.bundles[b]["status"] == "STORED" and self.bundles[b]["loc"]["kind"] == "stack"
                   for b in o["bundles"]):
                out.append(o)
        return sorted(out, key=lambda o: o["order_number"])

    def release_order(self, number: str | None = None) -> dict:
        if number:
            o = self.orders.get(number)
            if o is None or o not in self.eligible_orders():
                raise ValueError(f"{number} is not available for release")
        else:
            el = self.eligible_orders()
            if not el:
                raise ValueError("No booked order has all bundles in stock")
            o = el[0]
        o["status"] = "RELEASED"
        o["released_at"] = self.ts()
        for bid in o["bundles"]:
            self.bundles[bid]["reserved"] = o["order_number"]
        self.kpi["orders_released"] += 1
        self.oracle.pick_release_message(o, self.now())
        self.emit("ORDER_RECEIVED", f"Oracle order {o['order_number']} received (pick release) — {o['customer']}, "
                  f"{len(o['bundles'])} bundles of {o['lines'][0]['description']}", "info", order=o["order_number"])
        locs = []
        buried = 0
        for bid in o["bundles"]:
            b = self.bundles[bid]
            sb = self.stack_bundles[b["loc"]["stack"]]
            above = len(sb) - sb.index(bid) - 1
            buried += 1 if above else 0
            locs.append(self.loc_info(b)["code"])
        self.emit("ORDER_ALLOCATED", f"Identified {len(locs)} bundles for {o['order_number']}: " + ", ".join(locs)
                  + (f" — {buried} buried, rehandle required" if buried else ""), "success", order=o["order_number"])
        if self.db is not None:
            self.db.order(o)
        return o

    def start_picking(self, number: str | None = None, prefer_first: str | None = None) -> dict:
        cands = [o for o in self.orders.values() if o["status"] == "RELEASED"]
        if number:
            cands = [o for o in cands if o["order_number"] == number]
        if not cands:
            raise ValueError("No released order waiting for picking")
        o = sorted(cands, key=lambda x: x["order_number"])[0]
        lane = next((ln for ln, own in self.lane_owner.items() if own is None
                     and not any(self.stack_bundles[s] or self.incoming[s] for s in self.layout.lanes[ln])), None)
        if lane is None:
            raise ValueError("All dispatch staging lanes are occupied")
        self.lane_owner[lane] = o["order_number"]
        o["lane"] = lane
        o["status"] = "PICKING"
        # top-most bundles first so the order never rehandles its own bundles
        def height(bid):
            b = self.bundles[bid]
            return -b["loc"].get("level", 0)
        for i, bid in enumerate(sorted(o["bundles"], key=height)):
            self.queue.append({"id": self._id("task", "RQ"), "type": "PICK", "bundle": bid, "order": o["order_number"],
                               "prefer": prefer_first if i == 0 else None, "strict": bool(prefer_first and i == 0),
                               "created": self.t + i * 0.01, "prio": 1, "dst": None})
        self.emit("PICKING_STARTED", f"Picking engine created {len(o['bundles'])} pick tasks for {o['order_number']} "
                  f"→ staging {lane}", "info", order=o["order_number"], lane=lane)
        if self.db is not None:
            self.db.order(o)
        return o

    # ============================================================ dispatcher
    def _idle_forklifts(self, role: str) -> list[Forklift]:
        return [f for f in self.forklifts.values() if f.role == role and f.job is None]

    def _pick_forklift(self, req: dict, role: str, near: tuple) -> Forklift | None:
        idle = self._idle_forklifts(role)
        if req.get("prefer"):
            pf = self.forklifts.get(req["prefer"])
            if pf in idle:
                return pf
            if req.get("strict") or self.t - req["created"] < 20:
                return None
        if not idle:
            return None
        return min(idle, key=lambda f: math.hypot(f.x - near[0], f.z - near[1]))

    def _new_task(self, ttype: str, bid: str, src: tuple, dst: tuple, order: str | None, note: str = "") -> dict:
        task = {"id": self._id("task", "T-", 5), "type": ttype, "status": "ASSIGNED", "bundle": bid, "order": order,
                "src": src, "dst": dst, "forklift": None, "created": self.t, "started": None, "finished": None,
                "distance": 0.0, "path": [], "from_code": None,
                "to_code": None, "note": note}
        self.tasks[task["id"]] = task
        return task

    def _assign_job(self, f: Forklift, tasks: list[dict], locks: list[tuple], created: float | None = None):
        jid = self._id("job", "J", 5)
        for ep in locks:
            self.locks[self.lock_key(ep)] = jid
        for t in tasks:
            t["forklift"] = f.id
            t["job"] = jid
            if created is not None:
                t["created"] = created
        f.job = deque(tasks)
        f.job_id = jid
        f.job_locks = [self.lock_key(ep) for ep in locks]
        f.actions.clear()
        f.at_park = False
        first = tasks[0]
        b = self.bundles[first["bundle"]]
        kinds = " + ".join(dict.fromkeys(t["type"] for t in tasks))
        self.emit("TASK_ASSIGNED", f"{f.id} assigned {kinds} for {b['barcode']} ({self.ep_label(first['src'])} → "
                  f"{self.ep_label(tasks[-1]['dst'])})", "info", forklift=f.id, bundle=first["bundle"],
                  order=tasks[-1]["order"], task=first["id"], task_type=tasks[-1]["type"])
        self._start_next_task(f)

    def _try_assign(self, req: dict) -> bool:
        b = self.bundles.get(req["bundle"])
        if b is None:
            return True  # stale request
        if b["loc"]["kind"] != "stack":
            return b["loc"]["kind"] != "forklift"  # wait while it is being rehandled
        src = ("S", b["loc"]["stack"])
        if self.locked(src):
            return False
        sgeom = self.ep_geom(src)
        if req["type"] == "PUTAWAY":
            dst = ("S", req["dst"])
            if self.locked(dst):
                return False
            f = self._pick_forklift(req, "PUTAWAY", sgeom["pre"])
            if f is None:
                return False
            t = self._new_task("PUTAWAY", b["id"], src, dst, None)
            self._assign_job(f, [t], [src, dst], req["created"])
            return True
        if req["type"] == "PICK":
            o = self.orders[req["order"]]
            lane = [("S", s) for s in self.layout.lanes[o["lane"]]]
            free = [ep for ep in lane if not self.locked(ep)
                    and len(self.ep_list(ep)) + self.incoming[ep[1]] < self.ep_max(ep)]
            if not free:
                return False
            f = self._pick_forklift(req, "PICKING", sgeom["pre"])
            if f is None:
                return False
            sb = self.stack_bundles[src[1]]
            blockers = list(reversed(sb[sb.index(b["id"]) + 1:]))
            plan = {}
            targets = []
            for blk in blockers:
                r = self.choose_relocation_stack(src[1], plan, self.bundles[blk]["so"])
                if r is None:
                    return False
                plan[r] = plan.get(r, 0) + 1
                targets.append(r)
            dst = min(free, key=lambda ep: len(self.ep_list(ep)) + self.incoming[ep[1]])
            tasks = []
            for blk, r in zip(blockers, targets):
                self.incoming[r] += 1
                tasks.append(self._new_task("RELOCATE", blk, src, ("S", r), o["order_number"],
                                            note=f"Rehandle: unblock {b['barcode']}"))
            self.incoming[dst[1]] += 1
            tasks.append(self._new_task("PICK", b["id"], src, dst, o["order_number"]))
            locks = [src, dst] + [("S", r) for r in dict.fromkeys(targets)]
            if blockers:
                self.emit("REHANDLE", f"{b['barcode']} is under {len(blockers)} bundle(s) in {src[1]} — "
                          f"{f.id} will relocate them first", "warning", bundle=b["id"], order=o["order_number"],
                          forklift=f.id)
            self._assign_job(f, tasks, locks, req["created"])
            return True
        return True

    def _dispatch(self):
        for bid in list(self._awaiting_location):
            self._awaiting_location.remove(bid)
            self.request_putaway(self.bundles[bid])
        for req in sorted(self.queue, key=lambda r: (r["prio"], r["created"])):
            if self._try_assign(req):
                self.queue.remove(req)
        for o in list(self.orders.values()):
            if o["status"] in ("LOADING",) and o.get("truck"):
                self._dispatch_loading(o)
        for f in self.forklifts.values():
            if f.job is None and not f.at_park and not f.actions and self.t - f.idle_since > 12:
                self._send_home(f)

    # ============================================================ forklift actions
    def _plan(self, f: Forklift, node: str, final: list[tuple]) -> dict:
        lay = self.layout
        starts = [f.node] + ([f.next_node] if f.next_node and f.next_node != f.node else [])
        best = None
        for s in starts:
            r = lay.route(s, node)
            pts = [lay.nodes[n] for n in r]
            d = math.hypot(pts[0][0] - f.x, pts[0][1] - f.z) + sum(
                math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(pts, pts[1:]))
            if best is None or d < best[0]:
                best = (d, r)
        route = best[1]
        pts = [lay.nodes[n] for n in route] + final
        nodes = list(route) + [None] * len(final)
        out_p, out_n = [], []
        for p, n in zip(pts, nodes):
            last = out_p[-1] if out_p else (f.x, f.z)
            if math.hypot(p[0] - last[0], p[1] - last[1]) < 0.05:
                if n and out_n:
                    out_n[-1] = n
                elif n:
                    f.node = n
                continue
            out_p.append(p)
            out_n.append(n)
        return {"k": "move", "pts": out_p, "nodes": out_n, "i": 0, "rev": False,
                "speed": SPEED_LOADED if f.load else SPEED_EMPTY}

    def _goto_ep(self, f: Forklift, ep: tuple) -> list:
        g = self.ep_geom(ep)
        f.dest = {"x": g["pre"][0], "z": g["pre"][1], "label": self.ep_label(ep)}
        return [self._plan(f, g["node"], [g["pre"]])]

    def _send_home(self, f: Forklift):
        p = f.park
        f.state = "RETURNING"
        f.dest = {"x": p["x"], "z": p["z"], "label": f"Parking {p['id']}"}
        f.actions = deque([
            {"k": "expand", "fn": lambda: [self._plan(f, p["node"], [(p["x"], p["z"])])]},
            {"k": "turn", "h": p["heading"]},
            {"k": "call", "fn": lambda: self._parked(f)},
        ])

    def _parked(self, f: Forklift):
        f.at_park = True
        f.state = "IDLE"
        f.dest = None

    def _start_next_task(self, f: Forklift):
        if not f.job:
            self._finish_job(f)
            return
        task = f.job[0]
        f.task = task
        src, dst = task["src"], task["dst"]
        f.actions = deque([
            {"k": "call", "fn": lambda: self._task_started(f, task)},
            {"k": "expand", "fn": lambda: self._goto_ep(f, src)},
            {"k": "call", "fn": lambda: self._at_source(f, task)},
            {"k": "expand", "fn": lambda: self._pick_seq(f, task, src)},
            {"k": "expand", "fn": lambda: self._goto_ep(f, dst)},
            {"k": "call", "fn": lambda: self._at_dest(f, task)},
            {"k": "expand", "fn": lambda: self._place_seq(f, task, dst)},
            {"k": "call", "fn": lambda: self._task_finished(f, task)},
        ])

    def _task_started(self, f: Forklift, task: dict):
        task["status"] = "IN_PROGRESS"
        task["started"] = self.t
        task["_d0"] = f.distance
        task["from_code"] = self.ep_code(task["src"], self._level_of(task["bundle"]))
        f.track = [(round(f.x, 2), round(f.z, 2))]
        f.state = "TO_PICKUP"
        self._persist_task(task)

    def _level_of(self, bid: str) -> int | None:
        loc = self.bundles[bid]["loc"]
        return loc.get("level")

    def _at_source(self, f: Forklift, task: dict):
        f.state = "PICKING_UP"
        self.emit("FORKLIFT_AT_SOURCE", f"{f.id} arrived at {self.ep_label(task['src'])}", "info", forklift=f.id,
                  bundle=task["bundle"], order=task["order"], task=task["id"], task_type=task["type"])

    def _at_dest(self, f: Forklift, task: dict):
        f.state = "PLACING"
        self.emit("FORKLIFT_AT_DESTINATION", f"{f.id} arrived at {self.ep_label(task['dst'])}", "info",
                  forklift=f.id, bundle=task["bundle"], order=task["order"], task=task["id"], task_type=task["type"])

    def _pick_seq(self, f: Forklift, task: dict, ep: tuple) -> list:
        g = self.ep_geom(ep)
        lst = self.ep_list(ep)
        if task["bundle"] not in lst:
            self._abort_task(f, task, "bundle no longer at source")
            return []
        level = lst.index(task["bundle"]) + 1
        bottom = L.level_bottom(level, g["base"])
        return [
            {"k": "turn", "h": g["heading"]},
            {"k": "fork", "h": bottom - 0.06},
            {"k": "move", "pts": [g["app"]], "nodes": [None], "i": 0, "rev": False, "speed": SPEED_APPROACH},
            {"k": "call", "fn": lambda: self._attach(f, task, ep, level)},
            {"k": "fork", "h": bottom + 0.1},
            {"k": "move", "pts": [g["pre"]], "nodes": [None], "i": 0, "rev": True, "speed": SPEED_APPROACH},
            {"k": "fork", "h": CARRY_H},
        ]

    def _place_seq(self, f: Forklift, task: dict, ep: tuple) -> list:
        g = self.ep_geom(ep)
        level = len(self.ep_list(ep)) + 1
        bottom = L.level_bottom(level, g["base"])
        return [
            {"k": "turn", "h": g["heading"]},
            {"k": "fork", "h": bottom + 0.06},
            {"k": "move", "pts": [g["app"]], "nodes": [None], "i": 0, "rev": False, "speed": SPEED_APPROACH},
            {"k": "fork", "h": bottom - 0.06},
            {"k": "call", "fn": lambda: self._detach(f, task, ep)},
            {"k": "move", "pts": [g["pre"]], "nodes": [None], "i": 0, "rev": True, "speed": SPEED_APPROACH},
            {"k": "fork", "h": LOW_H},
        ]

    def _attach(self, f: Forklift, task: dict, ep: tuple, level: int):
        b = self.bundles[task["bundle"]]
        lst = self.ep_list(ep)
        if b["id"] in lst:
            lst.remove(b["id"])
        code = self.ep_code(ep, level)
        b["loc"] = {"kind": "forklift", "forklift": f.id}
        b["status"] = "IN_TRANSIT"
        f.load = b["id"]
        f.state = "TO_DROP"
        self.inv_version += 1
        self.kpi["rfid_reads"] += 1
        if ep[0] == "S" and self.db is not None:
            self.db.level(ep[1], level, None, len(lst))
        if ep[0] == "T":
            self.trucks[ep[1]]["epcs_on_board"] = self._truck_epcs(ep[1])
        self._persist_bundle_loc(b)
        self._movement("PICKUP", b, f, task, code)
        self.emit("RFID_READ", f"{f.id} fork reader confirmed EPC {b['epc'][-8:]} ({b['barcode']})", "info",
                  forklift=f.id, bundle=b["id"], epc=b["epc"], x=f.x, z=f.z, rfid=True)
        self.emit("BUNDLE_PICKED", f"{f.id} picked {b['barcode']} from {code}", "info", forklift=f.id, bundle=b["id"],
                  order=task["order"], task=task["id"], task_type=task["type"], location=code)
        self.emit("STACK_UPDATED", f"{self.ep_label(ep)} now holds {len(lst)} bundle(s)", "info", bundle=b["id"],
                  stack=ep[1] if ep[0] == "S" else None, op="pick", forklift=f.id, order=task["order"],
                  task_type=task["type"])

    def _detach(self, f: Forklift, task: dict, ep: tuple):
        b = self.bundles[task["bundle"]]
        lst = self.ep_list(ep)
        lst.append(b["id"])
        level = len(lst)
        code = self.ep_code(ep, level)
        f.load = None
        if ep[0] == "S":
            self.incoming[ep[1]] = max(0, self.incoming[ep[1]] - 1)
            st = self.layout.stacks[ep[1]]
            b["loc"] = {"kind": "stack", "stack": ep[1], "level": level}
            b["status"] = "STAGED" if st.kind == "STAGING" else "STORED"
            if self.db is not None:
                self.db.level(ep[1], level, b["id"], level)
        else:
            tr = self.trucks[ep[1]]
            tr["incoming"][ep[2]] = max(0, tr["incoming"][ep[2]] - 1)
            b["loc"] = {"kind": "truck", "truck": ep[1], "col": ep[2], "level": level}
            b["status"] = "LOADED"
            tr["epcs_on_board"] = self._truck_epcs(ep[1])
        b["last_move"] = {"type": task["type"], "ts": self.ts(), "from": task.get("from_code"), "to": code,
                          "forklift": f.id, "task": task["id"]}
        task["to_code"] = code
        self.inv_version += 1
        self._persist_bundle_loc(b)
        self._movement("PLACE", b, f, task, code)
        self.emit("BUNDLE_PLACED", f"{f.id} placed {b['barcode']} at {code}", "success", forklift=f.id,
                  bundle=b["id"], order=task["order"], task=task["id"], task_type=task["type"], location=code)
        self.emit("STACK_UPDATED", f"Twin updated: {b['barcode']} → {code}", "info", bundle=b["id"],
                  stack=ep[1] if ep[0] == "S" else None, op="place", forklift=f.id, order=task["order"],
                  task_type=task["type"])
        o = self.orders.get(task["order"]) if task["order"] else None
        if task["type"] == "PICK" and o:
            self.oracle.move_order_message(o, b, self.now(), task["from_code"], code)
            self.emit("BUNDLE_STAGED", f"{b['barcode']} staged in {o.get('lane')} for {o['order_number']}", "success",
                      bundle=b["id"], order=o["order_number"], forklift=f.id)
            if all(self.bundles[x]["status"] == "STAGED" for x in o["bundles"]):
                o["status"] = "STAGED"
                o["staged_at"] = self.ts()
                self.kpi["orders_staged"] += 1
                if o.get("released_at"):
                    rel = (datetime.fromisoformat(o["staged_at"]) - datetime.fromisoformat(o["released_at"])).total_seconds()
                    self.cycle["ORDER"].append(rel)
                self.emit("ORDER_STAGED", f"{o['order_number']} fully staged in {o['lane']} — ready for dispatch",
                          "success", order=o["order_number"])
                if self.db is not None:
                    self.db.order(o)
        if task["type"] == "LOAD":
            self.emit("BUNDLE_LOADED", f"{b['barcode']} loaded on truck {ep[1]} ({code})",
                      "warning" if task.get("wrong") else "success", bundle=b["id"], order=task["order"],
                      truck=ep[1], forklift=f.id)
        if task["type"] == "UNLOAD":
            b["reserved"] = None

    def _movement(self, kind: str, b: dict, f: Forklift, task: dict, code: str):
        if self.db is not None:
            self.db.movement({"ts": self.ts(), "event_type": kind, "bundle_id": b["id"], "forklift_id": f.id,
                              "task_id": task["id"], "location_code": code, "x": round(f.x, 2), "z": round(f.z, 2)})

    def _persist_task(self, task: dict):
        if self.db is None:
            return
        self.db.task({
            "id": task["id"], "type": task["type"], "status": task["status"], "bundle_id": task["bundle"],
            "sales_order": task["order"], "forklift_id": task["forklift"], "from_code": task.get("from_code"),
            "to_code": task.get("to_code"), "created_at": iso(SIM_START + timedelta(seconds=task["created"])),
            "started_at": iso(SIM_START + timedelta(seconds=task["started"])) if task["started"] is not None else None,
            "finished_at": iso(SIM_START + timedelta(seconds=task["finished"])) if task["finished"] is not None else None,
            "distance_m": round(task["distance"], 1), "path": task["path"],
        })

    def _task_finished(self, f: Forklift, task: dict):
        task["status"] = "DONE"
        task["finished"] = self.t
        task["distance"] = f.distance - task.get("_d0", f.distance)
        f.track.append((round(f.x, 2), round(f.z, 2)))
        task["path"] = f.track
        f.track = []
        f.tasks_done += 1
        b = self.bundles[task["bundle"]]
        f.history.appendleft({"task": task["id"], "type": task["type"], "bundle": b["id"], "barcode": b["barcode"],
                              "from": task.get("from_code"), "to": task.get("to_code"), "order": task["order"],
                              "start": iso(SIM_START + timedelta(seconds=task["started"])),
                              "end": self.ts(), "duration_s": round(task["finished"] - task["started"], 1),
                              "distance_m": round(task["distance"], 1)})
        key = {"PUTAWAY": "putaways", "PICK": "picks", "RELOCATE": "relocations", "LOAD": "loads",
               "UNLOAD": "unloads"}[task["type"]]
        self.kpi[key] += 1
        if task["type"] in self.cycle:
            self.cycle[task["type"]].append(task["finished"] - task["created"])
        self._persist_task(task)
        self.emit("TASK_COMPLETED", f"{f.id} completed {task['type']} {task['id']} in "
                  f"{task['finished'] - task['started']:.0f}s ({task['distance']:.0f} m)", "info", forklift=f.id,
                  task=task["id"], bundle=b["id"], order=task["order"], task_type=task["type"])
        if task["type"] in ("LOAD", "UNLOAD") and task["order"] in self.orders:
            o = self.orders[task["order"]]
            o["active_loads"] = max(0, o.get("active_loads", 0) - 1)
        self._trim_tasks()
        f.job.popleft()
        f.task = None
        self._start_next_task(f)

    def _abort_task(self, f: Forklift, task: dict, reason: str):
        task["status"] = "CANCELLED"
        self.emit("TASK_CANCELLED", f"{task['id']} cancelled: {reason}", "warning", forklift=f.id, task=task["id"])
        f.job = deque()
        f.actions.clear()
        self._finish_job(f)

    def _finish_job(self, f: Forklift):
        for k in getattr(f, "job_locks", []):
            if self.locks.get(k) == f.job_id:
                del self.locks[k]
        f.job_locks = []
        f.job = None
        f.job_id = None
        f.task = None
        f.state = "IDLE"
        f.dest = None
        f.idle_since = self.t

    def _trim_tasks(self):
        if len(self.tasks) > 800:
            done = [t for t in self.tasks.values() if t["status"] in ("DONE", "CANCELLED")]
            for t in sorted(done, key=lambda t: t["finished"] or 0)[:200]:
                del self.tasks[t["id"]]

    def _exec(self, f: Forklift, a: dict, dt: float) -> float:
        k = a["k"]
        if k == "call":
            a["done"] = True
            a["fn"]()
            return 0.0
        if k == "expand":
            a["done"] = True
            a["result"] = a["fn"]() or []
            return 0.0
        if k == "wait":
            use = min(dt, a["t"])
            a["t"] -= use
            a["done"] = a["t"] <= 1e-9
            return use
        if k == "fork":
            d = a["h"] - f.fork
            step = FORK_SPEED * dt
            if abs(d) <= step:
                f.fork = a["h"]
                a["done"] = True
                return abs(d) / FORK_SPEED
            f.fork += math.copysign(step, d)
            return dt
        if k == "turn":
            d = angdiff(a["h"], f.heading)
            step = TURN_RATE * dt
            if abs(d) <= step:
                f.heading = a["h"]
                a["done"] = True
                return abs(d) / TURN_RATE
            f.heading += math.copysign(step, d)
            return dt
        if k == "move":
            used = 0.0
            pts, nodes = a["pts"], a["nodes"]
            while used < dt - 1e-9 and a["i"] < len(pts):
                tx, tz = pts[a["i"]]
                dx, dz = tx - f.x, tz - f.z
                dist = math.hypot(dx, dz)
                f.next_node = nodes[a["i"]]
                if dist < 1e-3:
                    if nodes[a["i"]]:
                        f.node = nodes[a["i"]]
                    f.track.append((round(tx, 2), round(tz, 2)))
                    a["i"] += 1
                    continue
                if not a["rev"]:
                    want = L.heading_of(dx, dz)
                    diff = angdiff(want, f.heading)
                    if abs(diff) > 0.12:
                        rot = min(abs(diff), TURN_RATE * (dt - used))
                        f.heading += math.copysign(rot, diff)
                        used += rot / TURN_RATE
                        if abs(diff) > 0.5:
                            continue
                    else:
                        f.heading = want
                rem = dt - used
                if rem <= 1e-9:
                    break
                step = min(dist, a["speed"] * rem)
                f.x += dx / dist * step
                f.z += dz / dist * step
                f.distance += step
                used += step / a["speed"]
            if a["i"] >= len(pts):
                a["done"] = True
                f.next_node = None
            return used
        a["done"] = True
        return 0.0

    def _step_forklift(self, f: Forklift, dt: float):
        rem = dt
        guard = 0
        while rem > 1e-9 and f.actions and guard < 50:
            guard += 1
            a = f.actions[0]
            used = self._exec(f, a, rem)
            rem -= used
            if a.get("done"):
                if f.actions and f.actions[0] is a:
                    f.actions.popleft()
                if a["k"] == "expand":
                    f.actions.extendleft(reversed(a["result"]))
        if f.job is not None:
            f.busy_time += dt
            f.battery = max(18.0, f.battery - dt * 0.0012)
        elif f.at_park:
            f.battery = min(100.0, f.battery + dt * 0.002)

    # ============================================================ trucks & gate
    def _truck_epcs(self, tid: str) -> list:
        tr = self.trucks[tid]
        return [self.bundles[b]["epc"] for col in tr["slots"] for b in col]

    def dock_busy(self) -> dict | None:
        return next((t for t in self.trucks.values() if t["state"] in ACTIVE_TRUCK_STATES), None)

    def dispatch_order(self, number: str | None = None) -> dict:
        busy = self.dock_busy()
        if busy:
            raise ValueError(f"Dock 1 is occupied by truck {busy['id']} ({busy['state']})")
        cands = [o for o in self.orders.values() if o["status"] == "STAGED"]
        if number:
            cands = [o for o in cands if o["order_number"] == number]
        if not cands:
            raise ValueError("No staged order ready for dispatch")
        o = sorted(cands, key=lambda x: x["order_number"])[0]
        tid = self._id("truck", "TRK-", 2)
        letters = "".join(self.rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(2))
        tr = {"id": tid, "plate": f"KA-{self.rng.randint(1, 60):02d}-{letters}-{self.rng.randint(1000, 9999)}",
              "carrier": o["carrier"], "order": o["order_number"], "state": "ARRIVING",
              "x": L.TRUCK_ENTRY[0], "z": L.TRUCK_ENTRY[1], "heading": L.DOCK["heading"],
              "path": [(L.DOCK["x"], L.DOCK["z"])], "rev": False, "on_arrive": "dock",
              "slots": [[] for _ in L.TRUCK_COLS], "incoming": [0 for _ in L.TRUCK_COLS], "arrived": self.t,
              "epcs_on_board": [], "manifest": None}
        self.trucks[tid] = tr
        o["status"] = "LOADING"
        o["truck"] = tid
        o["active_loads"] = 0
        o.setdefault("inject_wrong", False)
        o.setdefault("inject_missing", False)
        self.emit("TRUCK_INBOUND", f"Truck {tr['plate']} ({o['carrier']}) entering yard for {o['order_number']}",
                  "info", truck=tid, order=o["order_number"])
        if self.db is not None:
            self.db.order(o)
        return tr

    def _truck_arrived(self, tr: dict):
        cb = tr.get("on_arrive")
        tr["on_arrive"] = None
        o = self.orders.get(tr["order"])
        if cb == "dock":
            tr["state"] = "AT_DOCK"
            self._seq["manifest"] += 1
            mid = f"DM-{o['order_number'][3:]}-{self._seq['manifest']}"
            mf = {"id": mid, "order_number": o["order_number"], "truck_id": tr["id"], "truck_plate": tr["plate"],
                  "delivery_id": f"WSH-{self.rng.randint(7000000, 7999999)}",
                  "expected_epcs": [self.bundles[b]["epc"] for b in o["bundles"]],
                  "expected_barcodes": [self.bundles[b]["barcode"] for b in o["bundles"]],
                  "expected_bundles": list(o["bundles"]), "status": "LOADING", "created_at": self.ts(),
                  "validated_at": None, "result": None, "reads": []}
            self.manifests[mid] = mf
            tr["manifest"] = mid
            o["manifest"] = mid
            self.emit("TRUCK_ARRIVED", f"Truck {tr['plate']} docked at DOCK-1 for {o['order_number']}", "info",
                      truck=tr["id"], order=o["order_number"])
            self.emit("MANIFEST_CREATED", f"Dispatch manifest {mid}: {len(mf['expected_epcs'])} bundles expected "
                      f"({', '.join(mf['expected_barcodes'])})", "info", order=o["order_number"], manifest=mid,
                      truck=tr["id"])
            self.emit("LOADING_STARTED", f"Picking forklifts sent to dispatch: loading {o['order_number']}", "info",
                      order=o["order_number"], truck=tr["id"])
            if self.db is not None:
                self.db.manifest(mf)
        elif cb == "gate":
            tr["state"] = "READING"
            self.gate.update(state="READING", truck=tr["id"], reads=[], t=self.t, result=None)
            self.after(2.5, lambda: self._gate_reconcile(tr))
            mf = self.manifests[tr["manifest"]]
            for col in tr["slots"]:
                for bid in col:
                    b = self.bundles[bid]
                    rd = {"epc": b["epc"], "bundle": bid, "barcode": b["barcode"], "rssi": round(self.rng.uniform(-63, -41), 1),
                          "antenna": self.rng.randint(1, 4), "count": self.rng.randint(3, 14), "ts": self.ts()}
                    self.gate["reads"].append(rd)
                    mf["reads"].append(rd)
                    self.kpi["rfid_reads"] += 1
                    if self.db is not None:
                        self.db.dispatch_event({"manifest_id": mf["id"], "ts": self.ts(), "event_type": "READ",
                                                "epc": b["epc"], "bundle_id": bid, "detail": rd})
            self.emit("GATE_READ", f"RFID gate GATE-01 reading truck {tr['plate']}: {len(self.gate['reads'])} EPCs "
                      "detected", "info", truck=tr["id"], order=tr["order"], x=L.GATE["x"], z=L.GATE["z"], rfid=True)
            self.emit("GATE_READ_COMPLETE", f"Gate read complete — {len(self.gate['reads'])} unique EPCs",
                      "info", truck=tr["id"], order=tr["order"])
        elif cb == "hold":
            pass
        elif cb == "exit":
            tr["state"] = "DEPARTED"
            for col in tr["slots"]:
                for bid in col:
                    b = self.bundles[bid]
                    b["loc"] = {"kind": "dispatched", "truck": tr["id"]}
                    b["status"] = "DISPATCHED"
                    self._persist_bundle_loc(b)
            self.inv_version += 1
            self.cycle["TRUCK"].append(self.t - tr["arrived"])
            self.emit("TRUCK_DEPARTED", f"Truck {tr['plate']} departed with {o['order_number']}", "success",
                      truck=tr["id"], order=o["order_number"])
            self.trucks.pop(tr["id"], None)
        elif cb == "redock":
            tr["state"] = "AT_DOCK"
            o["status"] = "LOADING"
            self.gate.update(state="IDLE", truck=None)
            self.emit("TRUCK_REDOCKED", f"Truck {tr['plate']} back at DOCK-1 for correction", "info",
                      truck=tr["id"], order=o["order_number"])
            for ci, col in enumerate(tr["slots"]):
                for bid in list(col):
                    if self.bundles[bid]["reserved"] != o["order_number"]:
                        self._request_unload(tr, ci, bid)
            for bid in o["bundles"]:
                self.bundles[bid]["left_behind"] = False

    def _request_unload(self, tr: dict, col: int, bid: str):
        b = self.bundles[bid]
        dst = self.choose_putaway_stack(b)
        if dst is None:
            return
        self.incoming[dst] += 1
        tr.setdefault("unloads", []).append({"bundle": bid, "col": col, "dst": dst})

    def _dispatch_loading(self, o: dict):
        tr = self.trucks.get(o["truck"])
        if tr is None or tr["state"] != "AT_DOCK":
            return
        # corrective unloads first
        for u in list(tr.get("unloads", [])):
            src = ("T", tr["id"], u["col"])
            dst = ("S", u["dst"])
            if self.locked(src) or self.locked(dst):
                continue
            idle = self._idle_forklifts("PICKING")
            if not idle:
                return
            f = min(idle, key=lambda f: math.hypot(f.x - L.DOCK["x"], f.z))
            t = self._new_task("UNLOAD", u["bundle"], src, dst, o["order_number"], note="Exception correction")
            o["active_loads"] = o.get("active_loads", 0) + 1
            tr["unloads"].remove(u)
            self._assign_job(f, [t], [src, dst])
        pending = [b for b in o["bundles"] if self.bundles[b]["loc"]["kind"] == "stack"
                   and self.bundles[b]["status"] == "STAGED" and not self.bundles[b]["left_behind"]]
        if o.get("inject_missing") and not o.get("missing_done") and pending:
            # the bottom bundle of a staging stack is the one an operator would overlook
            bottoms = [self.stack_bundles[sid][0] for sid in self.layout.lanes[o["lane"]]
                       if self.stack_bundles[sid] and self.stack_bundles[sid][0] in pending]
            if bottoms:
                bid = bottoms[0]
                self.bundles[bid]["left_behind"] = True
                o["missing_done"] = True
                pending.remove(bid)
                self.emit("OPERATOR_ERROR", f"Simulated error: {self.bundles[bid]['barcode']} will be left behind in "
                          "staging", "warning", bundle=bid, order=o["order_number"])
        for sid in self.layout.lanes[o["lane"]]:
            sb = self.stack_bundles[sid]
            if not sb or self.locked(("S", sid)):
                continue
            top = sb[-1]
            if top not in pending:
                continue
            cols = [c for c in range(len(L.TRUCK_COLS)) if not self.locked(("T", tr["id"], c))
                    and len(tr["slots"][c]) + tr["incoming"][c] < L.TRUCK_LEVELS]
            idle = self._idle_forklifts("PICKING")
            if not cols or not idle:
                break
            c = min(cols, key=lambda c: len(tr["slots"][c]) + tr["incoming"][c])
            st = self.layout.stacks[sid]
            f = min(idle, key=lambda f: math.hypot(f.x - st.pre[0], f.z - st.pre[1]))
            tr["incoming"][c] += 1
            o["active_loads"] = o.get("active_loads", 0) + 1
            t = self._new_task("LOAD", top, ("S", sid), ("T", tr["id"], c), o["order_number"])
            self._assign_job(f, [t], [("S", sid), ("T", tr["id"], c)])
            pending.remove(top)
        if pending or o.get("active_loads") or tr.get("unloads"):
            return
        if o.get("inject_wrong") and not o.get("wrong_done"):
            cands = []
            for s in self.layout.stacks.values():
                sb = self.stack_bundles[s.id]
                if s.kind == "STORAGE" and sb and not self.locked(("S", s.id)) and not self.bundles[sb[-1]]["reserved"]:
                    cands.append(s)
            cols = [c for c in range(len(L.TRUCK_COLS)) if len(tr["slots"][c]) + tr["incoming"][c] < L.TRUCK_LEVELS]
            idle = self._idle_forklifts("PICKING")
            if not cands or not cols or not idle:
                return
            s = min(cands, key=lambda s: math.hypot(s.x - L.DOCK["x"], s.z))
            bid = self.stack_bundles[s.id][-1]
            c = min(cols, key=lambda c: len(tr["slots"][c]))
            f = min(idle, key=lambda f: math.hypot(f.x - s.pre[0], f.z - s.pre[1]))
            tr["incoming"][c] += 1
            o["active_loads"] = o.get("active_loads", 0) + 1
            o["wrong_done"] = True
            t = self._new_task("LOAD", bid, ("S", s.id), ("T", tr["id"], c), o["order_number"],
                               note="Simulated operator error: wrong bundle")
            t["wrong"] = True
            self.emit("OPERATOR_ERROR", f"Simulated error: {f.id} sent to load {self.bundles[bid]['barcode']} "
                      f"({self.bundles[bid]['so']}) onto {tr['id']}", "warning", bundle=bid, order=o["order_number"],
                      forklift=f.id)
            self._assign_job(f, [t], [("S", s.id), ("T", tr["id"], c)])
            return
        o["status"] = "LOADED"
        tr["state"] = "LOADED"
        self.emit("TRUCK_LOADED", f"Truck {tr['plate']} loading complete: {len(self._truck_epcs(tr['id']))} bundles on board",
                  "info", truck=tr["id"], order=o["order_number"])
        if self.db is not None:
            self.db.order(o)
        if self.autopilot or self.auto_gate or (self.scenario and self.scenario.get("id") == 3
                                                and self.scenario["status"] == "RUNNING"):
            self.after(3.0, lambda: self.send_to_gate(tr["id"], quiet=True))

    def send_to_gate(self, tid: str | None = None, quiet: bool = False) -> dict:
        tr = self.trucks.get(tid) if tid else next((t for t in self.trucks.values() if t["state"] == "LOADED"), None)
        if tr is None or tr["state"] != "LOADED":
            if quiet:
                return {}
            raise ValueError("No loaded truck waiting at the dock")
        tr["state"] = "TO_GATE"
        tr["path"] = [(L.GATE["x"], L.GATE["z"])]
        tr["rev"] = False
        tr["on_arrive"] = "gate"
        o = self.orders[tr["order"]]
        o["status"] = "AT_GATE"
        self.emit("TRUCK_TO_GATE", f"Truck {tr['plate']} proceeding to RFID gate GATE-01", "info", truck=tr["id"],
                  order=o["order_number"])
        return tr

    def _gate_reconcile(self, tr: dict):
        o = self.orders[tr["order"]]
        mf = self.manifests[tr["manifest"]]
        actual = set(self._truck_epcs(tr["id"]))
        expected = set(mf["expected_epcs"])
        by_epc = {b["epc"]: b for b in self.bundles.values()}

        def info(epc):
            b = by_epc[epc]
            return {"epc": epc, "bundle": b["id"], "barcode": b["barcode"], "so": b["so"], "customer": b["customer"],
                    "location": self.loc_info(b)["code"]}
        missing = [info(e) for e in sorted(expected - actual)]
        unexpected = [info(e) for e in sorted(actual - expected)]
        ok = not missing and not unexpected
        result = {"ok": ok, "expected": len(expected), "read": len(actual), "matched": len(expected & actual),
                  "missing": missing, "unexpected": unexpected, "ts": self.ts()}
        mf["result"] = result
        self.kpi["gate_validations"] += 1
        self.gate.update(state="AUTHORIZED" if ok else "EXCEPTION", result=result)
        self.emit("RECONCILED", f"Manifest {mf['id']}: expected {len(expected)}, read {len(actual)}, matched "
                  f"{len(expected & actual)}", "info", order=o["order_number"], truck=tr["id"], manifest=mf["id"])
        if self.db is not None:
            self.db.dispatch_event({"manifest_id": mf["id"], "ts": self.ts(), "event_type": "RECONCILE", "epc": None,
                                    "bundle_id": None, "detail": result})
        if ok:
            first_pass = not o.get("had_exception")
            if first_pass:
                self.kpi["first_pass_ok"] += 1
            mf["status"] = "VALIDATED"
            mf["validated_at"] = self.ts()
            o["status"] = "DISPATCHED"
            o["dispatched_at"] = self.ts()
            self.kpi["trucks_dispatched"] += 1
            self.kpi["bundles_dispatched"] += len(actual)
            for col in tr["slots"]:
                for bid in col:
                    self.bundles[bid]["status"] = "DISPATCHED"
            self.lane_owner[o["lane"]] = None
            tr["state"] = "AUTHORIZED"
            tr["path"] = [L.TRUCK_HOLD, L.TRUCK_EXIT]
            tr["on_arrive"] = "exit"
            self.oracle.ship_confirm_message(o, mf, self.now())
            self.emit("DISPATCH_VALIDATED", f"Dispatch AUTHORIZED: all {len(expected)} bundles of {o['order_number']} "
                      f"verified by RFID — Oracle ship confirm sent", "success", order=o["order_number"],
                      truck=tr["id"], manifest=mf["id"])
            self.after(6.0, lambda: self.gate.update(state="IDLE", truck=None) if self.gate.get("truck") == tr["id"] else None)
        else:
            o["had_exception"] = True
            o["status"] = "EXCEPTION"
            mf["status"] = "EXCEPTION"
            tr["state"] = "EXCEPTION"
            tr["path"] = [L.TRUCK_HOLD]
            tr["on_arrive"] = "hold"
            self.kpi["exceptions"] += 1
            exc = {"id": self._id("exc", "EX-", 4), "order": o["order_number"], "truck": tr["id"], "plate": tr["plate"],
                   "manifest": mf["id"], "missing": missing, "unexpected": unexpected, "ts": self.ts(), "t": self.t,
                   "resolved": False}
            self.exceptions.append(exc)
            self.oracle.exception_message(o, mf, result, self.now())
            parts = []
            if missing:
                parts.append(f"{len(missing)} missing ({', '.join(m['barcode'] for m in missing)})")
            if unexpected:
                parts.append(f"{len(unexpected)} unexpected ({', '.join(u['barcode'] + ' / ' + u['so'] for u in unexpected)})")
            self.emit("DISPATCH_EXCEPTION", f"Dispatch BLOCKED for {o['order_number']}: " + "; ".join(parts),
                      "error", order=o["order_number"], truck=tr["id"], exception=exc["id"])
        if self.db is not None:
            self.db.manifest(mf)
            self.db.order(o)

    def resolve_exception(self, exc_id: str | None = None) -> dict:
        open_ = [e for e in self.exceptions if not e["resolved"]]
        if exc_id:
            open_ = [e for e in open_ if e["id"] == exc_id]
        if not open_:
            raise ValueError("No open dispatch exception")
        exc = open_[0]
        tr = self.trucks.get(exc["truck"])
        if tr is None or tr["state"] != "EXCEPTION":
            raise ValueError("Truck is not holding at the gate")
        exc["resolved"] = True
        exc["resolved_at"] = self.ts()
        self.kpi["exceptions_resolved"] += 1
        o = self.orders[exc["order"]]
        o["inject_wrong"] = False
        o["inject_missing"] = False
        tr["state"] = "RETURNING"
        tr["path"] = [(L.DOCK["x"], L.DOCK["z"])]
        tr["rev"] = True
        tr["on_arrive"] = "redock"
        self.auto_gate_once = True
        self.emit("EXCEPTION_RESOLVING", f"Supervisor released {exc['id']}: truck {tr['plate']} returning to dock "
                  "for correction", "warning", order=o["order_number"], truck=tr["id"], exception=exc["id"])
        return exc

    def _step_truck(self, tr: dict, dt: float):
        if not tr["path"]:
            return
        rem = dt
        while rem > 1e-9 and tr["path"]:
            tx, tz = tr["path"][0]
            dx, dz = tx - tr["x"], tz - tr["z"]
            d = math.hypot(dx, dz)
            if d < 1e-3:
                tr["path"].pop(0)
                continue
            if not tr["rev"]:
                tr["heading"] = L.heading_of(dx, dz)
            spd = TRUCK_SPEED if d > 8 else max(1.5, TRUCK_SPEED * d / 8)
            step = min(d, spd * rem)
            tr["x"] += dx / d * step
            tr["z"] += dz / d * step
            rem -= step / spd
        if not tr["path"]:
            tr["rev"] = False
            self._truck_arrived(tr)

    # ============================================================ autopilot
    def _autopilot(self):
        if self.t - self._last_auto["tick"] < 4:
            return
        self._last_auto["tick"] = self.t
        active = [o for o in self.orders.values() if o["status"] in ("RELEASED", "PICKING")]
        if len(active) < 3 and self.t - self._last_auto["order"] > 50 and self.eligible_orders():
            self._last_auto["order"] = self.t
            try:
                self.release_order()
            except ValueError:
                pass
        for o in sorted(self.orders.values(), key=lambda o: o["order_number"]):
            if o["status"] == "RELEASED" and self.t - (self._t_of(o["released_at"])) > 6:
                try:
                    self.start_picking(o["order_number"])
                except ValueError:
                    break
        if not self.dock_busy() and any(o["status"] == "STAGED" for o in self.orders.values()):
            try:
                self.dispatch_order()
            except ValueError:
                pass
        for e in self.exceptions:
            if not e["resolved"] and self.t - e["t"] > 18:
                try:
                    self.resolve_exception(e["id"])
                except ValueError:
                    pass

    def _t_of(self, s: str | None) -> float:
        if not s:
            return self.t
        return (datetime.fromisoformat(s) - SIM_START).total_seconds()

    # ============================================================ main loop
    def step(self, real_dt: float):
        if not self.running:
            return
        dt_total = min(real_dt, 0.25) * self.speed
        sub = max(1, math.ceil(dt_total / 0.1))
        dt = dt_total / sub
        for _ in range(sub):
            self.t += dt
            due = [x for x in self._timers if x[0] <= self.t]
            if due:
                self._timers = [x for x in self._timers if x[0] > self.t]
                for _, fn in due:
                    fn()
            if (self.auto_putaway or self.autopilot) and self.t >= self._next_prod:
                fill = self._storage_fill()
                pace = 2.5 if fill > 0.8 else 1.5 if fill > 0.7 else 0.8 if fill < 0.5 else 1.0
                self._next_prod = self.t + self.prod_interval * pace * self.rng.uniform(0.8, 1.25)
                self.produce()
            if self.autopilot:
                self._autopilot()
            if self.t - self._last_dispatch >= 0.5:
                self._last_dispatch = self.t
                self._dispatch()
            for f in self.forklifts.values():
                self._step_forklift(f, dt)
            for tr in list(self.trucks.values()):
                self._step_truck(tr, dt)
            if getattr(self, "auto_gate_once", False):
                lt = next((t for t in self.trucks.values() if t["state"] == "LOADED"), None)
                if lt:
                    self.auto_gate_once = False
                    self.after(2.0, lambda tid=lt["id"]: self.send_to_gate(tid, quiet=True))
            if self.t >= self._next_sample:
                self._sample()
        if self.db is not None and self.t - self._last_pos_persist > 2.0:
            self._last_pos_persist = self.t
            self.db.positions([self._position_row(f) for f in self.forklifts.values()])

    def _storage_fill(self) -> float:
        used = cap = 0
        for st in self.layout.stacks.values():
            if st.kind == "STORAGE" and st.warehouse_id == "WH01":
                cap += st.max_levels
                used += len(self.stack_bundles[st.id]) + self.incoming[st.id]
        return used / cap if cap else 0.0

    def _sample(self):
        self._next_sample = self.t + 30.0
        counts = self.inventory_counts()
        util = [f.busy_time / self.t for f in self.forklifts.values()] if self.t > 1 else [0]
        self.series.append({"t": round(self.t), "clock": self.now().strftime("%H:%M"),
                            "putaways": self.kpi["putaways"], "picks": self.kpi["picks"],
                            "loads": self.kpi["loads"], "dispatched": self.kpi["bundles_dispatched"],
                            "indoor": counts["WH01"], "yard": counts["WH02"], "staging": counts["staging"],
                            "utilization": round(100 * sum(util) / len(util), 1), "exceptions": self.kpi["exceptions"]})
        self.series = self.series[-240:]

    # ============================================================ scenarios
    def _scenario_check(self, ev: dict):
        sc = self.scenario
        if not sc or sc["status"] != "RUNNING":
            return
        while sc["cursor"] < len(sc["steps"]) and self._scn_match[sc["cursor"]](ev):
            st = sc["steps"][sc["cursor"]]
            st["done"] = True
            st["t"] = self.ts()
            st["detail"] = ev["message"]
            if ev["type"] == "DISPATCH_EXCEPTION":
                st["label"] = "Exception raised — dispatch blocked"
                st["error"] = True
            sc["cursor"] += 1
        if sc["cursor"] >= len(sc["steps"]):
            sc["status"] = "DONE"
            sc["finished"] = self.ts()

    def start_scenario(self, sid: int, inject: str | None = None) -> dict:
        def R(**want):
            def m(ev):
                for k, v in want.items():
                    actual = ev["type"] if k == "type" else ev["refs"].get(k)
                    if actual != v:
                        return False
                return True
            return m

        if sid == 1:
            free = [s for s in self.layout.stacks.values() if s.kind == "RECEIVING" and not self.stack_bundles[s.id]]
            if not free:
                raise ValueError("Receiving area is full — wait for putaway forklifts to clear it")
            bid = f"B{self._seq['bundle'] + 1:06d}"
            steps = ["Finished bundle arrives from production", "Bundle barcode and RFID EPC associated",
                     "System assigns a floor-stack location", "Forklift F-01 receives the putaway task",
                     "F-01 moves to the assigned bay and places the bundle", "3D twin updates stack and bundle location"]
            self._scn_match = [R(type="BUNDLE_PRODUCED", bundle=bid), R(type="RFID_ASSOCIATED", bundle=bid),
                               R(type="LOCATION_ASSIGNED", bundle=bid), R(type="TASK_ASSIGNED", bundle=bid, forklift="F-01"),
                               R(type="BUNDLE_PLACED", bundle=bid), R(type="STACK_UPDATED", bundle=bid, op="place")]
            self.scenario = self._scn(1, "Automatic Putaway", steps, {"forklift": "F-01", "bundle": bid})
            self._prefer_next_putaway = "F-01"
            b = self.produce(scenario=True)
            if b is None:
                self.scenario = None
                raise ValueError("Receiving area is full")
            req = next((r for r in self.queue if r["bundle"] == b["id"]), None)
            if req:
                req["prefer"] = "F-01"
                req["strict"] = True
                req["prio"] = 0
            return self.scenario
        if sid == 2:
            target = "SO-45892"
            el = self.eligible_orders()
            o = next((x for x in el if x["order_number"] == target), el[0] if el else None)
            if o is None:
                raise ValueError("No booked order with all bundles in stock")
            n = o["order_number"]
            steps = [f"Oracle order {n} is received", "System identifies the required bundles",
                     "Picking forklift F-05 is assigned", "F-05 navigates to the required stack",
                     "Bundle is picked and stack inventory updated", "Bundle is moved to dispatch staging",
                     f"All bundles of {n} staged — ready for dispatch"]
            self._scn_match = [R(type="ORDER_RECEIVED", order=n), R(type="ORDER_ALLOCATED", order=n),
                               R(type="TASK_ASSIGNED", order=n, forklift="F-05"),
                               R(type="FORKLIFT_AT_SOURCE", order=n, forklift="F-05"),
                               R(type="BUNDLE_PICKED", order=n, forklift="F-05", task_type="PICK"),
                               R(type="BUNDLE_STAGED", order=n, forklift="F-05"), R(type="ORDER_STAGED", order=n)]
            self.scenario = self._scn(2, "Order-Based Picking", steps, {"forklift": "F-05", "order": n})
            self.release_order(n)
            self.start_picking(n, prefer_first="F-05")
            return self.scenario
        if sid == 3:
            staged = sorted([o for o in self.orders.values() if o["status"] == "STAGED"], key=lambda o: o["order_number"])
            if not staged:
                raise ValueError("No staged order — run Scenario 2 first")
            if self.dock_busy():
                raise ValueError("Dock 1 is occupied")
            o = staged[0]
            n = o["order_number"]
            o["inject_wrong"] = inject == "wrong"
            o["inject_missing"] = inject == "missing"
            steps = ["Truck arrives with dispatch order", "Required bundle manifest is displayed",
                     "Forklifts load bundles onto the truck", "RFID gate automatically reads bundle EPCs",
                     "System compares actual bundles against the order", "Validated dispatch is authorized"]
            self._scn_match = [R(type="TRUCK_ARRIVED", order=n), R(type="MANIFEST_CREATED", order=n),
                               R(type="TRUCK_LOADED", order=n), R(type="GATE_READ_COMPLETE", order=n),
                               R(type="RECONCILED", order=n),
                               lambda ev: ev["type"] in ("DISPATCH_VALIDATED", "DISPATCH_EXCEPTION")
                               and ev["refs"].get("order") == n]
            self.scenario = self._scn(3, "Truck Dispatch Assurance", steps, {"order": n, "inject": inject})
            tr = self.dispatch_order(n)
            self.scenario["focus"]["truck"] = tr["id"]
            return self.scenario
        raise ValueError("Unknown scenario")

    def _scn(self, sid, title, steps, focus) -> dict:
        return {"id": sid, "title": title, "status": "RUNNING", "cursor": 0, "started": self.ts(), "focus": focus,
                "steps": [{"label": s, "done": False, "t": None} for s in steps]}

    def stop_scenario(self):
        self.scenario = None
        self._scn_match = []

    def inject(self, kind: str) -> dict:
        if kind not in ("wrong", "missing"):
            raise ValueError("kind must be 'wrong' or 'missing'")
        target = None
        for st in ("LOADING", "STAGED"):
            c = sorted([o for o in self.orders.values() if o["status"] == st and not o.get(f"{kind}_done")],
                       key=lambda o: o["order_number"])
            if c:
                target = c[0]
                break
        if target is None:
            raise ValueError("No staged or loading order to inject an error into")
        target["inject_" + kind] = True
        label = "wrong bundle" if kind == "wrong" else "missing bundle"
        self.emit("INJECTION_ARMED", f"Demo: {label} error armed for {target['order_number']}", "warning",
                  order=target["order_number"])
        return target

    # ============================================================ read models
    def inventory_counts(self) -> dict:
        c = {"WH01": 0, "WH02": 0, "staging": 0, "receiving": 0, "in_transit": 0, "on_truck": 0, "total": 0}
        for b in self.bundles.values():
            k = b["loc"]["kind"]
            if k == "stack":
                st = self.layout.stacks[b["loc"]["stack"]]
                if st.kind == "STAGING":
                    c["staging"] += 1
                elif st.kind == "RECEIVING":
                    c["receiving"] += 1
                else:
                    c[st.warehouse_id] += 1
            elif k == "forklift":
                c["in_transit"] += 1
            elif k == "truck":
                c["on_truck"] += 1
            if k not in ("dispatched", "incoming"):
                c["total"] += 1
        return c

    def forklift_dict(self, f: Forklift, detail: bool = False) -> dict:
        route = []
        if f.actions:
            a = f.actions[0]
            if a["k"] == "move":
                route = [[round(f.x, 2), round(f.z, 2)]] + [[round(p[0], 2), round(p[1], 2)] for p in a["pts"][a["i"]:]]
        t = f.task
        d = {"id": f.id, "name": f.name, "role": f.role, "roleLabel": ROLE_LABEL[f.role], "state": f.state,
             "x": round(f.x, 3), "z": round(f.z, 3), "h": round(f.heading, 4), "fork": round(f.fork, 3),
             "load": f.load, "loadBarcode": self.bundles[f.load]["barcode"] if f.load else None,
             "task": {"id": t["id"], "type": t["type"], "bundle": t["bundle"],
                      "barcode": self.bundles[t["bundle"]]["barcode"], "order": t["order"],
                      "from": self.ep_label(t["src"]), "to": self.ep_label(t["dst"])} if t else None,
             "queued": max(0, len(f.job) - 1) if f.job else 0,
             "dest": f.dest, "route": route, "battery": round(f.battery, 1),
             "util": round(100 * f.busy_time / self.t, 1) if self.t > 1 else 0.0,
             "distance": round(f.distance, 1), "done": f.tasks_done,
             "warehouse": self._wh_at(f.x), "uwbErr": round(0.05 + 0.06 * abs(math.sin(self.t * 0.7 + hash(f.id) % 7)), 3)}
        if detail:
            d["history"] = list(f.history)
        return d

    def truck_dict(self, tr: dict) -> dict:
        return {"id": tr["id"], "plate": tr["plate"], "carrier": tr["carrier"], "order": tr["order"],
                "state": tr["state"], "x": round(tr["x"], 2), "z": round(tr["z"], 2), "h": round(tr["heading"], 4),
                "manifest": tr["manifest"], "onBoard": sum(len(c) for c in tr["slots"])}

    def bundle_brief(self, b: dict) -> dict:
        loc = b["loc"]
        k = loc["kind"]
        if k == "stack":
            lc = {"k": "s", "s": loc["stack"], "l": loc["level"]}
        elif k == "forklift":
            lc = {"k": "f", "f": loc["forklift"]}
        elif k == "truck":
            lc = {"k": "t", "t": loc["truck"], "c": loc["col"], "l": loc["level"]}
        else:
            lc = {"k": k[0]}
        return {"id": b["id"], "bc": b["barcode"], "so": b["so"], "w": b["wrap"], "st": b["status"],
                "len": b["length_mm"], "loc": lc, "p": b["product"]}

    def bundle_detail(self, bid: str) -> dict | None:
        b = self.bundles.get(bid)
        if b is None:
            return None
        li = self.loc_info(b)
        prod = PRODUCT_BY_CODE[b["product"]]
        o = self.orders.get(b["so"], {})
        return {**{k: v for k, v in b.items() if k not in ("loc",)}, "location": li, "outdoor_allowed": prod["outdoor"],
                "order_status": o.get("status"), "ship_to": o.get("ship_to"),
                "stack_height": len(self.stack_bundles[li["stack_id"]]) if li.get("stack_id") else None}

    def stack_detail(self, sid: str) -> dict | None:
        st = self.layout.stacks.get(sid)
        if st is None:
            return None
        return {"id": st.id, "kind": st.kind, "warehouse": st.warehouse_id, "zone": self.layout.zones[st.zone_id].name,
                "bay": self.layout.bays[st.bay_id].code, "stack": st.code, "maxLevels": st.max_levels,
                "locked": self.locked(("S", sid)), "incoming": self.incoming[sid],
                "levels": [{"level": i + 1, "code": st.location_code(i + 1), **self.bundle_brief(self.bundles[b]),
                            "customer": self.bundles[b]["customer"], "product_name": self.bundles[b]["product_name"]}
                           for i, b in enumerate(self.stack_bundles[sid])]}

    def order_dict(self, o: dict, detail: bool = False) -> dict:
        bundles = [self.bundles[b] for b in o["bundles"] if b in self.bundles]
        d = {k: o.get(k) for k in ("order_number", "customer", "ship_to", "carrier", "status", "priority", "booked_at",
                                   "released_at", "staged_at", "dispatched_at", "lane", "truck", "manifest", "lines",
                                   "inject_wrong", "inject_missing")}
        d["bundle_count"] = len(bundles)
        d["in_stock"] = sum(1 for b in bundles if b["status"] in ("STORED", "STAGED"))
        d["staged"] = sum(1 for b in bundles if b["status"] == "STAGED")
        d["loaded"] = sum(1 for b in bundles if b["status"] in ("LOADED", "DISPATCHED"))
        if detail:
            d["pick_list"] = [{"bundle": b["id"], "barcode": b["barcode"], "epc": b["epc"], "status": b["status"],
                               "location": self.loc_info(b)["code"], "product": b["product_name"],
                               "length_mm": b["length_mm"], "weight_kg": b["weight_kg"],
                               "last_move": b["last_move"]} for b in bundles]
            mf = self.manifests.get(o.get("manifest") or "")
            d["manifest_detail"] = {k: v for k, v in mf.items()} if mf else None
            d["tasks"] = [self.task_dict(t) for t in self.tasks.values() if t["order"] == o["order_number"]]
            d["exceptions"] = [e for e in self.exceptions if e["order"] == o["order_number"]]
        return d

    def task_dict(self, t: dict) -> dict:
        b = self.bundles.get(t["bundle"], {})
        return {"id": t["id"], "type": t["type"], "status": t["status"], "bundle": t["bundle"],
                "barcode": b.get("barcode"), "order": t["order"], "forklift": t["forklift"],
                "from": t.get("from_code") or self.ep_label(t["src"]), "to": t.get("to_code") or self.ep_label(t["dst"]),
                "created": iso(SIM_START + timedelta(seconds=t["created"])),
                "duration_s": round((t["finished"] or self.t) - (t["started"] or self.t), 1) if t["started"] else None,
                "distance_m": round(t["distance"], 1), "note": t.get("note", "")}

    def queue_dict(self, r: dict) -> dict:
        b = self.bundles.get(r["bundle"], {})
        return {"id": r["id"], "type": r["type"], "bundle": r["bundle"], "barcode": b.get("barcode"),
                "order": r.get("order"), "prefer": r.get("prefer"), "waiting_s": round(self.t - r["created"], 1),
                "to": r.get("dst")}

    def analytics(self) -> dict:
        def avg(xs):
            return round(sum(xs) / len(xs), 1) if xs else None
        counts = self.inventory_counts()
        cap = {"WH01": 0, "WH02": 0, "staging": 0}
        for s in self.layout.stacks.values():
            if s.kind == "STORAGE":
                cap[s.warehouse_id] += s.max_levels
            elif s.kind == "STAGING":
                cap["staging"] += s.max_levels
        hours = max(self.t / 3600, 1e-6)
        order_status = {}
        for o in self.orders.values():
            order_status[o["status"]] = order_status.get(o["status"], 0) + 1
        by_product = {}
        for b in self.bundles.values():
            if b["loc"]["kind"] == "stack":
                by_product[b["product"]] = by_product.get(b["product"], 0) + 1
        gv = self.kpi["gate_validations"]
        return {
            "clock": self.ts(), "elapsed_s": round(self.t), "kpi": dict(self.kpi), "inventory": counts,
            "occupancy": {k: round(100 * counts[k] / cap[k], 1) if cap[k] else 0 for k in cap}, "capacity": cap,
            "cycle_avg_s": {k: avg(v) for k, v in self.cycle.items()},
            "throughput_per_hour": {"putaways": round(self.kpi["putaways"] / hours, 1),
                                    "picks": round(self.kpi["picks"] / hours, 1),
                                    "dispatched": round(self.kpi["bundles_dispatched"] / hours, 1)},
            "dispatch_accuracy": round(100 * self.kpi["first_pass_ok"] / gv, 1) if gv else None,
            "fleet": [{"id": f.id, "role": f.role, "util": round(100 * f.busy_time / self.t, 1) if self.t > 1 else 0,
                       "distance": round(f.distance), "done": f.tasks_done, "battery": round(f.battery)}
                      for f in self.forklifts.values()],
            "orders_by_status": order_status, "inventory_by_product": by_product,
            "series": self.series,
            "history": self._history_days(),
        }

    def _history_days(self) -> list:
        r = random.Random(self.seed + 7)
        out = []
        for d in range(7, 0, -1):
            day = (SIM_START - timedelta(days=d)).strftime("%a %d")
            out.append({"day": day, "putaways": r.randint(160, 230), "dispatched": r.randint(140, 210),
                        "exceptions_caught": r.randint(0, 4), "search_minutes_saved": r.randint(140, 260)})
        return out

    def state_msg(self) -> dict:
        return {"type": "state", "t": round(self.t, 2), "clock": self.ts(), "running": self.running, "speed": self.speed,
                "autopilot": self.autopilot, "autoPutaway": self.auto_putaway,
                "forklifts": [self.forklift_dict(f) for f in self.forklifts.values()],
                "trucks": [self.truck_dict(t) for t in self.trucks.values()],
                "gate": {k: self.gate[k] for k in ("state", "truck", "result")} | {"reads": len(self.gate["reads"])},
                "invVersion": self.inv_version, "scenario": self.scenario}

    def inventory_msg(self) -> dict:
        return {"type": "inventory", "version": self.inv_version,
                "bundles": [self.bundle_brief(b) for b in self.bundles.values()
                            if b["loc"]["kind"] not in ("dispatched", "incoming")]}

    def ops_msg(self) -> dict:
        orders = sorted(self.orders.values(), key=lambda o: o["order_number"])
        active = [o for o in orders if o["status"] not in ("BOOKED",)]
        return {"type": "ops",
                "orders": [self.order_dict(o) for o in active][-40:],
                "booked": len([o for o in orders if o["status"] == "BOOKED"]),
                "eligible": [o["order_number"] for o in self.eligible_orders()[:8]],
                "queue": [self.queue_dict(r) for r in self.queue],
                "active": [self.task_dict(t) for t in self.tasks.values() if t["status"] in ("ASSIGNED", "IN_PROGRESS")],
                "recent": [self.task_dict(t) for t in sorted(
                    (t for t in self.tasks.values() if t["status"] == "DONE"), key=lambda t: -t["finished"])[:25]],
                "exceptions": self.exceptions[-10:],
                "lanes": {k: v for k, v in self.lane_owner.items()},
                "kpi": self.kpi, "inventory": self.inventory_counts(),
                "dock": self.truck_dict(self.dock_busy()) if self.dock_busy() else None}

    def replay(self, task_id: str | None = None) -> dict | None:
        done = [t for t in self.tasks.values() if t["status"] == "DONE" and t["path"]]
        if task_id:
            done = [t for t in done if t["id"] == task_id]
        if not done:
            return None
        t = max(done, key=lambda t: t["finished"])
        b = self.bundles[t["bundle"]]
        return {"task": self.task_dict(t), "path": t["path"], "forklift": t["forklift"], "bundle": b["id"],
                "barcode": b["barcode"], "wrap": b["wrap"], "duration_s": round(t["finished"] - t["started"], 1),
                "role": self.forklifts[t["forklift"]].role}
