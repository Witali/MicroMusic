"""Measure integer output DC removal independently of natural asymmetry.

Original WAVs and all generated WAVs remain in ignored build directories.
Example: python tools/probe-speech-dc.py --report <retained-report.json>
Optional --fixed-model chego=path.json measures an already retuned decoder.
"""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import numpy as np
import soundfile as sf
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective
from colored_period import decode_colored
from fixed_period import decode_fixed, from_colored
from dc_blocker import block_dc

SR = 7500


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pwm_float(pcm):
    return (pcm.astype(np.float64)-128)/128


def output_metrics(pcm, reference, objective):
    x = pwm_float(pcm)
    # The same RMS gain is used for mean/window drift and spectral statistics.
    # Ratio is independent of playback loudness, unlike raw PWM mean in LSB.
    rms = float(np.sqrt(np.mean(x*x)))
    means = np.convolve(x, np.ones(750)/750, mode='valid')
    return dict(stoi=float(stoi(reference, x, SR)), **objective.spectrum(x),
                mean_pwm_lsb=float(np.mean(x)*128),
                mean_over_rms=float(np.mean(x)/max(rms, 1e-20)),
                window_100ms_mean_rms_over_signal_rms=float(np.sqrt(np.mean(means*means))/max(rms, 1e-20)),
                window_100ms_mean_peak_lsb=float(np.max(abs(means))*128),
                positive_peak_lsb=int(np.max(pcm.astype(int)-128)),
                negative_peak_lsb=int(np.min(pcm.astype(int)-128)))


def continuity_metrics(pcm, shift):
    zeros = np.full(SR//4, 128, np.uint8)
    # Whole filter call is equivalent to streaming/chunked playback: no resets
    # on entering silence or crossing a phrase boundary.
    sequence = np.r_[zeros, np.tile(pcm, 3), zeros]
    out, state, clipped, peak = block_dc(sequence, shift)
    tail = out[-len(zeros):].astype(int)-128
    nonzero = np.flatnonzero(tail)
    steady = out[len(zeros)+2*len(pcm):len(zeros)+3*len(pcm)]
    joins = [len(zeros)+len(pcm), len(zeros)+2*len(pcm)]
    return dict(final_state=int(state), clipped=clipped,
                pre_clamp_peak_lsb=peak,
                tail_settle_samples=int(nonzero[-1]+1) if len(nonzero) else 0,
                final_512_samples_all_zero=bool(np.all(tail[-512:] == 0)),
                carried_third_loop_mean_lsb=float(np.mean(steady.astype(int)-128)),
                loop_boundary_steps_lsb=[int(out[j])-int(out[j-1]) for j in joins])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-root', type=Path, default=Path('C:/Work/MicroMusic/build/hq4-preview'))
    parser.add_argument('--output', type=Path, default=ROOT/'build/speech-dc')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--fixed-model', action='append', default=[], metavar='CLIP=PATH')
    args = parser.parse_args()
    supplied = dict(item.split('=', 1) for item in args.fixed_model)
    manifest = json.loads((ROOT/'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))
    report = dict(schema='micromusic-speech-dc-v1', sample_rate=SR,
                  arithmetic='estimate=(state+2^(shift-1))>>shift; y=x-estimate; state+=y; output=saturate_s8(y)',
                  state_bytes=2, default_shift=7,
                  rounding='nearest, ties toward positive infinity; signed arithmetic shifts',
                  continuity='state retained across chunks/loops; reset only at new playback; zero input after end',
                  note='Natural waveform asymmetry is preserved. These are postfilter measurements, not encoder retuning.',
                  packages={name:version(name) for name in ('numpy', 'scipy', 'numba', 'pystoi', 'soundfile')},
                  normalized_source_sha256={name:hashlib.sha256((ROOT/name).read_text(encoding='utf-8').encode('utf-8')).hexdigest() for name in (
                      'ATtiny13A/Sound/codec/dc_blocker.py', 'tools/probe-speech-dc.py',
                      'ATtiny13A/Sound/codec/fixed_period.py', 'ATtiny13A/Sound/codec/colored_period.py',
                      'ATtiny13A/Sound/codec/period_wave.py', 'ATtiny13A/Sound/codec/auto_encoder.py')}, clips={})
    for clip in manifest['clips']:
        ident = clip['id']
        original = args.original_root/ident/'original.wav'
        if sha(original) != clip['sha256']:
            raise ValueError(f'Original hash mismatch: {ident}')
        reference, rate = sf.read(original)
        if rate != SR or reference.shape != (clip['samples'],):
            raise ValueError(f'Original format mismatch: {ident}')
        objective = SpectralObjective(reference)
        model_path = ROOT/'ATtiny13A/Sound/research/period-balanced'/ident/'model.json'
        model = json.loads(model_path.read_text(encoding='utf-8'))
        float_pcm = np.clip(np.rint(decode_colored(model)*128)+128, 0, 255).astype(np.uint8)
        fixed_path = Path(supplied[ident]) if ident in supplied else None
        fixed_model = json.loads(fixed_path.read_text(encoding='utf-8')) if fixed_path else from_colored(model, 4)
        sources = dict(approved_float_rounded8=float_pcm, integer_fixed4=decode_fixed(fixed_model))
        original_means = np.convolve(reference, np.ones(750)/750, mode='valid')
        item = dict(original_sha256=sha(original), colored_model_sha256=sha(model_path),
                    original_dc=dict(mean_pwm_lsb=float(np.mean(reference)*128),
                        window_100ms_mean_peak_lsb=float(np.max(abs(original_means))*128),
                        positive_peak_lsb=float(np.max(reference)*128),
                        negative_peak_lsb=float(np.min(reference)*128)),
                    fixed_model_sha256=sha(fixed_path) if fixed_path else None,
                    fixed_model_origin=str(fixed_path) if fixed_path else 'from_colored(approved_model, phase_bits=4), no retuning',
                    sources={})
        output_dir = args.output/ident
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, pcm in sources.items():
            source = dict(before=output_metrics(pcm, reference, objective), candidates=[])
            for gain in (128, 112):
                # Optional 7/8 headroom is measured explicitly, never hidden by
                # clipping or normalization. Native encoder should reserve it.
                gained = np.clip(((pcm.astype(int)-128)*gain+64)//128, -128, 127).astype(np.int16)+128
                gained = gained.astype(np.uint8)
                for shift in (5, 6, 7):
                    out, state, clipped, peak = block_dc(gained, shift)
                    source['candidates'].append(dict(shift=shift, input_gain_q7=gain,
                        after=output_metrics(out, reference, objective),
                        state_after_phrase=int(state), clipped=clipped, pre_clamp_peak_lsb=peak,
                        continuity=continuity_metrics(gained, shift)))
                    if gain == 128 and shift == 7:
                        sf.write(output_dir/f'{name}-dc7.wav', pwm_float(out), SR, subtype='PCM_16')
            item['sources'][name] = source
            best = next(v for v in source['candidates'] if v['shift']==7 and v['input_gain_q7']==128)
            print(f"{ident} {name}: mean {source['before']['mean_pwm_lsb']:.3f}->{best['after']['mean_pwm_lsb']:.3f} LSB; "
                  f"STOI {source['before']['stoi']:.6f}->{best['after']['stoi']:.6f}; clipped={best['clipped']}")
        report['clips'][ident] = item
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.report or args.output/'quality.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(f'Report: {path}')


if __name__ == '__main__':
    main()
