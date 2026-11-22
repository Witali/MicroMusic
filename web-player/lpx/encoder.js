import { MAX_SAMPLES } from './codec.js';

export async function createEncoder(binary) {
  const { instance } = await WebAssembly.instantiate(binary);
  const api = instance.exports;
  return (pcm, sampleRate, profile, progress = () => {}) => {
    if (!(pcm instanceof Int16Array) || !pcm.length || pcm.length > MAX_SAMPLES) throw new Error('Запись должна содержать от 1 до 32 000 000 отсчётов.');
    if (!api.enc_reserve(pcm.length)) throw new Error('Недостаточно памяти для кодирования этой записи.');
    new Int16Array(api.memory.buffer, api.enc_input(), pcm.length).set(pcm);
    const blocks = api.enc_begin(pcm.length, profile, sampleRate);
    if (blocks < 1) throw new Error('Некорректные параметры кодирования.');
    for (let i = 0; i < blocks; i++) {
      api.enc_step();
      if (i % 8 === 0 || i === blocks - 1) progress((i + 1) / blocks);
    }
    const size = api.enc_finish();
    if (size < 13) throw new Error(`Энкодер не прошёл внутреннюю проверку C-декодером (${size}).`);
    return new Uint8Array(api.memory.buffer, api.enc_output(), size).slice();
  };
}
