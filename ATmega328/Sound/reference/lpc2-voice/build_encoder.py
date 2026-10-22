"""Build backwards-compatible experimental LPC2 Voice v2 codec UI from v11 codec."""
from pathlib import Path
P=Path(__file__).resolve().parent
src=P/'lpc2_v11_original.html' if (P/'lpc2_v11_original.html').exists() else P.parent/'MicroMusic_MultiPhrase/lpc2_improved_encoder.html'
s=src.read_text(encoding='utf-8')
def patch(old,new,minimum=1):
 global s
 n=s.count(old)
 assert n>=minimum, f'patch not found: {old[:130]!r} count {n}'
 s=s.replace(old,new)
 return n
patch('const LPC2_LSF_BITS10=[5,5,4,4,4,4,4,3,3,3],LPC2_LSF_BITS4=[5,5,4,4],LPC2_PITCH_MIN=55,LPC2_PITCH_MAX=420;',
      'const LPC2_LSF_BITS10=[5,5,4,4,4,4,4,3,3,3],LPC2_LSF_BITS4=[5,5,4,4];let LPC2_PITCH_MIN=65,LPC2_PITCH_MAX=850;')
patch('function qLpc2Pitch(q,sr){const f=LPC2_PITCH_MIN*(LPC2_PITCH_MAX/LPC2_PITCH_MIN)**(q/63);return sr/f}',
      'function qLpc2Pitch(q,sr,minHz=LPC2_PITCH_MIN,maxHz=LPC2_PITCH_MAX){const f=minHz*(maxHz/minHz)**(q/63);return sr/f}')
patch('  const path=trackPitchViterbi(rec,c.voicing,c.pitchSmooth),frames=[];let previous=null',
      '  const path=trackPitchViterbi(rec,c.voicing,c.pitchSmooth);\n'
      '  // Optional external pYIN track: analysis-by-synthesis may use original F0 without altering the decoder.\n'
      '  if(Array.isArray(c.pitchGuideHz))for(let j=0;j<path.length;j++){\n'
      '    const hz=Number(c.pitchGuideHz[j]);\n'
      '    if(Number.isFinite(hz)&&hz>=LPC2_PITCH_MIN&&hz<=LPC2_PITCH_MAX)\n'
      '      path[j]={period:sr/hz,corr:.99};\n'
      '  }\n'
      '  const frames=[];let previous=null')
patch('return{meta:{codec:"lpc2",ver:1,sr,H,W,order:10,samples:x.length,frameCount:F,pre:c.pre,voicing:c.voicing}',
      'return{meta:{codec:"lpc2",ver:2,pitchMin:LPC2_PITCH_MIN,pitchMax:LPC2_PITCH_MAX,sr,H,W,order:10,samples:x.length,frameCount:F,pre:c.pre,voicing:c.voicing}')
patch('v.setUint8(4,1);v.setUint8(5,m.order);v.setUint16(6,m.sr,true);v.setUint16(8,m.H,true);',
      'v.setUint8(4,2);v.setUint8(5,m.order);v.setUint16(6,m.sr,true);v.setUint16(8,m.H,true);')
patch('v.setUint32(32,0,true);new Uint8Array(b,36).set(payload);',
      'v.setUint16(32,Math.round(m.pitchMin||LPC2_PITCH_MIN),true);v.setUint16(34,Math.round(m.pitchMax||LPC2_PITCH_MAX),true);new Uint8Array(b,36).set(payload);')
patch('stats:{version:1,codec:"lpc2",frames:F.length', 'stats:{version:2,codec:"lpc2",frames:F.length')
patch('v.getUint8(4)!==1)throw Error("Это не поддерживаемый поток LPC2")',
      '![1,2].includes(v.getUint8(4)))throw Error("Это не поддерживаемый поток LPC2")')
patch('const m={codec:"lpc2",ver:1,order:v.getUint8(5),sr:v.getUint16(6,true)',
      'const m={codec:"lpc2",ver:v.getUint8(4),pitchMin:v.getUint8(4)===2?v.getUint16(32,true):55,pitchMax:v.getUint8(4)===2?v.getUint16(34,true):420,order:v.getUint8(5),sr:v.getUint16(6,true)')
patch('if(m.order!==10||36+Math.ceil(m.payloadBits/8)>b.byteLength)throw Error("Повреждён или не поддерживается LPC2");',
      'if(m.order!==10||m.pitchMin<20||m.pitchMax>2500||m.pitchMax<=m.pitchMin||36+Math.ceil(m.payloadBits/8)>b.byteLength)throw Error("Повреждён или не поддерживается LPC2");')
patch('pitchSum+=m.sr/qLpc2Pitch(pitch,m.sr)', 'pitchSum+=m.sr/qLpc2Pitch(pitch,m.sr,m.pitchMin,m.pitchMax)')
patch('stats:{version:1,codec:"lpc2",frames:m.frameCount', 'stats:{version:m.ver,codec:"lpc2",frames:m.frameCount')
patch('qLpc2Pitch(first.pitch,m.sr):m.sr/120','qLpc2Pitch(first.pitch,m.sr,m.pitchMin,m.pitchMax):m.sr/120')
patch('isPitch?qLpc2Pitch(cur.pitch,m.sr):prevPitch','isPitch?qLpc2Pitch(cur.pitch,m.sr,m.pitchMin,m.pitchMax):prevPitch')
# Broaden range in UI selection at time of encoding, automatically included in v2 stream.
insert='''<label class="lpc2Only codecHidden">Диапазон голоса (F₀)<select id="lpc2VoiceRange"><option value="65-850" selected>Универсальный: 65–850 Гц</option><option value="65-500">Низкий голос: 65–500 Гц</option><option value="180-850">Высокий голос: 180–850 Гц</option><option value="220-800">Очень высокий: 220–800 Гц</option></select><span class="codecNote">В версии LPC2 Voice v2 диапазон записывается в заголовок файла; v1 читается как 55–420 Гц.</span></label>'''
patch('<label class="lpc2Only codecHidden">Формантный постфильтр',insert+'<label class="lpc2Only codecHidden">Формантный постфильтр')
patch('const c={frameMs:+U.frameMs.value,windowMs:+U.lpc2WindowMs.value,',
      'const pr=$("lpc2VoiceRange").value.split("-").map(Number);LPC2_PITCH_MIN=pr[0];LPC2_PITCH_MAX=pr[1];const c={frameMs:+U.frameMs.value,windowMs:+U.lpc2WindowMs.value,')
patch('<title>Audio Codec Lab v11 — LPC2 Improved</title>','<title>MicroMusic LPC2 Voice v2 — сохранение высоты и тембра голоса</title>')
patch('<h1>Audio Codec Lab v11: LPC2 Improved</h1>','<h1>MicroMusic LPC2 Voice v2 — высокий голос без среза F₀</h1>')
needle='<p>Страница сравнивает три независимых кодека:'
patch(needle,'<p><b>Исправлено:</b> диапазон основной частоты теперь до 850 Гц, задаётся для каждой записи и хранится в LPC2 v2. Старые LPC2 v1 декодируются в исходном диапазоне 55–420 Гц. Это исправляет искусственное понижение высокого голоса, но не восстанавливает потерянные свойства голосового импульса.</p><p>Страница сравнивает три независимых кодека:')
(P/'LPC2_Voice_v2.html').write_text(s,encoding='utf-8')
print('Generated',P/'LPC2_Voice_v2.html',len(s.encode()))
