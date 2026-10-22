#!/usr/bin/env python3
"""Create a self-contained page for private A/B comparison.
The reference tracks are *not* included in the published code-only archive.
"""
from pathlib import Path
import base64,json,numpy as np,soundfile as sf
BASE=Path(__file__).resolve().parent
REFERENCE=BASE/'references'
WAVES={};FW={};REF={}
for k in ['chego','otvechaesh','vinni']:
    loc=BASE/'samples'/k
    ref=REFERENCE/k
    WAVES[k]={}
    for mode,f in [('original','original.wav'),('lpx3','lpx3.wav'),('full','full350.wav')]:
        samples,rate=sf.read(ref/f,dtype='float32')
        assert rate==7500 and len(samples)==len((loc/'expected_pcm.raw').read_bytes())
        q=(np.maximum(-1,np.minimum(1,samples))*32767).astype('<i2')
        WAVES[k][mode]=base64.b64encode(q.tobytes()).decode()
    avr=np.frombuffer((loc/'avr_pcm.raw').read_bytes(),np.uint8)
    WAVES[k]['native']=base64.b64encode(((avr.astype(np.int16)-128)*256).astype('<i2').tobytes()).decode()
    FW[k]=base64.b64encode((loc/'firmware.bin').read_bytes()).decode()
    REF[k]=base64.b64encode((loc/'expected_pcm.raw').read_bytes()).decode()
