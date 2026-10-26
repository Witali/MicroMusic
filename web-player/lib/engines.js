export const DEFAULT_ENGINE = 'wasm';

// Load only the selected engine: JS playback also works without WebAssembly.
export async function createRenderer(entry, sampleRate, controls, engine = DEFAULT_ENGINE) {
  if (!['js','wasm','transpiled','device'].includes(engine)) throw new Error('Unknown AVR engine: ' + engine);
  if(entry.device==='attiny88'&&engine==='device')throw Error('The physical device engine supports only ATtiny13A');
  if(entry.devicePackage){
    if(!['device','transpiled'].includes(engine))throw Error('An ATtiny13A package requires the device engine or AVR → WASM');
    const {createPackageRenderer}=await import('./renderer-package.js');
    const renderer=await createPackageRenderer(entry,sampleRate,controls);renderer.engine=engine;return renderer;
  }
  const { Renderer } = await (engine === 'js' ? import('./renderer-js.js?v=20261025-board-um88-pipeline') : engine === 'transpiled' ? import('./renderer-transpiled.js') : engine === 'device' ? import('./renderer-device.js') : import('./renderer.js?v=20261025-board-um88-pipeline'));
  const renderer = new Renderer(entry, sampleRate, controls);
  renderer.engine = engine;
  return renderer;
}
