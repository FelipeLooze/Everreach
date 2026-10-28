"""Developer-only cube charts of the same continuous spherical J1 partition."""
from PIL import Image, ImageDraw, ImageFont
from .adapter import adapt_unit, evaluate_opportunities
from .catalog import load_catalog
from ..sphere_topology import face_point

PALETTE = [(174,131,105),(81,92,105),(158,105,78),(99,115,128),(99,132,85),
           (216,202,160),(193,158,105),(115,110,131),(149,111,100),(175,153,127),
           (200,205,207),(218,193,208),(119,150,143),(153,161,178),(174,146,172)]


def write_preview(plan, destination, *, seed):
    catalog = load_catalog()
    image = Image.new("RGB", (1510, 1060), "#101e29")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 17)
        small = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 13)
    except OSError:
        font = small = ImageFont.load_default()
    counts = {u["geological_unit_id"]: len(evaluate_opportunities(adapt_unit(u, plan.signature), catalog)["opportunities"]) for u in plan.units}
    draw.text((20,15), f"EVERREACH J1 / seed {seed} / R={plan.data['radius_m']/1000:g} km / {len(plan.units)} geological units", font=font, fill="white")
    draw.text((20,45), "Lithology + unit contacts (left) | eligible unit/material opportunities (right). Developer diagnostic.", font=small, fill="#becbd1")
    size, resolution = 220, 48
    for face in range(6):
        col, row = face%3, face//3
        for kind in range(2):
            x0, y0 = 20+col*242+kind*750, 105+row*285
            patch = Image.new("RGB", (resolution,resolution))
            pixels = patch.load()
            identities = []
            for y in range(resolution):
                identities.append([])
                for x in range(resolution):
                    u = plan.unit_at(face_point(face, 2*x+1, 2*y+1, 2*resolution))
                    identities[y].append(u["geological_unit_id"])
                    number = int(u["substrates"][0][-3:])
                    count = counts[u["geological_unit_id"]]
                    color = PALETTE[number-1] if kind == 0 else (min(240,35+count*8), min(210,55+count*5), 95)
                    pixels[x,y] = color
            if kind == 0:
                for y in range(resolution):
                    for x in range(resolution):
                        if ((x+1<resolution and identities[y][x]!=identities[y][x+1]) or
                                (y+1<resolution and identities[y][x]!=identities[y+1][x])):
                            pixels[x,y] = (39,54,64)
            image.paste(patch.resize((size,size),Image.Resampling.NEAREST),(x0,y0))
            draw.text((x0,y0-25),f"Face {face}"+(" / candidates" if kind else " / substrate"),font=small,fill="white")
    y0 = 690
    for i, (identifier, record) in enumerate(catalog["substrates"].items()):
        x, y = 20+(i%4)*370, y0+(i//4)*38
        number = int(identifier[-3:])
        draw.rectangle((x,y,x+14,y+14),fill=PALETTE[number-1] if number<=15 else "#53616a")
        draw.text((x+22,y),f"{number:02d} {record['slug']}"+(" [blocked]" if number>15 else ""),font=small,fill="white")
    draw.text((20,920),"Contacts belong to spherical bodies, not render sectors; identical points on face seams have identical unit IDs.",font=small,fill="#b4c5cd")
    draw.text((20,950),"Opportunity is NOT ore, exposed material, loot or a confirmed deposit. Rarity/budgets are separate and experimental.",font=small,fill="#e4b777")
    draw.text((20,980),"J1 histories are new procedural model records. No current climate, river, reef or ecosystem is inferred.",font=small,fill="#b4c5cd")
    draw.text((20,1010),"Each color is a primary host rock. No terrain height was modified. Canonical exceptional sources remain blocked.",font=small,fill="#b4c5cd")
    image.save(destination)
