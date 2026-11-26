// Per-encode/session host policy; the LPX wire format and decoder do not change.
export function qualityTargetCode(value = 'pwm') {
  if (value === 'pcm') return 0;
  if (value === 'pwm') return 1;
  throw new Error('Неизвестный выход кодирования. Выберите PCM или AVR PWM.');
}
export function callQualityEncoder(api, name, args, target) {
  const explicit = api[`${name}_target`];
  if (typeof explicit === 'function') return explicit(...args, target);
  if (target === 0) throw new Error('Обновите страницу: этот WASM-энкодер не поддерживает выбор выхода PCM.');
  if (typeof api[name] !== 'function') throw new Error('Обновите страницу: выбранный энкодер недоступен.');
  return api[name](...args);
}
