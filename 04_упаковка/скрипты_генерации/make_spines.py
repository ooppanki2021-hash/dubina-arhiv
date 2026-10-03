# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont
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

BG=(59,44,30); CREAM=(242,237,224); GREEN=(31,69,53); INK=(59,44,30)
F =DEJAVU + "/DejaVuSans.ttf"
FB=DEJAVU + "/DejaVuSans-Bold.ttf"

PW,PH=430,1380          # корешок
TW,TH=PH,PW             # холст до поворота
PAD_L=60                # поле вдоль корешка
PAD_T=34                # поле поперёк корешка
MAXW=TW-2*PAD_L         # доступная длина строки
_m=Image.new("RGB",(10,10)); _d=ImageDraw.Draw(_m)

def wrap(blocks,size):
    """blocks: список абзацев; абзац = список (текст,'b'|'g'|'n')
       возвращает список строк, строка = список (текст,шрифт,цвет)"""
    f=ImageFont.truetype(F,size); fb=ImageFont.truetype(FB,size)
    fg=ImageFont.truetype(FB,int(size*1.12))
    sty={'n':(f,INK),'b':(fb,INK),'g':(fg,GREEN)}
    out=[]
    for bi,para in enumerate(blocks):
        if bi: out.append(None)
        line=[]; lw=0
        for txt,st in para:
            fnt,col=sty[st]
            for word in txt.split(' '):
                if not word: continue
                w=_d.textlength(word+' ',font=fnt)
                if lw+w>MAXW and line:
                    out.append(line); line=[]; lw=0
                line.append((word+' ',fnt,col)); lw+=w
        if line: out.append(line)
    return out

def fit(blocks):
    """максимальный кегль, при котором блок заполняет корешок и влезает"""
    best=None
    for size in range(14,44):
        lines=wrap(blocks,size)
        n=len([l for l in lines if l]); g=len([l for l in lines if l is None])
        lh=size*1.45; need=n*lh+g*size*0.8
        if need<=TH-2*PAD_T:
            best=(size,lines,lh,size*0.8)
    return best

def render(blocks,size=None):
    if size is None:
        size,lines,lh,gap=fit(blocks)
    else:
        lines=wrap(blocks,size); lh=size*1.45; gap=size*0.8
    img=Image.new("RGB",(TW,TH),CREAM); d=ImageDraw.Draw(img)
    h=sum(gap if l is None else lh for l in lines)
    y=(TH-h)/2                      # равные поля поперёк
    for line in lines:
        if line is None: y+=gap; continue
        x=PAD_L                     # общее левое поле = ровный старт всех строк
        for txt,fnt,col in line:
            d.text((x,y),txt,font=fnt,fill=col); x+=d.textlength(txt,font=fnt)
        y+=lh
    img=img.rotate(90,expand=True)
    out=Image.new("RGB",(PW,PH),CREAM); out.paste(img,(0,0))
    d2=ImageDraw.Draw(out)
    d2.rectangle([14,14,PW-15,PH-15],outline=GREEN,width=2)
    d2.rectangle([22,22,PW-23,PH-23],outline=GREEN,width=1)
    return out,size

left=[
 [("СОСТАВ",'g'),("5–15%: анионные ПАВ. Менее 5%: КМЦ, ЭДТА, диоксид кремния, экстракт коры дуба, отдушка, токоферол, лимонная кислота. Без фосфатов.",'n')],
 [("ВНИМАНИЕ.",'b'),("Беречь от детей. Избегать попадания в глаза. При попадании промыть водой. Работать в перчатках. Не для шерсти и шёлка.",'n')],
]
right=[
 [("ДОЗИРОВКА",'g'),("на 5 кг сухого белья: 30 г — лёгкое загрязнение, мягкая вода; 50 г — стандартная стирка, жёсткая вода. Стирка при 60 °С и выше. 1 кг — 20–33 стирки.",'n')],
 [("Масса нетто: 1 кг · Дата изготовления и срок годности: см. на упаковке · Партия: см. на упаковке · Хранить в сухом месте при +5…+25 °С · Страна: Россия · Изготовитель: ООО «____________», адрес ____________ · Свидетельство о госрегистрации № ____________",'n')],
]

SZ=min(fit(left)[0],fit(right)[0])   # единый кегль для обоих корешков
L,s1=render(left,SZ); R,s2=render(right,SZ)
print("кегль:",SZ)
M=60; GAP=80
c=Image.new("RGB",(M*2+PW*2+GAP,M*2+PH),BG)
c.paste(L,(M,M)); c.paste(R,(M+PW+GAP,M))
c.save(OUT_DIR / "УСТАРЕЛО_корешки_порошок_цветной.png"); print("ok",c.size)
