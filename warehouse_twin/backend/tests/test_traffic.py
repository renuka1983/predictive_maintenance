"""Traffic rules: right-hand lanes, long-load fork side choice and collision avoidance."""
import math

from app.layout import LANE_OFFSET, LANE_OFFSET_FORKS_LEFT, heading_of
from app.sim.engine import Simulation, angdiff
from app.sim.traffic import footprint, overlap


def test_lanes_keep_right():
    s = Simulation(seed=1)
    lay = s.layout
    route = [lay.node(x, 15.0) for x in (-62.5, -53.5, -46.5)]  # eastbound along service aisle z=15
    east = [p for p, _, _ in s._lane_polyline(route)]
    assert all(abs(z - (15.0 + LANE_OFFSET)) < 1e-9 for _, z in east)   # +z is south = right of east
    west = [p for p, _, _ in s._lane_polyline(route[::-1])]
    assert all(abs(z - (15.0 - LANE_OFFSET)) < 1e-9 for _, z in west)


def test_loaded_forklift_arrives_facing_the_stack_without_spinning():
    s = Simulation(seed=42)
    f = s.forklifts["F-05"]
    f.load = next(iter(s.bundles))
    st = s.layout.stacks["WH01-Z03-B010-S02"]  # on the left of westbound travel
    mv = s._plan(f, st.node, [st.pre], final_heading=st.heading)
    *_, last_lane, pre = mv["pts"]
    last_mode = mv["modes"][-2]
    assert last_mode == "sideL"  # forks already point at the stack
    dx, dz = last_lane[0] - mv["pts"][-3][0], last_lane[1] - mv["pts"][-3][1]
    assert abs(angdiff(s._mode_heading(last_mode, dx, dz), st.heading)) < 1e-6
    assert abs(abs(last_lane[1] - 15.0) - LANE_OFFSET_FORKS_LEFT) < 1e-9


def test_footprint_overlap_geometry():
    a = footprint(0, 0, 0, None)
    assert overlap(a, footprint(2.0, 0, math.pi, None))
    assert not overlap(a, footprint(0, 2 * LANE_OFFSET, 0, None))  # opposite lanes pass cleanly
    loaded = footprint(0, 0, heading_of(0, 1), 6.0)  # sideways, bundle along x
    assert not overlap(loaded, footprint(0, -2 * LANE_OFFSET, heading_of(-1, 0), None))


def test_no_head_on_traffic_and_little_contact_in_an_autopilot_hour():
    s = Simulation(seed=3)
    s.speed = 1
    s.autopilot = True
    ids = list(s.forklifts)
    prev = {f.id: (f.x, f.z) for f in s.forklifts.values()}
    contact = head_on = 0
    for i in range(36000):
        s.step(0.1)
        if i % 5:
            continue
        vel, fps = {}, {}
        for f in s.forklifts.values():
            dx, dz = f.x - prev[f.id][0], f.z - prev[f.id][1]
            prev[f.id] = (f.x, f.z)
            vel[f.id] = (dx, dz) if math.hypot(dx, dz) > 0.2 else None
            fps[f.id] = footprint(f.x, f.z, f.heading, s._load_len(f))
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                if overlap(fps[ids[a]], fps[ids[b]]):
                    contact += 1
                    va, vb = vel[ids[a]], vel[ids[b]]
                    if va and vb and (va[0] * vb[0] + va[1] * vb[1]) / (math.hypot(*va) * math.hypot(*vb)) < -0.7:
                        head_on += 1
    # before right-hand lanes + yielding this seed produced ~370 head-on and ~1,400 contact samples
    assert head_on <= 25
    assert contact <= 400
    assert s.kpi["yields"] > 0
    assert s.kpi["trucks_dispatched"] >= 10
