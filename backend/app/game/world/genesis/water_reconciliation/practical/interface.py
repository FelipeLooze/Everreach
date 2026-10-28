"""A local finite-volume interface has one canonical point/head on both views."""
from ...sphere_topology import SurfacePoint
from ...terrain.field import checksum


def interface_contract(terrain_signature, endpoints, point, terrain_mm, head_mm):
    pair = sorted([list(SurfacePoint(*p).xyz) for p in endpoints])
    canonical = list(SurfacePoint(*point).xyz)
    identity = "k1-interface:"+checksum([terrain_signature, pair, canonical])[:32]
    common = {"id": identity, "point": canonical, "terrain_mm": terrain_mm, "head_mm": head_mm}
    return {"version": 1, "source_view": {**common, "side": "outgoing"},
            "receiver_view": {**common, "side": "incoming"},
            "scope": "internal_shared_interface_no_unprepared_region_is_assumed_blocked"}
