#!/usr/bin/env python3
"""Generate self-contained, file:// friendly MicroMusic A/B player.
PCM is embedded for immediate playback; AVR HEX binary is embedded for an actual
instruction-by-instruction recheck when the user presses Verify.
"""
from pathlib import Path
import base64,json,numpy as np,soundfile as sf
ROOT=Path(__file__).resolve().parent
REL=ROOT/'release'
NAMES=['chego','otvechaesh','vinni']
TITLE={'chego':'Чего тебе нужно?','otvechaesh':'Что ж ты не отвечаешь?','vinni':'Сова! Открывай! Медведь пришёл!'}
RECS={'hq3':'MiniLPC HQ3 — проверенный','stoi':'HQ4 — приоритет разборчивости','timbre':'HQ4 — приоритет тембра'}
report=json.loads((REL/'report.json').read_text())
met={(r['phrase'],r['codec']):r for r in report}
data={}
for name in NAMES:
    d={}
    for kind in ['original','lpx3','hq3','stoi','timbre']:
        if kind in ['original','lpx3']:
            y,sr=sf.read(REL/name/(kind+'.wav'));assert sr==7500
        else:
            raw=np.frombuffer((REL/name/kind/'pcm.u8').read_bytes(),np.uint8)
            y=(raw.astype(np.float64)-128)/128
        q=np.clip(np.round(np.asarray(y)*32767),-32768,32767).astype('<i2')
        entry={'audio':base64.b64encode(q.tobytes()).decode(),'samples':len(q)}
        if kind not in ['original','lpx3']:
            entry.update(met[name,kind]);entry['firmware']=base64.b64encode((REL/name/kind/'firmware.bin').read_bytes()).decode()
        d[kind]=entry
    data[name]=d

