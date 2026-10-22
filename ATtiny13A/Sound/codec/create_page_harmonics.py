#!/usr/bin/env python3
"""Create offline AVR-instruction-emulated and host-harmonic-comparison HTML."""
from pathlib import Path
import re, base64, json
P=Path(__file__).resolve().parent
old=P.parent/'MicroMusic-ATtiny13-LPC-v4'
s=(old/'index.html').read_text('utf-8')
s=s.replace('TinyLPC v4 · оригинальная речь на ATtiny13A', 'TinyLPC v5 · гармоники и мягкое возбуждение на ATtiny13A')
s=s.replace('TinyLPC v4 · ATtiny13A</b>', 'TinyLPC v5 · ATtiny13A</b>',1)
s=s.replace('ATtiny13A · TinyLPC v3', 'ATtiny13A · TinyLPC v5')
s=s.replace('TinyLPC v4 ·', 'TinyLPC v5 ·',1) # initial context only first occurrence in display text maybe
s=s.replace('Семь коэффициентов LPC с покадровой оптимизацией по исходному звуку, точно подобранным периодом и энергией.', 'Новый четырёхотсчётный паттерн [2, 3, 2, −1], уменьшенные скачки сигнала; семь коэффициентов LPC по-прежнему подбираются по оригиналу.',1)
s=s.replace('Теперь кодируем <strong>настоящую присланную запись</strong> вместо eSpeak. Ниже можно переключаться между оригинальным голосом и разными способами его сжатия. Первый вариант исполняет <strong>реальные инструкции AVR-прошивки</strong> в браузере, с учётом тактов процессора и переполнений Timer0.', 'Сравнение оригинального голоса, реальных AVR-прошивок v4 и v5 и экспериментов с 4, 8, 12 дополнительными гармониками. <strong>Режимы AVR действительно исполняют инструкции HEX</strong>; многочастотные профили воспроизводятся из результатов компьютерной модели и <strong>пока не помещены в ATtiny13A</strong>.')
new_cards='''
<article class="track" id="card-v4"><div class="track-title"><b>TinyLPC v4 · прежняя AVR</b><span class="tag">1 КБ AVR</span></div><div class="note">Старые параметры и импульс [5, 3, 0, −2]. Исполняется старый HEX. Сравнивайте щелчки и разборчивость.</div><button data-play="v4">▶ Слушать v4</button></article>
<article class="track" id="card-h4"><div class="track-title"><b>4 гармоники</b><span class="tag alt">Модель</span></div><div class="note">Оригинальный источник возбуждения смешан с четырьмя синусоидальными обертонами. Не AVR-прошивка.</div><button data-play="h4">▶ 4 гармоники</button></article>
<article class="track" id="card-h8"><div class="track-title"><b>8 гармоник</b><span class="tag alt">Модель</span></div><div class="note">Больше обертонов, спад относительной амплитуды гармоник 1/n. Не AVR-прошивка.</div><button data-play="h8">▶ 8 гармоник</button></article>
<article class="track" id="card-h12"><div class="track-title"><b>12 гармоник</b><span class="tag alt">Модель</span></div><div class="note">Дополнительные обертоны до предела Найквиста, с затуханием 1/n. Не AVR-прошивка.</div><button data-play="h12">▶ 12 гармоник</button></article>
<article class="track" id="card-hprofile"><div class="track-title"><b>4 спектральных профиля</b><span class="tag alt">Модель · 2 бита</span></div><div class="note">Для каждого 34-мс кадра выбирается один из четырёх профилей (обычный импульс, 4/8/12 обертонов). Нужна дополнительная память и логика, на ATtiny13A пока не исполняется.</div><button data-play="hprofile">▶ Профили</button></article>
'''
s=s.replace('<article class="track" id="card-v3">', new_cards+'<article class="track" id="card-v3">',1)
s=s.replace('const modeLabels={firmware:\'TinyLPC v4 · AVR\',',"const modeLabels={firmware:'TinyLPC v5 · AVR',v4:'TinyLPC v4 · AVR',h4:'4 гармоники · модель',h8:'8 гармоник · модель',h12:'12 гармоник · модель',hprofile:'4 гармонических профиля · модель',",1)
# old base firmware -> v5; older v4 inserted under new symbol
v5_hex=(P/'firmware_broadband/tinylpc.hex').read_text().strip()
v4_hex=(old/'tinylpc.hex').read_text().strip()
replaced=re.sub(r'const HEX_FIRMWARE=`[^`]*`;', 'const HEX_FIRMWARE=`'+v5_hex+'`;\nconst HEX_V4=`'+v4_hex+'`;',s,count=1)
assert replaced!=s;s=replaced
new_lpc=base64.b64encode((P/'firmware_broadband/voice_tinylpc.bin').read_bytes()).decode()
s, n=re.subn(r"const BASE64_FRAMES='[^']*';", "const BASE64_FRAMES='"+new_lpc+"';",s,count=1)
assert n==1
more={ 'HARMONIC4':P/'harmonics_4_test.wav', 'HARMONIC8':P/'harmonics_8_test.wav', 'HARMONIC12':P/'harmonics_12_test.wav', 'HARMONICPROFILE':P/'TinyLPC_harmonic_profiles.wav' }
constants='\n'.join("const BASE64_"+key+"='"+base64.b64encode(path.read_bytes()).decode()+"';" for key,path in more.items())+'\n'
s=s.replace('const SAMPLE_COUNT=87*256;', constants+'const SAMPLE_COUNT=87*256;',1)
s=s.replace("if(mode==='firmware'||mode==='v3'){", "if(mode==='firmware'||mode==='v3'||mode==='v4'){",1)
s=s.replace("mode==='v3'? HEX_V3 : HEX_FIRMWARE", "mode==='v3'? HEX_V3 : mode==='v4'? HEX_V4 : HEX_FIRMWARE",1)
s=s.replace(" }else if(mode==='lpc2'){", " }else if(['h4','h8','h12','hprofile'].includes(mode)){\n  const b={h4:BASE64_HARMONIC4,h8:BASE64_HARMONIC8,h12:BASE64_HARMONIC12,hprofile:BASE64_HARMONICPROFILE}[mode];const wav=readWav(rawBuffer(b));data=normalize(wav.data);sr=wav.sr;\n }else if(mode==='lpc2'){",1)
s=s.replace("mode==='firmware'||mode==='v3')?3350", "mode==='firmware'||mode==='v3'||mode==='v4')?3350",1)
s=s.replace("MicroMusic_TinyLPC_v3_ATtiny13.hex", "MicroMusic_TinyLPC_v5_ATtiny13.hex")
s=s.replace("MicroMusic_TinyLPC_v3_speech.bin", "MicroMusic_TinyLPC_v5_speech.bin")
s=s.replace('Результаты A/B-сравнения','Результаты v4 → v5 и гармонических экспериментов',1)
newtable='''<table><thead><tr><th>Метрика</th><th>v4 AVR</th><th class="v4">v5 AVR</th><th>4 профиля (модель)</th></tr></thead><tbody>
<tr><td>STOI (выше лучше)</td><td>0,782</td><td class="v4">0,779</td><td>0,784</td></tr>
<tr><td>Ошибка спектральной огибающей (ниже лучше)</td><td>0,553</td><td class="v4">0,516</td><td>0,533</td></tr>
<tr><td>Макс. изменение соседних PCM-отсчётов</td><td>75</td><td class="v4">54</td><td>56</td></tr>
<tr><td>Скачков PCM на 60 уровней или более</td><td>20</td><td class="v4">0</td><td>0</td></tr>
<tr><td>ATtiny13 Flash</td><td>1012 Б</td><td class="v4">1012 Б</td><td>пока не реализовано</td></tr>
</tbody></table>'''
s,n=re.subn(r'(<div id="quality" class="quality">).*?(</div>)',lambda m:m.group(1)+newtable+m.group(2),s,count=1,flags=re.S);assert n==1
s=s.replace('STOI оценивает разборчивость, а спектральная ошибка измеряет сходство огибающей;', 'STOI оценивает разборчивость, а спектральная ошибка измеряет сходство огибающей; больший размах между соседними отсчётами — лишь косвенный признак щелчков;',1)
s=s.replace('спектральная огибающая подбирается по оригинальному голосу, а не только стандартным LPC-анализом; при поиске основного тона распознаются ложные гармоники (в том числе скачки в 2–3 раза). Качество оценивается STOI, спектральным расстоянием и сравнением высоты голоса.', 'новый четырёхотсчётный импульс [2, 3, 2, −1] вместо [5, 3, 0, −2], повторный анализ по оригинальной записи и проверка DSP вплоть до выполняемых инструкций AVR. Дополнительные спектральные гармоники вынесены в отдельные компьютерные эксперименты.',1)
s=s.replace('1012/1024 Б · прошивка и LPC-поток','1012/1024 Б · v5, прошивка и LPC-поток',1)
s=s.replace('Голос из мультфильма','Голос из мультфильма',1)
# Update main diagram spectrogram replacing v4 image only in body.
img=base64.b64encode((P/'spectrogram_v5.png').read_bytes()).decode()
s,n=re.subn(r'src="data:image/webp;base64,[^"]+"', 'src="data:image/png;base64,'+img+'"',s,count=1)
assert n==1
s=s.replace('Спектрограмма показывает слева направо то же время для эталона, TinyLPC и LPC2.', 'На этой спектрограмме сверху вниз: оригинал, v4 AVR, v5 AVR и модель с переключаемыми гармониками.',1)
s=s.replace('У TinyLPC видны упрощённые гармоники и изменения формант;', 'Сравнение позволяет увидеть изменения гармоник и формант;',1)
s=s.replace('Спектрограммы оригинальной речи, 1-КБ ATtiny13A и LPC2','Спектрограммы оригинальной речи, v4 AVR, v5 AVR и гармонической модели',1)
s=s.replace('данные LPC1/LPC2', 'данные LPC1/LPC2',1)
s=s.replace('В таблице показатели получены из реально выполненных AVR-прошивок и одного и того же эталонного WAV.', 'Для столбцов v4 и v5 показатели получены из исполнения AVR HEX; для четырёх спектральных профилей — из той же арифметической модели фильтра на компьютере.',1)
# Avoid mistaken assertion v5 F0 measured, hard-coded v4 F0 in table not now
s=s.replace('«Сова! Открывай!<br>', '«Сова! Открывай!<br>',1)
(P/'index.html').write_text(s,'utf8')
print('HTML',len(s.encode()),'bytes', 'mode count',s.count('data-play='),'embedded 2 hex', 'const HEX_V4=' in s)
