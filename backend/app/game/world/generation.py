"""Phase 15A — World generation identity.

A Campaign owns one root world_seed (Campaign.world_seed). Every generated
piece of the world (regions now, subregions/settlements/etc. in later
subphases) derives its own seed from that root via derive_seed, salted by
a stable string key — never drawn independently at random. This is what
makes "reproducibility where useful" (Phase 15A spec) actually hold: the
same campaign world_seed always produces the same region generation_seed,
regardless of process, machine or Python version (hashlib, not
random.Random, so we never depend on stdlib PRNG seeding stability).

generation_version exists separately from the seed: it records which
generator *logic* produced a piece of world content, so a future rewrite
of the generator (v2, v3...) never silently regenerates or reinterprets
content a save already persisted under an earlier version (see Phase 15
spec's own "GENERATION VERSIONING" section).
"""

import hashlib

CURRENT_REGION_GENERATION_VERSION = 1


def derive_seed(seed: int, salt: str) -> int:
    """Deterministically derive a child seed from a parent seed + a stable
    salt key (e.g. "region:0", "subregion:3"). Same inputs always produce
    the same output, independent of Python's random module internals."""
    digest = hashlib.sha256(f"{seed}:{salt}".encode("utf-8")).digest()
    # Masked to 63 bits so it always fits SQLite's signed 64-bit INTEGER,
    # matching the range random.SystemRandom().getrandbits(63) already uses.
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)
