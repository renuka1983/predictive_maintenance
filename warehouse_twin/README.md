# Warehouse Digital Twin: Bundle Tracking & Dispatch Assurance (PoC)

This is an interactive 3D simulation of an aluminium finished-goods warehouse and its outdoor
yard. It is built to show a customer how autonomous bundle tracking works without any
warehouse hardware: finished bundles are put away into floor stacks, forklifts pick customer
orders on their own, and an RFID gate checks every truck before it leaves.

All data is simulated: Oracle ERP, the RFID readers and UWB positioning are all mocks. The
data model, the location hierarchy and the integration contract are built to production
shape, so the mocks can be replaced with real adapters later.

```
React + TypeScript + MUI ── Three.js / React Three Fiber (3D twin)
          │  REST + WebSocket (10 Hz state, event stream)
FastAPI ── Simulation engine (putaway · picking · dispatch · forklift motion)
          │  write-behind persistence thread
PostgreSQL (SQLite for local runs) ── 17-table relational model
          └─ Mock Oracle adapter · RFID event simulator · UWB position simulator
```

## Run it

### Docker (PostgreSQL + backend + frontend)

```bash
cd warehouse_twin
docker compose up --build
```

Open http://localhost:8080. The API docs are at http://localhost:8000/docs.

### Local development (SQLite, no Docker)

```bash
cd warehouse_twin/backend
pip install -r requirements.txt
uvicorn app.main:app --port 8000          # DATABASE_URL defaults to sqlite:///./warehouse_twin.db
```

```bash
cd warehouse_twin/frontend
npm install
npm run dev                               # http://localhost:5173 (proxies /api and /ws to :8000)
```

To use PostgreSQL locally, set
`DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname`. Tables are created on startup,
and every simulation reset reseeds them.

### Tests

```bash
cd warehouse_twin/backend && python -m pytest -q
```

The tests cover all three scenarios, including the wrong-bundle and missing-bundle exception
paths, a two-hour autopilot run with stack and location invariants, the traffic rules (lanes,
fork-side choice, a head-on and contact budget over an autopilot hour), and an API/WebSocket
round trip.

## What the customer sees

| Screen | Contents |
|---|---|
| **Live Digital Twin** | 3D indoor warehouse (walls, dock doors, zones, bays, aisles) and outdoor yard (fence, staging lanes, truck dock, RFID gate). Shows 8 animated forklifts, floor stacks built from real bundle dimensions, live routes, RFID read pulses and UWB anchor links. Click any bundle, stack, forklift or truck for details. |
| **Operations** | Putaway, picking and dispatch workflows side by side: queued and running tasks, staging lanes, dock status and exceptions. |
| **Inventory** | Searches the database by barcode, EPC, sales order, customer, product or location code. Click a row to fly the 3D camera to that bundle. |
| **Fleet** | Live 2D UWB map, a card for each forklift (task, load, position, utilization, battery) and per-forklift movement history with replay. |
| **Orders** | Oracle orders, pick lists, dispatch manifests, RFID gate reads, reconciliation results and the Oracle integration message log. |
| **Analytics** | Throughput, cycle times, rehandles, first-pass dispatch accuracy, exceptions caught, utilization, inventory trend and database row counts. |

Clicking a **bundle** shows its barcode, RFID EPC, customer, sales order, product and
dimensions, warehouse, zone/bay/stack/level, status, last movement and the forklift that
handled it. It also shows the stack's vertical sequence and the movement history stored in the
database.

Clicking a **forklift** shows its current task, UWB position, load, fork height, destination,
utilization and movement history. Each history entry has a *replay* button.

## Demo script (Demo Control Panel)

1. **① Automatic putaway**: a finished bundle arrives from extrusion. Its barcode is associated
   with an RFID EPC, the putaway engine allocates a floor-stack location, and **F-01** carries the
   bundle there and places it. The stack updates in the twin.
