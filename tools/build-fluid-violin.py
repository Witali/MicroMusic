"""Build the FluidR3 violin adaptation from retained measurements (NumPy)."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'ATtiny13A/Music/final/attiny13a_synth_release'
OUT = ROOT / 'ATtiny13A/Music/variants/fluid-violin'
hash_bytes = lambda b: hashlib.sha256(b).hexdigest()


def ihex(raw):
    rows = []
    for start in range(0, len(raw), 16):
        b = bytes([len(raw[start:start + 16]), start >> 8, start & 255, 0]) + raw[start:start + 16]
        rows.append(':' + (b + bytes([-sum(b) & 255])).hex().upper())
    return '\n'.join(rows + [':00000001FF', ''])


def spectrum(q):
    # The AVR holds each of the 16 values; include its zero-order-hold response.
    amp = abs(np.fft.rfft(q))[1:8] * np.sinc(np.arange(1, 8) / 16)
    return amp / np.linalg.norm(amp)


def quantize(values):
    q = np.clip(np.rint(values), -8, 7).astype(int)
    while q.sum():
        direction = -1 if q.sum() > 0 else 1
        allowed = np.flatnonzero((q > -8) if direction < 0 else (q < 7))
        loss = (q[allowed] + direction - values[allowed]) ** 2 - (q[allowed] - values[allowed]) ** 2
        q[allowed[np.argmin(loss)]] += direction
    return q


def fit(measurements, midi_notes, baseline):
    frames = [frame for note in measurements['notes'] if note['midi'] in midi_notes for frame in note['frames']]
    features = np.array([f['amplitudes'][:7] for f in frames])
    features /= np.linalg.norm(features, axis=1)[:, None]
    target = np.median(features, axis=0)
    target /= np.linalg.norm(target)
    reference = frames[int(np.argmin(np.sum((features - target) ** 2, axis=1)))]
    phase = np.array(reference['relativePhases'][:7])
    goal_rms = float(np.sqrt(np.mean(np.array(baseline, dtype=float) ** 2)) * .90)

    def loss(q):
        rms = np.sqrt(np.mean(q.astype(float) ** 2))
        if rms < 1: return 100.
        spectral = np.sum((spectrum(q) - target) ** 2)
        roughness = np.mean(np.diff(np.r_[q, q[0]]) ** 2) / rms ** 2
        return float(5 * spectral + .25 * (rms / goal_rms - 1) ** 2 + .002 * roughness + .0005 * q[0] ** 2)

    best, minimum = None, float('inf')
    for shift in np.linspace(0, 2 * np.pi, 64, endpoint=False):
        t = np.arange(16) * 2 * np.pi / 16 + shift
        wave = np.sum(target[:, None] / np.sinc(np.arange(1, 8) / 16)[:, None] *
                      np.cos(np.arange(1, 8)[:, None] * t + phase[:, None]), axis=0)
        wave -= wave.mean()
        for peak in [5., 5.5, 6., 6.5, 7.]:
            q = quantize(wave * peak / max(abs(wave)))
            candidate = loss(q)
            if candidate < minimum: minimum, best = candidate, q
    # Zero-DC pair moves refine the quantized, very small EEPROM table.
    for _ in range(32):
        candidate, score = best, minimum
        for up in range(16):
            if best[up] >= 7: continue
            for down in range(16):
                if up == down or best[down] <= -8: continue
                q = best.copy(); q[up] += 1; q[down] -= 1
                value = loss(q)
                if value < score - 1e-12: candidate, score = q, value
        if score >= minimum - 1e-12: break
        best, minimum = candidate, score
    # Choose a zero-crossing start; cyclic rotation retains the fitted spectrum.
    start = min(range(16), key=lambda i: (abs(int(best[i])), abs(int(best[(i + 1) % 16] - best[i]))))
    best = np.roll(best, -start)
    return best.tolist(), dict(referenceMidi=midi_notes, targetHarmonics=target.tolist(),
        fittedHarmonics=spectrum(best).tolist(), originalHarmonics=spectrum(baseline).tolist(),
        originalSpectralDistance=float(np.linalg.norm(spectrum(baseline) - target)),
        fittedSpectralDistance=float(np.linalg.norm(spectrum(best) - target)),
        originalRms=float(np.sqrt(np.mean(np.array(baseline, dtype=float) ** 2))),
        fittedRms=float(np.sqrt(np.mean(best.astype(float) ** 2))),
        phaseReferenceAgeSeconds=reference['ageSeconds'])


def encode(instruction, pc, labels):
    op, *args = instruction.replace(',', ' ').split()
    reg = lambda s: int(s[1:])
    if op == 'nop': return 0
    if op in ('mov', 'add'):
        d, r = map(reg, args)
        return (0x2c00 if op == 'mov' else 0x0c00) | d << 4 | (r & 15) | (r & 16) << 5
    if op in ('ldi', 'andi', 'cpi', 'ori'):
        d, k = reg(args[0]), int(args[1])
        return {'ldi': 0xe000, 'andi': 0x7000, 'cpi': 0x3000, 'ori': 0x6000}[op] | (d - 16) << 4 | (k & 15) | (k & 240) << 4
    if op == 'clr':
        d = reg(args[0]); return 0x2400 | d << 4 | (d & 15) | (d & 16) << 5
    if op == 'sbrc': return 0xfc00 | reg(args[0]) << 4 | int(args[1])
    if op == 'inc': return 0x9403 | reg(args[0]) << 4
    if op in ('rjmp', 'breq', 'brcc'):
        k = (labels[args[0]] - pc - 2) // 2
        if op == 'rjmp': return 0xc000 | (k & 4095)
        assert -64 <= k <= 63
        return (0xf001 if op == 'breq' else 0xf400) | (k & 127) << 3
    raise ValueError(instruction)


def assemble_changed_words(original, updated, original_rom):
    # All code in the preserved source consists of one-word instructions.
    # No relocation or data address moves. Verify changed original words and
    # encode only the reviewed one-word subset above.
    def instructions(source):
        clean = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
        rows, labels, pc = {}, {}, 0
        for line in clean.splitlines():
            line = line.strip()
            if not line or line.startswith('.'): continue
            if line.endswith(':'): labels[line[:-1]] = pc
            else: rows[pc] = line; pc += 2
        # Dot-prefixed local labels need to be recorded as well.
        pc = 0
        for line in clean.splitlines():
            line = line.strip()
            if line.endswith(':'): labels[line[:-1]] = pc
            elif line and not line.startswith('.'): pc += 2
        return rows, labels
    old, old_labels = instructions(original)
    new, new_labels = instructions(updated)
    assert len(old) == len(new) and old_labels == new_labels, 'Instruction or label addresses changed'
    rom, patches = bytearray(original_rom), []
    for pc, instruction in new.items():
        if instruction == old[pc]: continue
        previous = encode(old[pc], pc, old_labels)
        assert int.from_bytes(rom[pc:pc + 2], 'little') == previous, (pc, old[pc])
        value = encode(instruction, pc, new_labels)
        rom[pc:pc + 2] = value.to_bytes(2, 'little')
        patches.append(dict(address=pc, previous=old[pc], updated=instruction, oldWord=f'{previous:04X}', newWord=f'{value:04X}'))
    return bytes(rom), patches


def main():
    measurements = json.loads((OUT / 'measurements.json').read_text(encoding='utf-8'))
    assert measurements['capture']['soundfont']['sha256'] == '74594e8f4250680adf590507a306655a299935343583256f3b722c48a1bc1cb0'
    old_ep = (BASE / 'eeprom.bin').read_bytes()
    names = list(json.loads((BASE / 'waveforms.json').read_text(encoding='utf-8')))
    waves = {name: [v for b in old_ep[i * 8:i * 8 + 8] for v in [(b & 15) - 8, (b >> 4) - 8]] for i, name in enumerate(names)}
    metrics = {}
    for name, notes in [('violin_low', [52, 55]), ('violin_high', [62, 69, 74])]:
        waves[name], metrics[name] = fit(measurements, notes, waves[name])
    ep = bytes((values[i] + 8) | ((values[i + 1] + 8) << 4) for values in waves.values() for i in range(0, 16, 2))
    assert ep[16:] == old_ep[16:] and len(ep) == 64
    original = (BASE / 'synth.S').read_text(encoding='utf-8')
    old_attack = '''  mov r16, r1
  andi r16, 15
  cpi r16, 13
  brcc .L07e
  ldi r16, 3
  add r1, r16
  rjmp .L08e
.L07e:
  ldi r16, 143
  mov r1, r16
  rjmp .L08e'''
    new_attack = '''  mov r16, r1
  cpi r16, 143
  breq .L08e
  mov r16, r24
  andi r16, 3
  breq .L08e
  inc r1
.L07e:
  rjmp .L08e
  nop
  nop'''
    old_note = '  clr r3\n  ldi r16, 130\n  mov r1, r16'
    new_note = '  mov r16, r1\n  ori r16, 128\n  mov r1, r16'
    old_release = '  dec r1\n  breq .L08e\n  dec r1'
    new_release = '  dec r1\n  sbrc r1, 3\n  dec r1'
    assert original.count(old_attack) == original.count(old_note) == original.count(old_release) == 1
    updated = original.replace(old_attack, new_attack).replace(old_note, new_note).replace(old_release, new_release)
    updated = updated.replace(' * ATtiny13A release binary; running build.py reassembles and byte-compares it.',
        ' * ATtiny13A release binary; tools/build-fluid-violin.py builds this revision.')
    updated = updated.replace(' * All addresses, and every opcode, are retained. A general purpose source',
        ' * All addresses are retained; the lead envelope opcodes are changed. A source')
    rom, patches = assemble_changed_words(original, updated, (BASE / 'synth.bin').read_bytes())
    assert len(rom) == 1024
    (OUT / 'synth.S').write_text('/* FluidR3: slow attack, continuous level/phase on legato, tapered release. */\n' + updated, encoding='utf-8', newline='\n')
    for filename, content in [('synth.bin', rom), ('eeprom.bin', ep)]: (OUT / filename).write_bytes(content)
    for filename, content in [('synth.hex', ihex(rom)), ('eeprom.hex', ihex(ep))]: (OUT / filename).write_text(content, encoding='utf-8', newline='\n')
    (OUT / 'waveforms.json').write_text(json.dumps(waves, indent=2) + '\n', encoding='utf-8', newline='\n')
    for name in ['config.inc', 'score.inc', 'score.json']: shutil.copyfile(BASE / name, OUT / name)
    html = (BASE / 'player_template.html').read_text(encoding='utf-8').replace('/*AVR_CORE*/', (BASE / 'avr_core.js').read_text(encoding='utf-8')).replace('/*FIRMWARE_HEX*/', ihex(rom)).replace('/*EEPROM_HEX*/', ihex(ep))
    html = html.replace('ATtiny13A — проигрыватель AVR-прошивки', 'ATtiny13A — скрипка FluidR3')
    (OUT / 'player.html').write_text(html, encoding='utf-8', newline='\n')
    report = dict(flashBytes=len(rom), eepromBytes=len(ep), flashSha256=hash_bytes(rom), eepromSha256=hash_bytes(ep),
        baselineFlashSha256=hash_bytes((BASE / 'synth.bin').read_bytes()), baselineEepromSha256=hash_bytes(old_ep),
        unchangedAccompanimentEepromRange='0x10..0x3F', packing='AVR phase order: even index in low nibble, odd index in high nibble; +8 offset',
        source='FluidR3 GM 3.1 / GM program 40 Violin / velocity 100', waveFit=metrics,
        attack=dict(startLevel=0, maximum=15, increment=1, gate='music tick modulo 4 != 0', maximumRiseMs=15 * 4 / 3 * 512 / 37500 * 1000),
        legato='Keep the current envelope level and full DDS phase on note-on; restart attack from current level.',
        release=dict(levelsAfterTicks=[13, 11, 9, 7, 6, 5, 4, 3, 2, 1, 0], maximumDurationMs=11 * 512 / 37500 * 1000),
        sourceAssembly='Source-only one-word replacements with original opcode assertions. Same code/data addresses; no toolchain required to rebuild these reviewed words.', patches=patches)
    (OUT / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    for name, data in metrics.items(): print(name, 'spectral distance', round(data['originalSpectralDistance'], 4), '->', round(data['fittedSpectralDistance'], 4), waves[name])
    print('Flash', len(rom), 'EEPROM', len(ep), 'reviewed instruction changes', len(patches))


if __name__ == '__main__': main()
