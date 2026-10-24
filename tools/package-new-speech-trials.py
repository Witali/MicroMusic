"""Package independently verified private speech trials for listening/programming.

Inputs and generated audio/HEX stay in ignored build/. --retain copies only
compressed parameters and research reports, never original MP3 or WAV files.
"""
import argparse
import hashlib
import html
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

import numpy as np
import soundfile as sf
from scipy.signal import sosfilt
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective
from fixed_period import decode_fixed
from hq4_core import pack_stream
from hq4_speech_search import deterministic_estoi
from model import decode
from tiny_period import pack_tiny


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')


def hex_image(text):
    """Validate Intel HEX checksums/addresses, then reconstruct its byte image."""
    image, upper, finished = {}, 0, False
    for line in text.splitlines():
        if not line.strip():
            continue
        if finished or not line.startswith(':'):
            raise ValueError('Invalid data after HEX EOF or missing record prefix')
        row = bytes.fromhex(line[1:])
        if len(row) < 5 or len(row) != row[0]+5 or sum(row) & 255:
            raise ValueError('Invalid HEX length/checksum')
        length, address, kind = row[0], int.from_bytes(row[1:3], 'big'), row[3]
        data = row[4:-1]
        if kind == 0:
            for i, value in enumerate(data):
                target = upper+address+i
                if target in image and image[target] != value:
                    raise ValueError('Conflicting HEX records')
                image[target] = value
        elif kind == 1 and length == 0:
            finished = True
        elif kind == 4 and length == 2:
            upper = int.from_bytes(data, 'big') << 16
        elif kind == 2 and length == 2:
            upper = int.from_bytes(data, 'big') << 4
        else:
            raise ValueError('Unsupported HEX record')
    if not finished or not image or min(image) != 0 or max(image) >= 1024:
        raise ValueError('HEX must have EOF and a device-sized image beginning at zero')
    return bytes(image.get(i, 255) for i in range(max(image)+1))


def verified_bundle(folder, samples):
    """Refuse stale, oversized, looping, mismatched or incomplete recordings."""
    report = read_json(folder/'build.json')
    v = report.get('verification') or {}
    if (report.get('status') != 'verified' or report.get('playbackMode') != 'once'
            or report.get('phraseSamples') != samples or not v.get('pass')
            or set(v.get('engines', ())) != {'reference', 'wasm', 'wasm-unoptimized'}
            or v.get('verifiedSamples') != 3*samples or v.get('phraseSamples') != samples
            or v.get('verifiedLoops') != 1 or v.get('silenceSamplesVerified') != 2*samples
            or v.get('mismatches') != 0 or v.get('lostOverflows') != 0 or v.get('missedSamples') != 0):
        raise ValueError(f'Incomplete three-engine, one-shot AVR verification: {folder}')
    image = (folder/'firmware.bin').read_bytes()
    actual = (folder/'actual.raw').read_bytes()
    if not 1 <= len(image) <= 1024 or len(image) != report.get('flashBytes'):
        raise ValueError('Firmware exceeds Flash or disagrees with its report')
    if (sha(image) != report.get('imageSha256') or sha(image) != v.get('imageSha256')
            or hex_image((folder/'firmware.hex').read_text(encoding='ascii')) != image):
        raise ValueError('Firmware BIN/HEX/report SHA mismatch')
    if (len(actual) != samples*3 or actual[samples:] != bytes([128])*(samples*2)
            or sha(actual) != v.get('actualPcmSha256')
            or sha(actual) != v.get('expectedPcmSha256')
            or (folder/'expected.raw').read_bytes() != actual
            or (report.get('expectedPcmSha256') is not None
                and sha(actual) != report['expectedPcmSha256'])):
        raise ValueError('Actual AVR phrase/silence/PCM SHA mismatch')
    eeprom_used = report.get('eepromUsedBytes', report.get('eepromBytes', 0))
    if not 0 <= eeprom_used <= 64 or not 0 <= report.get('eepromBytes', 0) <= 64:
        raise ValueError('EEPROM limit exceeded')
    if eeprom_used:
        eeprom = (folder/'eeprom.bin').read_bytes()
        if (len(eeprom) != report['eepromBytes'] or sha(eeprom) != report.get('eepromSha256')
                or sha(eeprom) != v.get('eepromSha256')
                or hex_image((folder/'eeprom.hex').read_text(encoding='ascii')) != eeprom):
            raise ValueError('EEPROM BIN/HEX/report SHA mismatch')
    return report, np.frombuffer(actual[:samples], np.uint8).copy()


