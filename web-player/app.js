import { parseHex } from './lib/hex.js';
import { RealtimeMonitor } from './lib/realtime.js';
const $ = id => document.getElementById(id);
const formatHex = (value, length=2) => value.toString(16).toUpperCase().padStart(length,'0');
const canvas = $('wave');
const originalAudio = $('original-audio');
let catalog, selected, runtime, runtimeReady=false, connectedRuntime, playing=false, busy=false;
let audio, output, scopes=[new Float32Array(512)], headroom=0;
let session=0, hasPlayed=false, completed=false, realtime;
let playAttempt=0, busyAttempt=0;
let lastScopeDraw=-Infinity, scopeDrawTimer;
let originalLoading=false, originalAttempt=0;
const speechCollection=new URL(location.href).searchParams.get('collection')==='hq4';
const tiny88Boards={
  'bare-8mhz':{cpuHz:8000000,catalog:'./firmware-attiny88.json'},
  'mh-et-live-16mhz':{cpuHz:16000000,catalog:'./firmware-attiny88-16mhz.json'},
};
const boardId=value=>Object.hasOwn(tiny88Boards,value)?value:'bare-8mhz';
let currentDevice='attiny13a', currentBoard=boardId(new URL(location.href).searchParams.get('board')), deviceRequest=0;

