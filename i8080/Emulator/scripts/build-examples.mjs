import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
const root = new URL('../', import.meta.url);
const definitions = [
  { id: 'voice32', title: 'Голос · «С воздушным шаром…» · 42,68 кГц', rom: '../Sound/voice-pwm82/dualcrc-voice-pwm82.bin',
    description: 'Исходный голос нормализован на весь диапазон 0–15 без обрезания пиков и пересчитан на 21,34 кГц без изменения темпа. Ровно два одинаковых импульса на отсчёт, все периоды речи — 82 T. Диагностика, Dual CRC и плавный старт.',
    meta: '32 КиБ · PWM 42,68 кГц · звук 21,34 кГц', source: '../Sound/voice-pwm82/README.md' },
  { id: 'owl32', title: 'Голос · «Сова, открывай!» · без диагностики', rom: '../Sound/voice-pwm82/owl/owl-voice-pwm82.bin',
    description: '«Сова! Открывай! Медведь пришёл!» Исходник нормализован на весь диапазон 0–15 без обрезания пиков. Звук 21,34 кГц, ровный PWM 42,68 кГц, ровно два одинаковых импульса на отсчёт. Без стартовых проверок и гудков.',
    meta: '32 КиБ · PWM 42,68 кГц · без стартовой диагностики', source: '../Sound/voice-pwm82/README.md' },
  { id: 'uniform26-fluid-pwm99', title: 'Музыка · FluidR3 · фортепиано и гитара', rom: '../Music/fluid-pwm99/uniform26-fluid-pwm99.bin',
    description: 'Фортепиано и нейлоновая гитара FluidR3: волны по 256 точек, отдельные состояния атаки и затухания. Пиковая нормализация на диапазон 0–15. Темп и ноты пересчитаны, ровный PWM 99 T / 35,35 кГц и звук 8,84 кГц.',
    meta: '32 КиБ · 35,35 кГц · 256 точек на волну', source: '../Music/fluid-pwm99/README.md' },
];
const entries = [];
const khz = hz => (hz / 1000).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
for (const definition of definitions) {
  const variants = [];
  for (const hz of [2000000, 2500000, 3500000]) {
    const rom = hz === 3500000 ? definition.rom : definition.rom.replace(/\/([^/]+)$/, `/clocks/${hz}/$1`);
    const bytes = await readFile(new URL(rom, root));
    const music = definition.id === 'uniform26-fluid-pwm99', carrier = hz / (music ? 99 : 82), rate = carrier / (music ? 4 : 2);
    let description = definition.description;
    if (hz !== 3500000) {
      description = music
        ? `Фортепиано и нейлоновая гитара FluidR3: волны по 256 точек, атака и затухание. Темп и ноты пересчитаны для ${String(hz / 1e6).replace('.', ',')} МГц, сохранены исходные банки и нормализация 0–15. Ровный PWM 99 T, звук ${khz(rate)} кГц.`
        : `Исходный голос нормализован на весь диапазон 0–15 без обрезания пиков и пересчитан на ${khz(rate)} кГц с сохранением темпа и высоты. Ровно два одинаковых импульса на отсчёт, все периоды речи — 82 T. ` +
          (definition.id === 'voice32' ? 'Диагностика, Dual CRC, гудки и плавный старт подстроены под частоту процессора.' : 'Без стартовых проверок, гудков и плавного старта.');
    }
    variants.push({ rom, hz, filename: rom.split('/').at(-1).replace(/\.bin$/, hz === 3500000 ? '.bin' : `-${hz / 1e6}MHz.bin`),
      bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex'),
      title: definition.title.replace('42,68 кГц', `${khz(carrier)} кГц`), description,
      meta: `${String(hz / 1e6).replace('.', ',')} МГц · PWM ${khz(carrier)} кГц · звук ${khz(rate)} кГц`,
      carrier_hz: carrier, sample_rate_hz: rate });
  }
  entries.push({ ...definition, ...variants.at(-1), memory: 'rom', output: 'inte', variants });
}
const output = JSON.stringify({ defaultId: 'voice32', entries }, null, 2) + '\n';
const target = new URL('examples.json', root);
if (process.argv.includes('--check')) {
  if ((await readFile(target, 'utf8')).replace(/\r\n/g, '\n') !== output) throw Error('Examples catalog is stale');
  console.log('PASS: examples metadata matches ROMs');
} else { await writeFile(target, output); console.log('Wrote examples.json'); }
