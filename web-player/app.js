import {renderFirmwareCatalog,bitrateLabel} from './lib/player-catalog.js?v=20261102-speex-nano';
import {readSpeechExamples,orderSpeechEntries,selectSpeechEntry,speechCatalogRows,speechProfileUI} from './lib/speech-catalog.js?v=20261102-speex-nano';
import {speexFirmwareEntries} from './lib/speex-preview.js?v=20261102-speex-nano';
import {speechSignals,speechWindow} from './lib/speech-waveform.js';
import {tiny88Boards,boardId,applyDeviceLayout,applyCollectionLayout} from './lib/player-layout.js?v=20261102-speex-nano';
import { parseHex } from './lib/hex.js';
import { RealtimeMonitor } from './lib/realtime.js';
import { universalPackageEntry } from './lib/universal-package.js?v=20261025-um88-channels';
import { lpxPreviewEntries, lpxFirmwareEntries, previewWaveform } from './lib/native-preview.js?v=20261102-nano';
const $ = id => document.getElementById(id);
const formatHex = (value, length=2) => value.toString(16).toUpperCase().padStart(length,'0');
const canvas = $('wave');
const originalAudio = $('original-audio');
const previewAudio=$('preview-audio'), previewWaves=new Map();
const nativePreview=()=>selected?.playback==='native-pwm8';
const previewCodec=()=>selected?.codec==='speex'?'Speex':'LPX';
let catalog, selected, runtime, runtimeReady=false, connectedRuntime, playing=false, busy=false;
let audio, output, scopes=[new Float32Array(512)], headroom=0;
let signalPoint='output', signalScopes={input:scopes,output:scopes};
let session=0, hasPlayed=false, completed=false, realtime;
let playAttempt=0, busyAttempt=0;
let lastScopeDraw=-Infinity, scopeDrawTimer;
let originalLoading=false, originalAttempt=0;
const speechCollection=new URL(location.href).searchParams.get('collection')==='hq4'||new URL(location.href).searchParams.get('device')==='atmega328p';
let currentDevice='attiny13a', currentBoard=boardId(new URL(location.href).searchParams.get('board')), deviceRequest=0;
let importAttempt=0;
let speechExamples;
let speechWaveforms,phraseRaw,phraseSignals,phraseSignalKey,playbackSeconds=0;
let scopeView='phrase';

