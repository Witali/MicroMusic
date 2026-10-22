// Same-origin, self-contained browser integration tests for this project's UI.
// Open browser-smoke.html via the local server and press the test button.
const frame = document.getElementById('player'), output = document.getElementById('result');
const messages = [];
const wait = async predicate => { const start = performance.now(); while (!predicate()) { if (performance.now() - start > 20000) throw Error('Timeout'); await new Promise(resolve => setTimeout(resolve, 20)); } };
const check = (condition, message) => { if (!condition) throw Error(message); };
const log = message => { messages.push(message); output.textContent = messages.join('\n'); };
const ready = async () => { await wait(() => frame.contentDocument?.getElementById('registers')?.children.length === 8); return frame.contentDocument; };
const load = async (document, bytes, name) => {
  const transfer = new DataTransfer(); transfer.items.add(new File([bytes], name));
  const input = document.getElementById('file'); input.value = ''; input.files = transfer.files;
  input.dispatchEvent(new Event('change', { bubbles: true }));
  await wait(() => !document.getElementById('run').disabled || !document.getElementById('error').hidden);
};
const set = (document, id, value) => { const el = document.getElementById(id); el.value = value; el.dispatchEvent(new Event('change', { bubbles: true })); };
const run = async document => {
  document.getElementById('run').click();
  await wait(() => document.getElementById('status').textContent.includes('Завершение:') || !document.getElementById('error').hidden);
  check(document.getElementById('error').hidden, document.getElementById('error').textContent);
  await wait(() => document.getElementById('run').textContent.includes('Эмулировать'));
};
async function suite(target) {
  frame.src = target;
  await new Promise(resolve => frame.addEventListener('load', resolve, { once: true }));
  const doc = await ready(), errors = [];
    frame.contentWindow.addEventListener('error', event => errors.push(event.message));
  check(doc.getElementById('run').disabled, 'empty page must not run');
  check(!doc.querySelector('audio'), 'no separate audio player');
  await load(doc, Uint8Array.of(0xfb, 0x00, 0xf3, 0x76), 'inte.bin'); await run(doc);
  check(doc.getElementById('cycles').textContent === '19', 'EI/NOP/DI/HLT must be 19 T');
  check(doc.getElementById('edges').textContent === '2', 'two INTE edges');
  check(doc.getElementById('download').hasAttribute('href'), 'WAV download');
  const firstWav = doc.getElementById('download').href;
  set(doc, 'filter', '0-1');
  check(doc.getElementById('download').href !== firstWav, 'filter rebuilds WAV');
  const wav = new DataView(await (await fetch(doc.getElementById('download').href)).arrayBuffer());
  check(wav.getUint32(24, true) === 96000, 'WAV sample rate');
  check(doc.getElementById('cycles').textContent === '19', 'filter preserves CPU result');
  log(`PASS ${target}: BIN → INTE → HLT → WAV 96 kHz; filter`);

  await load(doc, ':04000000FB00F37698\n:00000001FF\n', 'good.hex'); await run(doc);
  check(doc.getElementById('cycles').textContent === '19', 'HEX loads same code');
  await load(doc, ':04000000FB00F37600\n:00000001FF\n', 'bad.hex');
  check(!doc.getElementById('error').hidden && doc.getElementById('run').disabled, 'bad HEX invalidates previous ROM');
  check(!doc.getElementById('download').hasAttribute('href'), 'bad HEX invalidates previous WAV');
  log(`PASS ${target}: valid HEX; checksum rejection clears stale image/audio`);

  await load(doc, Uint8Array.of(0x31, 0, 0x30, 0x21, 0x34, 0x12, 0xe5, 0x21, 0xcd, 0xab, 0xe1, 0x76), 'stack.bin');
  set(doc, 'memory', 'allram'); set(doc, 'output', 'wr'); await run(doc);
  check(doc.getElementById('writes').textContent === '2', 'PUSH must write two bytes');
  check(doc.getElementById('edges').textContent === '4', 'PUSH must generate four WR edges');
  check(doc.getElementById('cpu-status').textContent.includes('SP 3000'), 'SP restored');
  check(doc.getElementById('registers').children[4].textContent === 'H12', 'H restored');
  check(doc.getElementById('registers').children[5].textContent === 'L34', 'L restored');
  log(`PASS ${target}: RAM stack; /WR pulses; register inspector`);

  await load(doc, Uint8Array.of(0xc3, 0, 0), 'loop.bin');
  set(doc, 'seconds', '120'); doc.getElementById('run').click();
  await wait(() => doc.getElementById('run').textContent.includes('Пауза'));
  await wait(() => doc.getElementById('elapsed').textContent !== '00:00.0');
  doc.getElementById('run').click();
  await wait(() => doc.getElementById('run').textContent.includes('Продолжить'));
  const pausedAt = doc.getElementById('elapsed').textContent;
  await new Promise(resolve => setTimeout(resolve, 150));
  check(doc.getElementById('elapsed').textContent === pausedAt, 'paused audio clock');
  const pausedSteps = doc.getElementById('steps').textContent;
  await new Promise(resolve => setTimeout(resolve, 100));
  check(doc.getElementById('steps').textContent === pausedSteps, 'paused CPU');
  check(Number(doc.getElementById('cycles').textContent.replace(/\D/g, '')) / 3500000 < 3, 'bounded live lookahead');
  doc.getElementById('run').click(); await wait(() => doc.getElementById('run').textContent.includes('Пауза'));
  doc.getElementById('cancel').click();
  check(doc.getElementById('status').textContent.includes('Сброс'), 'reset');
  check(!doc.getElementById('run').disabled && !doc.getElementById('hz').disabled, 'controls reenabled');
  await load(doc, Uint8Array.of(0x08), 'illegal.bin'); await (async () => {
    doc.getElementById('run').click(); await wait(() => !doc.getElementById('error').hidden);
    check(doc.getElementById('error').textContent.includes('Undocumented'), 'opcode trap');
  })();
  check(errors.length === 0, errors.join('\n'));
  log(`PASS ${target}: live audio clock; pause/resume/reset; opcode error; no separate audio player`);
}
document.getElementById('test').onclick = async () => {
  messages.length = 0; document.getElementById('test').disabled = true;
  try {
    await suite('../'); await suite('../Intel_8080_ROM_Player.html');
    frame.classList.add('mobile');
    const doc = await ready();
    check(doc.documentElement.scrollWidth <= frame.clientWidth, 'mobile horizontal overflow');
    await load(doc, Uint8Array.of(0xfb, 0, 0xf3, 0x76), 'inte.bin'); await run(doc);
    log('PASS responsive layout: 390 px, no horizontal overflow');
    log('ALL BROWSER SMOKE TESTS PASSED');
  } catch (error) { log('FAIL: ' + error.message); }
  finally { document.getElementById('test').disabled = false; }
};
document.getElementById('mobile').onclick = () => frame.classList.toggle('mobile');
