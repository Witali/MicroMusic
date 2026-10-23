#!/usr/bin/env python3
"""Create a self-contained Web Audio A/B page from the trained C encoder output."""
from pathlib import Path
import base64,io,json
import numpy as np
import soundfile as sf
from fast_train import HERE, SOURCE, Native, unpack_stream

CAPTIONS={
    'chego':'Чего тебе нужно?',
    'otvechaesh':'Что ж ты не отвечаешь?',
    'vinni':'Сова! Открывай! Медведь пришёл!'
}

def as_wav(y):
    with io.BytesIO() as mem:
        sf.write(mem,y,7500,format='WAV',subtype='PCM_16')
        return base64.b64encode(mem.getvalue()).decode('ascii')

cases={}
for name,caption in CAPTIONS.items():
    ref,sr=sf.read(SOURCE/name/'original.wav');assert sr==7500
    native=Native(ref)
    f,d=unpack_stream((SOURCE/name/'speech.hq').read_bytes())
    raw=native.decode(f,d);baseline=(raw.astype('float32')-128)/128
    new=HERE/'final'/name
    nr=json.loads((new/'result.json').read_text());pcm=np.frombuffer((new/'expected_pcm.raw').read_bytes(),dtype=np.uint8)
    new_wav=(pcm.astype('float32')-128)/128
    outputs={
        'original':as_wav(ref),
        'hq3':as_wav(baseline),
        'fast_c':as_wav(new_wav)
    }
    variants=[{'value':'original','label':'Оригинал'},
              {'value':'hq3','label':'Исходная HQ3'},
              {'value':'fast_c','label':'C-кодировщик'}]
    if name=='chego':
        wavb=np.frombuffer((HERE/'final'/'chego_balanced'/'expected_pcm.raw').read_bytes(),np.uint8)
        outputs['balanced']=as_wav((wavb.astype('float32')-128)/128)
        variants.append({'value':'balanced','label':'C, баланс спектра'})
    gap=np.zeros(7500//4,dtype=np.float32)
    ab=np.concatenate([ref.astype(np.float32),gap,new_wav]).astype(np.float32)
    cases[name]={
        'caption':caption,
        'flash':nr['flash'],
        'stoibase':nr['verified_stoi_before'] if name!='chego' else 0.8948381653757012,
        'stoi':nr['verified_stoi_after'],
        'variants':variants,
        'wavs':outputs,
        'ab':as_wav(ab),
        'hex':base64.b64encode((new/'firmware.hex').read_bytes()).decode('ascii')
    }
    native.close()

payload=json.dumps(cases,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
html='''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MicroMusic C Encoder — A/B test</title>
<style>
:root{color-scheme:dark;font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0e1625;color:#f0f6ff}
body{max-width:780px;margin:auto;padding:24px 14px 60px;line-height:1.52}
h1{font-size:clamp(24px,5vw,34px);letter-spacing:-.03em}
p,small{color:#acbcd0}.card{background:#16253a;border:1px solid #37485f;border-radius:16px;padding:18px;margin:17px 0}
label{display:block;color:#bfcde0;margin:10px 0 6px}select{display:block;box-sizing:border-box;width:100%;font:inherit;background:#0e1a29;color:white;border:1px solid #536b83;padding:12px;border-radius:10px}
.actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:18px}button{font:inherit;font-weight:650;padding:12px 14px;border:0;border-radius:10px;background:#61acff;color:#0b1c30;cursor:pointer}button.secondary{color:#e4f1ff;background:#304a64}
button:disabled{opacity:.4}.bar{height:8px;background:#344358;border-radius:8px;overflow:hidden;margin-top:18px}.bar>div{height:100%;width:0;background:#73c6f8;transition:width 0.2s}
.metrics{display:flex;gap:28px;flex-wrap:wrap}.metrics strong{display:block;font-size:22px}.muted{font-size:13px;color:#9eb0c7}
canvas{width:100%;height:140px;background:#0b1829;border-radius:8px;margin-top:12px}
</style></head><body>
<h1>MicroMusic · C-encoder</h1>
<p>Сравнение оригинала, прежней HQ3 и результата нативного кодировщика. Прошивки рассчитаны на ATtiny13A, 9,6 МГц, PWM PB1.</p>
<div class="card">
<label for="voice">Фраза</label><select id="voice"></select>
<label for="variant">Вариант звучания</label><select id="variant"></select>
<div class="actions">
<button id="play">▶ Слушать</button><button id="ab">⇄ Оригинал → C</button>
<button id="stop" class="secondary">■ Стоп</button><button id="savehex" class="secondary">↓ HEX</button>
</div><div class="bar"><div id="progress"></div></div><p id="status" class="muted">Выберите вариант и нажмите «Слушать».</p><canvas id="wave" width="750" height="140"></canvas>
</div><div class="card"><div class="metrics"><div><strong id="score">—</strong><small>STOI</small></div><div><strong id="flash">—</strong><small>Flash / 1024 Б</small></div></div>
<p class="muted">Результат STOI относится к обучающим записям. Высокая разборчивость не гарантирует идентичный оригиналу тембр. Аппаратное тестирование на физическом ATtiny13A не проводилось.</p></div>
<script>
const DATA=__DATA__;
const $=id=>document.getElementById(id);
let ctx=null,src=null,buf=null;
function draw(wave){const cvs=$('wave'),g=cvs.getContext('2d');g.fillStyle='#0b1829';g.fillRect(0,0,750,140);if(!wave)return;
 g.strokeStyle='#82c9fb';g.lineWidth=1.4;g.beginPath();const stride=Math.max(1,Math.floor(wave.length/750));
 for(let i=0;i<750;i++){let x=i/750*wave.length,y=wave[Math.min(wave.length-1,Math.floor(x))];const yy=70-y*58;i?g.lineTo(i,yy):g.moveTo(i,yy)}g.stroke();}
function choose(){let v=$('voice').value,d=DATA[v];$('variant').innerHTML='';
 for(const opt of d.variants){let e=new Option(opt.label,opt.value);$('variant').appendChild(e)}
 $('score').textContent=d.stoi.toFixed(6);$('flash').textContent=d.flash+' Б';draw(null)}
function stop(){try{if(src){src.stop();src.disconnect()}}catch(e){}src=null;$('progress').style.width='0%'}
function b64toBuffer(b){const s=atob(b);let a=new Uint8Array(s.length);for(let i=0;i<s.length;i++)a[i]=s.charCodeAt(i);return a.buffer}
async function play(data){try{
 stop();ctx=ctx||(new (window.AudioContext||window.webkitAudioContext)());await ctx.resume();
 const wav=await ctx.decodeAudioData(b64toBuffer(data));buf=wav;
 src=ctx.createBufferSource();src.buffer=wav;const volume=ctx.createGain();volume.gain.value=0.85;src.connect(volume);volume.connect(ctx.destination);src.start();
 draw(wav.getChannelData(0));$('status').textContent='Воспроизведение — '+wav.duration.toFixed(2)+' с';
 const playing=src;src.onended=()=>{if(src===playing){src=null;$('status').textContent='Воспроизведение завершено';$('progress').style.width='0%'}};
 const t0=ctx.currentTime, duration=wav.duration;
 function tick(){if(!src)return;let p=Math.min(1,(ctx.currentTime-t0)/duration);$('progress').style.width=(100*p).toFixed(0)+'%';if(p<1)requestAnimationFrame(tick)}requestAnimationFrame(tick)
 }catch(err){$('status').textContent='Не удалось воспроизвести: '+err.message;console.error(err)}}
$('voice').innerHTML=Object.entries(DATA).map(([k,v])=>'<option value="'+k+'">'+v.caption+'</option>').join('');
$('voice').addEventListener('change',()=>{stop();choose()});
$('play').addEventListener('click',()=>play(DATA[$('voice').value].wavs[$('variant').value]));
$('ab').addEventListener('click',()=>play(DATA[$('voice').value].ab));
$('stop').addEventListener('click',stop);
$('savehex').addEventListener('click',()=>{const v=$('voice').value;const blob=new Blob([b64toBuffer(DATA[v].hex)],{type:'text/plain'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='MicroMusic_'+v+'_C.hex';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)});
choose();
</script></body></html>'''.replace('__DATA__',payload)
(HERE/'MicroMusic_C_Encoder_Player.html').write_text(html)
print('wrote',HERE/'MicroMusic_C_Encoder_Player.html','bytes',len(html))
