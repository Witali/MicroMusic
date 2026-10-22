#!/usr/bin/env python3
"""Build a self-contained offline PIC16F1503 music/CPU emulator HTML."""
import base64,html,re
from pathlib import Path
r=Path(__file__).resolve().parents[1]
core=(r/'web/pic16-core.mjs').read_text().replace('export class PIC16F1503','class PIC16F1503').replace('export function readPIC16Hex','function readPIC16Hex')
hextext=(r/'firmware/micromusic_with_config.hex').read_text()
audio=(r/'reference/preview_pic16_asm.pcm8').read_bytes()
preview=base64.b64encode(audio).decode()
css=r'''<style>
:root{font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;color-scheme:dark;background:#0c1421;color:#edf2f9}
*{box-sizing:border-box}body{margin:0;padding:24px 16px}main{max-width:880px;margin:auto}h1{font-size:26px;margin:0 0 6px}
p{line-height:1.55}.muted{color:#a7b6ca;font-size:14px}.pill{color:#80d6b1;border:1px solid #386e62;border-radius:30px;padding:4px 10px;font-size:12px;display:inline-block}
section{margin-top:18px;border:1px solid #273950;border-radius:14px;padding:18px;background:#152234}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}.metric{border:1px solid #263951;padding:11px;border-radius:10px}.metric strong{font-size:19px;display:block;margin-top:5px}
button{font:inherit;cursor:pointer;border:1px solid #428ecc;background:#164b75;color:#edf2f9;border-radius:9px;padding:9px 14px;margin:3px 6px 3px 0}
button:disabled{opacity:.5;cursor:default}button.ghost{background:transparent;border-color:#567188}
canvas{display:block;background:#071321;border-radius:9px;width:100%;height:210px;border:1px solid #344961;margin-top:10px}
input[type=file]{max-width:100%;margin:5px 0 10px}#log{white-space:pre-wrap;word-break:break-word;font:12px/1.5 ui-monospace,monospace;padding:12px;background:#071321;border-radius:9px;color:#bbe5ff;min-height:40px}a{color:#78bff3}footer{font-size:13px;color:#9db0c4;padding-top:24px}
</style>'''
markup=r'''<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MicroMusic PIC16F1503 — Assembler ROM Emulator</title>@@CSS@@</head>
<body><main>
<div class="pill">PIC16F1503 · реальный PIC HEX · 16 МГц</div>
<h1>MicroMusic: ассемблер PIC16F1503</h1>
<p class="muted">Четыре голоса: скрипка, пианино, гитара и ударные. При проверке выполняются настоящие 14-битные инструкции PIC. WAV предпросмотр получен исполнением того же HEX (не отдельным JS-синтезатором).</p>
<section><h2>Прослушивание</h2>
<button id="listen">▶ Слушать 14-секундный фрагмент</button><button id="stop" class="ghost">■ Стоп</button>
<canvas id="scope" width="840" height="210"></canvas>
<p class="muted">Центр сигнала — PWM=128. Несущая PWM3 — 62,5 кГц; звуковые отсчёты — 12,5 кГц; таймерное прерывание с постделителем 1:5.</p>
<div class="grid"><div class="metric">Осциллятор<strong>16 МГц</strong></div><div class="metric">PCM из PIC HEX<strong>12 500 Гц</strong></div><div class="metric">FLASH<strong>2 048 слов</strong></div><div class="metric">Аудиовыход<strong>RA2 / PWM3</strong></div></div>
</section>
<section><h2>Исполнение PIC HEX по инструкциям</h2>
<p class="muted">Встроен исходный машинный код. Можно загрузить другой Intel HEX PIC16F1503. Проверка запускает процессор, моделирует PWM3 и Timer2 и показывает полученные от процессора отсчёты.</p>
<label>Загрузить HEX: <input id="file" type="file" accept=".hex,.HEX,text/plain"></label>
<div><button id="check">Запустить 0,5 секунды PIC-кода</button><button id="reset" class="ghost">Вернуть встроенный HEX</button></div>
<div id="log">Ожидается запуск теста.</div>
</section>
<footer>Источник инструментов: <a href="https://github.com/Witali/MicroMusic">Witali/MicroMusic</a>. Регистры, команды и периферия: Microchip PIC16(L)F1503 DS40001607D. Это частичный эмулятор ядра и используемых периферийных блоков, а не полная модель всех аналоговых характеристик кристалла.</footer>
</main><script>@@JS@@</script></body></html>'''
script=r'''
@@CORE@@
const BUILTIN_HEX=@@HEX@@;
const PREVIEW_DATA=@@PCM@@;
const RATE=12500, PWM_CARRIER=62500;
let audioContext=null,audioNode=null,currentHex=BUILTIN_HEX;
function fromB64(s){const raw=atob(s),v=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)v[i]=raw.charCodeAt(i);return v;}
const preview=fromB64(PREVIEW_DATA);
function scope(samples){const canvas=document.getElementById('scope');const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;
 ctx.fillStyle='#071321';ctx.fillRect(0,0,w,h);
 for(let k=0;k<=4;k++){const y=k*h/4;ctx.strokeStyle=k===2?'#d2bc6f':'#26394f';ctx.lineWidth=k===2?1.4:1;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();}
 ctx.beginPath();ctx.strokeStyle='#61c3ed';ctx.lineWidth=1.8;

 for(let x=0;x<w;x++){const v=samples[Math.min(samples.length-1,Math.floor(x*(samples.length-1)/(w-1)))]??128;
 const y=(255-v)*h/255;if(x===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}
 ctx.stroke();ctx.fillStyle='#bfd3e7';ctx.font='13px system-ui';ctx.fillText('255',8,16);ctx.fillText('128',8,h/2-8);ctx.fillText('0',8,h-8);
}
scope(preview.subarray(1000,1500));
document.getElementById('listen').onclick=async()=>{
 if(audioNode){try{audioNode.stop();}catch(_){}}
 audioContext??=new (window.AudioContext||window.webkitAudioContext)();await audioContext.resume();
 const audio=audioContext.createBuffer(1,preview.length,RATE),dst=audio.getChannelData(0);
 for(let i=0;i<preview.length;i++)dst[i]=(preview[i]-128)/128;
 audioNode=audioContext.createBufferSource();audioNode.buffer=audio;audioNode.connect(audioContext.destination);audioNode.start();
 scope(preview.subarray(3500,4000));
};
document.getElementById('stop').onclick=()=>{if(audioNode){try{audioNode.stop();}catch(_){}}};
document.getElementById('reset').onclick=()=>{currentHex=BUILTIN_HEX;document.getElementById('file').value='';document.getElementById('log').textContent='Возвращён встроенный HEX.';};
document.getElementById('file').onchange=async(e)=>{
 const file=e.target.files?.[0];if(!file)return;
 try{const content=await file.text();readPIC16Hex(content);currentHex=content;document.getElementById('log').textContent=`Загружен ${file.name} (${file.size} байт).`;}catch(err){document.getElementById('log').textContent=String(err)}
};
document.getElementById('check').onclick=async()=>{
 const button=document.getElementById('check'),log=document.getElementById('log');button.disabled=true;log.textContent='PIC CPU работает...';
 try{
 await new Promise(r=>setTimeout(r,20));
 const cpu=new PIC16F1503(readPIC16Hex(currentHex));
 const samples=PWM_CARRIER/2, t0=performance.now();
 // Yield periodically, so browsers can repaint while CPU executes.
 while(cpu.samples.length<samples){for(let i=0;i<125000 && cpu.samples.length<samples;i++)cpu.step();await new Promise(r=>setTimeout(r,0));}
 const out=cpu.samples.filter((_,idx)=>idx%5===4);
 let sum=0,min=255,max=0;for(const x of out){sum+=x;min=Math.min(min,x);max=Math.max(max,x);}
 scope(out.subarray?out.subarray(500,1000):out.slice(500,1000));
 log.textContent=`Проверено: ${out.length} звуковых отсчётов (${(out.length/RATE).toFixed(3)} с)\nИнструкций: ${cpu.totalInstructions.toLocaleString('ru-RU')}\nPIC циклов: ${cpu.cycle.toLocaleString('ru-RU')}\nTimer2 IRQ: ${cpu.irqCount}\nPWM3 PR2: ${cpu.mem[0x1b]}\nPWM3CON: 0x${cpu.mem[0x619].toString(16)}\nМинимум / максимум: ${min} / ${max}\nСредний PWM: ${(sum/out.length).toFixed(2)}\nОпустошений очереди: ${cpu.mem[0x60]}\nВремя эмуляции: ${((performance.now()-t0)/1000).toFixed(2)} с`;
 }catch(err){log.textContent='Ошибка выполнения PIC HEX: '+err.stack;}
 finally{button.disabled=false;}
};
'''
script=script.replace('@@CORE@@',core).replace('@@HEX@@',repr(hextext)).replace('@@PCM@@',repr(preview))
content=markup.replace('@@CSS@@',css).replace('@@JS@@',script)
(r/'web/player.html').write_text(content,encoding='utf8')
print('Wrote HTML',len(content),'bytes / actual sample audio',len(audio))
