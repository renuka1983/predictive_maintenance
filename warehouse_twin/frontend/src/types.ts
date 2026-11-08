export type Rect = [number, number, number, number];

export interface StackDef {
  id: string; code: string; bay: string; zone: string; warehouse: string;
  kind: 'STORAGE' | 'RECEIVING' | 'STAGING'; x: number; z: number; maxLevels: number; yaw: number; lane: string | null;
}
export interface ZoneDef { id: string; code: string; warehouse_id: string; name: string; kind: string; rect: Rect; color: string }
export interface BayDef { id: string; code: string; zone_id: string; warehouse_id: string; rect: Rect; label: string }
export interface Layout {
  plant: string;
  bundle: { length: number; width: number; height: number; dunnage: number; pitch: number };
  warehouses: { id: string; name: string; kind: string; bounds: Rect }[];
  zones: ZoneDef[]; bays: BayDef[]; stacks: StackDef[];
  parking: { id: string; x: number; z: number; heading: number; warehouse: string }[];
  anchors: { id: string; x: number; y: number; z: number; warehouse: string }[];
  doors: { id: string; name: string; x: number; z: number; width: number; height: number }[];
  dock: { x: number; z: number; heading: number };
  truck: { cols: number[]; levels: number; bed: number };
  gate: { x: number; z: number; width: number; height: number };
  graph: { nodes: Record<string, [number, number]>; edges: [string, string][] };
  lanes: Record<string, string[]>;
}

export interface ForkliftTask { id: string; type: string; bundle: string; barcode: string; order: string | null; from: string; to: string }
export interface ForkliftLive {
  id: string; name: string; role: 'PUTAWAY' | 'PICKING'; roleLabel: string; state: string;
  x: number; z: number; h: number; fork: number; load: string | null; loadBarcode: string | null;
  task: ForkliftTask | null; queued: number; dest: { x: number; z: number; label: string } | null;
  route: [number, number][]; battery: number; util: number; distance: number; done: number; warehouse: string; uwbErr: number;
  history?: HistoryEntry[];
}
export interface HistoryEntry {
  task: string; type: string; bundle: string; barcode: string; from: string; to: string; order: string | null;
  start: string; end: string; duration_s: number; distance_m: number;
}
export interface TruckLive { id: string; plate: string; carrier: string; order: string; state: string; x: number; z: number; h: number; manifest: string | null; onBoard: number }
export interface ScenarioStep { label: string; done: boolean; t: string | null; detail?: string; error?: boolean }
export interface Scenario { id: number; title: string; status: 'RUNNING' | 'DONE'; cursor: number; started: string; focus: Record<string, string | null>; steps: ScenarioStep[] }
export interface GateResult { ok: boolean; expected: number; read: number; matched: number; missing: ExcItem[]; unexpected: ExcItem[]; ts: string }
export interface ExcItem { epc: string; bundle: string; barcode: string; so: string; customer: string; location: string }
export interface SimState {
  t: number; clock: string; running: boolean; speed: number; autopilot: boolean; autoPutaway: boolean;
  forklifts: ForkliftLive[]; trucks: TruckLive[];
  gate: { state: string; truck: string | null; result: GateResult | null; reads: number };
  invVersion: number; scenario: Scenario | null;
}
export interface BundleBrief {
  id: string; bc: string; so: string; w: 'bare' | 'film' | 'paper' | 'kraft'; st: string; len: number; p: string;
  loc: { k: 's'; s: string; l: number } | { k: 'f'; f: string } | { k: 't'; t: string; c: number; l: number } | { k: string };
}
export interface SimEvent { id: number; t: number; ts: string; type: string; severity: 'info' | 'success' | 'warning' | 'error'; message: string; refs: Record<string, any> }
export interface OrderSummary {
  order_number: string; customer: string; ship_to: string; carrier: string; status: string; priority: string;
  booked_at: string; released_at: string | null; staged_at: string | null; dispatched_at: string | null;
  lane: string | null; truck: string | null; manifest: string | null;
  lines: { line: number; product: string; description: string; alloy: string; finish: string; qty_bundles: number }[];
  bundle_count: number; in_stock: number; staged: number; loaded: number; inject_wrong?: boolean; inject_missing?: boolean;
}
export interface TaskRow { id: string; type: string; status: string; bundle: string; barcode: string; order: string | null; forklift: string | null; from: string; to: string; created: string; duration_s: number | null; distance_m: number; note: string }
export interface DispatchException { id: string; order: string; truck: string; plate: string; manifest: string; missing: ExcItem[]; unexpected: ExcItem[]; ts: string; resolved: boolean }
export interface Ops {
  orders: OrderSummary[]; booked: number; eligible: string[];
  queue: { id: string; type: string; bundle: string; barcode: string; order: string | null; prefer: string | null; waiting_s: number; to: string | null }[];
  active: TaskRow[]; recent: TaskRow[]; exceptions: DispatchException[]; lanes: Record<string, string | null>;
  kpi: Record<string, number>; inventory: Record<string, number>; dock: TruckLive | null;
}
export type Selection = { kind: 'bundle' | 'forklift' | 'truck' | 'stack'; id: string } | null;
export interface Replay { task: TaskRow; path: [number, number][]; forklift: string; bundle: string; barcode: string; wrap: string; duration_s: number; role: string; startedAt?: number }