function showError(message) { $('error').textContent = message; $('error').hidden = !message; }
function audioControls() {
  return {cutoff:+$('cutoff').value,volume:+$('volume').value,signal:signalPoint};
}
function signalPointUI() {
  if(nativePreview()){
    $('scope-zero').textContent='0';$('scope-left-label').textContent='НАТИВНОЕ PWM8-ПРЕВЬЮ';
    canvas.dataset.signal='preview';canvas.setAttribute('aria-label','Осциллограмма выбранного WAV-превью '+previewCodec());
    return;
  }
  const input=signalPoint==='input';
  $('signal-point').value=signalPoint;
  $('scope-zero').textContent=$('scope-zero-right').textContent=input?'128':'0';
  for(const id of ['wave','wave-right']){
    $(id).dataset.signal=signalPoint;
    $(id).setAttribute('aria-label',input?'Значение звука в регистре OCR до фильтра':'Звуковой выход после фильтра и громкости');
  }
  const stereo=selected?.audioChannels===2,timer=currentDevice==='attiny88'?'1':'0';
  const physical=!input&&(selectedEngine()==='device'||!!selected?.devicePackage);
  $('scope-left-label').textContent=physical?(stereo?'L · PB0':'МОНО · PB1'):(stereo?`L · OCR${timer}A`:`МОНО · OCR${timer}B`);
  $('scope-right-label').textContent=physical?'R · PB1':`R · OCR${timer}B`;
  scopes=signalScopes[signalPoint];draw();
}
function selectedEngine() { return document.querySelector('input[name="engine"]:checked').value; }
function deviceUI(device) {
  applyDeviceLayout(document,{device,board:currentBoard,speech:speechCollection,pwmOutput:selected?.firmware?.pwmOutput});
}
async function switchDevice(device,board=currentBoard) {
  if(!catalog&&speechCollection)return;
  const request=++deviceRequest;
  device=device==='atmega328p'?'atmega328p':device==='attiny88'?'attiny88':'attiny13a';
  if(device==='atmega328p'&&!speechCollection){
    const url=new URL(location.href);url.searchParams.set('collection','hq4');url.searchParams.set('device',device);
    url.searchParams.delete('firmware');url.searchParams.delete('board');location.href=url.href;return;
  }
  board=boardId(board);
  if(speechCollection){
    const entries=orderSpeechEntries(catalog.entries.filter(entry=>(entry.device||'attiny13a')===device),speechExamples);
    if(!entries.length){showError('Речевые примеры временно недоступны.');$('device-select').value=currentDevice;return;}
    currentDevice=device;if(device==='attiny88')currentBoard='mh-et-live-16mhz';
    $('search').value='';load(selectSpeechEntry(entries,selected));return;
  }
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
  $('run-status').textContent = originalLoading ? 'Загрузка оригинала…' : originalPlaying ? 'Оригинальная запись' : busy ? 'Подключение звука…' : playing ? (nativePreview()?'Нативное превью '+previewCodec():'Воспроизведение') : completed ? 'Завершено' : runtimeReady ? (hasPlayed ? 'Пауза' : 'Готов к запуску') : 'Загрузка образа…';
}
function previewUI(enabled) {
  document.body.dataset.preview=String(enabled);
  for(const id of ['fuses','engine-controls','cutoff-control','signal-point-control','scope-metrics','avr-inspector','package-import'])$(id).hidden=enabled;
  $('rom-hash').hidden=enabled&&!selected?.firmware;
  $('preview-note').hidden=!enabled;
  $('preview-playback-note').textContent=selected?.codec==='speex'
    ? 'ПРЕВЬЮ · Точные PWM8-отсчёты этой AVR-прошивки Speex. Полный HEX проверен с активными прерываниями, без пропусков. В браузере воспроизводится WAV; физическая плата не проверялась.'
    : selected?.firmware
    ? 'ПРЕВЬЮ · Точные PWM8-отсчёты нативного декодера LPX. Полный HEX для Arduino Nano проверен в simavr с активными прерываниями, без пропусков. В браузере воспроизводится WAV; физическая плата не проверялась.'
    : 'ПРЕВЬЮ · Точные PWM8-отсчёты нативного декодера LPX. Целевая плата — MH-ET LIVE Tiny88, 16 МГц. Работа LPX-прошивки на этой плате ещё не подтверждена.';
  $('preview-format-note').hidden=!enabled||!selected?.formatNotice;
  $('preview-format-note').textContent=enabled&&selected?.formatNotice?selected.formatNotice+' ':'';
  $('flash-measurement-note').hidden=!enabled||!selected?.flashMeasurement;
  $('flash-measurement-note').textContent=enabled&&selected?.flashMeasurement?'Размер относится к тестовой сборке без очереди и звукового ISR. ':'';
  document.querySelector('.signal-outputs').hidden=enabled;
  if(enabled){
    if(currentDevice==='attiny88')$('tiny88-power').textContent='Целевой профиль: MH-ET LIVE Tiny88 · 16 МГц.';
    $('cpu-status').textContent='';$('memory').textContent='';$('rom-size').textContent='';
    for(const id of ['average','isr','lost','headroom','tempo','lag'])$(id).textContent='—';
  }
}
function elapsed(seconds) {
  $('elapsed').textContent=String(Math.floor(seconds/60)).padStart(2,'0')+':'+(seconds%60).toFixed(1).padStart(4,'0');
}
function previewPosition() {
  if(!nativePreview()||!playing)return;
  elapsed(Math.min(previewAudio.currentTime,selected.phraseSamples/selected.sampleHz));draw();
}
previewAudio.addEventListener('timeupdate',previewPosition);
previewAudio.addEventListener('ended',()=>{
  if(!nativePreview()||!playing)return;
  completed=true;elapsed(selected.phraseSamples/selected.sampleHz);pause();
});
previewAudio.addEventListener('playing',()=>{
  if(!nativePreview()||(!playing&&!busy))previewAudio.pause();
});
previewAudio.addEventListener('pause',()=>{
  if(nativePreview()&&playing){playing=false;transport();}
});
previewAudio.addEventListener('error',()=>{
  if(!nativePreview())return;
  pause();showError('Не удалось загрузить LPX-превью.');
});
async function loadPreviewWave(entry,epoch) {
  try {
    if(!previewWaves.has(entry.nativeAudioUrl))previewWaves.set(entry.nativeAudioUrl,(async()=>{
      const response=await fetch(entry.nativeAudioUrl);if(!response.ok)throw Error('HTTP '+response.status);
      return previewWaveform(await response.arrayBuffer(),entry);
    })());
    const waveform=await previewWaves.get(entry.nativeAudioUrl);
    if(session!==epoch||selected!==entry)return;
    phraseRaw=waveform;phraseSignals=null;scopes=[waveform];signalScopes={input:scopes,output:scopes};canvas.dataset.samples=String(waveform.length);draw();
  }catch{
    previewWaves.delete(entry.nativeAudioUrl);
    if(session===epoch&&selected===entry)$('scope-left-label').textContent='WAV-ПРЕВЬЮ · ОСЦИЛЛОГРАММА НЕДОСТУПНА';
  }
}
async function loadFirmwareWave(entry,epoch){
  const asset=speechWaveforms?.entries.find(item=>item.id===entry.id&&item.flashSha256===entry.flashSha256
    &&(item.eepromSha256??null)===(entry.eepromSha256??null)&&item.phraseSamples===entry.phraseSamples);
  if(!asset){if(speechWaveforms)$('scope-note').textContent='Для этого образа доступен текущий сигнал при воспроизведении.';return;}
  try{
    const url=new URL(asset.audio,import.meta.url);url.searchParams.set('v',asset.wavSha256.slice(0,16));
    const response=await fetch(url);if(!response.ok)throw Error('HTTP '+response.status);
    const wave=previewWaveform(await response.arrayBuffer(),entry);
    if(session!==epoch||selected!==entry)return;
    phraseRaw=wave;phraseSignals=null;canvas.dataset.samples=String(wave.length);draw();
  }catch{if(session===epoch)$('scope-note').textContent='Полная форма недоступна; текущий сигнал появится при воспроизведении.';}
}
function draw() {
  const now=performance.now(), wait=1000/30-(now-lastScopeDraw);
  if(wait>0){
    if(scopeDrawTimer===undefined)scopeDrawTimer=setTimeout(()=>{scopeDrawTimer=undefined;draw();},wait);
    return;
  }
  if(scopeDrawTimer!==undefined){clearTimeout(scopeDrawTimer);scopeDrawTimer=undefined;}
  lastScopeDraw=now;
  let view=scopes[0];
  if(speechCollection&&phraseRaw){
    const key=[signalPoint,$('cutoff').value,$('volume').value].join('/');
    if(!phraseSignals||phraseSignalKey!==key){phraseSignals=speechSignals(phraseRaw,selected.sampleHz,{native:nativePreview(),...audioControls()});phraseSignalKey=key;}
    const signal=phraseSignals[signalPoint],seconds=nativePreview()?previewAudio.currentTime:playbackSeconds;
    if(scopeView==='phrase')view=signal;
    else if(nativePreview()||!hasPlayed)view=speechWindow(signal,phraseSignals.sampleRate,seconds);
    canvas.dataset.view=scopeView;
    document.querySelector('.scope-scale').textContent=scopeView==='phrase'?(selected.phraseSamples/selected.sampleHz).toLocaleString('ru')+' с · вся фраза':'85 мс · текущий сигнал';
  }
  drawWave(canvas,view,'#c9ef86');
  if(scopes[1])drawWave($('wave-right'),scopes[1],'#86d9ef');
  if(playing&&nativePreview())scopeDrawTimer=setTimeout(()=>{scopeDrawTimer=undefined;draw();},1000/30);
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
  if(scope.length>width*2){
    for(let x=0;x<width;x++){
      const start=Math.floor(x*scope.length/width),end=Math.max(start+1,Math.floor((x+1)*scope.length/width));
      let low=Infinity,high=-Infinity;for(let i=start;i<end;i++){low=Math.min(low,scope[i]);high=Math.max(high,scope[i]);}
      ctx.moveTo(x,height/2-high*height*.43);ctx.lineTo(x,height/2-low*height*.43);
    }
  }else for (let i=0;i<scope.length;i++) { const x=i/(scope.length-1)*width,y=height/2-scope[i]*height*.43; if (!i) ctx.moveTo(x,y); else ctx.lineTo(x,y); } ctx.stroke();
  if(speechCollection&&scopeView==='phrase'){
    const seconds=nativePreview()?previewAudio.currentTime:playbackSeconds;
    const x=Math.min(1,seconds/(selected.phraseSamples/selected.sampleHz))*width;
    ctx.strokeStyle='#e8eddf';ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,height);ctx.stroke();
  }
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
function downloadUI(id,source,filename,title) {
  const link=$(id);link.hidden=false;link.title=title;
  if(source){
    link.href=source;link.download=filename;link.removeAttribute('aria-disabled');link.removeAttribute('tabindex');
  }else{
    link.removeAttribute('href');link.removeAttribute('download');
    link.setAttribute('aria-disabled','true');link.setAttribute('tabindex','-1');
  }
}
function renderCatalog() {
  const query=$('search').value.toLocaleLowerCase('ru').trim();
  const available=catalog.entries.filter(entry=>!speechCollection||(entry.device||'attiny13a')===currentDevice);
  const entries=speechCollection?speechCatalogRows(available,selected,speechExamples,currentDevice):available;
  renderFirmwareCatalog(document,{entries,selectedId:selected?.id,query,onSelect:load});
}
function connectAudio() {
  if (nativePreview()||!runtime||!output || !runtimeReady || connectedRuntime===runtime) return;
  const channel=new MessageChannel();
  output.port.postMessage({type:'connect',session,channels:selected.audioChannels||1,port:channel.port1},[channel.port1]);
  runtime.postMessage({type:'audio-port',port:channel.port2,sampleRate:audio.sampleRate,controls:audioControls()},[channel.port2]);
  connectedRuntime=runtime;
  document.querySelector('.scope-scale').textContent=(4096/audio.sampleRate*1000).toFixed(0)+' мс';
}
function pause() { playAttempt++; playing=false; previewAudio.pause();output?.port.postMessage({type:'playing',value:false}); transport(); }
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
  stopOriginal(); pause(); showError(''); busy=false; runtimeReady=false; runtime?.terminate();runtime=null; connectedRuntime=null;
  session++; hasPlayed=false; completed=false;
  const autoplayAttempt=playAttempt;
  output?.port.postMessage({type:'disconnect'});
  selected=entry; headroom=0;
  phraseRaw=null;phraseSignals=null;playbackSeconds=0;let displayOrder=entry.order;
  canvas.dataset.view=speechCollection?scopeView:'live';
  $('signal-view-control').hidden=!speechCollection;$('signal-view').value=scopeView;
  $('scope-note').textContent=speechCollection?'Вся фраза — полный сигнал выбранного образа; текущий сигнал — окно 85 мс.':'';
  if(speechCollection){currentDevice=entry.device||'attiny13a';if(currentDevice==='attiny88')currentBoard='mh-et-live-16mhz';}
  deviceUI(currentDevice);
  $('device-select').disabled=false;
  previewUI(nativePreview());
  applyCollectionLayout(document,{device:currentDevice,speech:speechCollection,preview:nativePreview(),codec:entry.codec});
  const speechEntries=speechCollection?catalog.entries.filter(item=>(item.device||'attiny13a')===currentDevice):[];
  speechProfileUI(document,speechEntries,entry);
  if(speechExamples&&speechCollection){
    const example=speechExamples.examples.find(item=>item.id===entry.audioReferenceId);
    document.querySelector('.library h2').textContent='Выберите фразу';
    document.querySelector('.subtitle').textContent='Одинаковые фразы для всех микроконтроллеров. Сравните кодеки и исходную запись.';
    if(example)displayOrder=example.order;
  }
  previewAudio.removeAttribute('src');previewAudio.load();delete canvas.dataset.samples;
  if(entry.devicePackage){
    for(const choice of document.querySelectorAll('input[name="engine"]')){choice.disabled=choice.value!=='transpiled';choice.checked=choice.value==='transpiled';}
    const configuration=entry.deviceConfiguration;
    $('fuse-low').textContent='0x'+formatHex(configuration.fuseLow);
    $('fuse-high').textContent='0x'+formatHex(configuration.fuseHigh);
    $('fuse-high-note').textContent='из пакета';
    const clock=['Внешний источник','Внутренний RC','Внутренний RC','Внутренний 128 кГц'][configuration.fuseLow&3];
    $('fuse-clock-value').textContent=clock+' · '+(configuration.oscillatorHz/1000000).toLocaleString('ru')+' МГц';
    $('fuse-clock-note').textContent=configuration.fuseLow&16?'CKDIV8 отключён · делитель /1':'CKDIV8 включён · делитель /8';
  }
  if(currentDevice==='attiny88'&&entry.firmwareEngine==='UM88'&&currentBoard!=='mh-et-live-16mhz'){
    $('board-isp-option').textContent='UM88 · '+(entry.cpuHz/1000000).toLocaleString('ru')+' МГц · ISP';
    $('board-note').textContent='Профиль UM88 из пакета/каталога · EEPROM не требуется';
    $('machine-details').textContent='512 Б SRAM · 64 Б EEPROM · '+(entry.cpuHz/1000000).toLocaleString('ru')+' МГц';
    $('tiny88-clock').textContent=(entry.cpuHz/1000000).toLocaleString('ru')+' MHz · PDIP-28';
    if(entry.cpuHz!==8000000){
      for(const id of ['fuse-low','fuse-high','fuse-extended-value'])$(id).textContent='—';
      $('fuse-high-note').textContent='зависят от платы';
      $('fuse-clock-value').textContent='F_CPU · '+(entry.cpuHz/1000000).toLocaleString('ru')+' МГц';
      $('fuse-clock-note').textContent='Источник тактов и фьюзы задаются конфигурацией платы';
    }
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
  signalScopes={input:scopes,output:scopes};
  $('stereo-output').hidden=!stereo;$('scope-right').hidden=!stereo;$('panorama').hidden=!stereo||!!entry.devicePackage;
  $('right-output-label').textContent=(stereo?'R · ':'')+(micronucleus?'PB2 / OC1B · D10':tiny88?'PB2 / OC1B · вывод 16':'PB1 / OC0B · вывод 6');
  $('right-output-label').title=micronucleus?'D10 на плате MH-ET LIVE':tiny88?'Вывод 16 в корпусе PDIP-28':'Вывод 6 в 8-выводных корпусах';
  $('left-output-label').textContent='L · '+(micronucleus?'PB1 / OC1A · D9':tiny88?'PB1 / OC1A · вывод 15':'PB0 / OC0A · вывод 5');
  $('left-output-label').title=micronucleus?'D9 на плате MH-ET LIVE':tiny88?'Вывод 15 в корпусе PDIP-28':'Вывод 5 в 8-выводных корпусах';
  $('audio-mode').textContent=nativePreview()?`НАТИВНОЕ ПРЕВЬЮ · ${(entry.sampleHz/1000).toLocaleString('ru')} кГц · МОНО`:stereo?'СТЕРЕО · 2 PWM-ВЫХОДА':'МОНО · 1 PWM-ВЫХОД';
  signalPointUI();
  $('average-label').textContent=stereo?'СРЕДНИЙ PWM · L / R':'СРЕДНИЙ PWM';
  $(tiny88?'chip-attiny88':'chip-attiny13a').setAttribute('aria-label',tiny88
    ? micronucleus?'MH-ET LIVE Tiny88, 16 МГц: '+(stereo?'R — D10 / PB2, L — D9 / PB1':'моно — D10 / PB2'):'ATtiny88, PDIP-28, вид сверху: '+(stereo?'правый канал PB2 вывод 16, левый канал PB1 вывод 15':'выход PWM PB2 вывод 16')
    : 'ATtiny13A, вид сверху: '+(stereo?'правый канал PB1 вывод 6, левый канал PB0 вывод 5':'выход PWM PB1 вывод 6'));
  draw();
  $('elapsed').textContent='00:00.0'; $('average').textContent=stereo?'128.0 / 128.0':'128.0'; $('headroom').textContent='—';
  $('tempo').textContent='100.0%'; $('lag').textContent='0.0 мс'; realtime?.resetAnchor();
  delete $('tempo').dataset.wallMs; delete $('tempo').dataset.audioMs;
  $('selected-order').textContent=displayOrder; $('selected-title').textContent=entry.title; $('selected-description').textContent=entry.description;
  if(entry.kind==='speech') {
    const research=entry.research||(entry.codec?.startsWith('lpx')?'../Codecs/LPX/README.md':entry.codec==='hq4-t'
      ? '../ATtiny13A/Sound/codec/timbre/README.md'
      : '../ATtiny13A/Sound/research/hq4-emulator-comparison.json');
    $('speech-audit').href=research.endsWith('.md')
      ? new URL(research,'https://github.com/Witali/MicroMusic/blob/main/web-player/').href : research;
    $('speech-audit').textContent=entry.codec==='speex'?'Исследование Speex ↗':entry.codec?.startsWith('lpx') ? 'Исследование LPX ↗' : entry.codec==='tiny-period' ? 'Исследование речевого ядра ↗'
      : entry.codec==='hq4-t' ? 'Исследование HQ4-T ↗' : 'Сверка HQ4 ↗';
  }
  $('speech-audit').hidden=entry.kind!=='speech';
  const capacity=micronucleus?6012:tiny88?8192:1024, prefix=micronucleus?'attiny88-mh-et-live-16mhz':currentDevice;
  if(nativePreview()){
    const file=entry.id+(entry.streamExtension||'.lpx');
    $('rom-name').href=entry.streamUrl;$('rom-name').download=file;$('rom-name').textContent=file;
    $('download').textContent='↓ Flash HEX';
    downloadUI('download',entry.firmware?.source,entry.firmware?entry.id+'.hex':null,entry.firmware?'Полный Flash HEX для Arduino Nano / ATmega328P · 16 МГц.':'Flash HEX недоступен: готовая звуковая прошивка для ATtiny88 ещё не проверена.');
    downloadUI('download-eeprom',null,null,'EEPROM не используется этим примером.');
    const measurement=entry.flashMeasurement;
    const cost=entry.firmware
      ? `${entry.firmware.programFlashBytes.toLocaleString('ru')} Б программа + ${entry.streamBytes.toLocaleString('ru')} Б звук = ${entry.firmware.flashBytes.toLocaleString('ru')} Б Flash · ${entry.firmware.staticSramBytes} Б SRAM`
      : measurement
      ? `${measurement.programFlashBytes.toLocaleString('ru')} Б программа + ${measurement.encodedBytes.toLocaleString('ru')} Б звук = ${measurement.totalFlashBytes.toLocaleString('ru')} Б Flash · тестовая сборка`
      : `Программа: — (не измерено) · ${entry.streamBytes.toLocaleString('ru')} Б данных LPX`;
    $('rom-details').textContent=`${cost} · ${bitrateLabel(entry.bitrateBps)} · ${entry.phraseSamples.toLocaleString('ru')} отсчётов · ${(entry.phraseSamples/entry.sampleHz).toLocaleString('ru')} с`;
    $('board-upload').hidden=true;$('upload-command').textContent='';$('reset').disabled=false;
    $('original-player').hidden=true;$('wav-link').hidden=false;$('wav-link').href=entry.nativeAudioUrl;
    $('reference-wav').hidden=false;$('reference-wav').href=originalUrl;
    $('rom-hash').textContent='';$('rom-hash').title='';
    if(entry.firmware){
      $('rom-name').href=entry.firmware.source;$('rom-name').download=entry.id+'.hex';$('rom-name').textContent=entry.id+'.hex';
      $('rom-hash').textContent=entry.firmware.hexSha256.slice(0,16)+'…';$('rom-hash').title='SHA-256 HEX: '+entry.firmware.hexSha256;
    }
    previewAudio.src=entry.nativeAudioUrl;previewAudio.volume=+$('volume').value;previewAudio.load();
    document.querySelector('.scope-scale').textContent=(entry.phraseSamples/entry.sampleHz).toLocaleString('ru')+' с · вся запись';
    loadPreviewWave(entry,session);
  }else{
  const flashSource=entry.source||'data:text/plain;charset=utf-8,'+encodeURIComponent(entry.flashHex);
  $('rom-name').textContent=`${prefix}-${entry.id}.hex`; $('rom-details').textContent=`${entry.flashBytes} / ${capacity} Б Flash · ${entry.eepromBytes} / 64 Б EEPROM · ${(entry.sampleHz/1000).toLocaleString('ru')} кГц ${entry.kind==='speech'?'отсчёты':'PWM'}`;
  if(micronucleus)$('rom-details').textContent=`${entry.flashBytes} / ${capacity} Б приложения · тембры во Flash · ${(entry.sampleHz/1000).toLocaleString('ru')} кГц PWM`;
  if(entry.devicePackage)$('rom-details').textContent=`${entry.flashBytes} / ${capacity} Б Flash · ${entry.eepromBytes} / 64 Б EEPROM · пакет ATtiny13A`;
  if(entry.firmwareEngine==='UM88')$('rom-details').textContent=`${entry.flashBytes} / ${capacity} Б ${micronucleus?'приложения · тембры во Flash':'Flash'} · EEPROM не требуется · синтез ${(entry.synthesisHz/1000).toLocaleString('ru')} кГц · ${(entry.pwmHz/1000).toLocaleString('ru')} кГц PWM`;
  $('rom-name').href=flashSource; $('rom-name').download=`${prefix}-${entry.id}.hex`;
  $('rom-hash').textContent=entry.flashSha256.slice(0,16)+'…'; $('rom-hash').title='SHA-256 Flash: '+entry.flashSha256;
  $('rom-size').textContent=entry.flashBytes+' байт';
  $('original-player').hidden=!entry.originalPlayer; if(entry.originalPlayer)$('original-player').href=entry.originalPlayer;
  $('wav-link').hidden=!entry.preview; if (entry.preview) $('wav-link').href=entry.preview;
  const reference=originalUrl||entry.reference;
  $('reference-wav').hidden=!reference; if(reference)$('reference-wav').href=reference;
  $('reset').disabled=false;
  $('board-upload').hidden=!micronucleus;
  $('upload-command').textContent=`micronucleus --run ${prefix}-${entry.id}.hex`;
  $('download').textContent=micronucleus?'↓ HEX для Micronucleus':'↓ Flash HEX';
  const eepromSource=entry.firmwareEngine==='UM88'?null:entry.eepromSource||(entry.eepromHex ? 'data:text/plain;charset=utf-8,'+encodeURIComponent(entry.eepromHex) : null);
  downloadUI('download',flashSource,`${prefix}-${entry.id}.hex`,micronucleus?'Образ Flash для Micronucleus.':'Образ прошивки Flash HEX.');
  downloadUI('download-eeprom',eepromSource,`${prefix}-${entry.id}-eeprom.hex`,eepromSource?'Образ EEPROM для этой прошивки.':'Этой прошивке EEPROM не требуется.');
  const bytes=parseHex(entry.flashHex,capacity); $('memory').textContent=Array.from({length:8},(_,line)=>formatHex(line*16,4)+'  '+Array.from(bytes.subarray(line*16,line*16+16),x=>formatHex(x)).join(' ')).join('\n');
  }
  const url=new URL(location.href); url.searchParams.set('firmware',entry.id);
  if(currentDevice!=='attiny13a')url.searchParams.set('device',currentDevice);else url.searchParams.delete('device');
  if(speechCollection)url.searchParams.set('collection','hq4');
  if(micronucleus)url.searchParams.set('board',currentBoard);else url.searchParams.delete('board');
  history.replaceState(null,'',url);
  renderCatalog(); transport();
  if(nativePreview()){
    previewUI(true);runtimeReady=true;transport();if(autoplay)toggle();return;
  }
  document.querySelector('.scope-scale').textContent='85 мс';
  if(speechCollection)loadFirmwareWave(entry,session);
  const worker=new Worker(new URL('./worker.js?v=20261026-signal-point',import.meta.url),{type:'module'}); runtime=worker;
  worker.onmessage=({data})=>{
    if (runtime!==worker) return;
    if (data.type==='ready') {
      runtimeReady=true; stateUI(data.state); connectAudio(); transport();
      if(autoplay&&autoplayAttempt===playAttempt)toggle();
    }
    if (data.type==='state') {
      stateUI(data.state);
      signalScopes={input:data.inputScopes??data.scopes,output:data.outputScopes??data.scopes};
      scopes=signalScopes[signalPoint];draw();$('average').textContent=data.averages.map(x=>x.toFixed(1)).join(' / ');
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
      if (nativePreview()||data.type!=='position' || data.session!==session || !playing) return;
      const timing=realtime.observe(data,performance.now());
      const duration=selected.playOnce ? selected.phraseSamples/selected.sampleHz : Infinity;
      const seconds=Math.min(timing.seconds,duration);
      playbackSeconds=seconds;draw();
      elapsed(seconds);
      $('tempo').textContent=timing.tempoPercent.toFixed(1)+'%'; $('lag').textContent=timing.lagMs.toFixed(1)+' мс';
      $('tempo').dataset.wallMs=timing.wallMs.toFixed(3); $('tempo').dataset.audioMs=timing.audioMs.toFixed(3);
      if(timing.seconds>=duration){completed=true;pause();return;}
      if (data.underruns) $('run-status').textContent=`Воспроизведение · задержки звука: ${data.underruns}`;
    };
    output.onprocessorerror=()=>{ if(!nativePreview()){pause();showError('Ошибка звукового потока. Обновите страницу для повторного запуска.');} };
    connectAudio(); await audio.resume();
  } catch (error) { await context.close(); audio=null; throw error; }
}
async function toggle() {
  if (!runtimeReady || busy) return;
  if (playing) { pause(); return; }
  if (completed) { load(selected,{autoplay:true}); return; }
  stopOriginal();
  if(nativePreview()){
    const target=selected,attempt=++playAttempt;busyAttempt=attempt;busy=true;transport();showError('');
    try{
      await previewAudio.play();
      if(target!==selected||attempt!==playAttempt)return;
      playing=true;hasPlayed=true;transport();
    }catch(error){if(target===selected&&attempt===playAttempt&&error.name!=='AbortError'){pause();showError('Не удалось включить LPX-превью: '+error.message);}}
    finally{if(busyAttempt===attempt){busy=false;transport();}}
    return;
  }
  const target=runtime,attempt=++playAttempt; busyAttempt=attempt; busy=true; transport(); showError('');
  try {
    await ensureAudio();
    if (target!==runtime||attempt!==playAttempt) return;
    connectAudio(); realtime.resetAnchor(); playing=true; hasPlayed=true; output.port.postMessage({type:'playing',value:true});
  } catch (error) { if(target===runtime&&attempt===playAttempt)showError('Не удалось включить звук: '+error.message); }
  finally { if(busyAttempt===attempt){busy=false;transport();} }
}
$('play').onclick=toggle; $('play-original').onclick=toggleOriginal; $('reset').onclick=()=>load(selected); $('search').oninput=renderCatalog;
$('volume').oninput=()=>{originalAudio.volume=previewAudio.volume=+$('volume').value;runtime?.postMessage({type:'controls',controls:audioControls()});draw();};
$('cutoff').onchange=()=>{runtime?.postMessage({type:'controls',controls:audioControls()});draw();};
$('signal-view').onchange=()=>{scopeView=$('signal-view').value==='live'?'live':'phrase';canvas.dataset.view=scopeView;draw();};
$('signal-point').onchange=()=>{
  signalPoint=$('signal-point').value==='input'?'input':'output';signalPointUI();
  runtime?.postMessage({type:'controls',controls:audioControls()});
};
for (const choice of document.querySelectorAll('input[name="engine"]')) choice.onchange=()=>{
  if (selected) load(selected);
};
$('device-select').onchange=()=>switchDevice($('device-select').value);
$('speech-profile-select').onchange=()=>{
  const entry=catalog.entries.find(item=>item.id===$('speech-profile-select').value&&(item.device||'attiny13a')===currentDevice);
  if(entry)load(entry);
};
$('board-select').onchange=()=>switchDevice('attiny88',$('board-select').value);
$('package-file').onchange=async event=>{
  if(nativePreview())return;
  const file=event.target.files[0];if(!file)return;
  const attempt=++importAttempt,device=currentDevice,request=deviceRequest;
  try{
    if(file.size>16*1024*1024)throw Error('Пакет превышает 16 МБ');
    const text=await file.text();
    const entry=device==='attiny88'?await universalPackageEntry(text):await (await import('./lib/package-entry.js')).packageEntry(text,{name:file.name});
    if(device==='attiny88'&&((entry.board==='mh-et-live-16mhz')!==(currentBoard==='mh-et-live-16mhz')))
      throw Error('Профиль пакета не соответствует выбранной плате: выберите '+(entry.board?'Micronucleus':'профиль ISP'));
    if(attempt!==importAttempt||device!==currentDevice||request!==deviceRequest)return;
    catalog.entries=catalog.entries.filter(e=>!['package','universal'].includes(e.kind));catalog.entries.push(entry);
    $('search').value='';load(entry);
  }catch(error){if(attempt===importAttempt&&device===currentDevice&&request===deviceRequest)showError('Не удалось открыть пакет: '+error.message);}
  finally{event.target.value='';}
};
document.addEventListener('keydown',event=>{ if (event.code==='Space' && !event.repeat && !/^(INPUT|SELECT|TEXTAREA|BUTTON|A|AUDIO)$/.test(event.target.tagName)) { event.preventDefault(); toggle(); } });
window.addEventListener('pagehide',()=>{ pause();stopOriginal();runtime?.terminate(); audio?.close(); });
try {
  const speech=speechCollection;
  deviceUI('attiny13a');
  if(speech){
    $('device-select').disabled=true;
    applyCollectionLayout(document,{device:'attiny13a',speech:true});
    $('original-player').textContent='Плеер из ChatGPT ↗';
    $('speech-audit').hidden=false;
  }
  if(!speech) {
    await switchDevice(new URL(location.href).searchParams.get('device'));
  } else {
  // Original recordings are shared public assets. Local listening can also use
  // restored emulator previews and the archived ChatGPT player.
  const response=await fetch(speech?'./hq4-firmware.json?v=20261023-mobile-original':'./firmware.json');
  if (!response.ok) throw new Error('HTTP '+response.status);
  catalog=await response.json();
  try{
    const response=await fetch(new URL('./audio/speech-waveforms/manifest.json?v=20261102-signal-view',import.meta.url));
    if(response.ok){const data=await response.json();if(data.schemaVersion===1&&Array.isArray(data.entries))speechWaveforms=data;}
  }catch{/* Live signal remains available without saved phrase duties. */}
  try{
    const response=await fetch(new URL('./firmware-attiny13a-speech-extra.json?v=20261102-shared-speech',import.meta.url));
    if(!response.ok)throw Error('HTTP '+response.status);
    const extra=await response.json();
    if(extra.schema!==1||!Array.isArray(extra.entries))throw Error('Неверный каталог дополнительных фраз.');
    for(const entry of extra.entries){
      if(entry.kind!=='speech'||entry.audioReferenceId!=='bread'||entry.flashBytes>1024||entry.eepromBytes>64)throw Error('Неверный образ ATtiny13A.');
      if(parseHex(entry.flashHex,1024).length!==entry.flashBytes)throw Error('Неверный размер Flash.');
    }
    catalog.entries.push(...extra.entries);
  }catch{/* Retained original speech stays usable if supplemental firmware is unavailable. */}
  try{
    const response=await fetch(new URL('./speech-examples.json?v=20261102-shared-speech',import.meta.url));
    if(!response.ok)throw Error('HTTP '+response.status);
    speechExamples=readSpeechExamples(await response.json());
  }catch{/* Older/offline catalogs retain their own examples when the shared index is unavailable. */}
  let previewError,nanoError,speexError;
  try{
    const response=await fetch(new URL('./firmware-atmega328p.json?v=20261102-nano',import.meta.url));
    if(!response.ok)throw Error('HTTP '+response.status);
    catalog.entries.push(...lpxFirmwareEntries(await response.json(),import.meta.url));
  }catch(error){nanoError=error;}
  try{
    const response=await fetch(new URL('./firmware-speex-atmega328p.json?v=20261102-speex-nano',import.meta.url));
    if(!response.ok)throw Error('HTTP '+response.status);
    catalog.entries.push(...speexFirmwareEntries(await response.json(),import.meta.url));
  }catch(error){speexError=error;}
  try{
    const response=await fetch(new URL('./audio/lpx-bread/manifest.json?v=20261101-flash',import.meta.url));
    if(!response.ok)throw Error('HTTP '+response.status);
    catalog.entries.push(...lpxPreviewEntries(await response.json(),import.meta.url));
  }catch(error){previewError=error;}
  try{
    const response=await fetch(new URL('./audio/lpx-speech/manifest.json?v=20261102-shared-speech',import.meta.url));
    if(!response.ok)throw Error('HTTP '+response.status);
    const data=await response.json();
    if(data.schemaVersion!==1||!Array.isArray(data.clips))throw Error('Неверный набор LPX.');
    catalog.entries.push(...data.clips.flatMap(clip=>lpxPreviewEntries(clip,import.meta.url)));
  }catch{/* Existing LPX clips remain usable if additional assets cannot load. */}
  document.querySelector('footer span:last-child').textContent='Речевые кодеки · AVR-прошивки и сравнение с оригиналом';
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
  const exact=catalog.entries.find(entry=>entry.id===id);
  const requestedDevice=new URL(location.href).searchParams.get('device');
  const device=requestedDevice==='atmega328p'||exact?.device==='atmega328p'?'atmega328p':exact?.playback==='native-pwm8'||requestedDevice==='attiny88'?'attiny88':'attiny13a';
  const available=orderSpeechEntries(catalog.entries.filter(entry=>(entry.device||'attiny13a')===device),speechExamples);
  load(available.find(entry=>entry.id===id)||available[0]||catalog.entries.find(entry=>entry.id===catalog.defaultId));
  if(previewError&&(device==='attiny88'||requested.startsWith('lpx-bread-')))showError('LPX-примеры временно недоступны.');
  if(nanoError&&speexError&&device==='atmega328p')showError('Не удалось загрузить речевые прошивки Arduino Nano.');
  }
} catch (error) { showError('Не удалось загрузить каталог прошивок. Обновите страницу или проверьте подключение. '+error.message); }
draw();
