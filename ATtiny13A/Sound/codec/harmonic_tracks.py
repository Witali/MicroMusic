"""Automatic strongest-partial trajectories for same-time speech fitting.

Local peaks are ranked by amplitude, not assigned to F0 multiples. The 1024
point Hann STFT has a 128-sample hop. Log-parabolic interpolation estimates
sub-bin frequency and amplitude. IDs follow predicted frequency through rank
swaps, short gaps and resolvable crossings; IDs never refer to rank positions.
This is an offline fitting diagnostic, not a perceptual quality standard.
"""
from copy import copy
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.signal import butter, sosfilt, stft


VERSION = 'strongest-partial-tracks-v1'


def _weighted_percentile(values, weights, fraction=.95):
    if not values:
        return 0.
    values,weights = np.asarray(values),np.asarray(weights)
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    return float(values[order[min(len(order)-1,int(np.searchsorted(cumulative,cumulative[-1]*fraction)))]] )


def _audio(value, samples=None):
    value = np.asarray(value,dtype=np.float64)
    if (value.ndim != 1 or len(value) < 1024 or not np.all(np.isfinite(value))
            or (samples is not None and len(value) != samples)):
        raise ValueError('Expected finite mono audio of unchanged duration, at least 1024 samples')
    return value


def _associate(frequencies, amplitudes, hop_seconds, bin_hz, max_gap):
    """Frequency prediction keeps IDs independent of changing amplitude rank."""
    ids = np.full(frequencies.shape,-1,dtype=np.int64)
    active, next_id = {}, 0
    for frame in range(len(frequencies)):
        indices = np.flatnonzero(amplitudes[frame] > 0)
        active = {key:state for key,state in active.items() if frame-state[0] <= max_gap+1}
        keys = sorted(active)
        assigned = {}
        if keys and len(indices):
            states = np.asarray([active[key] for key in keys],dtype=float)
            elapsed = (frame-states[:,0])*hop_seconds
            predicted = states[:,1]+states[:,3]*elapsed
            tolerance = np.maximum(3*bin_hz,abs(predicted)*.035)
            # A gap increases uncertainty while preserving a bounded gate.
            tolerance += np.maximum(0.,elapsed-hop_seconds)*bin_hz/hop_seconds*.35
            distance = abs(predicted[:,None]-frequencies[frame,indices][None,:])/tolerance[:,None]
            levels = abs(np.log(np.maximum(amplitudes[frame,indices][None,:],1e-20)/
                                np.maximum(states[:,2,None],1e-20)))
            cost = distance+.08*np.minimum(levels,5)
            cost[distance > 2.5] = 1e6
            # A dummy permits an old track to remain absent instead of jumping
            # to an unrelated new partial, even when counts happen to agree.
            rows,cols = linear_sum_assignment(np.c_[cost,np.full((len(keys),len(keys)),2.6)])
            for row,col in zip(rows,cols):
                if col < len(indices) and cost[row,col] < 2.6:
                    assigned[int(indices[col])] = keys[row]
        for index in indices:
            index = int(index)
            if index in assigned:
                key = assigned[index]
                last,frequency,amplitude,velocity = active[key]
                observed = (frequencies[frame,index]-frequency)/((frame-last)*hop_seconds)
                velocity = .65*observed+.35*velocity
            else:
                key,velocity = next_id,0.
                next_id += 1
            active[key] = (frame,float(frequencies[frame,index]),float(amplitudes[frame,index]),float(velocity))
            ids[frame,index] = key
    return ids


