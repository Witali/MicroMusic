import { createEncoder } from './encoder.js?v=20261124-stream-quality';

// Minimal module returning a v128.const. Validation runs no code or imports.
const simdProbe = new Uint8Array([0,97,115,109,1,0,0,0,1,5,1,96,0,1,123,3,2,1,0,
  10,22,1,20,0,253,12,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,11]);
export function supportsSimd() {
  try { return WebAssembly.validate(simdProbe); } catch { return false; }
}
async function fetchBinary(backend) {
  const name = backend === 'simd' ? 'encoder-adaptive-simd.wasm' : 'encoder-adaptive.wasm';
  const response = await fetch(new URL(`./${name}?v=20261124-stream-quality`, import.meta.url));
  if (!response.ok) throw new Error('Не удалось загрузить WASM-кодировщик.');
  return response.arrayBuffer();
}
export async function createEncoderBackend(mode = 'auto', { readBinary = fetchBinary, simdAvailable = supportsSimd() } = {}) {
  if (!['auto', 'scalar', 'simd'].includes(mode)) throw new Error('Неизвестный режим кодирования.');
  if (mode === 'simd' && !simdAvailable) throw new Error('SIMD недоступен в этом браузере. Выберите «Обычное».');
  const backend = mode === 'auto' ? (simdAvailable ? 'simd' : 'scalar') : mode;
  try {
    return { encode: await createEncoder(await readBinary(backend)), backend };
  } catch (error) {
    // Only Auto falls back on a loading/instantiation failure. Encoding/model
    // errors remain visible and never trigger a silent retry with another mode.
    if (mode !== 'auto' || backend !== 'simd') throw error;
    return { encode: await createEncoder(await readBinary('scalar')), backend: 'scalar' };
  }
}
