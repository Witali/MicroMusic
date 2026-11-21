import { encodeWav } from './codec.js';

const $ = id => document.getElementById(id);
const audio = $('audio'), canvas = $('wave'), context = canvas.getContext('2d');
const controls = ['play', 'restart', 'seek', 'loop', 'export'];
const number = (value, digits = 2) => value.toLocaleString('ru-RU', { maximumFractionDigits: digits });
const clock = value => {
  const total = Math.floor(Math.max(0, value || 0) * 100);
  return `${Math.floor(total / 6000)}:${String(Math.floor(total / 100) % 60).padStart(2, '0')}.${String(total % 100).padStart(2, '0')}`;
};
let worker, loadId = 0, clip = null, wavUrl = null, frame = 0, lastVolume = 0.75;
audio.volume = 0.75;
function message(text, error = false) { $('message').textContent = text; $('message').classList.toggle('error', error); }
try {
  worker = new Worker(new URL('./decode-worker.js', import.meta.url), { type: 'module' });
  worker.onmessage = ({ data }) => {
    if (data.id !== loadId) return;
    $('open').textContent = 'Открыть файл';
    if (data.error) { message(data.error, true); return; }
    install(data.result);
  };
  worker.onerror = event => {
    event.preventDefault();
    message('Не удалось запустить декодер. Откройте страницу через HTTP/HTTPS и обновите её.', true);
    $('open').textContent = 'Открыть файл';
  };
} catch {
  message('Этот браузер не поддерживает Web Workers. Используйте современный браузер.', true);
  $('open').disabled = true;
}

$('open').onclick = () => $('file').click();
$('file').onchange = () => { if ($('file').files[0]) load($('file').files[0]); $('file').value = ''; };
const dropZone = $('drop-zone');
let dragDepth = 0;
dropZone.addEventListener('dragenter', event => { event.preventDefault(); dragDepth++; dropZone.classList.add('dragging'); });
dropZone.addEventListener('dragover', event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; });
dropZone.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; dropZone.classList.remove('dragging'); } });
document.addEventListener('dragover', event => event.preventDefault());
document.addEventListener('drop', event => {
  event.preventDefault(); dragDepth = 0; dropZone.classList.remove('dragging');
  const files = event.dataTransfer.files;
  if (files.length === 1) load(files[0]);
  else if (files.length > 1) message('Выберите один LPX V9 файл для воспроизведения.', true);
});
let requestedName = '';
async function load(file) {
  const id = ++loadId;
  $('open').textContent = 'Открыть файл';
  if (!worker) return;
  if (!file.size || file.size > 65535) { message('Выберите LPX V9 размером от 13 до 65 535 байт.', true); return; }
  requestedName = file.name;
  $('open').textContent = 'Декодирование…';
  message('Читаем LPX V9 и декодируем звук на вашем устройстве…');
  try {
    const buffer = await file.arrayBuffer();
    if (id === loadId) worker.postMessage({ id, buffer }, [buffer]);
  } catch {
    if (id === loadId) { $('open').textContent = 'Открыть файл'; message('Не удалось прочитать файл. Попробуйте выбрать его снова.', true); }
  }
}
function install(result) {
  audio.pause();
  if (wavUrl) URL.revokeObjectURL(wavUrl);
  clip = { ...result, name: requestedName };
  wavUrl = URL.createObjectURL(new Blob([encodeWav(clip.pcm, clip.sampleRate)], { type: 'audio/wav' }));
  audio.src = wavUrl;
  audio.load();
  audio.playbackRate = Number($('speed').value);
  $('filename').textContent = clip.name;
  const profile = clip.profile === 15 ? 'Sparse80' : `P${clip.profile}`;
  $('profile-badge').textContent = profile;
  $('file-summary').textContent = `LPX V9 · ${number(clip.sampleRate / 1000)} кГц · ${number(clip.bytes / 1024)} КБ`;
  $('info-profile').textContent = profile + (clip.extraPulses ? ' + extra' : '');
  $('info-rate').textContent = `${number(clip.sampleRate / 1000)} кГц`;
  $('info-duration').textContent = `${number(clip.duration, 3)} с`;
  $('info-size').textContent = `${number(clip.bytes, 0)} Б`;
  $('info-bitrate').textContent = `${number(clip.bitrate / 1000)} кбит/с`;
  $('duration').textContent = clock(clip.duration);
  $('seek').max = clip.duration;
  controls.forEach(id => { $(id).disabled = false; });
  $('wave-empty').hidden = true;
  $('play-state').textContent = 'Готов к воспроизведению';
  message('Файл готов. Нажмите «Слушать» или пробел.');
  update();
}

