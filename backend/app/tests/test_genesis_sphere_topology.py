import json
import math
import os
import subprocess
import sys

import pytest

from app.game.world.genesis.sphere_config import SphereConfig, parse_config
from app.game.world.genesis.sphere_geography import elevation_at, generate_sector, global_plan
from app.game.world.genesis.sphere_metric import advance, distance_m, from_lat_lon
from app.game.world.genesis.sphere_topology import (
    CellKey, DIRECTIONS, SurfacePoint, cell_at, cell_center, cell_contains,
    cell_vertices, edge_points, face_point, nearby_cells, neighbor, owning_face,
)


@pytest.mark.parametrize("kwargs", [{"radius_m": 0}, {"radius_m": float("inf")},
    {"sector_level": 25}, {"macro_level": 13}, {"sample_intervals": True},
    {"sample_intervals": 3}, {"topology": "cylinder"}, {"generator_version": 1}])
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        SphereConfig(**kwargs)


@pytest.mark.parametrize("data", [{}, {"config_version": 4}, {"config_version": True},
                                  {"config_version": 2, "generator_version": 999}])
def test_configuration_dispatch_fails_closed(data):
    with pytest.raises(ValueError):
        parse_config(data)


def test_address_validation_and_canonicalization():
    assert SurfacePoint(4, -8, 12) == SurfacePoint(1, -2, 3)
    for xyz in ((0, 0, 0), (True, 1, 1), (1.5, 0, 0), (2**54, 1, 0)):
        with pytest.raises(ValueError):
            SurfacePoint(*xyz)
    for address in ((6, 2, 0, 0), (0, -1, 0, 0), (0, 2, 4, 0), (True, 1, 0, 0)):
        with pytest.raises(ValueError):
            CellKey(*address)
    with pytest.raises(ValueError):
        face_point(0, 3, 0, 2)
    with pytest.raises(ValueError):
        nearby_cells(CellKey(0, 0, 0, 0), 5)


