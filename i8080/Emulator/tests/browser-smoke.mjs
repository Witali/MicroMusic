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
const finished = async document => {
  await wait(() => document.getElementById('status').textContent.includes('Завершение:') || !document.getElementById('error').hidden);
  check(document.getElementById('error').hidden, document.getElementById('error').textContent);
  await wait(() => document.getElementById('run').textContent.includes('Эмулировать'));
};
const run = async document => { document.getElementById('run').click(); await finished(document); };
async function suite(target) {
  frame.src = target;
  await new Promise(resolve => frame.addEventListener('load', resolve, { once: true }));
  const doc = await ready(), errors = [];
    frame.contentWindow.addEventListener('error', event => errors.push(event.message));
  await wait(() => !doc.getElementById('run').disabled && doc.querySelectorAll('[data-example]').length === 2);
  check(doc.getElementById('file-name').textContent.includes('32,11 кГц'), '109T / two pulses per sample tempo-preserving default');
  check(!doc.querySelector('audio'), 'no separate audio player');
  check(!doc.getElementById('download'), 'no WAV download control');
  check(doc.querySelector('.machine-spec').textContent.includes('244 инструкции'), 'instruction wording');
  check(doc.querySelector('.cpu-wire svg') && !doc.querySelector('.cpu-wire b'), 'speaker symbol');
  const catalog = await (await fetch('../examples.json')).json();
  for (const entry of catalog.entries) {
    doc.querySelector(`[data-example="${entry.id}"]`).click();
    await wait(() => !doc.getElementById('run').disabled && doc.getElementById('file-name').textContent === entry.title);
    const bytes = await (await fetch(doc.getElementById('download-rom').href)).arrayBuffer();
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(n => n.toString(16).padStart(2, '0')).join('');
    check(digest === entry.sha256, entry.id + ' ROM hash');
    check(doc.querySelector(`[data-example="${entry.id}"]`).getAttribute('aria-pressed') === 'true', 'selected example');
  }
  for (const id of ['uniform26-pwm108']) {
    const entry = catalog.entries.find(entry => entry.id === id);
    doc.querySelector(`[data-example="${id}"]`).click();
    await wait(() => !doc.getElementById('run').disabled && doc.getElementById('file-name').textContent === entry.title);
    const canvas = doc.getElementById('scope'), blank = canvas.toDataURL(), blankSize = `${canvas.width}x${canvas.height}`;
    check(/^\d+ мс$/.test(doc.querySelector('.scope-scale').textContent), 'time scale matches ATtiny13A format');
    set(doc, 'seconds', '2'); doc.getElementById('run').click();
    await wait(() => doc.getElementById('elapsed').textContent !== '00:00.0' && canvas.toDataURL() !== blank);
    const firstScope = canvas.toDataURL();
    await wait(() => canvas.toDataURL() !== firstScope);
    doc.getElementById('run').click();
    await wait(() => doc.getElementById('run').textContent.includes('Продолжить'));
    const pausedScope = canvas.toDataURL();
    await new Promise(resolve => setTimeout(resolve, 150));
    check(canvas.toDataURL() === pausedScope, 'scope freezes while paused');
    doc.getElementById('run').click();
    await wait(() => doc.getElementById('run').textContent.includes('Пауза'));
    await wait(() => canvas.toDataURL() !== pausedScope);
    await finished(doc);
    const endedScope = canvas.toDataURL();
    await new Promise(resolve => setTimeout(resolve, 100));
    check(canvas.toDataURL() === endedScope, 'scope freezes at end');
    const cycles = Number(doc.getElementById('cycles').textContent.replace(/\D/g, ''));
    check(cycles >= 7000000 && cycles <= 7000018, id + ' two-second execution');
    check(doc.getElementById('elapsed').textContent === '00:02.0', id + ' live audio drains');
    check(doc.getElementById('writes').textContent === '0', id + ' ROM-only execution');
    check(Number(doc.getElementById('edges').textContent.replace(/\D/g, '')) > 0, id + ' audible signal');
    doc.getElementById('cancel').click();
    check(canvas.toDataURL() === blank, `reset clears the live scope (${blankSize} → ${canvas.width}x${canvas.height})`);
  }
  set(doc, 'seconds', '90');
  log(`PASS ${target}: selected 108T music streams two seconds; live scope advances, freezes on pause/end, resumes and resets; no RAM writes`);
  const search = doc.getElementById('search'); search.value = '32,11 кГц'; search.dispatchEvent(new Event('input', { bubbles: true }));
  check(doc.querySelectorAll('[data-example]').length === 1, 'example search');
  doc.querySelector('[data-example="voice32"]').click();
  await wait(() => !doc.getElementById('run').disabled && doc.getElementById('file-name').textContent.includes('32,11 кГц'));
  search.value = ''; search.dispatchEvent(new Event('input', { bubbles: true }));
  await run(doc);
  check(Number(doc.getElementById('cycles').textContent.replace(/\D/g, '')) === 19700539, '109T / two pulses per sample full firmware and diagnostics');
  check(doc.getElementById('writes').textContent === '0', 'ROM-only voice');
  check(doc.getElementById('download-rom').hasAttribute('href'), 'example firmware download');
  doc.querySelector('[data-example="uniform26-pwm108"]').click();
  await wait(() => !doc.getElementById('run').disabled && doc.getElementById('file-name').textContent === catalog.entries.find(entry => entry.id === 'uniform26-pwm108').title);
  check(doc.getElementById('cycles').textContent === '0' && doc.getElementById('elapsed').textContent === '00:00.0', 'example switch clears prior result/audio');
  if (target.includes('ROM_Player')) {
    const resources = frame.contentWindow.performance.getEntriesByType('resource');
    check(!resources.some(resource => /\.(bin|json|mjs)(\?|$)/.test(resource.name)), 'standalone examples and engines stay embedded');
  }
  log(`PASS ${target}: two selected examples and ROM hashes; 109T / two pulses per sample default → HLT; search; source switching; embedded standalone library`);
  await load(doc, Uint8Array.of(0xfb, 0x00, 0xf3, 0x76), 'inte.bin'); await run(doc);
  check(!doc.querySelector('[data-example][aria-pressed="true"]'), 'upload deselects examples');
  check(doc.getElementById('cycles').textContent === '19', 'EI/NOP/DI/HLT must be 19 T');
  check(doc.getElementById('edges').textContent === '2', 'two INTE edges');
  const savedFirmware = new Uint8Array(await (await fetch(doc.getElementById('download-rom').href)).arrayBuffer());
  check(savedFirmware.join(',') === '251,0,243,118', 'downloaded BIN matches the loaded image');
  set(doc, 'filter', '0-1');
  check(doc.getElementById('cycles').textContent === '19', 'filter preserves CPU result');
  log(`PASS ${target}: BIN → INTE → HLT; firmware download; filter; no WAV export`);

  await load(doc, ':04000000FB00F37698\n:00000001FF\n', 'good.hex'); await run(doc);
  check(doc.getElementById('cycles').textContent === '19', 'HEX loads same code');
  await load(doc, ':04000000FB00F37600\n:00000001FF\n', 'bad.hex');
  check(!doc.getElementById('error').hidden && doc.getElementById('run').disabled, 'bad HEX invalidates previous ROM');
  check(!doc.getElementById('download-rom').hasAttribute('href'), 'bad HEX invalidates previous firmware download');
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
  doc.querySelector('[data-example="voice32"]').click();
  await wait(() => !doc.getElementById('run').disabled && doc.getElementById('file-name').textContent.includes('32,11 кГц'));
  check(doc.getElementById('elapsed').textContent === '00:00.0' && doc.getElementById('cycles').textContent === '0', 'switching a live example resets CPU and audio');
  check(doc.getElementById('memory').value === 'rom' && doc.getElementById('output').value === 'inte', 'example machine configuration');
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
