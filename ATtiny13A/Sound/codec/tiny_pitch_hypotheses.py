"""Encoder-only F0 hypotheses for the unchanged Tiny integer speech decoder."""
from copy import deepcopy
import hashlib
import time

import numpy as np
from pystoi import stoi

from fixed_period import decode_fixed
from hq4_speech_search import deterministic_estoi
from new_tiny_encoder import analyze_reference, initialize_model, pad_reference, attenuate
from period_wave import track_pitch, continuous_phase, align_phase, quantize_phase, fit_periods
from speech_pitch import track_speech_pitch
from speech_regression import compare_recording_metrics
from spectrogram_objective import SpectrogramObjective
from tiny_period import pack_tiny, unpack_tiny


def pitch_hypotheses(reference):
    centres, legacy, quality = track_pitch(reference)
    items = [dict(name='legacy', centres=centres, f0=legacy, quality=quality,
                  metadata=dict(prior_hz=None, transformed_frames=0))]
    for name, factor in (('octave-down', .5), ('octave-up', 2.)):
        changed = (legacy > 0) & (legacy*factor >= 65.) & (legacy*factor <= 850.)
        frequency = np.where(changed, legacy*factor, legacy)
        items.append(dict(name=name, centres=centres, f0=frequency, quality=quality,
                          metadata=dict(factor=factor, admissible_low_hz=65., admissible_high_hz=850.,
                                        transformed_frames=int(changed.sum()), inadmissible_policy='Keep legacy F0; preserve unvoiced frames')))
    _, _, _, persistent = track_speech_pitch(reference)
    prior = persistent['prior_hz']
    if prior is None:
        frequency, soft_quality = legacy.copy(), quality.copy()
    else:
        _, frequency, soft_quality = track_pitch(reference, prior_hz=prior, prior_weight=.15)
    items.append(dict(name='persistent-soft', centres=centres, f0=frequency, quality=soft_quality,
                      metadata=dict(prior_hz=prior, prior_weight=.15,
                                    transformed_frames=int(np.sum(frequency != legacy)),
                                    prior_policy='Existing source-derived persistent-run estimator; only its soft F0 prior is used, not its hard voice/onset mask')))
    return items


def analysis_from_pitch(reference, item):
    f0, centres = item['f0'], item['centres']
    phase = align_phase(reference, continuous_phase(f0, centres, len(reference)), f0, centres)
    phase -= np.floor(phase[0])
    initial = int(np.rint(phase[0]*65536)) % 65536
    phase += initial/65536-phase[0]
    codes, quantized = quantize_phase(phase, len(reference))
    shapes = fit_periods(reference, quantized, f0, centres)
    base = dict(initial_phase_u16=initial,
                frames=[[int(code), 0, 0, int(f > 0)] for code, f in zip(codes, f0)])
    return base, dict(shapes=shapes, f0=f0, centres=centres, phase=quantized)


def safe_initialize(reference, base, analysis, words, seed):
    model = initialize_model(reference, base, analysis, words, starts=1, seed=seed)
    for attenuation in range(11):
        pcm = decode_fixed(model)
        raw = decode_fixed(dict(model, dc_block_shift=0))
        if np.max(abs(pcm.astype(int)-128)) <= 121 and not np.any((raw == 0) | (raw == 255)):
            return model, attenuation
        model = attenuate(model)
    raise ValueError('Tiny initializer cannot avoid sample clipping after ten automatic attenuation steps')


def score(reference, model, objective):
    pcm = decode_fixed(model)
    packed = pack_tiny(model)
    if not np.array_equal(pcm, decode_fixed(unpack_tiny(packed))):
        raise AssertionError('Tiny packing changed exact integer PCM')
    audio = (pcm.astype(float)-128)/128
    return dict(**objective.evaluate(audio), stoi=float(stoi(reference, audio, 7500)),
                estoi=deterministic_estoi(reference, audio, 7500),
                flash_data_bytes=len(packed['flash_data']), eeprom_used_bytes=packed['constants']['EEPROM_USED_BYTES'],
                flash_data_sha256=hashlib.sha256(packed['flash_data']).hexdigest(),
                eeprom_sha256=hashlib.sha256(packed['eeprom']).hexdigest(),
                pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),
                peak_signed=int(np.max(abs(pcm.astype(int)-128))))


