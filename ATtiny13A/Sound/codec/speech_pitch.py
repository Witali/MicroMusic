"""Optional single-speaker F0 prior, estimated from persistent periodic runs.

The prior is encoder analysis only. Short attacks cannot establish the voice
pitch; selected attacks stay unvoiced. This is an acoustic heuristic, not a
semantic speech/effects classifier, and never assigns manual clip timestamps.
"""
import numpy as np
from scipy.signal import butter,sosfilt

from period_wave import SR,HOP,track_pitch


def track_speech_pitch(audio,sr=SR,hop=HOP,window=256,prior_weight=.35,
                       onset_ratio=2.5,onset_hold_frames=4,min_periodicity=.55,
                       min_stability=.7,min_run_ms=80.):
    if (prior_weight<0 or onset_ratio<=1 or onset_hold_frames<1 or
            not 0<min_periodicity<1 or not 0<min_stability<=1 or min_run_ms<=0):
        raise ValueError('Invalid speech pitch mask thresholds')
    x = np.asarray(audio,dtype=float)
    centres,raw,raw_quality = track_pitch(x,sr,hop,window)
    padded = np.pad(x,(window,window))
    rms,flux,previous = [],[],None
    for centre in centres:
        start = int(centre)-window//2+window
        segment = padded[start:start+window]
        rms.append(float(np.sqrt(np.mean(segment*segment))))
        spectrum = abs(np.fft.rfft(segment*np.hanning(window)))
        flux.append(float(np.maximum(spectrum-(previous if previous is not None else spectrum),0).sum()))
        previous = spectrum
    rms,flux = np.asarray(rms),np.asarray(flux)
    flux_floor = np.median(flux)+3*np.median(abs(flux-np.median(flux)))
    rms_floor = max(float(np.sqrt(np.mean(x*x)))*.06,1e-8)
    attacks = np.zeros(len(centres),bool)
    for i in range(len(centres)):
        before = np.median(rms[max(0,i-3):i]) if i else rms_floor
        if rms[i]>rms_floor and rms[i]>onset_ratio*max(before,rms_floor) and flux[i]>flux_floor:
            attacks[i:min(len(centres),i+onset_hold_frames)] = True
    stable = np.zeros(len(centres),float)
    for i,f in enumerate(raw):
        if f<=0:
            continue
        local = raw[max(0,i-4):min(len(raw),i+5)]
        stable[i] = np.count_nonzero((local>0)&(abs(np.log2(np.maximum(local,1e-12)/f))<.18))/len(local)
    eligible = (raw>0)&(raw_quality>=.7)&(stable>=min_stability)&(rms>rms_floor)&~attacks
    # Require an uninterrupted interval, not a total of unrelated periodic
    # frames collected from different attacks across the recording.
    run_mask = np.zeros(len(raw),bool)
    runs = []
    index = 0
    while index<len(raw):
        if not eligible[index]:
            index += 1
            continue
        start = index
        index += 1
        while (index<len(raw) and eligible[index] and
               abs(np.log2(raw[index]/raw[index-1]))<.18):
            index += 1
        duration_ms = (index-start)*hop/sr*1000
        accepted = duration_ms>=min_run_ms
        runs.append(dict(start_frame=start,end_frame_exclusive=index,
                         start_seconds=start*hop/sr,end_seconds=min(len(x),index*hop)/sr,
                         duration_ms=duration_ms,median_hz=float(np.median(raw[start:index])),
                         accepted=accepted))
        if accepted:
            run_mask[start:index] = True
    eligible &= run_mask
    prior = None
    if np.any(eligible):
        logs = np.log2(raw[eligible])
        weights = raw_quality[eligible]*stable[eligible]**2*np.sqrt(rms[eligible])
        grid = np.arange(np.log2(65),np.log2(850)+1/24,1/24)
        density = np.asarray([weights[abs(logs-value)<.12].sum() for value in grid])
        centre = grid[int(np.argmax(density))]
        selected = abs(logs-centre)<.15
        order = np.argsort(logs[selected])
        values,ordered_weights = logs[selected][order],weights[selected][order]
        prior = float(2**values[np.searchsorted(np.cumsum(ordered_weights),ordered_weights.sum()/2)])
    if prior is None:
        f0 = np.zeros_like(raw)
    else:
        _,f0,_ = track_pitch(x,sr,hop,window,prior_hz=prior,prior_weight=prior_weight)
    # Recompute periodicity at the selected lag, not at the best unrelated
    # resonance. The legacy quality value refers to the best CMND trough.
    filtered = np.pad(sosfilt(butter(2,1300,fs=sr,output='sos'),x),(window,window))
    selected_quality = np.zeros_like(raw_quality)
    maximum_lag = int(np.ceil(sr/65))+1
    for i,f in enumerate(f0):
        if f<=0:
            continue
        start = int(centres[i])-window//2+window
        segment = filtered[start:start+window]
        width = window-maximum_lag
        diff = np.asarray([np.sum((segment[:width]-segment[k:k+width])**2) for k in range(maximum_lag+1)])
        cmnd = np.ones_like(diff)
        cmnd[1:] = diff[1:]*np.arange(1,len(diff))/np.maximum(np.cumsum(diff[1:]),1e-20)
        lag = min(maximum_lag,max(1,round(sr/f)))
        selected_quality[i] = max(0.,1-float(cmnd[lag]))
    detected_attacks = attacks.copy()
    # An onset can be a legitimate vowel entry. Preserve it when the selected
    # lag already has strong periodicity at the persistent voice pitch.
    protected_voice = ((selected_quality>=.85)&(f0>0)&
        (abs(np.log2(np.maximum(f0,1e-12)/(prior or 1)))<.18))
    attacks &= ~protected_voice
    f0[attacks|(selected_quality<min_periodicity)|(rms<rms_floor)] = 0
    voice_mask = f0>0
    margin = int(np.ceil(window/2/hop))
    expanded_attacks = attacks.copy()
    for i in np.flatnonzero(attacks):
        expanded_attacks[max(0,i-margin):min(len(attacks),i+margin+1)] = True
    book_mask = voice_mask&~expanded_attacks
    report = dict(schema='persistent-speech-pitch-v1',prior_hz=prior,prior_weight=prior_weight,
                  attack_frames=attacks.tolist(),detected_onset_frames=detected_attacks.tolist(),
                  protected_voiced_onsets=(detected_attacks&protected_voice).tolist(),prior_eligible_frames=eligible.tolist(),
                  prior_runs=runs,
                  voice_mask=voice_mask.tolist(),book_mask=book_mask.tolist(),
                  rms=rms.tolist(),raw_f0_hz=raw.tolist(),raw_periodicity=raw_quality.tolist(),
                  selected_f0_hz=f0.tolist(),selected_periodicity=selected_quality.tolist(),
                  thresholds=dict(onset_ratio=onset_ratio,onset_hold_frames=onset_hold_frames,
                                  min_periodicity=min_periodicity,min_stability=min_stability,min_run_ms=min_run_ms),
                  criterion='Dominant persistent periodic run, weighted by energy and stability; onset ratio plus positive spectral flux detects attacks; strong selected-lag periodicity near the prior protects legitimate voiced onsets; remaining attacks and low periodicity stay unvoiced; dictionary training excludes windows touching rejected attacks.',
                  semantic_ground_truth=False)
    return centres,f0,selected_quality,report
