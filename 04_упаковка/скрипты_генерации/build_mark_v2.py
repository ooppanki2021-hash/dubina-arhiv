# -*- coding: utf-8 -*-
"""Знак v2: те же годовые кольца (seed 7), новый узнаваемый дубовый лист.
   Вариант A — лист с прожилками; вариант B — лист + жёлудь."""
from PIL import Image, ImageDraw
import numpy as np, math, sys
# Пути считаются от расположения самого файла, поэтому запускать можно из любой
# папки (правлено 03.10.2026). Раньше часть скриптов работала только из
# финальные_макеты/, а make_spines_light.py — только из скрипты_генерации/.
# Каталог шрифтов задаётся переменными FONTS_DIR и DEJAVU_DIR; значения по
# умолчанию — прежние пути. Логика, тексты, координаты, цвета и сиды не менялись.
import os, tempfile
from pathlib import Path
_HERE = Path(__file__).resolve().parent; _PACK = _HERE.parent
IN_DIR = _PACK / 'исходники_дизайнера'; OUT_DIR = _PACK / 'финальные_макеты'
# Montserrat лежит в архиве (04_упаковка/шрифты/Montserrat, лицензия OFL 1.1).
# Переменная FONTS_DIR переопределяет каталог; прежний путь /home/user/tools/fonts
# больше не требуется.
FONTS = (os.environ.get('FONTS_DIR') or str(_PACK / 'шрифты' / 'Montserrat')).rstrip('/')
DEJAVU = os.environ.get('DEJAVU_DIR', '/usr/share/fonts/truetype/dejavu').rstrip('/')
INK=(43,30,24); LEAF=(30,62,40); CREAM=(246,239,222); OCHRE=(197,135,49)
S=2400; ring=Image.new('RGBA',(S,S),(0,0,0,0)); d=ImageDraw.Draw(ring); cx=cy=S/2
rng=np.random.default_rng(7)
def blob(r,wob,width,pts=900):
    ph=rng.uniform(0,6.28,4); amp=rng.uniform(0.4,1.0,4)*wob; xy=[]
    for i in range(pts+1):
        t=i/pts*2*math.pi; rr=r*(1+sum(amp[k]*math.sin((k+2)*t+ph[k]) for k in range(4))/100)
        xy.append((cx+rr*math.cos(t),cy+rr*math.sin(t)))
    d.line(xy,fill=INK+(255,),width=width,joint='curve')
R=S*0.47; blob(R,2.6,int(S*0.012))
for f in [0.86,0.75,0.645,0.545,0.45]: blob(R*f,1.7,int(S*0.0065))

def oak_leaf(L, acorn=False):
    """Контур дубового листа: вытянутый, шире в верхней трети, 5 пар закруглённых
       лопастей с глубокими выемками почти до средней жилки, верхушечная лопасть."""
    SS=3; L2=L*SS; W=int(L2*0.9); H=int(L2*1.15)
    im=Image.new('RGBA',(W,H),(0,0,0,0)); g=ImageDraw.Draw(im); c=W/2
    top=L2*0.03; bot=L2*0.88
    # границы лопастей по длине (доли) и вынос кончика лопасти (доли L)
    ys=[0.0,0.13,0.29,0.46,0.63,0.79,0.93]   # 0 — верх, дальше вниз
    outs=[0.12,0.22,0.27,0.25,0.18,0.09]        # верхушка, затем лопасти сверху вниз
    sinus=0.065                                  # глубина выемки: расстояние до жилки
    def side(sgn,shift):
        pts=[]
        for i in range(len(outs)):
            y0=top+(bot-top)*min(1,ys[i]+(shift if i else 0)); y1=top+(bot-top)*(ys[i+1]+(shift if i+1<len(outs) else 0))
            o=outs[i]*L2; s0=(0 if i==0 else sinus*L2)
            for k in range(41):
                tt=k/40; y=y0+(y1-y0)*tt
                bulge=math.sin(math.pi*tt)**0.7
                base=s0+(sinus*L2-s0)*tt
                pts.append((c+sgn*(base+(o-base)*bulge),y-L2*0.035*bulge*(i>0)))
        return pts
    left=side(-1,0.0); right=side(1,0.02)       # лёгкая асимметрия справа
    poly=[(c,top)]+left+[(c-L2*0.03,bot),(c+L2*0.03,bot)]+right[::-1]
    g.polygon(poly,fill=LEAF+(255,))
    g.line([(c,bot-L2*0.01),(c,bot+L2*0.1)],fill=LEAF+(255,),width=int(L2*0.028))
    # прожилки
    vw=max(2,int(L2*0.011)); g.line([(c,top+L2*0.06),(c,bot)],fill=CREAM+(255,),width=vw)
    for i in range(1,len(outs)):
        for sgn,sh in ((-1,0),(1,0.02)):
            ym=top+(bot-top)*((ys[i]+ys[i+1])/2+sh)
            g.line([(c,ym+L2*0.03),(c+sgn*outs[i]*L2*0.7,ym-L2*0.03)],fill=CREAM+(255,),width=max(2,vw*3//4))
    if acorn:
        ax,ay=c+L2*0.24,bot+L2*0.0; aw=L2*0.12
        g.ellipse([ax-aw*0.5,ay,ax+aw*0.5,ay+aw*1.2],fill=OCHRE+(255,))
        g.pieslice([ax-aw*0.66,ay-aw*0.5,ax+aw*0.66,ay+aw*0.55],180,360,fill=INK+(255,))
        g.line([(ax,ay-aw*0.45),(ax+aw*0.1,ay-aw*0.75)],fill=INK+(255,),width=int(aw*0.12))
    return im.resize((W//SS,H//SS),Image.LANCZOS)

for name,ac in [('A',False),('B',True)]:
    r=ring.copy(); lf=oak_leaf(int(S*0.52),ac)
    from PIL import ImageFilter, ImageChops
    pos=(int(cx-lf.size[0]/2),int(cy-lf.size[1]*0.47))
    knock=Image.new('L',(S,S),0); knock.paste(lf.getchannel('A'),pos)
    knock=knock.point(lambda v:255 if v>20 else 0).filter(ImageFilter.MaxFilter(int(S*0.018)//2*2+1))
    r.putalpha(ImageChops.subtract(r.getchannel('A'),knock))   # просвет вокруг листа
    r.alpha_composite(lf,pos)
    out=r.resize((1200,1200),Image.LANCZOS); out.save(IN_DIR / f'знак_v2_{name}_для_скрипта.png')

print('ok')