def quality(reference, pcm, sr):
    objective = SpectralObjective(reference, sr)
    audio = (pcm.astype(float)-128)/128
    spectrum = objective.spectrum(audio)
    value = float(stoi(reference, audio, sr))
    return dict(**spectrum, stoi=value, estoi=deterministic_estoi(reference, audio, sr),
                balanced_score=value-.08*spectrum['loss'], pcm_sha256=sha(pcm.tobytes()),
                measured_from='actual AVR recording', samples=len(pcm), sample_rate=sr)


def candidate(folder, family, entry, reference):
    avr = folder/'avr' if (folder/'avr/build.json').exists() else folder
    if not (avr/'build.json').exists() or read_json(avr/'build.json').get('status') != 'verified':
        return None
    report, pcm = verified_bundle(avr, entry['reference_samples'])
    model_file = folder/'model.json'
    if family == 'tiny':
        matches = [p for p in (folder/'fit-model.json', folder/'quality-model.json')
                   if p.exists() and sha(p.read_bytes()) == report.get('modelSha256')]
        if not matches:
            raise ValueError('No retained Tiny model matches the assembled image')
        model_file = matches[0]
        model = read_json(model_file)
        expected = decode_fixed(model)
        packed = pack_tiny(model)
        if sha(packed['flash_data']) != report.get('dataSha256') or sha(packed['eeprom']) != report.get('eepromSha256'):
            raise ValueError('Tiny packed model differs from verified Flash/EEPROM')
        training_file = folder/'quality.json'
    elif family in ('hq4', 'tonal'):
        model = read_json(model_file)
        if model.get('reference_sha256') != entry['reference_sha256']:
            raise ValueError('HQ4 model reference SHA differs')
        f, d = np.asarray(model['frames'], np.uint8), np.asarray(model['durations'], np.uint16)
        stream = pack_stream(f, d)
        if (stream != (folder/'speech.hq').read_bytes() or sha(stream) != model.get('stream_sha256')
                or sha(stream) != report.get('streamSha256')):
            raise ValueError('HQ4 model, stream and assembled image differ')
        expected = decode(f, d, 0)
        training_file = folder/'training.json'
    else:
        from bell_model import SINE, decode_bell
        model = read_json(model_file)
        if (report.get('modelSha256') != sha(model_file.read_bytes())
                or model.get('reference_sha256') != entry['reference_sha256']):
            raise ValueError('Hybrid model SHA differs')
        voice = model['voice']
        expected = np.r_[decode_bell(model), decode(np.asarray(voice['frames'], np.uint8),
                                                   np.asarray(voice['durations'], np.uint16), 0)]
        if (avr/'eeprom.bin').read_bytes() != SINE.tobytes():
            raise ValueError('Hybrid EEPROM differs from its exact sine table')
        training_file = folder/'quality.json'
    if not np.array_equal(expected, pcm):
        raise ValueError('Compressed model and actual AVR phrase PCM differ')
    if report.get('phrasePcmSha256') and report['phrasePcmSha256'] != sha(pcm.tobytes()):
        raise ValueError('AVR phrase SHA differs')
    return dict(family=family, folder=folder, avr=avr, model_file=model_file,
                training_file=training_file, build=report, pcm=pcm,
                quality=quality(reference, pcm, entry['sample_rate']))


def load_entries(manifests):
    merged = {}
    for manifest in manifests:
        for value in read_json(manifest)['clips']:
            entry = dict(value)
            if not re.fullmatch(r'[a-z0-9_-]+', entry['id']):
                raise ValueError('Input clip IDs must be safe lowercase slugs')
            entry['_reference'] = manifest.parent/entry['id']/entry['reference_file']
            entry['_manifest'] = manifest
            merged[entry['id']] = entry
    for entry in merged.values():
        if entry.get('selection_start_seconds') is not None:
            entry['id'] += '-final'
    return list(merged.values())