source=(REL/'avr_emulator.js').read_text()
base='''<!doctype html><html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>MicroMusic HQ4 — тембр и разборчивость</title>
<style>
:root{color-scheme:dark;--bg:#0c1422;--panel:#182338;--line:#334762;--text:#eff4fc;--sub:#acc1d8;--accent:#79c2ff}*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.53 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:950px;margin:auto;padding:22px 15px 52px}
h1{font-size:clamp(23px,4.5vw,34px);margin:0 0 7px}.sub{margin:0;color:var(--sub)}.card{background:var(--panel);border:1px solid var(--line);padding:17px;border-radius:15px;margin:15px 0}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}select,button{font:inherit;border-radius:10px}select{display:block;width:100%;border:1px solid #637d9c;background:#111b2e;color:white;padding:12px}
label{display:block;color:var(--sub);font-weight:600;font-size:13px;margin-bottom:5px}button{background:#334965;border:1px solid #627996;color:white;padding:11px 13px;cursor:pointer}button.main{background:#6fc0ff;color:#091c31;border-color:#6fc0ff;font-weight:700}button:hover{filter:brightness(1.09)}button:disabled{opacity:.5;cursor:default}.buttons{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.metric{background:#111b2e;border:1px solid #2d3f59;border-radius:9px;padding:10px;text-align:center}.metric strong{font-size:22px;display:block}.metric small{color:var(--sub);font-size:11px}
canvas{width:100%;height:142px;border-radius:9px;background:#0a111e;margin:12px 0 1px}#status{min-height:24px;color:#b8e6d4;white-space:pre-wrap}.note{font-size:12px;color:var(--sub)}.muted{color:var(--sub)}code{color:#b3d8ff}pre{white-space:pre-wrap;font-size:12px;overflow-wrap:anywhere}
@media(max-width:570px){.grid{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(3,minmax(0,1fr))}.metric strong{font-size:18px}button{flex:1 1 130px}}
</style></head><body><main><h1>MicroMusic · MiniLPC-HQ4</h1><p class="sub">Исследование компромисса: разборчивость или близость тембра. ATtiny13A · Flash 1024 Б · 9,6 МГц · 8-ступенчатый LPC.</p>
<section class="card"><div class="grid"><div><label for="voice">Пример речи</label><select id="voice"><option value="chego">Чего тебе нужно?</option><option value="otvechaesh">Что ж ты не отвечаешь?</option><option value="vinni">Сова! Открывай! Медведь пришёл!</option></select></div><div><label for="codec">Источник / кодек</label><select id="codec"><option value="original">Оригинал (эталон)</option><option value="lpx3">LPX3 (эталонный WAV)</option><option value="hq3">HQ3 — стабильная AVR-прошивка</option><option value="stoi">HQ4 — оптимизация разборчивости</option><option value="timbre">HQ4 — оптимизация тембра</option></select></div></div>
<div class="buttons"><button class="main" id="play">▶ Воспроизвести</button><button id="compare">⇄ Оригинал → выбранное</button><button id="stop">■ Стоп</button></div>
<div class="buttons"><button id="wav">↓ Скачать WAV</button><button id="hex">↓ Скачать HEX</button><button id="verify">↻ Исполнить HEX в эмуляторе</button></div>
<p id="status">Выберите запись и кодек, затем нажмите воспроизведение.</p></section>
<section class="card"><div class="metrics"><div class="metric"><strong id="flash">—</strong><small>Flash / 1024 Б</small></div><div class="metric"><strong id="stoi">—</strong><small>STOI, выше лучше</small></div><div class="metric"><strong id="spectral">—</strong><small>Спектральная ошибка ↓</small></div></div><canvas id="wave" width="900" height="142" aria-label="Осциллограмма"></canvas><p class="note">Кнопка «Воспроизвести» использует заранее проверенные PCM-отсчёты для быстрого запуска звука. «Исполнить HEX» заново запускает AVR-инструкции и проверяет каждый отсчёт. Исходные оригиналы включены только для частного эксперимента.</p></section>
<section class="card"><h3>Как читать результаты</h3><p>Вариант «разборчивость» ориентирован на STOI, а «тембр» на близость логарифмической спектральной огибающей. В этой серии изменения небольшие: вариант HQ4 не следует считать безусловно лучше HQ3. Полный LPX3 здесь не помещается в ATtiny13A и представлен только эталонным WAV.</p>
<pre id="verifyReport">Повторная проверка HEX появится здесь.</pre><p class="note">Формат потоков HQ3/HQ4 один и тот же, без веток обратной совместимости в микроконтроллере. На физической плате испытаний не было. STOI измерен на этих же трёх записях, использованных при настройке.</p></section>
</main><script id="db" type="application/json">@@DATABASE@@</script><script>
@@AVR_EMULATOR@@
const DATA=JSON.parse(document.getElementById('db').textContent), $=id=>document.getElementById(id), SR=7500;
let ctx=null,active=null,revision=0;const cache=new Map();
function base64Bytes(s){const raw=atob(s),a=new Uint8Array(raw.length);for(let i=0;i<a.length;i++)a[i]=raw.charCodeAt(i);return a}
function pcm(name,codec){const key=name+':'+codec;if(cache.has(key))return cache.get(key);const src=DATA[name][codec];let bytes=base64Bytes(src.audio),view=new DataView(bytes.buffer);const out=new Float32Array(bytes.length/2);for(let i=0;i<out.length;i++)out[i]=view.getInt16(i*2,true)/32768;cache.set(key,out);return out}
function choose(){return [$('voice').value,$('codec').value]}
function metrics(){const [name,codec]=choose(),x=DATA[name][codec],isFirmware=!!x.firmware;$('flash').textContent=isFirmware?x.flash_bytes+' Б':'—';$('stoi').textContent=isFirmware?x.stoi.toFixed(4):'—';$('spectral').textContent=isFirmware?x.spectral_error.toFixed(4):'—';$('hex').disabled=!isFirmware;$('verify').disabled=!isFirmware;draw(pcm(name,codec))}
function draw(p){let c=$('wave'),g=c.getContext('2d');g.fillStyle='#0a111e';g.fillRect(0,0,c.width,c.height);g.strokeStyle='#324562';g.beginPath();g.moveTo(0,c.height/2);g.lineTo(c.width,c.height/2);g.stroke();g.strokeStyle='#76c7ff';g.lineWidth=1.7;g.beginPath();let block=Math.max(1,Math.floor(p.length/c.width));for(let i=0;i<c.width;i++){let idx=i*block;let v=p[idx]||0;let y=c.height/2-v*c.height*.42;if(!i)g.moveTo(i,y);else g.lineTo(i,y)}g.stroke()}
function rms(x){let s=0;for(const v of x)s+=v*v;return Math.sqrt(s/(x.length||1))}
async function playAudio(a){stop();ctx=ctx&&ctx.state!=='closed'?ctx:new (window.AudioContext||window.webkitAudioContext)();await ctx.resume();let b=ctx.createBuffer(1,a.length,SR);b.copyToChannel(a,0);let node=ctx.createBufferSource();node.buffer=b;node.connect(ctx.destination);active=node;node.onended=()=>{if(active===node)active=null};node.start();$('status').textContent='Воспроизводится. Для корректной работы на Android откройте HTML в Chrome.'}
function stop(){if(active){try{active.stop()}catch(e){}active.disconnect();active=null}}
$('play').onclick=async()=>{try{const [a,b]=choose();await playAudio(pcm(a,b))}catch(e){$('status').textContent='Ошибка воспроизведения: '+e.message}};
$('compare').onclick=async()=>{try{let [n,c]=choose();let original=pcm(n,'original'),selected=pcm(n,c);let silence=Math.floor(SR*.3),both=new Float32Array(original.length+silence+selected.length);let oa=.17/Math.max(.02,rms(original)),ob=.17/Math.max(.02,rms(selected));for(let i=0;i<original.length;i++)both[i]=Math.min(.96,Math.max(-.96,original[i]*oa));for(let i=0;i<selected.length;i++)both[original.length+silence+i]=Math.min(.96,Math.max(-.96,selected[i]*ob));await playAudio(both);$('status').textContent='A/B: оригинал → выбранный кодек, громкость выровнена по RMS.'}catch(e){$('status').textContent='Ошибка A/B: '+e.message}};
$('stop').onclick=()=>{stop();$('status').textContent='Остановлено.'};
function download(name,bytes,mime){let url=URL.createObjectURL(new Blob([bytes],{type:mime})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1200)}
function wavBytes(p){let n=p.length;const b=new ArrayBuffer(44+n*2),d=new DataView(b);function st(o,v){for(let i=0;i<v.length;i++)d.setUint8(o+i,v.charCodeAt(i))}st(0,'RIFF');d.setUint32(4,36+n*2,true);st(8,'WAVE');st(12,'fmt ');d.setUint32(16,16,true);d.setUint16(20,1,true);d.setUint16(22,1,true);d.setUint32(24,SR,true);d.setUint32(28,SR*2,true);d.setUint16(32,2,true);d.setUint16(34,16,true);st(36,'data');d.setUint32(40,n*2,true);for(let i=0;i<n;i++)d.setInt16(44+i*2,Math.max(-32768,Math.min(32767,Math.round(p[i]*32767))),true);return b}
$('wav').onclick=()=>{let [n,c]=choose();download('MiniLPC_'+n+'_'+c+'.wav',wavBytes(pcm(n,c)),'audio/wav')};
function hex(bytes){let l=[];for(let i=0;i<bytes.length;i+=16){let r=[Math.min(16,bytes.length-i),(i>>8)&255,i&255,0,...bytes.slice(i,i+16)];r.push(-r.reduce((a,b)=>a+b,0)&255);l.push(':'+r.map(z=>z.toString(16).toUpperCase().padStart(2,'0')).join(''))}return l.join('\\n')+'\\n:00000001FF\\n'}
$('hex').onclick=()=>{let [n,c]=choose(),x=DATA[n][c];if(x.firmware)download('MiniLPC_'+n+'_'+c+'.hex',hex(base64Bytes(x.firmware)),'text/plain')};
$('verify').onclick=async()=>{
 let [n,c]=choose(),entry=DATA[n][c];if(!entry.firmware)return;let v=++revision;stop();$('verify').disabled=true;$('verifyReport').textContent='Исполнение настоящего HEX...';$('status').textContent='Проверка может занять некоторое время на телефоне.';
 try{let core=new AVRCore(base64Bytes(entry.firmware));let expected=pcm(n,c);let errors=0,lastIRQ=0,irregular=0;for(let i=0;i<expected.length;i++){let got=core.takeSample(),expectedUint8=Math.max(0,Math.min(255,Math.round(expected[i]*128+128)));if(got!==expectedUint8)errors++;let delta=core.irqCount-lastIRQ;if(i>0&&(delta<4||delta>6))irregular++;lastIRQ=core.irqCount;if(i%700===0){$('verifyReport').textContent='Проверено '+i+' / '+expected.length;await new Promise(r=>setTimeout(r,0))}}if(revision!==v)return;
 $('verifyReport').textContent=`Отсчётов: ${expected.length}\nНесовпадений PCM: ${errors}\nПропусков Timer0: ${core.missedOverflows}\nНерегулярных интервалов PWM: ${irregular}\nМакс. длительность ISR: ${core.maxISR} тактов\nFlash: ${entry.flash_bytes} / 1024 байт`;
 $('status').textContent=errors||core.missedOverflows||irregular?'Обнаружено расхождение.':'Проверка HEX пройдена, PCM совпадает с эталоном.';
 }catch(e){$('verifyReport').textContent=e.stack||e.message;$('status').textContent='Ошибка эмуляции'}finally{metrics()}
};
$('voice').onchange=()=>{revision++;stop();metrics()};$('codec').onchange=()=>{revision++;stop();metrics()};metrics();
</script></body></html>'''
result=base.replace('@@DATABASE@@',json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')).replace('@@AVR_EMULATOR@@',source)
(REL/'index.html').write_text(result)
(ROOT/'MicroMusic_HQ4_Tradeoffs.html').write_text(result)
print('Generated HTML',len(result.encode()),'B; tracks',len(NAMES)*5)
