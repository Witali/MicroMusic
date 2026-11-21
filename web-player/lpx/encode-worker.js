import { createEncoder } from './encoder.js';

const ready = fetch(new URL('./encoder.wasm', import.meta.url)).then(response => {
  if (!response.ok) throw new Error('Не удалось загрузить WASM-энкодер.');
  return response.arrayBuffer();
}).then(createEncoder);
ready.catch(() => {});
self.onmessage = async ({ data }) => {
  try {
    const encode = await ready;
    const pcm = new Int16Array(data.pcm);
    const parts = Math.ceil(pcm.length / 64000);
    for (let index = 0; index < parts; index++) {
      const start = index * 64000, segment = pcm.subarray(start, start + 64000);
      const bytes = encode(segment, data.sampleRate, data.profile, fraction => {
        self.postMessage({ progress: (index + fraction) / parts, index, parts });
      });
      self.postMessage({ segment: { bytes, samples: segment.length, index, parts, start } }, [bytes.buffer]);
    }
    self.postMessage({ done: true });
  } catch (error) { self.postMessage({ error: error.message || 'Ошибка кодирования LPX.' }); }
};
