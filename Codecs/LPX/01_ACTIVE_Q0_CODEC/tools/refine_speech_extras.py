"""Optional-pulse refinement using the existing exact integer replay.

This low-level phase owns no LPC/controller policy. Callers supply validated
fields, an exact prefix state and their active-extra capacity.
"""
from __future__ import annotations

from copy import deepcopy
from numbers import Integral
import time

import numpy as np
from numba import njit

from enhance_speech_compact import advance, sse
from q0_model import coefficient_trace, table
from refine_speech_compact import no_regression, quality
from search_cpu_budget import CpuBudget, CpuBudgetExceeded
import speech_compact as compact
from standard_metrics import pwm_duties
from wav_lpc import pack_frames


@njit(cache=True)
def refit_extra_group(reference, co, params, pulses, extras, steps, pre, bright,
                      at, stop, hist, dd, cc, ring, active_count, capacity,
                      causal_positions=False):
    """Return position, amplitude, local SSE and trials for one 40-sample group.

    Preserve the cheap refitter's candidate order, strict-improvement ties and
    amplitude rule. The caller-owned extras array is temporary trial storage;
    its original row is restored before normal return. No other field changes.
    Explicit causal_positions also tests the two actual mandatory locations;
    it does not widen the legacy amplitude set or change the default policy.
    """
    index = at//40
    original = extras[index].copy()
    best = original.copy()
    target = reference[at:stop]
    out, _, _, _, _ = advance(co, params, pulses, extras, steps, pre, bright,
                              at, stop, hist, dd, cc, ring)
    loss = sse(target, out)
    evaluations = 1
    valid = min(40, len(reference)-at)
    positions = np.zeros(40, np.uint8)
    peak, peak_error = 0, -1
    for j in range(valid):
        error = abs(np.int64(target[j])-np.int64(out[j]))
        if error > peak_error:
            peak_error, peak = error, j
    positions[peak] = 1
    if original[1]:
        for delta in (-1, 0, 1):
            pos = original[0]+delta
            if 0 <= pos < valid:
                positions[pos] = 1
    if causal_positions:
        for half in range(2):
            pos = half*20+pulses[at//20+half, 0]
            if 0 <= pos < valid:
                positions[pos] = 1
    for pos in range(valid):
        if not positions[pos]:
            continue
        for amp in range(-8, 8):
            if not (amp in (-4, -2, 0, 2, 4) or abs(amp-original[1]) <= 1):
                continue
            if amp and not original[1] and active_count >= capacity:
                continue
            extras[index, 0] = pos if amp else -1
            extras[index, 1] = amp
            trialout, _, _, _, _ = advance(co, params, pulses, extras, steps, pre, bright,
                                          at, stop, hist, dd, cc, ring)
            trial = sse(target, trialout)
            evaluations += 1
            if trial < loss:
                loss, best = trial, extras[index].copy()
    extras[index] = original
    return best[0], best[1], loss, evaluations


def refine_existing_extras(reference, blob, decoder, *, max_bytes,
                           causal_positions=False, horizon=160,
                           max_trial_evaluations=None, cpu_seconds=None,
                           max_checkpoints=4, candidate_sink=None, speech=True):
    """Refine initially active played P4 extras; return selected/PCM/report/raw.

    Spectra, parameters, mandatory pulses, the first 20 header bytes, inactive
    slots and unplayed pulses remain fixed. No extra can be added. The working
    forward pass is independent of the retained best complete checkpoints.
    Sink receives each distinct native/model-verified (stream, full PCM SSE)
    before another quota check. Local PCM/PWM/STOI selection here still needs
    the caller's whole-chain period, clipping and joint voice/noise admission.
    """
    for value,name,low,high in ((max_bytes,'byte cap',22,65535),
                               (horizon,'horizon',80,320),
                               (max_checkpoints,'checkpoint count',1,16)):
        if isinstance(value,bool) or not isinstance(value,Integral) or not low<=value<=high:
            raise ValueError('Unsupported '+name)
    if horizon not in (80,160,320):
        raise ValueError('Unsupported horizon')
    max_bytes,horizon,max_checkpoints=map(int,(max_bytes,horizon,max_checkpoints))
    if (max_trial_evaluations is not None and
            (isinstance(max_trial_evaluations,bool) or not isinstance(max_trial_evaluations,Integral)
             or not 0<=max_trial_evaluations<=10000000)):
        raise ValueError('Expected a nonnegative bounded trial limit or None')
    if not isinstance(causal_positions,bool) or not isinstance(speech,bool):
        raise ValueError('Expected boolean causal_positions and speech settings')
    if decoder is None or candidate_sink is not None and not callable(candidate_sink):
        raise ValueError('Expected a native decoder and optional callable candidate sink')
    CpuBudget.validate(cpu_seconds)
    ref=np.asarray(reference)
    if (ref.ndim!=1 or ref.dtype.kind not in 'iu' or
            np.any(ref < -32768) or np.any(ref > 32767)):
        raise ValueError('Expected mono PCM16 reference')
    original=bytes(blob)
    fields=compact.unpack(original)
    n,profile,spectra,params,pulses,pre,bright,extras=fields
    if profile!=4:
        raise ValueError('Existing-extra pass currently supports profile 4 only')
    if len(ref)!=n or len(original)>max_bytes:
        raise ValueError('Reference geometry or original complete byte cap differs')

    begun,cpu_begun=time.perf_counter(),time.process_time()
    budget=CpuBudget(cpu_seconds)
    reference64=ref.astype(np.int64)
    pp,ii,initial=(np.asarray(x,np.int64) for x in (params,pulses,extras))
    working=initial.copy()
    eligible=[i for i,(pos,amp) in enumerate(extras) if amp and i*40+pos<n]
    initial_active=int(np.count_nonzero(initial[:,1]))
    active=initial_active
    trial_limit=49*len(eligible) if max_trial_evaluations is None else int(max_trial_evaluations)
    atomic_bound=49 if causal_positions else 33
    vectors=[[(v<<5)+16 for v in row] for row in spectra for _ in range(2)]
    co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n)
    steps=table('scale_table.inc')
    zero_h=np.zeros(10,np.int64);zero_ring=np.zeros(256,np.int64)
    baseline_pcm=advance(co,pp,ii,initial,steps,pre,bright,0,n,zero_h,0,0,zero_ring)[0]
    counters=dict(full_synthesis_evaluations=1,independent_model_checks=0,
                  native_output_domain_comparisons=0,serialization_calls=0,
                  state_advances=0,prefix_synthesized_samples=0)
    catalogue=[];by_stream={}

    def verify(stream,pcm):
        actual=decoder.decode_one_s16(stream,n)
        duty=decoder.decode_one(stream,n)
        model=compact.decode_model(stream)
        if (actual is None or duty is None or not np.array_equal(actual,pcm)
                or not np.array_equal(duty,pwm_duties(pcm)) or not np.array_equal(model,pcm)):
            raise AssertionError('Existing-extra native/model PCM/PWM mismatch')
        counters['independent_model_checks']+=1
        counters['native_output_domain_comparisons']+=2

    def remember(stream,pcm,label,covered,stop_sample):
        if stream in by_stream:
            identifier=by_stream[stream]
            if label not in catalogue[identifier]['labels']:
                catalogue[identifier]['labels'].append(label)
            return identifier
        verify(stream,pcm)
        identifier=len(catalogue)
        point=dict(id=identifier,stream=stream,pcm=pcm.copy(),file_bytes=len(stream),
            full_sse=int(sse(reference64,pcm)),labels=[label],
            completed_active_groups=covered,stop_sample=stop_sample)
        catalogue.append(point);by_stream[stream]=identifier
        if candidate_sink is not None:
            candidate_sink(stream,point['full_sse'])
        return identifier

    remember(original,baseline_pcm,'baseline',0,0)
    baseline_sse=catalogue[0]['full_sse']
    eligible_set=set(eligible)

    def publish(label,covered,stop_sample):
        if np.array_equal(working,initial):
            return remember(original,baseline_pcm,label,covered,stop_sample)
        stream=compact.pack(n,profile,spectra,pp,ii,pre,bright,extras=working.tolist(),
                            force_extras=bool(original[5]&128))[0]
        counters['serialization_calls']+=1
        restored=compact.unpack(stream)
        if (stream[:20]!=original[:20] or restored[:7]!=fields[:7]
                or len(stream)>max_bytes or len(stream)>len(original)):
            raise AssertionError('Existing-extra frozen base/header/cap contract failed')
        for index,((pos,amp),(old_pos,old_amp)) in enumerate(zip(restored[7],extras)):
            if index not in eligible_set and (amp!=old_amp or amp and pos!=old_pos):
                raise AssertionError('Existing-extra pass changed an inactive or unplayed pulse')
        if stream in by_stream:
            return remember(stream,catalogue[by_stream[stream]]['pcm'],label,covered,stop_sample)
        pcm=advance(co,pp,ii,working,steps,pre,bright,0,n,zero_h,0,0,zero_ring)[0]
        counters['full_synthesis_evaluations']+=1
        return remember(stream,pcm,label,covered,stop_sample)

    goals=[(len(eligible)*slot+max_checkpoints-1)//max_checkpoints
           for slot in range(1,max_checkpoints+1)]
    checkpoints={};visited=[];covered=trials=changed=0
    cursor=0;h=zero_h.copy();ring=zero_ring.copy();dd=cc=0
    last_identifier=last_published_coverage=0
    stopped_by='complete'
    if not eligible:
        stopped_by='no_active_played_extras'
    elif not baseline_sse:
        stopped_by='zero_error'
    else:
        for index in eligible:
            try:
                budget.check()
            except CpuBudgetExceeded:
                stopped_by='cpu_limit';break
            if trials+atomic_bound>trial_limit:
                stopped_by='trial_limit';break
            at=index*40;end=min(n,at+40)
            if cursor<at:
                _,h,dd,cc,ring=advance(co,pp,ii,working,steps,pre,bright,
                                      cursor,at,h,dd,cc,ring)
                counters['state_advances']+=1
                counters['prefix_synthesized_samples']+=at-cursor
            old=working[index].copy()
            pos,amp,_,count=refit_extra_group(reference64,co,pp,ii,working,steps,pre,bright,
                at,min(n,at+horizon),h,dd,cc,ring,active,initial_active,causal_positions)
            if int(count)>atomic_bound or trials+int(count)>trial_limit:
                raise AssertionError('Existing-extra atomic trial bound failed')
            working[index]=(pos,amp)
            active+=int(amp!=0)-int(old[1]!=0)
            if active>initial_active:
                raise AssertionError('Existing-extra active count increased')
            trials+=int(count);changed+=int(pos!=old[0] or amp!=old[1]);covered+=1
            _,h,dd,cc,ring=advance(co,pp,ii,working,steps,pre,bright,at,end,h,dd,cc,ring)
            counters['state_advances']+=1
            counters['prefix_synthesized_samples']+=end-at
            cursor=end
            visited.append(index)
            due=[slot for slot,goal in enumerate(goals,1) if goal==covered]
            if due:
                last_identifier=publish('checkpoint-'+str(due[0]),covered,cursor)
                last_published_coverage=covered
                for slot in due:
                    if 'checkpoint-'+str(slot) not in catalogue[last_identifier]['labels']:
                        catalogue[last_identifier]['labels'].append('checkpoint-'+str(slot))
                    checkpoints[slot]=dict(slot=slot,target_active_groups=goals[slot-1],
                        completed_active_groups=covered,candidate_id=last_identifier,status='complete')
    budget.finish_search()
    if covered>last_published_coverage:
        last_identifier=publish('interrupted-final',covered,cursor)
    for slot,goal in enumerate(goals,1):
        if slot not in checkpoints:
            checkpoints[slot]=dict(slot=slot,target_active_groups=goal,
                completed_active_groups=covered,candidate_id=last_identifier,
                status='no_work' if not eligible or not baseline_sse else 'partial_fallback')

    metrics=[quality(ref,point['pcm'],speech=speech) for point in catalogue]
    rank=lambda point:(point['full_sse'],point['file_bytes'],point['id'])
    raw=min(catalogue,key=rank)
    allowed=[point for point in catalogue if point['id']==0 or no_regression(metrics[point['id']],metrics[0])]
    selected=min(allowed,key=rank)
    for identifier in {0,selected['id'],raw['id']}:
        verify(catalogue[identifier]['stream'],catalogue[identifier]['pcm'])
    public=[]
    for point in catalogue:
        public.append(dict(**{key:deepcopy(value) for key,value in point.items() if key not in ('stream','pcm')},
            metrics=deepcopy(metrics[point['id']]),conservative_floors_passed=bool(point['id']==0 or
                no_regression(metrics[point['id']],metrics[0]))))
    report=dict(proposal='compact_existing_extra_pass',samples=n,profile=profile,
        baseline_bytes=len(original),max_file_bytes=int(max_bytes),file_bytes=selected['file_bytes'],
        raw_file_bytes=raw['file_bytes'],selected_id=selected['id'],raw_id=raw['id'],
        baseline=deepcopy(metrics[0]),selected=deepcopy(metrics[selected['id']]),
        raw_best=deepcopy(metrics[raw['id']]),
        causal_positions=causal_positions,horizon=int(horizon),max_checkpoints=int(max_checkpoints),
        max_trial_evaluations=trial_limit,atomic_trial_bound=atomic_bound,trial_evaluations=trials,
        initial_active_extras=initial_active,eligible_active_groups=len(eligible),
        preserved_unplayed_extras=initial_active-len(eligible),completed_active_groups=covered,
        eligible_group_indices=list(eligible),visited_group_indices=list(visited),
        all_eligible_groups_visited=visited==eligible,changed_active_groups=changed,
        working_active_extras=active,stopped_by=stopped_by,
        checkpoints=[checkpoints[slot] for slot in sorted(checkpoints)],candidates=public,
        candidate_sink_streams=len(catalogue) if candidate_sink is not None else 0,
        frozen_base_header_exact=True,inactive_unplayed_pulses_preserved=True,
        native_model_pwm_exact=True,quality_kind='speech' if speech else 'non-speech-numerical',
        selection_scope='PCM/PWM SSE/STOI only; caller must apply whole-chain voice/noise/period/clipping gates',
        cpu_budget=budget.report(),validation=counters,
        seconds=time.perf_counter()-begun,cpu_seconds=time.process_time()-cpu_begun)
    return selected['stream'],selected['pcm'].copy(),report,raw['stream']
