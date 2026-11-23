// Export only the standalone application. Never copy the enclosing Git history.
import { mkdirSync, copyFileSync, writeFileSync, lstatSync, rmSync } from 'node:fs';
import { resolve, join, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../../', import.meta.url));
const destination = resolve(process.argv[2] || join(root, 'build/lpx-site'));
if (!destination.startsWith(resolve(root, 'build') + sep)) throw new Error('Export must stay inside this checkout’s build directory.');
for (const path of [resolve(root, 'build'), destination, join(destination, 'dist'), join(destination, '.openai')]) {
  if (lstatSync(path, { throwIfNoEntry: false })?.isSymbolicLink()) throw new Error('Do not export through symbolic links.');
}
mkdirSync(join(destination, 'dist'), { recursive: true });
mkdirSync(join(destination, '.openai'), { recursive: true });
const files = ['index.html', 'styles.css', 'app.js', 'codec.js', 'decode-worker.js', 'decoder.wasm', 'favicon.svg',
  'converter.js', 'encoder.js', 'encoder-backend.js', 'encode-worker.js', 'encoder-adaptive.wasm', 'encoder-adaptive-simd.wasm'];
for (const name of files) copyFileSync(join(root, 'web-player/lpx', name), join(destination, 'dist', name));
copyFileSync(join(root, 'Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LICENSE-pystoi.txt'), join(destination, 'dist/LICENSE-pystoi.txt'));
for (const name of ['encoder.wasm', 'encoder-simd.wasm']) {
  const old = join(destination, 'dist', name);
  if (lstatSync(old, { throwIfNoEntry: false })?.isFile()) rmSync(old);
}
// Retire only the obsolete asset from this application's earlier ZIP export.
const obsolete = join(destination, 'dist/zip.js');
if (lstatSync(obsolete, { throwIfNoEntry: false })?.isFile()) rmSync(obsolete);
copyFileSync(join(root, 'web-player/lpx/.openai/hosting.json'), join(destination, '.openai/hosting.json'));
writeFileSync(join(destination, '.gitignore'), 'node_modules/\n.sites-*\n');
console.log(`Exported ${files.length} application assets and Site manifest to ${destination}`);
