#!/usr/bin/env python3
"""Embed HQ4 HEX, decoded original/HQ3/LPX3 and verified AVR PCM in offline UI."""
import re,json,base64,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent
s=(R/'MicroMusic_HQ3_Verified_Release/index.html').read_text()
match=re.search(r'const DATA=(\{.*?\});\s*const rate=7500;',s,re.S)
assert match
D=json.loads(match.group(1))
M={v['phrase']:v for v in json.loads((R/'HQ4/results.json').read_text())}
for name in ['chego','otvechaesh','vinni']:
 item=D[name];meta=M[name];p=R/'HQ4'/name
 item['pcm']['hq3']=item['pcm']['hq'].copy()
 item['metrics']['hq3']=item['metrics']['hq']
 pcm=(p/'verified_pcm.raw').read_bytes()
 item['pcm']['hq']={'fmt':'u8','bytes':base64.b64encode(pcm).decode('ascii')}
 item['metrics']['hq']=meta['stoi']
 item['hex']=(p/'firmware.hex').read_text()
 item['asm']=(p/'firmware.S').read_text()
 item['info'].update(code_bytes=meta['code_bytes'],speech_bytes=meta['speech_bytes'],flash_bytes=meta['flash_bytes'])
s=s[:match.start(1)]+json.dumps(D,ensure_ascii=False,separators=(',',':'))+s[match.end(1):]
s=s.replace('MiniLPC-HQ3','MiniLPC-HQ4')
s=s.replace('<option value="hq">MiniLPC-HQ4 · ATtiny13A</option>', '<option value="hq">MiniLPC-HQ4 · ATtiny13A</option><option value="hq3">MiniLPC-HQ3 · предыдущий</option>')
s=s.replace('Короткие кадры 8,5 мс','Короткие кадры 8,5 мс')
s=s.replace('Эксперимент с кодированием периода и длительности кадра в одном байте (SILK-подобный приём) и совместным поиском LPC, периода, громкости и возбуждения по методу CELP/Speex. Кадры 8,5 / 17 / 34 мс.', 'Оптимизация MiniLPC по оригинальным записям с контролем STOI, спектра и щелчков. Код AVR не увеличен; изменены только речевые данные.')
s=s.replace("mode==='original'?'1,000':DATA[name].metrics[mode].toFixed(3)","mode==='original'?'1,000':DATA[name].metrics[mode].toFixed(3)")
out=R/'MiniLPC_HQ4_Player.html';out.write_text(s)
print('Saved',out,'bytes',out.stat().st_size)
# Validate all datasets, hex lengths and new AVR bytes
for name in D:
 assert 'hq3' in D[name]['pcm']
 assert len(base64.b64decode(D[name]['pcm']['hq']['bytes']))==D[name]['info']['samples']
 assert D[name]['info']['flash_bytes']<=1024
print('All speech options and HEX embedded')
