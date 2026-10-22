#!/usr/bin/env python3
"""Build offline HTML comparison with runnable JavaScript AVR emulator.
Sound buttons deliberately use WebAudio buffers (not huge data:audio URLs).
"""
from pathlib import Path
import base64,json,math,html
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parent
NAMES=[('xtuj-ntt','Чего тебе нужно?','8-ступенчатый TinyLPC, обновлённая F₀'),('ne-otv','Что ж ты не отвечаешь?','8-ступенчатый TinyLPC, подстройка коэффициентов'),('vinni','Сова! Открывай! Медведь пришёл!','7-ступенчатый AutoLPC2 — длинная реплика')]


def pcm16_audio(path):
 x,sr=sf.read(path,always_2d=True,dtype='float32');x=x.mean(axis=1)
 if sr!=7500:
  g=math.gcd(sr,7500);x=resample_poly(x,7500//g,sr//g)
 x=x.astype('float64')
 # A/B loudness matching: don't trade amplitude differences for spectral differences.
 # Fix RMS at .19 and peak below .88, equal playback loudness.
 peak=float(np.max(abs(x))) if len(x) else 0
 rms=float(np.sqrt(np.mean(x*x))) if len(x) else 0
 if rms>1e-8:x*=min(.19/rms,.88/max(peak,1e-8))
 return np.clip(np.rint(x*32767),-32768,32767).astype('<i2')

def pcm16_from_raw(path):
 raw=np.fromfile(path,dtype=np.uint8)
 y=(raw.astype(np.float64)-128)/128
 pk=float(np.max(abs(y)));rms=float(np.sqrt(np.mean(y*y)))
 if rms>1e-8:y*=min(.19/rms,.88/max(pk,1e-8))
 return np.clip(np.rint(y*32767),-32768,32767).astype('<i2')

payload={}; cards=[]
for idx,(name,title,desc) in enumerate(NAMES):
 p=ROOT/name
 rep=json.loads((p/'report.json').read_text())
 if name=='vinni':
  rom=(p/'tinylpc.hex').read_text(); raw=(p/'emu_pwm_u8.raw').read_bytes()
 else:
  rom=(p/'firmware/tinylpc.hex').read_text(); raw=(p/'firmware/emu_pwm_u8.raw').read_bytes()
 audios={
  'source':pcm16_audio(p/'original.wav'),
  'lpc2':pcm16_audio(p/'lpc2_voice_v2.wav'),
  'avr':pcm16_from_raw(p/'emu_pwm_u8.raw' if name=='vinni' else p/'firmware/emu_pwm_u8.raw')
 }
 labels={'source':'Исходная запись','lpc2':'Полный LPC2 '+('Improved v1' if name=='vinni' else 'Voice v2'), 'avr':'ATtiny13A — реальный HEX'}
 entries=[]
 for variant,a in audios.items():
  key=f'{name}_{variant}'
  payload[key]={'name':name,'variant':variant,'label':labels[variant], 'rate':7500,'pcm16':base64.b64encode(a.tobytes()).decode('ascii'),'duration':round(len(a)/7500,3)}
  entries.append(f'<div class="track"><button class="play" data-track="{key}" title="Воспроизвести">▶ <span>Слушать</span></button><div class="track-caption"><b>{labels[variant]}</b><small>{len(a)/7500:.2f} с</small></div><span class="kind">{"AVR" if variant=="avr" else "Ref" if variant=="source" else "LPC2"}</span></div>')
 payload[name+'_firmware']={'hex':rom,'raw':base64.b64encode(raw).decode('ascii'),'samples':len(raw),'flash':rep['flash_bytes'],'voice':rep['voice_bytes']}
 meta=f'{rep["flash_bytes"]} / 1024 Б Flash · {rep["voice_bytes"]} Б речевых данных · {len(raw)/7500:.2f} с'
 met=''
 if rep.get('metrics'):
  m=rep['metrics'];met=f'STOI {m["stoi"]:.3f} · спектральная ошибка {m["mel_original"]:.3f} · скачков ≥48: {m["clicks_48"]}'
 else: met='Проверенная ранее 7-ступенчатая версия для длинной реплики'
 cards.append(f'''<section class="clip"><div class="clip-header"><h2>{html.escape(title)}</h2><div class="micro">{html.escape(desc)}</div></div><p class="sub">{meta}</p>{''.join(entries)}<div class="footer"><button class="verify" data-name="{name}"> <span>⚙</span> Проверить HEX в эмуляторе</button><span id="verify-{name}" class="verify-result">{met}</span></div></section>''')
jsdata=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
source=(ROOT/'tools/avr_emulator.js').read_text()
# No Node code required in browser; browser global lexical AVRCore class is accessible in the next script.
page='''<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"/><title>MicroMusic / ATtiny13A + LPC2 Voice v2</title>
<style>
:root{color-scheme:dark;background:#0b1220;color:#ecf4ff;font:15px/1.5 system-ui,-apple-system,Roboto,sans-serif}*{box-sizing:border-box}
body{margin:auto;max-width:930px;padding:20px 15px 50px}h1{font-size:clamp(26px,5vw,38px);letter-spacing:-.035em;margin:0 0 4px}h2{font-size:20px;line-height:1.3;margin:0 0 3px}p{color:#b6c8df}
.preamble{font-size:15px;max-width:750px;margin:4px 0 16px} .eyebrow{color:#8bb9e6;letter-spacing:.15em;text-transform:uppercase;font-size:11px;font-weight:800;margin-bottom:7px}
.sticky{background:#1c2b40;border:1px solid #38516f;border-radius:14px;position:sticky;top:8px;z-index:5;padding:12px 15px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;box-shadow:0 8px 32px #030916b0}
button{font:inherit;cursor:pointer;font-weight:750;border:0;border-radius:10px;background:#7ac4ff;color:#0b1423;padding:11px 12px;min-height:44px;touch-action:manipulation}
button:hover{filter:brightness(1.06)}button:disabled{opacity:.5;cursor:progress}
#stop{background:#3d536c;color:#fff}#status{font-size:13px;flex:1;min-width:180px}#volume{width:95px;accent-color:#7ac4ff}
#scope{width:100%;height:112px;display:block;background:#111b2e;border-radius:12px;margin:13px 0 25px;border:1px solid #2c425f}
.clip{background:#192638;border:1px solid #344761;border-radius:15px;padding:17px;margin-bottom:20px}
.clip-header{display:flex;justify-content:space-between;gap:15px;align-items:start;flex-wrap:wrap}.micro{color:#a5b9d0;font-size:12px;max-width:270px}.sub{font-size:12px;color:#9cb1c9;margin:8px 0 12px}
.track{padding:12px 0;border-top:1px solid #32445b;display:flex;align-items:center;gap:14px;min-height:64px}.track-caption{flex:1;display:flex;flex-direction:column;gap:2px;min-width:0}.track-caption small{font-size:12px;color:#98abc4}
.kind{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#aec2da;border:1px solid #395372;border-radius:5px;padding:4px 6px}
.play{width:117px}.play.active{background:#ffe0a8}.footer{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:10px;padding-top:12px;border-top:1px solid #32445b}.verify{background:#354f70;color:#eaf5ff;font-size:12px;padding:10px}.verify-result{color:#a6bed9;font-size:12px;flex:1;min-width:210px}
.hint{border-top:1px solid #32445b;margin-top:20px;padding-top:16px;color:#a6b8d0;font-size:13px}code{font-size:12px;color:#d1e8ff}a{color:#8fd0ff}
@media(max-width:480px){body{padding:12px 10px}.clip{padding:12px}.track{gap:8px}.play{width:102px;font-size:13px;padding:9px}.sticky{padding:10px}}
</style></head><body>
<div class="eyebrow">MICROMUSIC / ATtiny13A / Speech Lab</div>
<h1>ATtiny13A + LPC2 Voice v2</h1>
<p class="preamble">Сравнение оригинального голоса, полного LPC2 Voice v2 и реальной прошивки ATtiny13A. Нажми «Слушать». Если переключиться на другую версию той же реплики, она продолжится с той же позиции — удобно сравнивать тембр.</p>
<div class="sticky"><button id="stop" disabled>■ Стоп</button><label style="font-size:12px">Громкость <input type="range" id="volume" min="0" max="1.5" value="0.9" step="0.05"></label><div id="status" role="status" aria-live="polite">Готов. Аудио запускается по нажатию.</div></div>
<canvas id="scope" width="850" height="112" aria-label="Осциллограмма"></canvas>
__SECTIONS__
<div class="hint"><b>Как устроен тест.</b> Звук кнопок воспроизводится через Web Audio API, без встроенных ссылок <code>data:audio</code>. Кнопка «Проверить HEX» заново исполняет инструкции AVR в браузере и сравнивает каждый сэмпл PWM с контрольной записью. MCU 9,6 МГц, PWM 37,5 кГц на PB1/OC0B, частота речи 7,5 кГц. Сначала подключай RC-фильтр и усилитель, динамик напрямую к PB1 не подключай. Исходные аудиофрагменты встроены для частного исследования: не публикуй страницу с ними в открытом репозитории без прав.</div>
<script>
__EMU__
</script>
<script>
'use strict';
const DATA=__DATA__;
const $=id=>document.getElementById(id), status=$('status'), scope=$('scope'), g=scope.getContext('2d');
let ctx=null, src=null, gain=null, playing=null, started=0, cursor=0, viewId=null, trackSamples=null, playToken=0;
const PCM=new Map();
function decode16(key){if(PCM.has(key))return PCM.get(key);const b=atob(DATA[key].pcm16),n=b.length>>1,a=new Float32Array(n);for(let i=0,j=0;i<n;i++,j+=2){const v=b.charCodeAt(j)|(b.charCodeAt(j+1)<<8);a[i]=(v<32768?v:v-65536)/32768;}PCM.set(key,a);return a}
function write(s){status.textContent=s}
function clearBtns(){document.querySelectorAll('.play').forEach(b=>{b.classList.remove('active');b.innerHTML='▶ <span>Слушать</span>'});$('stop').disabled=true}
function stop(full=true){playToken++;if(viewId!==null){cancelAnimationFrame(viewId);viewId=null}if(src){const was=src;src=null;was.onended=null;try{was.stop()}catch(e){}try{was.disconnect()}catch(e){}}playing=null;trackSamples=null;clearBtns();if(full){cursor=0;write('Остановлено');draw(null)}}
function draw(a,seconds=0){const W=scope.width,H=scope.height;g.fillStyle='#101b2d';g.fillRect(0,0,W,H);g.strokeStyle='#29415e';g.beginPath();g.moveTo(0,H/2);g.lineTo(W,H/2);g.stroke();if(!a?.length)return;const width=Math.min(800,a.length),pos=Math.max(0,Math.min(a.length-width,Math.floor(seconds*7500)-width/2));g.beginPath();g.strokeStyle='#80caff';g.lineWidth=1.5;for(let x=0;x<W;x++){const i=pos+Math.min(width-1,Math.floor(x*width/W));const y=H/2-a[i]*H*.45;if(x===0)g.moveTo(x,y);else g.lineTo(x,y)}g.stroke()}
$('stop').addEventListener('click',()=>stop());
$('volume').addEventListener('input',()=>{if(gain&&ctx)gain.gain.setTargetAtTime(+$('volume').value,ctx.currentTime,.014)});
async function play(key,button){
 if(playing===key){stop();return}
 const group=DATA[key].name;
 let offset=0;
 if(src && playing && DATA[playing].name===group && ctx){offset=Math.max(0,ctx.currentTime-started)}
 stop(false);
 const token=++playToken;
 const item=DATA[key];
 button.classList.add('active');button.textContent='Подготовка…';
 try{
  const Ctor=window.AudioContext||window.webkitAudioContext;
  if(!Ctor)throw Error('В этом браузере нет Web Audio API');
  if(!ctx)ctx=new Ctor();
  const resume=ctx.resume(); // resumes within the actual user click gesture
  const samples=decode16(key);
  const buffer=ctx.createBuffer(1,samples.length,item.rate);buffer.getChannelData(0).set(samples);
  await resume;
  if(token!==playToken)return;
  if(ctx.state!=='running')throw Error('AudioContext: '+ctx.state);
  offset=Math.min(offset,Math.max(0,item.duration-0.02));
  gain=ctx.createGain();gain.gain.setValueAtTime(0,ctx.currentTime);gain.gain.linearRampToValueAtTime(+$('volume').value,ctx.currentTime+.009);
  const remaining=item.duration-offset;
  gain.gain.setValueAtTime(+$('volume').value,ctx.currentTime+Math.max(.010,remaining-.012));gain.gain.linearRampToValueAtTime(0,ctx.currentTime+remaining);
  const s=ctx.createBufferSource();s.buffer=buffer;s.connect(gain).connect(ctx.destination);src=s;
  playing=key;started=ctx.currentTime-offset;cursor=offset;trackSamples=samples;
  s.onended=()=>{if(src===s)stop()};
  s.start(0,offset);$('stop').disabled=false;button.innerHTML='■ <span>Стоп</span>';
  write(item.label+' · '+group+' · '+item.duration.toFixed(2)+' с');
  function animate(){if(playing!==key)return;const elapsed=ctx.currentTime-started;draw(samples,elapsed);viewId=requestAnimationFrame(animate)}animate();
 }catch(err){console.error(err);stop();write('Ошибка звука: '+(err.message||String(err))+' — открой HTML в Chrome или используй WAV из архива')}
}
document.querySelectorAll('.play').forEach(b=>b.addEventListener('click',()=>play(b.dataset.track,b)));
function yieldNow(){return new Promise(resolve=>setTimeout(resolve,0))}
async function verifyFirmware(name,button){
 const el=$('verify-'+name),meta=DATA[name+'_firmware'];button.disabled=true;let out;
 try{
  const emulator=AVRCore.fromHex(meta.hex);
  const bin=atob(meta.raw);
  let bad=0,first=-1,large=0,maxGap=0,last=0;
  for(let i=0;i<meta.samples;i++){
   const value=emulator.takeSample();
   if(value!==bin.charCodeAt(i)){bad++;if(first===-1)first=i}
   if(i>0){const gap=emulator.cycles-last;maxGap=Math.max(maxGap,gap);if(gap>1290)large++}
   last=emulator.cycles;
   if((i+1)%1024===0){el.textContent='Проверка '+(100*(i+1)/meta.samples).toFixed(0)+'%';await yieldNow()}
  }
  const ok=(bad===0&&emulator.missedOverflows===0&&emulator.maxISR<256&&large===0&&emulator.maxStack<=64);
  el.textContent=ok?`✓ Совпали все ${meta.samples} отсчётов. Timer0 IRQ: ${emulator.irqCount}; пропуски: 0; макс. ISR: ${emulator.maxISR} тактов.`:`Ошибка: несовпадения=${bad}, первое=${first}, Timer0=${emulator.missedOverflows}, gap=${large}`;
 }catch(err){console.error(err);el.textContent='Ошибка эмуляции: '+(err.message||String(err))}
 finally{button.disabled=false}
}
document.querySelectorAll('.verify').forEach(b=>b.addEventListener('click',()=>verifyFirmware(b.dataset.name,b)));
draw(null);
</script></body></html>'''
page=page.replace('__SECTIONS__','\n'.join(cards)).replace('__EMU__',source).replace('__DATA__',jsdata)
(ROOT/'index.html').write_text(page,encoding='utf8')
print('Created',ROOT/'index.html','bytes',len(page.encode()),'includes:',list(payload))
