"""Sparse, deterministic WGS2 multi-cell footprint contract.

Coverage is classified by cell-centre containment on the sphere. It is a
physical footprint index, not a navigation graph or a player-facing map.
"""
from __future__ import annotations

from types import SimpleNamespace
from .sphere_metric import distance_m
from .sphere_topology import CellKey, SurfacePoint, cell_at, cell_center, neighbor, DIRECTIONS

VERSION = "WGS2_COVERAGE_V2"
MAX_SEARCH_HOPS = 8


def footprint_cells(center: SurfacePoint, level: int, radius_m: int, span_m: int) -> tuple[CellKey, ...]:
    """Return all nearby TP1 cells whose centres lie in a spherical disc.

    The eight-edge-hop bound covers the WGS2 V2 span cap (3.4 km) at the
    pinned TP1 scale, including cube-chart edge distortion. An explicit error
    prevents silent truncation if a future world config breaks that bound.
    """
    if radius_m <= 0 or span_m <= 0:
        raise ValueError("coverage needs positive planetary radius and span")
    center_cell = cell_at(center, level)
    metric = SimpleNamespace(radius_m=radius_m)
    result = {center_cell}
    frontier = {center_cell}
    for hop in range(1, MAX_SEARCH_HOPS + 1):
        layer = {neighbor(key, direction) for key in frontier for direction in DIRECTIONS} - result
        if hop == MAX_SEARCH_HOPS and any(
            distance_m(metric, center, cell_center(key)) <= span_m / 2 for key in layer
        ):
            raise RuntimeError("WGS2 coverage exceeds its bounded eight-cell-hop index")
        result.update(layer)
        frontier = layer
    result = tuple(sorted(
        key for key in result
        if distance_m(metric, center, cell_center(key)) <= span_m / 2
    ))
    return result or (center_cell,)


def contract_checksum(formation_key: str, cells: tuple[CellKey, ...], span_m: int) -> str:
    from .terrain.field import checksum
    return checksum({"version": VERSION, "formation_key": formation_key,
                     "span_m": span_m, "cells": [vars(cell) for cell in cells]})


def persisted_coverage_valid(rows, formation_key: str, span_m: int) -> bool:
    if not rows or any(row.contract_version != VERSION for row in rows):
        return False
    cells = tuple(sorted(CellKey(row.face, row.level, row.x, row.y) for row in rows))
    expected = contract_checksum(formation_key, cells, span_m)
    return all(row.contract_checksum == expected for row in rows)
