# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont

# Пути считаются от расположения самого файла (правлено 03.10.2026).
import os, sys
from pathlib import Path
_HERE = Path(__file__).resolve().parent; _PACK = _HERE.parent
OUT_DIR = _PACK / 'финальные_макеты'
DEJAVU = os.environ.get('DEJAVU_DIR', '/usr/share/fonts/truetype/dejavu').rstrip('/')
SRC=OUT_DIR / 'УСТАРЕЛО_спина_гель_v1.png'; OUT=OUT_DIR / 'УСТАРЕЛО_спина_гель_v2.png'
V3 =OUT_DIR / 'УСТАРЕЛО_спина_гель_v3.png'

# Восстановление входа. _v1 и _v2 никогда не коммитились (проверено по всей
# истории репозитория, 94 коммита) — они существовали только на машине автора.
# Но этот скрипт обратим: он переносит верх исходника дословно, низ дословно,
# а середину достраивает плиткой фона и текстом. Значит _v1 собирается из
# сохранённого _v3 без угадывания — ровно теми же срезами, только в обратную
# сторону. Проверено: цепочка на восстановленном входе даёт _v3 побайтово
# идентичный архивному (1 931 719 Б).
#
# Оговорка, которую важно не потерять. Восстановление точно везде, КРОМЕ зоны
# логотипа (примерно x 30..834, y 18..185): её на _v3 перезаписал swap_logo.py,
# и исходных пикселей под ней больше нет. Именно поэтому результат совпадает
# побайтово — следующий шаг всё равно затирает эту зону и клеит логотип заново.
# Как картинка «до правок» восстановленный _v1 неполон; как вход конвейера —
# достаточен и доказуемо точен.
_BB, _ADD = 1217, 430
def _restore_v1():
    from PIL import Image as _I
    v3 = _I.open(V3).convert('RGB'); W, H = v3.size
    top = v3.crop((0, 0, W, _BB - 2))
    bot = v3.crop((0, _BB - 2 + _ADD, W, H))
    out = _I.new('RGB', (W, top.size[1] + bot.size[1]))
    out.paste(top, (0, 0)); out.paste(bot, (0, top.size[1]))
    return out

_im_restored = None
if SRC.exists():
    pass                                    # настоящий исходник авторской машины
elif V3.exists():
    _im_restored = _restore_v1()
    print(f"вход {SRC.name} восстановлен из {V3.name} обратным срезом; "
          f"зона логотипа в нём не подлинная — её перезапишет swap_logo.py")
else:
    sys.exit(
        f"Нет ни {SRC.name}, ни {V3.name}.\n"
        "Конвейер был: _v1 -> (этот скрипт) -> _v2 -> swap_logo.py -> _v3.\n"
        "_v1 восстанавливается из сохранённого _v3, но если нет и его — "
        "строить не из чего.")
GREEN=(31,69,53); INK=(59,44,30)
F =DEJAVU + "/DejaVuSans.ttf"
FB=DEJAVU + "/DejaVuSans-Bold.ttf"

im=_im_restored if _im_restored is not None else Image.open(SRC).convert('RGB')
W,H=im.size
BL, BR, BT, BB = 22, 839, 22, 1217          # рамка исходника
ADD=430                                      # насколько удлиняем панель

canvas=Image.new('RGB',(W,H+ADD),(250,238,212))
# 1) всё до нижней рамки
canvas.paste(im.crop((0,0,W,BB-2)),(0,0))
# 2) растянутая полоса фона внутри рамки (берём чистый участок над QR)
tile=im.crop((0,674,W,692))          # чистая полоса фона без текста и колец
ty=BB-2
while ty < BB-2+ADD+2:
    canvas.paste(tile,(0,ty)); ty+=tile.size[1]
# 3) нижняя кромка с рамкой
canvas.paste(im.crop((0,BB-2,W,H)),(0,BB-2+ADD))

d=ImageDraw.Draw(canvas)
MX=int(W*0.055); MAXW=W-2*MX
S=int(W*0.0245); f=ImageFont.truetype(F,S); fb=ImageFont.truetype(FB,int(S*1.08))
LH=int(S*1.45)

y=BB-2+int(ADD*0.10)
d.line([(MX,y),(W-MX,y)],fill=GREEN,width=2); y+=int(S*1.2)

def para(runs,y):
    words=[]
    for t,fn,c in runs:
        for w in t.split(' '):
            if w: words.append((w+' ',fn,c))
    line=[];lw=0
    for w,fn,c in words:
        wl=d.textlength(w,font=fn)
        if lw+wl>MAXW and line:
            x=MX
            for tt,ff,cc in line: d.text((x,y),tt,font=ff,fill=cc); x+=d.textlength(tt,font=ff)
            y+=LH; line=[];lw=0
        line.append((w,fn,c)); lw+=wl
    if line:
        x=MX
        for tt,ff,cc in line: d.text((x,y),tt,font=ff,fill=cc); x+=d.textlength(tt,font=ff)
        y+=LH
    return y

y=para([("СОСТАВ (INCI): ",fb,GREEN),
 ("Aqua, Sodium Laureth Sulfate, Cocamidopropyl Betaine, Glycerin, Quercus Robur Bark Extract, Phenoxyethanol, Xanthan Gum, Polysorbate 20, Disodium EDTA, Potassium Sorbate, Camellia Sinensis Leaf Extract, o-Cymen-5-Ol, Citric Acid, Sodium Chloride.",f,INK)],y)
y+=int(S*0.8)
y=para([("Объём: 250 мл · pH 5,2 · Дата изготовления и срок годности: см. на упаковке · Партия: см. на упаковке · Хранить при +5…+25 °С, беречь от прямых солнечных лучей · Избегать попадания в глаза; при попадании промыть водой · Страна: Россия · Изготовитель: ООО «____________», адрес ____________ · Декларация ЕАЭС № ____________",f,INK)],y)

canvas.save(OUT); print('ok',canvas.size,'кегль',S,'низ текста',y,'рамка',BB+ADD)
