from pathlib import Path
import base64,json, soundfile as sf, numpy as np
P=Path(__file__).parent
engine=(P/'pitch_glide/avr_emulator.js').read_text()
orig,sr=sf.read(P/'original_reference.wav',dtype='int16');assert sr==7500
lpc2=(P/'lpc2_improved_reference.s16le').read_bytes()
hexs={k:(P/v).read_text().strip() for k,v in [('v5','v5_reference.hex'),('glide','pitch_glide/tinylpc.hex'),('mixed','mixed_excitation/tinylpc.hex')]}
metrics=json.loads((P/'verified_metrics.json').read_text())
meta={
 'original':dict(label='Оригинальная запись',desc='Исходная фраза из мультфильма, эталон для сравнения',tag='Референс',sr=7500),
 'lpc2':dict(label='LPC2 Improved',desc='Прежний 10-полюсный LSF-вокодер с интерполяцией и постфильтром; декодирован ранее в браузере',tag='Больший декодер',sr=8000),
 'v5':dict(label='TinyLPC v5',desc='Предыдущая проверенная прошивка: 7-ступенчатый LPC и короткий импульс',tag='AVR · 1012 Б',sr=7500),
 'glide':dict(label='TinyLPC2-Lite · F₀',desc='Небольшие изменения высоты тона интерполируются, тишина кодируется сериями',tag='AVR · 1012 Б',sr=7500),
 'mixed':dict(label='TinyLPC2-Lite · mixed',desc='Смешанное возбуждение выбрано по режимам из настоящего потока LPC2',tag='AVR · 1020 Б',sr=7500),
}
styles='''
:root{color-scheme:dark;font:15px/1.5 system-ui,-apple-system,Segoe UI,Arial,sans-serif;background:#071321;color:#eaf4ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% -9%,#15435b,transparent 55%),#071321;min-height:100vh}
main{max-width:1030px;margin:auto;padding:32px 18px 64px}.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.mark{letter-spacing:.15em;color:#86eed0;font-size:13px;font-weight:900}h1{font-size:clamp(27px,5vw,43px);line-height:1.14;letter-spacing:-.025em;margin:22px 0 7px}h2{font-size:20px;margin:0 0 13px}
p{color:#b4c8dc;margin:8px 0 16px}.small{font-size:12px}.pill{border:1px solid #39566d;border-radius:20px;padding:4px 9px;color:#b8c8d6;font-size:12px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.track,.panel{border:1px solid #34516b;border-radius:14px;background:#10263a;padding:18px}
.track{display:flex;gap:8px;flex-direction:column;min-height:166px}.track.selected{outline:2px solid #6cebbf}.track-top{display:flex;align-items:start;justify-content:space-between;gap:8px}.track b{font-size:17px}.track p{font-size:13px;margin:0;flex:1}.tag{color:#b3ead5;background:#204a43;padding:4px 7px;border-radius:6px;font-size:11px;white-space:nowrap}
.actions{display:flex;flex-wrap:wrap;gap:7px;margin-top:auto}button{appearance:none;background:#86eac5;border:0;border-radius:9px;color:#082334;font:700 13px system-ui;padding:10px 13px;cursor:pointer}button:hover{filter:brightness(1.09)}button.alt{background:#294b68;color:#e4f3ff;border:1px solid #446481}button:disabled{opacity:.6;cursor:wait}
.panel{margin-top:15px}.statgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:17px 0}.stat{padding:13px;border:1px solid #2d4963;background:#112338;border-radius:10px}.stat strong{display:block;font-size:23px}.stat span{color:#a7bfda;font-size:12px}
canvas{width:100%;height:160px;border-radius:10px;background:#091729;border:1px solid #34516b}.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
#status{font-size:13px;color:#9bdfc9;min-height:28px}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #314e66;padding:9px;text-align:left;font-size:13px}th{color:#c7e6fd}td:first-child{font-weight:600}
footer{font-size:12px;color:#93adbf;margin-top:23px;border-top:1px solid #2d4560;padding-top:17px}
@media(max-width:700px){.grid{grid-template-columns:1fr}.statgrid{grid-template-columns:repeat(2,1fr)}.track{min-height:140px}main{padding:18px 13px}}
'''
cards=[]
for id,item in meta.items():
 cards.append(f'''<section class="track" data-card="{id}"><div class="track-top"><b>{item['label']}</b><span class="tag">{item['tag']}</span></div><p>{item['desc']}</p><div class="actions"><button data-play="{id}">▶ Слушать</button><button class="alt" data-compare="{id}" {'disabled' if id=='original' else ''}>A/B с оригиналом</button></div></section>''')
