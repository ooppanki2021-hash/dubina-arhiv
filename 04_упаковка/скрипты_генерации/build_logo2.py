# УСТАРЕЛ 26.09.2026: бренд «ДУБРАВА 40+» занят в реестре и переименован в «ДУБИНА 40+».
# Актуальный скрипт логотипа — logo_dubina.py. Этот файл сохранён как история,
# запускать для печати нельзя: соберёт старое название.
# -*- coding: utf-8 -*-
"""ДУБРАВА 40+: кольца отрисованы заново (резкие, органичные),
   слово ДУБРАВА взято с лицевой стороны, 40+ — узкое, охра «СТОП»."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np, math
from scipy import ndimage
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

OCHRE=(197,135,49); INK=(43,30,24); LEAF=(30,62,40)
# Папка uploads/ в архиве не сохранена. Файл того же имени лежит в
# исходники_дизайнера/; подстановка проверена побайтовым воспроизведением
# архивного УСТАРЕЛО_логотип_на_фоне.png — совпало, значит файл тот же.
face=Image.open(IN_DIR / 'УСТАРЕЛО_порошок_цветной_40plus_лицо.png').convert('RGB')

# ---------- 1. слово ДУБРАВА с лица (чистое, без колец и 40+) ----------
w=face.crop((258,314,416,360))
a=np.array(w).astype(int)
lum=a[:,:,0]*.299+a[:,:,1]*.587+a[:,:,2]*.114
al=np.clip((np.percentile(lum,93)-lum)/(np.percentile(lum,93)-40)*255,0,255)
al[al<70]=0
m=al>0; lab,n=ndimage.label(m); sz=ndimage.sum(m,lab,range(1,n+1))
keep=np.zeros_like(m)
for i,s_ in enumerate(sz,1):
    if s_>=180: keep|=(lab==i)
al=al*keep
word=Image.fromarray(np.dstack([a,al]).astype(np.uint8),'RGBA')
word=word.crop(word.getbbox())
WS=6
word=word.resize((word.size[0]*WS,word.size[1]*WS),Image.LANCZOS)
WW,WH=word.size

# ---------- 2. кольца рисуем заново ----------
D=int(WH*2.15)                       # диаметр знака
SS=4                                 # суперсэмплинг
S=D*SS
ring=Image.new('RGBA',(S,S),(0,0,0,0))
d=ImageDraw.Draw(ring)
cx=cy=S/2
rng=np.random.default_rng(7)

def blob(r,wob,pts=720,width=3):
    """слегка неровная окружность — как годовое кольцо"""
    ph=rng.uniform(0,6.28,4); amp=rng.uniform(0.4,1.0,4)*wob
    xy=[]
    for i in range(pts+1):
        t=i/pts*2*math.pi
        rr=r*(1+sum(amp[k]*math.sin((k+2)*t+ph[k]) for k in range(4))/100)
        xy.append((cx+rr*math.cos(t), cy+rr*math.sin(t)))
    d.line(xy,fill=INK+(255,),width=width,joint='curve')

R=S*0.47
blob(R,       2.6, width=int(11*SS/2))      # внешний контур — толще
for k,f_ in enumerate([0.86,0.75,0.645,0.545,0.45]):
    blob(R*f_, 1.7, width=int(6.0*SS/2))

# ---------- 3. дубовый лист ----------
def oak_leaf(size):
    """дубовый лист: круглые лопасти, глубокие пазухи"""
    H=int(size*1.30)
    ss=4
    im=Image.new('RGBA',(size*ss,H*ss),(0,0,0,0)); dd=ImageDraw.Draw(im)
    c=size*ss/2
    top,bot=H*ss*0.06, H*ss*0.80
    L=bot-top
    # (позиция по оси, радиус лопасти) — широкие в середине
    lob=[(0.10,0.15),(0.30,0.25),(0.52,0.30),(0.74,0.24),(0.92,0.14)]
    for pos,rad in lob:
        y=top+L*pos; r=size*ss*rad
        for sgn in (-1,1):
            x=c+sgn*(size*ss*rad*0.62)
            dd.ellipse([x-r,y-r*0.78,x+r,y+r*0.78],fill=LEAF+(255,))
    # центральная масса + кончик
    dd.polygon([(c-size*ss*0.10,top),(c+size*ss*0.10,top),
                (c+size*ss*0.20,bot),(c-size*ss*0.20,bot)],fill=LEAF+(255,))
    dd.ellipse([c-size*ss*0.09,top-size*ss*0.04,c+size*ss*0.09,top+size*ss*0.14],fill=LEAF+(255,))
    # черешок
    dd.line([(c,bot-size*ss*0.05),(c,H*ss*0.97)],fill=LEAF+(255,),width=max(2,int(size*ss/24)))
    return im.resize((size,H),Image.LANCZOS)

lf=oak_leaf(int(S*0.27))
ring.paste(lf,(int(cx-lf.size[0]/2),int(cy-lf.size[1]/2)),lf)

ring=ring.resize((D,D),Image.LANCZOS)

# ---------- 4. 40+ узкое, охра ----------
size=int(WH*0.82)
fnt=ImageFont.truetype(DEJAVU + "/DejaVuSans.ttf",size)
tmp=Image.new('L',(size*3,size*2),0)
ImageDraw.Draw(tmp).text((0,0),"40+",font=fnt,fill=255)
tmp=tmp.crop(tmp.getbbox())
tmp=tmp.filter(ImageFilter.MinFilter(3))            # тоньше штрих
tmp=tmp.resize((int(tmp.size[0]*0.80),tmp.size[1]),Image.LANCZOS)  # УЖЕ по ширине
plus=Image.new('RGBA',tmp.size,OCHRE+(0,)); plus.putalpha(tmp)

# ---------- 5. сборка в строку ----------
GAP1=int(D*0.16); GAP2=int(WH*0.30)
Wt=D+GAP1+WW+GAP2+plus.size[0]
Ht=max(D,WH)
M=int(Ht*0.22)
out=Image.new('RGBA',(Wt+2*M,Ht+2*M),(0,0,0,0))
base=M+ (Ht-WH)//2                                  # верх слова
out.paste(ring,(M,M+(Ht-D)//2),ring)
out.paste(word,(M+D+GAP1,base),word)
out.paste(plus,(M+D+GAP1+WW+GAP2, base+WH-plus.size[1]-int(WH*0.06)),plus)

out.save(OUT_DIR / 'УСТАРЕЛО_логотип.png'); print('ok',out.size)
prev=Image.new('RGB',out.size,(243,229,207)); prev.paste(out,(0,0),out)
prev.save(Path(tempfile.gettempdir()) / 'lp.png')   # превью, не вход
