"""Offline W2 ledger views. Pending requests are not mapped water occupation."""
from collections import Counter
from pathlib import Path
from PIL import Image, ImageDraw
from ..terrain.preview import _font


def metrics(revisions):
    rows = [t for r in revisions for t in r["transfers"]]
    return {"revisions": len(revisions), "applied_transfer_count": sum(t["status"] == "applied" for t in rows),
        "applied_transfer_liters": sum(t["applied_liters"] for t in rows),
        "request_outcome_counts": dict(Counter(t["status"] for t in rows)),
        "pending_reasons": dict(Counter(reason for t in rows for reason in t["reasons"])),
        "max_absolute_residual_liters": max([abs(b["residual_liters"]) for r in revisions for b in r["budgets"].values()] or [0]),
        "periods": [r["period"] for r in revisions], "permanent_waterbody_declared": False,
        "W1_climatology_recredited": False}


def write_preview(water, node, revisions, output, *, seed, radius_m, g1_image=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1500, 1080), "#111d27")
    draw = ImageDraw.Draw(image)
    small, font = _font(17), _font(21)
    draw.text((22, 16), f"EVERREACH / W2   seed {seed}   R={radius_m:,} m   node {node}", font=_font(27), fill="white")
    draw.text((22, 58), "W1 availability / G1 geometry / W2 reconciled quantities are separate layers.", font=small, fill="#c2d4e2")
    draw.text((22, 110), "G1 reference (not water occupation)", font=font, fill="white")
    if g1_image and Path(g1_image).exists():
        with Image.open(g1_image) as raw:
            image.paste(raw.resize((710, 550)), (22, 145))
    else:
        draw.rectangle((22, 145, 732, 695), outline="#547187")
    draw.text((780, 110), "One W1 checkpoint, preserved stocks", font=font, fill="white")
    before = revisions[0]["before"][str(node)]["accounts"]
    after = revisions[-1]["after"][str(node)]["accounts"]
    total = sum(before.values())
    for i, (name, amount) in enumerate(before.items()):
        y = 152+i*57
        draw.text((780, y), f"{name}: {amount:,} L", font=small, fill="#c8d8e5")
        width = int(630*amount/max(1, total))
        draw.rectangle((780, y+26, 780+max(1, width), y+39), fill="#79aac8")
    draw.text((780, 515), f"Total before: {total:,} L", font=small, fill="white")
    draw.text((780, 544), f"Total after:  {sum(after.values()):,} L", font=small, fill="white")
    report = metrics(revisions)
    draw.text((780, 588), f"Applied W2 transfers: {report['applied_transfer_count']} / {report['applied_transfer_liters']:,} L", font=small, fill="#8be5ae")
    draw.text((780, 617), f"Maximum residual: {report['max_absolute_residual_liters']} L", font=small, fill="#8be5ae")
    draw.text((22, 725), "Four logical periods: explicit requests, no new rain credited", font=font, fill="white")
    for season, revision in enumerate(revisions[:4]):
        x = 22+season*370
        rows = revision["transfers"]
        amount = sum(t["applied_liters"] for t in rows)
        runoff = water.solution.periods[revision["period"]]["fluxes"]["local_runoff"][node]
        draw.text((x, 765), f"Period {revision['period']+1}", font=font, fill="white")
        draw.text((x, 800), f"W1 runoff ref: {runoff:.3g} L", font=small, fill="#80bce6")
        draw.text((x, 828), f"W2 applied: {amount:,} L", font=small, fill="#8be5ae")
        draw.text((x, 856), "W1 reference is NOT a credit", font=_font(15), fill="#c7b78b")
    reasons = sorted(report["pending_reasons"], key=lambda x: (-report["pending_reasons"][x], x))[:4]
    draw.text((22, 910), "Pending: "+", ".join(reasons[:2]), font=small, fill="#edbc76")
    draw.text((22, 938), ", ".join(reasons[2:]), font=small, fill="#edbc76")
    draw.text((22, 985), "No real example has sufficient hydraulic-capacity evidence. Zero approved transfer is intentional.", font=small, fill="#d6b88e")
    draw.text((22, 1017), "Unlocalized water remains in its original account. No incision, lake, perennial river or ocean export is invented.", font=small, fill="#d6b88e")
    image.save(output/"reconciliation.png")
    return report
