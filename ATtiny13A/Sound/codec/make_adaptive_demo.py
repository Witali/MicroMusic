"""Adaptive keyframe LPC8: standalone Web Audio test, AVR HEX verifier, and A/B WAVs.
Private page contains users' original copyrighted cartoon audio: not for publication.
"""
from pathlib import Path
import base64, html, json
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, butter, sosfilt
ROOT=Path(__file__).resolve().parent
DEST=ROOT/'release';DEST.mkdir(exist_ok=True)
from sys import path

from perceptual import load_wav
CLIPS={'xtuj-ntt':'Чего тебе нужно?','ne-otv':'Что ж ты не отвечаешь?'}

def load_avr_raw(p):return np.fromfile(p,'u1').astype(np.float64)/128.-1.
def pcm_wav(path,x):sf.write(path,x,7500,subtype='PCM_16')
def pcm16b64(x):
    x=np.asarray(x,dtype=np.float64);x=np.clip(x,-0.99997,0.99997)
    arr=np.round(x*32767).astype('<i2')
    return base64.b64encode(arr.tobytes()).decode('ascii')
def padtrim(y,n):
    if len(y)>n:return y[:n]
    return np.pad(y,(0,n-len(y)))

audio={};info={}
for clip,title in CLIPS.items():
    new=ROOT/'adaptive_results'/clip; previous=ROOT/clip; old=ROOT/'datasets'/clip
    teacher=old/'lpx3_voice.wav'
    base=old/'baseline_pcm_u8.raw'
    orig=load_wav(old/'original.wav')
    newwav=load_avr_raw(new/'emu_pwm_u8.raw')
    signals={'original':orig,'lpx3':load_wav(teacher),'keyframe':load_avr_raw(previous/'emu_pwm_u8.raw'),'adaptive':newwav}
    n=len(newwav)
    normalized={}
    sos=butter(2,[45,3300],fs=7500,btype='bandpass',output='sos')
    for kind,pcm in signals.items():
        pcm=padtrim(pcm,n)
        # Speaker model comparison: apply same near-DC and ultrasonic suppression to all tracks
        filt=sosfilt(sos,pcm)
        rms=float(np.sqrt(np.mean(filt**2)))
        factor=min(2.5,0.14/max(rms,1e-8))
        normalized[kind]=np.clip(filt*factor,-0.98,0.98)
        audio[clip+'_'+kind]=pcm16b64(normalized[kind])
    pcm_wav(DEST/(clip+'_avr_adaptive.wav'),normalized['adaptive'])
    # 0.25s separators; original -> LPX3 -> old LPC8 -> keyframe -> old LPC8 -> keyframe
    gap=np.zeros(1875,float)
    concat=np.concatenate([np.concatenate([normalized[kind],gap]) for kind in ['original','lpx3','keyframe','adaptive','keyframe','adaptive']])
    pcm_wav(DEST/(clip+'_AB.wav'),concat)
    # embed true firmware BIN and reference raw bytes for the JS AVR instruction verification
    audio[clip+'_flash']=base64.b64encode((new/'tinylpc.bin').read_bytes()).decode('ascii')
    audio[clip+'_raw']=base64.b64encode((new/'emu_pwm_u8.raw').read_bytes()).decode('ascii')
    info[clip]={'title':title,'frames':n//256,'length':n,'report':json.loads((new/'report.json').read_text())}

js_core=(ROOT/'avr_emulator.js').read_text()
# Prevent quote break if a future upstream emulator contains closing script string.
js_core=js_core.replace('</script>','<\\/script>')
audio_json=json.dumps(audio,ensure_ascii=False,separators=(',',':'))
info_json=json.dumps(info,ensure_ascii=False,separators=(',',':'))
card_html=''
for clip,title in CLIPS.items():
    r=info[clip]['report'];m=r['verified_AVR']['metrics'];b=r['baseline_previous_AVR']
    card_html+=f'''<section class="card" data-clip="{clip}">
    <div class="top"><h2>{html.escape(title)}</h2><span class="tag">{r['verified_AVR']['flash_bytes']} / 1024 Б Flash</span></div>
    <div class="small">STOI: предыдущая {b['stoi']:.3f} → адаптивная {m['stoi']:.3f} · ключевых спектров: {r['keyframes']} · быстрых/медленных переходов: {r['fast_frames']}/{r['slow_frames']} · {r['speech_bytes']} Б речи</div>
    <div class="buttonrow">
        <button data-play="{clip}_original">Оригинал</button>
        <button data-play="{clip}_lpx3">LPX3</button>
        <button data-play="{clip}_keyframe">Keyframe LPC-8 (v1)</button>
        <button data-play="{clip}_adaptive" class="primary">Adaptive LPC-8 (v2)</button>
    </div>
    <div class="timeline" data-timeline="{clip}" title="Зелёный — быстро (4 отсчёта), синий — медленно (8 отсчётов)">__TIMELINE_{clip}__</div>
    <canvas id="wave-{clip}" width="700" height="95"></canvas>
    <div class="utility"><button class="secondary" data-check="{clip}">Проверить HEX в AVR-эмуляторе</button><button class="secondary" data-save="{clip}_adaptive">Сохранить результат WAV</button></div>
    <div class="verify small" id="verify-{clip}">Нажми кнопку проверки, чтобы выполнить машинный код и сравнить каждый отсчёт.</div>
    </section>'''

page='''<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MicroMusic · Adaptive Keyframe LPC-8 · ATtiny13A</title>
<style>
:root{color-scheme:dark;--bg:#0a1220;--card:#172438;--line:#35455d;--fg:#edf6ff;--muted:#9cb0c8;--good:#69e1bf}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:850px;padding:25px 14px 60px;margin:auto}h1{font-size:clamp(24px,5vw,36px);margin:0 0 8px}h2{font-size:clamp(18px,4vw,23px);margin:0}.intro{color:var(--muted)}
.card{padding:19px;margin:17px 0;border:1px solid var(--line);border-radius:17px;background:var(--card)}
.top,.buttonrow,.utility,.settings{display:flex;align-items:center;flex-wrap:wrap;gap:10px}.top{justify-content:space-between}.tag{border-radius:100px;background:#294560;padding:3px 10px;font-size:12px;color:#dff6ff}
.small{color:var(--muted);font-size:13px;margin:7px 0 14px}
button{font:inherit;border:1px solid #456281;border-radius:10px;color:var(--fg);background:#293d58;padding:10px 12px;cursor:pointer;touch-action:manipulation}
button.primary{background:#43b3ab;color:#06191e;border-color:#43b3ab;font-weight:700}button.secondary{font-size:13px;background:#202f47}
.timeline{display:flex;overflow:hidden;height:11px;border-radius:4px;margin:7px 0 9px}.timeline span{flex:1;min-width:2px;background:#4274a2}.timeline span.fast{background:#6addab}.timeline span.silence{background:#25334a}button.playing{outline:2px solid #a6f7ef}button:disabled{opacity:.45;cursor:not-allowed}canvas{display:block;width:100%;height:95px;margin:13px 0;border-radius:8px;background:#0b1628}
.verify{margin:10px 0 0;min-height:1.3em}.verify.success{color:var(--good)}.verify.error{color:#ff9f94}
#status{font-weight:600;min-height:1.5em}input[type=range]{width:110px}a{color:#84c8ff}
footer{border-top:1px solid var(--line);margin-top:26px;padding-top:10px;color:var(--muted);font-size:13px}
</style></head><body><main>
<h1>MicroMusic · Adaptive LPC-8</h1>
<p class="intro">ATtiny13A, 9,6 МГц · PWM 37,5 кГц · выход 7500 отсчётов/с · 8-ступенчатый LPC-фильтр. Двухскоростная интерполяция формант и громкости: 4 отсчёта на шаг для быстрых переходов, 8 для протяжных. Скорость автоматически выбирается из исходного голоса и занимает один ранее свободный бит кадра. Аудио встроено: интернет не нужен.</p>
<section class="card settings"><button id="stop">■ Остановить</button><label>Громкость <input id="volume" type="range" min="0" max="1" step="0.01" value="0.65"></label><span id="status" aria-live="polite">Выбери вариант звучания.</span></section>
__CARDS__
<footer>Adaptive LPC-8 — экспериментальная прошивка с автоматическим выбором ключевых кадров и скорости переходов. Сравнение с LPX3 отражает разницу между качественным речевым кодеком и моделью для 1 КБ Flash. Оригинальные фрагменты предназначены для частного исследования и не должны публиковаться без разрешения правообладателей. Проверена программная AVR-эмуляция; аппаратное испытание ещё не выполнено.</footer>
</main><script>
__AVR_CORE__
const STORE=__AUDIO__;
const META=__META__;
let context=null,src=null,node=null,activeButton=null,currentClip=null;
const status=document.querySelector('#status'), volume=document.querySelector('#volume');
function bytes(b64){const raw=atob(b64);const a=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)a[i]=raw.charCodeAt(i);return a}
function pcm(key){const d=bytes(STORE[key]);const view=new DataView(d.buffer,d.byteOffset,d.byteLength);const a=new Float32Array(d.length/2);for(let i=0;i<a.length;i++)a[i]=view.getInt16(i*2,true)/32768;return a}
function stop(){if(src){try{src.stop()}catch(e){};src.disconnect();src=null}if(node){node.disconnect();node=null}if(activeButton){activeButton.classList.remove('playing');activeButton=null}currentClip=null;status.textContent='Остановлено.'}
async function play(key,btn){
 stop(); if(!context)context=new(window.AudioContext||window.webkitAudioContext)();
 try{await context.resume();if(context.state!=='running')throw Error('AudioContext заблокирован браузером');
 const samples=pcm(key),buf=context.createBuffer(1,samples.length,7500);buf.copyToChannel(samples,0);
 src=context.createBufferSource();src.buffer=buf;
 node=context.createGain();node.gain.value=+volume.value;
 src.connect(node);node.connect(context.destination);src.start();activeButton=btn;btn.classList.add('playing');currentClip=key.split('_')[0];
 const source=src;source.onended=()=>{if(src===source){btn.classList.remove('playing');src=null;status.textContent='Воспроизведение завершено.'}};
 status.textContent='▶ '+(META[currentClip]?.title||currentClip)+' — '+key.slice(currentClip.length+1)+' ('+(samples.length/7500).toFixed(2)+' с)';
 draw(key,samples);
 }catch(e){console.error(e);status.textContent='Не удалось включить звук: '+e.message;}
}
volume.oninput=()=>{if(node)node.gain.value=+volume.value};document.querySelector('#stop').onclick=stop;
function draw(key,wave){const c=document.querySelector('#wave-'+key.split('_')[0]),g=c.getContext('2d'),W=c.width,H=c.height;g.clearRect(0,0,W,H);g.strokeStyle='#395b7a';g.beginPath();g.moveTo(0,H/2);g.lineTo(W,H/2);g.stroke();g.strokeStyle='#61dbba';g.lineWidth=1.3;g.beginPath();for(let i=0;i<W;i++){let from=Math.floor(wave.length*i/W),end=Math.max(from+1,Math.floor(wave.length*(i+1)/W)),mn=1,mx=-1;for(let j=from;j<end;j++){mn=Math.min(mn,wave[j]);mx=Math.max(mx,wave[j])}g.moveTo(i,(1-mx)*H/2);g.lineTo(i,(1-mn)*H/2)}g.stroke()}
function writeWav(key){const a=bytes(STORE[key]),ab=new Uint8Array(44+a.length),v=new DataView(ab.buffer),str=(o,s)=>{for(let i=0;i<s.length;i++)ab[o+i]=s.charCodeAt(i)};
 str(0,'RIFF');v.setUint32(4,36+a.length,true);str(8,'WAVEfmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,7500,true);v.setUint32(28,15000,true);v.setUint16(32,2,true);v.setUint16(34,16,true);str(36,'data');v.setUint32(40,a.length,true);ab.set(a,44);
 const blob=new Blob([ab],{type:'audio/wav'}),u=URL.createObjectURL(blob),link=document.createElement('a');link.href=u;link.download=key+'.wav';link.click();setTimeout(()=>URL.revokeObjectURL(u),2000)}
async function check(clip,button){const el=document.querySelector('#verify-'+clip);button.disabled=true;el.className='verify small';el.textContent='Проверка машинных инструкций AVR…';
 try{const core=new AVRCore(bytes(STORE[clip+'_flash'])),ref=bytes(STORE[clip+'_raw']);let diff=0,maxDelta=0,last=0;
 for(let i=0;i<ref.length;i++){const s=core.takeSample();if(s!==ref[i])diff++;if(i){maxDelta=Math.max(maxDelta,core.cycles-last)}last=core.cycles;if((i&127)===0){if((i&511)===0)el.textContent='AVR-эмуляция: '+Math.round(100*i/ref.length)+'%';await new Promise(r=>setTimeout(r,0))}}
 const ok=diff===0&&core.missedOverflows===0&&maxDelta<1290&&core.maxISR<256;
 el.className='verify small '+(ok?'success':'error');el.textContent=(ok?'✓ Проверка пройдена. ':'✗ Есть расхождения. ')+`Отсчётов: ${ref.length}; ошибок PCM: ${diff}; IRQ: ${core.irqCount}; пропущено: ${core.missedOverflows}; ISR: ${core.maxISR}/256 тактов; максимум между отсчётами: ${maxDelta} тактов.`;
 }catch(e){console.error(e);el.className='verify small error';el.textContent='Ошибка проверки: '+e.message}
 finally{button.disabled=false}}
document.querySelectorAll('[data-play]').forEach(b=>b.addEventListener('click',()=>play(b.dataset.play,b)));
document.querySelectorAll('[data-check]').forEach(b=>b.addEventListener('click',()=>check(b.dataset.check,b)));
document.querySelectorAll('[data-save]').forEach(b=>b.addEventListener('click',()=>writeWav(b.dataset.save)));
for(const clip of Object.keys(META))draw(clip+'_adaptive',pcm(clip+'_adaptive'));
</script></body></html>'''
for clip in CLIPS:
    z=np.load(ROOT/'adaptive_results'/clip/'trained_parameters.npz')
    timeline=''.join('<span class="'+('silence' if int(e)==0 else 'fast' if int(f) else 'slow')+'"></span>' for e,f in zip(z['E'],z['fast']))
    card_html=card_html.replace('__TIMELINE_'+clip+'__',timeline)
page=page.replace('__CARDS__',card_html).replace('__AVR_CORE__',js_core).replace('__AUDIO__',audio_json).replace('__META__',info_json)
(DEST/'index.html').write_text(page,encoding='utf-8')
(ROOT/'MicroMusic_Adaptive_LPC8.html').write_text(page,encoding='utf-8')
Path('/mnt/data/MicroMusic_Adaptive_LPC8.html').write_text(page,encoding='utf-8')
print('created standalone html',len(page.encode()),'bytes')
