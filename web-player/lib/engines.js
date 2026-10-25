export const DEFAULT_ENGINE = 'wasm';

// Load only the selected engine: JS playback also works without WebAssembly.
export async function createRenderer(entry, sampleRate, controls, engine = DEFAULT_ENGINE) {
  if (!['js','wasm','transpiled','device'].includes(engine)) throw new Error('Unknown AVR engine: ' + engine);
  if(entry.device==='attiny88'&&!['js','wasm'].includes(engine))throw Error('ATtiny88 requires the JS or WASM engine');
  if(entry.devicePackage){
    if(engine!=='device')throw Error('An ATtiny13A package requires the device engine');
    const {createPackageRenderer}=await import('./renderer-package.js');
    const renderer=await createPackageRenderer(entry,sampleRate,controls);renderer.engine=engine;return renderer;
  }
  const { Renderer } = await (engine === 'js' ? import('./renderer-js.js?v=20261025-attiny88-board') : engine === 'transpiled' ? import('./renderer-transpiled.js') : engine === 'device' ? import('./renderer-device.js') : import('./renderer.js?v=20261025-attiny88-board'));
  const renderer = new Renderer(entry, sampleRate, controls);
  renderer.engine = engine;
  return renderer;
}
