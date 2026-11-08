"""Write-behind persistence of simulation state into the relational model.

The simulation engine is the live source of truth and runs in the asyncio
loop; every state change it makes is queued here and written to the database
by a single background thread, so database latency never stalls animation.
"""
from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime

from sqlalchemy import create_engine, delete, event
from sqlalchemy.orm import Session, sessionmaker

from . import models as m

log = logging.getLogger("persistence")


def make_engine(url: str):
    kwargs = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _pragma(conn, _):  # pragma: no cover - trivial
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()
    return eng


def _dt(s):
    if s is None or isinstance(s, datetime):
        return s
    return datetime.fromisoformat(s)


class Persistence:
    def __init__(self, url: str, enabled: bool = True):
        self.enabled = enabled
        self.engine = make_engine(url)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        m.Base.metadata.create_all(self.engine)
        self.q: queue.Queue = queue.Queue()
        self.generation = 0
        self._stop = threading.Event()
        self.writes = 0
        self.errors = 0
        self._thread = threading.Thread(target=self._run, name="db-writer", daemon=True)
        self._thread.start()

    # ---------------------------------------------------------------- worker
    def _run(self):
        while not self._stop.is_set():
            try:
                first = self.q.get(timeout=0.25)
            except queue.Empty:
                continue
            batch = [first]
            while len(batch) < 500:
                try:
                    batch.append(self.q.get_nowait())
                except queue.Empty:
                    break
            live = [(fn, args) for gen, fn, args in batch if gen == self.generation or fn == self._op_reset]
            try:
                with self.Session() as s:
                    for fn, args in live:
                        fn(s, *args)
                    s.commit()
                self.writes += len(live)
            except Exception:
                log.warning("persistence batch failed; retrying operations one by one", exc_info=True)
                for fn, args in live:  # isolate the bad operation instead of losing the whole batch
                    try:
                        with self.Session() as s:
                            fn(s, *args)
                            s.commit()
                        self.writes += 1
                    except Exception:  # pragma: no cover - logged for operators
                        self.errors += 1
                        log.exception("persistence operation %s failed", getattr(fn, "__name__", fn))
            finally:
                for _ in batch:
                    self.q.task_done()

    def submit(self, fn, *args):
        if self.enabled:
            self.q.put((self.generation, fn, args))

    def flush(self, timeout: float = 10.0):
        if not self.enabled:
            return
        done = threading.Event()
        self.q.put((self.generation, lambda s: done.set(), ()))
        done.wait(timeout)

    def stop(self):
        self._stop.set()

    # -------------------------------------------------------------- reset/seed
    def reset(self, seed: dict):
        """Wipe all tables and load master + initial data. ``seed`` holds plain dicts."""
        self.generation += 1
        if self.enabled:
            self.q.put((self.generation, self._op_reset, (seed,)))

    @staticmethod
    def _op_reset(s: Session, seed: dict):
        for table in reversed(m.Base.metadata.sorted_tables):
            s.execute(delete(table))
        s.flush()
        for key, model in (("warehouses", m.Warehouse), ("zones", m.WarehouseZone), ("bays", m.WarehouseBay)):
            s.add_all(model(**row) for row in seed[key])
            s.flush()
        s.add_all(m.BundleStack(**row) for row in seed["stacks"])
        s.flush()
        s.add_all(m.BundleStackLevel(**row) for row in seed["levels"])
        s.flush()
        s.add_all(m.Bundle(**{**row, "produced_at": _dt(row["produced_at"])}) for row in seed["bundles"])
        s.flush()
        s.add_all(m.RfidTag(**{**row, "associated_at": _dt(row["associated_at"])}) for row in seed["tags"])
        s.add_all(m.BundleLocation(**{**row, "updated_at": _dt(row["updated_at"])}) for row in seed["locations"])
        s.flush()
        s.add_all(m.Forklift(**row) for row in seed["forklifts"])
        s.flush()
        s.add_all(m.ForkliftPosition(**{**row, "updated_at": _dt(row["updated_at"])}) for row in seed["positions"])
        for o in seed["orders"]:
            Persistence._op_order(s, o)
        s.flush()
        for mf in seed["manifests"]:
            Persistence._op_manifest(s, mf)

    # ----------------------------------------------------------------- ops
    @staticmethod
    def _op_bundle(s: Session, b: dict):
        s.merge(m.Bundle(**{**b, "produced_at": _dt(b["produced_at"])}))

    @staticmethod
    def _op_tag(s: Session, t: dict):
        s.merge(m.RfidTag(**{**t, "associated_at": _dt(t["associated_at"])}))

    @staticmethod
    def _op_location(s: Session, loc: dict):
        s.merge(m.BundleLocation(**{**loc, "updated_at": _dt(loc["updated_at"])}))

    @staticmethod
    def _op_level(s: Session, stack_id: str, level: int, bundle_id, height: int):
        row = s.get(m.BundleStackLevel, f"{stack_id}-L{level:02d}")
        if row is not None:
            row.bundle_id = bundle_id
        st = s.get(m.BundleStack, stack_id)
        if st is not None:
            st.current_height = height

    @staticmethod
    def _op_status(s: Session, bundle_id: str, status: str):
        b = s.get(m.Bundle, bundle_id)
        if b is not None:
            b.status = status

    @staticmethod
    def _op_movement(s: Session, ev: dict):
        s.add(m.MovementEvent(**{**ev, "ts": _dt(ev["ts"])}))

    @staticmethod
    def _op_task(s: Session, t: dict):
        s.merge(m.MovementTask(**{**t, **{k: _dt(t.get(k)) for k in ("created_at", "started_at", "finished_at")}}))

    @staticmethod
    def _op_positions(s: Session, rows: list):
        for r in rows:
            s.merge(m.ForkliftPosition(**{**r, "updated_at": _dt(r["updated_at"])}))

    @staticmethod
    def _op_order(s: Session, o: dict):
        s.merge(m.SalesOrder(
            order_number=o["order_number"], customer=o["customer"], ship_to=o["ship_to"], carrier=o["carrier"],
            status=o["status"], priority=o["priority"], booked_at=_dt(o.get("booked_at")),
            released_at=_dt(o.get("released_at")), staged_at=_dt(o.get("staged_at")),
            dispatched_at=_dt(o.get("dispatched_at")), lines=o["lines"],
        ))
        for bid in o.get("bundles", []):
            s.merge(m.SalesOrderBundle(id=f"{o['order_number']}:{bid}", order_number=o["order_number"],
                                       bundle_id=bid, status=o["status"]))

    @staticmethod
    def _op_manifest(s: Session, mf: dict):
        s.merge(m.DispatchManifest(
            id=mf["id"], order_number=mf["order_number"], truck_id=mf["truck_id"], truck_plate=mf["truck_plate"],
            expected_epcs=mf["expected_epcs"], status=mf["status"], created_at=_dt(mf["created_at"]),
            validated_at=_dt(mf.get("validated_at")), result=mf.get("result"),
        ))

    @staticmethod
    def _op_dispatch_event(s: Session, ev: dict):
        s.add(m.DispatchEvent(**{**ev, "ts": _dt(ev["ts"])}))

    @staticmethod
    def _op_sim_event(s: Session, ev: dict):
        s.add(m.SimulationEvent(id=ev["id"], ts=_dt(ev["ts"]), sim_t=ev["t"], type=ev["type"],
                                severity=ev["severity"], message=ev["message"], refs=ev["refs"]))

    # public helpers --------------------------------------------------------
    def bundle(self, b): self.submit(self._op_bundle, b)
    def tag(self, t): self.submit(self._op_tag, t)
    def location(self, loc): self.submit(self._op_location, loc)
    def level(self, stack_id, level, bundle_id, height): self.submit(self._op_level, stack_id, level, bundle_id, height)
    def status(self, bundle_id, status): self.submit(self._op_status, bundle_id, status)
    def movement(self, ev): self.submit(self._op_movement, ev)
    def task(self, t): self.submit(self._op_task, t)
    def positions(self, rows): self.submit(self._op_positions, rows)
    def order(self, o): self.submit(self._op_order, o)
    def manifest(self, mf): self.submit(self._op_manifest, mf)
    def dispatch_event(self, ev): self.submit(self._op_dispatch_event, ev)
    def sim_event(self, ev): self.submit(self._op_sim_event, ev)
