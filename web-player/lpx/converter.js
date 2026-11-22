import { MAX_SAMPLES } from './codec.js';

const $ = id => document.getElementById(id);
let source = null, worker = null, running = false, job = 0, urls = [], output = null;
const status = (text, error = false) => { $('convert-status').textContent = text; $('convert-status').classList.toggle('error', error); };
const baseName = name => name.replace(/\.[^.]+$/, '').replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').slice(0, 120) || 'audio';
function select(file) {
  if (running) return;
  if (!file.size || file.size > 100 * 1024 * 1024) { status('Выберите аудиофайл размером до 100 МБ.', true); return; }
  source = file;
  $('source-name').textContent = file.name;
  $('source-summary').textContent = `${(file.size / 1024).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} КБ · готов к конвертации`;
  $('convert').disabled = false;
  status('Выберите профиль и частоту, затем нажмите «В LPX V9».');
}
$('source-open').onclick = () => $('source-file').click();
$('source-file').onchange = () => { if ($('source-file').files[0]) select($('source-file').files[0]); $('source-file').value = ''; };
$('source-drop').addEventListener('dragover', event => { event.preventDefault(); event.stopPropagation(); event.currentTarget.classList.add('dragging'); });
$('source-drop').addEventListener('dragleave', event => event.currentTarget.classList.remove('dragging'));
$('source-drop').addEventListener('drop', event => {
  event.preventDefault(); event.stopPropagation(); event.currentTarget.classList.remove('dragging');
  if (event.dataTransfer.files.length === 1) select(event.dataTransfer.files[0]);
  else status('Выберите один исходный аудиофайл.', true);
});
function busy(value) {
  running = value;
  ['source-open', 'source-file', 'encode-profile', 'encode-rate', 'convert'].forEach(id => { $(id).disabled = value || (id === 'convert' && !source); });
  $('cancel-convert').hidden = !value;
}
function stop() { if (worker) worker.terminate(); worker = null; busy(false); }
$('cancel-convert').onclick = () => { job++; stop(); status('Конвертация отменена.'); };
function link(blob, name) {
  const url = URL.createObjectURL(blob); urls.push(url);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name;
  return anchor;
}
function appendResult(result) {
  const name = output.stem + '.lpx';
  const row = document.createElement('div'); row.className = 'result-row';
  const description = document.createElement('span');
  const title = document.createElement('b'); title.textContent = name;
  const meta = document.createElement('small'); meta.textContent = `${(result.samples / output.rate).toLocaleString('ru-RU', { maximumFractionDigits: 3 })} с · ${result.bytes.length.toLocaleString('ru-RU')} Б · ${result.long ? 'LPX V9 Long' : 'LPX V9'}`;
  description.append(title, meta);
  const actions = document.createElement('div'); actions.className = 'result-actions';
  const preview = document.createElement('button'); preview.className = 'button button-outline'; preview.textContent = 'Слушать';
  preview.onclick = () => {
    document.dispatchEvent(new CustomEvent('lpx-open', { detail: { name, bytes: result.bytes } }));
    $('player').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'center' });
  };
  const download = link(new Blob([result.bytes], { type: 'application/octet-stream' }), name);
  download.className = 'button button-outline'; download.textContent = 'Скачать LPX';
  actions.append(preview, download); row.append(description, actions); $('convert-results').append(row);
}
$('convert').onclick = async () => {
  if (!source || running) return;
  const id = ++job, rate = Number($('encode-rate').value), profile = Number($('encode-profile').value);
  output = { stem: baseName(source.name), rate, profile };
  urls.forEach(url => URL.revokeObjectURL(url)); urls = [];
  $('convert-results').replaceChildren(); $('convert-progress').value = 0;
  busy(true); status('Читаем аудио и пересчитываем частоту…');
  try {
    const buffer = await source.arrayBuffer();
    if (id !== job) return;
    const decoder = new OfflineAudioContext(1, 1, rate);
    let audio;
    try { audio = await decoder.decodeAudioData(buffer); }
    catch { throw new Error('Браузер не смог прочитать этот формат. Попробуйте WAV, MP3, FLAC, OGG или M4A без DRM. Поддержка зависит от браузера.'); }
    if (id !== job) return;
    if (!audio.length || audio.sampleRate !== rate) throw new Error('Не удалось подготовить аудио в выбранной частоте.');
    if (audio.length > MAX_SAMPLES) throw new Error('Запись превышает предел браузерного энкодера — 32 000 000 отсчётов. Выберите более короткую запись или меньшую частоту.');
    const channels = Array.from({ length: audio.numberOfChannels }, (_, index) => audio.getChannelData(index));
    const pcm = new Int16Array(audio.length); let clipped = 0;
    for (let i = 0; i < pcm.length; i++) {
      let sample = 0; for (const channel of channels) sample += channel[i] / channels.length;
      if (!Number.isFinite(sample)) throw new Error('Исходник содержит некорректные аудиосэмплы.');
      const value = Math.round(sample * 32768); if (value < -32768 || value > 32767) clipped++;
      pcm[i] = Math.min(32767, Math.max(-32768, value));
    }
    $('source-summary').textContent = `${audio.duration.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} с · ${channels.length} кан. → моно · ${rate / 1000} кГц${clipped ? ` · насыщение ${clipped} отсч.` : ''}`;
    worker = new Worker(new URL('./encode-worker.js?v=20261122-prefix-search', import.meta.url), { type: 'module' });
    worker.onerror = event => { event.preventDefault(); if (id === job) { stop(); status('Не удалось запустить энкодер. Обновите страницу и повторите.', true); } };
    worker.onmessage = ({ data }) => {
      if (id !== job) return;
      if (data.error) { stop(); status(data.error, true); return; }
      if (data.progress !== undefined) {
        const percent = Math.round(data.progress * 100); $('convert-progress').value = percent;
        status(`Кодирование: ${percent}%`);
      }
      if (data.result) {
        appendResult(data.result);
        stop(); $('convert-progress').value = 100;
        status(`Готово: один файл · ${(data.result.bytes.length / 1024).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} КБ.`);
      }
    };
    worker.postMessage({ pcm: pcm.buffer, sampleRate: rate, profile }, [pcm.buffer]);
  } catch (error) { if (id === job) { stop(); status(error.message || 'Не удалось конвертировать аудио.', true); } }
};
