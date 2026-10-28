"""Technical E1 plots only; colors are not flora or player discoveries."""
import colorsys
from hashlib import sha256
from PIL import Image,ImageDraw,ImageFont
from .catalog import load_environment_catalog


def color(identifier):
    if not identifier:return (66,78,87)
    hue=int(sha256(identifier.encode()).hexdigest()[:6],16)%360
    return tuple(round(v*255) for v in colorsys.hsv_to_rgb(hue/360,.55,.85))


def fonts():
    try:return ImageFont.truetype("C:/Windows/Fonts/consola.ttf",20),ImageFont.truetype("C:/Windows/Fonts/consola.ttf",14)
    except OSError:return ImageFont.load_default(),ImageFont.load_default()


def continuous(value,low,high):
    if value is None:return (45,55,69)
    t=max(0,min(1000000,int((value-low)*1000000/(high-low))))
    return (40+190*t//1000000,90+80*(1000000-abs(2*t-1000000))//1000000,220-170*t//1000000)


def write_global_preview(samples,sampler,path,*,seed):
    image=Image.new("RGB",(1530,1420),"#101e29");draw=ImageDraw.Draw(image);font,small=fonts()
    draw.text((20,18),f"EVERREACH / E1 environmental POTENTIAL / seed {seed} / R={sampler.regional.sites.radius/1000:g} km",font=font,fill="white")
    draw.text((20,54),"Same V4/T1/C2/JR1. No vegetation, species or permanent aquatic habitats are created by these colors.",font=small,fill="#c3d0d7")
    rows=("Potential environment / marine reference in blue; unclassified land in grey",
          "C2 mean temperature at T1 altitude / blue=-70 C, red=40 C",
          "C2 annual precipitation / blue=0 mm, red=3000 mm",
          "Unchanged T1 height / blue=-6000 m, red=6000 m")
    for row,title in enumerate(rows):
        y0=100+row*260;draw.text((20,y0),title,font=small,fill="white")
        for face in range(6):
            patch=Image.new("RGB",(8,8));pixels=patch.load()
            for y in range(8):
                for x in range(8):
                    s=samples[face*64+y*8+x]
                    if row==0:
                        value=color(s["primary_potential"]) if s["land"] else (27,68,111)
                    elif row==1:value=continuous(s["temperature_c"],-70,40)
                    elif row==2:value=continuous(s["rain_mm"],0,3000)
                    else:value=continuous(s["height_m"],-6000,6000)
                    pixels[x,y]=value
            x0=20+face*250
            image.paste(patch.resize((220,220),Image.Resampling.NEAREST),(x0,y0+25))
            draw.text((x0+6,y0+31),str(face),font=small,fill="white")
    catalog=load_environment_catalog();identifiers=sorted({s["primary_potential"] for s in samples if s["primary_potential"]})
    for i,identifier in enumerate(identifiers):
        x=20+(i%4)*375;y=1165+(i//4)*26
        draw.rectangle((x,y,x+13,y+13),fill=color(identifier))
        draw.text((x+22,y),catalog["natural"][identifier]["nome"],font=small,fill="white")
    draw.text((20,1370),"Offline diagnostic. Pending hydrology/ice/cavities remain pending. No player map, species quota or biome quota.",font=small,fill="#d9b780")
    image.save(path)


def write_region_preview(window,path,*,seed):
    identifiers=sorted({s["primary_potential"] for row in window["samples"] for s in row if s["primary_potential"]})
    image=Image.new("RGB",(1230,1320+26*((len(identifiers)+2)//3)),"#101e29");draw=ImageDraw.Draw(image);font,small=fonts()
    draw.text((20,20),f"E1 regional mosaic / seed {seed} / window {window['width_m']/1000:g} km",font=font,fill="white")
    draw.text((20,58),"Physical point queries; no random biome noise. Ecotones are overlapping suitability, not established vegetation.",font=small,fill="#c3d0d7")
    grid=window["samples"];n=len(grid)
    titles=("Potential primary environment","C2 mean temperature at T1 height","P / PET (blue=0, red=2)","Mixture ambiguity / brighter = stronger overlap")
    for i,title in enumerate(titles):
        x0=20+(i%2)*610;y0=110+(i//2)*530
        draw.text((x0,y0),title,font=small,fill="white")
        patch=Image.new("RGB",(n,n));pixels=patch.load()
        for y,row in enumerate(grid):
            for x,s in enumerate(row):
                if i==0:c=color(s["primary_potential"]) if s["land"] else (27,68,111)
                elif i==1:c=continuous(s["temperature_c"],-60,35)
                elif i==2:c=continuous(s["P_over_PET"],0,2)
                else:
                    overlap=1000000-s["mixture"][0]["weight_ppm"] if s["mixture"] else 0
                    c=continuous(overlap,0,800000)
                pixels[x,y]=c
        image.paste(patch.resize((485,485),Image.Resampling.NEAREST),(x0,y0+28))
    draw.text((20,1190),f"Primary diversity: {window['primary_diversity']} / eligible IDs: {window['eligible_diversity']} / transition edges: {window['transition_edges']}",font=small,fill="white")
    draw.text((20,1220),"Relief, local features and hydrological candidates are separate layers; a waterfall never replaces the cover.",font=small,fill="#c3d0d7")
    draw.text((20,1250),"Unconfirmed vegetation, seasonal ice and hydrological features are not drawn as physically established objects.",font=small,fill="#d9b780")
    catalog=load_environment_catalog()
    for i,identifier in enumerate(identifiers):
        x=20+(i%3)*400;y=1290+(i//3)*26
        draw.rectangle((x,y,x+13,y+13),fill=color(identifier))
        draw.text((x+22,y),catalog["natural"][identifier]["nome"],font=small,fill="white")
    image.save(path)
