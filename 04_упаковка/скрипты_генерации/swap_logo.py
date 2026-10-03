# -*- coding: utf-8 -*-
from PIL import Image
import numpy as np

# Пути считаются от расположения самого файла (правлено 03.10.2026).
import os, sys
from pathlib import Path
_HERE = Path(__file__).resolve().parent; _PACK = _HERE.parent
IN_DIR = _PACK / 'исходники_дизайнера'; OUT_DIR = _PACK / 'финальные_макеты'
# Папка uploads/ в архиве не сохранена; файл того же имени лежит в
# исходники_дизайнера/. Подстановка проверена побайтовым воспроизведением
# архивного УСТАРЕЛО_спина_порошок_v5.png — совпало, значит файл тот же.
FACE=IN_DIR / 'УСТАРЕЛО_порошок_цветной_40plus_лицо.png'
face=Image.open(FACE).convert('RGB')

# 1) вырезаем логотип с лицевой стороны
logo=face.crop((188,308,460,368))          # кольцо + ДУБИНА + 40+
L=np.array(logo).astype(int)

# 2) фон лица кремовый -> делаем альфу по яркости (тёмное = знак, золото тоже сохраняем)
r,g,b=L[:,:,0],L[:,:,1],L[:,:,2]
lum=(r*0.299+g*0.587+b*0.114)
bg=np.percentile(lum,92)                    # уровень кремового фона
alpha=np.clip((bg-lum)/(bg-40)*255,0,255).astype(np.uint8)
alpha[alpha<45]=0                            # убираем бледные фоновые дуги
logo_rgba=Image.fromarray(np.dstack([np.array(logo),alpha]).astype(np.uint8),'RGBA')

def swap(path,out,box):
    """box = (x,y,w) зона старого логотипа на спине"""
    im=Image.open(path).convert('RGB')
    x,y,w=box
    h=int(w*logo_rgba.size[1]/logo_rgba.size[0])
    # затираем старый логотип фоном-плиткой из чистой зоны
    tile=im.crop((30,526,im.size[0]-30,538))
    patch=Image.new('RGB',(im.size[0]-60,h+95))
    ty=0
    while ty<patch.size[1]:
        patch.paste(tile,(0,ty)); ty+=tile.size[1]
    im.paste(patch,(30,y-20))
    new=logo_rgba.resize((w,h),Image.LANCZOS)
    im.paste(new,(x,y),new)
    im.save(out); print('ok',out,im.size)

_gel=OUT_DIR / 'УСТАРЕЛО_спина_гель_v2.png'
if _gel.exists():
    swap(_gel, OUT_DIR / 'УСТАРЕЛО_спина_гель_v3.png', (48,38,330))
else:
    print('пропущено: нет входа УСТАРЕЛО_спина_гель_v2.png — его даёт '
          'add_gel_legal.py, а тому нужен отсутствующий в архиве _v1')
swap(OUT_DIR / 'УСТАРЕЛО_спина_порошок_v4.png', OUT_DIR / 'УСТАРЕЛО_спина_порошок_v5.png', (52,48,340))