function showError(message) { $('error').textContent = message; $('error').hidden = !message; }
function audioControls() {
  return {cutoff:+$('cutoff').value,volume:+$('volume').value};
}
function selectedEngine() { return document.querySelector('input[name="engine"]:checked').value; }
function deviceUI(device) {
  const tiny88=device==='attiny88', name=tiny88?'ATtiny88':'ATtiny13A';
  const micronucleus=tiny88&&currentBoard==='mh-et-live-16mhz';
  const mhz=tiny88?tiny88Boards[currentBoard].cpuHz/1000000:9.6;
  document.body.dataset.device=device;
  document.body.dataset.board=tiny88?currentBoard:'';
  $('device-select').value=device;
  $('device-control').hidden=speechCollection;
  $('board-control').hidden=!tiny88||speechCollection;
  $('board-select').value=currentBoard;
  $('board-note').textContent=micronucleus?'Внешний генератор · загрузка по USB · тембры во Flash':'Внутренний RC · загрузка Flash и EEPROM через ISP';
  $('tiny88-clock').textContent=mhz+' MHz · '+(micronucleus?'MH-ET LIVE':'PDIP-28');
  $('chip-attiny13a').hidden=tiny88; $('chip-attiny88').hidden=!tiny88;
  $('tiny88-power').hidden=!tiny88;
  $('tiny88-power').textContent=micronucleus?'MH-ET LIVE: питание по USB · моно / R — D10 · L — D9.':'PDIP-28: питание VCC 7 и AVCC 20 · земля GND 8 и 22.';
  document.querySelector('.tiny88-vcc').textContent=micronucleus?'USB 5 В':'VCC 7';
  document.querySelector('.tiny88-gnd').textContent=micronucleus?'GND':'GND 8';
  $('machine-memory').textContent=tiny88?'8':'1';
  $('machine-details').textContent=tiny88?`512 Б SRAM · 64 Б EEPROM · ${mhz} МГц`:'64 Б SRAM · 64 Б EEPROM · 9,6 МГц';
  $('fuses').setAttribute('aria-label',micronucleus?'Штатные настройки платы MH-ET LIVE':'Рекомендуемые фьюзы '+name);
  $('fuse-low').textContent=micronucleus?'—':tiny88?'0xEE':'0x7A';
  $('fuse-high').textContent=micronucleus?'—':tiny88?'0xDF':'0xFF';
  $('fuse-high-note').textContent=micronucleus?'сохранить фьюзы платы':tiny88?'SPI включён · RESET включён':'сохранить заводской';
  $('fuse-extended').hidden=!tiny88; $('fuse-extended-value').textContent=micronucleus?'—':'0xFF';
  $('fuse-clock-value').textContent=micronucleus?'Внешний генератор · 16 МГц':'Внутренний RC · '+(tiny88?'8':'9,6')+' МГц';
  $('fuse-clock-note').textContent=micronucleus?'Штатный Micronucleus · делитель /1 в прошивке':'CKDIV8 отключён · делитель /1';
  $('fuse-datasheet').href=tiny88?'https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf':'https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf';
  $('fuse-datasheet').textContent='Фьюзы в datasheet, §'+(tiny88?'20.2':'17.2')+' ↗';
  for(const choice of document.querySelectorAll('input[name="engine"]'))choice.disabled=tiny88&&!['js','wasm'].includes(choice.value);
  if(document.querySelector('input[name="engine"]:checked').disabled){
    for(const choice of document.querySelectorAll('input[name="engine"]'))choice.checked=choice.value==='wasm';
  }
  $('package-file').disabled=tiny88;
  $('engine-note').textContent='При смене — сброс на начало.';
  if(!speechCollection) {
    document.title=`MicroMusic / ${name} — плеер прошивок`;
    document.querySelector('.intro .eyebrow').textContent=name+' / МУЗЫКА ИЗ МАШИННОГО КОДА';
    document.querySelector('.library h2').textContent=tiny88?'Музыка на ATtiny88':'Как звучит один килобайт?';
    document.querySelector('.source-only').hidden=tiny88;
    const history=document.querySelector('.header-link');
    history.href=tiny88?'https://github.com/Witali/MicroMusic/blob/main/ATtiny88/Music/HARDWARE_REVIEW_RU.md':'../ATtiny13A/Music/DEVELOPMENT_HISTORY_RU.txt';
    history.textContent=tiny88?'Подключение ATtiny88 ↗':'История разработки ↗';
  }
}
async function switchDevice(device,board=currentBoard) {
  const request=++deviceRequest;
  device=device==='attiny88'&&!speechCollection?'attiny88':'attiny13a';
  board=boardId(board);
  try {
    const response=await fetch(device==='attiny88'?tiny88Boards[board].catalog:'./firmware.json');
    if(!response.ok)throw new Error('HTTP '+response.status);
    const next=await response.json();
    if(request!==deviceRequest)return;
    const requested=selected?.id||new URL(location.href).searchParams.get('firmware')||next.defaultId;
    const id=next.aliases?.[requested]??requested;
    const entry=next.entries.find(e=>e.id===id)||next.entries.find(e=>e.id===next.defaultId);
    if(!entry)throw new Error('В каталоге нет доступных прошивок.');
    if(entry.cpuHz!==(device==='attiny88'?tiny88Boards[board].cpuHz:9600000))throw new Error('Частота прошивки не соответствует выбранной плате.');
    parseHex(entry.flashHex,device==='attiny88'?(board==='mh-et-live-16mhz'?6012:8192):1024);
    catalog=next; currentDevice=device;if(device==='attiny88')currentBoard=board;deviceUI(device);load(entry);
  } catch(error) {
    if(request!==deviceRequest)return;
    $('device-select').value=currentDevice;
    $('board-select').value=currentBoard;
    showError('Не удалось загрузить каталог прошивок. '+error.message);
  }
}
function transport() {
  const originalPlaying=!originalAudio.paused&&!originalAudio.ended;
  document.body.dataset.playing = String(playing);
  document.body.dataset.originalPlaying = String(originalPlaying);
  $('play-icon').textContent = playing ? 'Ⅱ' : '▶';
  $('play-label').textContent = playing ? 'Пауза' : completed ? 'Ещё раз' : 'Слушать';
  $('play').disabled = !runtimeReady || busy;
  $('play-original').textContent=originalPlaying||originalLoading ? 'Остановить оригинал' : 'Прослушать оригинал';
  $('play-original').setAttribute('aria-pressed',String(originalPlaying||originalLoading));
  $('run-status').textContent = originalLoading ? 'Загрузка оригинала…' : originalPlaying ? 'Оригинальная запись' : busy ? 'Подключение звука…' : playing ? 'Воспроизведение' : completed ? 'Завершено' : runtimeReady ? (hasPlayed ? 'Пауза' : 'Готов к запуску') : 'Загрузка образа…';
}
function draw() {
  const now=performance.now(), wait=1000/30-(now-lastScopeDraw);
  if(wait>0){
    if(scopeDrawTimer===undefined)scopeDrawTimer=setTimeout(()=>{scopeDrawTimer=undefined;draw();},wait);
    return;
  }
  if(scopeDrawTimer!==undefined){clearTimeout(scopeDrawTimer);scopeDrawTimer=undefined;}
  lastScopeDraw=now;
  drawWave(canvas,scopes[0],'#c9ef86');
  if(scopes[1])drawWave($('wave-right'),scopes[1],'#86d9ef');
}
function drawWave(canvas,scope,color){
  const ctx=canvas.getContext('2d');
  const ratio = window.devicePixelRatio || 1, width=canvas.clientWidth, height=canvas.clientHeight;
  if (!width || !height) return;
  if (canvas.width !== Math.round(width*ratio) || canvas.height !== Math.round(height*ratio)) { canvas.width=Math.round(width*ratio); canvas.height=Math.round(height*ratio); }
  ctx.setTransform(ratio,0,0,ratio,0,0); ctx.fillStyle='#0e140e'; ctx.fillRect(0,0,width,height);
  ctx.lineWidth=1; ctx.strokeStyle='#232e21'; ctx.beginPath();
  for (let x=0;x<width;x+=width/12) { ctx.moveTo(x,0); ctx.lineTo(x,height); }
  for (let y=0;y<=height;y+=height/4) { ctx.moveTo(0,y); ctx.lineTo(width,y); } ctx.stroke();
  ctx.strokeStyle='#647b45'; ctx.setLineDash([4,5]); ctx.beginPath(); ctx.moveTo(0,height/2); ctx.lineTo(width,height/2); ctx.stroke(); ctx.setLineDash([]);
  ctx.strokeStyle=color; ctx.lineWidth=1.5; ctx.beginPath();
  for (let i=0;i<scope.length;i++) { const x=i/(scope.length-1)*width,y=height/2-scope[i]*height*.43; if (!i) ctx.moveTo(x,y); else ctx.lineTo(x,y); } ctx.stroke();
}
new ResizeObserver(draw).observe(canvas);
new ResizeObserver(draw).observe($('wave-right'));
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
    const meta=document.createElement('span'); meta.className='card-meta'; meta.textContent=entry.kind==='package'?'FLASH + EEPROM · PB0 / PB1':entry.kind==='speech'
      ? `${entry.flashBytes} Б Flash${entry.eepromBytes ? ` + ${entry.eepromBytes} Б EEPROM` : ''} · речь 7,5 кГц`
      : `${entry.flashBytes} Б Flash${entry.eepromBytes ? ' + 64 Б EEPROM' : ''} · ${entry.status==='experimental' ? 'ТЕСТ' : `${voices} ${voices===1?'ОСНОВНОЙ':'ОСНОВНЫХ'}`}${entry.releaseTailSlots ? ` · ${entry.releaseTailSlots} РЕЗЕРВНЫХ` : ''}${entry.audioChannels===2?' · СТЕРЕО L / R':''}`;
    const arrow=document.createElement('span'); arrow.className='card-arrow'; arrow.textContent=selected?.id===entry.id ? '●' : '↗'; arrow.setAttribute('aria-hidden','true');
    body.append(name,meta); button.append(number,body,arrow); button.onclick=()=>load(entry); item.append(button); $('catalog').append(item);
  }
  if (!entries.length) { const p=document.createElement('p'); p.className='empty'; p.textContent='Ничего не найдено. Попробуйте другое название.'; $('catalog').append(p); }
}
function connectAudio() {
  if (!output || !runtimeReady || connectedRuntime===runtime) return;
  const channel=new MessageChannel();
  output.port.postMessage({type:'connect',session,channels:selected.audioChannels||1,port:channel.port1},[channel.port1]);
  runtime.postMessage({type:'audio-port',port:channel.port2,sampleRate:audio.sampleRate,controls:audioControls()},[channel.port2]);
  connectedRuntime=runtime;
  document.querySelector('.scope-scale').textContent=(4096/audio.sampleRate*1000).toFixed(0)+' мс';
}
function pause() { playAttempt++; playing=false; output?.port.postMessage({type:'playing',value:false}); transport(); }
function stopOriginal() {
  originalAttempt++; originalLoading=false;
  originalAudio.pause(); originalAudio.currentTime=0; transport();
}
async function toggleOriginal() {
  if(selected?.kind!=='speech'||!selected.originalAudioUrl)return;
  if(originalLoading||!originalAudio.paused){stopOriginal();return;}
  pause(); showError('');
  const attempt=++originalAttempt; originalLoading=true; transport();
  try { await originalAudio.play(); }
  catch(error) {
    if(attempt===originalAttempt&&error.name!=='AbortError') {
      stopOriginal(); showError('Не удалось воспроизвести оригинальную запись: '+error.message);
    }
  } finally { if(attempt===originalAttempt){originalLoading=false;transport();} }
}
for(const event of ['playing','pause','ended'])originalAudio.addEventListener(event,transport);
originalAudio.addEventListener('error',()=>{
  if(selected?.originalAudioUrl){stopOriginal();showError('Не удалось загрузить оригинальную запись.');}
});
function load(entry,{autoplay=false}={}) {
  stopOriginal(); pause(); showError(''); busy=false; runtimeReady=false; runtime?.terminate(); connectedRuntime=null;
  session++; hasPlayed=false; completed=false;
  const autoplayAttempt=playAttempt;
  output?.port.postMessage({type:'disconnect'});
  selected=entry; headroom=0;
  deviceUI(currentDevice);
  if(entry.devicePackage){
    for(const choice of document.querySelectorAll('input[name="engine"]')){choice.disabled=choice.value!=='device';choice.checked=choice.value==='device';}
    const configuration=entry.deviceConfiguration;
    $('fuse-low').textContent='0x'+formatHex(configuration.fuseLow);
    $('fuse-high').textContent='0x'+formatHex(configuration.fuseHigh);
    $('fuse-high-note').textContent='из пакета';
    const clock=['Внешний источник','Внутренний RC','Внутренний RC','Внутренний 128 кГц'][configuration.fuseLow&3];
    $('fuse-clock-value').textContent=clock+' · '+(configuration.oscillatorHz/1000000).toLocaleString('ru')+' МГц';
    $('fuse-clock-note').textContent=configuration.fuseLow&16?'CKDIV8 отключён · делитель /1':'CKDIV8 включён · делитель /8';
  }
  const originalUrl=entry.kind==='speech' ? entry.originalAudioUrl : null;
  $('play-original').hidden=!originalUrl;
  // Mobile media decoders may reject the canonical recordings' 7500 Hz rate.
  // Keep the reference link canonical and play a resampled PCM listening copy.
  if(originalUrl)originalAudio.src=entry.originalPlaybackUrl||originalUrl;else originalAudio.removeAttribute('src');
  originalAudio.load(); originalAudio.volume=+$('volume').value;
  const stereo=entry.audioChannels===2;
  const tiny88=currentDevice==='attiny88', timer=tiny88?'1':'0';
  const micronucleus=tiny88&&currentBoard==='mh-et-live-16mhz';
  document.body.dataset.stereo=String(stereo);
  scopes=Array.from({length:stereo?2:1},()=>new Float32Array(512));
  $('stereo-output').hidden=!stereo;$('scope-right').hidden=!stereo;$('panorama').hidden=!stereo||!!entry.devicePackage;
  $('right-output-label').textContent=(stereo?'R · ':'')+(micronucleus?'PB2 / OC1B · D10':tiny88?'PB2 / OC1B · вывод 16':'PB1 / OC0B · вывод 6');
  $('right-output-label').title=micronucleus?'D10 на плате MH-ET LIVE':tiny88?'Вывод 16 в корпусе PDIP-28':'Вывод 6 в 8-выводных корпусах';
  $('left-output-label').textContent='L · '+(micronucleus?'PB1 / OC1A · D9':tiny88?'PB1 / OC1A · вывод 15':'PB0 / OC0A · вывод 5');
  $('left-output-label').title=micronucleus?'D9 на плате MH-ET LIVE':tiny88?'Вывод 15 в корпусе PDIP-28':'Вывод 5 в 8-выводных корпусах';
  $('audio-mode').textContent=stereo?'СТЕРЕО · 2 PWM-ВЫХОДА':'МОНО · 1 PWM-ВЫХОД';
  const physical=selectedEngine()==='device';
  $('scope-left-label').textContent=physical?(stereo?'L · PB0':'МОНО · PB1'):(stereo?`L · OCR${timer}A`:`МОНО · OCR${timer}B`);
  $('scope-right-label').textContent=physical?'R · PB1':`R · OCR${timer}B`;
  $('wave').setAttribute('aria-label',stereo?'Левый канал PWM до фильтра':'Осциллограмма PWM до фильтра');
  $('average-label').textContent=stereo?'СРЕДНИЙ PWM · L / R':'СРЕДНИЙ PWM';
  $(tiny88?'chip-attiny88':'chip-attiny13a').setAttribute('aria-label',tiny88
    ? micronucleus?'MH-ET LIVE Tiny88, 16 МГц: '+(stereo?'R — D10 / PB2, L — D9 / PB1':'моно — D10 / PB2'):'ATtiny88, PDIP-28, вид сверху: '+(stereo?'правый канал PB2 вывод 16, левый канал PB1 вывод 15':'выход PWM PB2 вывод 16')
    : 'ATtiny13A, вид сверху: '+(stereo?'правый канал PB1 вывод 6, левый канал PB0 вывод 5':'выход PWM PB1 вывод 6'));
  draw();
  $('elapsed').textContent='00:00.0'; $('average').textContent=stereo?'128.0 / 128.0':'128.0'; $('headroom').textContent='—';
  $('tempo').textContent='100.0%'; $('lag').textContent='0.0 мс'; realtime?.resetAnchor();
  delete $('tempo').dataset.wallMs; delete $('tempo').dataset.audioMs;
  $('selected-order').textContent=entry.order; $('selected-title').textContent=entry.title; $('selected-description').textContent=entry.description;
  if(entry.kind==='speech') {
    const research=entry.research||(entry.codec==='hq4-t'
      ? '../ATtiny13A/Sound/codec/timbre/README.md'
      : '../ATtiny13A/Sound/research/hq4-emulator-comparison.json');
    $('speech-audit').href=research.endsWith('.md')
      ? new URL(research,'https://github.com/Witali/MicroMusic/blob/main/web-player/').href : research;
    $('speech-audit').textContent=entry.codec==='tiny-period' ? 'Исследование речевого ядра ↗'
      : entry.codec==='hq4-t' ? 'Исследование HQ4-T ↗' : 'Сверка HQ4 ↗';
  }
  const flashSource=entry.source||'data:text/plain;charset=utf-8,'+encodeURIComponent(entry.flashHex);
  const capacity=micronucleus?6012:tiny88?8192:1024, prefix=micronucleus?'attiny88-mh-et-live-16mhz':currentDevice;
  $('rom-name').textContent=`${prefix}-${entry.id}.hex`; $('rom-details').textContent=`${entry.flashBytes} / ${capacity} Б Flash · ${entry.eepromBytes} / 64 Б EEPROM · ${(entry.sampleHz/1000).toLocaleString('ru')} кГц ${entry.kind==='speech'?'отсчёты':'PWM'}`;
  if(micronucleus)$('rom-details').textContent=`${entry.flashBytes} / ${capacity} Б приложения · тембры во Flash · ${(entry.sampleHz/1000).toLocaleString('ru')} кГц PWM`;
  if(entry.devicePackage)$('rom-details').textContent=`${entry.flashBytes} / ${capacity} Б Flash · ${entry.eepromBytes} / 64 Б EEPROM · пакет ATtiny13A`;
  $('rom-name').href=flashSource; $('rom-name').download=`${prefix}-${entry.id}.hex`;
  $('rom-hash').textContent=entry.flashSha256.slice(0,16)+'…'; $('rom-hash').title='SHA-256 Flash: '+entry.flashSha256;
  $('rom-size').textContent=entry.flashBytes+' байт';
  $('original-player').hidden=!entry.originalPlayer; if(entry.originalPlayer)$('original-player').href=entry.originalPlayer;
  $('wav-link').hidden=!entry.preview; if (entry.preview) $('wav-link').href=entry.preview;
  const reference=originalUrl||entry.reference;
  $('reference-wav').hidden=!reference; if(reference)$('reference-wav').href=reference;
  $('download-eeprom').hidden=!entry.eepromHex; $('reset').disabled=false;
  $('board-upload').hidden=!micronucleus;
  $('upload-command').textContent=`micronucleus --run ${prefix}-${entry.id}.hex`;
  $('download').textContent=micronucleus?'↓ HEX для Micronucleus':'↓ Flash HEX';
  const eepromSource=entry.eepromSource||(entry.eepromHex ? 'data:text/plain;charset=utf-8,'+encodeURIComponent(entry.eepromHex) : null);
  for(const [id,source,suffix] of [['download',flashSource,''],['download-eeprom',eepromSource,'-eeprom']]){
    const link=$(id);if(source){link.href=source;link.download=`${prefix}-${entry.id}${suffix}.hex`;link.removeAttribute('aria-disabled');}
  }
  const bytes=parseHex(entry.flashHex,capacity); $('memory').textContent=Array.from({length:8},(_,line)=>formatHex(line*16,4)+'  '+Array.from(bytes.subarray(line*16,line*16+16),x=>formatHex(x)).join(' ')).join('\n');
  const url=new URL(location.href); url.searchParams.set('firmware',entry.id);
  if(tiny88)url.searchParams.set('device','attiny88');else url.searchParams.delete('device');
  if(micronucleus)url.searchParams.set('board',currentBoard);else url.searchParams.delete('board');
  history.replaceState(null,'',url);
  renderCatalog(); transport();
  const worker=new Worker(new URL('./worker.js?v=20261025-board-um88',import.meta.url),{type:'module'}); runtime=worker;
  worker.onmessage=({data})=>{
    if (runtime!==worker) return;
    if (data.type==='ready') {
      runtimeReady=true; stateUI(data.state); connectAudio(); transport();
      if(autoplay&&autoplayAttempt===playAttempt)toggle();
    }
    if (data.type==='state') {
      stateUI(data.state); scopes=data.scopes; draw(); $('average').textContent=data.averages.map(x=>x.toFixed(1)).join(' / ');
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
    audio=context; realtime=new RealtimeMonitor(audio.sampleRate); output=new AudioWorkletNode(audio,'firmware-output',{numberOfInputs:0,numberOfOutputs:1,outputChannelCount:[2]});
    output.connect(audio.destination);
    output.port.onmessage=({data})=>{
      if (data.type!=='position' || data.session!==session || !playing) return;
      const timing=realtime.observe(data,performance.now());
      const duration=selected.playOnce ? selected.phraseSamples/selected.sampleHz : Infinity;
      const seconds=Math.min(timing.seconds,duration);
      $('elapsed').textContent=String(Math.floor(seconds/60)).padStart(2,'0')+':'+(seconds%60).toFixed(1).padStart(4,'0');
      $('tempo').textContent=timing.tempoPercent.toFixed(1)+'%'; $('lag').textContent=timing.lagMs.toFixed(1)+' мс';
      $('tempo').dataset.wallMs=timing.wallMs.toFixed(3); $('tempo').dataset.audioMs=timing.audioMs.toFixed(3);
      if(timing.seconds>=duration){completed=true;pause();return;}
      if (data.underruns) $('run-status').textContent=`Воспроизведение · задержки звука: ${data.underruns}`;
    };
    output.onprocessorerror=()=>{ pause(); showError('Ошибка звукового потока. Обновите страницу для повторного запуска.'); };
    connectAudio(); await audio.resume();
  } catch (error) { await context.close(); audio=null; throw error; }
}
async function toggle() {
  if (!runtimeReady || busy) return;
  if (playing) { pause(); return; }
  if (completed) { load(selected,{autoplay:true}); return; }
  stopOriginal();
  const target=runtime,attempt=++playAttempt; busyAttempt=attempt; busy=true; transport(); showError('');
  try {
    await ensureAudio();
    if (target!==runtime||attempt!==playAttempt) return;
    connectAudio(); realtime.resetAnchor(); playing=true; hasPlayed=true; output.port.postMessage({type:'playing',value:true});
  } catch (error) { if(target===runtime&&attempt===playAttempt)showError('Не удалось включить звук: '+error.message); }
  finally { if(busyAttempt===attempt){busy=false;transport();} }
}
$('play').onclick=toggle; $('play-original').onclick=toggleOriginal; $('reset').onclick=()=>load(selected); $('search').oninput=renderCatalog;
$('volume').oninput=()=>{originalAudio.volume=+$('volume').value;runtime?.postMessage({type:'controls',controls:audioControls()});};
$('cutoff').onchange=()=>runtime?.postMessage({type:'controls',controls:audioControls()});
for (const choice of document.querySelectorAll('input[name="engine"]')) choice.onchange=()=>{
  if (selected) load(selected);
};
$('device-select').onchange=()=>switchDevice($('device-select').value);
$('board-select').onchange=()=>switchDevice('attiny88',$('board-select').value);
$('package-file').onchange=async event=>{
  const file=event.target.files[0];if(!file)return;
  try{
    if(file.size>16*1024*1024)throw Error('Пакет превышает 16 МБ');
    const {packageEntry}=await import('./lib/package-entry.js');
    const entry=await packageEntry(await file.text(),{name:file.name});
    catalog.entries=catalog.entries.filter(e=>e.kind!=='package');catalog.entries.push(entry);
    $('search').value='';load(entry);
  }catch(error){showError('Не удалось открыть пакет: '+error.message);}
  finally{event.target.value='';}
};
document.addEventListener('keydown',event=>{ if (event.code==='Space' && !event.repeat && !/INPUT|SELECT|TEXTAREA|BUTTON|A/.test(event.target.tagName)) { event.preventDefault(); toggle(); } });
window.addEventListener('pagehide',()=>{ originalAudio.pause(); runtime?.terminate(); audio?.close(); });
try {
  const speech=speechCollection;
  deviceUI('attiny13a');
  if(speech){
    document.title='MicroMusic / ATtiny13A — речевые кодеки';
    document.querySelector('.intro .eyebrow').textContent='ATtiny13A / РЕЧЬ ИЗ МАШИННОГО КОДА';
    document.querySelector('.intro h1').textContent='Речь в одном килобайте.';
    document.querySelector('.subtitle').textContent='Три фразы — три выбранных варианта. Сравните прошивку с оригиналом.';
    document.querySelector('.library h2').textContent='Выберите фразу';
    document.querySelector('.library-caption').textContent='Слушайте речь из прошивки и сравнивайте с исходной записью.';
    document.querySelector('.source-only').hidden=true;
    const history=document.querySelector('.header-link');history.href='https://github.com/Witali/MicroMusic/blob/main/ATtiny13A/Sound/AUDIO_REFERENCES.md';history.textContent='Звуковые эталоны ↗';
    $('original-player').textContent='Плеер из ChatGPT ↗';
    $('speech-audit').hidden=false;
    document.querySelector('footer span:last-child').textContent='Речевые кодеки · Worker + AudioWorklet';
  }
  if(!speech) {
    await switchDevice(new URL(location.href).searchParams.get('device'));
  } else {
  // Original recordings are shared public assets. Local listening can also use
  // restored emulator previews and the archived ChatGPT player.
  const response=await fetch(speech?'./hq4-firmware.json?v=20261023-mobile-original':'./firmware.json');
  if (!response.ok) throw new Error('HTTP '+response.status);
  catalog=await response.json();
  if(speech)document.querySelector('footer span:last-child').textContent=`Речевые кодеки · ${catalog.entries.length} фразы · Worker + AudioWorklet`;
  if(speech&&['127.0.0.1','localhost'].includes(location.hostname)) {
    try {
      const localResponse=await fetch('../build/hq4-preview/firmware.json');
      if(localResponse.ok) {
        const local=await localResponse.json();
        for(const entry of catalog.entries) {
          const same=local.entries.find(e=>e.id===entry.id&&e.flashSha256===entry.flashSha256);
          const reference=same||local.entries.find(e=>e.id==='hq4-'+entry.audioReferenceId);
          if(same?.preview)entry.preview=same.preview;
          if(reference?.reference)entry.reference=reference.reference;
          if(reference?.originalPlayer)entry.originalPlayer=reference.originalPlayer;
        }
      }
    } catch { /* Optional private listening assets must not hide public firmware. */ }
  }
  const requested=new URL(location.href).searchParams.get('firmware')||catalog.defaultId;
  const id=catalog.aliases?.[requested]??requested;
  load(catalog.entries.find(e=>e.id===id)||catalog.entries.find(e=>e.id===catalog.defaultId));
  }
} catch (error) { showError('Не удалось загрузить каталог прошивок. Обновите страницу или проверьте подключение. '+error.message); }
draw();
