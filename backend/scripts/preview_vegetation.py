"""Static technical maps of finite Vg1 communities; never a player map."""
from collections import Counter
from hashlib import sha256
import json,math
from PIL import Image,ImageDraw,ImageFont
from scripts.validate_vegetation import OUT,SCALES

COLORS={"barren":"#b6aaa0","dense_forest":"#1e533a","open_forest":"#467b45","woodland":"#819554",
    "savanna_mosaic":"#b2ad65","shrubland":"#958950","grass_forb_field":"#a1b95d","steppe":"#c8b480",
    "sparse_desert_vegetation":"#d9bd90","polar_alpine_cover":"#9babb0","cryptogam_cover":"#72918a"}
LABELS={"wet":"Úmida temperada","moderate":"Moderada","arid":"Árida","dry":"Seca extrema","cold":"Fria extrema"}


def font(size):
    return ImageFont.truetype("C:/Windows/Fonts/arial.ttf",size)


def color(sample,mode):
    if mode=="Forma":return COLORS[sample["physiognomy"]]
    if mode=="Espécie dominante":
        return tuple(50+b*3//4 for b in sha256(sample["dominant_species"].encode()).digest()[:3]) if sample["dominant_species"] else "#b6aaa0"
    if mode=="Cobertura":
        v=sample["cover_ppm"]/1000000;return (int(224-190*v),int(209-60*v),int(177-124*v))
    if mode=="Densidade":
        v=min(1,math.log10(1+sample["density_per_ha"])/4);return (int(235-185*v),int(222-120*v),int(205-45*v))
    if mode=="Riqueza":
        v=min(1,len(sample["populations"])/12);return (int(224-130*v),int(224-155*v),int(224-40*v))
    trees=sample["strata_cover_ppm"]["canopy"]/1000000
    ground=sample["strata_cover_ppm"]["ground"]/1000000
    return (int(215-150*trees),int(210-100*ground),int(200-100*trees))


def maps(seed):
    root=OUT/f"seed-{seed}"
    baseline=json.loads((root/"ecological_v1/windows.json").read_text(encoding="utf-8"))
    directed=json.loads((root/"exploration_mosaic_v1/windows.json").read_text(encoding="utf-8"))
    modes=("Forma","Espécie dominante","Cobertura","Densidade","Riqueza","Estratos")
    im=Image.new("RGB",(1560,1260),"#f6f2e9");d=ImageDraw.Draw(im)
    d.text((24,15),f"Everreach · Vg1 · seed {seed} · raio 63.710 km",font=font(25),fill="#24362e")
    d.text((24,49),"Comunidades fundadoras estabelecidas • janelas de 20 km • snapshots offline • não é o mapa do jogador",font=font(17),fill="#34453c")
    for col,mode in enumerate(modes):d.text((190+col*224,85),mode,font=font(17),fill="black")
    for row,(region,window) in enumerate(directed.items()):
        top=120+row*206;grid=window["grid"];n=len(grid);step=180//n
        d.text((15,top),LABELS[region],font=font(16),fill="#253b2c")
        metrics=window["metrics"]
        d.text((15,top+27),f"{metrics['species_established']} espécies\n{metrics['mean_cover_ppm']/10000:.1f}% cobertura",font=font(14),fill="black")
        for col,mode in enumerate(modes):
            left=190+col*224
            for y,line in enumerate(grid):
                for x,s in enumerate(line):d.rectangle((left+x*step,top+y*step,left+(x+1)*step,top+(y+1)*step),fill=color(s,mode))
            d.rectangle((left,top,left+n*step,top+n*step),outline="#586254")
    d.text((15,1170),"Cobertura: 0–100% (claro–verde). Densidade: log(1 + organismos/ha), 0–10.000. Riqueza: 0–12 espécies por patch.",font=font(16),fill="black")
    d.text((15,1201),"Cores de dominância são identificadores de composição. Beige = ausência. Clareiras integram a cobertura; estratos não são novos biomas.",font=font(15),fill="black")
    im.save(root/"vegetation-mosaics.png")
    # Direct before/after, same physical geography and eligibility.
    im=Image.new("RGB",(1380,690),"#f6f2e9");d=ImageDraw.Draw(im)
    d.text((22,15),f"Seed {seed} · ecológico → mosaico de exploração · mesmas fontes C3/W1/E1",font=font(23),fill="black")
    for col,region in enumerate(("wet","moderate","arid")):
        for row,(label,data) in enumerate((("Ecológico",baseline),("Dirigido",directed))):
            left=30+col*450;top=85+row*270;grid=data[region]["grid"];n=len(grid);step=230//n
            d.text((left,top-26),f"{LABELS[region]} · {label}",font=font(17),fill="black")
            for y,line in enumerate(grid):
                for x,s in enumerate(line):d.rectangle((left+x*step,top+y*step,left+(x+1)*step,top+(y+1)*step),fill=color(s,"Espécie dominante"))
            m=data[region]["metrics"]
            d.text((left+238,top+15),f"{m['dominant_species']}\ndominantes\n\n{m['species_established']}\nespécies\n\n{m['mean_cover_ppm']/10000:.1f}%\ncobertura",font=font(17),fill="black")
    d.text((24,640),"A direção varia composição e estrutura entre candidatas elegíveis. Não modifica chuva, água nem transforma áreas inviáveis em florestas.",font=font(16),fill="black")
    im.save(root/"ecological-vs-directed.png")
    # Planet face atlas for the actual generated populations.
    rows=json.loads((root/"exploration_mosaic_v1/planet.json").read_text())
    im=Image.new("RGB",(1100,800),"#f6f2e9");d=ImageDraw.Draw(im)
    d.text((25,15),f"Vg1 · seed {seed} · amostragem planetária de 384 patches",font=font(24),fill="black")
    for r in rows:
        face,_,x,y=r["cell"];left=25+(face%3)*360;top=90+(face//3)*315
        d.rectangle((left+x*36,top+(7-y)*36,left+(x+1)*36,top+(8-y)*36),fill=color(r["community"],"Forma") if r["land"] else "#54879e")
        d.text((left,top-28),f"Face {face}",font=font(18),fill="black")
    d.text((25,735),"Azul: referência marinha W1. Beige: sem população estabelecida. Resolução diagnóstica, não censo contínuo.",font=font(16),fill="black")
    im.save(root/"planet-established-vegetation.png")


def routes():
    seeds=(42,0,7,2026,12345)
    im=Image.new("RGB",(1470,940),"#f6f2e9");d=ImageDraw.Draw(im)
    d.text((20,15),"Mudanças de espécie dominante em percursos • ecológico / dirigido",font=font(25),fill="black")
    for col,km in enumerate(SCALES):d.text((250+col*235,65),f"{km} km",font=font(20),fill="black")
    y=110
    for seed in seeds:
        a=json.loads((OUT/f"seed-{seed}/ecological_v1/report.json").read_text());b=json.loads((OUT/f"seed-{seed}/exploration_mosaic_v1/report.json").read_text())
        for region in ("wet","moderate","arid"):
            d.text((20,y),f"{seed} · {LABELS[region]}",font=font(18),fill="black")
            for col,km in enumerate(SCALES):
                av=a["routes"][region][str(km)]["dominance_changes"];bv=b["routes"][region][str(km)]["dominance_changes"]
                left=250+col*235
                d.rectangle((left,y,left+av*6,y+8),fill="#a38d69")
                d.rectangle((left,y+12,left+bv*6,y+20),fill="#367653")
                d.text((left+125,y),f"{av} / {bv}",font=font(17),fill="black")
            y+=48
    d.text((20,860),"21 pontos por percurso; passos de 250 m a 25 km. Valores resumem amostras, sem afirmar mudanças exatas entre elas.",font=font(17),fill="black")
    im.save(OUT/"exploration-routes-comparison.png")


if __name__=="__main__":
    for seed in (42,0,7,2026,12345):maps(seed)
    routes()
