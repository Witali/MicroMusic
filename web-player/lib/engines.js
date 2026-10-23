export const DEFAULT_ENGINE = 'wasm';

// Load only the selected engine: JS playback also works without WebAssembly.
export async function createRenderer(entry, sampleRate, controls, engine = DEFAULT_ENGINE) {
  if (engine !== 'js' && engine !== 'wasm') throw new Error('Unknown AVR engine: ' + engine);
  const { Renderer } = await (engine === 'js' ? import('./renderer-js.js') : import('./renderer.js'));
  const renderer = new Renderer(entry, sampleRate, controls);
  renderer.engine = engine;
  return renderer;
}
