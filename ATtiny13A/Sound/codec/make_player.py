#!/usr/bin/env python3
"""Create a standalone offline A/B listener with a real cycle-counting AVR verifier."""
from pathlib import Path
import base64,json,numpy as np,soundfile as sf
from pystoi import stoi
from quality import Compare
ROOT=Path(__file__).resolve().parent
ROOT.joinpath('index.html')
LABELS={'chego':'Чего тебе нужно?','otvechaesh':'Что ж ты не отвечаешь?','vinni':'Сова! Открывай! Медведь пришёл!'}
clips={}
manifest=json.loads((ROOT/'manifest.json').read_text())
for n in LABELS:
 original,sr=sf.read(ROOT/'references'/n/'original.wav');lp,sr2=sf.read(ROOT/'references'/n/'lpx3.wav');assert sr==sr2==7500
 baseline=np.frombuffer((ROOT/'samples'/n/'baseline_pcm.raw').read_bytes(),np.uint8)
 hq=np.frombuffer((ROOT/'samples'/n/'avr_pcm.raw').read_bytes(),np.uint8)
 assert len(original)==len(hq)==len(baseline)==len(lp)
 def encf32_16(x):return base64.b64encode(np.round(np.clip(x,-1,1)*32767).astype('<i2').tobytes()).decode()
 clips[n]={
  'title':LABELS[n],
  'duration':len(original)/7500,
  'pcm':{
   'original':{'fmt':'i16','bytes':encf32_16(original)},
   'lpx3':{'fmt':'i16','bytes':encf32_16(lp)},
   'old':{'fmt':'u8','bytes':base64.b64encode(baseline.tobytes()).decode()},
   'hq':{'fmt':'u8','bytes':base64.b64encode(hq.tobytes()).decode()},
  },
  'hex':(ROOT/'samples'/n/'firmware.hex').read_text(),
  'asm':(ROOT/'samples'/n/'firmware.S').read_text(),
  'info':manifest[n],
  'metrics':{
    'old':float(stoi(original,(baseline.astype(np.float32)-128)/128,7500)),
    'hq':float(stoi(original,(hq.astype(np.float32)-128)/128,7500)),
    'lpx3':float(stoi(original,lp,7500)),
  }
 }

