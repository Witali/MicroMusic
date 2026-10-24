"""Encoder-only lookahead trellis for exact compact Q3 pulsebook profiles.

Original-derived LPC perceptual weights rank joint neighbouring-frame proposals.
They never replace full-duration STOI/spectrogram or arithmetic/size guards.
No independently synthesized PCM blocks are joined together.
"""
import argparse
from collections import Counter
from copy import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.linalg import solve_toeplitz
from scipy.signal import sosfilt
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from hq4_core import pack_stream
from hq4_speech_search import deterministic_estoi
from harmonic_tracks import HarmonicTrackObjective
from partial_bounds import check_partial_bounds


def load_cycles():
    name = 'q3_perceptual_cycle_api'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name,ROOT/'tools/probe-q3-pulsebook-cycles.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def frame_bounds(durations):
    """Exact frozen oracle: frame0 is also reloaded at sample N-1."""
    d = np.asarray(durations,dtype=int)
    starts = np.r_[0,np.cumsum(d)[:-1]-1]
    stops = np.r_[starts[1:],int(d.sum())-1]
    return starts,stops


def perceptual_weights(reference_frames,order=8,gamma1=.92,gamma2=.6):
    """Power response |A(gamma1*z^-1)/A(gamma2*z^-1)|^2.

    LPCs depend only on the original. Autocorrelation diagonal loading and
    bandwidth expansion make silence/near-periodic frames finite. This is a
    Speex-style weighting variant with experiment gamma1=.92, gamma2=.6;
    it is a ranking guide, not a port of its CELP encoder or final criterion.
    """
    x = np.asarray(reference_frames,dtype=float)
    if (x.ndim != 2 or x.shape[1] <= order or order < 1
            or not 0 < gamma2 < gamma1 < 1 or not np.all(np.isfinite(x))):
        raise ValueError('Expected finite original frames and stable LPC weighting parameters')
    window = np.hanning(x.shape[1])
    weights,coefficients = [],[]
    for frame in x:
        y = (frame-frame.mean())*window
        ac = np.array([np.dot(y[k:],y[:len(y)-k]) for k in range(order+1)])
        ac[0] += max(ac[0]*1e-3,1e-12)
        a = np.r_[1.,solve_toeplitz(ac[:-1],-ac[1:],check_finite=False)]
        a1,a2 = a*gamma1**np.arange(order+1),a*gamma2**np.arange(order+1)
        power = abs(np.fft.rfft(a1,n=x.shape[1]))**2/np.maximum(abs(np.fft.rfft(a2,n=x.shape[1]))**2,1e-20)
        if not np.all(np.isfinite(power)) or np.any(power <= 0):
            raise ValueError('Nonfinite perceptual LPC response')
        weights.append(power)
        coefficients.append(a)
    return np.asarray(weights),np.asarray(coefficients)


class PerceptualGuide:
    """Two independent proposal rankings: weighted residual and log magnitude.

    Whole-clip PCM always comes from the exact decoder. Scoring windows include
    512 samples of context on each side of a proposed trajectory. No clipping,
    time alignment, per-window gain matching or reference PCM reaches a model.
    """
    def __init__(self,reference,window=512,hop=128):
        self.reference = np.asarray(reference,dtype=float)
        self.window,self.hop = window,hop
        self.starts = np.arange(0,len(reference),hop,dtype=int)
        self.window_values = np.hanning(window)
        padded = np.pad(self.reference,(0,window))
        frames = np.array([padded[t:t+window] for t in self.starts])
        self.weights,self.lpc = perceptual_weights(frames)
        self.reference_fft = np.fft.rfft(frames*self.window_values,axis=1)
        self.floor = max(float(np.max(abs(self.reference_fft)))*1e-4,1e-12)

    def evaluate(self,audio,start,stop):
        audio = np.asarray(audio,dtype=float)
        if audio.shape != self.reference.shape or not np.all(np.isfinite(audio)):
            raise ValueError('Guide requires exact full-duration finite PCM')
        indices = np.flatnonzero((self.starts < min(len(audio),stop+512))
            & (self.starts+self.window > max(0,start-512)))
        padded = np.pad(audio,(0,self.window))
        frames = np.array([padded[self.starts[i]:self.starts[i]+self.window] for i in indices])
        candidate = np.fft.rfft(frames*self.window_values,axis=1)
        reference,weight = self.reference_fft[indices],self.weights[indices]
        residual = float(np.sum(weight*abs(candidate-reference)**2)/max(float(np.sum(weight*abs(reference)**2)),1e-20))
        log_error = float(np.sum(weight*(np.log(np.maximum(abs(candidate),self.floor))
            -np.log(np.maximum(abs(reference),self.floor)))**2)/np.sum(weight))
        return residual,log_error


