#!/usr/bin/env python3
"""Build a no-server mobile friendly LPX3 vs LPC2 comparison page."""
from pathlib import Path
import json,base64, argparse
import numpy as np,soundfile as sf
R=Path(__file__).resolve().parent
clips={'vinni':{'name':'Сова! Открывай! Медведь пришёл!', 'desc':'Мужской голос • Винни-Пух'},
       'xtuj-ntt':{'name':'Чего тебе нужно?', 'desc':'Высокий голос • пример 1'},
       'ne-otv':{'name':'Что ж ты не отвечаешь?', 'desc':'Высокий голос • пример 2'}}
ap=argparse.ArgumentParser()
ap.add_argument('--clips',nargs='*',default=list(clips))
ap.add_argument('--out',default=str(R/'index.html'))
args=ap.parse_args()
rep=json.loads((R/'benchmark.json').read_text()) if (R/'benchmark.json').exists() else {}
all_samples={}
for key in args.clips:
 info=clips.get(key,{'name':key.replace('_',' '),'desc':'Новая запись'})
 p=R/'samples'/key
 if not p.exists():p=R/key
 report_file=p/'metrics.json'
 report=json.loads(report_file.read_text()) if report_file.exists() else rep[key]
 a={'title':info['name'],'description':info['desc'],'modes':{},'metrics':report}
 for fn,label in [('original','Оригинал'),('lpc2_voice_v2','LPC2 Voice v2')]:
  pcm,sr=sf.read(p/(fn+'.wav'));assert sr==8000
  pcm16=np.clip(np.rint(pcm*32767),-32768,32767).astype('<i2')
  a['modes'][fn]={'kind':'pcm16','b64':base64.b64encode(pcm16.tobytes()).decode(),'label':label}
 for n in [2,3,4]:
  bin=(p/f'voice_v3_{n}bit.lpx3').read_bytes()
  a['modes'][f'v3_{n}']={'kind':'lpx3','b64':base64.b64encode(bin).decode(),
                          'label':f'LPX3 {n} бит/отсчёт','bytes':len(bin),
                          'metrics':report['modes'][str(n)]}
 all_samples[key]=a
