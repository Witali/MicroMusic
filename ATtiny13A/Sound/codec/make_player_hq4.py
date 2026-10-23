#!/usr/bin/env python3
"""Generate one offline, mobile-friendly player with real AVR instruction emulator.
The original film audio is embedded for private A/B listening, not public redistribution.
"""
import base64,json,html,hashlib
from pathlib import Path
import numpy as np,soundfile as sf
from build_hq4 import DEST, REF, CLIPS, wav_bytes

DATA={};REPORT=json.loads((DEST/'report.json').read_text())
for name in CLIPS:
    folder=DEST/name
    item={'name':{'chego':'Чего тебе нужно?','otvechaesh':'Что ж ты не отвечаешь?','vinni':'Сова! Открывай! Медведь пришёл!'}[name],
          'meta':REPORT[name], 'bin':base64.b64encode((folder/'firmware.bin').read_bytes()).decode(),
          'hex':(folder/'firmware.hex').read_text(),
          'expected':base64.b64encode((folder/'expected.raw').read_bytes()).decode(),
          'sound':{}}
    for k,filename in [('original','original.wav'),('old','hq3.wav'),('new','hq4.wav'),('lpx3','lpx3.wav')]:
        item['sound'][k]=base64.b64encode((folder/filename).read_bytes()).decode()
    if name=='chego':
        m=DEST/'chego_stoi_max'
        item['sound']['max']=base64.b64encode((m/'hq4.wav').read_bytes()).decode()
        item['binMax']=base64.b64encode((m/'firmware.bin').read_bytes()).decode()
        item['hexMax']=(m/'firmware.hex').read_text()
        item['expectedMax']=base64.b64encode((m/'expected.raw').read_bytes()).decode()
        item['metaMax']={'stoi':0.901820609779717,'flash_bytes':len((m/'firmware.bin').read_bytes())}
    DATA[name]=item
    # A/B sequence, unaltered individual originals plus headroom-balanced contrasts.
    ref,sr=sf.read(folder/'original.wav')
    old,_=sf.read(folder/'hq3.wav')
    new,_=sf.read(folder/'hq4.wav')
    lpx,_=sf.read(folder/'lpx3.wav')
    chunks=[]
    pause=np.zeros(int(sr*.25),dtype=np.float32)
    for y in [ref,old,ref,new,lpx]:
        z=np.asarray(y,dtype=np.float32)
        rms=lambda a:float(np.sqrt(np.mean(a*a)+1e-12))
        z=np.clip(z*.14/max(rms(z),.02),-.94,.94)
        chunks.extend((z,pause))
    (folder/'AB.wav').write_bytes(wav_bytes(np.concatenate(chunks),sr))

