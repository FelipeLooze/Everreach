import json

from app.game.world.generation import derive_seed


def coordinate_seed(seed: int, version: int, subsystem: str, *coordinates: int) -> int:
    """Independent addressable entropy; no shared mutable random stream."""
    address = json.dumps(["genesis", version, subsystem, *coordinates], separators=(",", ":"))
    return derive_seed(seed, address)