rows=[]
for id in ('v5','glide','mixed'):
 m=metrics['v5' if id=='v5' else 'pitch_glide' if id=='glide' else 'mixed_excitation']
 rows.append(f'''<tr><td>{meta[id]['label']}</td><td>{m['bytes_flash']} Б</td><td>{m['bytes_voice']} Б</td><td>{m['stoi']:.3f}</td><td>{m['spectral_error']:.3f}</td></tr>''')
html=f'''<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MicroMusic — LPC2 Improved → ATtiny13A</title><style>{styles}</style></head>
<body><main><div class="top"><span class="mark">♫ MICROMUSIC / TINY SPEECH LAB</span><span class="pill">ATtiny13A · 9,6 МГц · PWM</span></div>
<h1>LPC2 Improved → ATtiny13A</h1>
<p>Эксперимент с оригинальной фразой «Сова! Открывай! Медведь пришёл!». Ниже можно сравнить полный LPC2 Improved с двумя упрощёнными версиями для микроконтроллера. <strong>В режимах AVR браузер исполняет реальные машинные инструкции из HEX</strong>, а не заранее записанный WAV.</p>
<div class="statgrid"><div class="stat"><strong>1024 Б</strong><span>вся Flash-память ATtiny13A</span></div><div class="stat"><strong>343 Б</strong><span>новые речевые данные</span></div><div class="stat"><strong>7,5 кГц</strong><span>звук из AVR</span></div><div class="stat"><strong>2,97 с</strong><span>длительность фразы</span></div></div>
<div class="grid">{''.join(cards)}</div>
<section class="panel"><div class="top"><h2>Осциллограмма и управление</h2><button id="stop" class="alt">■ Остановить</button></div><canvas id="scope" width="950" height="160"></canvas><div class="controls"><span>Громкость</span><input id="volume" type="range" min="0" max="1" step="0.01" value="0.7"><button class="alt" id="download" disabled>↓ Скачать выбранный WAV</button></div><p id="status">Выберите вариант для прослушивания.</p><div id="runtime" class="small" style="color:#98b5ce"></div></section>
<section class="panel"><h2>Проверенные результаты</h2><table><thead><tr><th>Вариант</th><th>Flash</th><th>Речь</th><th>STOI ↑</th><th>Спектральная ошибка ↓</th></tr></thead><tbody>{''.join(rows)}</tbody></table><p class="small">STOI оценивает разборчивость, а не сходство тембра на слух. Речевые данные включены в Flash. LPC2 Improved представлен только как компьютерный эталон и не исполняется на ATtiny13A.</p></section>
<footer>Для частного эксперимента. Исходный звук и производные от него не следует публиковать в открытом репозитории без разрешения правообладателей. Это проверка в эмуляторе AVR, а не измерение на физическом ATtiny13A.</footer></main>
<script>{engine}
const HEXES={json.dumps(hexs,ensure_ascii=False)};
const ORIGINAL_BASE64='{base64.b64encode(orig.astype('<i2').tobytes()).decode()}';
const LPC2_BASE64='{base64.b64encode(lpc2).decode()}';
const META={json.dumps(meta,ensure_ascii=False)};
const LENGTH=87*256;
const cache=new Map();let audio=null;let activeSources=[];let last=null;let lastMode='';let vol=0.7;let stopped=false;
const $=id=>document.getElementById(id);
const note=s=>$('status').textContent=s;
const yieldUI=()=>new Promise(resolve=>setTimeout(resolve,0));
function fromBase64(v){{const s=atob(v),a=new Int16Array(s.length/2);for(let i=0;i<a.length;i++){{let n=s.charCodeAt(2*i)|(s.charCodeAt(2*i+1)<<8);a[i]=n>=32768?n-65536:n}}return Float32Array.from(a,x=>x/32768)}}
function scaled(a){{let acc=0,peak=0;for(const x of a){{acc+=x*x;peak=Math.max(peak,Math.abs(x))}}const rms=Math.sqrt(acc/a.length),gain=Math.min(.12/Math.max(1e-8,rms),.95/Math.max(1e-8,peak));return Float32Array.from(a,x=>x*gain)}}
async function decodeTrack(mode){{
 if(cache.has(mode))return cache.get(mode);
 let samples,sr,stats=null;
 if(mode==='original'){{samples=fromBase64(ORIGINAL_BASE64);sr=7500}}
 else if(mode==='lpc2'){{samples=fromBase64(LPC2_BASE64);sr=8000}}
 else {{const core=AVRCore.fromHex(HEXES[mode]);samples=new Float32Array(LENGTH);sr=7500;note('Эмулирую ATtiny13A: '+META[mode].label+'…');await yieldUI();
   for(let i=0;i<samples.length;i++){{samples[i]=(core.takeSample()-128)/128;if((i&2047)===2047)await yieldUI()}}
   stats={{irq:core.irqCount,missed:core.missedOverflows,maxISR:core.maxISR,stack:core.maxStack}};
 }}
 const result={{samples:scaled(samples),sr,stats}};cache.set(mode,result);return result;
}}
function plot(a){{const c=$('scope'),ctx=c.getContext('2d');ctx.fillStyle='#091729';ctx.fillRect(0,0,c.width,c.height);ctx.strokeStyle='#24394f';ctx.beginPath();ctx.moveTo(0,c.height/2);ctx.lineTo(c.width,c.height/2);ctx.stroke();if(!a)return;ctx.strokeStyle='#7deaca';ctx.lineWidth=1.7;ctx.beginPath();const step=a.length/c.width;for(let i=0;i<c.width;i++){{let y=a[Math.min(a.length-1,Math.floor(i*step))];const h=c.height/2-y*(c.height*.44);i?ctx.lineTo(i,h):ctx.moveTo(i,h)}}ctx.stroke()}}
function stop(){{for(const n of activeSources){{try{{n.stop()}}catch(e){{}}try{{n.disconnect()}}catch(e){{}}}}activeSources=[];stopped=true}}
function webBuffer(v){{const buf=audio.createBuffer(1,v.samples.length,v.sr);buf.copyToChannel(v.samples,0);return buf}}
function playAt(v,at){{const src=audio.createBufferSource();src.buffer=webBuffer(v);const gn=audio.createGain();gn.gain.value=vol;src.connect(gn).connect(audio.destination);src.start(at);activeSources.push(src)}}
async function play(mode,ab=false){{
 stop();stopped=false;try{{
  audio ||= new (window.AudioContext||window.webkitAudioContext)();await audio.resume();
  let v=await decodeTrack(mode);if(stopped)return;
  const a=ab?await decodeTrack('original'):null;if(stopped)return;
  const at=audio.currentTime+.05;if(a)playAt(a,at);
  playAt(v,at+(a?a.samples.length/a.sr+.3:0));
  last=v;lastMode=mode;plot(v.samples);
  $('download').disabled=false;
  document.querySelectorAll('[data-card]').forEach(el=>el.classList.toggle('selected',el.getAttribute('data-card')===mode));
  const st=v.stats;if(st)$('runtime').textContent=`AVR: ${{st.irq.toLocaleString('ru')}} прерываний Timer0, пропусков ${{st.missed}}, максимум ISR ${{st.maxISR}} тактов, стек ${{st.stack}} байт`;
  else $('runtime').textContent='Эталонный аудиосигнал, без эмуляции AVR.';
  note((ab?'A/B: оригинал → ':'Воспроизводится: ')+META[mode].label);
 }}catch(e){{note('Ошибка воспроизведения: '+e.message);console.error(e)}}
}}
$('stop').onclick=()=>{{stop();note('Воспроизведение остановлено.')}};
$('volume').oninput=e=>{{vol=+e.target.value}};
for(const b of document.querySelectorAll('[data-play]'))b.onclick=()=>play(b.dataset.play);
for(const b of document.querySelectorAll('[data-compare]'))b.onclick=()=>play(b.dataset.compare,true);
function createWav(v){{const a=v.samples,d=new ArrayBuffer(44+a.length*2),w=new DataView(d),wr=(offset,str)=>{{for(let i=0;i<str.length;i++)w.setUint8(offset+i,str.charCodeAt(i))}};wr(0,'RIFF');w.setUint32(4,36+a.length*2,true);wr(8,'WAVE');wr(12,'fmt ');w.setUint32(16,16,true);w.setUint16(20,1,true);w.setUint16(22,1,true);w.setUint32(24,v.sr,true);w.setUint32(28,v.sr*2,true);w.setUint16(32,2,true);w.setUint16(34,16,true);wr(36,'data');w.setUint32(40,a.length*2,true);for(let i=0;i<a.length;i++)w.setInt16(44+2*i,Math.round(Math.max(-1,Math.min(1,a[i]))*32767),true);return new Blob([d],{{type:'audio/wav'}})}}
$('download').onclick=()=>{{if(!last)return;const url=URL.createObjectURL(createWav(last));const a=document.createElement('a');a.href=url;a.download=lastMode+'_comparison.wav';a.click();setTimeout(()=>URL.revokeObjectURL(url),5000)}};
plot(null);
</script></body></html>'''
(P/'MicroMusic_LPC2_Lite_Emulator.html').write_text(html)
print('HTML',len(html.encode('utf8')),'bytes')