core_js=(DEST/'avr_emulator.js').read_text()
# Standalone client HTML. Unlike the earlier long data: audio URLs, each WAV is
# decoded into Web AudioBuffer on click after resuming the user-gesture context.
TEMPLATE=r'''<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>MicroMusic · MiniLPC HQ4 AVR Emulator</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,Segoe UI,Arial;background:#0c1220;color:#ecf2fb}
*{box-sizing:border-box}body{max-width:900px;margin:0 auto;padding:19px 14px 60px;line-height:1.46}
h1{font-size:clamp(23px,4vw,36px);letter-spacing:-.03em;margin:0 0 8px}
p{color:#bac8da}h2{font-size:19px}
.card{background:#162235;border:1px solid #32445e;border-radius:15px;margin:16px 0;padding:18px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
@media(max-width:560px){.grid{grid-template-columns:1fr}.card{padding:13px}}
label{display:flex;flex-direction:column;gap:5px;font-weight:650;font-size:14px}
select{font:inherit;background:#253954;border:1px solid #59718d;color:#fff;padding:11px;border-radius:9px;width:100%}
.buttons{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
button{padding:12px 15px;border:0;background:#85bcff;border-radius:9px;color:#071222;font-weight:700;font-size:14px;cursor:pointer}
button.secondary{background:#32455e;color:#eaf3ff}button:disabled{opacity:.48;cursor:default}
canvas{width:100%;height:144px;background:#091526;border-radius:10px;display:block;margin-top:10px}
.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.metric{background:#101d2d;border-radius:9px;padding:11px 9px}.metric strong{display:block;font-size:20px;font-variant-numeric:tabular-nums}.metric span{font-size:12px;color:#b5c5d7}
#status{font-size:14px;min-height:35px;color:#a6dbff;white-space:pre-wrap}details{margin-top:12px;font-size:13px;color:#c1cbda}
progress{display:block;width:100%;height:12px;margin-top:10px}a{color:#b1d6ff}
</style></head><body>
<h1>MicroMusic · MiniLPC HQ4</h1>
<p>Три речевых примера. Оригинал, HQ3, улучшенная HQ4 и LPX3. Для HQ4 доступны настоящие ATtiny13A HEX и эмуляция AVR-инструкций с подсчётом тактов.</p>
<section class="card"><div class="grid">
<label>Пример звука<select id="clip"><option value="chego">Чего тебе нужно?</option><option value="otvechaesh">Что ж ты не отвечаешь?</option><option value="vinni">Сова! Открывай! Медведь пришёл!</option></select></label>
<label>Вариант кодека<select id="codec"><option value="original">Оригинал</option><option value="old">MiniLPC HQ3</option><option value="new">MiniLPC HQ4 · сбалансированный</option><option value="max">MiniLPC HQ4 · максимум STOI (первая фраза)</option><option value="lpx3">LPX3 · референсное WAV</option></select></label>
</div><div class="buttons"><button id="play">▶ Слушать</button><button class="secondary" id="ab">⇄ Сравнить оригинал / HQ4</button><button class="secondary" id="stop">■ Стоп</button></div>
<div class="buttons"><button class="secondary" id="verify">Проверить HEX в AVR-эмуляторе</button><button class="secondary" id="downloadWav">↓ WAV выбранного звука</button><button class="secondary" id="downloadHex">↓ HEX HQ4</button></div>
<progress id="progress" value="0" max="100" style="display:none"></progress>
<p id="status">Выбери пример и нажми «Слушать». Встроенные файлы не требуют сервера.</p>
<canvas id="osc" width="880" height="144" aria-label="Осциллограмма звука"></canvas></section>
<section class="card"><h2>Текущая прошивка ATtiny13A</h2><div class="metrics"><div class="metric"><strong id="flash">—</strong><span>Flash / 1024 байт</span></div><div class="metric"><strong id="quality">—</strong><span>STOI относительно оригинала</span></div><div class="metric"><strong id="codebytes">406 Б</strong><span>Сам декодер</span></div></div>
<details><summary>Что именно эмулируется?</summary>
<p>Новый вариант содержит настоящий AVR-бинарник с речевыми параметрами. Кнопка проверки пошагово выполняет инструкции CPU, прерывания Timer0 и записи в OCR0B, затем сравнивает каждый сэмпл с контрольным выводом.</p>
<p>Обычная кнопка «Слушать» воспроизводит заранее рассчитанный WAV от той же прошивки для плавного звука в мобильном браузере. LPX3 — сравнительное WAV, а не прошивка ATtiny13A.</p></details></section>
<script>const CLIPS=__DATA__;</script>
<script>__AVR_CORE__</script>
<script>
'use strict';
const $=(id)=>document.getElementById(id);
const fromB64=(s)=>Uint8Array.from(atob(s),x=>x.charCodeAt(0));
const clipSel=$('clip'),codecSel=$('codec'),status=$('status'),can=$('osc');
let audio=null,playing=[],verifyRunning=false;let waveCache={};
function selected(){return CLIPS[clipSel.value]}
function info(){let m=codecSel.value==='max'&&clipSel.value==='chego'?selected().metaMax:selected().meta;$('flash').textContent=m.flash_bytes+' Б';$('quality').textContent=m.stoi.toFixed(4);draw();}
function draw(samples=null){const ctx=can.getContext('2d');let w=can.width,h=can.height;ctx.fillStyle='#091526';ctx.fillRect(0,0,w,h);ctx.strokeStyle='#263b56';ctx.beginPath();ctx.moveTo(0,h/2);ctx.lineTo(w,h/2);ctx.stroke();
 if(!samples){const d=selected();samples=fromB64(codecSel.value==='max'&&clipSel.value==='chego'?d.expectedMax:d.expected);}
 let stride=Math.max(1,Math.floor(samples.length/w));ctx.strokeStyle='#6fbaff';ctx.lineWidth=1.3;ctx.beginPath();
 for(let i=0;i<w;i++){let k=Math.min(samples.length-1,i*stride),v=samples[k];let y=h/2-((v-128)/128)*h*.43;if(i===0)ctx.moveTo(i,y);else ctx.lineTo(i,y);}ctx.stroke();}
async function context(){if(!audio)audio=new (window.AudioContext||window.webkitAudioContext)();await audio.resume();return audio;}
function stop(){for(const n of playing){try{n.stop()}catch(e){}}playing=[];status.textContent='Воспроизведение остановлено.'}
async function soundBuffer(k){const a=await context();const src=fromB64(selected().sound[k]);return await a.decodeAudioData(src.buffer.slice(src.byteOffset,src.byteOffset+src.byteLength));}
function level(buff){const a=buff.getChannelData(0);let v=0;for(let j=0;j<a.length;j++)v+=a[j]*a[j];return Math.sqrt(v/a.length)}
async function play(){try{stop();const a=await context(),name=codecSel.value,b=await soundBuffer(name);const s=a.createBufferSource();s.buffer=b;
let gain=a.createGain();gain.gain.value=.8;s.connect(gain).connect(a.destination);s.start();playing=[s];status.textContent='Слушаем '+selected().name+' — '+codecSel.options[codecSel.selectedIndex].text;s.onended=()=>{playing=playing.filter(x=>x!==s)};}catch(e){status.textContent='Ошибка звука: '+e.message}}
async function ab(){try{stop();const a=await context();const b0=await soundBuffer('original');const target=codecSel.value==='max'&&clipSel.value==='chego'?'max':'new';const b1=await soundBuffer(target);let at=a.currentTime+.04;
for(let b of [b0,b1,b0,b1]){let s=a.createBufferSource(),g=a.createGain();s.buffer=b;g.gain.value=Math.min(1.4,.13/Math.max(.04,level(b)));s.connect(g).connect(a.destination);s.start(at);playing.push(s);at+=b.duration+.24;}status.textContent='Сравнение: оригинал → HQ4 → оригинал → HQ4 (RMS приблизительно выровнен).';}catch(e){status.textContent='Ошибка A/B: '+e.message}}
function saveBytes(bytes,filename,type){const blob=new Blob([bytes],{type}),url=URL.createObjectURL(blob);let a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),3000)}
function saveHex(){const d=selected(),s=(codecSel.value==='max'&&clipSel.value==='chego')?d.hexMax:d.hex;saveBytes(new TextEncoder().encode(s),clipSel.value+'_HQ4_ATtiny13.hex','text/plain')}
function saveWav(){saveBytes(fromB64(selected().sound[codecSel.value]),clipSel.value+'_'+codecSel.value+'.wav','audio/wav')}
const afterFrame=()=>new Promise(resolve=>requestAnimationFrame(resolve));
async function verify(){if(verifyRunning)return;verifyRunning=true;const b=$('verify'),p=$('progress');b.disabled=true;p.style.display='block';p.value=0;
let name=clipSel.value,d=CLIPS[name],max=(codecSel.value==='max'&&name==='chego'),expected=fromB64(max?d.expectedMax:d.expected),actual=new Uint8Array(expected.length);
try{const core=new AVRCore(fromB64(max?d.binMax:d.bin));let mismatch=0;
for(let i=0;i<expected.length;){let until=Math.min(expected.length,i+256);for(;i<until;i++){let v=core.takeSample();actual[i]=v;if(v!==expected[i])mismatch++}
 p.value=Math.round(i*100/expected.length);if(i%2048===0||i===expected.length){status.textContent='Эмуляция '+d.name+': '+i+' / '+expected.length+' отсчётов';await afterFrame()}}
if(mismatch||core.missedOverflows)status.textContent='Проверка обнаружила ошибки: отличий '+mismatch+', потерянных переполнений '+core.missedOverflows;
else status.textContent='HEX проверен: '+expected.length+' отсчётов совпали; '+core.irqCount+' прерываний Timer0; 0 потерь. Макс. ISR '+core.maxISR+' тактов.';
draw(actual);
}catch(e){status.textContent='Ошибка эмуляции: '+e.message}
finally{b.disabled=false;verifyRunning=false;p.style.display='none';}}
function updateModes(){let o=codecSel.querySelector('option[value=\"max\"]');o.disabled=clipSel.value!=='chego';if(o.disabled&&codecSel.value==='max')codecSel.value='new'}
clipSel.addEventListener('change',()=>{stop();updateModes();info()});codecSel.addEventListener('change',()=>{stop();info()});$('play').onclick=play;$('ab').onclick=ab;$('stop').onclick=stop;$('verify').onclick=verify;$('downloadWav').onclick=saveWav;$('downloadHex').onclick=saveHex;updateModes();info();
</script>
</body></html>'''
htmltext=TEMPLATE.replace('__DATA__',json.dumps(DATA,ensure_ascii=False,separators=(',',':'))).replace('__AVR_CORE__',core_js)
(DEST/'index.html').write_text(htmltext)
(Path(__file__).resolve().parent/'MicroMusic_MiniLPC_HQ4.html').write_text(htmltext)
print('HTML bytes',len(htmltext),'clips',len(DATA),'sha256',hashlib.sha256(htmltext.encode()).hexdigest())
