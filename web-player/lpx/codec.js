export const MAX_SAMPLES = 32000000;
export const MAX_FILE_BYTES = 100 * 1024 * 1024;

export function parseHeader(buffer) {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  if (bytes.length < 13 || bytes.length > MAX_FILE_BYTES) throw new Error('Выберите LPX V9 размером от 13 байт до 100 МБ.');
  if (bytes[0] !== 0x4c || bytes[1] !== 0x39) throw new Error('Это не LPX V9: ожидается сигнатура L9. Старые версии LPX не поддерживаются.');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const long = !!(bytes[2] & 64), hasGain = !!(bytes[2] & 32), baseHeader = long ? 17 : 13;
  const headerBytes = baseHeader + (hasGain ? 2 : 0);
  if (bytes.length < headerBytes || (!long && bytes.length > 65535)) throw new Error('Некорректный размер заголовка или файла LPX V9.');
  const profile = bytes[2] & 31;
  if (![4, 6, 15].includes(profile) || (profile === 15 && (bytes[2] & 128))) throw new Error('Неподдерживаемый профиль LPX V9.');
  const sampleRate = view.getUint16(3, true), samples = long ? view.getUint32(5, true) : view.getUint16(5, true);
  const pre = view.getUint16(long ? 9 : 7, true), brightness = view.getUint16(long ? 11 : 9, true);
  if (![8000, 12000, 16000].includes(sampleRate)) throw new Error('Поддерживаются частоты 8, 12 и 16 кГц.');
  if (!samples || (!long && samples > 64000) || pre > 16384 || brightness > 11469) throw new Error('Некорректные параметры заголовка LPX V9.');
  if (samples > MAX_SAMPLES) throw new Error('Для этого браузерного плеера предел — 32 000 000 отсчётов на файл.');
  if ((long ? view.getUint32(13, true) : view.getUint16(11, true)) !== bytes.length - headerBytes) throw new Error('Размер данных не совпадает с заголовком: файл повреждён или обрезан.');
  const gainQ12 = hasGain ? view.getUint16(baseHeader, true) : 4096;
  if (!gainQ12) throw new Error('Некорректный коэффициент громкости LPX.');
  return { profile, long, hasGain, gainQ12, gainDb: 20 * Math.log10(gainQ12 / 4096), format: (long ? 'LPX V9 Long' : 'LPX V9') + (hasGain ? ' + gain' : ''), extraPulses: !!(bytes[2] & 128), sampleRate, samples, bytes: bytes.length,
    duration: samples / sampleRate, bitrate: bytes.length * 8 * sampleRate / samples };
}

export async function createDecoder(binary) {
  const { instance } = await WebAssembly.instantiate(binary);
  const api = instance.exports;
  return buffer => {
    const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
    const metadata = parseHeader(bytes);
    if (!api.lpx_reserve(bytes.length, metadata.samples)) throw new Error('Недостаточно памяти для декодирования этой записи.');
    new Uint8Array(api.memory.buffer, api.lpx_input(), bytes.length).set(bytes);
    if (api.lpx_decode(bytes.length) !== 0) throw new Error('Повреждён поток LPX: декодер отклонил данные или окончание файла.');
    if (api.lpx_samples() !== metadata.samples || api.lpx_rate() !== metadata.sampleRate) throw new Error('Декодер вернул неверные параметры звука.');
    return { ...metadata, pcm: new Int16Array(api.memory.buffer, api.lpx_output(), metadata.samples).slice() };
  };
}

export function encodeWav(pcm, sampleRate) {
  const buffer = new ArrayBuffer(44 + pcm.length * 2), view = new DataView(buffer);
  const text = (offset, value) => [...value].forEach((char, index) => view.setUint8(offset + index, char.charCodeAt(0)));
  text(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); text(8, 'WAVE'); text(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, 'data');
  view.setUint32(40, pcm.length * 2, true);
  pcm.forEach((value, index) => view.setInt16(44 + index * 2, value, true));
  return buffer;
}
