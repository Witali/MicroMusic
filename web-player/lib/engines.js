export const DEFAULT_ENGINE = 'wasm';

// Load only the selected engine: JS playback also works without WebAssembly.
export async function createRenderer(entry, sampleRate, controls, engine = DEFAULT_ENGINE) {
  if (engine !== 'js' && engine !== 'wasm') throw new Error('Unknown AVR engine: ' + engine);
  if (entry.device === 'attiny88' && engine !== 'js') throw new Error('ATtiny88 playback requires the JavaScript engine');
  const { Renderer } = await (engine === 'js' ? import('./renderer-js.js?v=20261024-ocr0a') : import('./renderer.js?v=20261024-ocr0a'));
  const renderer = new Renderer(entry, sampleRate, controls);
  renderer.engine = engine;
  return renderer;
}
