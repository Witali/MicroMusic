import { parseIntelHex, validateBinary } from './formats.mjs';
import { RealtimeSpeaker } from './speaker.mjs';

const $ = id => document.getElementById(id), rate = 96000;
const hex = (n, width = 2) => n.toString(16).toUpperCase().padStart(width, '0');
const number = n => n.toLocaleString('ru-RU');
const machineInputs = [...document.querySelectorAll('[data-machine]')];
let firmware = null, filename = '', loadTicket = 0, worker = null, romURL = null;
let catalog = null, selectedExample = null;
let starting = false, runTicket = 0, scopeFrame = null;
const speaker = new RealtimeSpeaker(status => {
  const seconds = status.seconds, minutes = Math.floor(seconds / 60);
  $('elapsed').textContent = `${String(minutes).padStart(2, '0')}:${(seconds % 60).toFixed(1).padStart(4, '0')}`;
  worker?.postMessage({ kind: 'played', seconds });
  if (status.ended) { stopScope(); redrawScope(); $('playback-status').textContent = 'Воспроизведение завершено'; setBusy(false); }
});
const soundOptions = () => {
  const [cutoff, poles] = $('filter').value.split('-').map(Number);
  return { rate, cutoff, poles, normalize: $('normalize').checked, volume: Number($('volume').value) };
};

// Replaced with an embedded worker by scripts/build-standalone.mjs.
function createWorker() { return new Worker(new URL('./worker.mjs', import.meta.url), { type: 'module' }); }
// Replaced by embedded data in the standalone build.
async function getExampleCatalog() { const response = await fetch(new URL('./examples.json', import.meta.url)); if (!response.ok) throw Error('Не удалось загрузить список примеров'); return response.json(); }
async function readExample(entry) { const response = await fetch(new URL(entry.rom, import.meta.url)); if (!response.ok) throw Error('Не удалось загрузить ROM примера'); return response.arrayBuffer(); }
function exampleSourceURL(entry) { return new URL(entry.source, 'https://github.com/Witali/MicroMusic/blob/main/i8080/Emulator/').href; }

function renderCatalog() {
  if (!catalog) return;
  const query = $('search').value.toLocaleLowerCase('ru').trim();
  const entries = catalog.entries.filter(entry => `${entry.title} ${entry.description} ${entry.meta}`.toLocaleLowerCase('ru').includes(query));
  $('catalog-count').textContent = query ? `${entries.length} / ${catalog.entries.length}` : catalog.entries.length;
  $('catalog').replaceChildren(...entries.map(entry => {
    const item = document.createElement('div'), button = document.createElement('button');
    item.setAttribute('role', 'listitem'); button.type = 'button'; button.className = 'firmware-card';
    button.dataset.example = entry.id; button.setAttribute('aria-pressed', String(selectedExample === entry.id));
    const order = document.createElement('span'), body = document.createElement('span'), title = document.createElement('strong');
    const meta = document.createElement('span'), arrow = document.createElement('span');
    order.className = 'card-number'; order.textContent = String(catalog.entries.indexOf(entry) + 1).padStart(2, '0');
    body.className = 'card-body'; title.textContent = entry.title; meta.className = 'card-meta'; meta.textContent = entry.meta;
    arrow.className = 'card-arrow'; arrow.textContent = selectedExample === entry.id ? '●' : '↗'; arrow.setAttribute('aria-hidden', 'true');
    body.append(title, meta); button.append(order, body, arrow);
    button.addEventListener('click', () => loadExample(entry)); item.append(button); return item;
  }));
  if (!entries.length) { const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = 'Примеры не найдены.'; $('catalog').append(empty); }
}
function loadExample(entry) {
  return loadFile({ name: entry.filename, size: entry.bytes, arrayBuffer: () => readExample(entry) }, entry);
}
async function initializeExamples() {
  try {
    catalog = await getExampleCatalog(); renderCatalog(); $('catalog-status').textContent = 'Выберите пример и нажмите «Эмулировать».';
    // A user upload takes priority over an initial catalog request still in flight.
    if (loadTicket === 0) await loadExample(catalog.entries.find(entry => entry.id === catalog.defaultId));
  } catch (error) { $('catalog-status').textContent = `${error.message}. Можно загрузить собственный файл.`; }
}