def summarize_training(value):
    # Keep search settings/final evidence; discard optimizer trajectories and
    # the many rejected initialization measurements/candidate snapshots.
    return {k: v for k, v in value.items() if k not in ('history', 'candidates', 'measurements', 'triallog')}


def retain_candidate(destination, item):
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(item['model_file'], destination/'model.json')
    if (item['folder']/'speech.hq').exists():
        shutil.copyfile(item['folder']/'speech.hq', destination/'speech.hq')
    if item['training_file'].exists():
        write_json(destination/'training.json', summarize_training(read_json(item['training_file'])))
    write_json(destination/'build.json', item['build'])
    write_json(destination/'quality.json', item['quality'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT/'build/new-speech/listen')
    p.add_argument('--retain', type=Path)
    p.add_argument('--final-family', choices=('hq4', 'tonal', 'hybrid'), default='hq4')
    p.add_argument('--input-manifest', type=Path, action='append')
    p.add_argument('--trial-root', type=Path, default=ROOT/'build/new-speech')
    a = p.parse_args()
    manifests = a.input_manifest or [a.trial_root/'input/manifest.json', a.trial_root/'tail-input/manifest.json']
    entries = load_entries(manifests)
    a.output.mkdir(parents=True, exist_ok=True)
    cards, selected_records, zip_files = [], [], []
    for entry in entries:
        ident = entry['id']
        reference_path = entry['_reference']
        if sha(reference_path.read_bytes()) != entry['reference_sha256']:
            raise ValueError('Prepared reference SHA differs from input manifest')
        reference, sr = sf.read(reference_path)
        if sr != entry['sample_rate'] or len(reference) != entry['reference_samples']:
            raise ValueError('Prepared reference length/rate differs')
        choices = []
        for family in ('hq4', 'tiny'):
            item = candidate(a.trial_root/family/ident, family, entry, reference)
            if item:
                choices.append(item)
        if not any(c['family'] == 'hq4' for c in choices):
            raise ValueError('Every phrase needs a verified full HQ4 control')
        selected = max(choices, key=lambda item: item['quality']['balanced_score'])
        if ident.endswith('-final'):
            selected = next(c for c in choices if c['family'] == 'hq4')
            for family, path in (('tonal', a.trial_root/'hq4'/ident.replace('-final', '-tonal')),
                                 ('hybrid', a.trial_root/'bell-hybrid/result')):
                special = candidate(path, family, entry, reference)
                if special:
                    choices.append(special)
                    if family == a.final_family:
                        selected = special
        hybrid = next((c for c in choices if c['family'] == 'hybrid' and c is not selected), None)
        audio_dir = a.output/'audio'/ident
        firmware_dir = a.output/'firmware'/ident
        audio_dir.mkdir(parents=True, exist_ok=True)
        firmware_dir.mkdir(parents=True, exist_ok=True)
        objective = SpectralObjective(reference, sr)
        signals = [reference, (selected['pcm'].astype(float)-128)/128]
        if hybrid:
            signals.append((hybrid['pcm'].astype(float)-128)/128)
        pair = [sosfilt(objective.hp, x) for x in signals]
        pair = [x*objective.rms/(np.sqrt(np.mean(x*x))+1e-10) for x in pair]
        common_scale = .85/max(float(np.max(abs(x))) for x in pair)
        for name, audio in zip(('original', 'after', 'hybrid'), pair):
            sf.write(audio_dir/(name+'.wav'), audio*common_scale, sr, subtype='PCM_16')
        shutil.copyfile(reference_path, audio_dir/'reference.wav')
        shutil.copyfile(selected['avr']/'firmware.hex', firmware_dir/'firmware.hex')
        zip_files.append(firmware_dir/'firmware.hex')
        report = selected['build']
        used = report.get('eepromUsedBytes', report.get('eepromBytes', 0))
        if used:
            shutil.copyfile(selected['avr']/'eeprom.hex', firmware_dir/'eeprom.hex')
            zip_files.append(firmware_dir/'eeprom.hex')
        instruction = (f'ATtiny13A / {ident}\nFamily: {selected["family"]}\n'
                       f'Flash: {report["flashBytes"]}/1024 bytes. EEPROM used: {used}/64 bytes.\n'
                       'CPU clock: internal 9.6 MHz; software resets CLKPR; PWM output PB1/OC0B.\n'
                       'Program firmware.hex into Flash.\n'
                       + ('Program the paired eeprom.hex into EEPROM before playback.\n' if used else '')
                       + 'One complete phrase, then midpoint silence; reset restarts playback.\n'
                       'Verified digitally using three AVR engines, not tested on physical hardware.\n')
        (firmware_dir/'PROGRAMMING.txt').write_text(instruction, encoding='utf-8', newline='\n')
        zip_files.append(firmware_dir/'PROGRAMMING.txt')
        hybrid_html = ''
        if hybrid:
            alternate = firmware_dir/'hybrid'
            alternate.mkdir(parents=True, exist_ok=True)
            for name in ('firmware.hex', 'eeprom.hex'):
                shutil.copyfile(hybrid['avr']/name, alternate/name)
                zip_files.append(alternate/name)
            (alternate/'PROGRAMMING.txt').write_text('Alternative bell + HQ4 voice firmware.\nProgram BOTH firmware.hex into Flash AND eeprom.hex into EEPROM.\nATtiny13A, 9.6 MHz, PWM PB1/OC0B, one-shot.\nThis variant fits the bell spectrum better but has lower measured speech intelligibility.\n', encoding='utf-8', newline='\n')
            zip_files.append(alternate/'PROGRAMMING.txt')
            hybrid_html = (f'<details><summary>Альтернатива: точнее звон, ниже разборчивость речи</summary><p>Три частоты звона + HQ4. Flash {hybrid["build"]["flashBytes"]}/1024 · EEPROM 64/64 байт. Этот вариант оставлен для сравнения.</p>'
                           f'<audio controls preload="none" src="audio/{ident}/hybrid.wav"></audio><p>'
                           f'<a href="firmware/{ident}/hybrid/firmware.hex" download>Альтернативный Flash HEX</a> · '
                           f'<a href="firmware/{ident}/hybrid/eeprom.hex" download>Парный EEPROM HEX — обязателен</a></p></details>')
        clean_entry = {k: v for k, v in entry.items() if not k.startswith('_')}
        record = dict(id=ident, input=clean_entry, selectedFamily=selected['family'],
                      requestedFinalFamily=a.final_family if ident.endswith('-final') else None,
                      selectionProvisional=True, flashBytes=report['flashBytes'], eepromUsedBytes=used,
                      phraseSamples=len(reference), sampleHz=sr, imageSha256=report['imageSha256'],
                      actualPhrasePcmSha256=selected['quality']['pcm_sha256'], quality=selected['quality'],
                      alternatives=[dict(family=c['family'], flashBytes=c['build']['flashBytes'],
                                         eepromUsedBytes=c['build'].get('eepromUsedBytes', 0), quality=c['quality']) for c in choices],
                      originalAudio=f'audio/{ident}/original.wav', afterAudio=f'audio/{ident}/after.wav',
                      referenceAudio=f'audio/{ident}/reference.wav', firmware=f'firmware/{ident}/firmware.hex',
                      eeprom=f'firmware/{ident}/eeprom.hex' if used else None,
                      hybridAlternative=(dict(audio=f'audio/{ident}/hybrid.wav',
                                              firmware=f'firmware/{ident}/hybrid/firmware.hex',
                                              eeprom=f'firmware/{ident}/hybrid/eeprom.hex') if hybrid else None),
                      verification=dict(engines=report['verification']['engines'],
                                        verifiedSamples=report['verification']['verifiedSamples'],
                                        silenceSamplesVerified=report['verification']['silenceSamplesVerified'],
                                        lostOverflows=0, missedSamples=0))
        selected_records.append(record)
        if a.retain:
            retained = a.retain/ident
            write_json(retained/'input.json', clean_entry)
            for item in choices:
                retain_candidate(retained/item['family'], item)
            write_json(retained/'selection.json', record)
        title = html.escape(entry['source_file'])
        if ident.endswith('-final'):
            title += ' · заключительная фраза со звоном'
        cards.append(f'<article><h2>{title}</h2><p>{len(reference)/sr:.2f} с · {html.escape(selected["family"])} · Flash {report["flashBytes"]}/1024 · EEPROM {used}/64 байт</p>'
                     f'<label>Оригинал<audio controls preload="none" src="audio/{ident}/original.wav"></audio></label>'
                     f'<label>Из проверенного HEX<audio controls preload="none" src="audio/{ident}/after.wav"></audio></label>'
                     f'<p><a href="firmware/{ident}/firmware.hex" download>Flash HEX</a>'
                     + (f' · <a href="firmware/{ident}/eeprom.hex" download>EEPROM HEX — записать вместе</a>' if used else '')
                     + f' · <a href="audio/{ident}/reference.wav" download>Исходный WAV 7500 Гц</a></p>{hybrid_html}</article>')
    manifest = dict(schema='new-speech-listening-v1', selectionPolicy='highest STOI - 0.08*spectral_loss among verified controls; final family explicitly selected',
                    humanListeningVerified=False, hardwareTested=False,
                    runtime={name: importlib.metadata.version(name) for name in ('numpy', 'scipy', 'pystoi', 'soundfile')},
                    packagerSha256NormalizedLf=sha(Path(__file__).read_text(encoding='utf-8').encode('utf-8')),
                    listeningProcessing='Both previews: identical 70-Hz highpass, RMS matching and common peak scale. Raw reference is separately available.',
                    clips=selected_records)
    write_json(a.output/'manifest.json', manifest)
    if a.retain:
        write_json(a.retain/'manifest.json', manifest)
        (a.retain/'README.md').write_text('# New phrase trials\n\nCompressed source models and independent AVR qualification are retained here. Original MP3/WAV, assembled binaries and optimizer checkpoints remain outside Git. Input reports preserve external source filenames, SHA-256, preprocessing and any requested excerpt boundaries.\n\nSelections are provisional comparisons of the same exact AVR PCM using STOI, deterministic eSTOI and the common multi-resolution spectral objective. Human listening and physical hardware tests are not claimed. Nonselected verified models preserve useful negative evidence.\n\nHQ4: rebuild each `speech.hq` using `tools/build-hq4-oneshot.py --stream <stream> --clip <id> --samples <reference_samples> --output <build-directory>`. Tiny: rebuild its `model.json` using `tools/build-tiny-speech.py --model <model> --output <build-directory> --play-once`. Refer to the hybrid model and builder when the selected family is hybrid.\n', encoding='utf-8', newline='\n')
    page = ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Новые речевые прошивки ATtiny13A</title><style>body{font:16px system-ui;max-width:960px;margin:40px auto;padding:0 20px;background:#11151d;color:#e8edf5}h1{font-size:30px}h2{font-size:19px;overflow-wrap:anywhere}p{line-height:1.5;color:#b9c5d6}article{padding:22px;margin:22px 0;border:1px solid #35435c;border-radius:15px;background:#1a2230}label{display:block;margin:15px 0}audio{display:block;width:100%;margin-top:7px}a{color:#8ecbff}header>a{display:inline-block;padding:10px;border:1px solid #48678a;border-radius:8px}</style>'
            '<header><h1>Пять новых речевых примеров · ATtiny13A</h1><p>Оригинал и звук, записанный из эмуляции собранной прошивки. Громкость пары выровнена. Каждая прошивка произносит фразу один раз.</p><a href="firmware.zip" download>Скачать все 5 прошивок ZIP</a></header>'
            + ''.join(cards) + '<p>Варианты выбраны предварительно по разборчивости и спектральной ошибке. Все HEX проверены тремя реализациями эмулятора; проверки на физическом контроллере пока нет.</p></html>')
    (a.output/'index.html').write_text(page, encoding='utf-8', newline='\n')
    with zipfile.ZipFile(a.output/'firmware.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(zip_files):
            archive.write(file, file.relative_to(a.output/'firmware').as_posix())
    print(json.dumps(dict(output=str(a.output), clips=[dict(id=c['id'], family=c['selectedFamily'], flash=c['flashBytes'], eeprom=c['eepromUsedBytes'], stoi=c['quality']['stoi']) for c in selected_records]), ensure_ascii=False))


if __name__ == '__main__':
    main()