def state_key(state):
    return state.frames.tobytes(),state.durations.tobytes(),state.book.tobytes()


def unused_pole_conversion(model):
    """Explicit schema conversion only when the exceptional nibble is unused.

    Both frozen full-duration oracles must agree in PCM and internal counts.
    An assembled ordinary-core report is still required by the caller.
    """
    cycles = load_cycles()
    pole,ordinary = cycles.load_search(True),cycles.load_search(False)
    if model['schema'] != pole.SCHEMA:
        raise ValueError('Feature selection expects an explicitly tagged pole model')
    f,d,b = np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16),np.asarray(model['pulsebook'],np.int8)
    zero_count = int(np.sum((f[:,2:] & 15) == 0)+np.sum((f[:,2:] >> 4) == 0))
    if zero_count:
        raise ValueError('An active -15/16 coefficient cannot use ordinary Q3')
    nearest,tilt = bool(model.get('nearest',False)),int(model.get('tilt_shift',1))
    pole.validate(f,d,b,int(d.sum()))
    ordinary.validate(f,d,b,int(d.sum()))
    a,ac = pole.render(f,d,b,tilt,nearest)
    z,zc = ordinary.render(f,d,b,tilt,nearest)
    if not np.array_equal(a,z) or not np.array_equal(ac,zc):
        raise AssertionError('Unused-pole conversion changed exact PCM or internal arithmetic')
    converted = dict(model,schema=ordinary.SCHEMA)
    return converted,dict(from_schema=pole.SCHEMA,to_schema=ordinary.SCHEMA,unused_exception_nibbles=zero_count,
        exact_pcm_equal=True,exact_internal_counts_equal=True,pcm_sha256=hashlib.sha256(a.tobytes()).hexdigest(),
        source_parameters_unchanged=True,actual_converted_firmware_verified=False)


def zero_tail_conversion(model):
    """Remove only unused lags16..31 after two frozen exact oracle checks."""
    import q3_pulsebook32 as extended
    ordinary = load_cycles().load_search(False)
    if model['schema'] != extended.SCHEMA:
        raise ValueError('Tail trimming requires an explicitly tagged 32-tap model')
    f,d,b = np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16),np.asarray(model['pulsebook'],np.int8)
    extended.validate(f,d,b,int(d.sum()))
    if np.any(b[:,16:]):
        raise ValueError('Active 32-tap excitation tails cannot be silently removed')
    trimmed = b[:,:16].copy()
    payload = ordinary.validate(f,d,trimmed,int(d.sum()))
    nearest,tilt = bool(model.get('nearest',False)),int(model.get('tilt_shift',1))
    a,ac = extended.render(f,d,b,tilt,nearest)
    z,zc = ordinary.render(f,d,trimmed,tilt,nearest)
    if not np.array_equal(a,z) or not np.array_equal(ac,zc):
        raise AssertionError('Zero-tail conversion changed exact PCM or internal arithmetic')
    if payload != extended.validate(f,d,b,int(d.sum())):
        raise AssertionError('Zero-tail conversion changed the complete packed parameter stream')
    return dict(model,schema=ordinary.SCHEMA,pulsebook=trimmed.tolist()),dict(
        from_schema=extended.SCHEMA,to_schema=ordinary.SCHEMA,removed_table_entries=64,
        all_removed_entries_zero=True,exact_pcm_equal=True,exact_internal_counts_equal=True,
        exact_packed_stream_equal=True,pcm_sha256=hashlib.sha256(a.tobytes()).hexdigest(),
        source_frames_durations_unchanged=True,actual_converted_firmware_verified=False)


