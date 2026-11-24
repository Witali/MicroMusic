// Export only standalone static application assets. GitHub Pages serves the
// tracked web-player/lpx directory from main; this bundle is optional.
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
const files = ['index.html', 'styles.css', 'app.js', 'codec.js', 'decode-worker.js', 'decoder.wasm', 'favicon.svg',
  'converter.js', 'encoder.js', 'encoding-policy.js', 'streaming.js', 'encoder-backend.js', 'encode-worker.js', 'encoder-adaptive.wasm', 'encoder-adaptive-simd.wasm',
  'audio-source.js', 'audio-demux.js', 'm4a-demux.js', 'input-resampler.wasm'];
for (const name of files) copyFileSync(join(root, 'web-player/lpx', name), join(destination, 'dist', name));
copyFileSync(join(root, 'Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LICENSE-pystoi.txt'), join(destination, 'dist/LICENSE-pystoi.txt'));
copyFileSync(join(root, 'Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LICENSE-libebur128.txt'), join(destination, 'dist/LICENSE-libebur128.txt'));
for (const name of ['encoder.wasm', 'encoder-simd.wasm']) {
  const old = join(destination, 'dist', name);
  if (lstatSync(old, { throwIfNoEntry: false })?.isFile()) rmSync(old);
}
// Retire only the obsolete asset from this application's earlier ZIP export.
const obsolete = join(destination, 'dist/zip.js');
if (lstatSync(obsolete, { throwIfNoEntry: false })?.isFile()) rmSync(obsolete);
// Remove the retired hosting configuration from an older local export.
const oldHosting=join(destination,'.openai/hosting.json');
const oldHostingInfo=lstatSync(oldHosting,{throwIfNoEntry:false});
if(oldHostingInfo && !oldHostingInfo.isFile())throw Error('Unexpected object at the retired hosting configuration path.');
if(oldHostingInfo)rmSync(oldHosting);
writeFileSync(join(destination, '.gitignore'), 'node_modules/\n');
console.log(`Exported ${files.length} static application assets to ${destination}`);
