"""Structure-first static diagnostics. Colors mean physiognomy, not species IDs."""
import json,math
from PIL import Image,ImageDraw
from scripts.calibrate_vegetation import OUT
from scripts.preview_vegetation import font,COLORS
from app.game.world.genesis.vegetation.diagnostics import structure

NAMES={"dense_forest":"Floresta densa","open_forest":"Floresta aberta","woodland":"Bosque","savanna_mosaic":"Savana",
    "grass_forb_field":"Campo","steppe":"Estepe","shrubland":"Arbustal","sparse_desert_vegetation":"Vegetação esparsa",
    "polar_alpine_cover":"Cobertura polar/alpina","cryptogam_cover":"Musgos/líquens","barren":"Sem vegetação"}
REGIONS={"wet":"Úmida","moderate":"Moderada","arid":"Árida"}


def color(s,mode):
    if mode=="Fisionomia":return COLORS[s["physiognomy"]]
    if mode=="Cobertura":
        t=s["cover_ppm"]/1000000;return (int(235-195*t),int(218-65*t),int(187-130*t))
    if mode=="Altura média":
        t=min(1,structure(s)["mean_height_cm"]/2500);return (int(235-170*t),int(224-110*t),int(192-55*t))
    if mode=="Densidade":
        t=min(1,math.log10(1+s["density_per_ha"])/4);return (int(235-190*t),int(225-110*t),int(210-50*t))
    st=s["strata_cover_ppm"];return tuple(min(255,60+int(st[k]*195/1000000)) for k in ("canopy","shrub","ground"))


def legend(d,y):
    x=20
    for i,(key,name) in enumerate(NAMES.items()):
        col=i%6;row=i//6;left=20+col*225;top=y+row*29
        d.rectangle((left,top,left+14,top+14),fill=COLORS[key]);d.text((left+20,top-2),name,font=font(14),fill="black")


