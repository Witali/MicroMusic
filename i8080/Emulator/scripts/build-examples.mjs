import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
const root = new URL('../', import.meta.url);
const definitions = [
  { id: 'voice159', title: 'Голос · ровный PWM 159 T', rom: '../Sound/dual-crc-voice/dualcrc-uniform159.bin',
    description: 'Исходный темп с отклонением всего +0,13%. Постоянный период речи, все 16 уровней и 63 085 отсчётов сохранены. Диагностика, Dual CRC и плавный старт.',
    meta: '32 КиБ · 22,01 кГц · 16 уровней', source: '../Sound/dual-crc-voice/README.md' },
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
const output = JSON.stringify({ defaultId: 'voice159', entries }, null, 2) + '\n';
const target = new URL('examples.json', root);
if (process.argv.includes('--check')) {
  if ((await readFile(target, 'utf8')).replace(/\r\n/g, '\n') !== output) throw Error('Examples catalog is stale');
  console.log('PASS: examples metadata matches ROMs');
} else { await writeFile(target, output); console.log('Wrote examples.json'); }
