"""Simulation engine behaviour: the three customer demo scenarios and invariants."""
import pytest

from app.sim.engine import Simulation


def run(sim, seconds, dt=0.05, until=None):
    for _ in range(int(seconds / dt)):
        sim.step(dt)
        if until and until(sim):
            return True
    return False


@pytest.fixture
def sim():
    s = Simulation(seed=42)
    s.speed = 1
    return s


def check_invariants(sim):
    seen = set()
    for sid, lst in sim.stack_bundles.items():
        st = sim.layout.stacks[sid]
        assert len(lst) <= st.max_levels, sid
        for lvl, bid in enumerate(lst, 1):
            assert bid not in seen
            seen.add(bid)
            assert sim.bundles[bid]["loc"] == {"kind": "stack", "stack": sid, "level": lvl}
    for f in sim.forklifts.values():
        if f.load:
            assert sim.bundles[f.load]["loc"] == {"kind": "forklift", "forklift": f.id}


def test_seed_is_consistent(sim):
    check_invariants(sim)
    assert len(sim.forklifts) == 8
    assert sum(f.role == "PUTAWAY" for f in sim.forklifts.values()) == 4
    assert sim.orders["SO-45891"]["status"] == "STAGED"
    assert "SO-45892" in [o["order_number"] for o in sim.eligible_orders()]
    epcs = [b["epc"] for b in sim.bundles.values()]
    assert len(set(epcs)) == len(epcs)


def test_scenario_1_putaway_by_f01(sim):
    sc = sim.start_scenario(1)
    bid = sc["focus"]["bundle"]
    assert run(sim, 300, until=lambda s: s.scenario["status"] == "DONE")
    b = sim.bundles[bid]
    assert b["status"] == "STORED" and b["loc"]["kind"] == "stack"
    assert b["last_move"]["forklift"] == "F-01"
    assert sim.layout.stacks[b["loc"]["stack"]].kind == "STORAGE"
    check_invariants(sim)


def test_scenario_2_picking_with_rehandle(sim):
    sim.start_scenario(2)
    assert run(sim, 900, until=lambda s: s.scenario["status"] == "DONE")
    o = sim.orders["SO-45892"]
    assert o["status"] == "STAGED"
    assert all(sim.bundles[b]["status"] == "STAGED" for b in o["bundles"])
    assert sim.kpi["relocations"] >= 1  # one SO-45892 bundle was seeded under another bundle
    assert any(t["forklift"] == "F-05" and t["type"] == "PICK" for t in sim.tasks.values())
    check_invariants(sim)


def test_scenario_3_clean_dispatch(sim):
    sim.start_scenario(3)
    assert run(sim, 600, until=lambda s: s.orders["SO-45891"]["status"] == "DISPATCHED")
    assert sim.kpi["first_pass_ok"] == 1 and sim.kpi["exceptions"] == 0
    assert all(s["done"] for s in sim.scenario["steps"])


@pytest.mark.parametrize("kind,field", [("wrong", "unexpected"), ("missing", "missing")])
def test_scenario_3_exception_then_resolution(sim, kind, field):
    sim.start_scenario(3, kind)
    assert run(sim, 600, until=lambda s: s.exceptions)
    exc = sim.exceptions[0]
    assert len(exc[field]) == 1
    assert sim.orders["SO-45891"]["status"] == "EXCEPTION"
    assert run(sim, 60, until=lambda s: next(iter(s.trucks.values()))["state"] == "EXCEPTION")
    sim.resolve_exception()
    assert run(sim, 900, until=lambda s: s.orders["SO-45891"]["status"] == "DISPATCHED")
    o = sim.orders["SO-45891"]
    mf = sim.manifests[o["manifest"]]
    assert mf["result"]["ok"]
    check_invariants(sim)


def test_autopilot_steady_state():
    s = Simulation(seed=3)
    s.speed = 1
    s.autopilot = True
    run(s, 2 * 3600, dt=0.1)
    assert s.kpi["trucks_dispatched"] >= 15
    assert s.kpi["putaways"] >= 80
    assert s._storage_fill() < 0.95
    check_invariants(s)


def test_reset_restores_seed(sim):
    sim.start_scenario(2)
    run(sim, 100)
    sim.reset()
    assert sim.orders["SO-45892"]["status"] == "BOOKED"
    assert sim.kpi["picks"] == 0
