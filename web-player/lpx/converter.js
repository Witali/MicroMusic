import { MAX_SAMPLES, MAX_STREAM_SAMPLES } from './codec.js?v=20261124-common-timbre';
import { supportsSimd } from './encoder-backend.js?v=20261124-common-timbre';
import { removeTemporaryInput, recoverTemporaryInputs } from './audio-source.js?v=20261124-common-timbre';

const $ = id => document.getElementById(id);
if (!supportsSimd()) {
  $('encode-backend').querySelector('option[value="simd"]').disabled = true;
  $('backend-note').textContent = 'В этом браузере доступно обычное кодирование. Авто выберет его.';
}
let source = null, worker = null, running = false, job = 0, urls = [], output = null;
let temporaryName=null;
const recovery=recoverTemporaryInputs().catch(()=>{});
async function cleanTemporary(name){
  for(let attempt=0;attempt<5;attempt++)try{await removeTemporaryInput(name);return;}
  catch(error){if(attempt===4)throw error;await new Promise(resolve=>setTimeout(resolve,50*2**attempt));}
}
function applyProfileConstraints() {
  $('encode-rate').disabled = running;
  $('encode-allowance').value='0';$('encode-allowance').disabled=true;
  $('bitrate-note').hidden=false;
}
$('encode-profile').onchange = applyProfileConstraints;
applyProfileConstraints();
function applyLevelSettings() {
  const enabled = $('encode-level').checked;
  $('encode-target').disabled = running || !enabled;
  $('encode-max-gain').disabled = running || !enabled;
  $('target-value').value = `${$('encode-target').value} LUFS`;
  $('max-gain-value').value = `+${$('encode-max-gain').value} дБ`;
}
$('encode-level').onchange = applyLevelSettings;
$('encode-target').oninput = applyLevelSettings;
$('encode-max-gain').oninput = applyLevelSettings;
applyLevelSettings();
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
  ['source-open', 'source-file', 'encode-profile', 'encode-rate', 'encode-backend', 'encode-processing', 'encode-allowance', 'encode-level', 'convert'].forEach(id => { $(id).disabled = value || (id === 'convert' && !source); });
  applyProfileConstraints();
  applyLevelSettings();
  $('cancel-convert').hidden = !value;
}
function stop() { if (worker) worker.terminate(); worker = null; const name=temporaryName;temporaryName=null;if(name)void cleanTemporary(name).catch(()=>status('Не удалось удалить временные данные. Очистите локальные данные этого сайта в браузере.',true));busy(false); }
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
  const backend = result.backend === 'simd' ? 'SIMD' : 'Обычное';
  const meta = document.createElement('small'); meta.textContent = `${(result.samples / output.rate).toLocaleString('ru-RU', { maximumFractionDigits: 3 })} с · ${result.bytes.length.toLocaleString('ru-RU')} Б · ${result.long ? 'LPX V9 Long' : 'LPX V9'} · ${backend}${result.processing === 'stream' ? ' · потоковая обработка' : ''}`;
  meta.textContent+=` · P${output.profile}`;
  description.append(title, meta);
  if (result.memoryFallback) {
    const note = document.createElement('small');
    note.textContent = 'Сохранён полностью проверенный контрольный вариант: для финального сравнения качества не хватило памяти.';
    description.append(note);
  }
  if (result.loudness) {
    const note = document.createElement('small'), level = result.loudness;
    const number = value => value.toLocaleString('ru-RU', { maximumFractionDigits: 1 });
    if (level.status === 1) {
      note.textContent = `Громкость до сжатия: ${number(level.input)} → ${number(level.prepared)} LUFS · усиление ${level.gainDb >= 0 ? '+' : ''}${number(level.gainDb)} дБ${level.limited ? ' · ограничено пиками' : level.gainLimited ? ' · достигнут предел усиления' : ''}`;
      if (Number.isFinite(level.decoded)) note.textContent += ` · после LPX: ${number(level.decoded)} LUFS`;
    } else note.textContent = level.status === 2 ? 'Громкость сохранена: запись короче 0,4 с.' : 'Громкость сохранена: тишина или уровень ниже порога измерения.';
    description.append(note);
  }
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
  const id = ++job, rate = Number($('encode-rate').value), profile = Number($('encode-profile').value), backend = $('encode-backend').value;
  const sizeAllowancePercent = Number($('encode-allowance').value);
  const processing = $('encode-processing').value;
  const normalization = $('encode-level').checked ? 'loudness' : 'preserve';
  const targetLufs = Number($('encode-target').value), maxGainDb = Number($('encode-max-gain').value);
  output = { stem: baseName(source.name), rate, profile };
  urls.forEach(url => URL.revokeObjectURL(url)); urls = [];
  $('convert-results').replaceChildren(); $('convert-progress').value = 0;
  busy(true); status('Читаем аудио и пересчитываем частоту…');
  try {
    const incrementalAudio=/\.(?:m4a|mp4|mp3|aac|wav)$/i.test(source.name)||['audio/mp4','video/mp4','audio/x-m4a','audio/mpeg','audio/aac','audio/wav','audio/x-wav'].includes(source.type);
    let audio,channels,pcm;
    const streamingAudio=incrementalAudio;
    if(!streamingAudio){
    const buffer = await source.arrayBuffer();
    if (id !== job) return;
    const decoder = new OfflineAudioContext(1, 1, rate);
    try { audio = await decoder.decodeAudioData(buffer); }
    catch { throw new Error('Браузер не смог прочитать этот формат. Попробуйте WAV, MP3, FLAC, OGG или M4A без DRM. Поддержка зависит от браузера.'); }
    if (id !== job) return;
    if (!audio.length || audio.sampleRate !== rate) throw new Error('Не удалось подготовить аудио в выбранной частоте.');
    const fast=processing==='stream'||processing==='auto'&&audio.length>128000;
    const limit=fast?MAX_STREAM_SAMPLES:MAX_SAMPLES;
    if (audio.length > limit) throw new Error(fast?'Быстрая потоковая обработка поддерживает до 64 000 000 отсчётов.':'Полный поиск и потоковое уточнение поддерживают до 32 000 000 отсчётов. Выберите быструю потоковую обработку.');
    channels = Array.from({ length: audio.numberOfChannels }, (_, index) => audio.getChannelData(index));
    }
    if(streamingAudio){await recovery;if(id!==job)return;temporaryName='pcm-'+crypto.randomUUID()+'.tmp';}
    const streaming = streamingAudio || processing === 'stream' || processing === 'stream-refine' || processing === 'auto' && audio.length > 128000;
    let clipped = 0;
    const pcmRange = (offset, count, trackClipping = false) => {
      if (!Number.isInteger(offset) || !Number.isInteger(count) || offset < 0 || count < 1 || offset + count > audio.length) throw new Error('Некорректный запрос порции аудио.');
      const pcm = new Int16Array(count);
      for (let i = 0; i < count; i++) {
        let sample = 0; for (const channel of channels) sample += channel[offset + i] / channels.length;
        if (!Number.isFinite(sample)) throw new Error('Исходник содержит некорректные аудиосэмплы.');
        const value = Math.round(sample * 32768); if (trackClipping && (value < -32768 || value > 32767)) clipped++;
        pcm[i] = Math.min(32767, Math.max(-32768, value));
      }
      return pcm;
    };
    pcm = streaming ? null : pcmRange(0, audio.length, true);
    $('source-summary').textContent = streamingAudio ? 'Читаем аудио по порциям…' : `${audio.duration.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} с · ${channels.length} кан. → моно · ${rate / 1000} кГц${clipped ? ` · насыщение ${clipped} отсч.` : ''}`;
    worker = new Worker(new URL('./encode-worker.js?v=20261124-common-timbre', import.meta.url), { type: 'module' });
    worker.onerror = event => { event.preventDefault(); if (id === job) { stop(); status('Не удалось запустить энкодер. Обновите страницу и повторите.', true); } };
    worker.onmessage = ({ data }) => {
      if (id !== job) return;
      if(data.sourceInfo){const info=data.sourceInfo;$('source-summary').textContent=`${info.duration.toLocaleString('ru-RU',{maximumFractionDigits:2})} с · ${info.channels} кан. → моно · ${rate/1000} кГц · потоковое чтение ${info.kind.toUpperCase()}`;return;}
      if (data.read) {
        try {
          const portion = pcmRange(data.read.offset, data.read.samples);
          worker.postMessage({ readReply: data.read.id, pcm: portion.buffer }, [portion.buffer]);
        } catch (error) { worker.postMessage({ readReply: data.read.id, error: error.message }); }
        return;
      }
      if (data.error) { stop(); status(data.error, true); return; }
      if (data.progress !== undefined) {
        if (data.phase) {
          $('convert-progress').value = Math.round(data.progress * 100);
          const phases = { source:'Декодируем аудио по порциям', measure: 'Измеряем громкость всей записи', encode: 'Кодируем по порциям', verify: 'Проверяем непрерывный файл', quality: 'Проверяем итоговое качество', done: 'Готовим результат' };
          status(`${phases[data.phase] || 'Обрабатываем запись'}… ${(data.progress * 100).toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`);
        } else if (data.progress < 1) {
          $('convert-progress').removeAttribute('value');
          status('Адаптивный поиск и проверка качества… Для длинных записей это может занять несколько минут.');
        }
      }
      if (data.result) {
        appendResult(data.result);
        stop(); $('convert-progress').value = 100;
        const name = data.result.backend === 'simd' ? 'SIMD' : 'Обычное';
        const elapsed = (data.result.elapsedMs / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 3 });
        status(`Готово: один файл · ${(data.result.bytes.length / 1024).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} КБ · ${name} · кодирование ${elapsed} с.`);
      }
    };
    const settings = { sampleRate: rate, profile, backend, sizeAllowancePercent:0, normalization, targetLufs, maxGainDb,accuracy:true };
    if(streamingAudio)worker.postMessage({...settings,source,temporaryName,processingSelection:processing});
    else if (streaming) worker.postMessage({ ...settings, processing: 'stream', samples: audio.length, calls: processing === 'stream-refine' ? 4 : 0 });
    else worker.postMessage({ ...settings, pcm: pcm.buffer }, [pcm.buffer]);
  } catch (error) { if (id === job) { stop(); status(error.message || 'Не удалось конвертировать аудио.', true); } }
};
