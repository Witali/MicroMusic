#!/usr/bin/env python3
"""Build a totally standalone HTML page with Web Audio player and real AVR HEX verifier."""
from pathlib import Path
import base64,json,html
ROOT=Path(__file__).resolve().parent
DATA={}
metrics=json.loads((ROOT/'metrics.json').read_text())
for n in ('chego','otvechaesh','vinni'):
    p=ROOT/'results'/n
    def b64(data):return base64.b64encode(data).decode('ascii')
    data={'info':metrics[n], 'hex':(p/'firmware.hex').read_text(),
          'firmware':b64((p/'firmware.bin').read_bytes()),
          'pcm':b64((p/'expected.raw').read_bytes()),
          'audio':{key:b64((p/f'{key}_player.wav').read_bytes()) for key in ('original','HQ3','HQ4','LPX3')}}
    DATA[n]=data
core=(ROOT/'avr_emulator.js').read_text()
page='''<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><title>MicroMusic · MiniLPC-HQ4</title>
<style>
:root{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color-scheme:dark;background:#0d1320;color:#f1f6fc}
*{box-sizing:border-box}body{margin:0;padding:24px 15px 50px;line-height:1.5}main{max-width:900px;margin:auto}
h1{font-size:clamp(25px,5vw,37px);line-height:1.15;margin:0 0 10px}h2{font-size:19px;margin:0 0 14px}
p{margin:8px 0 14px;color:#bdcada}.eyebrow{font-size:12px;font-weight:700;letter-spacing:.12em;color:#8cbcff;text-transform:uppercase}
.card{background:#1b2636;border:1px solid #35455c;border-radius:16px;padding:18px;margin-top:16px}
.picker{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:600px){.picker{grid-template-columns:1fr}}
label{font-weight:600;font-size:14px;display:block;color:#c7d6e9}select{margin-top:7px;width:100%;font:inherit;color:#f1f6fc;background:#101a29;border:1px solid #435875;border-radius:10px;padding:12px}
.buttons{display:flex;gap:9px;flex-wrap:wrap;margin:14px 0}button{font:inherit;cursor:pointer;border:1px solid #49617e;border-radius:10px;padding:11px 15px;background:#34465e;color:#fff;font-weight:600}button.primary{background:#5ca4ff;color:#0c172b;border:1px solid #77b4ff}button:disabled{opacity:.4;cursor:not-allowed}button:hover:not(:disabled){filter:brightness(1.14)}button:focus-visible,select:focus-visible{outline:3px solid #aacfff;outline-offset:2px}
.meters{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:8px}.meter{background:#121d2d;padding:13px;border-radius:10px}.meter strong{font-size:23px;display:block}.meter span{font-size:12px;color:#aec1d7}
@media(max-width:480px){.meters{grid-template-columns:1fr 1fr}.meter strong{font-size:19px}}
#scope{width:100%;height:145px;border-radius:10px;background:#0b1524;border:1px solid #2c3e56}
#status{margin-top:12px;min-height:30px;color:#aad3ff;white-space:pre-wrap;font-size:14px}
.tag{font-size:12px;color:#b7ddff;border:1px solid #3e597b;border-radius:100px;padding:4px 9px;white-space:nowrap}
footer{margin-top:24px;padding-top:16px;border-top:1px solid #304357;color:#aabbcc;font-size:13px}
small,.note{font-size:13px;color:#a5b8ce}.good{color:#9fedcb}.bad{color:#ffb09d}
</style></head><body><main>
<p class="eyebrow">MicroMusic · ATtiny13A · 9,6 МГц</p>
<h1>MiniLPC-HQ4 — эксперимент с речью</h1>
<p>Звук создаётся восьмиступенчатым LPC-фильтром. Выберите фразу и вариант записи. Для HQ3 и HQ4 в комплекте есть реальные HEX-прошивки; кнопка проверки заново исполняет HQ4 на модели процессора AVR по тактам.</p>
<div class="card">
 <div class="picker">
  <label>Пример речи<select id="phrase"><option value="chego">«Чего тебе нужно?»</option><option value="otvechaesh">«Что ж ты не отвечаешь?»</option><option value="vinni">«Сова! Открывай! Медведь пришёл!»</option></select></label>
  <label>Кодек<select id="codec"><option value="HQ4">MiniLPC-HQ4 — AVR</option><option value="HQ3">Предыдущий HQ3 — AVR</option><option value="LPX3">LPX3 — программный эталон</option><option value="original">Оригинал</option></select></label>
 </div>
 <div class="meters" id="meters"></div>
 <div class="buttons">
  <button class="primary" id="play">▶ Слушать</button>
  <button id="ab">⇄ Оригинал → выбранный</button>
  <button id="stop">■ Стоп</button>
 </div>
 <canvas id="scope" width="850" height="145" aria-label="Осциллограмма выбранной записи"></canvas>
 <div id="status" role="status">Готов к воспроизведению.</div>
</div>
<div class="card">
 <h2>Проверка реальной прошивки</h2>
 <p>Прошивка собиралась из AVR-ассемблера. Тест здесь заново исполняет её инструкции, считывает значения PWM и сравнивает с эталонным PCM по каждому отсчёту. Эта проверка может занять несколько секунд на телефоне.</p>
 <div class="buttons"><button id="verify">↻ Проверить HEX</button><button id="downloadHex">↓ Скачать HEX</button><button id="downloadWav">↓ Скачать WAV</button></div>
 <p class="note">Для LPX3 используется программный декодер; LPX3 не помещается в ATtiny13A. В WAV лежит результат исполнения HQ4 в цикловой модели AVR. Реальный выход PB1/OC0B зависит от RC-фильтра и усилителя.</p>
</div>
<div class="card">
 <h2>Текущие результаты</h2>
 <p>HQ4 автоматически подбирает длительности кадров, высоту, усиление, форманты и форму импульса, анализируя синтезированный сигнал. STOI — показатель разборчивости, а не точного сходства тембра.</p>
 <table style="border-collapse:collapse;width:100%;font-size:13px"><thead><tr><th style="text-align:left;padding:9px">Фраза</th><th>HQ3</th><th>HQ4</th><th>Flash</th></tr></thead><tbody id="summary"></tbody></table>
</div>
<footer>Сохранён исходный экспериментальный поток, автоматический кодировщик, AVR-ассемблер и проверка исполнения. Все результаты относятся к трём известным записям; ATtiny13A на физическом чипе ещё не испытывался. Исходные фрагменты мультфильмов — только для частных тестов.</footer>
</main><script>
__AVR_CORE__
const SAMPLES=__DATA__;
const $=id=>document.getElementById(id);
let ctx=null,playing=[],cached=new Map(),busy=false;
const labels={original:'Оригинал',HQ3:'MiniLPC-HQ3',HQ4:'MiniLPC-HQ4',LPX3:'LPX3'};
function names(){return [String($('phrase').value),String($('codec').value)]}
function binaryFromBase64(str){const bin=atob(str),arr=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)arr[i]=bin.charCodeAt(i);return arr}
function current(){const [name,codec]=names();return SAMPLES[name]}
function setStatus(text,kind=''){const el=$('status');el.textContent=text;el.className=kind}
function info(){const s=current().info,code=$('codec').value,fit=['HQ4','HQ3'].includes(code);
 $('meters').innerHTML=`<div class="meter"><strong>${s.stoi_after.toFixed(4)}</strong><span>STOI HQ4</span></div><div class="meter"><strong>${s.flash_bytes} / 1024 Б</strong><span>Вся Flash</span></div><div class="meter"><strong>${fit?'AVR HEX':'Эталон'}</strong><span>${fit?'Помещается в ATtiny13A':'Программное воспроизведение'}</span></div>`;
}
function summary(){let html='';for(let n of ['chego','otvechaesh','vinni']){let s=SAMPLES[n].info;
 html+=`<tr><td style="padding:9px;border-top:1px solid #31465b">${s.phrase}</td><td style="text-align:center;border-top:1px solid #31465b">${s.stoi_before.toFixed(4)}</td><td style="text-align:center;border-top:1px solid #31465b"><b>${s.stoi_after.toFixed(4)}</b></td><td style="text-align:center;border-top:1px solid #31465b">${s.flash_bytes} Б</td></tr>`;}
 $('summary').innerHTML=html;}
async function audioCtx(){if(!ctx)ctx=new(window.AudioContext||window.webkitAudioContext)();await ctx.resume();return ctx}
async function getAudio(n,kind){let key=n+':'+kind;if(cached.has(key))return cached.get(key);
 const c=await audioCtx(),bin=binaryFromBase64(SAMPLES[n].audio[kind]);
 const buffer=await c.decodeAudioData(bin.buffer.slice(0));cached.set(key,buffer);return buffer}
function stop(){for(const src of playing){try{src.stop()}catch(e){}}playing=[]}
function draw(buffer){const canvas=$('scope'),g=canvas.getContext('2d'),w=canvas.width,h=canvas.height;
 g.clearRect(0,0,w,h);g.fillStyle='#0b1524';g.fillRect(0,0,w,h);g.strokeStyle='#243b59';
 for(let y=28;y<h;y+=28){g.beginPath();g.moveTo(0,y);g.lineTo(w,y);g.stroke();}
 if(!buffer)return;const d=buffer.getChannelData(0);g.beginPath();g.strokeStyle='#70b2ff';g.lineWidth=1.6;
 for(let x=0;x<w;x++){let a=Math.floor(x*d.length/w),b=Math.floor((x+1)*d.length/w),lo=1,hi=-1;
 for(let z=a;z<Math.max(a+1,b);z++){let v=d[z];if(v<lo)lo=v;if(v>hi)hi=v}
 let y=(lo+hi)/2;let py=h/2-y*h*.42;if(x===0)g.moveTo(x,py);else g.lineTo(x,py)}g.stroke();}
function playBuffer(buffer,when=0){let source=ctx.createBufferSource(),gain=ctx.createGain();gain.gain.value=.85;source.buffer=buffer;
 source.connect(gain);gain.connect(ctx.destination);source.start(ctx.currentTime+when);playing.push(source);return buffer.duration;}
async function playAB(ab){try{let [name,kind]=names();stop();await audioCtx();const first=await getAudio(name,ab?'original':kind);
 if(ab){const second=await getAudio(name,kind);playBuffer(first,0);playBuffer(second,first.duration+.22);draw(second);
 setStatus('A/B: оригинал → '+labels[kind]+'.')}else{playBuffer(first);draw(first);setStatus('Воспроизводится: '+labels[kind]);}}
 catch(err){setStatus('Не удалось воспроизвести: '+err.message,'bad')}}
function saveFile(bytes,name,type){const url=URL.createObjectURL(new Blob([bytes],{type}));const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}
$('play').onclick=()=>playAB(false);$('ab').onclick=()=>playAB(true);$('stop').onclick=()=>{stop();setStatus('Воспроизведение остановлено.')};
$('phrase').onchange=()=>{stop();info();setStatus('Выберите вариант и нажмите Слушать.')};
$('codec').onchange=()=>{stop();info()};
$('downloadHex').onclick=()=>{let [name]=names();saveFile(new TextEncoder().encode(SAMPLES[name].hex),`MiniLPC-HQ4-${name}.hex`,'text/plain')};
$('downloadWav').onclick=()=>{let [name,kind]=names();saveFile(binaryFromBase64(SAMPLES[name].audio[kind]),`MicroMusic-${name}-${kind}.wav`,'audio/wav')};
$('verify').onclick=async()=>{
 if(busy)return;busy=true;$('verify').disabled=true;const [name]=names();const data=SAMPLES[name];const pcm=binaryFromBase64(data.pcm);
 try{let core=new AVRCore(binaryFromBase64(data.firmware)),bad=0;
 for(let i=0;i<pcm.length;i++){const got=core.takeSample();if(got!==pcm[i])bad++;
 if(i%512===511){setStatus(`AVR HEX: ${i+1}/${pcm.length} отсчётов...`);await new Promise(r=>setTimeout(r,0))}}
 const good=bad===0&&core.missedOverflows===0;
 setStatus(`${good?'Проверка пройдена':'Ошибка эмуляции'}: ${pcm.length} отсчётов, несовпадений ${bad}, пропусков переполнения ${core.missedOverflows}, прерываний ${core.irqCount}, max ISR ${core.maxISR} тактов.`,good?'good':'bad');}
 catch(err){setStatus('Ошибка проверки AVR: '+err.message,'bad')}
 finally{busy=false;$('verify').disabled=false}
};
summary();info();draw(null);
</script></body></html>'''
page=page.replace('__AVR_CORE__',core).replace('__DATA__',json.dumps(DATA,ensure_ascii=False))
out=ROOT/'index.html';out.write_text(page,encoding='utf-8')
print('Standalone player:',out,len(page),'chars')
