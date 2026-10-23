"""Strict per-partial bounds; unmatched original peaks are violations.

Unlike weighted means/p95, every selected reference peak must be present and
within the requested level bound. This checks selected reference peaks only;
extra candidate peaks and full-spectrum errors require companion constraints.
"""
import numpy as np


def check_partial_bounds(details, *, max_level_error_db=5.,max_frequency_error_cents=None,
                         max_frequency_error_hz=None,max_intervals=10,duration_seconds=None):
    """Audit HarmonicTrackObjective.details without changing its assignment.

    Absolute level dB is 20log10(amplitude ratio), equivalently 10log10(power
    ratio). If both optional frequency bounds are provided, both must hold.
    Missing peaks never receive zero error; they always fail this audit.
    """
    bounds = [value for value in (max_level_error_db,max_frequency_error_cents,max_frequency_error_hz)
              if value is not None]
    if (max_level_error_db is None or not all(np.isfinite(value) and value >= 0 for value in bounds)
            or max_intervals < 1 or (duration_seconds is not None and duration_seconds <= 0)):
        raise ValueError('Expected nonnegative finite bounds and a positive interval limit/duration')
    reference,candidate = details['reference_tracks'],details['candidate_tracks']
    times = np.asarray(reference['times'],dtype=float)
    if len(times) != len(candidate['times']) or not np.array_equal(times,candidate['times']):
        raise ValueError('Reference/candidate tracks must have identical timing')
    matches,output_keys = {},set()
    for match in details['matches']:
        key = (int(match['frame']),int(match['reference_id']))
        out_key = (int(match['frame']),int(match['candidate_id']))
        if key in matches or out_key in output_keys:
            raise ValueError('Partial bounds require one-to-one same-time matches')
        matches[key] = match
        output_keys.add(out_key)
    records = []
    frame_count = len(times)
    for frame in range(frame_count):
        for column in np.flatnonzero(reference['amplitude'][frame] > 0):
            track_id = int(reference['track_id'][frame,column])
            match = matches.get((frame,track_id))
            missing = match is None
            level = None if missing else abs(float(match['level_error_db']))
            cents = None if missing else abs(float(match['frequency_error_cents']))
            hz = None if missing else abs(float(match['frequency_error_hz']))
            level_bad = not missing and level > max_level_error_db+1e-9
            frequency_bad = not missing and ((max_frequency_error_cents is not None and cents > max_frequency_error_cents+1e-9)
                or (max_frequency_error_hz is not None and hz > max_frequency_error_hz+1e-9))
            records.append(dict(frame=frame,track_id=track_id,missing=missing,
                level_error_db=level,frequency_error_cents=cents,frequency_error_hz=hz,
                level_violation=bool(level_bad),frequency_violation=bool(frequency_bad),
                violation=bool(missing or level_bad or frequency_bad),
                reference_energy=float(reference['amplitude'][frame,column]**2)))
    total_energy = sum(record['reference_energy'] for record in records)
    bad = [record for record in records if record['violation']]
    missing = [record for record in records if record['missing']]
    matched = [record for record in records if not record['missing']]
    def maximum(items,key):
        values = [record[key] for record in items if record[key] is not None]
        return max(values) if values else None
    result = dict(schema='strict-partial-bounds-v1',
        scope='Every selected reference peak; extra candidate peaks reported separately, not bounded here',
        bounds=dict(max_level_error_db=float(max_level_error_db),
                    max_frequency_error_cents=max_frequency_error_cents,max_frequency_error_hz=max_frequency_error_hz),
        passed=not bool(bad),selected_reference_peaks=len(records),matched_reference_peaks=len(matched),
        missing_reference_peaks=len(missing),matched_level_violations=sum(record['level_violation'] for record in records),
        matched_frequency_violations=sum(record['frequency_violation'] for record in records),
        violating_reference_peaks=len(bad),violating_reference_peak_fraction=len(bad)/max(len(records),1),
        violating_reference_power_fraction=sum(record['reference_energy'] for record in bad)/max(total_energy,1e-30),
        missing_reference_power_fraction=sum(record['reference_energy'] for record in missing)/max(total_energy,1e-30),
        max_matched_level_error_db=maximum(matched,'level_error_db'),
        max_matched_frequency_error_cents=maximum(matched,'frequency_error_cents'),
        max_matched_frequency_error_hz=maximum(matched,'frequency_error_hz'),
        extra_candidate_peaks=int(np.sum(candidate['amplitude']>0))-len(output_keys),
        global_track_metrics=details['metrics'],worst_intervals=[])
    # Split contiguous violation runs into automatic <=250ms windows, so a
    # phrase-wide failure still gives localized intervals for inspection.
    hop = float(np.median(np.diff(times))) if len(times)>1 else 0.
    width = max(1,int(round(.25/hop))) if hop else 1
    bad_frames = np.zeros(frame_count,dtype=bool)
    for record in bad:
        bad_frames[record['frame']] = True
    frame = 0
    intervals = []
    while frame < frame_count:
        if not bad_frames[frame]:
            frame += 1
            continue
        end = frame
        while end < frame_count and bad_frames[end]:
            end += 1
        for start in range(frame,end,width):
            stop = min(end,start+width)
            selected = [record for record in records if start <= record['frame'] < stop]
            failed = [record for record in selected if record['violation']]
            time_end = float(times[stop-1]+hop)
            if duration_seconds is not None:
                time_end = min(time_end,float(duration_seconds))
            intervals.append(dict(start_seconds=float(times[start]),end_seconds=time_end,
                selected_reference_peaks=len(selected),violating_reference_peaks=len(failed),
                missing_reference_peaks=sum(record['missing'] for record in selected),
                matched_level_violations=sum(record['level_violation'] for record in selected),
                matched_frequency_violations=sum(record['frequency_violation'] for record in selected),
                violating_reference_power_fraction=sum(record['reference_energy'] for record in failed)/max(total_energy,1e-30),
                max_matched_level_error_db=maximum(selected,'level_error_db'),
                max_matched_frequency_error_cents=maximum(selected,'frequency_error_cents')))
        frame = end
    result['worst_intervals'] = sorted(intervals,key=lambda interval:interval['violating_reference_power_fraction'],reverse=True)[:max_intervals]
    return result