function report(message, error = false) {
  $('status').textContent = message;
  $('error').hidden = !error;
  $('error').textContent = error ? message : '';
}
function setBusy(busy) {
  const active = speaker.active || busy;
  document.body.dataset.playing = String(active && !speaker.paused);
  $('run').disabled = starting || !firmware;
  $('run').textContent = starting ? 'Запуск…' : speaker.active ? speaker.paused ? '▶ Продолжить' : 'Ⅱ Пауза' : '▶ Эмулировать';
  $('cancel').disabled = !firmware;
  for (const input of machineInputs) input.disabled = starting || active;
  $('run-state').textContent = speaker.paused ? 'Пауза' : active ? 'Исполнение и звук' : firmware ? 'Образ загружен' : 'Ожидание образа';
}
function stopWorker() { if (worker) { worker.terminate(); worker = null; } setBusy(false); }
function resetPlayback() {
  runTicket++; starting = false; stopScope(); speaker.reset(); stopWorker(); clearResult(); setBusy(false);
  $('playback-status').textContent = 'Звук запускается кнопкой «Эмулировать»'; $('elapsed').textContent = '00:00.0';
}
function drawScope(samples) {
  const canvas = $('scope'), context = canvas.getContext('2d');
  const ratio = window.devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  if (canvas.width !== Math.round(w*ratio) || canvas.height !== Math.round(h*ratio)) {
    canvas.width = Math.round(w*ratio); canvas.height = Math.round(h*ratio);
  }
  context.setTransform(1, 0, 0, 1, 0, 0); context.clearRect(0, 0, canvas.width, canvas.height);
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.fillStyle = '#0e140e'; context.fillRect(0, 0, w, h);
  context.strokeStyle = '#232e21'; context.lineWidth = 1;
  context.beginPath();
  for (let x = 0; x < w; x += w / 12) { context.moveTo(x, 0); context.lineTo(x, h); }
  for (let y = 0; y <= h; y += h / 4) { context.moveTo(0, y); context.lineTo(w, y); }
  context.stroke();
  context.strokeStyle = '#647b45'; context.setLineDash([4, 5]); context.beginPath();
  context.moveTo(0, h/2); context.lineTo(w, h/2); context.stroke(); context.setLineDash([]);
  if (!samples?.length) return;
  const limit = samples.length;
  context.strokeStyle = '#c9ef86'; context.lineWidth = 1.5; context.beginPath();
  // Min/max per pixel preserves short pulses instead of skipping between samples.
  for (let x = 0; x < w; x++) {
    const begin = Math.floor(x * limit / w), end = Math.max(begin + 1, Math.floor((x + 1) * limit / w));
    let low = 1, high = -1;
    for (let i = begin; i < Math.min(end, limit); i++) { low = Math.min(low, samples[i]); high = Math.max(high, samples[i]); }
    context.moveTo(x, h / 2 - high * h * 0.43); context.lineTo(x, h / 2 - low * h * 0.43);
  }
  context.stroke();
}
function updateRegisters(result) {
  const regs = result?.registers || Array(8).fill(0), flags = result?.flags || 2;
  $('registers').replaceChildren(...['B', 'C', 'D', 'E', 'H', 'L', 'A', 'F'].map((name, i) => {
    const box = document.createElement('div'), label = document.createElement('span'), value = document.createElement('strong');
    box.className = 'cpu-register'; label.textContent = name;
    value.textContent = hex(i === 6 ? regs[7] : i === 7 ? flags : regs[i]);
    box.append(label, value); return box;
  }));
  $('flags').replaceChildren(...[['S', 7], ['Z', 6], ['AC', 4], ['P', 2], ['CY', 0]].map(([name, bit]) => {
    const flag = document.createElement('span'), value = (flags >> bit) & 1;
    flag.className = 'flag'; flag.dataset.set = String(!!value); flag.textContent = `${name} ${value}`; return flag;
  }));
  $('cpu-status').textContent = `PC ${hex(result?.pc || 0, 4)} · SP ${hex(result?.sp || 0, 4)} · INTE ${result?.inte || 0}`;
  $('write-note').textContent = result ? `Записей в память: ${number(result.memWrites)}; проигнорировано в ПЗУ: ${number(result.ignoredWrites)}. Начальная точка — 0000h.` : 'Регистры показаны в шестнадцатеричном виде. Начальная точка — 0000h.';
}
function clearResult() {
  for (const id of ['steps', 'cycles', 'edges', 'writes', 'io-writes']) $(id).textContent = '0';
  $('cpu-time').textContent = '0,000 с'; $('progress').value = 0;
  $('scope-scale').textContent = '85 мс'; drawScope(null); updateRegisters(null);
}
function redrawScope() {
  const samples = speaker.readScope();
  $('scope-scale').textContent = `${Math.round(speaker.scopeMilliseconds)} мс`;
  drawScope(samples);
}
function stopScope() {
  if (scopeFrame !== null) cancelAnimationFrame(scopeFrame);
  scopeFrame = null;
}
function startScope() {
  stopScope();
  let lastDraw = -Infinity;
  const tick = now => {
    scopeFrame = null;
    if (!speaker.active || speaker.paused) return;
    if (now-lastDraw >= 1000/30) { redrawScope(); lastDraw = now; }
    scopeFrame = requestAnimationFrame(tick);
  };
  scopeFrame = requestAnimationFrame(tick);
}
async function loadFile(file, example = null) {
  if (!file) return;
  const ticket = ++loadTicket;
  resetPlayback(); firmware = null; filename = ''; setBusy(false);
  selectedExample = example?.id || null; renderCatalog();
  if (romURL) { URL.revokeObjectURL(romURL); romURL = null; }
  $('download-rom').removeAttribute('href'); $('download-rom').setAttribute('aria-disabled', 'true');
  $('example-description').hidden = true; $('example-source').hidden = true;
  report('Загрузка образа…');
  $('file-name').textContent = 'Загрузка…'; $('file-info').textContent = ''; $('file-hash').textContent = '';
  try {
    // A BIN is at most 64 KiB. HEX ASCII is bounded separately, before reading it.
    if (file.size > 2 * 1024 * 1024) throw Error('Файл слишком большой: ожидается образ до 64 КиБ');
    const bytes = /\.(hex|ihx|ihex)$/i.test(file.name) ? parseIntelHex(await file.text()) : validateBinary(new Uint8Array(await file.arrayBuffer()));
    let sha = '';
    if (crypto.subtle) sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
    if (example && (bytes.length !== example.bytes || (sha && sha !== example.sha256))) throw Error('ROM примера не совпадает с проверенным образом');
    if (ticket !== loadTicket) return;
    firmware = bytes; filename = file.name;
    if (example) {
      $('hz').value = example.hz; $('memory').value = example.memory; $('output').value = example.output; $('seconds').value = 90;
      updateMachineNotes();
      $('example-description').textContent = example.description; $('example-description').hidden = false;
      $('example-source').href = exampleSourceURL(example); $('example-source').hidden = false;
    }
    $('file-name').textContent = example?.title || filename;
    $('file-info').textContent = `${number(bytes.length)} байт · ${/\.(hex|ihx|ihex)$/i.test(filename) ? 'Intel HEX' : 'бинарный образ'} · PC 0000h`;
    $('file-hash').textContent = sha ? `SHA-256 ${sha}` : '';
    romURL = URL.createObjectURL(new Blob([bytes], { type: 'application/octet-stream' }));
    $('download-rom').href = romURL; $('download-rom').download = filename.replace(/\.[^.]+$/, '') + '.bin'; $('download-rom').setAttribute('aria-disabled', 'false');
    report('Образ загружен. Выберите параметры и нажмите «Эмулировать».'); setBusy(false);
  } catch (error) {
    if (ticket !== loadTicket) return;
    firmware = null; selectedExample = null; renderCatalog(); $('file-name').textContent = 'Образ не загружен'; $('file-info').textContent = '';
    report(error.message, true); setBusy(false);
  }
}
async function run() {
  if (!firmware || starting) return;
  if (speaker.active) {
    const ticket = runTicket;
    try { await speaker.togglePause(); if (ticket !== runTicket) return; if (speaker.paused) stopScope(); else startScope(); worker?.postMessage({ kind: speaker.paused ? 'pause' : 'resume' }); $('playback-status').textContent = speaker.paused ? 'Пауза' : 'Звук из исполняемого ROM'; setBusy(!!worker); }
    catch (error) { if (ticket !== runTicket) return; resetPlayback(); report(error.message, true); }
    return;
  }
  if (worker) return;
  const hz = Number($('hz').value), seconds = Number($('seconds').value);
  if (!Number.isFinite(hz) || hz < 100000 || hz > 10000000 || !Number.isFinite(seconds) || seconds < 0.1 || seconds > 120) {
    report('Частота: 100 000–10 000 000 Гц. Лимит времени: 0,1–120 с.', true); return;
  }
  resetPlayback(); const ticket = ++runTicket;
  const runOptions = { hz, seconds, output: $('output').value, memoryMode: $('memory').value, inputByte: Number($('input-byte').value), realtime: true };
  $('progress').max = seconds; starting = true; setBusy(true); report('Запуск эмуляции и звука…');
  try {
    if (!await speaker.start(soundOptions()) || ticket !== runTicket) return;
    starting = false; startScope(); setBusy(true); $('playback-status').textContent = 'Звук из исполняемого ROM';
    const activeWorker = worker = createWorker();
    worker.onmessage = event => {
      if (worker !== activeWorker) return;
      const message = event.data;
      if (message.kind === 'audio') {
        speaker.push(message.audio); return;
      }
      $('steps').textContent = number(message.steps || 0); $('cycles').textContent = number(message.t || 0);
      $('cpu-time').textContent = `${((message.t || 0) / hz).toLocaleString('ru-RU', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} с`;
      $('progress').value = Math.min(seconds, (message.t || 0) / hz);
      if (message.kind === 'progress') {
        updateRegisters(message); $('edges').textContent = number(message.edges); $('writes').textContent = number(message.memWrites); $('io-writes').textContent = number(message.ioWrites);
        report(`Выполнено ${number(message.steps)} команд. Процессорное время: ${message.seconds.toFixed(2)} с.`); return;
      }
      stopWorker();
      if (message.kind === 'error') { speaker.reset(); setBusy(false); $('playback-status').textContent = 'Остановлено'; report(`Ошибка эмуляции: ${message.message}`, true); return; }
      updateRegisters(message);
      speaker.finish();
      $('edges').textContent = number(message.edges); $('writes').textContent = number(message.memWrites); $('io-writes').textContent = number(message.ioWrites);
      const reason = message.stopReason === 'HLT' ? 'HLT' : message.stopReason === 'time_limit' ? 'лимит времени' : 'лимит команд';
      report(`Завершение: ${reason}. ${number(message.steps)} команд · ${number(message.t)} T · ${(message.t / hz).toFixed(3)} с.`);
    };
    worker.onerror = event => { if (worker === activeWorker) { speaker.reset(); stopWorker(); $('playback-status').textContent = 'Остановлено'; report(`Ошибка фонового эмулятора: ${event.message}`, true); } };
    const copy = firmware.slice(); worker.postMessage({ ...runOptions, rate, rom: copy.buffer }, [copy.buffer]);
  } catch (error) { if (ticket === runTicket) { starting = false; speaker.reset(); stopWorker(); report(error.message, true); } }
}