def run(audio, *, baseline_model=None, words=(4, 8), baseline_words=8, seed=23230):
    started = time.perf_counter()
    reference = pad_reference(audio)
    if any(w not in (4, 8) for w in words) or baseline_words not in (4, 8):
        raise ValueError('This bounded experiment uses four/eight words only')
    # Keep the original legacy path as an explicit exact control. The separate
    # hypothesis helper never changes frozen period_wave/new_tiny_encoder.
    _, legacy_base, legacy_analysis = analyze_reference(reference, starts=1, seed=seed, pitch_mode='legacy')
    hypotheses = pitch_hypotheses(reference)
    objective = SpectrogramObjective(reference)
    legacy_models = {}
    legacy_attenuations = {}
    trials = []
    for w in set(words) | {baseline_words}:
        model, attenuation = safe_initialize(reference, legacy_base, legacy_analysis, w, seed)
        legacy_models[w] = model
        legacy_attenuations[w] = attenuation
    if baseline_model is None:
        incumbent = deepcopy(legacy_models[baseline_words])
        label = f'legacy-initializer-{baseline_words}-words'
    else:
        incumbent = deepcopy(baseline_model)
        if incumbent.get('sample_rate') != 7500 or incumbent.get('samples') != len(reference):
            raise ValueError('Protected baseline must match the complete padded reference sample count and rate')
        label = 'protected-model'
    before = score(reference, incumbent, objective)
    budget = before['flash_data_bytes']
    selected, selected_score, selected_name = deepcopy(incumbent), before.copy(), 'baseline'
    for item in hypotheses:
        if item['name'] == 'legacy':
            base, analysis = legacy_base, legacy_analysis
        else:
            base, analysis = analysis_from_pitch(reference, item)
        for w in words:
            if item['name'] == 'legacy':
                model, attenuation = legacy_models[w], legacy_attenuations[w]
            else:
                model, attenuation = safe_initialize(reference, base, analysis, w, seed)
            metrics = score(reference, model, objective)
            gate = compare_recording_metrics(before, metrics)
            size_passed = metrics['flash_data_bytes'] <= budget and metrics['eeprom_used_bytes'] <= 64
            eligible = gate['candidate_passed'] and size_passed
            f0 = item['f0']
            voiced = f0[f0 > 0]
            trial = dict(hypothesis=item['name'], words=w, metrics=metrics, quality_gate=gate,
                         size_passed=size_passed, eligible=eligible, attenuation_steps=attenuation,
                         f0_summary=dict(voiced_frames=len(voiced), total_frames=len(f0),
                             median_hz=float(np.median(voiced)) if len(voiced) else None),
                         pitch_metadata=item['metadata'])
            trials.append(trial)
            if eligible and metrics['spectrogram_loss'] < selected_score['spectrogram_loss']-1e-12:
                selected, selected_score = deepcopy(model), metrics.copy()
                selected_name = f"{item['name']}-{w}-words"
    initial_pack, final_pack = pack_tiny(incumbent), pack_tiny(selected)
    if selected_name == 'baseline':
        assert initial_pack['flash_data'] == final_pack['flash_data']
        assert initial_pack['eeprom'] == final_pack['eeprom']
        assert np.array_equal(decode_fixed(incumbent), decode_fixed(selected))
    report = dict(schema='tiny-pitch-hypotheses-v1', baseline_label=label, baseline=before,
        selected_source=selected_name, selected=selected_score, baseline_fallback=selected_name == 'baseline',
        selected_quality_gate=compare_recording_metrics(before, selected_score),
        flash_data_budget=budget, seed=seed, starts=1, words=list(words), trials=trials,
        reference_samples=len(audio), encoded_samples=len(reference), padding_samples=len(reference)-len(audio),
        decoder_source_changes=False, added_decoder_instructions=0, avr_assembled=False,
        total_flash_qualified=False, hardware_tested=False, elapsed_seconds=time.perf_counter()-started,
        scope='Finite per-recording six-metric comparison, no guarantee for unseen recordings; no averaging across clips',
        normalization='No input gain, DC removal, cropping or time compression; only final incomplete-block zero padding')
    return reference, incumbent, selected, report
