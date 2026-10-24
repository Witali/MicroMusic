"""Build the two-output Lumiere firmware without changing the mono release."""
from pathlib import Path
import hashlib
import json
import re

from importlib.util import spec_from_file_location, module_from_spec

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'ATtiny13A/Music/variants/lumiere-stereo'


def module(name, path):
    spec = spec_from_file_location(name, ROOT / path)
    result = module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def compile_score(data):
    compiler = module('score_format', 'tools/score-format.py')
    return compiler.to_inc({**data, 'packing_candidates': 4096})


def build():
    common = module('build_rhythmic', 'tools/build-rhythmic.py')
    assembler = module('assembler', 'tools/assemble-avr.py')
    data = json.loads((FOLDER / 'score.json').read_text(encoding='utf-8'))
    if data.get('engine')=='lumiere-chords':
        return module('lumiere_chords','tools/build-lumiere-full.py').build(FOLDER,stereo=True)
    # These gains are implemented by the two accumulators in synth.S.
    # Reject metadata-only edits instead of claiming an inaudible pan change.
    gains = {name: (data['panorama'][name]['left'], data['panorama'][name]['right'])
             for name in ('lead', 'keys', 'pluck', 'drums')}
    assert gains == dict(lead=(1, .5), keys=(1, 1), pluck=(.5, 1), drums=(1, 1)), 'Update synth.S and its panning tests when changing the mix'
    score, meta = compile_score(data)
    step = round(data['tempo_bpm'] * 4 / 60 / (37500 / 512) * 65536)
    initial = -(-(65536 - step) // 256)
    settings = dict(REST_INDEX=meta['rest_index'], HOLD_INDEX=meta['hold_index'],
                    PLAYLIST_LEN=len(meta['playlist']), GRID_STEP_LOW=step & 255,
                    GRID_STEP_HIGH=step >> 8, GRID_INITIAL_HIGH=initial)
    (FOLDER / 'config.inc').write_text(''.join(f'.set {k}, {v}\n' for k, v in settings.items()), encoding='utf-8', newline='\n')
    (FOLDER / 'score.inc').write_text(score, encoding='utf-8', newline='\n')
    rom, labels = assembler.assemble(FOLDER / 'synth.S')
    assert len(rom) <= 1024, f'{len(rom)} bytes exceeds ATtiny13A Flash'
    ep = (FOLDER / 'eeprom.bin').read_bytes()
    (FOLDER / 'synth.bin').write_bytes(rom)
    for name, raw in [('synth', rom), ('eeprom', ep)]:
        (FOLDER / (name + '.hex')).write_text(common.ihex(raw), encoding='utf-8', newline='\n')
    report = dict(flashBytes=len(rom), codeBytes=labels['playlist'], tableBytes=len(rom) - labels['playlist'],
                  eepromBytes=len(ep), flashSha256=hashlib.sha256(rom).hexdigest(),
                  eepromSha256=hashlib.sha256(ep).hexdigest(), labels=labels, score=meta,
                  audioChannels=2, outputs=data['outputs'], panorama=data['panorama'],
                  timing=dict(phaseStep=step, phaseBits=16, envelopeTickCycles=131072,
                              tempoBpm=data['tempo_bpm'], actualTempoBpm=step / 65536 * (37500 / 512) * 60 / 4,
                              synthesisHz=18750, pwmHz=37500))
    (FOLDER / 'build-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    core = (ROOT / 'web-player/lib/avr-reference.js').read_text(encoding='utf-8').replace('export class AVRCore', 'class AVRCore')
    core += "\nif(typeof module!=='undefined' && module.exports)module.exports={AVRCore};\n"
    (FOLDER / 'avr_core.js').write_text(core, encoding='utf-8', newline='\n')
    html = (ROOT / 'tools/stereo-player-template.html').read_text(encoding='utf-8')
    for key, value in [('AVR_CORE', core), ('FIRMWARE_HEX', common.ihex(rom)), ('EEPROM_HEX', common.ihex(ep)),
                       ('HEX_PARSER', (ROOT / 'web-player/lib/hex.js').read_text(encoding='utf-8').replace('export function', 'function')),
                       ('RENDERER', '\n'.join(line for line in (ROOT / 'web-player/lib/renderer-js.js').read_text(encoding='utf-8').splitlines() if not line.startswith('import ')).replace('export class', 'class'))]:
        html = html.replace('/*' + key + '*/', value)
    (FOLDER / 'player.html').write_text(html, encoding='utf-8', newline='\n')
    print(f'Stereo: {len(rom)} Flash; {labels["playlist"]} code; {meta["total_data_bytes"]} tables')


if __name__ == '__main__':
    build()
