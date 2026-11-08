"""Physical warehouse layout: indoor warehouse (WH01) and outdoor yard (WH02).

Coordinates are metres. x runs west -> east, z runs north -> south, y is up.
The indoor building spans x in [-100, 0]; the yard spans x in [4, 122].

Location hierarchy: Plant / Warehouse / Zone / Bay / Stack / Level, e.g.
``PL01-WH01-Z02-B004-S02-L03``.

Bundles are stored in floor stacks (no racking). A bundle's long axis lies
along x; forklifts approach a stack from its service aisle, travelling in z,
so the load is carried across the forks (long-load handling).
"""
from __future__ import annotations

import heapq
import math
from dataclasses import asdict, dataclass, field

PLANT = "PL01"
BUNDLE_L = 6.0
BUNDLE_W = 1.2
BUNDLE_H = 0.5
DUNNAGE = 0.08
LEVEL_PITCH = BUNDLE_H + DUNNAGE
STACK_PITCH = 7.0
PRE_D = 4.5  # forklift centre -> stack centre when lined up in the aisle
APP_D = 2.0  # forklift centre -> stack centre when the load is over the stack
TRUCK_BED = 1.35

# (row centre z, service aisle z)
ROWS = [(-22.0, -15.0), (-8.0, -15.0), (8.0, 15.0), (22.0, 15.0)]
AISLES = [-15.0, 0.0, 15.0]
BAYS_INDOOR = [-80.0, -57.0, -34.0]
BAYS_YARD = [12.0, 35.0, 58.0]
STAGING_BAY = 86.0
STACKS_PER_BAY = 3

IN_W, IN_E = -85.0, -8.0  # indoor cross corridors
YD_W, YD_E = 8.0, 104.0  # yard cross corridors
RECEIVING_X = -93.0

DOCK = {"x": 113.0, "z": 0.0, "heading": math.pi / 2}
TRUCK_COLS = [3.3, -3.3]  # local x along the trailer
TRUCK_LEVELS = 4
GATE = {"x": 113.0, "z": -32.0, "width": 9.0, "height": 6.5}
TRUCK_ENTRY = (113.0, 85.0)
TRUCK_HOLD = (113.0, -46.0)
TRUCK_EXIT = (113.0, -110.0)


def level_bottom(level: int, base: float = 0.0) -> float:
    return base + DUNNAGE + (level - 1) * LEVEL_PITCH


def heading_of(dx: float, dz: float) -> float:
    """Yaw such that a model facing local +x points along (dx, dz)."""
    return math.atan2(-dz, dx)


@dataclass
class Warehouse:
    id: str
    code: str
    name: str
    kind: str
    bounds: tuple  # x0, z0, x1, z1


@dataclass
class Zone:
    id: str
    code: str
    warehouse_id: str
    name: str
    kind: str  # RECEIVING | STORAGE | STAGING | LOADING | PARKING
    rect: tuple
    color: str


@dataclass
class Bay:
    id: str
    code: str
    zone_id: str
    warehouse_id: str
    rect: tuple
    label: str = ""


@dataclass
class Stack:
    id: str
    code: str
    bay_id: str
    zone_id: str
    warehouse_id: str
    kind: str
    x: float
    z: float
    max_levels: int
    node: str
    pre: tuple
    app: tuple
    heading: float
    yaw: float = 0.0
    lane: str | None = None

    def location_code(self, level: int) -> str:
        return f"{PLANT}-{self.id}-L{level:02d}"


