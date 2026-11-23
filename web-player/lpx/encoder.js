import { MAX_SAMPLES } from './codec.js';

export async function createEncoder(binary) {
  const { instance } = await WebAssembly.instantiate(binary);
  const api = instance.exports;
  // Standalone C++ modules initialize their static containers exactly once.
  api.__wasm_call_ctors?.();
  return (pcm, sampleRate, profile, progress = () => {}, options = {}) => {
    if (!(pcm instanceof Int16Array) || !pcm.length || pcm.length > MAX_SAMPLES) throw new Error('Запись должна содержать от 1 до 32 000 000 отсчётов.');
    if (![8000, 12000, 16000].includes(sampleRate) || ![3, 4, 6, 8].includes(profile)) throw new Error('Некорректные параметры кодирования.');
    const allowance = options.sizeAllowancePercent ?? 0;
    if (!Number.isInteger(allowance) || allowance < 0 || allowance > 100) throw new Error('Некорректное ограничение размера.');
    const bitratePreset = profile === 3 || profile === 8;
    if (bitratePreset && (sampleRate !== 8000 || allowance !== 0)) throw new Error('Профили 3 и 8 кбит/с используют 8 кГц и точный предел размера без допуска.');
    if (bitratePreset && !api.enc_bitrate) throw new Error('Обновите страницу: этот кодировщик не поддерживает профили 3 и 8 кбит/с.');
    if (!api.enc_reserve(pcm.length)) throw new Error('Недостаточно памяти для кодирования этой записи.');
    new Int16Array(api.memory.buffer, api.enc_input(), pcm.length).set(pcm);
    if (bitratePreset) {
      progress(0);
      const size = api.enc_bitrate(pcm.length, profile, sampleRate, 0, 4);
      if (size < 13) throw new Error(`Не удалось уложить полный поток в ${profile} кбит/с (${size}).`);
      const cap = Math.floor(pcm.length * profile * 1000 / (8 * sampleRate));
      if (size > cap) throw new Error('Кодировщик превысил предел размера полного файла.');
      const bytes = new Uint8Array(api.memory.buffer, api.enc_adaptive_output(), size).slice();
      progress(1);
      return bytes;
    }
    if (api.enc_adaptive) {
      progress(0);
      const size = options.extendedSearch !== false && api.enc_adaptive_extended
        ? api.enc_adaptive_extended(pcm.length, profile, sampleRate, 0, 0, 4, allowance)
        : api.enc_adaptive(pcm.length, profile, sampleRate, 0, 0, 4);
      if (size < 13) throw new Error(`Адаптивный энкодер не прошёл проверку полного потока (${size}).`);
      // Memory can grow during the search. Construct the view only after it ends.
      const bytes = new Uint8Array(api.memory.buffer, api.enc_adaptive_output(), size).slice();
      progress(1);
      return bytes;
    }
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
