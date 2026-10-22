import { parseHex } from './lib/hex.js';
import { RealtimeMonitor } from './lib/realtime.js';
const $ = id => document.getElementById(id);
const formatHex = (value, length=2) => value.toString(16).toUpperCase().padStart(length,'0');
const canvas = $('wave'), ctx = canvas.getContext('2d');
let catalog, selected, runtime, runtimeReady=false, connectedRuntime, playing=false, busy=false;
let audio, output, scope=new Float32Array(512), headroom=0;
let session=0, hasPlayed=false, realtime;
let lastScopeDraw=-Infinity, scopeDrawTimer;

function showError(message) { $('error').textContent = message; $('error').hidden = !message; }
function audioControls() { return {cutoff:+$('cutoff').value,volume:+$('volume').value}; }
function selectedEngine() { return document.querySelector('input[name="engine"]:checked').value; }
function transport() {
  document.body.dataset.playing = String(playing);
  $('play-icon').textContent = playing ? 'Ⅱ' : '▶';
  $('play-label').textContent = playing ? 'Пауза' : 'Слушать';
  $('play').disabled = !runtimeReady || busy;
  $('run-status').textContent = busy ? 'Подключение звука…' : playing ? 'Воспроизведение' : runtimeReady ? (hasPlayed ? 'Пауза' : 'Готов к запуску') : 'Загрузка образа…';
}
function draw() {
  const now=performance.now(), wait=1000/30-(now-lastScopeDraw);
  if(wait>0){
    if(scopeDrawTimer===undefined)scopeDrawTimer=setTimeout(()=>{scopeDrawTimer=undefined;draw();},wait);
    return;
  }
  if(scopeDrawTimer!==undefined){clearTimeout(scopeDrawTimer);scopeDrawTimer=undefined;}
  lastScopeDraw=now;
  const ratio = window.devicePixelRatio || 1, width=canvas.clientWidth, height=canvas.clientHeight;
  if (!width || !height) return;
  if (canvas.width !== Math.round(width*ratio) || canvas.height !== Math.round(height*ratio)) { canvas.width=Math.round(width*ratio); canvas.height=Math.round(height*ratio); }
  ctx.setTransform(ratio,0,0,ratio,0,0); ctx.fillStyle='#0e140e'; ctx.fillRect(0,0,width,height);
  ctx.lineWidth=1; ctx.strokeStyle='#232e21'; ctx.beginPath();
  for (let x=0;x<width;x+=width/12) { ctx.moveTo(x,0); ctx.lineTo(x,height); }
  for (let y=0;y<=height;y+=height/4) { ctx.moveTo(0,y); ctx.lineTo(width,y); } ctx.stroke();
  ctx.strokeStyle='#647b45'; ctx.setLineDash([4,5]); ctx.beginPath(); ctx.moveTo(0,height/2); ctx.lineTo(width,height/2); ctx.stroke(); ctx.setLineDash([]);
  ctx.strokeStyle='#c9ef86'; ctx.lineWidth=1.5; ctx.beginPath();
  for (let i=0;i<scope.length;i++) { const x=i/(scope.length-1)*width,y=height/2-scope[i]*height*.43; if (!i) ctx.moveTo(x,y); else ctx.lineTo(x,y); } ctx.stroke();
}
new ResizeObserver(draw).observe(canvas);
const registerNodes=Array.from({length:32},(_,i) => {
  const box=document.createElement('div'); box.className='register';
  const label=document.createElement('span'); label.textContent='R'+i;
  const value=document.createElement('strong'); value.textContent='00'; box.append(label,value); $('registers').append(box); return value;
});
function stateUI(state) {
  registerNodes.forEach((node,i) => { node.textContent=formatHex(state.registers[i]); });
  $('cpu-status').textContent=`PC ${formatHex(state.pc,4)} · ${state.cycles.toLocaleString('ru')} тактов · ${state.irqs.toLocaleString('ru')} IRQ`;
  $('isr').textContent=state.maxISR ? state.maxISR+' т.' : '—';
  $('lost').textContent=state.lost.toLocaleString('ru');
}
function renderCatalog() {
  const query=$('search').value.toLocaleLowerCase('ru').trim();
  const entries=catalog.entries.filter(e => `${e.title} ${e.description} ${e.id} ${e.flashBytes}`.toLocaleLowerCase('ru').includes(query));
  $('catalog').replaceChildren(); $('catalog-count').textContent=query ? `${entries.length} / ${catalog.entries.length}` : catalog.entries.length;
  for (const entry of entries) {
    const item=document.createElement('div'); item.setAttribute('role','listitem');
    const button=document.createElement('button'); button.className='firmware-card'; button.dataset.firmware=entry.id;
    button.setAttribute('aria-pressed',String(selected?.id===entry.id));
    const number=document.createElement('span'); number.className='card-number'; number.textContent=entry.order;
    const body=document.createElement('span'); body.className='card-body';
    const name=document.createElement('strong'); name.textContent=entry.title;
    const voices=entry.voices??4;
    const meta=document.createElement('span'); meta.className='card-meta'; meta.textContent=entry.kind==='speech'
      ? `${entry.flashBytes} Б Flash · речь 7,5 кГц`
      : `${entry.flashBytes} Б Flash${entry.eepromBytes ? ' + 64 Б EEPROM' : ''} · ${entry.status==='experimental' ? 'ТЕСТ' : `${voices} ${voices===1?'ОСНОВНОЙ':'ОСНОВНЫХ'}`}${entry.releaseTailSlots ? ` · ${entry.releaseTailSlots} РЕЗЕРВНЫХ` : ''}`;
    const arrow=document.createElement('span'); arrow.className='card-arrow'; arrow.textContent=selected?.id===entry.id ? '●' : '↗'; arrow.setAttribute('aria-hidden','true');
    body.append(name,meta); button.append(number,body,arrow); button.onclick=()=>load(entry); item.append(button); $('catalog').append(item);
  }
  if (!entries.length) { const p=document.createElement('p'); p.className='empty'; p.textContent='Ничего не найдено. Попробуйте другое название.'; $('catalog').append(p); }
}
function connectAudio() {
  if (!output || !runtimeReady || connectedRuntime===runtime) return;
  const channel=new MessageChannel();
  output.port.postMessage({type:'connect',session,port:channel.port1},[channel.port1]);
  runtime.postMessage({type:'audio-port',port:channel.port2,sampleRate:audio.sampleRate,controls:audioControls()},[channel.port2]);
  connectedRuntime=runtime;
  document.querySelector('.scope-scale').textContent=(4096/audio.sampleRate*1000).toFixed(0)+' мс';
}
function pause() { playing=false; output?.port.postMessage({type:'playing',value:false}); transport(); }
function load(entry) {
  pause(); showError(''); busy=false; runtimeReady=false; runtime?.terminate(); connectedRuntime=null;
  session++; hasPlayed=false;
  output?.port.postMessage({type:'disconnect'});
  selected=entry; headroom=0; scope.fill(0); draw();
  $('elapsed').textContent='00:00.0'; $('average').textContent='128.0'; $('headroom').textContent='—';
  $('tempo').textContent='100.0%'; $('lag').textContent='0.0 мс'; realtime?.resetAnchor();
  delete $('tempo').dataset.wallMs; delete $('tempo').dataset.audioMs;
  $('selected-order').textContent=entry.order; $('selected-title').textContent=entry.title; $('selected-description').textContent=entry.description;
  const flashSource=entry.source||'data:text/plain;charset=utf-8,'+encodeURIComponent(entry.flashHex);
  $('rom-name').textContent=`attiny13a-${entry.id}.hex`; $('rom-details').textContent=`${entry.flashBytes} / 1024 Б Flash · ${entry.eepromBytes} / 64 Б EEPROM · ${(entry.sampleHz/1000).toLocaleString('ru')} кГц отсчёты`;
  $('rom-name').href=flashSource; $('rom-name').download=`attiny13a-${entry.id}.hex`;
  $('rom-hash').textContent=entry.flashSha256.slice(0,16)+'…'; $('rom-hash').title='SHA-256 Flash: '+entry.flashSha256;
  $('rom-size').textContent=entry.flashBytes+' байт';
  $('original-player').hidden=!entry.originalPlayer; if(entry.originalPlayer)$('original-player').href=entry.originalPlayer;
  $('wav-link').hidden=!entry.preview; if (entry.preview) $('wav-link').href=entry.preview;
  $('reference-wav').hidden=!entry.reference; if(entry.reference)$('reference-wav').href=entry.reference;
  $('download-eeprom').hidden=!entry.eepromHex; $('reset').disabled=false;
  for(const [id,source,suffix] of [['download',flashSource,''],['download-eeprom',entry.eepromSource,'-eeprom']]){
    const link=$(id);if(source){link.href=source;link.download=`attiny13a-${entry.id}${suffix}.hex`;link.removeAttribute('aria-disabled');}
  }
  const bytes=parseHex(entry.flashHex); $('memory').textContent=Array.from({length:8},(_,line)=>formatHex(line*16,4)+'  '+Array.from(bytes.subarray(line*16,line*16+16),x=>formatHex(x)).join(' ')).join('\n');
  const url=new URL(location.href); url.searchParams.set('firmware',entry.id); history.replaceState(null,'',url);
  renderCatalog(); transport();
  const worker=new Worker(new URL('./worker.js',import.meta.url),{type:'module'}); runtime=worker;
  worker.onmessage=({data})=>{
    if (runtime!==worker) return;
    if (data.type==='ready') { runtimeReady=true; stateUI(data.state); connectAudio(); transport(); }
    if (data.type==='state') {
      stateUI(data.state); scope=data.scope; draw(); $('average').textContent=data.averagePWM.toFixed(1);
      headroom=headroom ? headroom*.8+data.headroom*.2 : data.headroom; $('headroom').textContent=headroom.toFixed(1)+'×';
    }
    if (data.type==='error') { runtimeReady=false; pause(); showError('Ошибка эмуляции: '+data.message); }
  };
  worker.onerror=event=>{ if (runtime===worker) { runtimeReady=false; pause(); showError('Не удалось запустить AVR-эмулятор: '+event.message); } };
  worker.postMessage({type:'init',entry,engine:selectedEngine(),sampleRate:audio?.sampleRate||48000,controls:audioControls()});
}
async function ensureAudio() {
  if (audio) { await audio.resume(); return; }
  const Context=window.AudioContext||window.webkitAudioContext;
  if (!Context) throw new Error('Этот браузер не поддерживает Web Audio.');
  const context=new Context({latencyHint:'playback'});
  try {
    if (!context.audioWorklet) throw new Error('AudioWorklet недоступен. Откройте страницу через localhost или HTTPS.');
    await context.audioWorklet.addModule(new URL('./audio-worklet.js',import.meta.url));
    audio=context; realtime=new RealtimeMonitor(audio.sampleRate); output=new AudioWorkletNode(audio,'firmware-output',{numberOfInputs:0,numberOfOutputs:1,outputChannelCount:[1]});
    output.connect(audio.destination);
    output.port.onmessage=({data})=>{
      if (data.type!=='position' || data.session!==session || !playing) return;
      const timing=realtime.observe(data,performance.now()),seconds=timing.seconds;
      $('elapsed').textContent=String(Math.floor(seconds/60)).padStart(2,'0')+':'+(seconds%60).toFixed(1).padStart(4,'0');
      $('tempo').textContent=timing.tempoPercent.toFixed(1)+'%'; $('lag').textContent=timing.lagMs.toFixed(1)+' мс';
      $('tempo').dataset.wallMs=timing.wallMs.toFixed(3); $('tempo').dataset.audioMs=timing.audioMs.toFixed(3);
      if (data.underruns) $('run-status').textContent=`Воспроизведение · задержки звука: ${data.underruns}`;
    };
    output.onprocessorerror=()=>{ pause(); showError('Ошибка звукового потока. Обновите страницу для повторного запуска.'); };
    connectAudio(); await audio.resume();
  } catch (error) { await context.close(); audio=null; throw error; }
}
async function toggle() {
  if (!runtimeReady || busy) return;
  if (playing) { pause(); return; }
  const target=runtime; busy=true; transport(); showError('');
  try {
    await ensureAudio();
    if (target!==runtime) return;
    connectAudio(); realtime.resetAnchor(); playing=true; hasPlayed=true; output.port.postMessage({type:'playing',value:true});
  } catch (error) { showError('Не удалось включить звук: '+error.message); }
  finally { busy=false; transport(); }
}
$('play').onclick=toggle; $('reset').onclick=()=>load(selected); $('search').oninput=renderCatalog;
$('volume').oninput=()=>runtime?.postMessage({type:'controls',controls:audioControls()});
$('cutoff').onchange=()=>runtime?.postMessage({type:'controls',controls:audioControls()});
for (const choice of document.querySelectorAll('input[name="engine"]')) choice.onchange=()=>{ if (selected) load(selected); };
document.addEventListener('keydown',event=>{ if (event.code==='Space' && !event.repeat && !/INPUT|SELECT|TEXTAREA|BUTTON|A/.test(event.target.tagName)) { event.preventDefault(); toggle(); } });
window.addEventListener('pagehide',()=>{ runtime?.terminate(); audio?.close(); });
try {
  const speech=new URL(location.href).searchParams.get('collection')==='hq4';
  if(speech){
    document.title='MicroMusic / ATtiny13A — речь HQ4';
    document.querySelector('.intro .eyebrow').textContent='ATtiny13A / РЕЧЬ ИЗ МАШИННОГО КОДА';
    document.querySelector('.intro h1').textContent='Речь в одном килобайте.';
    document.querySelector('.subtitle').textContent='MiniLPC HQ4: три фразы и вариант с максимальным STOI.';
    document.querySelector('.library h2').textContent='Как звучит HQ4?';
    document.querySelector('.library-caption').textContent='Сохранённые прошивки. Переключайте JS и WASM для сравнения.';
    document.querySelector('.source-only').hidden=true;
    const history=document.querySelector('.header-link');history.href='../ATtiny13A/Sound/AUDIO_REFERENCES.md';history.textContent='Звуковые эталоны ↗';
    $('original-player').textContent='Плеер из ChatGPT ↗';
    $('speech-audit').hidden=false;
    document.querySelector('footer span:last-child').textContent='MiniLPC HQ4 · 4 образа · Worker + AudioWorklet';
  }
  // Public speech playback needs only the source-built catalog. Local listening
  // can additionally use restored original WAVs and the archived ChatGPT player.
  let response;
  if(speech&&['127.0.0.1','localhost'].includes(location.hostname)) {
    response=await fetch('../build/hq4-preview/firmware.json');
  }
  if(!response?.ok)response=await fetch(speech?'./hq4-firmware.json':'./firmware.json');
  if (!response.ok) throw new Error('HTTP '+response.status);
  catalog=await response.json();
  const id=new URL(location.href).searchParams.get('firmware')||catalog.defaultId;
  load(catalog.entries.find(e=>e.id===id)||catalog.entries.find(e=>e.id===catalog.defaultId));
} catch (error) { showError('Не удалось загрузить каталог прошивок. Обновите страницу или проверьте подключение. '+error.message); }
draw();