@dataclass
class Layout:
    warehouses: dict = field(default_factory=dict)
    zones: dict = field(default_factory=dict)
    bays: dict = field(default_factory=dict)
    stacks: dict = field(default_factory=dict)
    nodes: dict = field(default_factory=dict)
    adj: dict = field(default_factory=dict)
    parking: dict = field(default_factory=dict)
    anchors: list = field(default_factory=list)
    doors: list = field(default_factory=list)
    lanes: dict = field(default_factory=dict)  # staging lane id -> [stack ids]

    # ------------------------------------------------------------------ graph
    def node(self, x: float, z: float) -> str:
        nid = f"n{x:.1f}_{z:.1f}"
        self.nodes.setdefault(nid, (x, z))
        self.adj.setdefault(nid, {})
        return nid

    def link(self, a: str, b: str) -> None:
        (ax, az), (bx, bz) = self.nodes[a], self.nodes[b]
        d = math.hypot(ax - bx, az - bz)
        self.adj[a][b] = d
        self.adj[b][a] = d

    def chain(self, pts: list[tuple]) -> None:
        ids = [self.node(x, z) for x, z in pts]
        for a, b in zip(ids, ids[1:]):
            if a != b:
                self.link(a, b)

    def route(self, start: str, goal: str) -> list[str]:
        if start == goal:
            return [start]
        dist = {start: 0.0}
        prev: dict[str, str] = {}
        pq = [(0.0, start)]
        while pq:
            d, n = heapq.heappop(pq)
            if n == goal:
                break
            if d > dist.get(n, 1e18):
                continue
            for m, w in self.adj[n].items():
                nd = d + w
                if nd < dist.get(m, 1e18):
                    dist[m] = nd
                    prev[m] = n
                    heapq.heappush(pq, (nd, m))
        if goal not in dist:
            return [start, goal]
        out = [goal]
        while out[-1] != start:
            out.append(prev[out[-1]])
        return out[::-1]

    def nearest_node(self, x: float, z: float) -> str:
        return min(self.nodes, key=lambda n: math.hypot(self.nodes[n][0] - x, self.nodes[n][1] - z))

    # ------------------------------------------------------------ serialise
    def to_dict(self) -> dict:
        return {
            "plant": PLANT,
            "bundle": {"length": BUNDLE_L, "width": BUNDLE_W, "height": BUNDLE_H, "dunnage": DUNNAGE,
                       "pitch": LEVEL_PITCH},
            "warehouses": [asdict(w) for w in self.warehouses.values()],
            "zones": [asdict(z) for z in self.zones.values()],
            "bays": [asdict(b) for b in self.bays.values()],
            "stacks": [
                {"id": s.id, "code": s.code, "bay": s.bay_id, "zone": s.zone_id, "warehouse": s.warehouse_id,
                 "kind": s.kind, "x": s.x, "z": s.z, "maxLevels": s.max_levels, "yaw": s.yaw, "lane": s.lane}
                for s in self.stacks.values()
            ],
            "parking": list(self.parking.values()),
            "anchors": self.anchors,
            "doors": self.doors,
            "dock": DOCK,
            "truck": {"cols": TRUCK_COLS, "levels": TRUCK_LEVELS, "bed": TRUCK_BED},
            "gate": GATE,
            "graph": {
                "nodes": {k: list(v) for k, v in self.nodes.items()},
                "edges": sorted({tuple(sorted((a, b))) for a in self.adj for b in self.adj[a]}),
            },
            "lanes": self.lanes,
        }


def _add_stack(lay: Layout, wh: str, zone: str, bay: Bay, idx: int, x: float, row_z: float, aisle_z: float,
               max_levels: int, kind: str, lane: str | None = None) -> Stack:
    sid = f"{bay.id}-S{idx:02d}"
    toward = 1.0 if row_z > aisle_z else -1.0  # +1: stack is south of the aisle
    node = lay.node(x, aisle_z)
    st = Stack(
        id=sid, code=f"S{idx:02d}", bay_id=bay.id, zone_id=zone, warehouse_id=wh, kind=kind,
        x=x, z=row_z, max_levels=max_levels, node=node,
        pre=(x, row_z - toward * PRE_D), app=(x, row_z - toward * APP_D),
        heading=heading_of(0.0, toward), lane=lane,
    )
    lay.stacks[sid] = st
    return st


