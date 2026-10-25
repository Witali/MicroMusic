import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
const root = new URL('../', import.meta.url);
const definitions = [
  { id: 'voice32', title: 'Голос · «С воздушным шаром…» · 32,11 кГц', rom: '../Sound/voice32/dualcrc-voice32.bin',
    description: 'Исходный голос нормализован на весь диапазон 0–15 без обрезания пиков и пересчитан на 16,06 кГц без изменения темпа. Два импульса на отсчёт, все периоды речи — 109 T. Диагностика, Dual CRC и плавный старт.',
    meta: '32 КиБ · PWM 32,11 кГц · звук 16,06 кГц', source: '../Sound/voice32/README.md' },
  { id: 'owl32', title: 'Голос · «Сова, открывай!» · без диагностики', rom: '../Sound/voice32/owl/owl-voice32.bin',
    description: '«Сова! Открывай! Медведь пришёл!» Исходник нормализован на весь диапазон 0–15 без обрезания пиков. Звук 16,06 кГц, ровный PWM 32,11 кГц. Без стартовых проверок и гудков.',
    meta: '32 КиБ · PWM 32,11 кГц · без стартовой диагностики', source: '../Sound/voice32/owl/README.md' },
  { id: 'uniform26-pwm108', title: 'Музыка · UNIFORM26 · ровный PWM', rom: '../Music/uniform-pwm/uniform26-pwm108.bin',
    description: 'Постоянная несущая 32,41 кГц, 16 линейных уровней. Темп и высота нот сохранены пересчётом шагов синтеза. Все периоды, включая переходы между нотами, равны 108 T.',
    meta: '32 КиБ · 32,41 кГц · 16 уровней', source: '../Music/uniform-pwm/README.md' },
];
const entries = [];
for (const definition of definitions) {
  const bytes = await readFile(new URL(definition.rom, root));
  entries.push({ ...definition, filename: definition.rom.split('/').at(-1), bytes: bytes.length,
    sha256: createHash('sha256').update(bytes).digest('hex'), hz: 3500000, memory: 'rom', output: 'inte' });
}
const output = JSON.stringify({ defaultId: 'voice32', entries }, null, 2) + '\n';
const target = new URL('examples.json', root);
if (process.argv.includes('--check')) {
  if ((await readFile(target, 'utf8')).replace(/\r\n/g, '\n') !== output) throw Error('Examples catalog is stale');
  console.log('PASS: examples metadata matches ROMs');
} else { await writeFile(target, output); console.log('Wrote examples.json'); }
