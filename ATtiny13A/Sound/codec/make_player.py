from pathlib import Path
import base64,json,html
root=Path(__file__).resolve().parent
ids=('chego','otvechaesh','vinni')
names={'chego':'Чего тебе нужно?','otvechaesh':'Что ж ты не отвечаешь?','vinni':'Сова! Открывай! Медведь пришёл!'}
payload={n:{'name':names[n],
    'pcm':base64.b64encode((root/n/'emulated.pcm').read_bytes()).decode(),
    'bin':base64.b64encode((root/n/'firmware.bin').read_bytes()).decode(),
    'hex':(root/n/'firmware.hex').read_text(),
    'flash':len((root/n/'firmware.bin').read_bytes()),
    'baselineFlash':len((root/n/'reference.bin').read_bytes()),
    'duration':len((root/n/'emulated.pcm').read_bytes())/7500} for n in ids}
core=(root/'avr_emulator.js').read_text()
output='''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MicroMusic · HQ3 Decoder Optimization</title><style>
:root{color-scheme:dark;font:16px/1.55 system-ui, sans-serif;background:#0f1724;color:#eef3f9}
*{box-sizing:border-box}body{max-width:870px;margin:0 auto;padding:20px 16px 60px}h1{font-size:clamp(24px,5vw,32px);line-height:1.15;margin:9px 0 12px}h2{font-size:19px;margin:6px 0}p{color:#adbed1}.small{font-size:13px;color:#a7bbcd}.pill{background:#1c3345;border:1px solid #49647b;border-radius:20px;padding:4px 10px;font-size:12px;display:inline-block}.card{border:1px solid #344960;background:#172537;border-radius:15px;padding:18px;margin:14px 0}.fields{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{color:#b5d0eb;font-size:13px;display:block;margin-bottom:5px}select,button{font:inherit;border-radius:9px;padding:11px 12px}select{width:100%;color:#eaf6ff;background:#111f30;border:1px solid #4d6c87}button{border:1px solid #57728b;background:#293e56;color:#edf5ff;cursor:pointer}button.primary{background:#7bc5ff;color:#102034;border-color:#7bc5ff;font-weight:750}button:disabled{opacity:.5;cursor:default}.buttons{display:flex;flex-wrap:wrap;gap:9px;margin-top:13px}canvas{display:block;width:100%;height:130px;background:#091321;border:1px solid #314359;border-radius:10px}.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}.stat{background:#102033;border:1px solid #324a63;padding:10px;border-radius:9px}.stat strong{font-size:20px;display:block}.stat span{font-size:12px;color:#aec1d5}#status{color:#b8e7fb;min-height:30px;white-space:pre-wrap;font-size:14px}code{color:#d6f0fb}@media(max-width:580px){.fields{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}</style></head><body>
<span class="pill">ATtiny13A · 9,6 МГц · PWM PB1/OC0B</span>
<h1>MicroMusic · MiniLPC-HQ3</h1>
<p>Оптимизация декодера без изменения формата речи. Код уменьшен с <b>406 до 388 байт</b>, обработчик PWM — с <b>28 до 19 тактов</b>. На трёх записях звук совпадает с предыдущей прошивкой отсчёт в отсчёт.</p>
<section class="card">
<div class="fields"><div><label for="clip">Пример речи</label><select id="clip">
<option value="chego">Чего тебе нужно?</option><option value="otvechaesh">Что ж ты не отвечаешь?</option><option value="vinni">Сова! Открывай! Медведь пришёл!</option></select></div>
<div><label for="variant">Воспроизведение</label><select id="variant"><option value="new">Оптимизированный AVR (388 Б)</option><option value="old">Прежний AVR (406 Б) — звук идентичен</option></select></div></div>
<div class="stats"><div class="stat"><strong id="flash">—</strong><span>Байт Flash</span></div><div class="stat"><strong>388 Б</strong><span>Машинный код</span></div><div class="stat"><strong id="duration">—</strong><span>Длительность</span></div></div>
<div class="buttons"><button id="play" class="primary">▶ Слушать</button><button id="stop">■ Стоп</button><button id="verify">↻ Исполнить HEX и сверить PCM</button></div>
<p id="status">Выберите запись и нажмите «Слушать».</p><canvas id="wave" width="860" height="130" aria-label="Форма звукового сигнала"></canvas>
<div class="buttons"><button id="downloadHex">↓ HEX</button><button id="downloadWav">↓ WAV</button></div>
</section><section class="card"><h2>Что проверяет эмулятор?</h2><p>По нажатию кнопки он исполняет инструкции AVR из встроенного двоичного образа, обрабатывает Timer0 и OCR0B, затем сравнивает каждый PWM-отсчёт с сохранённой контрольной последовательностью. Выполнение происходит порциями, чтобы на телефоне интерфейс не зависал.</p><p class="small">Это программное моделирование ATtiny13A, а не испытание на физическом чипе. Данные речи предназначены для частного исследования; не публикуйте производные записи без прав.</p></section>
<script>
'''+core+'''\n</script><script>
const DATA='''+json.dumps(payload,ensure_ascii=False,separators=(',',':'))+''';
const $=s=>document.getElementById(s);let ctx=null,active=null,buffer=null,verifying=false;const SR=7500;
function bytes64(s){const raw=atob(s),a=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)a[i]=raw.charCodeAt(i);return a}
function getCurrent(){return DATA[$('clip').value]}
function update(){const d=getCurrent();$('flash').textContent=$('variant').value==='new'?d.flash:d.baselineFlash;$('duration').textContent=d.duration.toFixed(2)+' с';draw(bytes64(d.pcm));}
function draw(p){const cv=$('wave'),g=cv.getContext('2d');g.clearRect(0,0,cv.width,cv.height);g.fillStyle='#091321';g.fillRect(0,0,cv.width,cv.height);g.strokeStyle='#2d465e';g.beginPath();g.moveTo(0,cv.height/2);g.lineTo(cv.width,cv.height/2);g.stroke();g.strokeStyle='#79c5ff';g.lineWidth=1.6;g.beginPath();for(let x=0;x<cv.width;x++){let i=Math.floor(x*(p.length-1)/cv.width),v=(p[i]-128)/128,y=cv.height/2-v*cv.height*.45;if(x===0)g.moveTo(x,y);else g.lineTo(x,y)}g.stroke()}
function stop(){if(active){try{active.stop()}catch(e){}active.disconnect();active=null}}
async function play(){try{stop();ctx=ctx||new (window.AudioContext||window.webkitAudioContext)();await ctx.resume();const d=getCurrent(),bytes=bytes64(d.pcm),b=ctx.createBuffer(1,bytes.length,SR),a=b.getChannelData(0);for(let i=0;i<bytes.length;i++)a[i]=(bytes[i]-128)/128;const node=ctx.createBufferSource();node.buffer=b;const low=ctx.createBiquadFilter();low.type='lowpass';low.frequency.value=3200;node.connect(low);low.connect(ctx.destination);active=node;node.onended=()=>{if(active===node)active=null};node.start();$('status').textContent='Воспроизводится звук AVR · '+d.duration.toFixed(2)+' с. Оба варианта дают одинаковый PCM.'}catch(e){$('status').textContent='Ошибка аудио: '+e.message}}
function makeWav(p){const b=new ArrayBuffer(44+p.length*2),v=new DataView(b);let pos=0;for(const ch of 'RIFF')v.setUint8(pos++,ch.charCodeAt(0));v.setUint32(4,b.byteLength-8,true);pos=8;for(const ch of 'WAVEfmt ')v.setUint8(pos++,ch.charCodeAt(0));v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,SR,true);v.setUint32(28,SR*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);for(let i=0;i<4;i++)v.setUint8(36+i,'data'.charCodeAt(i));v.setUint32(40,p.length*2,true);for(let i=0;i<p.length;i++)v.setInt16(44+i*2,(p[i]-128)*256,true);return new Uint8Array(b)}
function download(bytes,name,type){const a=document.createElement('a'),url=URL.createObjectURL(new Blob([bytes],{type}));a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500)}
function verify(){if(verifying)return;verifying=true;$('verify').disabled=true;const key=$('clip').value,d=getCurrent(),expected=bytes64(d.pcm),core=new AVRCore(bytes64(d.bin));let count=0,errors=0,first=-1;function step(){try{const max=Math.min(count+80,expected.length);for(;count<max;count++){const v=core.takeSample();if(v!==expected[count]){errors++;if(first<0)first=count}}$('status').textContent='Проверка HEX: '+count+' / '+expected.length+' отсчётов';if(count<expected.length){setTimeout(step,0);return} $('status').textContent=key+': '+errors+' расхождений из '+count+' отсчётов. IRQ: '+core.irqCount+', пропусков Timer0: '+core.missedOverflows+', максимальный ISR: '+core.maxISR+' тактов.';}catch(e){$('status').textContent='Ошибка эмуляции: '+e.message;verifying=false;$('verify').disabled=false}finally{if(count>=expected.length){verifying=false;$('verify').disabled=false}}}step()}
$('clip').addEventListener('change',()=>{stop();update()});$('variant').addEventListener('change',update);$('play').addEventListener('click',play);$('stop').addEventListener('click',()=>{stop();$('status').textContent='Остановлено.'});$('verify').addEventListener('click',verify);$('downloadHex').addEventListener('click',()=>{let d=getCurrent();download(d.hex,$('clip').value+'-decoder-opt.hex','text/plain')});$('downloadWav').addEventListener('click',()=>download(makeWav(bytes64(getCurrent().pcm)),$('clip').value+'-decoder-opt.wav','audio/wav'));update();
</script></body></html>'''
(root/'index.html').write_text(output)
print('HTML',len(output),'bytes')
