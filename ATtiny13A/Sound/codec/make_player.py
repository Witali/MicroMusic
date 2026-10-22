"""Offline, single-file mobile Web Audio player. Explicit play buttons avoid unreliable data:audio URI sources.
Embedded samples are signed PCM16 mono, all at 7500 Hz. No network needed.
"""
from __future__ import annotations
import base64, html, json
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

SR=7500

def audio_pcm(path):
    x,sr=sf.read(str(path),always_2d=True,dtype='float32')
    x=x.mean(axis=1)
    if sr!=SR:
        import math
        g=math.gcd(sr,SR)
        x=resample_poly(x,SR//g,sr//g)
    x=np.clip(x,-1,1)
    pk=float(np.max(np.abs(x))) if len(x) else 0
    rms=float(np.sqrt(np.mean(x*x))) if len(x) else 0
    if pk>1e-6:
        x*=min(.18/max(rms,1e-6), .90/pk)
    return np.round(np.clip(x,-1,1)*32767).astype('<i2')

def generate(groups,destination):
    payload={}; list_html=[]; wave_links=[]
    for gi,group in enumerate(groups):
        variants=[]
        for j,variant in enumerate(group['variants']):
            key=f'g{gi}_v{j}'; data=audio_pcm(variant['file'])
            payload[key]={'rate':SR,'bytes':base64.b64encode(data.tobytes()).decode('ascii'), 'duration':round(len(data)/SR,3)}
            fileuri=variant.get('wav_download')
            dl=(f'<a class="save" href="{html.escape(fileuri,quote=True)}" download="">WAV <span aria-hidden="true">↗</span></a>' if fileuri else '')
            variants.append(f'<div class="clip"><button class="play" data-track="{key}" aria-label="Воспроизвести {html.escape(variant["name"])}">▶ <span>Слушать</span></button><div class="clipInfo"><strong>{html.escape(variant["name"])}</strong><small>{round(len(data)/SR,2):.2f} с</small></div>{dl}</div>')
        report=group.get('report',{})
        line=''
        if report:
            a=report.get('initial',{});b=report.get('optimized',{})
            if a and b:
                line=f'<p class="metric">STOI: <strong>{a["stoi"]:.3f} → {b["stoi"]:.3f} (LPC-7)</strong> · Flash: {report.get("flash","—")} Б</p>'
                if report.get('optimized8'):
                    line+=f'<p class="metric">STOI LPC-8: <strong>{report["optimized8"]["stoi"]:.3f}</strong> · Flash: {report["flash8"]} Б · Речь: {report["speech8"]} Б</p>'
        list_html.append(f'<section class="group"><h2>{html.escape(group["title"])}</h2><p class="desc">{html.escape(group["desc"])}</p>{"".join(variants)}{line}</section>')
    jsdata=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
    # JSON contains no script-ending substrings (the bytes are plain base64); escape as precaution.
    jsdata=jsdata.replace('</','<\\/')
    page=r'''<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>MicroMusic — TinyLPC speech comparisons (mobile audio fix)</title>
<style>
:root{font-family:system-ui,-apple-system,sans-serif;color-scheme:dark;background:#101725;color:#eaf3ff}
*{box-sizing:border-box}body{max-width:940px;padding:18px 14px 44px;margin:auto;line-height:1.4}
h1{font-size:clamp(22px,5vw,35px);margin:.1em 0}h2{font-size:20px;margin:0 0 8px;color:#deefff}
p{color:#b5c7df}header p{margin:4px 0 18px}h2,p{word-break:normal}
.info{color:#c4d6e6;font-size:14px}.group{background:#1a2639;border:1px solid #364b68;border-radius:15px;padding:16px;margin:20px 0}
.desc{margin:2px 0 13px;font-size:14px}
.clip{display:flex;align-items:center;gap:12px;padding:11px 2px;border-top:1px solid #31435b;min-height:63px}
.clipInfo{flex:1;display:flex;gap:3px;flex-direction:column;min-width:0}.clipInfo strong{font-size:15px;font-weight:650}.clipInfo small{color:#9dafc7}
button{font:inherit;background:#63b2ff;color:#091421;border:0;border-radius:11px;padding:11px 13px;font-weight:700;cursor:pointer;touch-action:manipulation;min-height:44px}
button:hover{filter:brightness(1.08)}button.play{min-width:112px}button.play.active{background:#ffd788}
.save{color:#aad8ff;font-size:13px;text-decoration:none;border-bottom:1px dotted #aad8ff;white-space:nowrap}
.metric{font-size:14px;margin:12px 0 0}.bar{display:flex;align-items:center;flex-wrap:wrap;gap:10px;background:#24334c;border-radius:12px;padding:12px 14px;position:sticky;top:0;z-index:5;box-shadow:0 3px 22px #0005}
#status{flex:1;font-size:14px}#stop{background:#485f79;color:#fff}#stop:disabled{opacity:.5}
input[type=range]{width:105px;accent-color:#81c0ff}canvas{width:100%;height:95px;border-radius:10px;background:#0c1320;display:block;margin:12px 0 0}
.hint{font-size:13px;color:#afc0d7;padding:6px 2px}code{color:#e8f1ff}footer{color:#9daec8;font-size:13px}
@media(max-width:520px){.group{padding:12px}.clip{gap:9px}button.play{min-width:92px;padding:9px 8px}.bar{padding:8px}}
</style></head><body>
<header><h1>MicroMusic · сравнение речи</h1><p>ATtiny13A · LPC2 Improved · автоматическая оптимизация по исходной записи. Нажми «Слушать» в нужной строке — теперь звук запускается через Web Audio API, а не через встроенные ссылки <code>data:audio</code>.</p></header>
<div class="bar"><button id="stop" disabled>■ Стоп</button><label>Громкость <input id="volume" type="range" min="0" max="1.5" step="0.05" value="0.95"/></label><div id="status" role="status" aria-live="polite">Готов к воспроизведению.</div></div>
<canvas id="scope" width="900" height="95" aria-label="Форма звукового сигнала"></canvas>
__GROUPS__
<p class="hint">Если звук не появился внутри приложения ChatGPT, открой HTML-файл в Chrome/Firefox. В архиве также находятся отдельные WAV-файлы — они воспроизводятся обычным аудиоплеером. Для запуска нужен явный нажим кнопки. Для реального динамика ATtiny13A необходим RC-фильтр и усилитель.</p>
<footer>Модели и звуковые результаты — исследовательские. Это не побитовая совместимость TinyLPC с LPC2 Improved. Исходные записи предназначены для частного сравнения.</footer>
<script>"use strict";
const DATA=__DATA__;
let ctx=null,source=null,gain=null,active=null,visual=null,started=0,activeSeconds=0;
const status=document.querySelector('#status'),stopBtn=document.querySelector('#stop');
const scope=document.querySelector('#scope'),g=scope.getContext('2d');
const Vol=document.querySelector('#volume');
function write(t){status.textContent=t;}
function resetControls(){document.querySelectorAll('button.play').forEach(x=>{x.classList.remove('active');x.innerHTML='▶ <span>Слушать</span>'});stopBtn.disabled=true;}
function stop(){if(visual)cancelAnimationFrame(visual);visual=null;if(source){const old=source;source=null;old.onended=null;try{old.stop()}catch(e){}try{old.disconnect()}catch(e){}}active=null;resetControls();write('Остановлено.');draw(new Float32Array(0));}
stopBtn.onclick=stop;
Vol.oninput=()=>{if(gain&&ctx)gain.gain.setTargetAtTime(Number(Vol.value),ctx.currentTime,.01)};
function parse16(sourceB64){
 const b=atob(sourceB64);const n=b.length>>1;const f=new Float32Array(n);
 for(let i=0,j=0;i<n;i++,j+=2){const u=b.charCodeAt(j)|(b.charCodeAt(j+1)<<8);f[i]=(u<32768?u:u-65536)/32768.0}return f;
}
function draw(signal,start=0){const W=scope.width,H=scope.height;g.fillStyle='#0c1320';g.fillRect(0,0,W,H);g.lineWidth=1;g.strokeStyle='#263f5a';g.beginPath();g.moveTo(0,H/2);g.lineTo(W,H/2);g.stroke();if(!signal.length)return;g.strokeStyle='#76caff';g.lineWidth=1.4;g.beginPath();const windowLen=Math.min(signal.length,1200);const from=Math.min(Math.max(0,Math.floor(start)),Math.max(0,signal.length-windowLen));for(let i=0;i<W;i++){const at=from+Math.min(windowLen-1,Math.floor(i*windowLen/W));const y=H*.5-signal[at]*H*.43;if(i===0)g.moveTo(i,y);else g.lineTo(i,y)}g.stroke();}
async function play(k,button){
 if(active===k){stop();return}
 stop();
 const item=DATA[k];if(!item){write('Файл не найден в странице.');return}
 button.classList.add('active');button.textContent='Подготовка…';
 try{
  const AudioCtor=window.AudioContext||window.webkitAudioContext;
  if(!AudioCtor)throw new Error('Браузер не поддерживает Web Audio API. Используйте отдельный WAV-файл.');
  if(!ctx)ctx=new AudioCtor();
  const resumed=ctx.resume();  // Called directly within the user's click gesture.
  const samples=parse16(item.bytes);
  const buffer=ctx.createBuffer(1,samples.length,item.rate);
  buffer.getChannelData(0).set(samples);
  await resumed;
  if(ctx.state!=='running')throw new Error('AudioContext не запустился: '+ctx.state);
  source=ctx.createBufferSource();source.buffer=buffer;
  gain=ctx.createGain();gain.gain.setValueAtTime(0,ctx.currentTime);
  gain.gain.linearRampToValueAtTime(Number(Vol.value),ctx.currentTime+.010);
  gain.gain.setValueAtTime(Number(Vol.value),ctx.currentTime+Math.max(.011,item.duration-.012));
  gain.gain.linearRampToValueAtTime(0,ctx.currentTime+item.duration);
  source.connect(gain).connect(ctx.destination);
  active=k;started=ctx.currentTime;activeSeconds=item.duration;stopBtn.disabled=false;
  button.innerHTML='■ <span>Стоп</span>';
  let cur=source;
  cur.onended=()=>{if(source===cur)stop()};
  source.start();write('Играет: '+button.closest('.clip').querySelector('.clipInfo strong').textContent+' · '+item.duration.toFixed(2)+' с');
  function animate(){if(active!==k)return;draw(samples,(ctx.currentTime-started)*item.rate);visual=requestAnimationFrame(animate)}
  animate();
 }catch(err){console.error(err);stop();write('Ошибка звука: '+(err.message||String(err))+' — откройте страницу в Chrome или используйте WAV.');}
}
document.querySelectorAll('button.play').forEach(b=>b.addEventListener('click',()=>play(b.dataset.track,b)));
draw(new Float32Array(0));
</script></body></html>'''
    page=page.replace('__GROUPS__','\n'.join(list_html)).replace('__DATA__',jsdata)
    Path(destination).parent.mkdir(parents=True,exist_ok=True)
    Path(destination).write_text(page,encoding='utf8')
    print('Player generated',destination,'bytes',len(page.encode()))

if __name__=='__main__':
    print('Use via run_multi.py or import generate')