2. **② Order-based picking**: Oracle releases **SO-45892** (TransLogix Trailers, 3 bundles). The
   system finds the bundles in two indoor stacks and one yard stack. One of them is buried under
   another order's bundle, so the picking engine relocates the blocking bundle first. **F-05** and
   the other picking forklifts then move all three bundles to a dispatch staging lane.
3. **③ Truck dispatch assurance**: a truck docks for the staged order and the manifest is
   displayed. The forklifts load the truck, the truck drives through **RFID GATE-01**, and the
   EPCs read at the gate are reconciled against the manifest.
   * **clean**: dispatch is authorized, the barrier opens and an Oracle ship confirm is sent.
   * **+ wrong**: a forklift loads a bundle from another order. The gate blocks dispatch and names
     the bundle and the order it belongs to.
   * **+ missing**: one bundle is left in staging. The gate blocks dispatch and shows where the
     missing bundle is.
   * **Resolve dispatch exception**: the truck reverses to the dock, the load is corrected, and
     the truck is re-validated automatically.

The panel also has these controls:

* Start, pause and reset.
* Simulation speed from 1× to 10×.
* Camera presets: overview, indoor, outdoor, dispatch, and follow-forklift.
* Toggles for RFID, UWB, routes, labels and roof.
* Manual operations: receive a bundle, generate an order, start picking, send forklifts to
  dispatch, run RFID gate validation, inject an error, replay the previous movement.
* **Autopilot**: continuous production, order release, picking, truck dispatch and
  auto-resolution of exceptions, for an unattended demo screen.

The seeded state is deterministic (`SIM_SEED`). SO-45891 is already staged, so scenario ③ works
straight after a reset, and SO-45892 is set up for scenario ②.

## Physical layout and location codes

`Plant / Warehouse / Zone / Bay / Stack / Level`, for example `PL01-WH01-Z02-B005-S01-L02`.

| Warehouse | Zones | Stacks |
|---|---|---|
| WH01 indoor (100 × 60 m) | Z01 Receiving · Z02 Storage Hall A · Z03 Storage Hall B · Z05 putaway fleet parking | 36 floor stacks × 5 levels, plus 4 receiving positions |
| WH02 yard (118 × 70 m) | Z01/Z02 Yard Storage · Z03 Dispatch Staging (LANE-1…4) · Z04 Truck Loading & RFID Gate · Z05 picking fleet parking | 36 floor stacks × 4 levels, plus 8 staging stacks × 3 levels |

* Bundles are 6 m × 1.2 m × 0.5 m with timber dunnage, and each stack level is 0.58 m. Forklifts
  carry the load across the forks.
* Only mill-finish profiles may be stored outdoors. Anodized and painted profiles stay indoors.
* Forklifts route over an aisle graph through the warehouse-to-yard door. Routes are planned with
  Dijkstra. Each job locks the stacks it uses, so jobs never conflict on a stack.

## What the forklift captures, and how Oracle is updated

At every pick-up and placement the forklift itself produces an evidence record:

* the RFID EPC read by its fork antennas, matched to the bundle barcode (LPN), with read strength
* its UWB position (x, y, z, accuracy), resolved by the twin into a location code
  (`PL01-WH01-Z02-B005-S01-L02`: plant, warehouse, zone, bay, stack, level)
* the forklift ID and timestamp

A card above the forklift shows the record as it is captured (cyan for pick-up, green for
placement). The same record is stored in the database and attached to the Oracle transaction:

| Moment | Oracle interface (mock adapter) | Direction |
|---|---|---|
| Putaway placement, or returning a wrongly loaded bundle | INV Subinventory Transfer (Putaway) | out |
| Customer order released | OE_ORDER_PUB → Pick Release | in |
| Rehandle of a blocking bundle | INV Locator Transfer (Rehandle) | out |
| Bundle placed in a staging lane | INV Move Order Transaction (Pick Confirm) | out |
| Bundle loaded on the truck | WSH Load Confirm (LPN to truck) | out |
| RFID gate validated or blocked | WSH Ship Confirm, or WSH Delivery Hold | out |

The live event stream tags these lines `ORACLE` and `RFID`. **Orders → Oracle ERP integration
log** shows every message with its full payload, filterable by putaway, picking or dispatch.