def maps(seed):
    folder=OUT/f"seed-{seed}";windows=json.loads((folder/"windows.json").read_text(encoding="utf-8"));wide=json.loads((folder/"wide-windows.json").read_text(encoding="utf-8"))
    for extent,data,name in ((20,windows,"structure-20km.png"),(100,wide,"structure-100km.png")):
        im=Image.new("RGB",(1410,1530),"#f6f2e9");d=ImageDraw.Draw(im)
        d.text((20,15),f"Everreach · 1.0.1 · seed {seed} · janelas de {extent} km",font=font(26),fill="#203e30")
        d.text((20,53),"Antes: Vg1 exploration_mosaic_v1. Depois: Vg2 regional_canopy_v2. Mesma geografia, clima e água.",font=font(17),fill="black")
        modes=("Fisionomia","Cobertura","Altura média","Densidade","Estratos")
        for col,mode in enumerate(modes):d.text((190+col*235,94),mode,font=font(18),fill="black")
        row=0
        for region in REGIONS:
            for version in ("Vg1","Vg2"):
                grid=data[region][version];left=190;top=132+row*202;n=len(grid);step=176//n
                values=[s for line in grid for s in line]
                cover=sum(s["cover_ppm"] for s in values)/len(values)/10000
                d.text((20,top+5),f"{REGIONS[region]} · {version}",font=font(17),fill="black")
                d.text((20,top+34),f"{cover:.1f}% cobertura",font=font(15),fill="black")
                d.text((20,top+62),f"{min(structure(s)['mean_height_cm'] for s in values)/100:.1f}–{max(structure(s)['mean_height_cm'] for s in values)/100:.1f} m\naltura média",font=font(14),fill="black")
                for col,mode in enumerate(modes):
                    left=190+col*235
                    for y,line in enumerate(grid):
                        for x,s in enumerate(line):d.rectangle((left+x*step,top+y*step,left+(x+1)*step,top+(y+1)*step),fill=color(s,mode))
                    d.rectangle((left,top,left+n*step,top+n*step),outline="#586254")
                row+=1
        legend(d,1360)
        d.text((20,1432),"Altura: cores saturam acima de 25 m. Cobertura: 0–100%. Densidade: log de organismos/colônias-modelo por hectare.",font=font(15),fill="black")
        d.text((20,1461),"Estratos: R = copa, G = arbustivo, B = solo. Cores de fisionomia permanecem iguais quando muda somente a espécie.",font=font(15),fill="black")
        d.text((20,1490),"Snapshots de comunidades fundadoras estabelecidas. Grade diagnóstica discreta; não é renderização ou Atlas.",font=font(15),fill="black")
        im.save(folder/name)
    # Numeric longitudinal profiles expose internal variation inside one forest class.
    routes=json.loads((folder/"routes.json").read_text(encoding="utf-8"))
    im=Image.new("RGB",(1410,920),"#f6f2e9");d=ImageDraw.Draw(im)
    d.text((20,15),f"Seed {seed} · perfis estruturais de 100 km · Vg1 / Vg2",font=font(25),fill="black")
    for row,region in enumerate(REGIONS):
        for col,(key,title,maximum) in enumerate((("cover_ppm","Cobertura (%)",1000000),("canopy_ppm","Copa (%)",1000000),("mean_height_cm","Altura média (m)",2500))):
            left=100+col*430;top=115+row*240;width=360;height=155
            d.text((left,top-37),f"{REGIONS[region]} · {title}",font=font(17),fill="black")
            d.line((left,top,left,top+height,left+width,top+height),fill="#7c8176",width=1)
            for label,colour in (("Vg1","#ad8651"),("Vg2","#246f4b")):
                samples=routes[region]["100"]["samples"][label]
                points=[(left+i*width//20,top+height-min(height,int(s[key]*height/maximum))) for i,s in enumerate(samples)]
                d.line(points,fill=colour,width=3)
            d.text((left,top+height+7),"0 km",font=font(14),fill="black");d.text((left+width-48,top+height+7),"100 km",font=font(14),fill="black")
    d.text((20,867),"Marrom = Vg1; verde = Vg2. A mesma classe florestal pode variar em altura e ocupação de copa sem virar outro bioma.",font=font(17),fill="black")
    im.save(folder/"structure-profiles-100km.png")


def route_chart():
    im=Image.new("RGB",(1500,970),"#f6f2e9");d=ImageDraw.Draw(im)
    d.text((20,15),"Mudanças de dominante / mudanças de fisionomia · antes → depois",font=font(24),fill="black")
    for col,km in enumerate((5,20,50,100,500)):d.text((250+col*240,65),f"{km} km",font=font(20),fill="black")
    y=110
    for seed in (42,0,7,2026,12345):
        report=json.loads((OUT/f"seed-{seed}/report.json").read_text())
        for region in REGIONS:
            d.text((20,y),f"{seed} · {REGIONS[region]}",font=font(18),fill="black")
            for col,km in enumerate((5,20,50,100,500)):
                r=report["routes"][region][str(km)];a,b=r["Vg1"],r["Vg2"]
                left=250+col*240
                d.text((left,y),f"ID {a['dominant_changes']} → {b['dominant_changes']}",font=font(16),fill="#52534d")
                d.text((left,y+20),f"Forma {a['form_changes']} → {b['form_changes']}",font=font(16),fill="#246f4b")
            y+=49
    d.text((20,884),"21 pontos por percurso; passos de 250 m a 25 km. Troca de ID não significa troca de bioma nem prova de mudança visual.",font=font(17),fill="black")
    im.save(OUT/"routes-identity-vs-physiognomy.png")


def gallery():
    path=OUT/"global-structure-pilot-42.json"
    if not path.exists():return
    examples=json.loads(path.read_text())["examples"]
    im=Image.new("RGB",(1420,890),"#f6f2e9");d=ImageDraw.Draw(im)
    d.text((20,15),"Seed 42 · formas reais encontradas nas 384 sondas planetárias Vg2",font=font(25),fill="black")
    for i,(name,s) in enumerate(examples.items()):
        x=25+(i%4)*350;y=85+(i//4)*240;m=structure(s)
        d.rectangle((x,y,x+320,y+180),outline="#a7a799")
        d.rectangle((x+8,y+9,x+22,y+23),fill=COLORS[name]);d.text((x+28,y+7),NAMES[name],font=font(17),fill="black")
        d.text((x+12,y+40),f"Cobertura {m['cover_ppm']/10000:.1f}%\nAltura média {m['mean_height_cm']/100:.2f} m\nAltura máxima {m['max_height_cm']/100:.2f} m\nDensidade {m['density_per_ha']}/ha",font=font(17),fill="black")
        total=0
        for key,colour in (("canopy_ppm","#254e32"),("shrub_ppm","#89904e"),("ground_ppm","#b9bd76")):
            w=m[key]*296//1000000
            if w:d.rectangle((x+12+total,y+151,x+12+total+w,y+169),fill=colour)
            total+=w
    d.text((20,834),"Barras = copa / arbustivo / solo. São agregados estruturais de populações finitas, não indivíduos renderizados.",font=font(17),fill="black")
    im.save(OUT/"physiognomy-gallery.png")


if __name__=="__main__":
    for seed in (42,0,7,2026,12345):maps(seed)
    route_chart();gallery()