b64js=json.dumps(all_samples,ensure_ascii=False,separators=(',',':'))
codec=(R/'lpx3_decoder.js').read_text()
head='''<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>MicroMusic LPC2 Voice v3 — сравнение голосов</title>
<style>
:root{color-scheme:dark;--bg:#0c1524;--panel:#192439;--line:#35445f;--txt:#f1f5ff;--muted:#a8b6cf;--accent:#8cc8ff;--good:#9dddaf}
*{box-sizing:border-box}body{background:var(--bg);color:var(--txt);font:15px/1.55 system-ui,-apple-system,sans-serif;margin:auto;max-width:940px;padding:18px 14px 60px}h1{font-size:clamp(23px,4vw,34px);margin-bottom:8px}h2{font-size:19px;margin-top:0}p{color:var(--muted)}.lead{font-size:16px}button{border:1px solid #566987;color:var(--txt);background:#263650;border-radius:10px;padding:10px 12px;font:inherit;cursor:pointer;min-height:43px;text-align:left}button:focus-visible{outline:2px solid var(--accent)}button:hover{border-color:var(--accent)}button.active{background:#224e78;border-color:#79b8f5}.controls{display:flex;gap:9px;flex-wrap:wrap}button.stop{background:#71383e;border-color:#93545b}.card{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:18px;margin:14px 0}.tracks{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px}.tracks button{display:flex;gap:5px;flex-direction:column}.tracks small{color:#b9c6da;font-size:12px}.row{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}.muted{color:var(--muted)}.numbers{font-variant-numeric:tabular-nums}.pill{display:inline-block;border:1px solid var(--line);border-radius:7px;color:var(--muted);padding:4px 7px;margin:2px 3px 2px 0;font-size:12px}#wave{width:100%;height:144px;background:#091120;border:1px solid #33445e;border-radius:9px}#status{white-space:pre-wrap;min-height:24px;color:var(--good)}input[type=range]{width:160px}a{color:#a6d3ff}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{border-bottom:1px solid var(--line);padding:8px 6px;text-align:left;font-size:13px}td:not(:first-child),th:not(:first-child){text-align:right}strong{color:#fff}summary{cursor:pointer;padding:5px}code{color:#c2ddff}
</style></head><body>
<h1>MicroMusic — LPC2 Voice v3</h1>
<p class="lead">Сравнение одной записи в старом LPC2 Voice v2 и новом LPC2 с уточнением возбуждения. Кодек использует <strong>одну универсальную схему для низких и высоких голосов</strong>, а параметры подбирает по записи.</p>
<div class="card"><div class="row"><div class="controls"><button id="stop" class="stop">■ Стоп</button><button id="check">Проверить декодер LPX3</button></div><label>Громкость <input id="volume" type="range" min="0" max="2" step="0.02" value="0.85"></label></div>
<p id="status">Нажмите ▶ на нужной дорожке. Звук формируется через Web Audio непосредственно после нажатия.</p><canvas id="wave" width="1000" height="144" aria-label="Осциллограмма"></canvas>
<p class="muted">Для честного A/B громкость автоматически выравнивается по RMS. Кнопка «Сравнить» проигрывает оригинал, паузу 0,25 с и выбранный кодек.</p></div>
<div id="clips"></div>
<details class="card"><summary><strong>Что означает LPC2 v3 и почему поток больше?</strong></summary><p>Классический LPC2 хранит главным образом частоту F₀, энергию, LSF/форманты и тип возбуждения. Он синтезирует типовой голосовой импульс, который заметно меняет тембр. LPX3 сохраняет прежнее ядро LPC2 v2 и дополнительно кодирует возбуждение с обратной связью по 2, 3 или 4 бита на отсчёт. Это лучше сохраняет индивидуальную периодику голоса, но требует 19–35 кбит/с вместо 2–4.</p><p>LPX3 — <strong>экспериментальный формат</strong>, не стандарт LPC-10 и не совместим побитово с TMS5220. <strong>В ATtiny13A с 1 КБ Flash фразы LPX3 не помещаются</strong>; там по-прежнему используется компактный TinyLPC.</p></details>
'''
script='''<script>
'''+codec+'\nconst SAMPLES='+b64js+';\n'+r'''
const $=x=>document.getElementById(x);
let ctx=null,playing=null,gain=null,cache=new Map(),refCache=new Map();
const decodeBytes=b64=>{const binary=atob(b64),result=new Uint8Array(binary.length);for(let i=0;i<binary.length;i++)result[i]=binary.charCodeAt(i);return result};
function pcm16bytes(b64){const b=decodeBytes(b64),v=new DataView(b.buffer,b.byteOffset,b.byteLength),x=new Float32Array(b.length/2);for(let i=0;i<x.length;i++)x[i]=v.getInt16(i*2,true)/32768;return x}
function getTrack(clip,id){const key=clip+'/'+id;if(cache.has(key))return cache.get(key);
 const mode=SAMPLES[clip].modes[id],ret=mode.kind==='lpx3'?decodeLPX3(decodeBytes(mode.b64)).pcm:pcm16bytes(mode.b64);
 cache.set(key,ret);return ret;
}
function rms(a){let s=0;for(let i=0;i<a.length;i++)s+=a[i]*a[i];return Math.sqrt(s/Math.max(1,a.length))}
function normalise(a){const v=new Float32Array(a.length),k=Math.min(4,0.16/Math.max(0.012,rms(a)));for(let i=0;i<a.length;i++)v[i]=a[i]*k;return v}
function draw(x){const can=$('wave'),g=can.getContext('2d'),w=can.width,h=can.height;g.fillStyle='#091120';g.fillRect(0,0,w,h);g.strokeStyle='#294567';g.beginPath();g.moveTo(0,h/2);g.lineTo(w,h/2);g.stroke();if(!x)return;g.strokeStyle='#81c9ff';g.lineWidth=1.5;g.beginPath();const win=Math.max(1,Math.floor(x.length/w));for(let i=0;i<w;i++){let hi=-99,lo=99;for(let j=i*win;j<Math.min((i+1)*win,x.length);j++){hi=Math.max(hi,x[j]);lo=Math.min(lo,x[j])}if(hi===-99)hi=lo=0;g.moveTo(i,h/2-hi*h*.42);g.lineTo(i,h/2-lo*h*.42)}g.stroke()}
async function initAudio(){if(!ctx)ctx=new (window.AudioContext||window.webkitAudioContext)();await ctx.resume();return ctx}
function stop(){if(playing){try{playing.stop()}catch(e){}playing.disconnect();playing=null;}$('status').textContent='Остановлено';document.querySelectorAll('button.active').forEach(e=>e.classList.remove('active'))}
async function play(clip,id,button,ab=false){
 try{
   const C=await initAudio();stop();
   let out=normalise(getTrack(clip,id));
   if(ab && id!=='original'){
     const ref=normalise(getTrack(clip,'original')),pause=new Float32Array(2000),merged=new Float32Array(ref.length+pause.length+out.length);
     merged.set(ref);merged.set(out,ref.length+pause.length);out=merged;
   }
   const abuf=C.createBuffer(1,out.length,8000);abuf.copyToChannel(out,0);
   let src=C.createBufferSource();src.buffer=abuf;
   gain=C.createGain();gain.gain.value=Number($('volume').value);src.connect(gain);gain.connect(C.destination);
   src.onended=()=>{if(playing===src){playing=null;button.classList.remove('active');$('status').textContent='Воспроизведение завершено.'}};
   playing=src;button.classList.add('active');src.start();draw(out);
   $('status').textContent=`Сейчас звучит: ${SAMPLES[clip].title} — ${SAMPLES[clip].modes[id].label}${ab?' (A/B сравнение)':''}`;
 }catch(e){$('status').textContent='Ошибка воспроизведения: '+e.message;console.error(e)}
}
$('stop').onclick=stop;
$('volume').oninput=()=>{if(gain)gain.gain.value=Number($('volume').value)};
$('check').onclick=()=>{
 const t0=performance.now();let total=0,ok=0;try{
 for(const [clip,s] of Object.entries(SAMPLES))for(const key of ['v3_2','v3_3','v3_4']){
  const mode=s.modes[key];const pcm=decodeLPX3(decodeBytes(mode.b64)).pcm;
  total+=pcm.length;
  if(pcm.length!==getTrack(clip,'original').length)throw Error('Length mismatch for '+clip+'/'+key);ok++;
  if(!pcm.every(Number.isFinite))throw Error('NaN in '+clip+' '+key);
 }
 $('status').textContent=`OK: декодированы ${ok} LPX3-потоков (${total.toLocaleString('ru')} отсчётов), NaN нет. ${(performance.now()-t0).toFixed(0)} мс.`;
 }catch(e){$('status').textContent='Ошибка декодера: '+e.message;console.error(e)}
};
for(const [key,s] of Object.entries(SAMPLES)){
 const card=document.createElement('section');card.className='card';
 const m=s.metrics;
 card.innerHTML=`<h2>${s.title}</h2><p>${s.description}. Длительность ${m.original_seconds} с.</p><div class="tracks"></div><div class="controls" style="margin-top:10px"></div>`;
 const g=card.querySelector('.tracks'),row=card.querySelector('.controls');
 for(const mode of ['original','lpc2_voice_v2','v3_2','v3_3','v3_4']){
   const d=s.modes[mode];let metric=mode.startsWith('v3_')?m.modes[mode.slice(3)]:null;
   const info=metric?`${metric.bitrate_kbps.toFixed(1)} кбит/с · STOI ${metric.stoi}`:mode==='original'?'Без потерь':`STOI ${m.baseline.stoi}`;
   const btn=document.createElement('button');btn.innerHTML=`<strong>▶ ${d.label}</strong><small>${info}</small>`;btn.onclick=()=>play(key,mode,btn);g.appendChild(btn);
 }
 const ab=document.createElement('button');ab.innerText='▶ A/B: оригинал → LPC2 v3 3-бит';ab.onclick=()=>play(key,'v3_3',ab,true);row.appendChild(ab);
 $('clips').appendChild(card);
}
draw(null);
</script></body></html>'''
dest=Path(args.out);dest.parent.mkdir(parents=True,exist_ok=True)
dest.write_text(head+script,encoding='utf-8')
print('Saved',dest,dest.stat().st_size)
