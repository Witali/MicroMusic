"""Bounded exact-PCM ASM comparison of frozen pitch-root table controls."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', required=True)
    parser.add_argument('--wb-corpus', required=True, type=Path)
    parser.add_argument('--nb-corpus', required=True, type=Path)
    args = parser.parse_args()
    source = ROOT / 'source'
    rows = []
    for profile, wideband, width, corpus in [('wb395', True, 10, args.wb_corpus),
                                            ('nb215-min', False, 6, args.nb_corpus)]:
        for name in ['coverage4096', 'en_letter_a', 'ru_slutskaya_a']:
            row = dict(profile=profile, stream=name, frames=128,
                       provenance='Existing retained independent compact-QMF corpus' if wideband else
                       'Existing retained independent low-rate NB corpus')
            for folder, extension, frame_bytes, key in [('streams', '.spxraw', width, 'input'),
                                                       ('oracle', '.pcm', 640 if wideband else 320, 'pcm')]:
                data = (corpus / folder / (name + extension)).read_bytes()
                selected = data[:128 * frame_bytes]
                assert len(selected) == 128 * frame_bytes
                destination = ROOT / 'data' / profile / folder / (name + extension)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(selected)
                row[key + 'Sha256'] = sha(selected)
                row['source' + key.title() + 'Sha256'] = sha(data)
            raw = (ROOT / 'data' / profile / 'streams' / (name + '.spxraw')).read_bytes()
            codes = [((int.from_bytes(raw[i:i+width], 'big') >> (width*8-34)) & 15) for i in range(0, len(raw), width)]
            row['positiveGainFrames'] = sum(code >= 4 for code in codes)
            rows.append(row)
    (ROOT / 'data.json').write_text(json.dumps(dict(streams=rows), indent=2) + '\n', encoding='utf-8')

    for wideband, filename in [(True, 'verify_wb.mjs'), (False, 'verify_avr.mjs')]:
        text = (source / 'tests' / filename).read_text()
        old = ("import {CPU,avrInstruction} from 'avr8js';" if wideband else
               "import {CPU, avrInstruction} from 'avr8js';")
        assert text.count(old) == 1
        text = text.replace(old, "import {createRequire} from 'node:module';\n"
                            "const require=createRequire(process.env.AVR8JS_PACKAGE);\n"
                            "const {CPU,avrInstruction}=require('avr8js');")
        if wideband:
            anchor = "assert.equal(metadata.backend,backend);"
            text = text.replace(anchor, anchor + "assert.equal(backend,'asm','C decoder execution is forbidden');")
        else:
            anchor = "const packetBytes=backend.packetBytes||20;"
            text = text.replace(anchor, "assert.equal(backend.backend,'asm','C decoder execution is forbidden');\n" + anchor)
        (ROOT / filename).write_text(text, encoding='utf-8')
    results = []
    for table in [0, 1]:
        for profile, wideband in [('wb395', True), ('nb215-min', False)]:
            destination = ROOT / ('table' + str(table)) / profile
            corpus = ROOT / 'data' / profile
            command = [args.node, ROOT / ('verify_wb.mjs' if wideband else 'verify_avr.mjs'),
                       '--backend', 'asm', '--firmware', destination, '--streams', corpus / 'streams',
                       '--oracle', corpus / 'oracle', '--packet-timing']
            if not wideband:
                command.append('--verify-reset')
            with (destination / 'screen.log').open('w', encoding='utf-8') as log:
                subprocess.run(list(map(str, command)), stdout=log, stderr=subprocess.STDOUT, check=True)
            report = json.loads((destination / ('verification.json' if wideband else 'avr-verification.json')).read_text())
            trace = json.loads((destination / 'packet-timing.json').read_text())
            assert report['backend'] == 'asm' and not report['includesInterrupts']
            assert report['frames'] == trace['frames'] == 384
            total = sum(sum(row['cycles']) for row in trace['streams'])
            row = dict(profile=profile, tableEnabled=bool(table), frames=384,
                       binarySha256=report['binarySha256'], flashBytes=report['flashBytes'],
                       staticSramBytes=report['staticSramBytes'], totalFrameCycles=total,
                       meanFrameCycles=total / 384, maxFrameCycles=report['maxCycles'],
                       peakStackBytes=report.get('peakStack', 2303-report.get('minStackPointer', 2303)),
                       pcmExact=True, resetExact=True, includesInterrupts=False)
            results.append(row)
            print('PASS', json.dumps(row), flush=True)
    (ROOT / 'screen.json').write_text(json.dumps(dict(
        scope='384-frame-per-image bounded ASM PCM/reset/timing comparison; interrupts excluded',
        rows=results), indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