def source_variants(state,index):
    """Joint source alternatives; beam composes these across adjacent frames."""
    old = state.frames[index]
    period,gain,mode = int(old[0]),int(old[1]) & 15,int(old[1]) >> 4
    changes = {(period,gain,mode)}
    for delta in (-3,-2,-1,1,2,3):
        if period and 1 <= period+delta <= 126:
            changes.add((period+delta,gain,mode))
    for delta in (-1,1):
        if 0 <= gain+delta <= 15:
            changes.add((period,gain+delta,mode))
            for dp in (-1,1):
                if period and 1 <= period+dp <= 126:
                    changes.add((period+dp,gain+delta,mode))
    for target in range(4):
        changes.add((period,gain,target))
    for p,g,m in sorted(changes):
        f = state.frames.copy()
        f[index,0],f[index,1] = p,g|(m << 4)
        yield type(state)(f,state.durations.copy(),state.book.copy(),state.nearest,state.tilt)


def coefficient_block_seeds(state,indices,pole):
    """Correlated half-run changes may cross a rejected single-nibble barrier.

    Each selected coefficient half's entire existing reuse run is edited, so
    the fit does not pay two new coefficient bytes at each edited frame.
    """
    yield state
    first,last = indices[0],indices[-1]+1
    seen = {state_key(state)}
    for half in (2,4):
        groups = []
        for i in range(first,last):
            left,right = i,i+1
            while left and np.array_equal(state.frames[left-1,half:half+2],state.frames[i,half:half+2]):
                left -= 1
            while right < len(state.frames) and np.array_equal(state.frames[right,half:half+2],state.frames[i,half:half+2]):
                right += 1
            if (left,right) not in groups:
                groups.append((left,right))
        # Same signed direction across one or both of the low-order pair.
        for positions in ((0,),(1,),(0,1)):
            for delta in (-1,1):
                f,valid = state.frames.copy(),True
                for left,right in groups:
                    for position in positions:
                        col,shift = half+position//2,(position%2)*4
                        value = ((int(f[left,col]) >> shift) & 15)+delta
                        if not (0 if pole else 1) <= value <= 15:
                            valid = False
                            break
                        f[left:right,col] = (f[left:right,col] & (255 ^ (15 << shift)))|(value << shift)
                    if not valid:
                        break
                if valid:
                    candidate = type(state)(f,state.durations.copy(),state.book.copy(),state.nearest,state.tilt)
                    key = state_key(candidate)
                    if key not in seen:
                        seen.add(key)
                        yield candidate


def diverse_best(scored,width):
    """Keep both guide rankings; raw residual cannot erase envelope candidates."""
    if width < 2:
        raise ValueError('A dual-guide beam needs at least two states')
    unique = {}
    for score,state in scored:
        unique[state_key(state)] = score,state
    selected,seen = [],set()
    queues = [sorted(unique.values(),key=lambda item:(item[0][i],item[0][1-i],state_key(item[1]))) for i in (0,1)]
    for i in range(max(len(q) for q in queues)):
        for queue in queues:
            if i < len(queue):
                item = queue[i]
                key = state_key(item[1])
                if key not in seen:
                    selected.append(item)
                    seen.add(key)
                    if len(selected) == width:
                        return selected
    return selected


