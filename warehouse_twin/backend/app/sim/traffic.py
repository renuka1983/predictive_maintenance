"""Forklift footprints and collision geometry used by the traffic manager.

A footprint is an oriented rectangle in the forklift's local frame (+x forward,
forks at the front). When loaded, the bundle lies across the forks, so the
footprint widens to the bundle length.
"""
from __future__ import annotations

import math

REAR = 1.3        # chassis/counterweight behind the forklift centre
FRONT = 2.65      # fork tips ahead of the forklift centre
HALF_W = 0.72     # half the chassis width


PARKED_FRONT = 1.35  # forks lowered inside the parking bay: only the chassis matters


def footprint(x: float, z: float, h: float, load_len: float | None, front: float = FRONT) -> list[tuple[float, float]]:
    hw = max(HALF_W, load_len / 2) if load_len else HALF_W
    c, s = math.cos(h), math.sin(h)
    out = []
    for lx, lz in ((-REAR, -hw), (front, -hw), (front, hw), (-REAR, hw)):
        # same convention as three.js rotation.y = h with the model facing local +x
        out.append((x + lx * c + lz * s, z - lx * s + lz * c))
    return out


def _axes(poly):
    for i in range(2):
        (x0, z0), (x1, z1) = poly[i], poly[i + 1]
        dx, dz = x1 - x0, z1 - z0
        n = math.hypot(dx, dz) or 1.0
        yield (-dz / n, dx / n)


def overlap(a: list, b: list, margin: float = 0.0) -> bool:
    """Separating-axis test for two convex quads, inflated by ``margin``."""
    for ax, az in list(_axes(a)) + list(_axes(b)):
        pa = [px * ax + pz * az for px, pz in a]
        pb = [px * ax + pz * az for px, pz in b]
        if max(pa) + margin < min(pb) or max(pb) + margin < min(pa):
            return False
    return True


def bbox(poly: list) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    zs = [p[1] for p in poly]
    return min(xs), min(zs), max(xs), max(zs)


def overlap_bb(a: list, abb: tuple, b: list, bbb: tuple, margin: float = 0.0) -> bool:
    """Bounding-box pre-check, then the exact separating-axis test."""
    if abb[2] + margin < bbb[0] or bbb[2] + margin < abb[0] or abb[3] + margin < bbb[1] or bbb[3] + margin < abb[1]:
        return False
    return overlap(a, b, margin)
