import { createEncoder } from './encoder.js';

const ready = fetch(new URL('./encoder.wasm?v=20261122-analysis-cache', import.meta.url)).then(response => {
  if (!response.ok) throw new Error('Не удалось загрузить WASM-энкодер.');
  return response.arrayBuffer();
}).then(createEncoder);
ready.catch(() => {});
self.onmessage = async ({ data }) => {
  try {
    const encode = await ready;
    const pcm = new Int16Array(data.pcm);
    const bytes = encode(pcm, data.sampleRate, data.profile, progress => self.postMessage({ progress }));
    self.postMessage({ result: { bytes, samples: pcm.length, long: !!(bytes[2] & 64) } }, [bytes.buffer]);
  } catch (error) { self.postMessage({ error: error.message || 'Ошибка кодирования LPX.' }); }
};