## Forklift traffic management

Forklifts never meet head-on in the same path:

* **Right-hand traffic lanes.** Every aisle and corridor carries two lanes, 1.6 m either side of the
  centre line (white chevrons on the floor). Routes are offset onto the lane on the right of the
  direction of travel, with mitred corners at junctions.
* **Long loads travel lengthwise.** A loaded forklift drives sideways (multi-directional / sideloader
  style), so the 6 m bundle lies along the aisle instead of across it. For each leg the planner
  chooses whether the forks point right or left of travel, to minimise turning with the bundle. For
  example, it arrives already facing a stack on the left. Forks-left travel uses a 3.0 m lane
  offset, so the forklift occupies the same band of its own lane either way. Empty forklifts drive
  forwards.
* **Look-ahead yielding.** Every 0.15 s each moving forklift checks the footprint (chassis, forks
  and bundle) it will sweep over the next few metres, including turning arcs. If that footprint
  would touch another forklift, it stops and yields. A forklift about to turn on the spot claims
  its whole turning circle, so nobody queues inside it.
* **Right of way.** When two forklifts block each other, the loaded one goes first, then the one
  that has waited longest. An idle forklift in the way is sent back to its parking bay. As a last
  resort, a forklift that has waited 15 s creeps past slowly. This happens a few times an hour.
* **Parking.** Each forklift has its own bay off a parking spur and reverses in. Reaching a bay
  never means driving through another parked forklift.

Measured over six simulated autopilot hours against the previous version (no lanes, no yielding):
overlaps between moving forklifts travelling in opposite directions fell from 2,313 to 52 (−98 %).
Overlaps of any kind fell from 8,896 to 1,016 (−89 %). Throughput was unchanged (82 vs 81 trucks,
366 vs 361 picks). While a forklift waits, its label turns amber and reads `yielding to F-0x`. The
Fleet page and Analytics report yields and waiting time.
* The putaway rule consolidates bundles by sales order. It avoids burying bundles of orders that
  will ship earlier, which keeps future rehandles low.

## Data model

`warehouse`, `warehouse_zone`, `warehouse_bay`, `bundle_stack`, `bundle_stack_level`, `bundle`,
`rfid_tag`, `bundle_location`, `forklift`, `forklift_position`, `movement_task`,
`movement_event`, `sales_order`, `sales_order_bundle`, `dispatch_manifest`, `dispatch_event`,
`simulation_event`. See `backend/app/models.py`.

The simulation engine holds the live state. Every change is written to the database by a single
background thread (`backend/app/persistence.py`), so database latency never stalls the
animation. The Inventory search, bundle history and DB statistics read from the database; the
3D twin streams live state over WebSocket.

## API overview

| Endpoint | Purpose |
|---|---|
| `GET /api/layout` | Warehouses, zones, bays, stacks, aisle graph, anchors, dock, gate |
| `WS /ws` | `state` (10 Hz), `inventory` (on change), `events`, `ops` (1 Hz) |
| `POST /api/sim/{start,pause,reset,speed,autopilot,auto-putaway}` | Simulation control |
| `POST /api/scenario/{1,2,3}` (`{"inject": "wrong" \| "missing"}`) | Scripted scenarios |
| `POST /api/ops/{receive,order,pick,dispatch,gate,inject,resolve}` | Manual operations |
| `GET /api/inventory/bundles?q=` · `GET /api/bundles/{id}/history` | Database search and history |
| `GET /api/orders[/{no}]` · `GET /api/oracle/log` · `GET /api/analytics` · `GET /api/replay` | Read models |

## Path to production

* Replace `oracle_mock.py` with an Oracle EBS/Fusion adapter (pick release in, move order and
  ship confirm out). The message shapes are already in the integration log.
* Feed real fork-mounted RFID reads and UWB positions into the engine's events instead of
  simulated ones. Forklift motion then comes from telemetry rather than the route planner.
* The putaway, picking (with rehandle planning) and gate reconciliation logic carries over
  unchanged.
