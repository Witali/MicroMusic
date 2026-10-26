import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const root = new URL('../', import.meta.url);
const read = async name => (await readFile(new URL(name, root), 'utf8')).replace(/\r\n/g, '\n');
const stripExports = source => source.replace(/^export /gm, '');
const stripImports = source => source.replace(/^import .*\n/gm, '');
const core = stripExports(await read('core8080.mjs'));
const worker = stripImports(await read('worker.mjs'));
const signal = stripExports(await read('signal.mjs'));
const formats = stripExports(stripImports(await read('formats.mjs')));
const scriptString = text => JSON.stringify(text).replace(/</g, '\\u003c');
let app = stripImports(await read('app.mjs'));
const catalog = JSON.parse(await read('examples.json'));
for (const entry of catalog.entries) for (const variant of entry.variants)
  variant.base64 = (await readFile(new URL(variant.rom, root))).toString('base64');
const embeddedCatalog = `const EXAMPLE_CATALOG = JSON.parse(${scriptString(JSON.stringify(catalog))});\n`;
app = app.replace(/^async function getExampleCatalog\(\).*$/m, 'async function getExampleCatalog() { return EXAMPLE_CATALOG; }');
app = app.replace(/^async function readExample\(entry\).*$/m, 'async function readExample(entry) { return Uint8Array.from(atob(entry.base64), c => c.charCodeAt(0)).buffer; }');
let speaker = stripExports(await read('speaker.mjs'));
const worklet = signal + '\n' + stripExports(stripImports(await read('stream-audio.mjs'))) + '\n' + stripImports(await read('speaker-worklet.mjs'));
speaker = speaker.replace(/^function createWorkletURL\(\).*$/m, () => `function createWorkletURL() { return URL.createObjectURL(new Blob([${scriptString(worklet)}], { type: 'text/javascript' })); }`);
const workerFactory = `function createWorker() { const url = URL.createObjectURL(new Blob([${scriptString(core + '\n' + worker)}], { type: 'text/javascript' })); const worker = new Worker(url); URL.revokeObjectURL(url); return worker; }`;
app = app.replace(/^function createWorker\(\).*$/m, () => workerFactory);
const css = await read('../../web-player/styles.css') + '\n' + await read('styles.css');
let html = await read('index.html');
html = html.replace(/  <link rel="icon"[^\n]*\n/, '');
html = html.replace(/  <link rel="stylesheet"[^\n]*\n/g, '');
html = html.replace(/  <script type="module"[^\n]*\n/, `  <style>${css}</style>\n`);
html = html.replace('href="./Intel_8080_ROM_Player.html" download', 'href="https://witali.github.io/MicroMusic/i8080/Emulator/" target="_blank" rel="noopener"');
html = html.replace('↓ Автономный HTML-плеер', 'Открыть онлайн-версию ↗');
html = html.replace('href="../../web-player/"', 'href="https://witali.github.io/MicroMusic/web-player/"');
html = html.replace('</body>', () => `<script>\n${signal}\n${formats}\n${speaker}\n${embeddedCatalog}\n${app.replaceAll('</script', '<\\/script')}\n</script>\n</body>`);
const output = new URL('Intel_8080_ROM_Player.html', root);
if (process.argv.includes('--check')) {
  if (await readFile(output, 'utf8') !== html) throw Error('Standalone HTML is stale; run build-standalone.mjs');
  console.log('PASS: standalone HTML matches current sources');
} else { await writeFile(output, html, 'utf8'); console.log(fileURLToPath(output)); }
