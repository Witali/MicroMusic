"""Build the illustrated Russian guide from pinned, retained firmware data.

Requires reportlab. All musical examples are checked against Git revision
a875a3e; no MIDI, SoundFont, network connection or firmware rebuild is used.
The PDF is vector based. The adjacent JSON records examples and input hashes.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import shutil
import subprocess
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, Line, String, Polygon, PolyLine, Circle
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak, Table, TableStyle

ROOT=Path(__file__).resolve().parents[1]
SOURCE_REVISION='a875a3ead0e6c0505fa964ff13b1415832455bb5'
REF=SOURCE_REVISION[:7]
GIT=shutil.which('git')
BLUE=colors.HexColor('#2459A6')
TEAL=colors.HexColor('#147D79')
ORANGE=colors.HexColor('#BD5A19')
PURPLE=colors.HexColor('#77549F')
GRAY=colors.HexColor('#61707C')
LIGHT=colors.HexColor('#EFF4FA')
GRID=colors.HexColor('#D9D9D9')
BLACK=colors.black
W=A4[0]-88
HASHES={}


def source(path):
    result=subprocess.run([GIT,'show',f'{SOURCE_REVISION}:{path}'],cwd=ROOT,check=True,capture_output=True).stdout
    HASHES[path]=hashlib.sha256(result).hexdigest()
    return result


def js(path):return json.loads(source(path))


def firmware(name):
    base=f'ATtiny13A/Music/variants/{name}/'
    report=js(base+'build-report.json')
    rom=source(base+'synth.bin');ep=source(base+'eeprom.bin')
    assert hashlib.sha256(rom).hexdigest()==report['flashSha256']
    assert hashlib.sha256(ep).hexdigest()==report['eepromSha256']
    return report,rom,ep


def collect():
    names=['rhythmic','alicia','turkish-march','children','greensleeves','lumiere-stereo',
           'cancion-del-mariachi-polyphonic','cancion-del-mariachi','cancion-del-mariachi-sparse']
    images={n:firmware(n) for n in names}
    scores={n:js(f'ATtiny13A/Music/variants/{n}/score.json') for n in names[:6]}
    codecs={n:js(f'ATtiny13A/Music/variants/{n}/compiled-score.json') for n in
            ['greensleeves','cancion-del-mariachi-polyphonic','cancion-del-mariachi-sparse']}
    bank=js('ATtiny13A/Music/instruments/bank.json')
    for path in ['tools/score-format.py','tools/pack-score.py','tools/instrument-bank.py',
                 'tools/build-lumiere-full.py','tools/arrange-alicia-multi.py','tools/alicia-native-template.S',
                 'tools/arrange-children-four.py','tools/children-native-template.S','tools/build-turkish-three.py',
                 'tools/build-mariachi-lossless.py','tools/pack-musical-events.py','tools/mariachi-percussion.py',
                 'tools/build-compact-four.py','tools/percussion-bank.py','tools/render-firmware-preview.mjs']:
        source(path)
    lr,rom,_=images['rhythmic'];lab=lr['labels']
    assert list(rom[lab['first_section']:lab['first_section']+7])==[224,25,57,97,64,80,225]
    assert rom[lab['chord_steps']:lab['chord_steps']+8].hex()=='5f0302040d058702'
    sparse=codecs['cancion-del-mariachi-sparse']
    assert sparse['bases'][2]==[1,8] and sparse['shapes'][1:3]==[58,182]
    assert sparse['rules'][61-sparse['baseCount']]==[1,2]
    full=codecs['cancion-del-mariachi-polyphonic']
    assert full['bases'][2]==[4,17] and full['shapes'][4:8]==[190,6,90,5]
    green=codecs['greensleeves']
    assert green['commands'][:10]==[15,42,72,102,129,0,32,64,96,17]
    assert len(green['commands'])==547 and len(green['rules'])*2==86 and len(green['stream'])==175
    gr,_,_=images['greensleeves'];norm=gr['outputNormalization']
    assert [norm['minimum'],norm['maximum']]==[-33,30] and len(norm['table'])==64
    assert bank['instruments']['violin']['waves']['low'][:2]==[-3,2]
    facts=dict(sourceRevision=SOURCE_REVISION,scope='ATtiny13A musical firmware only',
        images={n:{k:r[k] for k in ['flashBytes','codeBytes','tableBytes','eepromBytes','flashSha256','eepromSha256']}
                for n,(r,_,__) in images.items()},
        lumiere=dict(prefix=[224,25,57,97,64,80,225],chordBytes=list(rom[lab['chord_steps']:lab['chord_steps']+8]),
                     chordSteps=[int.from_bytes(rom[a:a+2],'little') for a in range(lab['chord_steps'],lab['chord_steps']+8,2)],
                     durations=lr['score']['durations'],compression=lr['score']['compression']),
        mariachiSparse=dict(base2=sparse['bases'][2],shapeAt1=sparse['shapes'][1:3],rule61=[1,2],
                             pitchPalette=sparse['pitchPalette'],gates=sparse['gates']),
        greensleeves=dict(prefix=green['commands'][:10],commands=547,streamBytes=175,ruleBytes=86,
                         normalizationBounds=[-33,30],normalizationGain=norm['gain']),
        waves={n:bank['instruments'][n]['waves'] for n in ['violin','acoustic-guitar-nylon']},inputSha256=HASHES)
    return images,scores,codecs,bank,facts


def text(d,x,y,value,size=10,anchor='start',font='Body',color=BLACK):
    d.add(String(x,y,str(value),fontName=font,fontSize=size,textAnchor=anchor,fillColor=color))


def block(d,x,y,w,h,lines,color=BLUE,size=10):
    d.add(Rect(x,y,w,h,fillColor=colors.Color(color.red,color.green,color.blue,.09),strokeColor=color,strokeWidth=.8,rx=4,ry=4))
    if isinstance(lines,str):lines=lines.split('\n')
    for i,s in enumerate(lines):text(d,x+w/2,y+h/2+(len(lines)-1)*7-i*14,s,size,'middle')


def arrow(d,x1,y1,x2,y2,color=GRAY):
    d.add(Line(x1,y1,x2,y2,strokeColor=color,strokeWidth=1.1))
    a=math.atan2(y2-y1,x2-x1);s=5
    d.add(Polygon([x2,y2,x2-s*math.cos(a-.5),y2-s*math.sin(a-.5),
                   x2-s*math.cos(a+.5),y2-s*math.sin(a+.5)],fillColor=color,strokeColor=color))


def bits(value,groups,labels,width=W):
    d=Drawing(width,115);left=44;bw=(width-left-8)/8;y=49
    at=0
    for length,color in groups:
        for i in range(length):
            b=at+i;d.add(Rect(left+b*bw,y,bw,30,fillColor=colors.Color(color.red,color.green,color.blue,.09),strokeColor=color,strokeWidth=.7))
            text(d,left+(b+.5)*bw,y+10,(value>>(7-b))&1,15,'middle','Mono')
            text(d,left+(b+.5)*bw,y+38,7-b,9,'middle',color=GRAY)
        at+=length
    text(d,0,58,f'0x{value:02X}',15,font='Mono')
    at=0
    for (length,color),label in zip(groups,labels):
        text(d,left+(at+length/2)*bw,23,label,10,'middle',color=color);at+=length
    return d


def pipeline():
    d=Drawing(W,219)
    nodes=[(0,155,140,48,'Исходные события\nJSON на компьютере',BLUE),
           (184,155,140,48,'Сборщик\nи упаковщик',TEAL),
           (368,155,139,48,'Flash\nкод и партитура',BLUE),
           (0,54,140,48,'EEPROM\nкороткие волны',ORANGE),
           (184,54,140,48,'Голоса DDS\nогибающие и сумма',TEAL),
           (368,54,139,48,'PWM и RC фильтр\nслышимый звук',PURPLE)]
    for x,y,w,h,t,c in nodes:block(d,x,y,w,h,t,c)
    arrow(d,141,179,181,179);arrow(d,325,179,365,179)
    arrow(d,438,153,254,105);arrow(d,141,78,181,78);arrow(d,325,78,365,78)
    text(d,438,130,'команды нот',9,'middle',color=BLUE)
    text(d,254,29,'SRAM хранит только текущее состояние и небольшую очередь',10,'middle')
    return d


def note_timeline():
    d=Drawing(W,240);x=104;span=W-x-8;unit=span/4
    lanes=[('Скрипка',BLUE,[(0,.5,'B3'),(.5,.5,'F#4'),(1,.5,'D5'),(1.5,.25,'G4'),(1.75,.25,'B4'),(2,.5,'G3'),(2.5,.5,'F#4'),(3,1,'C#5')]),
           ('Пиано 1',TEAL,[(0,2,'B3'),(2,2,'G3')]),('Пиано 2',TEAL,[(0,2,'D4'),(2,2,'B3')]),
           ('Пиано 3',TEAL,[(0,2,'F#4'),(2,2,'F#4')]),('Гитара',ORANGE,[(0,2,'F#3'),(2,2,'D3')])]
    for q in range(9):
        xx=x+q*unit/2;d.add(Line(xx,40,xx,219,strokeColor=GRID,strokeWidth=.5))
        if q%2==0:text(d,xx,24,q/2,9,'middle')
    for i,(label,color,notes) in enumerate(lanes):
        y=190-i*34;text(d,x-10,y+7,label,10,'end')
        for start,dur,pitch in notes:
            xx=x+start*unit;ww=dur*unit-1
            d.add(Rect(xx,y,ww,25,fillColor=colors.Color(color.red,color.green,color.blue,.14),strokeColor=color,strokeWidth=.7))
            text(d,xx+ww/2,y+8,pitch,9 if dur>=.5 else 7.5,'middle','Body')
    text(d,x+unit,225,'Bm',11,'middle','Bold',TEAL);text(d,x+3*unit,225,'Gmaj7',11,'middle','Bold',TEAL)
    text(d,x+span/2,4,'Время в четвертях    4 четверти = 3 секунды при 80 BPM',9.5,'middle')
    return d


def chord_figure(steps):
    d=Drawing(W,180);labels=['Пиано B3','Пиано D4','Пиано F#4','Гитара F#3']
    width=(W-18)/4
    for i,(step,label) in enumerate(zip(steps,labels)):
        xx=i*(width+6);c=ORANGE if i==3 else TEAL
        block(d,xx,125,width,31,f'{step&255:02X}  {step>>8:02X}',c,14)
        arrow(d,xx+width/2,121,xx+width/2,91,c)
        text(d,xx+width/2,73,f'0x{step:04X} = {step}',10,'middle','Mono')
        text(d,xx+width/2,50,label,11,'middle','Bold')
        text(d,xx+width/2,27,f'{step*18750/65536:.2f} Гц',10,'middle')
    text(d,W/2,165,'Одна строка chord_steps   8 байт',10,'middle',color=GRAY)
    return d


def decoder_figure():
    d=Drawing(W,205)
    block(d,12,139,130,44,'Счётчик ожидания\nдошёл до нуля',BLUE)
    block(d,187,139,135,44,'Прочитать байт\nиз Flash',BLUE)
    block(d,367,139,128,44,'Управление\nили FF',ORANGE)
    arrow(d,143,161,184,161);arrow(d,323,161,364,161)
    d.add(PolyLine([432,137,432,110,345,110,345,196,255,196],strokeColor=ORANGE,strokeWidth=1,fillColor=None))
    arrow(d,255,196,255,185,ORANGE)
    text(d,343,96,'время не меняется',9,'middle',color=ORANGE)
    block(d,177,14,155,56,'Нота REST или HOLD\nобновить голос\nзадать ожидание',TEAL)
    arrow(d,255,137,255,74,TEAL)
    block(d,12,20,130,44,'Вернуться\nк синтезу отсчётов',PURPLE)
    arrow(d,176,43,146,43,PURPLE)
    text(d,255,4,'Один вызов может обработать несколько команд управления',9,'middle')
    return d


def phrase_figure():
    d=Drawing(W,137)
    text(d,0,116,'playlist',11,font='Mono',color=BLUE)
    for i,v in enumerate(['A','B','A','A','B']):block(d,72+i*42,101,35,25,v,BLUE,11)
    block(d,58,20,165,46,'Фраза A\nкоманды ... FF',TEAL)
    block(d,285,20,165,46,'Фраза B\nкоманды ... FF',ORANGE)
    for i,v in enumerate(['A','B','A','A','B']):
        arrow(d,89+i*42,98,140 if v=='A' else 368,68,TEAL if v=='A' else ORANGE)
    text(d,W/2,1,'Схема условная   в настоящем playlist лежат смещения в байтах',9,'middle',color=GRAY)
    return d


def mariachi_figure():
    d=Drawing(W,220);left=88;span=W-left-12;s=span/640
    for tick in [0,160,320,480,640]:
        xx=left+tick*s;d.add(Line(xx,111,xx,192,strokeColor=GRID,strokeWidth=.5));text(d,xx,98,tick,9,'middle')
    for row,(name,color,segments) in enumerate([('B4',BLUE,[(0,160),(160,320),(480,640)]),('G4',TEAL,[(160,320),(480,640)])]):
        yy=165-row*39;text(d,left-12,yy+8,name,11,'end')
        for start,end in segments:d.add(Rect(left+start*s,yy,(end-start)*s-1,25,fillColor=colors.Color(color.red,color.green,color.blue,.15),strokeColor=color,strokeWidth=.8))
    text(d,left+400*s,151,'gap',11,'middle',color=ORANGE)
    text(d,left+560*s,199,'base 2',10,'middle',color=BLUE)
    block(d,0,18,117,52,'01 08\nбазовое событие',BLUE,11)
    arrow(d,120,44,165,44)
    block(d,169,18,144,52,'shape 1\n3A B6',TEAL,11)
    arrow(d,316,44,359,44)
    block(d,363,18,144,52,'EEPROM 58 и 54\nB4 и G4',ORANGE,10)
    text(d,W/2,78,'Тики исходника PPQN 480   одна единица кодека = 80 тиков',9,'middle')
    return d


def grammar_figure():
    d=Drawing(W,190)
    block(d,165,135,110,36,'61',PURPLE,15)
    arrow(d,187,132,128,99,PURPLE);arrow(d,252,132,316,99,PURPLE)
    block(d,80,56,95,39,'base 1',BLUE,12);block(d,280,56,95,39,'base 2',TEAL,12)
    text(d,127,35,'исполнить сейчас',10,'middle',color=BLUE)
    text(d,327,35,'отложить в стек',10,'middle',color=TEAL)
    text(d,W/2,7,'Порядок раскрытия   61 → 1 затем 2',11,'middle','Bold')
    block(d,409,61,90,74,'Стек\n2\n...',GRAY,11)
    text(d,220,178,'Реальное правило Mariachi sparse',10,'middle',color=GRAY)
    return d


def greens_figure():
    d=Drawing(W,175);x=112;span=W-x-15;half=span*.55
    for i,(name,pitch,code,c) in enumerate([('Флейта','E4',15,BLUE),('Скрипка','B3',42,TEAL),('Кларнет','G3',72,PURPLE),('Виолончель','E3',102,ORANGE)]):
        yy=134-i*32;text(d,x-10,yy+7,name,10,'end')
        d.add(Rect(x,yy,half,24,fillColor=colors.Color(c.red,c.green,c.blue,.12),strokeColor=c,strokeWidth=.8))
        text(d,x+half/2,yy+8,f'{pitch}   код {code}',10,'middle')
        if i==0:
            d.add(Rect(x+half+3,yy,span-half-3,24,fillColor=LIGHT,strokeColor=BLUE,strokeWidth=.8))
            text(d,x+half+(span-half)/2,yy+8,'G4   код 17',10,'middle')
    d.add(Line(x+half,21,x+half,162,strokeColor=GRAY,strokeWidth=.7))
    text(d,x,7,'0 с',9,'middle');text(d,x+half,7,'0,5 с',9,'middle')
    text(d,x+half+10,20,'Off 0 32 64 96',8,color=GRAY)
    return d


def macros_figure():
    d=Drawing(W,150);x=100;cell=(W-x-10)/16
    text(d,0,127,'Children',11,font='Bold')
    for i in range(17):
        xx=x+i*cell;d.add(Line(xx,44,xx,118,strokeColor=GRID,strokeWidth=.5))
        if i%4==0:text(d,xx,31,i,9,'middle')
    for label,yy,c,starts,dur in [('Эхо F5',87,TEAL,[0,4,8,12],2),('Бас Db2',51,ORANGE,[0],16)]:
        text(d,x-10,yy+8,label,10,'end')
        for i in starts:
            d.add(Rect(x+i*cell,yy,dur*cell-1,25,fillColor=colors.Color(c.red,c.green,c.blue,.15),strokeColor=c,strokeWidth=.7))
    text(d,x+(W-x)/2,9,'Шестнадцатые в одном такте   команда 0x98 задаёт весь рисунок',9,'middle')
    return d


def wave_figure(bank):
    d=Drawing(W,210);x=35;y=85;ww=W-53;hh=104
    waves=[('Скрипка',bank['instruments']['violin']['waves']['low'],BLUE),
           ('Гитара',bank['instruments']['acoustic-guitar-nylon']['waves']['low'],ORANGE)]
    for value in [-8,-4,0,4,8]:
        yy=y+value*hh/16;d.add(Line(x,yy,x+ww,yy,strokeColor=GRID,strokeWidth=.5));text(d,x-8,yy-3,value,9,'end')
    for name,values,c in waves:
        points=[]
        for i,v in enumerate(values):points.extend([x+i*ww/16,y+v*hh/16,x+(i+1)*ww/16,y+v*hh/16])
        d.add(PolyLine(points,strokeColor=c,strokeWidth=1.6,fillColor=None))
        for i,v in enumerate(values):d.add(Circle(x+i*ww/16,y+v*hh/16,1.7,fillColor=c,strokeColor=c))
    for i in range(16):text(d,x+(i+.4)*ww/16,17,i,8.5,'middle')
    text(d,W/2,1,'Номер отсчёта в одном периоде   0 … 15',9.5,'middle')
    text(d,42,183,'Скрипка',10,color=BLUE);text(d,150,183,'Нейлоновая гитара',10,color=ORANGE)
    text(d,W/2,199,'Реальные младшие волны из bank.json',10,'middle')
    return d


def nibble_figure():
    d=Drawing(W,112)
    block(d,185,66,130,32,'A5',BLUE,17)
    arrow(d,202,62,116,36,ORANGE);arrow(d,296,62,392,36,TEAL)
    text(d,112,17,'Старшие 4 бита A = 10',11,'middle',color=ORANGE)
    text(d,393,17,'Младшие 4 бита 5 = 5',11,'middle',color=TEAL)
    text(d,112,0,'второй отсчёт 10 − 8 = +2',10,'middle')
    text(d,393,0,'первый отсчёт 5 − 8 = −3',10,'middle')
    return d


def dds_figure():
    d=Drawing(W,210);x=38;y=67;ww=W-53;hh=85
    for n in [0,16384,32768,49152,65536]:
        yy=y+n/65536*hh;d.add(Line(x,yy,x+ww,yy,strokeColor=GRID,strokeWidth=.5));text(d,x-5,yy-3,'64k' if n==65536 else str(n//1024)+'k',8,'end')
    for step,c in [(769,TEAL),(1538,BLUE)]:
        pts=[]
        for i in range(90):
            xx=x+i/89*ww;phi=((i+1)*step)%65536
            if i and phi<((i*step)%65536):
                if len(pts)>3:d.add(PolyLine(pts,strokeColor=c,strokeWidth=1.4,fillColor=None))
                pts=[]
            pts.extend([xx,y+phi/65536*hh])
        if len(pts)>3:d.add(PolyLine(pts,strokeColor=c,strokeWidth=1.4,fillColor=None))
    text(d,48,181,'A3  шаг 769  около 220 Гц',10,color=TEAL)
    text(d,48,164,'A4  шаг 1538  около 440 Гц',10,color=BLUE)
    text(d,W/2,45,'Номер синтезированного отсчёта   0 … 89',9.5,'middle')
    text(d,W/2,23,'Фаза доходит до 65536 и оборачивается к нулю',10,'middle')
    return d


def envelope_figure():
    d=Drawing(W,188);x=42;y=40;ww=W-60;hh=113
    for level in [0,5,10,15]:
        yy=y+level/15*hh;d.add(Line(x,yy,x+ww,yy,strokeColor=GRID,strokeWidth=.5));text(d,x-8,yy-3,level,9,'end')
    # Conceptual trajectories, intentionally not a claim of one shared ADSR.
    bowed=[min(15,4*i) if i<22 else max(0,15-(i-21)) for i in range(40)]
    piano=[max(1,15-int(3*math.log(1+i))) if i<22 else max(0,5-2*(i-21)) for i in range(40)]
    for values,c in [(bowed,TEAL),(piano,ORANGE)]:
        d.add(PolyLine([v for i,a in enumerate(values) for v in (x+i/39*ww,y+a/15*hh)],strokeColor=c,strokeWidth=1.7,fillColor=None))
    xx=x+22/39*ww;d.add(Line(xx,y,xx,y+hh+7,strokeColor=GRAY,strokeWidth=.8,strokeDashArray=[3,3]))
    text(d,xx,18,'Note Off',10,'middle')
    text(d,62,169,'Смычковый звук',10,color=TEAL);text(d,244,169,'Щипок или пиано',10,color=ORANGE)
    text(d,W/2,0,'Условная форма огибающих   конкретные ступени задаёт профиль прошивки',9,'middle',color=GRAY)
    return d


def normalization_figure():
    d=Drawing(W,153);x=42;y=40;ww=W-58;hh=91
    for value in [0,64,128,192,255]:
        yy=y+value/255*hh;d.add(Line(x,yy,x+ww,yy,strokeColor=GRID,strokeWidth=.5));text(d,x-7,yy-3,value,9,'end')
    for fn,c in [(lambda v:128+v,GRAY),(lambda v:128+4*v,BLUE)]:
        d.add(PolyLine([a for v in range(-32,32) for a in (x+(v+32)/63*ww,y+fn(v)/255*hh)],strokeColor=c,strokeWidth=1.8,fillColor=None))
    text(d,x,22,'−32',9,'middle');text(d,x+32/63*ww,22,'0',9,'middle');text(d,x+ww,22,'+31',9,'middle')
    text(d,W/2,3,'Сумма голосов до общего усиления',9.5,'middle')
    text(d,53,140,'Без усиления',9.5,color=GRAY);text(d,218,140,'Mariachi sparse ×4',9.5,color=BLUE)
    return d


def pwm_figure():
    d=Drawing(W,205);x=40;ww=W-56;period=ww/6
    duty=[64,128,192,128,64,192]
    for i,v in enumerate(duty):
        start=x+i*period;on=period*v/256
        d.add(PolyLine([start,133,start,174,start+on,174,start+on,133,start+period,133],strokeColor=BLUE,strokeWidth=1.2,fillColor=None))
        d.add(Line(start,50,start,182,strokeColor=GRID,strokeWidth=.5))
        text(d,start+period/2,114,str(v),10,'middle','Mono')
        yy=54+v/256*43
        d.add(Line(start,yy,start+period,yy,strokeColor=ORANGE,strokeWidth=2.2))
    text(d,0,158,'PWM',10);text(d,0,73,'RC',10)
    text(d,W/2,192,'Высота импульса постоянна   меняется его длительность',10,'middle')
    text(d,W/2,28,'Один период PWM ≈ 26,67 мкс   около 37 500 периодов в секунду',9.5,'middle')
    text(d,W/2,7,'Рисунок идеализирован   оранжевым показан средний уровень периода',9,'middle',color=GRAY)
    return d


def fifo_figure():
    d=Drawing(W,95);values=['ср.','нов.','ср.','нов.','ср.','нов.','…','…'];x=56;bw=47
    for i,v in enumerate(values):block(d,x+i*bw,35,bw-3,27,v,BLUE if i%2 else TEAL,10)
    text(d,0,81,'Основной цикл добавляет пары значений',10,color=TEAL)
    text(d,W,4,'ISR забирает по одному значению',10,'end',color=BLUE)
    arrow(d,5,49,50,49,TEAL);arrow(d,x+8*bw,49,W-4,49,BLUE)
    return d


def flash_figure(images):
    d=Drawing(W,270);x=132;ww=W-x-42
    labels=[('rhythmic','Люмьер моно'),('lumiere-stereo','Люмьер стерео'),('alicia','Алисия'),
            ('children','Children'),('turkish-march','Турецкий марш'),('greensleeves','Greensleeves'),
            ('cancion-del-mariachi-polyphonic','Mariachi все ноты'),('cancion-del-mariachi-sparse','Mariachi sparse'),
            ('cancion-del-mariachi','Mariachi ансамбль')]
    for i,(name,label) in enumerate(labels):
        r=images[name][0];yy=230-i*23;text(d,x-9,yy+4,label,9.3,'end')
        a=r['codeBytes']/1024*ww;b=r['tableBytes']/1024*ww
        d.add(Rect(x,yy,a,15,fillColor=BLUE,strokeColor=None));d.add(Rect(x+a,yy,b,15,fillColor=ORANGE,strokeColor=None))
        text(d,x+a+b+5,yy+3,r['flashBytes'],9)
    d.add(Line(x+ww,38,x+ww,251,strokeColor=GRAY,strokeWidth=.8,strokeDashArray=[2,2]))
    text(d,x+ww,257,'1024 Б',9,'middle')
    text(d,x,5,'Код AVR',10,color=BLUE);text(d,x+110,5,'Все таблицы и партитура',10,color=ORANGE)
    return d


def memory_figure():
    d=Drawing(W,105);x=15;ww=W-30;y=52;parts=[(25,'Голоса',BLUE),(7,'',GRID),(16,'FIFO',TEAL),(10,'',GRID),(6,'Стек',ORANGE)]
    at=0
    for count,label,c in parts:
        width=count/64*ww;d.add(Rect(x+at/64*ww,y,width,30,fillColor=c,strokeColor=colors.white,strokeWidth=.7))
        if label:text(d,x+(at+count/2)/64*ww,y+10,f'{label} {count}',9,'middle',color=colors.white)
        at+=count
    text(d,x,y-17,'96',9);text(d,x+ww,y-17,'159',9,'end')
    text(d,W/2,4,'Пример Lumière mono   25 Б состояния + 16 Б очереди + до 6 Б стека',9.5,'middle')
    return d


class Guide(BaseDocTemplate):
    def afterFlowable(self,flowable):
        name=getattr(flowable,'guide_bookmark',None)
        if name:
            self.canv.bookmarkPage(name)
            self.canv.addOutlineEntry(flowable.getPlainText(),name,0,False)


def build(output,fontdir):
    fonts=[('Body','arial.ttf','DejaVuSans.ttf'),('Bold','arialbd.ttf','DejaVuSans-Bold.ttf'),
           ('Mono','consola.ttf','DejaVuSansMono.ttf')]
    for family,win,unix in fonts:
        path=fontdir/win
        if not path.exists():path=fontdir/unix
        pdfmetrics.registerFont(TTFont(family,str(path)))
    pdfmetrics.registerFontFamily('Body',normal='Body',bold='Bold',italic='Body',boldItalic='Bold')
    images,scores,codecs,bank,facts=collect()
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle('GuideTitle',fontName='Bold',fontSize=26,leading=31,textColor=BLACK,spaceAfter=17))
    styles.add(ParagraphStyle('GuideH',fontName='Bold',fontSize=21,leading=26,textColor=BLACK,spaceAfter=14,keepWithNext=True))
    styles.add(ParagraphStyle('GuideBody',fontName='Body',fontSize=11.2,leading=15.7,textColor=BLACK,spaceAfter=9))
    styles.add(ParagraphStyle('GuideSmall',fontName='Body',fontSize=9.3,leading=12.8,textColor=GRAY,spaceAfter=8))
    styles.add(ParagraphStyle('GuideCode',fontName='Mono',fontSize=10.2,leading=14,textColor=BLACK,spaceBefore=5,spaceAfter=11))
    styles.add(ParagraphStyle('GuideCell',fontName='Body',fontSize=9.8,leading=13,textColor=BLACK))
    styles.add(ParagraphStyle('GuideHeader',parent=styles['GuideCell'],fontName='Bold',textColor=colors.white))
    story=[];page=0
    def p(value,kind='GuideBody'):story.append(Paragraph(value,styles[kind]))
    def h(title,first=False):
        nonlocal page
        if page:story.append(PageBreak())
        page+=1
        element=Paragraph(title,styles['GuideTitle' if first else 'GuideH']);element.guide_bookmark=f'section_{page}'
        story.append(element)
    def fig(d,caption):
        story.append(Spacer(1,5));story.append(d);story.append(Spacer(1,5));p(caption,'GuideSmall')
    def table(headers,rows,widths):
        cells=[[Paragraph(escape(str(v)),styles['GuideHeader']) for v in headers]]
        cells += [[Paragraph(escape(str(v)),styles['GuideCell']) for v in row] for row in rows]
        t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#263C56')),('GRID',(0,0),(-1,-1),.5,GRID),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.append(t);story.append(Spacer(1,12))

    h('Ноты, аккорды и тембры<br/>в ATtiny13A',True)
    p('Как музыка хранится в памяти и превращается в звук','GuideBody')
    p('В наших музыкальных прошивках хранится компактная партитура и несколько коротких периодов звуковой волны. Микроконтроллер читает команды, рассчитывает голоса и выдаёт PWM. Полной звукозаписи мелодии в его памяти нет.')
    fig(pipeline(),'Схема 1. Подготовка данных выполняется на компьютере. Декодирование команд и синтез звука происходят в настоящей AVR-прошивке.')
    table(['Память','Размер','Что в ней находится'],[['Flash','1024 байта','Код AVR, команды, словари, частоты и другие таблицы'],['EEPROM','64 байта','Короткие волны тембров; в sparse Mariachi также частоты'],['SRAM','64 байта','Состояние голосов, очередь PWM, стек']], [75,84,W-159])
    p('Дальше: ноты и аккорды → упакованные байты → короткие волны → DDS → огибающие → микшер → PWM. В проекте несколько диалектов команд; их различия собраны на странице 15.')
    p(f'MicroMusic · музыкальные прошивки · срез {REF} от 24 октября 2026 года. Речь LPC и другие звуковые кодеки в этот документ не входят.','GuideSmall')

    h('Нота, партия и физический голос')
    p('<b>Нота</b> задаёт высоту и музыкальные границы звучания. <b>Партия</b> — последовательность нот инструмента. <b>Тембр</b> — форма волны и огибающая. <b>Голос</b> — один генератор, который в данный момент воспроизводит одну высоту.')
    fig(note_timeline(),'Схема 2. Первый такт Lumière. Три тональные партии используют пять генераторов: скрипка, три ноты пианино и гитара. Четвёртая партия ударных на рисунке не показана.')
    p('У пианино одна партия, но аккорд требует сразу трёх голосов. Поэтому «четыре инструмента» и «четыре одновременно звучащие ноты» — разные величины. Один тембр можно использовать во многих голосах без копирования его волны.')
    p('В JSON исходника сохраняются дорожки, MIDI-высоты, тики, Note On и Note Off, программы, контроллеры и метаданные. В Flash попадает уже подготовленная для конкретного движка версия. Сама прошивка не является универсальным MIDI-плеером.')
    p('Прямоугольники показывают музыкальные границы событий. Громкость внутри ноты меняется; после Note Off возможен хвост затухания. Название B3 здесь означает си малой октавы в научной системе, MIDI 59.')

    h('Нота занимает один командный байт')
    p('В Lumière и «Турецком марше» пять старших битов задают <b>индекс высоты P</b>, три младших — <b>индекс длительности D</b>. Значения читаются из отдельных маленьких таблиц.')
    p('Префикс 0x обозначает шестнадцатеричное число. В дампах его опускаем: байт 19 — это 0x19, или 25 в десятичной системе. Номера символов словаря и команды Greensleeves ниже даны десятично.','GuideSmall')
    fig(bits(0x19,[(5,BLUE),(3,ORANGE)],['P = 3 → B3','D = 1 → 2 единицы']),'Схема 3. Реальный байт 0x19. Это не MIDI-номер 25: число 3 выбирает B3 из палитры данной прошивки.')
    table(['D','Единиц сетки','Длительность в четвертях'],[[i,v,['¼','½','¾','1','1½','2','4'][i]] for i,v in enumerate([1,2,3,4,6,8,16])],[56,110,W-166])
    p('Одна единица здесь — шестнадцатая, то есть четверть / 4. При 80 BPM четверть длится 0,75 с. Команда 0x19 держит ноту две единицы: <b>0,375 с</b>. Код длительности 7 в этом диалекте не используется.')
    p('В Lumière индекс 13 означает REST, индекс 14 — HOLD. REST отпускает солирующий голос и запускает затухание. HOLD продолжает прежнюю ноту без новой атаки. Повторная нота той же высоты остаётся новой атакой. Числовые индексы REST и HOLD у других прошивок отличаются.')

    h('Один аккорд запускает несколько нот')
    p('Команда <b>E0</b> выбирает аккорд Bm. Она занимает один байт в потоке, но ссылается на отдельную строку таблицы. В нынешнем Lumière строка содержит четыре 16-битных приращения фазы DDS: три для пианино, одно для гитары.')
    fig(chord_figure(facts['lumiere']['chordSteps']),'Схема 4. Реальные восемь байт аккорда Bm. В каждом слове младший байт записан первым: 5F 03 означает 0x035F, то есть 863.')
    p('Скрипка использует собственную команду ноты и не входит в эти восемь байт. Частоты уже рассчитаны сборщиком: AVR не ищет интервалы минорного аккорда и не вычисляет степень двойки.')
    p('В аккорде Gmaj7 пианино играет G3, B3 и F#4, а гитара D3 дополняет квинту. Так четыре голоса дают четыре нужных класса высот. F# и F#m теперь отличаются нотой A# или A; одного басового корня для передачи этого различия недостаточно.')
    table(['Вариант','Данные одного аккорда'],[['Lumière','8 байт: три пианных DDS и один гитарный'],['Турецкий марш','4 байта: две выбранные ноты левой руки'],['Алисия','2 байта: индексы двух тонов, баса и длительности'],['Children','Дескриптор рисунка встроен в командный байт']], [147,W-147])
    p('Палитра Lumière хранит шесть уникальных расположений аккордов. Они переиспользуются при каждой смене гармонии. Это реализация аккордов сохранённой адаптации, а не восстановление полной оркестровой партитуры. [1, 2]','GuideSmall')

    h('Декодер и повторяющиеся фразы')
    p('В основном диалекте E0–EF выбирают гармонию. F1–FE отпускают партии по битовой маске: 1 — соло, 2 — пианино, 4 — гитара, 8 — ударные. В Lumière один бит пианино относится сразу ко всем трём его нотам. Команда FF выбирает следующую фразу; она сама не является паузой или Note Off.')
    fig(decoder_figure(),'Схема 5. Команды управления выполняются без сдвига музыкального времени. Нота, REST или HOLD устанавливает ожидание до следующего события.')
    fig(phrase_figure(),'Схема 6. Повтор читается по ссылке. В этом формате не нужно заранее распаковывать всю партитуру в SRAM.')
    p('playlist содержит однобайтовые смещения от начала melody_data. Фразы заканчиваются FF. Короткая фраза может использовать совпадающий конец длинной. Адрес начала должен помещаться в байт, но чтение фразы идёт 16-битным указателем и может продолжиться дальше смещения 255.')
    p('У Lumière развёрнутый поток содержит 491 командный байт, а фразы вместе с playlist — 231 байт. Более строгая оценка экономии: прежнее хранение секций занимало 257 байт, новое — 231, то есть выигрыш 26 байт. Частотные и другие таблицы считаются отдельно. [3]','GuideSmall')

    h('Mariachi хранит форму аккорда и время')
    p('В двухгитарном движке <b>shape</b> — конкретный список высот, включаемых одновременно и имеющих общий момент Note Off. Например B4 и G4. Базовое событие выбирает shape, паузу gap и удержание gate.')
    p('<b>on = предыдущий off + gap × единица</b><br/><b>off = on + gate × единица</b>','GuideCode')
    fig(mariachi_figure(),'Схема 7. Реальное начало sparse Mariachi. Gap считается от предыдущего Note Off. После отпускания струны её огибающая может ещё затихать.')
    p('В sparse-версии base 2 хранится как <b>01 08</b>. Байт 01 выбирает shape со смещения 1. Байт 08 = 00001 | 000: старшие пять битов дают gap / 2 = 1, значит gap = 2; младшие три выбирают gate[0] = 2. Одна единица — 80 исходных тиков, или 1/6 четверти: около 79,37 мс при 126 BPM.')
    p('Shape <b>3A B6</b> содержит адреса частот в EEPROM. 3A даёт адрес 58 → B4; B6 после снятия старшего бита даёт адрес 54 → G4. Старший бит B6 означает конец аккорда. В EEPROM эти частоты занимают по два байта.')
    p('У полной 1027-нотной версии формат другой: в shape лежат готовые DDS-слова с нулевым заполнением до 2 или 6 струн. Например BE 06 5A 05 — B4 и G4. Второй байт базы хранит индекс gap в старшей половине и gate прямо в младшей. Единица там равна 160 тикам, или 1/3 четверти. [4]','GuideSmall')
    p('У sparse сохранена 261 нота соло, сопровождение переработано до 120 нот. Упаковка этих 381 ноты точная; это другая аранжировка, а не сжатие всех прежних партий.','GuideSmall')

    h('Словарь раскрывается по мере чтения')
    p('В Mariachi и Greensleeves часто повторяющиеся пары символов заменяются одним новым символом. Правило тоже может ссылаться на более ранние правила. Это ограниченная бинарная грамматика, а не распаковка большого аудиофайла.')
    fig(grammar_figure(),'Схема 8. В sparse Mariachi баз 59. Символ 61 — правило, раскрывающееся в базовые события 1 и 2. Сначала исполняется 1, затем отложенное 2.')
    p('Условный пример: A B A B A B → X X X, где правило X = A B. Шесть байт превращаются в три ссылки и два байта правила: всего пять. Поиск словаря ограничен глубиной и не обещает математически минимального размера.')
    p('Декодер читает символ. Если это правило (A, B), он кладёт B в маленький стек ожидания и продолжает с A. Закончив A, берёт отложенное B. В RAM одновременно находятся только несколько символов, а не вся развернутая песня.')
    table(['Движок','Границы символов и стек'],[['Mariachi full','0…BASE_COUNT−1 — база; от BASE_COUNT — правило; FF — конец партии. Стеки 2 + 5 байт'],['Mariachi sparse','Тот же принцип; отдельные стеки двух гитар 4 + 3 байта'],['Greensleeves','0…191 — команды, 192…254 — правила; стек до 8 байт']], [150,W-150])
    p('Два гитарных потока имеют собственные курсоры и счётчики времени. Это позволяет одной гитаре держать аккорд, пока другая меняет ноты. Архивный формат MNC1 из pack-musical-events.py — отдельный формат на компьютере; прошивка не читает его заголовок напрямую. [4, 5]')

    h('Greensleeves хранит отдельные Note On и Off')
    p('Здесь четыре одноголосные партии, каждая со своим инструментом. Команда 0…127 содержит номер партии в битах 6…5 и однобазовый индекс высоты в битах 4…0. Индекс 0 означает Note Off. Высот в текущей общей палитре 22.')
    table(['Диапазон байтов','Действие'],[['0…127','Note On / Off выбранной партии'],['128…191','Ждать byte − 127 шестнадцатых: от 1 до 64'],['192…254','Раскрыть бинарное правило словаря'],['255','Начать поток сначала']], [145,W-145])
    fig(greens_figure(),'Схема 9. Реальное начало: 15 42 72 102 129 0 32 64 96 17. Команда 129 ждёт две шестнадцатых, то есть 0,5 с при 60 BPM.')
    p('Первые четыре команды включают E4, B3, G3 и E3 в разных партиях без ожиданий между ними. Затем идут четыре Off и новая G4 у флейты. При совпадении моментов сначала исполняются Off, затем On.')
    p('Поток начинается двумя сжатыми символами 201 и 206. Первый раскрывается в четыре начальные ноты, второй — в ожидание, четыре выключения и новую ноту. Все 235 On + 235 Off + 77 ожиданий дают 547 команд. Они занимают 175 байт потока с маркером конца и 86 байт правил. Частоты, уровни и нормализация хранятся отдельно. [6]')

    h('Специальные макросы экономят память')
    p('<b>Алисия.</b> Сетка содержит 12 единиц на четверть, поэтому сохраняются триоли. Двухбайтовый дескриптор <b>0x61 0x60</b> означает: тон A с индексом 1 = G3, тон B с индексом 6 = C4, бас с индексом 0 = C2, длительность 6 × 6 = 36 единиц = три четверти.')
    p('Одна команда запускает бас C2 и внутреннюю скрипку C4. Пианино чередует G3 и C4 каждые шесть единиц, то есть на восьмых. Перед границей аккорда сопровождение отпускается. Сотни повторных атак создаёт небольшой счётчик, а не сотни копий байтов.')
    p('<b>Children.</b> Команда <b>0x98 = 152</b> — уже сам дескриптор. Вычитаем 142: получаем 10 = 0x0A. Младшие четыре бита выбирают F5 для эха, старшие — бас Db2 и его рисунок. Пока макрос прежний, его не требуется повторять в каждом такте.')
    fig(macros_figure(),'Схема 10. Рисунок команды 0x98: эхо F5 на четвертях с gate восьмой и одна басовая атака в такте. Это макрос выбранной аранжировки, а не общее правило всех MIDI-файлов.')
    p('У Children особое правило также создаёт 448 поздних атак F5 в тембре GM50 на тактах 112…139, используя освободившийся голос пианино. Такое сокращение работает потому, что повторяемость отдельно сверена с исходными событиями.')
    p('Музыкальная редукция и упаковка — разные этапы. В «Алисии» третий тон исходных аккордов ещё опущен. В Children эхо и ранние струнные упрощены, некоторые поздние слои отсутствуют. Точное сжатие оставшегося потока не возвращает отброшенные ноты. [7, 8]')

    h('Сэмпл здесь является коротким периодом волны')
    p('Для тонального инструмента хранится не многосекундная PCM-запись, а 16 амплитуд одного повторяемого периода. Амплитуда — целое число от −8 до +7. Два значения помещаются в один байт: один период занимает всего <b>8 байт</b>.')
    fig(wave_figure(bank),'График 11. Реальные 16-точечные волны низкого регистра из банка FluidR3. Ступени показывают табличные отсчёты; линия не означает интерполяцию между ними.')
    fig(nibble_figure(),'Схема 12. Первый байт младшей волны скрипки — A5. Первый отсчёт находится в младших четырёх битах. Это offset binary: из каждой половинки вычитается 8.')
    p('У инструмента обычно две волны: low и high, вместе 16 байт. Код выбирает регистр по DDS-шагу; в рассматриваемых движках high начинается с шага 1024, примерно от 293 Гц. У пианино могут быть дополнительные волны атаки.')
    p('Типичная EEPROM: 3 пары волн = 48 байт, ещё 16 — атака пианино. Greensleeves отдаёт все 64 байта четырём инструментам. Sparse Mariachi использует 32 байта для двух гитар, 30 — для 15 частот, 2 оставляет свободными. Эти раскладки не взаимозаменяемы. [9]')

    h('DDS задаёт высоту звука скоростью фазы')
    p('Каждый голос хранит 16-битную фазу и 16-битный шаг. На каждом новом аудиоотсчёте фаза увеличивается; переполнение оборачивает её по кругу. Четыре старших бита выбирают одну из 16 амплитуд волны.')
    p('phase = (phase + step) mod 65536<br/>index = phase &gt;&gt; 12<br/>q = waveform[index]','GuideCode')
    fig(dds_figure(),'График 13. При удвоении шага период волны проходится вдвое быстрее. Пила на графике — фаза генератора, а не форма слышимого сигнала.')
    p('На компьютере сборщик переводит MIDI-высоту в частоту: f = 440 × 2^((n − 69) / 12), затем step = round(f × 65536 / 18750). Например A4 даёт step = <b>1538 = 0x0602</b>; в таблице лежат байты <b>02 06</b>. Реальная частота DDS — около 440,025 Гц.')
    p('Внутри периода интерполяции между 16 точками нет. Точность частоты задаётся 16-битным шагом, а грубость формы волны — её 16 точками и четырёхбитной амплитудой. Это разные ограничения.')
    p('У Lumière, Greensleeves, «Алисии», Children и марша фаза на атаке сохраняется. У двухгитарной Mariachi она сбрасывается. В некоторых DDS-словах марша и Children старший бит служит флагом быстрого затухания; перед использованием частоты он снимается. [1, 4, 6]')

    h('Огибающая делает форму волны инструментом')
    p('Одна и та же повторяющаяся волна без управления громкостью звучала бы как непрерывный тон. Огибающая задаёт атаку, спад и отпускание. Note Off снимает удержание; он не обязан немедленно обнулять звук.')
    fig(envelope_figure(),'График 14. Смычковый профиль плавно набирает уровень, щипковый или пианный — начинает с атаки и спадает. Это поясняющая схема, а не измеренные кривые конкретной записи.')
    p('Управляющий тик происходит примерно 73,24 раза в секунду, то есть раз в 13,65 мс. Простые прибавления, вычитания и битовые маски заменяют дорогие вычисления экспонент. В пианных профилях при малых уровнях спад может замедляться.')
    p('«Алисия» и Children имеют по два дополнительных голоса для хвостов: старая частота, фаза и огибающая копируются в более тихий из двух слотов, при необходимости заменяя уже звучащий хвост. В новых Lumière и марше это место занято настоящими нотами аккордов. В Greensleeves дополнительных хвостовых голосов нет.')
    p('<b>Ударные не читаются как PCM.</b> Бас-барабан строится коротким треугольным генератором, хай-хэт — шумом 16-битного LFSR с периодом 65 535 состояний. Спад задаётся ступенями 1, ½, ½, ¼. В sparse Mariachi применяется дополнительное тихое усиление примерно 1/8 с округлением.')
    p('Процедурные ударные экономят EEPROM. В стерео Lumière малый барабан использует шум без отдельного тонального тела; это осознанный компромисс, чтобы поместились второй выход и дополнительные ноты. [9, 10]')

    h('Микшер и постоянная нормализация')
    p('После чтения волны её отсчёт масштабируется огибающей. Например в Greensleeves вклад голоса равен <b>floor(q × level / 8)</b>. У других профилей коэффициенты отличаются; у Mariachi сначала суммируются струны одной гитары, затем применяется общая огибающая аккорда.')
    p('Затем вклады складываются. Микшер AVR использует ограниченные целочисленные регистры: выход за допустимый диапазон дал бы переполнение, а не мягкий лимитер. Поэтому аудитор отдельно суммирует вклады без ограничения разрядности и проверяет границы.')
    fig(normalization_figure(),'График 15. Sparse Mariachi: измеренный исходный микс −32…+31 после общего усиления ×4 превращается в PWM 0…252. Центр остаётся 128.')
    p('В Greensleeves возможные значения всех волн при всех уровнях дают доказанный диапазон микса <b>−33…+30</b>. Нормализация использует gain = 128 / 33 и таблицу 64 выходных значений. Это покрывает любые выравнивания фаз при последующих повторах, а не только один измеренный проход.')
    table(['Вариант','Как задаётся усиление','PWM'],[['Mariachi sparse','Два сдвига влево дают ×4','0…252'],['Greensleeves','Линейная Flash-таблица из 64 значений','Допустимо 0…244; первый проход 0…237'],['Другие обновлённые версии','Сохраняют фиксированные уровни микшера','Запас указан в отчёте каждой версии']], [120,219,W-339])
    p('Нормализация экспортируемого WAV — отдельный шаг после фильтра. Она не меняет HEX и не делает физический PWM автоматически громче. Ползунок браузера тоже регулирует только прослушивание. [6, 11]')

    h('PWM, очередь и реальные временные масштабы')
    p('Синтез рассчитывает <b>18 750 новых отсчётов в секунду</b>. Для каждой новой точки подготавливаются её среднее с предыдущей точкой и сама новая точка. Так в регистр PWM поступают 37 500 значений в секунду.')
    p('midpoint = floor((previous + current) / 2)','GuideCode')
    fig(fifo_figure(),'Схема 16. Небольшая очередь развязывает расчёт голосов и регулярную выдачу PWM. Интерполяция находится здесь, после микшера, а не между точками инструментальной волны.')
    fig(pwm_figure(),'График 17. Усреднение импульсов фильтром даёт меняющееся напряжение для усилителя. Физические граничные импульсы PWM и аппаратная фиксация OCR на рисунке не показаны.')
    p('CPU работает на 9,6 МГц. Между синтезируемыми точками доступно 512 тактов; период PWM — 256 тактов. Моно-ISR обычно занимает 15 тактов и лишь выдаёт заранее подготовленное значение. У стерео Lumière — 18 тактов, пары L/R хранятся согласованно.')
    p('Очередь имеет 16 байт. На управляющем тике декодер иногда делает длинный рывок, но запас подготовленных значений позволяет выдержать его без провала звука. Отсутствие потерь IRQ само по себе недостаточно: отдельно проверяется, что FIFO не опустела. [4, 6, 12]')

    h('Какие форматы нельзя смешивать')
    table(['Движок','Время и ноты','Гармония'],[
        ['Lumière','P:5 + D:3; 4 единицы/четверть','E0…EF → 8 байт на расположение'],
        ['Турецкий марш','Тот же основной диалект','E0…EF → 4 байта; 0-слово также гасит голос'],
        ['Алисия','P:5 + D:3; 12 единиц/четверть','C0…F7 → 2-байтовый дескриптор; отдельные темпы и тембр'],
        ['Children','Ноты 0…150; 4 единицы/четверть','151…253 — макрос; FE — отпускание; FF — фраза'],
        ['Greensleeves','Отдельные On/Off; wait 1…64 шестнадцатых','Четыре независимые одноголосные партии'],
        ['Mariachi full','База shape/gap/gate; 1/3 четверти','Готовые DDS; по 2 + 6 струн'],
        ['Mariachi sparse','База shape/gap/gate; 1/6 четверти','Адреса DDS в EEPROM; по 3 + 3 струны']], [104,188,W-292])
    p('Старая ансамблевая Mariachi с басом использует обычные фразы и пары сопровождения, а не двухгитарный shape-кодек. В «Алисии» F8/F9/FA задают 78/58/87 BPM, FB/FC меняют пианный и смычковый солирующий тембр. Значение байта всегда нужно читать вместе с типом движка.')
    fig(memory_figure(),'Схема 18. SRAM занята текущим состоянием. Серые области — запас. Длинная мелодия не обязана требовать большую оперативную память.')
    p('Типичный голос занимает 5 байт: огибающая 1, фаза 2, DDS-шаг 2. У Mariachi осциллятору хватает 4 байт, потому что огибающая общая на гитарную группу. Увеличить число голосов можно только с учётом SRAM, тактов и диапазона микшера.')

    h('Размеры, проверка и исходники')
    fig(flash_figure(images),'График 19. Реальные размеры готовых прошивок в срезе a875a3e. Оранжевая часть включает все таблицы: не только ноты, но и частоты, длительности, словари и при необходимости нормализацию.')
    p('Упаковщики сверяют восстановленные команды или события с подготовленной партитурой. AVR-аудит проверяет исполнение: высоты, атаки и выключения, фазы, микшер, порядок FIFO, такты и границы памяти. Это проверка цифровой модели; аналоговый звук также зависит от генератора тактов, RC-фильтра, усилителя и динамика.')
    refs=[
        ('1','score-format.py','Байты нот, длительности, DDS, Note Off'),
        ('2','build-lumiere-full.py','Полные расположения аккордов, моно и стерео'),
        ('3','pack-score.py','Фразы, playlist, суффиксы и проверка потока'),
        ('4','build-mariachi-lossless.py','Shapes, базы, два потока и синтез'),
        ('5','pack-musical-events.py','Группировка нот, грамматика, отдельный MNC1'),
        ('6','build-compact-four.py','Greensleeves, On/Off, голоса и нормализация'),
        ('7','arrange-alicia-multi.py','Нативная сетка, дескрипторы и арпеджио'),
        ('8','arrange-children-four.py','Макросы эха, баса и поздних струнных'),
        ('9','instrument-bank.py','Банк волн, упаковка половинок байта, EEPROM'),
        ('10','mariachi-percussion.py','Компактные ударные sparse Mariachi'),
        ('11','render-firmware-preview.mjs','WAV и нормализация после фильтра')]
    for number,file,topic in refs:
        url=f'https://github.com/Witali/MicroMusic/blob/{REF}/tools/{file}'
        p(f'[{number}] <link href="{url}" color="#2459A6">{escape(file)}</link> — {escape(topic)}','GuideSmall')
    p('[12] Синхронная очередь и PWM: код synth.S, build-report.json и verification-отчёты рядом с каждым вариантом в ATtiny13A/Music/variants и web-player/reports. Числа и примеры автоматически сверены при сборке этого документа.','GuideSmall')
    p('Пересоздание: python tools/build-music-format-guide.py<br/>Нужен пакет reportlab. Скрипт читает зафиксированный срез Git, сохраняет PDF и JSON с примерами и SHA-256 источников. PDF хранится в Git LFS.','GuideSmall')

    def on_page(canvas,doc):
        canvas.saveState();canvas.setFillColor(GRAY);canvas.setFont('Body',8)
        canvas.drawString(44,A4[1]-24,'MicroMusic   Музыкальные прошивки ATtiny13A')
        canvas.drawRightString(A4[0]-44,24,str(doc.page));canvas.restoreState()
    output.parent.mkdir(parents=True,exist_ok=True)
    doc=Guide(str(output),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=47,bottomMargin=42,
              title='Ноты, аккорды и тембры в ATtiny13A',author='MicroMusic',subject=f'Хранение и декодирование музыки в срезе {REF}',
              invariant=1,allowSplitting=1)
    doc.addPageTemplates(PageTemplate(id='guide',frames=[Frame(44,42,W,A4[1]-89,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=on_page))
    doc.build(story)
    facts['documentPages']=page
    output.with_name(output.stem+'-facts.json').write_text(json.dumps(facts,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(pdf=str(output),plannedPages=page,bytes=output.stat().st_size,examplesVerified=True),ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=ROOT/'ATtiny13A/Music/docs/music-storage-and-playback-ru.pdf')
    ap.add_argument('--font-dir',type=Path,default=Path('C:/Windows/Fonts') if Path('C:/Windows/Fonts').exists() else Path('/usr/share/fonts/truetype/dejavu'))
    args=ap.parse_args();build(args.output,args.font_dir)
