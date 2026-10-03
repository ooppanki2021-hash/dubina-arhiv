# -*- coding: utf-8 -*-
"""Логотип на фирменном кремовом фоне (взят с лицевой стороны коробки)."""
from PIL import Image
import numpy as np
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

logo=Image.open(OUT_DIR / 'УСТАРЕЛО_логотип.png').convert('RGBA')
# Папка uploads/ в архиве не сохранена. Файл того же имени лежит в
# исходники_дизайнера/; подстановка проверена побайтовым воспроизведением
# архивного УСТАРЕЛО_логотип_на_фоне.png — совпало, значит файл тот же.
face=Image.open(IN_DIR / 'УСТАРЕЛО_порошок_цветной_40plus_лицо.png').convert('RGB')

# чистый кусок фона коробки -> плитка
tile=face.crop((200,400,300,440))
LW,LH=logo.size
M=int(LH*0.45)                       # поля вокруг знака
W,H=LW+2*M, LH+2*M

bg=Image.new('RGB',(W,H))
for y in range(0,H,tile.size[1]):
    for x in range(0,W,tile.size[0]):
        bg.paste(tile,(x,y))
# лёгкое усреднение, чтобы не было видно стыков плитки
a=np.array(bg).astype(float)
a=a*0.35+np.array([243,229,207])*0.65
bg=Image.fromarray(a.astype(np.uint8))

bg.paste(logo,(M,M),logo)
bg.save(OUT_DIR / 'УСТАРЕЛО_логотип_на_фоне.png')
print('ok',bg.size)

# крупная версия для читаемости
bg.resize((W*2,H*2),Image.LANCZOS).save(OUT_DIR / 'УСТАРЕЛО_логотип_на_фоне@2x.png')
