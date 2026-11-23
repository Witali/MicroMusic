import { createDecoder } from './codec.js?v=20261123-quality-v3';

const ready = fetch(new URL('./decoder.wasm?v=20261123-quality-v3', import.meta.url)).then(response => {
  if (!response.ok) throw new Error('Не удалось загрузить WASM-декодер. Обновите страницу.');
  return response.arrayBuffer();
}).then(createDecoder);
// Keep initialization rejection handled until a request arrives.
ready.catch(() => {});
self.onmessage = async ({ data }) => {
  try {
    const decode = await ready;
    const result = decode(data.buffer);
    self.postMessage({ id: data.id, result }, [result.pcm.buffer]);
  } catch (error) {
    self.postMessage({ id: data.id, error: error.message || 'Не удалось прочитать файл LPX.' });
  }
};
