import { SignalFilter } from './signal.mjs';
// ROM loaders deliberately preserve holes as erased EPROM bytes (FFh).
export function parseIntelHex(text) {
  const image = new Uint8Array(65536).fill(0xff), used = new Uint8Array(65536);
  let base = 0, top = 0, eof = false;
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/);
  for (let lineNumber = 0; lineNumber < lines.length; lineNumber++) {
    const line = lines[lineNumber].trim();
    if (!line) continue;
    const fail = message => { throw Error(`HEX, строка ${lineNumber + 1}: ${message}`); };
    if (eof) fail('данные после EOF');
    if (!/^:(?:[0-9a-f]{2})+$/i.test(line)) fail('неверный формат записи');
    const b = Uint8Array.from(line.slice(1).match(/../g), x => parseInt(x, 16));
    if (b.length < 5 || b.length !== b[0] + 5) fail('неверная длина записи');
    if (b.reduce((sum, x) => sum + x, 0) % 256) fail('ошибка контрольной суммы');
    const size = b[0], address = b[1] * 256 + b[2], type = b[3];
    if (type === 0) {
      if (address + size > 65536 || base + address + size > 65536) fail('адрес вне 64 КиБ');
      for (let i = 0; i < size; i++) {
        const at = base + address + i, value = b[4 + i];
        if (used[at] && image[at] !== value) fail('противоречащие записи по одному адресу');
        used[at] = 1; image[at] = value; top = Math.max(top, at + 1);
      }
    } else if (type === 1) {
      if (size !== 0 || address !== 0) fail('неверная запись EOF');
      eof = true;
    } else if (type === 2 || type === 4) {
      if (size !== 2 || address !== 0) fail('неверная запись расширенного адреса');
      base = (b[4] * 256 + b[5]) * (type === 2 ? 16 : 65536);
    } else if (type === 3 || type === 5) {
      if (size !== 4 || address !== 0) fail('неверная запись начального адреса');
      // These metadata records do not override the 8080 reset vector, PC=0000h.
    } else fail(`неподдерживаемый тип ${type.toString(16).padStart(2, '0')}`);
  }
  if (!eof) throw Error('HEX: отсутствует запись EOF');
  if (!top) throw Error('HEX не содержит машинного кода');
  return image.slice(0, top);
}

export function validateBinary(bytes) {
  if (!(bytes instanceof Uint8Array) || !bytes.length || bytes.length > 65536) {
    throw Error('Размер образа должен быть от 1 до 65 536 байт');
  }
  return bytes;
}

// Cascaded RC poles are an audio reconstruction approximation, not a circuit model.
export function processAudio(raw, rate, cutoff = 4500, poles = 4, normalize = true) {
  if (!Number.isInteger(rate) || rate < 8000 || !Number.isFinite(cutoff) || cutoff < 0 || cutoff >= rate / 2 || !Number.isInteger(poles) || poles < 1 || poles > 8) throw Error('Invalid filter');
  const samples = new Float32Array(raw.length), filter = new SignalFilter(rate, cutoff, poles, normalize);
  for (let i = 0; i < raw.length; i++) {
    if (!Number.isFinite(raw[i])) throw Error('Non-finite audio sample');
    samples[i] = filter.step(raw[i]);
  }
  return samples;
}

export function encodeWav(samples, rate) {
  if (!Number.isInteger(rate) || rate < 8000 || rate > 192000) throw Error('Invalid WAV sample rate');
  const buffer = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buffer);
  const text = (offset, value) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)); };
  text(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); text(8, 'WAVE'); text(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, 'data'); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    if (!Number.isFinite(samples[i])) throw Error('Non-finite WAV sample');
    const sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
  }
  return buffer;
}
