"""Offline JR1 technical comparison, never a player-facing atlas."""
from PIL import Image,ImageDraw,ImageFont
from ..preview import PALETTE
from ..catalog import load_catalog
from .experiment import window_point,window_coordinates
from .occurrence import opportunities
from ...sphere_topology import SurfacePoint


def write_preview(sampler,center,formations,sources,measurement,path,*,seed):
    image=Image.new("RGB",(1530,1020),"#101e29");draw=ImageDraw.Draw(image)
    try:
        font=ImageFont.truetype("C:/Windows/Fonts/consola.ttf",18)
        small=ImageFont.truetype("C:/Windows/Fonts/consola.ttf",14)
    except OSError:
        font=small=ImageFont.load_default()
    draw.text((20,20),f"EVERREACH / J1 -> JR1 / seed {seed} / R={sampler.sites.radius/1000:g} km / 96 x 96 km",font=font,fill="white")
    draw.text((20,52),"Same unchanged T1. Physical geological bodies are independent of render tiles and player level.",font=small,fill="#c3d0d7")
    size,resolution=460,48
    images=[Image.new("RGB",(resolution,resolution)) for _ in range(3)]
    pixels=[i.load() for i in images];ids=[]
    catalog=load_catalog();assess={}
    for y in range(resolution):
        ids.append([])
        for x in range(resolution):
            p=window_point(center,-48000+(2*x+1)*96000//(2*resolution),48000-(2*y+1)*96000//(2*resolution),sampler.sites.radius)
            macro=sampler.macro.unit_at(p);f=sampler.formation(p);identifier=f["formation_id"]
            ids[y].append(identifier)
            pixels[0][x,y]=PALETTE[int(macro["substrates"][0][-3:])-1]
            color=PALETTE[int(f["substrates"][0][-3:])-1]
            if not f["exposure"]["rock_outcrop_model"]:
                color=tuple(v*2//3 for v in color)
            pixels[1][x,y]=color
            if identifier not in assess:
                assess[identifier]=len(opportunities(f,sampler.signature,catalog)["opportunities"])
            pixels[2][x,y]=(40,65,75) if assess[identifier] else (25,37,49)
    for y in range(resolution):
        for x in range(resolution):
            if (x+1<resolution and ids[y][x]!=ids[y][x+1]) or (y+1<resolution and ids[y][x]!=ids[y+1][x]):
                pixels[1][x,y]=(19,34,43)
    titles=("J1 / inherited primary host","JR1 / lithology + body contacts","Eligible hosts + selected test sources")
    for i,patch in enumerate(images):
        x0=20+510*i
        draw.text((x0,105),titles[i],font=small,fill="white")
        image.paste(patch.resize((size,size),Image.Resampling.NEAREST),(x0,140))
    colors={"comum":"#7fe4a0","incomum":"#68b8ff","raro":"#f2b364","muito_raro":"#cc95ff"}
    for source in sources:
        xy=window_coordinates(center,SurfacePoint(*source["anchor_surface_point"]),sampler.sites.radius)
        if xy is None:
            continue
        x=1040+(xy[0]+48000)*size/96000;y=140+(48000-xy[1])*size/96000
        color=colors.get(source["rarity"],"white")
        exposed=source["exposure_model"]["rock_outcrop_model"]
        draw.ellipse((x-4,y-4,x+4,y+4),outline=color,fill=color if exposed else "#101e29",width=2)
    draw.text((20,630),f"{len(formations)} formation anchors inside window / {len(sources)} selected sources / land area {measurement['land_area_km2']:.1f} km2",font=font,fill="white")
    draw.text((20,666),"JR1 bright hosts: rock-outcrop model. Dark hosts: buried cover. Neither is confirmed current exposure or access.",font=small,fill="#c4cfd5")
    draw.text((20,699),"Source markers: green=common, blue=uncommon, orange=rare, purple=very rare. Filled=outcrop model; hollow=buried.",font=small,fill="#c4cfd5")
    draw.text((20,732),"Eligible hosts (right background) are opportunities, not ore. Markers are experimental proposals unless persisted explicitly.",font=small,fill="#e9b87b")
    from collections import Counter
    hosts=Counter(f["substrates"][0] for f in formations.values())
    for i,identifier in enumerate(sorted(hosts)):
        record=catalog["substrates"][identifier];x=20+(i%4)*375;y=795+(i//4)*32
        draw.rectangle((x,y,x+14,y+14),fill=PALETTE[int(identifier[-3:])-1])
        draw.text((x+23,y),f"{record['slug']}: {hosts[identifier]}",font=small,fill="white")
    draw.text((20,950),"Developer diagnostic only. No mining, inventory, caves, terrain modification, biome inference or automatic save migration.",font=small,fill="#c4cfd5")
    image.save(path)