def build_layout() -> Layout:
    lay = Layout()
    lay.warehouses["WH01"] = Warehouse("WH01", "WH01", "Indoor Finished Goods Warehouse", "INDOOR", (-100, -30, 0, 30))
    lay.warehouses["WH02"] = Warehouse("WH02", "WH02", "Outdoor Storage Yard", "OUTDOOR", (4, -35, 122, 35))

    def zone(wh, code, name, kind, rect, color):
        z = Zone(f"{wh}-{code}", code, wh, name, kind, rect, color)
        lay.zones[z.id] = z
        return z

    zone("WH01", "Z01", "Receiving (from production)", "RECEIVING", (-99, -26, -88, 25), "#f59e0b")
    zone("WH01", "Z02", "Storage Hall A", "STORAGE", (-82, -27, -12, -4), "#3b82f6")
    zone("WH01", "Z03", "Storage Hall B", "STORAGE", (-82, 4, -12, 27), "#6366f1")
    zone("WH01", "Z05", "Putaway Fleet Parking", "PARKING", (-98, 25.5, -72, 29.5), "#22c55e")
    zone("WH02", "Z01", "Yard Storage A", "STORAGE", (10, -27, 81, -4), "#0ea5e9")
    zone("WH02", "Z02", "Yard Storage B", "STORAGE", (10, 4, 81, 27), "#14b8a6")
    zone("WH02", "Z03", "Dispatch Staging", "STAGING", (84, -27, 101, 27), "#a855f7")
    zone("WH02", "Z04", "Truck Loading & RFID Gate", "LOADING", (106, -40, 121, 12), "#ef4444")
    zone("WH02", "Z05", "Picking Fleet Parking", "PARKING", (85, 27.5, 102, 33), "#3b82f6")

    # --------------------------------------------------------------- storage
    bay_no = {"WH01": 0, "WH02": 0}
    for wh, starts, levels in (("WH01", BAYS_INDOOR, 5), ("WH02", BAYS_YARD, 4)):
        for r, (row_z, aisle_z) in enumerate(ROWS):
            zcode = ("Z02" if r < 2 else "Z03") if wh == "WH01" else ("Z01" if r < 2 else "Z02")
            for b, x0 in enumerate(starts):
                bay_no[wh] += 1
                bid = f"{wh}-{zcode}-B{bay_no[wh]:03d}"
                width = STACKS_PER_BAY * STACK_PITCH
                bay = Bay(bid, f"B{bay_no[wh]:03d}", f"{wh}-{zcode}", wh,
                          (x0, row_z - 1.6, x0 + width, row_z + 1.6))
                lay.bays[bid] = bay
                for s in range(STACKS_PER_BAY):
                    x = x0 + STACK_PITCH * (s + 0.5)
                    _add_stack(lay, wh, bay.zone_id, bay, s + 1, x, row_z, aisle_z, levels, "STORAGE")

    # -------------------------------------------------------------- receiving
    rbay = Bay("WH01-Z01-B000", "B000", "WH01-Z01", "WH01", (RECEIVING_X - 3.4, -26, RECEIVING_X + 3.4, 25), "Inbound")
    lay.bays[rbay.id] = rbay
    for i, (row_z, aisle_z) in enumerate(ROWS):
        _add_stack(lay, "WH01", "WH01-Z01", rbay, i + 1, RECEIVING_X, row_z, aisle_z, 1, "RECEIVING")

    # --------------------------------------------------------- dispatch staging
    for i, (row_z, aisle_z) in enumerate(ROWS):
        lane = f"LANE-{i + 1}"
        bay_no["WH02"] += 1
        bid = f"WH02-Z03-B{bay_no['WH02']:03d}"
        bay = Bay(bid, f"B{bay_no['WH02']:03d}", "WH02-Z03", "WH02",
                  (STAGING_BAY, row_z - 1.6, STAGING_BAY + 2 * STACK_PITCH, row_z + 1.6), f"Staging {lane}")
        lay.bays[bid] = bay
        ids = []
        for s in range(2):
            x = STAGING_BAY + STACK_PITCH * (s + 0.5)
            ids.append(_add_stack(lay, "WH02", "WH02-Z03", bay, s + 1, x, row_z, aisle_z, 3, "STAGING", lane).id)
        lay.lanes[lane] = ids

    # ------------------------------------------------------------------ graph
    indoor_xs = sorted({RECEIVING_X, IN_W, IN_E} | {s.x for s in lay.stacks.values() if s.warehouse_id == "WH01"})
    yard_xs = sorted({YD_W, YD_E} | {s.x for s in lay.stacks.values() if s.warehouse_id == "WH02"})
    for az in (-15.0, 15.0):
        lay.chain([(x, az) for x in indoor_xs])
        lay.chain([(x, az) for x in yard_xs])
    lay.chain([(IN_W, 0.0), (IN_E, 0.0), (YD_W, 0.0), (YD_E, 0.0)])  # main aisle through the dock door
    lay.chain([(IN_W, -15.0), (IN_W, 0.0), (IN_W, 15.0), (IN_W, 27.0)])
    lay.chain([(IN_E, -15.0), (IN_E, 0.0), (IN_E, 15.0)])
    lay.chain([(YD_W, -15.0), (YD_W, 0.0), (YD_W, 15.0)])
    lay.chain([(YD_E, -15.0), (YD_E, 0.0), (YD_E, 15.0), (YD_E, 29.5)])

    # ---------------------------------------------------------------- parking
    pin = lay.node(IN_W, 27.0)
    for i, x in enumerate([-96.0, -92.0, -79.0, -75.0]):
        fid = f"F-0{i + 1}"
        lay.parking[fid] = {"id": f"P-{fid}", "x": x, "z": 27.5, "node": pin, "heading": 0.0 if x > IN_W else math.pi,
                            "warehouse": "WH01"}
    pyd = lay.node(YD_E, 29.5)
    for i, x in enumerate([88.0, 92.0, 96.0, 100.0]):
        fid = f"F-0{i + 5}"
        lay.parking[fid] = {"id": f"P-{fid}", "x": x, "z": 30.5, "node": pyd, "heading": math.pi, "warehouse": "WH02"}

    # ------------------------------------------------------- UWB anchors, doors
    for x in (-100, -66, -33, 0):
        for z in (-30, 30):
            lay.anchors.append({"id": f"UWB-IN-{len(lay.anchors) + 1:02d}", "x": x, "y": 8.5, "z": z, "warehouse": "WH01"})
    for x in (6, 40, 75, 110):
        for z in (-35, 35):
            lay.anchors.append({"id": f"UWB-YD-{len(lay.anchors) - 7:02d}", "x": x, "y": 6.0, "z": z, "warehouse": "WH02"})
    lay.doors = [
        {"id": "D-PROD", "name": "Production transfer door", "x": -100, "z": 0, "width": 8, "height": 6, "axis": "z"},
        {"id": "D-YARD", "name": "Warehouse-to-yard door", "x": 0, "z": 0, "width": 10, "height": 6.5, "axis": "z"},
    ]
    return lay


def truck_slot_world(col: int, dock=DOCK) -> tuple[float, float]:
    lx = TRUCK_COLS[col]
    return dock["x"] + lx * math.cos(dock["heading"]), dock["z"] - lx * math.sin(dock["heading"])
