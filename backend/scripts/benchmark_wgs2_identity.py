"""Bounded warm microbenchmark of the unchanged selector and V5 fact adapter."""
import json
import tracemalloc
from time import perf_counter

from app.game.world.genesis.local_formations import catalog
from app.game.world.genesis.wgs2_families import candidate, VERSION_V2, SUPPORTED
from app.game.world.genesis.wgs2_identity import facts


def main():
    records = catalog()
    cells = [{"face": index % 6, "level": 17, "x": 20_000 + index // 6,
              "y": 30_000 + index // 6} for index in range(2_000)]
    tracemalloc.start()
    t = perf_counter()
    selected = [candidate(42, cell, records, version=VERSION_V2) for cell in cells]
    selector_ms = (perf_counter() - t) * 1_000
    t = perf_counter()
    shaped = [facts(item, records[item],
        {"horizontal_span_m": 500, "orientation_degrees": 90}, {},
        {"context": {"height_mm": 100_000, "reference_ocean_H1": False}})
        for item in (SUPPORTED[index % len(SUPPORTED)] for index in range(len(cells)))]
    identity_ms = (perf_counter() - t) * 1_000
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(json.dumps({"seed":42, "cells":len(cells), "selected":sum(item is not None for item in selected),
        "facts_created":len(shaped), "selector_ms":round(selector_ms,3),
        "identity_ms":round(identity_ms,3), "tracemalloc_peak_mib":round(peak / 1_048_576,3)},
        indent=2))


if __name__ == "__main__":
    main()