class HarmonicTrackObjective:
    """Cache <=10 strongest original partials and compare candidate tracks.

    Both signals get the same 70 Hz highpass and a single global RMS match.
    Silence has no RMS normalization; a nonzero candidate against silent
    reference is therefore penalized, rather than scaled away.

    ``evaluate`` returns only finite scalars. Frequency trajectory loss is 75%
    tolerance-normalized matched error plus 25% change-of-error over time
    for the same reference/candidate IDs. Level loss is normalized by the
    amplitude tolerance. Absolute weighted mean and p95 cents/Hz/dB remain
    separate and unchanged by tolerance configuration. They can enforce actual
    rate-control bounds; a lower normalized loss alone never proves a bound.
    Missing/extra energy and match rate are power weighted fractions. Matching
    is one-to-one at each unchanged time, with bounded frequency tolerance.
    IDs add a continuity preference and determine the trajectory comparison;
    they never permit matching a peak at a different time.
    """
    def __init__(self, reference, sr=7500, max_tracks=10, *, n_fft=1024, hop=128, max_gap=8,
                 frequency_tolerance_cents=50.,frequency_tolerance_hz=0.,amplitude_tolerance_db=3.):
        self.reference = _audio(reference)
        if (sr != 7500 or not 1 <= max_tracks <= 10 or n_fft < 1024
                or n_fft > len(self.reference) or not 1 <= hop <= n_fft or max_gap < 0):
            raise ValueError('Expected 7500 Hz, 1..10 tracks, FFT >=1024, and valid hop/gap')
        self.sr,self.max_tracks,self.n_fft,self.hop,self.max_gap = sr,int(max_tracks),int(n_fft),int(hop),int(max_gap)
        self.bin_hz = sr/n_fft
        self.hp = butter(2,70,fs=sr,btype='highpass',output='sos')
        self.filtered = sosfilt(self.hp,self.reference)
        self.rms = float(np.sqrt(np.mean(self.filtered**2)))
        self.amplitude_floor = max(self.rms*1e-3,1e-12)
        self.reference_tracks = self._extract(self.filtered)
        self.reference_energy = float(np.sum(self.reference_tracks['amplitude']**2))
        self._tolerances(frequency_tolerance_cents,frequency_tolerance_hz,amplitude_tolerance_db)

    def _tolerances(self, cents, hz, db):
        if not np.all(np.isfinite([cents,hz,db])) or cents <= 0 or hz < 0 or db <= 0:
            raise ValueError('Frequency cents/amplitude dB tolerances must be positive; Hz floor nonnegative')
        self.frequency_tolerance_cents = float(cents)
        self.frequency_tolerance_hz = float(hz)
        self.amplitude_tolerance_db = float(db)
        self.config = dict(version=VERSION,max_tracks=self.max_tracks,n_fft=self.n_fft,hop=self.hop,
            max_gap=self.max_gap,frequency_tolerance_cents=float(cents),
            frequency_tolerance_hz=float(hz),amplitude_tolerance_db=float(db),
            matching_gate_cents=100.,matching_gate_floor_hz=2*self.bin_hz)

    def with_tolerances(self, *, frequency_tolerance_cents=None,frequency_tolerance_hz=None,
                        amplitude_tolerance_db=None):
        """Reuse the frozen reference tracks with a different loss tolerance.

        Matching gates are deliberately independent of these tolerances, so a
        looser tolerance cannot relabel missing/extra energy as a valid match.
        """
        result = copy(self)
        result._tolerances(self.frequency_tolerance_cents if frequency_tolerance_cents is None else frequency_tolerance_cents,
            self.frequency_tolerance_hz if frequency_tolerance_hz is None else frequency_tolerance_hz,
            self.amplitude_tolerance_db if amplitude_tolerance_db is None else amplitude_tolerance_db)
        return result

    def matched(self, candidate):
        candidate = sosfilt(self.hp,_audio(candidate,len(self.reference)))
        rms = float(np.sqrt(np.mean(candidate**2)))
        if self.rms > 1e-12 and rms > 1e-15:
            candidate *= self.rms/rms
        return candidate

    def _extract(self, filtered):
        bins,times,z = stft(filtered,fs=self.sr,window='hann',nperseg=self.n_fft,
                            noverlap=self.n_fft-self.hop,boundary='zeros',padded=True)
        magnitude = abs(z)
        frame_count = magnitude.shape[1]
        frequencies = np.full((frame_count,self.max_tracks),np.nan)
        amplitudes = np.zeros_like(frequencies)
        candidates = ((magnitude[1:-1] > magnitude[:-2]) &
                      (magnitude[1:-1] >= magnitude[2:]) &
                      (bins[1:-1,None] >= 70))
        for frame in range(frame_count):
            indices = np.flatnonzero(candidates[:,frame])+1
            if not len(indices):
                continue
            # An absolute floor is tied to the ORIGINAL global level. The
            # relative floor only removes numerical/sidelobe peaks far below
            # the strongest peak, not the weaker first N harmonics of an F0.
            floor = max(self.amplitude_floor/2,float(magnitude[:,frame].max())*1e-4)
            indices = indices[magnitude[indices,frame] > floor]
            if not len(indices):
                continue
            order = np.argsort(-magnitude[indices,frame],kind='stable')[:self.max_tracks]
            indices = indices[order]
            left,centre,right = np.log(np.maximum(magnitude[np.stack((indices-1,indices,indices+1)),frame],1e-30))
            curvature = left-2*centre+right
            offset = np.clip(.5*(left-right)/np.minimum(curvature,-1e-20),-.5,.5)
            frequency = (indices+offset)*self.bin_hz
            amplitude = 2*np.exp(centre-.25*(left-right)*offset)
            frequencies[frame,:len(indices)] = frequency
            amplitudes[frame,:len(indices)] = amplitude
        ids = _associate(frequencies,amplitudes,self.hop/self.sr,self.bin_hz,self.max_gap)
        return dict(times=times,frequency_hz=frequencies,amplitude=amplitudes,
                    track_id=ids,count=np.sum(amplitudes>0,axis=1))

    def extract(self, candidate):
        """Return matched-level times and frame-by-rank arrays; absent IDs=-1."""
        return self._extract(self.matched(candidate))

    def _compare(self, candidate, include_matches):
        target = self.reference_tracks
        output = self.extract(candidate)
        target_total = self.reference_energy
        output_total = float(np.sum(output['amplitude']**2))
        matched_energy = missing_energy = extra_energy = 0.
        frequency_sum = level_sum = trajectory_sum = trajectory_weight = 0.
        cents_sum = hz_sum = db_sum = 0.
        absolute_cents,absolute_hz,absolute_db,energy_weights = [],[],[],[]
        previous_mapping,previous_reference = {},{}
        continuity_breaks = continuity_weight = 0.
        matches = []
        for frame in range(len(target['times'])):
            ri = np.flatnonzero(target['amplitude'][frame] > 0)
            ci = np.flatnonzero(output['amplitude'][frame] > 0)
            ra,ca = target['amplitude'][frame,ri],output['amplitude'][frame,ci]
            rf,cf = target['frequency_hz'][frame,ri],output['frequency_hz'][frame,ci]
            paired_r,paired_c = set(),set()
            if len(ri) and len(ci):
                # One semitone, with a two-bin floor for low frequencies.
                # Octave/half-frequency replacements cannot satisfy a track.
                tolerance = np.maximum(2*self.bin_hz,rf*(2**(100/1200)-1))
                distance = abs(rf[:,None]-cf[None,:])/tolerance[:,None]
                db = abs(20*np.log10(np.maximum(ca[None,:],1e-20)/np.maximum(ra[:,None],1e-20)))
                cost = distance**2+.15*np.minimum(db/20,2)
                for col,index in enumerate(ci):
                    cid = int(output['track_id'][frame,index])
                    old = previous_mapping.get(cid)
                    if old is not None and frame-old[1] <= self.max_gap+1:
                        cost[:,col] += .15*(target['track_id'][frame,ri] != old[0])
                cost[distance > 1] = 1e6
                rows,cols = linear_sum_assignment(np.c_[cost,np.full((len(ri),len(ri)),1.5)])
                for row,col in zip(rows,cols):
                    if col >= len(ci) or cost[row,col] >= 1.5:
                        continue
                    paired_r.add(int(row));paired_c.add(int(col))
                    rid = int(target['track_id'][frame,ri[row]])
                    cid = int(output['track_id'][frame,ci[col]])
                    energy = float(ra[row]**2)
                    error_cents = float(1200*np.log2(cf[col]/rf[row]))
                    hz_error = float(abs(cf[col]-rf[row]))
                    local_tolerance = max(self.frequency_tolerance_cents,
                        1200*np.log2((rf[row]+self.frequency_tolerance_hz)/rf[row]))
                    error = error_cents/local_tolerance
                    matched_energy += energy
                    frequency_sum += energy*abs(error)
                    db_error = float(db[row,col])
                    level_sum += energy*db_error/self.amplitude_tolerance_db
                    cents_sum += energy*abs(error_cents)
                    hz_sum += energy*hz_error
                    db_sum += energy*db_error
                    absolute_cents.append(abs(error_cents));absolute_hz.append(hz_error)
                    absolute_db.append(db_error);energy_weights.append(energy)
                    # Follow the SAME reference ID even if the candidate
                    # fragmented. A new candidate ID cannot erase a jump.
                    old = previous_reference.get(rid)
                    if old is not None and frame-old[0] <= self.max_gap+1:
                        trajectory_sum += energy*abs(error-old[1])/(frame-old[0])
                        trajectory_weight += energy
                        continuity_weight += energy
                        continuity_breaks += energy*int(cid != old[2])
                    previous_reference[rid] = (frame,error,cid)
                    previous_mapping[cid] = (rid,frame)
                    if include_matches:
                        matches.append(dict(frame=frame,time_seconds=float(target['times'][frame]),
                            reference_id=rid,candidate_id=cid,reference_hz=float(rf[row]),
                            candidate_hz=float(cf[col]),reference_amplitude=float(ra[row]),
                            candidate_amplitude=float(ca[col]),frequency_error_cents=error_cents,
                            frequency_error_hz=hz_error,level_error_db=db_error,reference_energy=energy))
            missing_energy += sum(float(ra[index]**2) for index in range(len(ri)) if index not in paired_r)
            extra_energy += sum(float(ca[index]**2) for index in range(len(ci)) if index not in paired_c)
        frequency = frequency_sum/max(matched_energy,1e-30)
        trajectory = trajectory_sum/max(trajectory_weight,1e-30)
        frequency_error = .75*frequency+.25*trajectory
        level_error = level_sum/max(matched_energy,1e-30)
        missing = missing_energy/max(target_total,1e-30)
        extra = extra_energy/max(target_total,output_total,1e-30)
        match_rate = matched_energy/target_total if target_total > 1e-30 else float(output_total <= 1e-30)
        break_rate = continuity_breaks/max(continuity_weight,1e-30)
        result = dict(harmonic_track_loss=.35*frequency_error+.2*level_error+.3*missing+.15*extra+.05*break_rate,
                      frequency_trajectory_error=frequency_error,level_error=level_error,
                      missing_reference_energy=missing,extra_candidate_energy=extra,
                      weighted_match_rate=match_rate,
                      frequency_error_cents=cents_sum/max(matched_energy,1e-30),
                      frequency_error_hz=hz_sum/max(matched_energy,1e-30),
                      level_error_db=db_sum/max(matched_energy,1e-30),
                      frequency_error_p95_cents=_weighted_percentile(absolute_cents,energy_weights),
                      frequency_error_p95_hz=_weighted_percentile(absolute_hz,energy_weights),
                      level_error_p95_db=_weighted_percentile(absolute_db,energy_weights))
        result['continuity_break_rate'] = break_rate
        if not all(np.isfinite(value) for value in result.values()):
            raise AssertionError('Non-finite harmonic tracking metric')
        return result,output,matches

    def evaluate(self, candidate):
        return self._compare(candidate,False)[0]

    def details(self, candidate):
        result,output,matches = self._compare(candidate,True)
        return dict(metrics=result,reference_tracks=self.reference_tracks,
                    candidate_tracks=output,matches=matches)
