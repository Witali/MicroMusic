import { createEncoderBackend } from './encoder-backend.js?v=20261123-adaptive-quality';
self.onmessage = async ({ data }) => {
  try {
    const { encode, backend } = await createEncoderBackend(data.backend ?? 'auto');
    const pcm = new Int16Array(data.pcm);
    const started = performance.now();
    const bytes = encode(pcm, data.sampleRate, data.profile, progress => self.postMessage({ progress }),
      { sizeAllowancePercent: data.sizeAllowancePercent ?? 0 });
    const elapsedMs = performance.now() - started;
    self.postMessage({ result: { bytes, samples: pcm.length, long: !!(bytes[2] & 64), backend, elapsedMs } }, [bytes.buffer]);
  } catch (error) { self.postMessage({ error: error.message || 'Ошибка кодирования LPX.' }); }
};
