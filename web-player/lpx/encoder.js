import { MAX_SAMPLES } from './codec.js?v=20261124-stream-quality';
import { createStreamSession } from './streaming.js?v=20261124-stream-quality';
import { encodingPolicy, bitrateBudget } from './encoding-policy.js?v=20261124-stream-quality';

export async function createEncoder(binary) {
  const { instance } = await WebAssembly.instantiate(binary);
  const api = instance.exports;
  // Standalone C++ modules initialize their static containers exactly once.
  api.__wasm_call_ctors?.();
  const loudnessReport = () => ({
    status: api.enc_loudness_status(), limited: !!api.enc_loudness_limited(), gainLimited: !!api.enc_loudness_gain_limited(),
    input: api.enc_loudness_input(), prepared: api.enc_loudness_prepared(),
    decoded: api.enc_loudness_decoded(), gainDb: api.enc_loudness_gain_db()
  });
  const encode = (pcm, sampleRate, profile, progress = () => {}, options = {}) => {
    encode.loudness = null;
    if (!(pcm instanceof Int16Array) || !pcm.length || pcm.length > MAX_SAMPLES) throw new Error('Запись должна содержать от 1 до 32 000 000 отсчётов.');
    if (![8000, 12000, 16000].includes(sampleRate) || ![3, 4, 6, 8].includes(profile)) throw new Error('Некорректные параметры кодирования.');
    const allowance = options.sizeAllowancePercent ?? 0;
    if (!Number.isInteger(allowance) || allowance < 0 || allowance > 100) throw new Error('Некорректное ограничение размера.');
    const accuracy=options.accuracy===true;
    const policy = encodingPolicy(profile, accuracy);
    const bitratePreset = policy.targetBitrate !== 0;
    if(accuracy&&(!api.enc_accuracy||allowance!==0))throw Error('Уровни точности требуют актуального энкодера и не используют допуск размера.');
    if (bitratePreset && (sampleRate !== 8000 || allowance !== 0)) throw new Error('Профили 3 и 8 кбит/с используют 8 кГц и точный предел размера без допуска.');
    if (bitratePreset && !api.enc_bitrate) throw new Error('Обновите страницу: этот кодировщик не поддерживает профили 3 и 8 кбит/с.');
    const normalization = options.normalization ?? 'preserve';
    if (!['preserve', 'loudness'].includes(normalization)) throw new Error('Неизвестный режим громкости.');
    const targetLufs = options.targetLufs ?? -18, maxGainDb = options.maxGainDb ?? 12;
    if (normalization === 'loudness' && (!Number.isInteger(targetLufs) || targetLufs < -30 || targetLufs > -9 || !Number.isInteger(maxGainDb) || maxGainDb < 0 || maxGainDb > 24)) throw new Error('Некорректные настройки нормализации.');
    if (normalization === 'loudness' && !(bitratePreset ? api.enc_bitrate_level : api.enc_adaptive_level)) throw new Error('Обновите страницу: этот энкодер не поддерживает настройки нормализации.');
    if (!api.enc_reserve(pcm.length)) throw new Error('Недостаточно памяти для кодирования этой записи.');
    new Int16Array(api.memory.buffer, api.enc_input(), pcm.length).set(pcm);
    if(accuracy){
      progress(0);const size=api.enc_accuracy(pcm.length,profile,sampleRate,options.calls??4,normalization==='loudness'?1:0,targetLufs,maxGainDb);
      if(size<13)throw Error(`Энкодер уровня точности не прошёл проверку (${size}).`);
      const bytes=new Uint8Array(api.memory.buffer,api.enc_adaptive_output(),size).slice();
      if(normalization==='loudness')encode.loudness=loudnessReport();progress(1);return bytes;
    }
    if (bitratePreset) {
      progress(0);
      const size = normalization === 'loudness'
        ? api.enc_bitrate_level(pcm.length, profile, sampleRate, 4, targetLufs, maxGainDb)
        : api.enc_bitrate(pcm.length, profile, sampleRate, 0, 4);
      if (size < 13) throw new Error(`Не удалось уложить полный поток в ${profile} кбит/с (${size}).`);
      const cap = bitrateBudget(pcm.length, policy, sampleRate);
      if (size > cap) throw new Error('Кодировщик превысил предел размера полного файла.');
      const bytes = new Uint8Array(api.memory.buffer, api.enc_adaptive_output(), size).slice();
      if (normalization === 'loudness') encode.loudness = loudnessReport();
      progress(1);
      return bytes;
    }
    if (api.enc_adaptive) {
      progress(0);
      const size = normalization === 'loudness'
        ? api.enc_adaptive_level(pcm.length, profile, sampleRate, 0, 4, allowance, options.extendedSearch !== false ? 1 : 0, targetLufs, maxGainDb)
        : options.extendedSearch !== false && api.enc_adaptive_extended
        ? api.enc_adaptive_extended(pcm.length, profile, sampleRate, 0, 0, 4, allowance)
        : api.enc_adaptive(pcm.length, profile, sampleRate, 0, 0, 4);
      if (size < 13) throw new Error(`Адаптивный энкодер не прошёл проверку полного потока (${size}).`);
      // Memory can grow during the search. Construct the view only after it ends.
      const bytes = new Uint8Array(api.memory.buffer, api.enc_adaptive_output(), size).slice();
      if (normalization === 'loudness') encode.loudness = loudnessReport();
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
  encode.createStream=settings=>createStreamSession(api,settings);
  return encode;
}