async function toggle() {
  if (!clip) return;
  if (!audio.paused) { audio.pause(); return; }
  if (audio.ended || audio.currentTime >= clip.duration) audio.currentTime = 0;
  try { await audio.play(); }
  catch { message('Браузер не смог начать воспроизведение. Нажмите «Слушать» ещё раз.', true); }
}
$('play').onclick = toggle;
$('restart').onclick = () => { audio.currentTime = 0; update(); };
$('loop').onclick = () => { audio.loop = !audio.loop; $('loop').setAttribute('aria-pressed', String(audio.loop)); };
$('seek').oninput = () => { if (clip) { audio.currentTime = Math.min(clip.duration, Number($('seek').value)); update(); } };
$('speed').onchange = () => { audio.playbackRate = Number($('speed').value); };
function setVolume(value) {
  audio.volume = value; audio.muted = value === 0;
  $('volume').value = Math.round(value * 100);
  $('volume-value').value = `${Math.round(value * 100)}%`;
  const label = value ? 'Выключить звук' : 'Включить звук';
  $('mute').setAttribute('aria-label', label); $('mute').title = label;
  $('mute').setAttribute('aria-pressed', String(!value));
  if (value) lastVolume = value;
}
$('volume').oninput = () => setVolume(Number($('volume').value) / 100);
$('mute').onclick = () => setVolume(audio.volume ? 0 : lastVolume);
$('export').onclick = () => {
  if (!wavUrl || !clip) return;
  const anchor = document.createElement('a'); anchor.href = wavUrl;
  anchor.download = clip.name.replace(/\.lpx$/i, '') + '.wav';
  document.body.append(anchor); anchor.click(); anchor.remove();
};
document.addEventListener('keydown', event => {
  if (event.code === 'Space' && !event.repeat && !event.target.closest('input,button,select,textarea,a,[contenteditable]')) {
    event.preventDefault(); toggle();
  }
});
audio.addEventListener('play', () => {
  $('play-label').textContent = 'Пауза'; $('play-symbol').setAttribute('href', '#pause-icon');
  $('play-state').textContent = 'Воспроизведение';
  cancelAnimationFrame(frame); animate();
});
audio.addEventListener('pause', () => {
  $('play-label').textContent = 'Слушать'; $('play-symbol').setAttribute('href', '#play-icon');
  if (clip) $('play-state').textContent = audio.ended ? 'Воспроизведение завершено' : 'На паузе';
  cancelAnimationFrame(frame); update();
});
audio.addEventListener('ended', () => { $('play-state').textContent = 'Воспроизведение завершено'; update(); });
audio.addEventListener('timeupdate', update);
audio.addEventListener('error', () => { if (clip) message('Браузер не смог открыть декодированный звук.', true); });
function animate() { update(); if (!audio.paused) frame = requestAnimationFrame(animate); }
function update() {
  $('elapsed').textContent = clock(audio.currentTime);
  $('seek').value = audio.currentTime;
  $('seek').setAttribute('aria-valuetext', `${clock(audio.currentTime)} из ${clock(clip?.duration || 0)}`);
  draw();
}
function draw() {
  if (!context) return;
  const width = canvas.clientWidth, height = canvas.clientHeight, dpr = window.devicePixelRatio || 1;
  if (!width || !height) return;
  if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
    canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
  }
  context.setTransform(dpr, 0, 0, dpr, 0, 0); context.clearRect(0, 0, width, height);
  context.strokeStyle = '#303a33'; context.lineWidth = 1;
  for (let i = 0; i <= 4; i++) { const x = 1 + (width - 2) * i / 4; context.beginPath(); context.moveTo(x, 8); context.lineTo(x, height - 8); context.stroke(); }
  context.beginPath(); context.moveTo(0, height / 2); context.lineTo(width, height / 2); context.stroke();
  if (!clip) return;
  const count = Math.ceil(width / 4), progress = audio.currentTime / clip.duration;
  for (let i = 0; i < count; i++) {
    const start = Math.floor(i * clip.pcm.length / count), end = Math.max(start + 1, Math.floor((i + 1) * clip.pcm.length / count));
    let peak = 0;
    for (let j = start; j < end; j++) peak = Math.max(peak, Math.abs(clip.pcm[j] || 0));
    const amplitude = Math.max(1, peak / 32768 * (height - 22));
    context.fillStyle = i / count <= progress ? '#bdfb78' : '#70836a';
    context.fillRect(i * width / count, (height - amplitude) / 2, 2, amplitude);
  }
  context.fillStyle = '#d8ffc0'; context.fillRect(Math.min(width - 1, width * progress), 3, 1, height - 6);
}
new ResizeObserver(draw).observe(canvas);
window.addEventListener('pagehide', () => { audio.pause(); });
draw();
