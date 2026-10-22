#!/usr/bin/env python3
"""Pack original audio, exact real AVR v3 + v4 HEX and LPC baselines in offline A/B player."""
from pathlib import Path
from base64 import b64encode
P=Path(__file__).resolve().parent
src=(P/'page_template.html').read_text(encoding='utf8')
original=P
# Header description and data
src=src.replace('TinyLPC v3', 'TinyLPC v4')
src=src.replace('v3 ·', 'v4 ·')
src=src.replace('v3.', 'v4.')
src=src.replace('v3:', 'v4:')
src=src.replace('первый вариант исполняет', 'первый вариант исполняет')
src=src.replace('7 коэффициентов отражения по 4 бита, период', '7 коэффициентов отражения по 4 бита, период')
src=src.replace('Улучшения относительно v2:', 'Улучшения относительно v3:')
src=src.replace('впервые используем настоящий голос из мультфильма; коэффициенты подстроены по оригиналу и ослаблены для предотвращения переполнений в 8-битных регистрах; в немых кадрах очищается память резонансного фильтра.', 'спектральная огибающая подбирается по оригинальному голосу, а не только стандартным LPC-анализом; при поиске основного тона распознаются ложные гармоники (в том числе скачки в 2–3 раза). Качество оценивается STOI, спектральным расстоянием и сравнением высоты голоса.')
src=src.replace('Семь коэффициентов LPC, усиленное затухание фильтра, четыре фазы голосового импульса. Звук вычисляется из', 'Семь коэффициентов LPC с покадровой оптимизацией по исходному звуку, точно подобранным периодом и энергией. Звук вычисляется из')
src=src.replace('<article class="track" id="card-lpc2">', '<article class="track" id="card-v3"><div class="track-title"><b>TinyLPC v3 · предыдущий</b><span class="tag alt">1 КБ AVR</span></div><div class="note">Результат предыдущей версии из исходного диалога, также исполняемый инструкциями AVR. Для сравнения тембра и интонации с новой версией.</div><button data-play="v3">▶ Слушать v3</button></article>\n<article class="track" id="card-lpc2">')
src=src.replace("const HEX_FIRMWARE=`__HEX_FIRMWARE__`;", "const HEX_FIRMWARE=`__HEX_FIRMWARE__`;\nconst HEX_V3=`__HEX_V3__`;")
src=src.replace("const modeLabels={firmware:'TinyLPC v4 · реальная AVR',", "const modeLabels={firmware:'TinyLPC v4 · AVR',v3:'TinyLPC v3 · AVR',")
src=src.replace("if(mode==='firmware'){\n  const cpu=AVRCore.fromHex(HEX_FIRMWARE);", "if(mode==='firmware'||mode==='v3'){\n  const cpu=AVRCore.fromHex(mode==='v3'? HEX_V3 : HEX_FIRMWARE);")
src=src.replace("mode==='firmware'?3350:4200", "(mode==='firmware'||mode==='v3')?3350:4200")
src=src.replace('о соответствии речи версии v3', 'о соответствии речи версии v4')
src=src.replace('между v2', 'между v3')
# Add display of measured, reproducible gains above original notes
src=src.replace('<section class="panel"><h2>Что поместилось в ATtiny13A</h2>', '<section class="panel"><h2>Результаты A/B-сравнения</h2><p>В таблице показатели получены из реально выполненных AVR-прошивок и одного и того же эталонного WAV. STOI оценивает разборчивость, а спектральная ошибка измеряет сходство огибающей; ни одна величина сама по себе не гарантирует совпадения голосового тембра.</p><div id="quality" class="quality">__METRICS_HTML__</div></section>\n<section class="panel"><h2>Что поместилось в ATtiny13A</h2>')
src=src.replace('loading="lazy"','loading="eager"')
src=src.replace('</style>', '.quality table{border-collapse:collapse;width:100%;font-size:13px}.quality th,.quality td{padding:9px;text-align:left;border-bottom:1px solid #34506c}.quality td:first-child{font-weight:700}.quality .v4{color:#93edcf} </style>')
import json
metrics=json.loads((P/'metrics.json').read_text())
q=f'''<table><thead><tr><th>Метрика</th><th>v3</th><th class="v4">v4</th></tr></thead><tbody>
<tr><td>STOI (выше лучше)</td><td>{metrics['v3']['stoi']:.3f}</td><td class="v4">{metrics['v4']['stoi']:.3f}</td></tr>
<tr><td>Ошибка спектральной огибающей (ниже лучше)</td><td>{metrics['v3']['mel']:.3f}</td><td class="v4">{metrics['v4']['mel']:.3f}</td></tr>
<tr><td>Ошибка F₀ на уверенно звонких участках (октав)</td><td>{metrics['v3']['pitch_error']:.2f}</td><td class="v4">{metrics['v4']['pitch_error']:.2f}</td></tr>
<tr><td>Flash, включая речевые данные</td><td>{metrics['v3']['flash']} Б</td><td class="v4">{metrics['v4']['flash']} Б</td></tr>
</tbody></table>'''
src=src.replace('__METRICS_HTML__',q)
for token,path in {'AVR_CORE':P/'avr_emulator.js','LPC_MATH':P/'lpc_math.js','HEX_FIRMWARE':P/'tinylpc.hex','HEX_V3':original/'tinylpc_v3.hex'}.items():
 src=src.replace('__'+token+'__',path.read_text())
for token,path in {'BASE64_FRAMES':'voice_tinylpc.bin','BASE64_LPC1':'phrase_lpc1.lpc','BASE64_LPC2':'phrase_lpc2.lp2','BASE64_REFERENCE':'speech_trimmed_7500.wav','BASE64_FULL':'source_original.mp3','SPECTRO_B64':'spectrogram_compare_v4.webp'}.items():
 src=src.replace('__'+token+'__',b64encode((P/path).read_bytes()).decode('ascii'))
assert '__' not in src.split('<script>')[-1], 'Unreplaced template variables'
(P/'index.html').write_text(src,encoding='utf8')
print('Created index.html',len(src.encode('utf-8')),'bytes')