def trajectory_beam(seeds,indices,guide,*,width=6,variants=source_variants):
    """Retain paths before exact endpoint acceptance; no greedy prefix commits."""
    scored = diverse_best([(guide(seed),seed) for seed in seeds],width)
    for index in indices:
        expanded = []
        for _,state in scored:
            for candidate in variants(state,index):
                score = guide(candidate)
                if score is not None:
                    expanded.append((score,candidate))
        if not expanded:
            return []
        scored = diverse_best(expanded,width)
    return scored


def final_metrics(module,state,reference):
    pcm,counts = module.render(state.frames,state.durations,state.book,state.tilt,state.nearest)
    audio = (pcm.astype(float)-128)/128
    tracks = HarmonicTrackObjective(reference)
    details = tracks.details(audio)
    raw_tracks = copy(tracks)
    raw_tracks.matched = lambda value:sosfilt(raw_tracks.hp,np.asarray(value,dtype=float))
    raw = raw_tracks.details(audio)
    return dict(estoi=deterministic_estoi(reference,audio,7500),harmonic_metrics=details['metrics'],
        strict_5db_level_matched=check_partial_bounds(details,max_level_error_db=5.,duration_seconds=len(reference)/7500),
        strict_5db_raw=check_partial_bounds(raw,max_level_error_db=5.,duration_seconds=len(reference)/7500),
        raw_mse=float(np.mean((reference-audio)**2)))


