"""Export an audited pilot for local listening; no encoding or level fitting."""
from __future__ import annotations
import argparse
import io
from pathlib import Path
import struct
import sys
import wave

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study as s
import runner as r


def pcm_wave(payload):
    if len(payload) != s.SAMPLES * 2:
        raise ValueError('Expected the complete 20-second PCM16 payload')
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(s.RATE)
        output.writeframes(payload)
    return buffer.getvalue()


def wave_payload(data):
    with wave.open(io.BytesIO(data), 'rb') as stream:
        if (stream.getnchannels() != 1 or stream.getsampwidth() != 2
                or stream.getframerate() != s.RATE or stream.getnframes() != s.SAMPLES
                or stream.getcomptype() != 'NONE'):
            raise ValueError('WAV geometry differs from the prepared target')
        payload = stream.readframes(s.SAMPLES + 1)
        if len(payload) != s.SAMPLES * 2 or stream.readframes(1):
            raise ValueError('WAV does not contain the complete expected samples')
    return payload


def pwm_duty_average(payload):
    if len(payload) != s.SAMPLES * 2:
        raise ValueError('Wrong complete waveform length')
    result = bytearray()
    for value, in struct.iter_unpack('<h', payload):
        q14 = (value + 1) // 2
        duty = max(0, min(255, 128 + ((q14 * 130 + 8192) >> 14)))
        result.extend(struct.pack('<h', (duty - 128) * 256))
    return bytes(result)


def write_wave(path, payload, output):
    path = Path(path)
    path.resolve().relative_to(output)
    expected = pcm_wave(payload)
    if path.exists():
        if path.read_bytes() != expected:
            raise ValueError('Existing listening output belongs to different evidence')
    else:
        with path.open('xb') as stream:
            stream.write(expected)
    if path.read_bytes() != expected or wave_payload(path.read_bytes()) != payload:
        raise ValueError('WAV readback changed the exact sample bytes')