engine=(ROOT/'avr_emulator.js').read_text().replace("if(typeof module!=='undefined'&&module.exports)module.exports={AVRCore};",'')
source=r'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MicroMusic · MiniLPC-HQ · ATtiny13A</title>
<style>
:root{color-scheme:dark;--bg:#0a101b;--panel:#151f31;--line:#33455c;--tx:#ecf3ff;--muted:#aabbd2;--cyan:#6fbaff;--green:#69dfb1}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}main{max-width:1040px;padding:22px 14px 55px;margin:auto}h1{font-size:clamp(25px,5vw,38px);line-height:1.17;margin:0 0 10px;letter-spacing:-.5px}.sub{color:var(--muted);margin:0 0 22px}.pill{display:inline-flex;border:1px solid #40607e;padding:5px 9px;border-radius:100px;margin-right:6px;font-size:12px;color:#b9dcff}.card{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:17px;margin:14px 0}label{display:block;font-size:13px;color:var(--muted);font-weight:650;margin-bottom:5px}select{width:100%;padding:12px 14px;border:1px solid #55708e;border-radius:10px;background:#10192a;color:var(--tx);font:inherit} .selects{display:grid;grid-template-columns:1fr 1fr;gap:12px}.buttons{display:flex;gap:9px;flex-wrap:wrap;margin-top:15px}button{cursor:pointer;padding:11px 14px;background:#263b57;color:#ecf3ff;border:1px solid #466486;border-radius:10px;font:inherit;font-weight:650}button.main{background:#5cafff;color:#091323;border:0}button:disabled{opacity:.5;cursor:default}button:hover:not(:disabled){filter:brightness(1.1)} .metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}.metric{border:1px solid #33465f;border-radius:11px;padding:12px 8px}.metric b{font-size:21px;display:block;line-height:1.3}.metric small{color:var(--muted)}canvas{width:100%;height:135px;background:#0c1626;border-radius:11px;border:1px solid var(--line)}pre{white-space:pre-wrap;word-break:break-word;color:#b9d7ff;font-size:12px}.status{min-height:22px;color:var(--green);white-space:pre-wrap}.fine{font-size:12px;color:var(--muted)}h2{font-size:20px;margin:0 0 12px}h3{font-size:16px;margin:0 0 8px}a{color:var(--cyan)} .legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted)} .legend span:first-child{color:#85caff}@media(max-width:650px){.selects{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}button{flex-grow:1}main{padding-top:16px}}
</style></head><body><main>
<div><span class="pill">ATtiny13A · 1 КБ Flash</span><span class="pill">MiniLPC-HQ · 8 LPC-ступеней</span></div>
<h1>MicroMusic · MiniLPC-HQ</h1><p class="sub">Эксперимент по приближению к STOI 0,85. Кадры 8,5 / 17 / 34 мс, индивидуальное распределение битов и автоматическая подстройка. Для AVR играет именно результат выполнения HEX; в обычном режиме используется уже проверенный PCM-кэш.</p>
<section class="card"><div class="selects"><div><label for="clip">Пример голоса</label><select id="clip"><option value="chego">Чего тебе нужно?</option><option value="otvechaesh">Что ж ты не отвечаешь?</option><option value="vinni">Сова! Открывай! Медведь пришёл!</option></select></div><div><label for="variant">Источник звука / кодек</label><select id="variant"><option value="hq">MiniLPC-HQ · ATtiny13A</option><option value="old">MiniLPC VBR2 · прежний HEX</option><option value="lpx3">LPX3 · эталон (WAV)</option><option value="original">Оригинальная запись</option></select></div></div>
<div class="buttons"><button class="main" id="play">▶ Слушать</button><button id="ab">⇄ Оригинал → результат</button><button id="stop">■ Стоп</button><button id="verify">↻ Выполнить HEX в эмуляторе</button></div><div class="buttons"><button id="wav">↓ WAV</button><button id="hex">↓ HEX</button><button id="asm">↓ ASM</button></div><p id="status" class="status">Готово. Нажмите «Слушать» для воспроизведения.</p></section>
<section class="card"><h2>Размер и качество</h2><div class="metrics"><div class="metric"><b id="flash">—</b><small>Flash, код + речь</small></div><div class="metric"><b id="speech">—</b><small>Речевые данные</small></div><div class="metric"><b id="stoi">—</b><small>STOI выбранного звука</small></div><div class="metric"><b id="frame">—</b><small>Короткие кадры 8,5 мс</small></div></div><div style="margin-top:13px"><canvas id="wave" width="900" height="140"></canvas></div><div class="legend"><span>Синий — выбранный аудиосигнал</span><span>7 500 отсчётов/с · PWM 37 500 Гц</span></div></section>
<section class="card"><h2>Проверка реальной прошивки</h2><p>Кнопка <b>«Выполнить HEX в эмуляторе»</b> заново исполняет машинные инструкции AVR с подсчётом тактов, проверяет Timer0, обновления OCR0B, каждую выходную выборку и затем воспроизводит результат. Эта операция может быть медленной на телефоне.</p><pre id="verifyStats">Данные проверки появятся после запуска эмулятора.</pre></section>
<section class="card"><h2>Как устроен новый формат</h2><p>Никакой поддержки старых форматов в прошивке: одна новая последовательность кадров длиной 64, 128 или 256 отсчётов. Каждый кадр хранит период F₀, громкость и номер одного из четырёх импульсных профилей; LPC-коэффициенты передаются целиком, частично или повторяются с предыдущего кадра.</p><p class="fine">Показатель STOI измеряет преимущественно разборчивость. Оптимизация выполнялась на самих этих фразах, поэтому результаты не являются оценкой качества на неизвестной речи. Здесь LPX3 и оригинал представлены заранее декодированными эталонными WAV, а не AVR-прошивками. Исходные фрагменты — для частных экспериментов.</p></section>
</main><script>
/* CORE */
/* DATA */
const rate=7500;const get=id=>document.getElementById(id);
let audio=null,active=[],verifiedBusy=false;
function decodeB64(s){const src=atob(s),out=new Uint8Array(src.length);for(let i=0;i<src.length;i++)out[i]=src.charCodeAt(i);return out}
function samples(name,mode){const item=DATA[name].pcm[mode],b=decodeB64(item.bytes);let result;
 if(item.fmt==='u8'){result=new Float32Array(b.length);for(let i=0;i<b.length;i++)result[i]=(b[i]-128)/128}
 else{const view=new DataView(b.buffer,b.byteOffset,b.byteLength);result=new Float32Array(b.length/2);for(let i=0;i<result.length;i++)result[i]=view.getInt16(i*2,true)/32768}
 return result}
function setStatus(message,bad=false){let el=get('status');el.textContent=message;el.style.color=bad?'#ff9e94':'#69dfb1'}
function pretty(n){return Number(n).toLocaleString('ru-RU')}
function draw(){let w=samples(get('clip').value,get('variant').value);let canvas=get('wave'),c=canvas.getContext('2d'),width=canvas.width,height=canvas.height;c.clearRect(0,0,width,height);c.fillStyle='#0c1626';c.fillRect(0,0,width,height);c.strokeStyle='#29405e';c.beginPath();c.moveTo(0,height/2);c.lineTo(width,height/2);c.stroke();c.strokeStyle='#7bc5ff';c.lineWidth=1.5;c.beginPath();let step=Math.max(1,Math.floor(w.length/width));for(let i=0;i<width;i++){let a=i*step,lo=1,hi=-1;for(let j=a;j<Math.min(a+step,w.length);j++){lo=Math.min(lo,w[j]);hi=Math.max(hi,w[j])}let x=i,y0=height/2-lo*height*.43,y1=height/2-hi*height*.43;c.moveTo(x,y0);c.lineTo(x,y1)}c.stroke()}
function summary(){const name=get('clip').value,mode=get('variant').value,info=DATA[name].info;get('flash').textContent=pretty(info.flash_bytes)+' Б';get('speech').textContent=pretty(info.speech_bytes)+' Б';get('frame').textContent=info.short_64+'/'+info.frames;get('stoi').textContent=mode==='original'?'1,000':DATA[name].metrics[mode].toFixed(3).replace('.',',');draw()}
function stop(){for(let x of active)try{x.stop()}catch(e){}active=[];setStatus('Воспроизведение остановлено.')}
async function ensureAudio(){if(!audio)audio=new(window.AudioContext||window.webkitAudioContext)();await audio.resume();return audio}
async function playTracks(list){if(verifiedBusy)return;try{const a=await ensureAudio();for(let x of active)try{x.stop()}catch(e){}active=[];let tm=a.currentTime+0.04;
 for(let [name,mode]of list){const sound=samples(name,mode),b=a.createBuffer(1,sound.length,rate);b.getChannelData(0).set(sound);let rms=0,peak=0;for(let v of sound){rms+=v*v;peak=Math.max(peak,Math.abs(v))}rms=Math.sqrt(rms/Math.max(1,sound.length));let gain=Math.min(.85/Math.max(.01,peak),.19/Math.max(.01,rms));let src=a.createBufferSource(),vol=a.createGain();vol.gain.value=gain;src.buffer=b;src.connect(vol).connect(a.destination);src.start(tm);active.push(src);tm+=b.duration+.25}
 setStatus('Воспроизведение: '+list.map(e=>e[1]).join(' → '));}catch(e){setStatus('Ошибка воспроизведения: '+e.message,true)}}
function nameFor(){return get('clip').value};function modeFor(){return get('variant').value}
function save(filename,blob,type){const obj=URL.createObjectURL(new Blob([blob],{type:type||'application/octet-stream'}));const a=document.createElement('a');a.href=obj;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(obj),2000)}
function packWav(y){let b=new ArrayBuffer(44+y.length*2),v=new DataView(b);const write=(o,s)=>{for(let i=0;i<s.length;i++)v.setUint8(o+i,s.charCodeAt(i))};write(0,'RIFF');v.setUint32(4,b.byteLength-8,true);write(8,'WAVE');write(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,rate,true);v.setUint32(28,rate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);write(36,'data');v.setUint32(40,y.length*2,true);for(let i=0;i<y.length;i++)v.setInt16(44+i*2,Math.round(Math.max(-1,Math.min(1,y[i]))*32767),true);return b}
get('clip').onchange=summary;get('variant').onchange=summary;
get('play').onclick=()=>playTracks([[nameFor(),modeFor()]]);
get('ab').onclick=()=>playTracks([[nameFor(),'original'],[nameFor(),modeFor()]]);
get('stop').onclick=stop;
get('wav').onclick=()=>save(nameFor()+'_'+modeFor()+'.wav',packWav(samples(nameFor(),modeFor())),'audio/wav');
get('hex').onclick=()=>save(nameFor()+'_MiniLPC_HQ.hex',DATA[nameFor()].hex,'text/plain');
get('asm').onclick=()=>save(nameFor()+'_MiniLPC_HQ.S',DATA[nameFor()].asm,'text/plain');
function pause(){return new Promise(ok=>setTimeout(ok,0))}
get('verify').onclick=async()=>{if(verifiedBusy)return;await ensureAudio();verifiedBusy=true;get('verify').disabled=true;const name=nameFor(),data=DATA[name],truth=decodeB64(data.pcm.hq.bytes),core=AVRCore.fromHex(data.hex);const out=new Uint8Array(truth.length);
 let diff=0,late=0,last=0;get('verifyStats').textContent='Начинаю исполнение HEX...';
 try{for(let i=0;i<truth.length;i++){out[i]=core.takeSample();if(out[i]!==truth[i])diff++;if(i>0&&core.cycles-last>1300)late++;last=core.cycles;
 if((i%160)===0){get('verifyStats').textContent='Выполнено '+pretty(i)+' из '+pretty(truth.length)+' аудиоотсчётов...';await pause()}}
 const report=['Flash: '+data.info.flash_bytes+'/1024 Б','PWM-отсчёты: '+truth.length,'Расхождения с проверенным WAV: '+diff,'Пропуски Timer0: '+core.missedOverflows,'Запоздавшие отсчёты: '+late,'Максимальный ISR: '+core.maxISR+' тактов','CPU: '+pretty(core.cycles)+' тактов'];get('verifyStats').textContent=report.join('\n');if(!diff&&!late&&!core.missedOverflows){setStatus('HEX успешно проверен. Звук совпадает с контрольным.');verifiedBusy=false;await playTracks([[name,'hq']])}else setStatus('Проверка обнаружила ошибки!',true)
 }catch(e){get('verifyStats').textContent='Ошибка эмуляции: '+e.message;setStatus('Не удалось выполнить HEX: '+e.message,true)}finally{verifiedBusy=false;get('verify').disabled=false}}
summary();
</script></body></html>'''
source=source.replace('/* CORE */',engine).replace('/* DATA */','const DATA='+json.dumps(clips,ensure_ascii=False,separators=(',',':'))+';')
(ROOT/'index.html').write_text(source)
print('Created',ROOT/'index.html',(ROOT/'index.html').stat().st_size,'bytes',flush=True)