def run(reference_path,model_path,core_report,output,*,exact_evaluations=500,beam_width=6,block_frames=4,passes=2,
        ordinary_core_report=None,trim_zero_tail=False):
    if exact_evaluations < 1 or beam_width < 2 or block_frames < 2 or passes < 1:
        raise ValueError('Expected positive finite search budget and multi-frame lookahead')
    started = time.perf_counter()
    cycles = load_cycles()
    core = cycles.load_core_profile(core_report)
    module = cycles.load_search(core['pole'])
    model = json.loads(Path(model_path).read_text(encoding='utf-8'))
    source_conversion = None
    if trim_zero_tail:
        if core['pole']:
            raise ValueError('Zero-tail conversion requires the compatible ordinary actual core')
        model,source_conversion = zero_tail_conversion(model)
    if model['schema'] != module.SCHEMA or bool(model.get('nearest',False)) != core['nearest']:
        raise ValueError('Seed schema/rounding must match the verified actual core')
    source_core,feature_selection = core,None
    if ordinary_core_report is not None:
        ordinary_core = cycles.load_core_profile(ordinary_core_report)
        if not core['pole'] or ordinary_core['pole'] or ordinary_core['nearest'] != core['nearest']:
            raise ValueError('Feature selection requires compatible pole and ordinary actual cores')
        model,feature_selection = unused_pole_conversion(model)
        core,module = ordinary_core,cycles.load_search(False)
        feature_selection.update(actual_core_bytes_freed=source_core['code_bytes']-core['code_bytes'],
            previous_stream_budget=source_core['stream_budget'],selected_stream_budget=core['stream_budget'])
    reference,sr = sf.read(reference_path,dtype='float64')
    if sr != 7500 or reference.ndim != 1 or len(reference) < 3072 or not np.all(np.isfinite(reference)):
        raise ValueError('Expected unchanged complete mono7500Hz original')
    if model.get('reference_sha256') != module.sha(reference_path):
        raise ValueError('Model and original reference SHA256 must agree')
    current = module.State(np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16),
        np.asarray(model['pulsebook'],np.int8),core['nearest'],int(model.get('tilt_shift',1)))
    objective = module.Objective(reference,stoi_target=.9,spectrum_target=.3449755536,
        floor_budget=core['stream_budget'],rounded_budget=core['stream_budget'])
    current.score = objective.evaluate(current)
    if current.score is None:
        raise ValueError('Seed fails exact full-duration arithmetic/size guards')
    output = Path(output)
    initial = current
    archive,guide_counts,history = [current],Counter(),[]
    exact,accepted,seen = 0,0,{state_key(current)}
    perceptual = PerceptualGuide(reference)
    starts,stops = frame_bounds(current.durations)
    module.export_state(output/'before',current,objective,module.sha(reference_path))
    block_order = []
    for epoch in range(passes):
        offset = (epoch*(block_frames//2))%block_frames
        blocks = [list(range(i,min(i+block_frames,len(current.frames))))
            for i in range(offset,len(current.frames)-1,block_frames)]
        if epoch % 2:
            blocks.reverse()
        for indices in blocks:
            if exact >= exact_evaluations:
                break
            block_order.append(indices)
            left,right = int(starts[indices[0]]),int(stops[indices[-1]])
            cache = {}
            def guide(candidate):
                key = state_key(candidate)
                if key in cache:
                    return cache[key]
                guide_counts['attempted'] += 1
                # Temporary source trajectories can exceed capacity by a few
                # pitch-extension bytes; only the final endpoint may be used.
                try:
                    module.validate(candidate.frames,candidate.durations,candidate.book,len(reference),core['stream_budget']+4)
                except ValueError:
                    guide_counts['layout'] += 1
                    cache[key] = None
                    return None
                pcm,counts = module.render(candidate.frames,candidate.durations,candidate.book,candidate.tilt,candidate.nearest)
                signed = pcm.astype(np.int16)-128
                if np.any(counts) or abs(signed).max() > 115 or np.any(abs(np.diff(signed)) >= 48):
                    guide_counts['arithmetic_peak_steps'] += 1
                    cache[key] = None
                    return None
                score = perceptual.evaluate(signed.astype(float)/128,left,right)
                guide_counts['valid'] += 1
                cache[key] = score
                return score
            seeds = []
            for candidate in coefficient_block_seeds(current,indices,core['pole']):
                score = guide(candidate)
                if score is not None:
                    seeds.append((score,candidate))
            if not seeds:
                continue
            # Incumbent is retained even if its cheap ranking is unfavourable.
            seeds = diverse_best(seeds,max(2,beam_width//2))
            if not any(state_key(state) == state_key(current) for _,state in seeds):
                seeds.append((guide(current),current))
            endpoints = trajectory_beam([state for _,state in seeds],indices,guide,width=beam_width)
            candidates = []
            for guide_score,candidate in endpoints:
                key = state_key(candidate)
                if key in seen:
                    continue
                seen.add(key)
                exact += 1
                candidate.score = objective.evaluate(candidate)
                if candidate.score is not None:
                    archive = module.pareto_add(archive,candidate)
                    candidates.append(candidate)
                if exact >= exact_evaluations:
                    break
            if candidates:
                best = min(candidates,key=lambda state:objective.energy(state.score))
                if objective.energy(best.score) < objective.energy(current.score)-1e-12:
                    history.append(dict(epoch=epoch,frames=indices,exact_evaluations=exact,
                        before=current.score,after=best.score,guide=list(guide(best)),
                        changed_frames=np.flatnonzero(np.any(best.frames != current.frames,axis=1)).tolist()))
                    current = best
                    accepted += 1
            print(json.dumps(dict(epoch=epoch,frames=indices,exact_evaluations=exact,accepted=accepted,
                guide_evaluations=guide_counts['valid'],stoi=current.score['stoi'],spectrum=current.score['spectrogram_loss'])),flush=True)
        if exact >= exact_evaluations:
            break
    initial_checks = final_metrics(module,initial,reference)
    selected = dict(balanced=current,stoi=max(archive,key=lambda state:state.score['stoi']),
        spectrum=min(archive,key=lambda state:state.score['spectrogram_loss']))
    finalists = {}
    for name,state in selected.items():
        # Fresh full oracle + objective rescore, not guide scores or cached PCM.
        state.score = objective.evaluate(state)
        checks = final_metrics(module,state,reference)
        exported = module.export_state(output/name,state,objective,module.sha(reference_path))
        exported.update(checks)
        exported['estoi_not_below_seed'] = bool(checks['estoi'] >= initial_checks['estoi']-1e-12)
        exported['dominates_seed_stoi_spectrum'] = bool(state.score['stoi'] >= initial.score['stoi']
            and state.score['spectrogram_loss'] <= initial.score['spectrogram_loss'])
        exported['quality_target_met'] = state.score['target_met']
        module.save(output/name/'quality.json',exported)
        finalists[name] = dict(quality=exported,memory=cycles.memory(core,state),avr_qualified=False)
    source_paths = [Path(__file__),ROOT/'tools/probe-q3-pulsebook.py',ROOT/'tools/probe-q3-pulsebook-cycles.py',
        CODEC/'q3_pulsebook.py',CODEC/'q3_pulsebook_pole.py',CODEC/'spectrogram_objective.py',
        CODEC/'harmonic_tracks.py',CODEC/'partial_bounds.py',CODEC/'hq4_speech_search.py',CODEC/'hq4_core.py']
    if source_conversion is not None:
        source_paths.append(CODEC/'q3_pulsebook32.py')
    report = dict(schema='q3-perceptual-lookahead-v1',reference_sha256=module.sha(reference_path),
        seed_sha256=module.sha(model_path),seed_model_path=Path(model_path).resolve().relative_to(ROOT).as_posix(),
        samples=len(reference),sample_rate=sr,core_profile=core,source_core_profile=source_core,
        feature_selection=feature_selection,source_conversion=source_conversion,
        initial=dict(**initial.score,**initial_checks),
        targets=dict(stoi=.9,spectrogram_loss=.3449755536),target_met=any(x['quality']['target_met'] for x in finalists.values()),
        configuration=dict(max_exact_evaluations=exact_evaluations,beam_width=beam_width,block_frames=block_frames,passes=passes,
            lpc_order=8,gamma1=.92,gamma2=.6,guide_window_samples=512,guide_hop_samples=128),
        exact_evaluations=exact,accepted_blocks=accepted,guide_evaluations=dict(guide_counts),
        block_order=block_order,history=history,finalists=finalists,pareto_points=len(archive),
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in source_paths},
        guide_policy='Two original-derived LPC-weighted rankings: complex residual energy and log-magnitude error; ranking only, no final metric substitute',
        acceptance_policy='Full unchanged decoder PCM and actual packed stream; existing absolute target scalar selects branch; tradeoffs and eSTOI/strict partial failures remain explicit',
        decoder_policy='Frozen compact profile; every trial renders the complete clip from reset with carried lattice/phase/noise/T1 states; no PCM concatenation',
        avr_policy='Actual existing core capacity evidence only; each fitted final needs separate assembled three-engine verification',
        hardware_tested=False,elapsed_seconds=time.perf_counter()-started)
    module.save(output/'report.json',report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--core-report',type=Path,required=True)
    p.add_argument('--ordinary-core-report',type=Path,help='Explicitly select a verified smaller ordinary core if the pole nibble is unused')
    p.add_argument('--trim-zero-tail',action='store_true',help='Explicitly convert a 32-tap seed only when removed lags are allzero and both exact oracles agree')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--exact-evaluations',type=int,default=500)
    p.add_argument('--beam-width',type=int,default=6)
    p.add_argument('--block-frames',type=int,default=4)
    p.add_argument('--passes',type=int,default=2)
    args = p.parse_args()
    run(args.reference,args.model,args.core_report,args.output,exact_evaluations=args.exact_evaluations,
        beam_width=args.beam_width,block_frames=args.block_frames,passes=args.passes,
        ordinary_core_report=args.ordinary_core_report,trim_zero_tail=args.trim_zero_tail)


if __name__ == '__main__':
    main()