def build_listening(args):
    study_root, freeze, build = r.load(args.study)
    if (freeze['first_development_ordinal'] != 1 or freeze['quality_target'] != 'pwm'
            or freeze['samples'] != s.SAMPLES or freeze['rate'] != s.RATE):
        raise ValueError('Expected the frozen first development pilot')
    cases = [case for case in freeze['cases']
             if case['ordinal'] == 1 and case['split'] == 'development']
    if len(cases) != 1:
        raise ValueError('Pilot source membership differs')
    case = cases[0]
    complete = r.completed(study_root, freeze, case)
    if complete is None or complete.get('status') != 'PASS':
        raise ValueError('Successful immutable pilot completion is required before export')
    folder = r.case_folder(study_root, case['ordinal'])
    completion_path = folder / 'complete-private.json'
    audit = r.gate(args.pilot_audit, 'lpx-audiobook-pilot-independent-v1')
    if (audit['freeze_sha256'] != s.sha(study_root / 'freeze-private.json')
            or audit['pilot_completion_sha256'] != s.sha(completion_path)):
        raise ValueError('Successful pilot audit does not bind this exact completion')

    report_path = folder / 'encode-private.json'
    verify_path = folder / 'verify-private.json'
    report, verified = s.read(report_path), s.read(verify_path)
    s.check_verification(verified, report)
    artifacts, waveform = s.check_artifacts(report, case['target'], folder / 'run')
    if artifacts != complete['artifacts'] or waveform != complete['waveform']:
        raise ValueError('Audited immutable pilot outputs changed')
    public = s.read(args.public)
    expected_case = r.public_case(study_root, freeze, case)
    if (public.get('schema') != 'lpx-audiobook-study-anonymous-v1' or public.get('phase') != 'pilot'
            or public.get('expected_cases') != 1 or public.get('cases') != [expected_case]
            or public.get('aggregate') != s.aggregate([expected_case], 1)
            or not public['aggregate']['complete']
            or public['software']['sources'] != build['sources']
            or public['software']['study_sources'] != freeze['software']
            or public['software']['binary_sha256'] != build['binary_sha256']):
        raise ValueError('Pilot public report does not reproduce the frozen private evidence')

    output = s.private(args.output)
    output.relative_to((s.ROOT / 'build/audiobook-training').resolve())
    source_wav = output / 'source.wav'
    if not source_wav.is_file():
        raise ValueError('The original source.wav must already exist and will not be replaced')
    source_wav.resolve().relative_to(output)
    original_wav = source_wav.read_bytes()
    source = Path(case['target']).read_bytes()
    if s.digest(source) != case['target_sha256'] or wave_payload(original_wav) != source:
        raise ValueError('Original source.wav differs from the exact frozen prepared target')
    before = dict(freeze=s.sha(study_root / 'freeze-private.json'), completion=s.sha(completion_path),
                  report=s.sha(report_path), verification=s.sha(verify_path), source_wav=s.digest(original_wav))

    exports = {'source.wav': source}
    for label, suffix in (('current', 'baseline'), ('selected', 'selected')):
        payload = (folder / ('run-' + suffix + '.pcm')).read_bytes()
        exports[label + '-pcm.wav'] = payload
        exports[label + '-pwm-duty-average.wav'] = pwm_duty_average(payload)
    raw_admitted = bool(report['raw_available'] and report['selected_changed']
        and (folder / 'run-raw.lpx').read_bytes() == (folder / 'run-selected.lpx').read_bytes())
    if raw_admitted != bool(report['stage']['selected']):
        raise ValueError('Raw diagnostic admission label differs from production selection')
    if report['raw_available']:
        raw_payload = (folder / 'run-raw.pcm').read_bytes()
        exports['raw-candidate-pcm.wav'] = raw_payload
        exports['raw-candidate-pwm-duty-average.wav'] = pwm_duty_average(raw_payload)
    same_pcm = exports['current-pcm.wav'] == exports['selected-pcm.wav']
    same_pwm = exports['current-pwm-duty-average.wav'] == exports['selected-pwm-duty-average.wav']
    if not report['selected_changed'] and not (same_pcm and same_pwm):
        raise ValueError('Unchanged production selection differs from the current waveform')
    raw_reason = ('no_valid_raw_proposal' if not report['raw_available'] else
                  'admitted_by_production_selector' if raw_admitted else
                  'production_octave_observation_floor' if report['stage']['selection_octave_rejected'] else
                  'optional_validation_failure' if report['stage']['error'] else
                  'production_selector_retained_incumbent')
    for name, payload in exports.items():
        if name == 'source.wav':
            continue  # Preserve its exact original header and bytes.
        write_wave(output / name, payload, output)
    for name, payload in exports.items():
        if wave_payload((output / name).read_bytes()) != payload:
            raise ValueError('Listening readback differs from the bound waveform')
    after = dict(freeze=s.sha(study_root / 'freeze-private.json'), completion=s.sha(completion_path),
                 report=s.sha(report_path), verification=s.sha(verify_path), source_wav=s.sha(source_wav))
    if before != after or r.completed(study_root, freeze, case) != complete:
        raise ValueError('Listening export modified a frozen input or the original source WAV')
    r.load(study_root)

    receipt = dict(schema='lpx-audiobook-listening-private-v1', passed=True, ordinal=1,
        study=str(study_root), freeze_sha256=before['freeze'], completion_sha256=before['completion'],
        report_sha256=before['report'], verification_sha256=before['verification'],
        pilot_audit=str(Path(args.pilot_audit).resolve()), pilot_audit_sha256=s.sha(args.pilot_audit),
        public_report_sha256=s.sha(args.public), target_sha256=case['target_sha256'],
        script_sha256=s.sha(Path(__file__)), samples=s.SAMPLES, rate=s.RATE,
        selected_changed=report['selected_changed'], original_source_wav_preserved=True,
        selected_pcm_equals_current=same_pcm, selected_pwm_equals_current=same_pwm,
        raw_available=report['raw_available'], raw_admitted=raw_admitted,
        raw_diagnostic_only=bool(report['raw_available'] and not raw_admitted),
        raw_reason=raw_reason,
        raw_stage_reason=dict(status=report['stage']['status'], error=report['stage']['error'],
            selection_error=report['stage']['selection_error'],
            selection_octave_rejected=report['stage']['selection_octave_rejected']),
        fitted_gain=False, fitted_delay=False, normalized=False, trimmed=False, resampled=False,
        no_encoding_or_search=True,
        scope='Native PCM and actual verified 130-gain rounded PWM duty-average transfer; not a physical board recording. The same untouched source reference is used for both comparisons.',
        comparisons=dict(native_pcm=['source.wav', 'current-pcm.wav', 'selected-pcm.wav'],
            pwm_duty_average=['source.wav', 'current-pwm-duty-average.wav', 'selected-pwm-duty-average.wav']),
        files={name: dict(wav_sha256=s.sha(output / name), pcm_sha256=s.digest(payload),
                         pcm_bytes=len(payload)) for name, payload in exports.items()})
    if report['raw_available']:
        receipt['comparisons']['diagnostic_raw_pcm'] = ['source.wav', 'current-pcm.wav', 'raw-candidate-pcm.wav']
        receipt['comparisons']['diagnostic_raw_pwm'] = ['source.wav', 'current-pwm-duty-average.wav', 'raw-candidate-pwm-duty-average.wav']
    s.write(output / 'listening-binding-private.json', receipt, immutable=True)
    print(s.encoded(dict(schema='lpx-audiobook-listening-ready-v1', passed=True, ordinal=1,
        samples=s.SAMPLES, rate=s.RATE, wav_files=len(exports), selected_changed=report['selected_changed'],
        selected_pcm_equals_current=same_pcm, selected_pwm_equals_current=same_pwm,
        raw_available=report['raw_available'], raw_admitted=raw_admitted,
        raw_diagnostic_only=bool(report['raw_available'] and not raw_admitted),
        raw_reason=raw_reason,
        original_source_preserved=True, no_encoding_or_search=True)).decode('utf-8').strip())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--pilot-audit', type=Path, required=True)
    parser.add_argument('--public', type=Path, default=HERE / 'results-pilot.json')
    parser.add_argument('--output', type=Path, default=s.ROOT / 'build/audiobook-training/listening-pilot')
    build_listening(parser.parse_args())