core=(BASE/'avr_emulator.js').read_text()
assert 'class AVRCore' in core
content=r'''<!doctype html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MicroMusic – New-only MiniLPC8</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,sans-serif;background:#0b1321;color:#e6eefb}
*{box-sizing:border-box}body{margin:0;padding:18px;line-height:1.5}main{max-width:860px;margin:auto}
h1{font-size:clamp(1.5rem,5vw,2.3rem);margin:0 0 .35em}.sub{color:#9aadc6;margin:0 0 20px}
.card{background:#172337;border:1px solid #344764;border-radius:15px;padding:18px;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
label{display:block;font-size:.88rem;font-weight:650;color:#c5d4eb;margin:0 0 6px}
select,input,button{font:inherit}select{width:100%;border:1px solid #526783;border-radius:9px;padding:10px;background:#101e30;color:#eaf2fe}
button{border:0;background:#69b6ff;color:#081522;padding:10px 13px;border-radius:9px;font-weight:700;cursor:pointer;touch-action:manipulation}
button.secondary{background:#30425a;color:#e5f0ff}button:disabled{opacity:.5;cursor:default}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin:13px 0}
.stat{display:flex;flex-direction:column;gap:2px;background:#0f1b2b;border-radius:8px;padding:9px 12px}
.stat b{font-size:1.2rem}.stat small,small{color:#a9bed6}#status{white-space:pre-wrap;min-height:1.4em;color:#9ce3c7}
#wave{display:block;background:#101b2c;width:100%;height:130px;border:1px solid #2e4663;border-radius:9px}
code{color:#9ee5c8}a{color:#9ed5ff}table{border-collapse:collapse;width:100%;font-size:.87rem}td,th{border-bottom:1px solid #30445b;text-align:left;padding:8px 5px}td:not(:first-child),th:not(:first-child){text-align:right}
@media(max-width:450px){body{padding:10px}.card{padding:13px}.actions button{flex:1 1 140px}}
</style></head><body><main>
<h1>MicroMusic · MiniLPC8</h1>
<p class="sub">Новый формат без обратной совместимости • ATtiny13A 9,6 МГц • 8 ступеней LPC • 4 голосовых профиля • PWM PB1</p>
<section class="card"><div class="grid"><div><label for="voice">Реплика</label><select id="voice">
<option value="chego">Чего тебе нужно?</option><option value="otvechaesh">Что ж ты не отвечаешь?</option><option value="vinni">Сова! Открывай! Медведь пришёл!</option></select></div>
<div><label for="codec">Алгоритм воспроизведения</label><select id="codec">
<option value="native">New-only MiniLPC8 · AVR 364 Б</option>
<option value="full">Full 350 · старый эталон (только в плеере)</option>
<option value="lpx3">LPX3 · эталон качества (ПК)</option>
<option value="original">Оригинальная запись</option></select></div></div>
<div class="actions"><button id="play">▶ Слушать</button><button id="ab" class="secondary">⇄ Оригинал / выбранный</button><button id="stop" class="secondary">■ Стоп</button></div>
<canvas id="wave" width="800" height="150"></canvas>
<div class="grid" style="margin-top:12px"><div class="stat"><small>Использование Flash</small><b id="flash">—</b></div><div class="stat"><small>Код / сжатая речь</small><b id="size">—</b></div><div class="stat"><small>Частота аудио</small><b>7,5 кГц</b></div></div>
<div class="actions"><button class="secondary" id="verify">↻ Исполнить HEX в эмуляторе</button><button class="secondary" id="getHex">↓ Скачать HEX</button></div>
<p id="status">Выберите запись и нажмите «Слушать».</p>
<p><small>В режиме New-only AVR-прошивка исполняет только новый формат. Full 350 и LPX3 доступны исключительно как независимые эталоны в этом браузерном плеере.</small></p>
</section>
<section class="card"><b>Результат сборки</b><table><thead><tr><th>Фраза</th><th>Flash</th><th>Код</th><th>Речь</th></tr></thead><tbody>
<tr><td>Чего тебе нужно?</td><td>581 Б</td><td>364 Б</td><td>216 Б</td></tr>
<tr><td>Что ж ты не отвечаешь?</td><td>551 Б</td><td>364 Б</td><td>186 Б</td></tr>
<tr><td>Сова! Открывай!</td><td>887 Б</td><td>364 Б</td><td>522 Б</td></tr></tbody></table>
<p><small>Каждая прошивка включает 1 байт маркера конца потока. Цикловая AVR-проверка дала 0 расхождений с прежними оптимизированными речевыми данными, 0 пропущенных переполнений таймера.</small></p>
</section>
</main><script>
''' + core + r'''
const TRACKS=__TRACKS__;
const PROGRAMS=__PROGRAMS__;
const GOLD=__EXPECTED__;
const DATA=__MANIFEST__;
const $=x=>document.getElementById(x);
let ctx, node=null, second=null, current=null, liveData=[];
function bytesFromB64(s){let bin=atob(s);let b=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)b[i]=bin.charCodeAt(i);return b}
function pcmFromB64(s){let data=bytesFromB64(s),view=new DataView(data.buffer),out=new Float32Array(data.length/2);for(let i=0;i<out.length;i++)out[i]=view.getInt16(i*2,true)/32768;return out}
function samples(voice,mode){return pcmFromB64(TRACKS[voice][mode])}
function audioBuffer(pcm){let b=ctx.createBuffer(1,pcm.length,7500);b.copyToChannel(pcm,0);return b}
function rms(pcm){let acc=0;for(let i=0;i<pcm.length;i++)acc+=pcm[i]*pcm[i];return Math.sqrt(acc/pcm.length)}
function stop(){try{node?.stop()}catch{}try{second?.stop()}catch{}node=null;second=null;}
function draw(pcm){let c=$('wave'),g=c.getContext('2d');g.clearRect(0,0,c.width,c.height);g.strokeStyle='#314a67';g.beginPath();g.moveTo(0,75);g.lineTo(800,75);g.stroke();if(!pcm.length)return;g.strokeStyle='#81ccff';g.lineWidth=1.3;g.beginPath();const bin=Math.max(1,Math.ceil(pcm.length/800));for(let i=0;i<800;i++){let m=0;for(let j=i*bin;j<Math.min(pcm.length,(i+1)*bin);j++)if(Math.abs(pcm[j])>Math.abs(m))m=pcm[j];let y=75-m*65;if(!i)g.moveTo(0,y);else g.lineTo(i,y)}g.stroke()}
function details(){let v=$('voice').value,m=DATA[v];$('flash').textContent=`${m.flash_bytes} / 1024 Б`;$('size').textContent=`${m.code_bytes} / ${m.speech_bytes} Б`;draw(samples(v,$('codec').value));$('status').textContent='Готово к воспроизведению.'}
async function start(ab){stop();if(!ctx)ctx=new(window.AudioContext||window.webkitAudioContext)();await ctx.resume();let v=$('voice').value,mode=$('codec').value,p=samples(v,mode);if(!ab){node=ctx.createBufferSource();node.buffer=audioBuffer(p);node.connect(ctx.destination);node.start();$('status').textContent='Воспроизведение: '+$('codec').selectedOptions[0].text;}
else{let a=samples(v,'original');let gain=Math.min(2,Math.max(.1,rms(a)/Math.max(rms(p),.0001)));node=ctx.createBufferSource();node.buffer=audioBuffer(a);node.connect(ctx.destination);second=ctx.createBufferSource();second.buffer=audioBuffer(p);let gn=ctx.createGain();gn.gain.value=gain;second.connect(gn);gn.connect(ctx.destination);let t=ctx.currentTime+.04;node.start(t);second.start(t+a.length/7500+.25);$('status').textContent='Сначала оригинал, затем выбранный кодек. Громкость выровнена.';}}
$('play').onclick=()=>start(false).catch(e=>{$('status').textContent='Ошибка звука: '+e.message});
$('ab').onclick=()=>start(true).catch(e=>{$('status').textContent='Ошибка звука: '+e.message});
$('stop').onclick=()=>{stop();$('status').textContent='Остановлено.'};
$('codec').onchange=details;$('voice').onchange=details;
$('getHex').onclick=()=>{let name=$('voice').value,b=bytesFromB64(PROGRAMS[name]);let lines=[];for(let at=0;at<b.length;at+=16){let data=Array.from(b.subarray(at,at+16)),v=[data.length,at>>8,at&255,0,...data];v.push((256-v.reduce((x,y)=>x+y,0)%256)&255);lines.push(':'+v.map(x=>x.toString(16).padStart(2,'0').toUpperCase()).join(''))}lines.push(':00000001FF');const a=document.createElement('a'),blob=new Blob([lines.join('\n')+'\n'],{type:'text/plain'});a.href=URL.createObjectURL(blob);a.download=`MiniLPC8_${name}_newonly.hex`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),3000)};
$('verify').onclick=async()=>{let name=$('voice').value;let btn=$('verify');btn.disabled=true;stop();let expected=bytesFromB64(GOLD[name]),sim=new AVRCore(bytesFromB64(PROGRAMS[name]));let diffs=0,stalls=0,last=0;try{for(let i=0;i<expected.length;i++){let b=sim.takeSample();if(b!==expected[i])diffs++;if(i && sim.cycles-last>1290)stalls++;last=sim.cycles;if(i%2048===0){$('status').textContent=`AVR: ${i}/${expected.length} отсчётов...`;await new Promise(r=>setTimeout(r,0))}}$('status').textContent=`AVR: ${expected.length} отсчётов, расхождений ${diffs}, пропусков Timer0 ${sim.missedOverflows}, поздних отсчётов ${stalls}, ISR максимум ${sim.maxISR} тактов.`}catch(e){$('status').textContent='Ошибка AVR: '+e.message}finally{btn.disabled=false}}
details();
</script></body></html>'''
content=content.replace('__TRACKS__',json.dumps(WAVES,separators=(',',':')))
content=content.replace('__PROGRAMS__',json.dumps(FW,separators=(',',':')))
content=content.replace('__EXPECTED__',json.dumps(REF,separators=(',',':')))
content=content.replace('__MANIFEST__',(BASE/'manifest.json').read_text())
(BASE/'index.html').write_text(content,encoding='utf8')
print('HTML bytes',len(content.encode()))