$('load').addEventListener('click', () => $('file').click());
$('file').addEventListener('change', () => loadFile($('file').files[0]));
$('run').addEventListener('click', run);
$('cancel').addEventListener('click', () => { resetPlayback(); report('Сброс на начало. Нажмите «Эмулировать», чтобы запустить прошивку.'); });
for (const id of ['filter', 'normalize']) $(id).addEventListener('change', () => { speaker.configure(soundOptions()); redrawScope(); });
$('volume').addEventListener('input', () => speaker.volume(Number($('volume').value)));
new ResizeObserver(redrawScope).observe($('scope'));
function updateMachineNotes() {
  $('signal-label').textContent = $('output').value === 'inte' ? 'INTE' : '/WR';
  $('memory-note').textContent = $('memory').value === 'rom' ? '32-КиБ образ зеркалируется по A15. Записи дают /WR, содержимое ПЗУ сохраняется.' : $('memory').value === 'ramupper' ? 'Адреса 8000–FFFF доступны для записи. A15 участвует в адресации.' : 'Все 64 КиБ доступны для чтения и записи, включая загруженный код.';
}
for (const input of machineInputs) input.addEventListener('change', () => {
  resetPlayback(); report(firmware ? 'Параметры изменены. Запустите эмуляцию заново.' : 'Загрузите образ прошивки.');
  updateMachineNotes();
});
$('search').addEventListener('input', renderCatalog);
for (const name of ['dragenter', 'dragover']) $('drop-zone').addEventListener(name, event => { event.preventDefault(); $('drop-zone').classList.add('drag-over'); });
for (const name of ['dragleave', 'drop']) $('drop-zone').addEventListener(name, event => { event.preventDefault(); $('drop-zone').classList.remove('drag-over'); });
$('drop-zone').addEventListener('drop', event => loadFile(event.dataTransfer.files[0]));
window.addEventListener('keydown', event => {
  if (event.code === 'Space' && !['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'A', 'SUMMARY'].includes(document.activeElement.tagName)) { event.preventDefault(); run(); }
});
window.addEventListener('beforeunload', () => { stopScope(); speaker.reset(); stopWorker(); if (romURL) URL.revokeObjectURL(romURL); });
clearResult(); setBusy(false); initializeExamples();
