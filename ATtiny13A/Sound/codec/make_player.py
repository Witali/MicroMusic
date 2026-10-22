#!/usr/bin/env python3
"""Build a truly offline audio comparison & machine-code validation page."""
import base64, json, html
from pathlib import Path
import numpy as np
import soundfile as sf
ROOT=Path(__file__).resolve().parent
NAMES=('chego','otvechaesh','vinni')
DISPLAY={'chego':'Чего тебе нужно?','otvechaesh':'Что ж ты не отвечаешь?','vinni':'Сова! Открывай! Медведь пришёл!'}

def b64(x):return base64.b64encode(x).decode('ascii')
def wav_pcm16(path):
 y,sr=sf.read(path,always_2d=True,dtype='float32')
 assert sr==7500 and y.shape[1]==1
 return b64((np.clip(y[:,0],-1,1)*32767).astype('<i2').tobytes())

DATA={}
for name in NAMES:
 d=ROOT/'samples'/name
 report=json.loads((d/'metrics.json').read_text())
 DATA[name]={
  'label':DISPLAY[name],
  'original':wav_pcm16(ROOT/'references'/name/'original.wav'),
  'lpx3':wav_pcm16(ROOT/'references'/name/'lpx3.wav'),
  'old':b64((d/'reference_pcm.raw').read_bytes()),
  'new':b64((d/'avr_pcm.raw').read_bytes()),
  'hex':(d/'firmware.hex').read_text(),
  'asm':(d/'firmware.S').read_text(),
  'compressed':b64((d/'speech.vbr').read_bytes()),
  'types':b64((d/'selected_modes.bin').read_bytes()),
  'metrics':report,
  'frameCount':report['frames'],
  'flashSize':len((d/'firmware.bin').read_bytes()),
  'oldFlashSize':364+report['bytes_original']+1,
 }

