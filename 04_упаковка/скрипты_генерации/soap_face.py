# Мыло, лицо v2: правки текста поверх v1 (ДУБИНА, ПРОТИВ ВОЗРАСТНОГО ЗАПАХА, 90 г)
from PIL import Image,ImageDraw,ImageFont
import numpy as np,cv2
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
import sys
def _need_faces(*names):
    miss = [f'Montserrat-{x}.ttf' for x in names if not (Path(FONTS) / f'Montserrat-{x}.ttf').exists()]
    if miss:
        sys.exit(f"Нет шрифтов в {FONTS}: {', '.join(miss)}.\n"
                 "Montserrat распространяется по лицензии OFL 1.1 и лежит в архиве:\n"
                 "04_упаковка/шрифты/Montserrat/. Если каталог пуст — скачайте начертания\n"
                 "из https://github.com/JulietaUla/Montserrat или задайте FONTS_DIR.")
_need_faces('Bold','Regular','Medium','ExtraBold')
F=FONTS + '/Montserrat-'
im=Image.open(IN_DIR / 'мыло_лицо_основа_для_скрипта.png').convert('RGB');a=np.array(im).astype(int)
H,W=a.shape[:2];m=np.zeros((H,W),np.uint8)
s=a.sum(2)
def reg(x0,y0,x1,y1,cond): 
    sub=cond[y0:y1,x0:x1]; m[y0:y1,x0:x1]|=sub.astype(np.uint8)*255
ochre=(a[:,:,0]-a[:,:,2])>70
reg(392,163,735,256,(s<600)|ochre)          # знак + ДУБИНА 40+
reg(598,282,776,331,ochre)                   # СТОП
reg(420,352,960,470,s>420)                   # текст в полосе
reg(700,515,980,600,s<600)                   # мелкий текст
m=cv2.dilate(m,np.ones((5,5),np.uint8),2)
out=cv2.inpaint(np.array(im)[:,:,::-1],m,7,cv2.INPAINT_TELEA)[:,:,::-1]
im=Image.fromarray(out);d=ImageDraw.Draw(im)
# ochre sample from original СТОП
ys,xs=np.where(ochre[282:331,598:776]);oc=tuple(int(v) for v in np.median(a[282:331,598:776][ys,xs],0))
INK=(43,32,26);CREAM=(246,239,222)
def cap(font,px):  # size so that cap height == px
    for sz in range(8,200):
        f=ImageFont.truetype(font,sz);b=f.getbbox('Н')
        if b[3]-b[1]>=px: return f
def text(x,ytop,t,f,fill,anchor='l'):
    b=f.getbbox(t);w=b[2]-b[0];hb=f.getbbox('Н')
    X={'l':x,'c':x-w/2,'r':x-w}[anchor]-b[0]
    d.text((X,ytop-hb[1]),t,font=f,fill=fill)
    return X+b[0]+w
# логотип вдвое меньше, по центру коробки (ось x=686), центр по y=210
mark=Image.open(IN_DIR / 'знак_v2_A_для_скрипта.png').convert('RGBA'); mark=mark.crop(mark.getbbox()); mark=mark.resize((round(mark.size[0]*42/mark.size[1]),42),Image.LANCZOS)
fb=cap(F+'Bold.ttf',14);f4=cap(F+'Regular.ttf',12)
w1=fb.getbbox('ДУБИНА');w2=f4.getbbox('40+')
gw=mark.size[0]+9+(w1[2]-w1[0])+4+(w2[2]-w2[0]);x0=398  # левый край, как у исходного логотипа
im.paste(mark,(x0,190),mark)
e=text(x0+mark.size[0]+9,203,'ДУБИНА',fb,INK);text(e+4,204,'40+',f4,oc)
text(686,288,'ПРОТИВ',cap(F+'ExtraBold.ttf',37),oc,'c')
fw=cap(F+'ExtraBold.ttf',37)
text(686,366,'ВОЗРАСТНОГО',fw,CREAM,'c'); text(686,424,'ЗАПАХА',fw,CREAM,'c')
fs=cap(F+'Medium.ttf',14)
for i,t_ in enumerate(['pH 5,3','с танинами дуба']): text(969,549+i*23,t_,fs,INK,'r')
im.save(OUT_DIR / 'ДУБИНА_мыло_лицо.png');print('ok')
