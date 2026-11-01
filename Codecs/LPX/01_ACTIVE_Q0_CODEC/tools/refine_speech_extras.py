"""Optional-pulse refinement using the existing exact integer replay.

This low-level phase owns no LPC/controller policy. Callers supply validated
fields, an exact prefix state and their active-extra capacity.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
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


@dataclass(frozen=True,eq=False,repr=False)
class _ExtraCheckpoint:
    _owner: object
    _epoch: int
    _covered: int
    _cursor: int
    _extras: np.ndarray
    _h: np.ndarray
    _dd: int
    _cc: int
    _ring: np.ndarray


class ExistingExtraPass:
    """Owned exact forward state for one fixed set of played P4 extras.

    Each step consumes the next initially eligible group once. Serialization
    and complete synthesis observe the current fields without moving the prefix.
    Native verification, full quality gates and publication belong to callers.
    """

    def __init__(self, reference, blob, *, max_bytes, causal_positions=False,
                 horizon=160, max_trial_evaluations=None, cpu_seconds=None):
        for value,name,low,high in ((max_bytes,'byte cap',22,65535),
                                   (horizon,'horizon',80,320)):
            if isinstance(value,bool) or not isinstance(value,Integral) or not low<=value<=high:
                raise ValueError('Unsupported '+name)
        if horizon not in (80,160,320):
            raise ValueError('Unsupported horizon')
        if (max_trial_evaluations is not None and
                (isinstance(max_trial_evaluations,bool) or not isinstance(max_trial_evaluations,Integral)
                 or not 0<=max_trial_evaluations<=10000000)):
            raise ValueError('Expected a nonnegative bounded trial limit or None')
        if not isinstance(causal_positions,bool):
            raise ValueError('Expected boolean causal_positions setting')
        CpuBudget.validate(cpu_seconds)
        ref=np.asarray(reference)
        if (ref.ndim!=1 or ref.dtype.kind not in 'iu' or
                np.any(ref < -32768) or np.any(ref > 32767)):
            raise ValueError('Expected mono PCM16 reference')
        self.original=bytes(blob)
        self._fields=compact.unpack(self.original)
        n,profile,spectra,params,pulses,self._pre,self._bright,extras=self._fields
        if profile!=4:
            raise ValueError('Existing-extra pass currently supports profile 4 only')
        if len(ref)!=n or len(self.original)>max_bytes:
            raise ValueError('Reference geometry or original complete byte cap differs')
        self.begun,self.cpu_begun=time.perf_counter(),time.process_time()
        self.budget=CpuBudget(cpu_seconds)
        self.n,self.profile=n,profile
        self.max_bytes,self.horizon=int(max_bytes),int(horizon)
        self.causal_positions=causal_positions
        self._reference=ref.astype(np.int64)
        self._pp,self._ii,self._initial=(np.asarray(x,np.int64) for x in (params,pulses,extras))
        self._working=self._initial.copy()
        self.eligible=tuple(i for i,(pos,amp) in enumerate(extras) if amp and i*40+pos<n)
        self._eligible_set=set(self.eligible)
        self.initial_active=int(np.count_nonzero(self._initial[:,1]))
        self.active=self.initial_active
        self.trial_limit=49*len(self.eligible) if max_trial_evaluations is None else int(max_trial_evaluations)
        self.atomic_bound=49 if causal_positions else 33
        vectors=[[(v<<5)+16 for v in row] for row in spectra for _ in range(2)]
        self._co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n)
        self._steps=table('scale_table.inc')
        self._zero_h=np.zeros(10,np.int64);self._zero_ring=np.zeros(256,np.int64)
        self._h=self._zero_h.copy();self._ring=self._zero_ring.copy();self._dd=self._cc=0
        self.cursor=self.covered=self.trials=self.changed=0
        self.visited=[]
        self._epoch=0
        self._counts=dict(full_synthesis_evaluations=0,serialization_calls=0,
            state_advances=0,prefix_synthesized_samples=0,snapshot_calls=0,
            snapshot_wall_seconds=0.,snapshot_cpu_seconds=0.,rollback_attempts=0,
            rollback_calls=0,rollback_state_advances=0,rollback_synthesized_samples=0,
            rollback_wall_seconds=0.,rollback_cpu_seconds=0.)

    def _advance_prefix(self, start, stop):
        _,self._h,self._dd,self._cc,self._ring=advance(
            self._co,self._pp,self._ii,self._working,self._steps,self._pre,self._bright,
            start,stop,self._h,self._dd,self._cc,self._ring)
        self._counts['state_advances']+=1
        self._counts['prefix_synthesized_samples']+=stop-start

    def step(self):
        """Consume one group; False means exhausted groups or atomic trial cap."""
        if self.covered==len(self.eligible):
            return False
        self.budget.check()
        if self.trials+self.atomic_bound>self.trial_limit:
            return False
        index=self.eligible[self.covered]
        at=index*40;end=min(self.n,at+40)
        if self.cursor<at:
            self._advance_prefix(self.cursor,at)
        old=self._working[index].copy()
        pos,amp,_,count=refit_extra_group(
            self._reference,self._co,self._pp,self._ii,self._working,self._steps,self._pre,self._bright,
            at,min(self.n,at+self.horizon),self._h,self._dd,self._cc,self._ring,
            self.active,self.initial_active,self.causal_positions)
        if int(count)>self.atomic_bound or self.trials+int(count)>self.trial_limit:
            raise AssertionError('Existing-extra atomic trial bound failed')
        self._working[index]=(pos,amp)
        self.active+=int(amp!=0)-int(old[1]!=0)
        if self.active>self.initial_active:
            raise AssertionError('Existing-extra active count increased')
        self.trials+=int(count);self.changed+=int(pos!=old[0] or amp!=old[1]);self.covered+=1
        self._advance_prefix(at,end)
        self.cursor=end
        self.visited.append(index)
        return True

    def serialize(self):
        """Return a complete bounded stream, preserving inactive/unplayed data."""
        if np.array_equal(self._working,self._initial):
            return self.original
        stream=compact.pack(self.n,self.profile,self._fields[2],self._pp,self._ii,self._pre,self._bright,
            extras=self._working.tolist(),force_extras=bool(self.original[5]&128))[0]
        self._counts['serialization_calls']+=1
        restored=compact.unpack(stream)
        if (stream[:20]!=self.original[:20] or restored[:7]!=self._fields[:7]
                or len(stream)>self.max_bytes or len(stream)>len(self.original)):
            raise AssertionError('Existing-extra frozen base/header/cap contract failed')
        for index,((pos,amp),(old_pos,old_amp)) in enumerate(zip(restored[7],self._fields[7])):
            if index not in self._eligible_set and (amp!=old_amp or amp and pos!=old_pos):
                raise AssertionError('Existing-extra pass changed an inactive or unplayed pulse')
        return stream

    def synthesize(self):
        """Return owned full PCM with no effect on the forward prefix state."""
        pcm=advance(self._co,self._pp,self._ii,self._working,self._steps,self._pre,self._bright,
            0,self.n,self._zero_h,0,0,self._zero_ring)[0]
        self._counts['full_synthesis_evaluations']+=1
        return pcm

    def snapshot(self):
        """Own the protected fields/prefix; never rewind paid group progress."""
        wall,cpu=time.perf_counter(),time.process_time()
        extras,h,ring=(a.copy() for a in (self._working,self._h,self._ring))
        for array in (extras,h,ring):
            array.flags.writeable=False
        result=_ExtraCheckpoint(self,self._epoch,self.covered,self.cursor,
            extras,h,self._dd,self._cc,ring)
        self._counts['snapshot_calls']+=1
        self._counts['snapshot_wall_seconds']+=time.perf_counter()-wall
        self._counts['snapshot_cpu_seconds']+=time.process_time()-cpu
        return result

    def rollback(self, checkpoint):
        """Restore protected rows and rebuild their state to the consumed cursor.

        Covered/visited groups, trials and attempted changes remain paid. All
        snapshots from the prior lineage become stale after a successful restore;
        callers must take a fresh snapshot before the next block. Compute replay
        before installing anything, so an arithmetic failure leaves live DSP
        state intact. Work counts include replay as a subset of prefix advances.
        """
        if not isinstance(checkpoint,_ExtraCheckpoint) or checkpoint._owner is not self:
            raise ValueError('Checkpoint belongs to another existing-extra pass')
        if checkpoint._epoch!=self._epoch:
            raise ValueError('Stale existing-extra checkpoint')
        if checkpoint._covered>self.covered or checkpoint._cursor>self.cursor:
            raise ValueError('Checkpoint is ahead of the consumed prefix')
        wall,cpu=time.perf_counter(),time.process_time()
        self._counts['rollback_attempts']+=1
        try:
            working=checkpoint._extras.copy()
            h,ring=checkpoint._h.copy(),checkpoint._ring.copy()
            dd,cc=checkpoint._dd,checkpoint._cc
            samples=self.cursor-checkpoint._cursor
            if samples:
                _,h,dd,cc,ring=advance(self._co,self._pp,self._ii,working,self._steps,
                    self._pre,self._bright,checkpoint._cursor,self.cursor,h,dd,cc,ring)
            self._working[:]=working
            self._h,self._dd,self._cc,self._ring=h,dd,cc,ring
            self.active=int(np.count_nonzero(self._working[:,1]))
            self._epoch+=1
            self._counts['rollback_calls']+=1
            if samples:
                self._counts['rollback_state_advances']+=1
                self._counts['rollback_synthesized_samples']+=samples
                self._counts['state_advances']+=1
                self._counts['prefix_synthesized_samples']+=samples
        finally:
            self._counts['rollback_wall_seconds']+=time.perf_counter()-wall
            self._counts['rollback_cpu_seconds']+=time.process_time()-cpu

    @property
    def committed_changed_groups(self):
        """Current meaningful field differences, separate from attempted edits."""
        return int(sum(self._working[i,1]!=self._initial[i,1] or
            bool(self._working[i,1]) and self._working[i,0]!=self._initial[i,0]
            for i in self.eligible))

    def work_counts(self):
        return dict(self._counts)


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
    if (isinstance(max_checkpoints,bool) or not isinstance(max_checkpoints,Integral)
            or not 1<=max_checkpoints<=16):
        raise ValueError('Unsupported checkpoint count')
    max_checkpoints=int(max_checkpoints)
    if not isinstance(speech,bool):
        raise ValueError('Expected boolean speech setting')
    if decoder is None or candidate_sink is not None and not callable(candidate_sink):
        raise ValueError('Expected a native decoder and optional callable candidate sink')
    walk=ExistingExtraPass(reference,blob,max_bytes=max_bytes,causal_positions=causal_positions,
        horizon=horizon,max_trial_evaluations=max_trial_evaluations,cpu_seconds=cpu_seconds)
    ref=np.asarray(reference)
    original,n,profile=walk.original,walk.n,walk.profile
    max_bytes,horizon=walk.max_bytes,walk.horizon
    begun,cpu_begun,budget=walk.begun,walk.cpu_begun,walk.budget
    reference64=ref.astype(np.int64)
    eligible=walk.eligible
    baseline_pcm=walk.synthesize()
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
    def publish(label,covered,stop_sample):
        stream=walk.serialize()
        if stream==original:
            return remember(original,baseline_pcm,label,covered,stop_sample)
        if stream in by_stream:
            return remember(stream,catalogue[by_stream[stream]]['pcm'],label,covered,stop_sample)
        pcm=walk.synthesize()
        return remember(stream,pcm,label,covered,stop_sample)

    goals=[(len(eligible)*slot+max_checkpoints-1)//max_checkpoints
           for slot in range(1,max_checkpoints+1)]
    checkpoints={};covered=0
    last_identifier=last_published_coverage=0
    stopped_by='complete'
    if not eligible:
        stopped_by='no_active_played_extras'
    elif not baseline_sse:
        stopped_by='zero_error'
    else:
        for index in eligible:
            try:
                stepped=walk.step()
            except CpuBudgetExceeded:
                stopped_by='cpu_limit';break
            if not stepped:
                stopped_by='trial_limit';break
            covered=walk.covered
            due=[slot for slot,goal in enumerate(goals,1) if goal==covered]
            if due:
                last_identifier=publish('checkpoint-'+str(due[0]),covered,walk.cursor)
                last_published_coverage=covered
                for slot in due:
                    if 'checkpoint-'+str(slot) not in catalogue[last_identifier]['labels']:
                        catalogue[last_identifier]['labels'].append('checkpoint-'+str(slot))
                    checkpoints[slot]=dict(slot=slot,target_active_groups=goals[slot-1],
                        completed_active_groups=covered,candidate_id=last_identifier,status='complete')
    budget.finish_search()
    if covered>last_published_coverage:
        last_identifier=publish('interrupted-final',covered,walk.cursor)
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
    counts=walk.work_counts()
    for name in ('full_synthesis_evaluations','serialization_calls',
                 'state_advances','prefix_synthesized_samples'):
        counters[name]=counts[name]
    report=dict(proposal='compact_existing_extra_pass',samples=n,profile=profile,
        baseline_bytes=len(original),max_file_bytes=int(max_bytes),file_bytes=selected['file_bytes'],
        raw_file_bytes=raw['file_bytes'],selected_id=selected['id'],raw_id=raw['id'],
        baseline=deepcopy(metrics[0]),selected=deepcopy(metrics[selected['id']]),
        raw_best=deepcopy(metrics[raw['id']]),
        causal_positions=causal_positions,horizon=int(horizon),max_checkpoints=int(max_checkpoints),
        max_trial_evaluations=walk.trial_limit,atomic_trial_bound=walk.atomic_bound,trial_evaluations=walk.trials,
        initial_active_extras=walk.initial_active,eligible_active_groups=len(eligible),
        preserved_unplayed_extras=walk.initial_active-len(eligible),completed_active_groups=covered,
        eligible_group_indices=list(eligible),visited_group_indices=list(walk.visited),
        all_eligible_groups_visited=tuple(walk.visited)==eligible,changed_active_groups=walk.changed,
        working_active_extras=walk.active,stopped_by=stopped_by,
        checkpoints=[checkpoints[slot] for slot in sorted(checkpoints)],candidates=public,
        candidate_sink_streams=len(catalogue) if candidate_sink is not None else 0,
        frozen_base_header_exact=True,inactive_unplayed_pulses_preserved=True,
        native_model_pwm_exact=True,quality_kind='speech' if speech else 'non-speech-numerical',
        selection_scope='PCM/PWM SSE/STOI only; caller must apply whole-chain voice/noise/period/clipping gates',
        cpu_budget=budget.report(),validation=counters,
        seconds=time.perf_counter()-begun,cpu_seconds=time.process_time()-cpu_begun)
    return selected['stream'],selected['pcm'].copy(),report,raw['stream']