css='''
:root{font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;color-scheme:dark;color:#edf3fb;background:#101721}
*{box-sizing:border-box}body{margin:0}main{width:min(960px,100%);margin:0 auto;padding:18px 15px 55px}
h1{font-size:clamp(25px,5vw,36px);margin:0 0 6px}p{line-height:1.5;color:#b7c7d8}
small,.muted{color:#a8bbce;font-size:13px}.accent{color:#96ddf4}
.card{border:1px solid #3b516a;background:#1b2838;border-radius:14px;padding:16px;margin:14px 0}
form{display:grid;grid-template-columns:1fr 1fr;gap:12px}label{display:block;color:#cdd9e7;font-weight:650;margin-bottom:7px}
select{width:100%;background:#132236;border:1px solid #536783;border-radius:10px;color:#f5f8fd;font-size:16px;padding:12px}
button{font:inherit;color:#f3f8ff;border:1px solid #516b88;background:#2a405b;border-radius:10px;padding:11px 14px;cursor:pointer;touch-action:manipulation;font-weight:650}
button.primary{color:#0d2430;background:#91dbff;border-color:#91dbff}button:disabled{opacity:.45;cursor:default}
.actions{display:flex;flex-wrap:wrap;gap:9px}.actions button{flex-grow:1}h2{font-size:18px;margin:4px 0 14px}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.metric{background:#122033;padding:12px 8px;border-radius:9px;min-width:0}
.metric strong{display:block;font-size:clamp(16px,2.9vw,23px);font-variant-numeric:tabular-nums}.metric span{font-size:12px;color:#b0c1d3}
.bar{height:11px;background:#34445a;border-radius:12px;overflow:hidden;margin-top:9px}.bar>div{background:linear-gradient(90deg,#6ba7ff,#87e3c9);height:100%;transition:width .15s}
canvas{display:block;width:100%;height:165px;background:#0d1928;border:1px solid #3c526e;border-radius:10px}
pre{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#cfe5f5;white-space:pre-wrap;overflow-wrap:anywhere}
#status{min-height:26px;color:#9de4bd;margin-top:12px}#status.err{color:#ffa7a7}#verifyStatus{color:#a8cfff;white-space:pre-line;margin-top:9px}
.tag{display:inline-block;border:1px solid #4f6883;color:#c3d2e0;border-radius:8px;font-size:12px;padding:5px 8px;margin:5px 6px 5px 0}
.w-ctl{display:flex;align-items:center;gap:8px;font-size:14px;color:#bcd0e2;margin-top:12px}
@media(max-width:560px){form{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.actions button{flex:1 1 100%}}
'''
markup='''
<main>
  <h1>MicroMusic <span class="accent">VBR LPC-8</span></h1>
  <p>Эксперимент с переменной длиной речевых кадров для ATtiny13A: 8-ступенчатый LPC, четыре профиля возбуждения, 7,5 кГц PCM и 37,5 кГц PWM.</p>
  <section class="card">
    <form onsubmit="return false">
      <div><label for="voice">Пример речи</label><select id="voice"><option value="chego">«Чего тебе нужно?»</option><option value="otvechaesh">«Что ж ты не отвечаешь?»</option><option value="vinni">«Сова! Открывай! Медведь пришёл!»</option></select></div>
      <div><label for="codec">Вариант звучания</label><select id="codec"><option value="original">Оригинальная запись</option><option value="lpx3">LPX3 (качественный эталон)</option><option value="old">MiniLPC — кадры по 6 байт</option><option value="new" selected>MiniLPC VBR — настоящий ATtiny13A HEX</option></select></div>
    </form>
    <div class="actions" style="margin-top:14px">
      <button class="primary" id="play">▶ Слушать</button>
      <button id="ab">⇄ Оригинал → выбранный</button>
      <button id="stop">■ Остановить</button>
    </div>
    <div class="w-ctl"><input type="checkbox" id="matchVolume" checked><label for="matchVolume" style="margin:0;font-weight:400">Выравнивать громкость для A/B</label></div>
    <div id="status" aria-live="polite">Готово. Нажмите «Слушать».</div>
  </section>
  <section class="card">
    <h2>Размер и качество</h2>
    <div class="metrics">
      <div class="metric"><strong id="flash"></strong><span>Flash, код + речь</span></div>
      <div class="metric"><strong id="speech"></strong><span>Речевые данные VBR</span></div>
      <div class="metric"><strong id="saving"></strong><span>Экономия Flash</span></div>
      <div class="metric"><strong id="stoi"></strong><span>STOI VBR / старый</span></div>
    </div>
    <div class="bar"><div id="barFill"></div></div>
    <div id="types" class="muted" style="margin-top:10px"></div>
  </section>
  <section class="card">
    <h2>Осциллограмма</h2>
    <canvas id="wave" width="940" height="165"></canvas>
    <div class="muted" style="margin-top:9px">Воспроизведение — через Web Audio. Для AVR-прошивки используется WAV, предварительно полученный исполнением HEX. Кнопка проверки ниже повторяет машинную эмуляцию.</div>
  </section>
  <section class="card">
    <h2>Эмуляция и файлы</h2>
    <div class="actions">
      <button class="primary" id="verify">Проверить настоящий HEX</button>
      <button id="getHex">↓ Firmware HEX</button>
      <button id="getSpeech">↓ VBR-данные</button>
      <button id="getAsm">↓ Исходник ASM</button>
      <button id="getWav">↓ Прослушиваемый WAV</button>
    </div>
    <div id="verifyStatus">Прошивка на 9,6 МГц, Timer0 Fast PWM, выход PB1/OC0B.</div>
  </section>
  <section class="card">
    <h2>Новый формат речевых кадров</h2>
    <pre>Байт 0: pitch (0 = шум)
Байт 1: gain[3:0] | profile[5:4] | type[7:6]

00: полный кадр         6 байт (8 LPC-коэффициентов)
01: повтор спектра       2 байта (новые pitch/gain)
10: изменить K1–K4      4 байта
11: изменить K5–K8      4 байта</pre>
    <p class="muted">Этот битовый поток — новый формат. Старый формат в AVR-декодере не поддерживается. Кодировщик автоматически выбирает тип кадров через обратное сравнение с исходным звуком и штраф за щелчки. Вариант с фиксированными кадрами показан только для сравнения.</p>
  </section>
  <p class="muted">Записи из мультфильмов включены для частного тестирования. Для публикации в открытом репозитории необходимо исключить защищённые аудиофрагменты и производные данные без разрешения правообладателей. Работа на физическом ATtiny13A пока не проверялась.</p>
</main>
'''
js='''
const DEMOS=__DATA__;
const $=id=>document.getElementById(id);
const SAMPLE_RATE=7500;
let ac=null,active=null,activePCM=null,playing=false;
const cache={};
function fromB64(x){const s=atob(x),b=new Uint8Array(s.length);for(let i=0;i<b.length;i++)b[i]=s.charCodeAt(i);return b}
function getSamples(voice,mode){
  const key=voice+':'+mode;if(cache[key])return cache[key];
  const b=fromB64(DEMOS[voice][mode]);let a;
  if(mode==='original'||mode==='lpx3'){
    const dv=new DataView(b.buffer,b.byteOffset,b.byteLength);a=new Float32Array(b.length/2);
    for(let i=0;i<a.length;i++)a[i]=dv.getInt16(i*2,true)/32768;
  }else{a=new Float32Array(b.length);for(let i=0;i<a.length;i++)a[i]=(b[i]-128)/128}
  return cache[key]=a;
}
function getGain(x){
  if(!$('matchVolume').checked)return 0.9;
  let sum=0;for(let i=0;i<x.length;i++)sum+=x[i]*x[i];
  let rms=Math.sqrt(sum/x.length)||.1;
  return Math.min(3.0,.16/rms);
}
function buildArray(chunks){let len=chunks.reduce((s,x)=>s+x.length,0);let y=new Float32Array(len),p=0;for(const a of chunks){y.set(a,p);p+=a.length}return y}
function limitedGain(a){let g=getGain(a);let peak=0;for(let x of a)peak=Math.max(peak,Math.abs(x*g));return peak>0.96?g*0.96/peak:g}
function getTrack(){return getSamples($('voice').value,$('codec').value)}
function currentPlayback(){const mode=$('codec').value,voice=$('voice').value;
  if($('playingAB'))return getSamples(voice,'original');
  return getSamples(voice,mode)}
async function startPCM(x){
  stop(false);
  ac ||= new (window.AudioContext||window.webkitAudioContext)();
  await ac.resume();
  const b=ac.createBuffer(1,x.length,SAMPLE_RATE);b.copyToChannel(x,0);
  const src=ac.createBufferSource();src.buffer=b;src.connect(ac.destination);active=src;playing=true;
  src.onended=()=>{if(active===src){active=null;playing=false;$('status').textContent='Воспроизведение завершено.'}};
  src.start();activePCM=x;draw(x);
}
function stop(update=true){if(active){try{active.stop()}catch(e){}try{active.disconnect()}catch(e){}active=null}playing=false;if(update)$('status').textContent='Остановлено.'}
function draw(pcm){const c=$('wave'),g=c.getContext('2d'),w=c.width,h=c.height;g.fillStyle='#0d1928';g.fillRect(0,0,w,h);
 g.lineWidth=1;g.strokeStyle='#2a425b';g.beginPath();g.moveTo(0,h/2);g.lineTo(w,h/2);g.stroke();
 g.strokeStyle='#8fd3ff';g.lineWidth=1.2;g.beginPath();const width=Math.max(1,Math.floor(pcm.length/w));
 for(let i=0;i<w;i++){let p0=i*width,p1=Math.min(pcm.length,p0+width),mn=1,mx=-1;
  for(let j=p0;j<p1;j++){mn=Math.min(mn,pcm[j]);mx=Math.max(mx,pcm[j])}
  if(p0>=pcm.length)break;g.moveTo(i,h*.5-mn*h*.4);g.lineTo(i,h*.5-mx*h*.4)
 }g.stroke();
}
function show(){stop(false);let v=DEMOS[$('voice').value],m=v.metrics;
 $('flash').textContent=v.flashSize+' Б / 1024 Б';$('speech').textContent=m.bytes_vbr+' Б';
 $('saving').textContent=(v.oldFlashSize-v.flashSize)+' Б';
 $('stoi').textContent=m.vbr.stoi.toFixed(3)+' / '+m.baseline.stoi.toFixed(3);
 $('barFill').style.width=(v.flashSize/1024*100).toFixed(2)+'%';
 let type=m.vbr.types;$('types').textContent=`Кадров: ${m.frames}. Полных (6 Б): ${type[0]}; повтор (2 Б): ${type[1]}; половина коэффициентов (4 Б): ${Number(type[2])+Number(type[3])}. Экономия речевых данных: ${m.bytes_original-m.bytes_vbr} Б.`;
 $('status').textContent='Выбран пример и режим. Нажмите «Слушать».';
 $('verifyStatus').textContent='Для нового формата можно повторно исполнить настоящую прошивку в AVR-эмуляторе.';
 draw(getTrack());
}
function makeWAV(samples){let size=44+samples.length*2;let ab=new ArrayBuffer(size),dv=new DataView(ab);
 const txt=(offset,s)=>{for(let i=0;i<s.length;i++)dv.setUint8(offset+i,s.charCodeAt(i))};
 txt(0,'RIFF');dv.setUint32(4,size-8,true);txt(8,'WAVEfmt ');dv.setUint32(16,16,true);dv.setUint16(20,1,true);dv.setUint16(22,1,true);
 dv.setUint32(24,SAMPLE_RATE,true);dv.setUint32(28,SAMPLE_RATE*2,true);dv.setUint16(32,2,true);dv.setUint16(34,16,true);
 txt(36,'data');dv.setUint32(40,samples.length*2,true);
 for(let i=0;i<samples.length;i++){let y=Math.max(-1,Math.min(1,samples[i]));dv.setInt16(44+i*2,Math.round(y*32767),true)}return ab;
}
function saveBlob(bytes,filename,type){const url=URL.createObjectURL(new Blob([bytes],{type:type||'application/octet-stream'}));
 const a=document.createElement('a');a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000)}
function save(name,ext,data,type){saveBlob(data,`${$('voice').value}_minilpc_vbr.${ext}`,type)}
$('voice').onchange=show;$('codec').onchange=show;
$('play').onclick=async()=>{try{let a=getTrack(),g=limitedGain(a),x=Float32Array.from(a,v=>v*g);
 await startPCM(x);$('status').textContent='Воспроизводится: '+$('codec').selectedOptions[0].textContent;
 }catch(e){$('status').textContent='Ошибка аудио: '+e.message;$('status').className='err'}};
$('ab').onclick=async()=>{try{let a=getSamples($('voice').value,'original'),b=getTrack(),gap=new Float32Array(Math.floor(.25*SAMPLE_RATE));
 let joined=buildArray([Float32Array.from(a,x=>x*limitedGain(a)),gap,Float32Array.from(b,x=>x*limitedGain(b))]);
 await startPCM(joined);$('status').textContent='Оригинал → выбранный кодек (с паузой 0,25 с)';
 }catch(e){$('status').textContent='Ошибка A/B: '+e.message;$('status').className='err'}};
$('stop').onclick=()=>stop();
$('getHex').onclick=()=>save('hex','hex',DEMOS[$('voice').value].hex,'text/plain');
$('getSpeech').onclick=()=>save('vbr','bin',fromB64(DEMOS[$('voice').value].compressed));
$('getAsm').onclick=()=>save('asm','S',DEMOS[$('voice').value].asm,'text/plain');
$('getWav').onclick=()=>save('wav','wav',makeWAV(getTrack()),'audio/wav');
$('verify').onclick=async()=>{
 $('verify').disabled=true;
 try{
  const voice=$('voice').value, data=DEMOS[voice], actual=fromB64(data.new), core=AVRCore.fromHex(data.hex);
  const count=actual.length;let mismatches=0;
  $('verifyStatus').textContent=`Эмуляция AVR: 0 / ${count} отсчётов…`;
  for(let i=0;i<count;i++){
    if(core.takeSample()!==actual[i])mismatches++;
    if(i%384===0){$('verifyStatus').textContent=`Эмуляция AVR: ${i} / ${count} отсчётов…`;await new Promise(r=>setTimeout(r,0))}
  }
  const ok=mismatches===0&&core.missedOverflows===0;
  $('verifyStatus').textContent=`${ok?'✓ Проверка пройдена':'✗ Ошибка'}: ${count} отсчётов, различий ${mismatches}, пропущенных переполнений ${core.missedOverflows}, максимум ISR ${core.maxISR} тактов. Размер Flash ${data.flashSize} Б.`;
 }catch(e){$('verifyStatus').textContent='Ошибка эмуляции: '+e.stack}
 finally{$('verify').disabled=false}
};
show();
'''
# Remove tiny unused malformed helper expression from JS (not called but confusing)
js=js.replace("function currentPlayback(){const mode=$('codec').value,voice=$('voice').value;\n  if($('playingAB'))return getSamples(voice,'original');\n  return getSamples(voice,mode)}\n",'')
js=js.replace('__DATA__',json.dumps(DATA,ensure_ascii=False,separators=(',',':')).replace('</','<\\/'))
script=(ROOT/'avr_emulator.js').read_text()
page='<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MicroMusic VBR LPC-8 / ATtiny13A</title><style>'+css+'</style></head><body>'+markup+'<script>'+script+'\n'+js+'</script></body></html>'
(ROOT/'index.html').write_text(page,encoding='utf8')
print('HTML',len(page.encode('utf8')),'bytes')