@pytest.mark.parametrize("level", [0, 1, 3, 24])
def test_every_face_has_unique_address_roundtrip_and_sparse_neighbors(level):
    size = 2**level
    for face in range(6):
        for x, y in {(0, 0), (size-1, size-1), (size//2, size//2)}:
            key = CellKey(face, level, x, y)
            assert cell_at(cell_center(key), level) == key
            for vertex in cell_vertices(key):
                assert cell_contains(key, vertex)
            assert key.parent(0) == CellKey(face, 0, 0, 0)
            nearby = nearby_cells(key, 4)
            assert nearby[0] == key
            assert len(set(nearby)) == len(nearby) <= 341


@pytest.mark.parametrize("face", range(6))
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_every_oriented_face_edge_and_corner_is_reciprocal_and_continuous(face, direction):
    config = SphereConfig(sector_level=3)
    size = 2**config.sector_level
    for offset in range(size):
        x = 0 if direction == "west" else size-1 if direction == "east" else offset
        y = 0 if direction == "south" else size-1 if direction == "north" else offset
        key = CellKey(face, config.sector_level, x, y)
        other = neighbor(key, direction)
        assert other.face != face
        reverse = [d for d in DIRECTIONS if neighbor(other, d) == key]
        assert len(reverse) == 1
        points = edge_points(key, direction)
        opposite_points = edge_points(other, reverse[0])
        assert points == opposite_points or points == opposite_points[::-1]
        a, b = generate_sector(42, config, key), generate_sector(42, config, other)
        def edge(heights, d):
            return ([row[0 if d == "west" else -1] for row in heights]
                    if d in ("west", "east") else heights[0 if d == "south" else -1])
        values = edge(a["elevation_m"], direction)
        other_values = edge(b["elevation_m"], reverse[0])
        assert values == other_values or values == other_values[::-1]
        assert values == [elevation_at(42, config, p) for p in points]
        for p in points:
            assert cell_contains(key, p) and cell_contains(other, p)


def test_internal_sector_continuity_and_lattice_plane_continuity():
    config = SphereConfig(sector_level=8)
    key = CellKey(0, 8, 99, 100)
    for direction in DIRECTIONS:
        other = neighbor(key, direction)
        assert key in [neighbor(other, d) for d in DIRECTIONS]
        assert set(edge_points(key, direction)) & set(cell_vertices(other))
    # Perturb a face seam and a triple-face vertex on each side by a tiny angle.
    for xyz in ((10**12, 10**12, 0), (10**12, 10**12, 10**12)):
        values = [elevation_at(42, config, SurfacePoint(*(v+(i == axis) for i, v in enumerate(xyz))))
                  for axis in range(3)]
        assert max(values)-min(values) <= 2


def test_all_cube_vertices_are_shared_by_three_faces_and_low_resolution_surface_is_connected():
    vertices = {}
    for face in range(6):
        for point in cell_vertices(CellKey(face, 0, 0, 0)):
            vertices.setdefault(point, set()).add(face)
    assert len(vertices) == 8
    assert all(len(faces) == 3 for faces in vertices.values())
    visited, frontier = set(), {CellKey(0, 2, 0, 0)}
    while frontier:
        visited.update(frontier)
        frontier = {neighbor(key, d) for key in frontier for d in DIRECTIONS} - visited
    assert len(visited) == 6*4**2
    # Radius changes metres, never chart addresses or terrain stream.
    p = SurfacePoint(1, 1, 1)
    assert elevation_at(42, SphereConfig(radius_m=1000), p) == elevation_at(
        42, SphereConfig(radius_m=1_000_000_000_000), p)


@pytest.mark.parametrize("sign", [-1, 1])
def test_poles_are_regular_points_and_can_be_crossed(sign):
    config = SphereConfig()
    pole = SurfacePoint(0, 0, sign)
    assert owning_face(pole) == (4 if sign > 0 else 5)
    assert from_lat_lon(sign*90, -180) == from_lat_lon(sign*90, 37) == pole
    start = from_lat_lon(sign*89, 0)
    step = math.pi/90*config.radius_m
    end = advance(config, start, 0 if sign > 0 else 180, step)
    expected = from_lat_lon(sign*89, 180)
    assert distance_m(config, end, expected) < 1e-6
    assert distance_m(config, pole, advance(config, pole, 0, 1000)) == pytest.approx(1000, abs=1e-6)


@pytest.mark.parametrize("radius", [1000, 6_371_000, 1_000_000_000_000])
def test_spherical_metric_and_global_displacement(radius):
    config = SphereConfig(radius_m=radius)
    x, y, negx = SurfacePoint(1, 0, 0), SurfacePoint(0, 1, 0), SurfacePoint(-1, 0, 0)
    assert distance_m(config, x, x) == 0
    assert distance_m(config, x, y) == pytest.approx(math.pi*radius/2)
    assert distance_m(config, x, negx) == pytest.approx(math.pi*radius)
    assert distance_m(config, y, x) == distance_m(config, x, y)
    assert distance_m(config, advance(config, x, 90, math.tau*radius), x) < 0.01
    assert distance_m(config, advance(config, x, 90, math.pi*radius/2), y) < 0.01
    before, after = from_lat_lon(0, 179.9), from_lat_lon(0, -179.9)
    assert distance_m(config, before, after) == pytest.approx(math.radians(0.2)*radius)
    assert distance_m(config, x, y) > math.sqrt(2)*radius  # arc, not chord


def test_displacement_invalid_inputs_and_exact_zero():
    p, config = SurfacePoint(1, 2, 3), SphereConfig()
    assert advance(config, p, 45, 0) is p
    for bearing, length in ((float("nan"), 1), (0, -1), (0, float("inf"))):
        with pytest.raises(ValueError):
            advance(config, p, bearing, length)
    with pytest.raises(ValueError):
        from_lat_lon(91, 0)


def test_geodesic_crosses_cube_seam_without_jump():
    config = SphereConfig(sector_level=10)
    start = from_lat_lon(0, 44.9)
    result = [advance(config, start, 90, i*1000) for i in range(25)]
    keys = [cell_at(p, config.sector_level) for p in result]
    assert {key.face for key in keys} == {0, 2}
    assert len(set(keys)) >= 4
    for a, b in zip(result, result[1:]):
        assert distance_m(config, a, b) == pytest.approx(1000, abs=1e-6)


def test_plan_is_constant_size_and_generation_order_and_cross_process_are_stable():
    config = SphereConfig()
    keys = [CellKey(0, 10, 1023, 512), CellKey(2, 10, 0, 512), CellKey(4, 10, 512, 512)]
    forward = {k: generate_sector(42, config, k) for k in keys}
    reverse = {k: generate_sector(42, config, k) for k in reversed(keys)}
    assert forward == reverse
    assert generate_sector(43, config, keys[0]) != forward[keys[0]]
    assert len(json.dumps(global_plan(42, SphereConfig(sector_level=24)))) < 1000
    source = ("import json; from app.game.world.genesis.sphere_config import SphereConfig; "
              "from app.game.world.genesis.sphere_geography import generate_sector; "
              "from app.game.world.genesis.sphere_topology import CellKey; "
              "print(json.dumps(generate_sector(42,SphereConfig(),CellKey(0,10,1023,512)), sort_keys=True))")
    outputs = [subprocess.check_output([sys.executable, "-c", source], text=True,
               env={**os.environ, "PYTHONHASHSEED": value}) for value in ("12", "777")]
    assert outputs[0] == outputs[1]
    assert json.loads(outputs[0]) == forward[keys[0]]
    assert elevation_at(42, config, SurfacePoint(1, 1, 0)) == 4872  # v2 replay vector
