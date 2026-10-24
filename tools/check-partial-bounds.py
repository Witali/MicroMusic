#!/usr/bin/env python3
"""Audit every selected original partial against absolute level/frequency caps."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from harmonic_tracks import HarmonicTrackObjective
from partial_bounds import check_partial_bounds


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--candidate',action='append',required=True,help='Label=full-duration WAV or AVR RAW')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-level-db',type=float,default=5.)
    p.add_argument('--max-frequency-cents',type=float)
    p.add_argument('--max-frequency-hz',type=float)
    a = p.parse_args()
    reference,sr = sf.read(a.reference,dtype='float64')
    objective = HarmonicTrackObjective(reference,sr)
    spec = importlib.util.spec_from_file_location('partial_bounds_reader',ROOT/'tools/compare-speech-spectrograms.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    result = dict(schema='strict-partial-bounds-report-v1',sample_rate=sr,samples=len(reference),
        reference_sha256=hashlib.sha256(a.reference.read_bytes()).hexdigest(),
        tracker=objective.config,candidates={})
    for entry in a.candidate:
        if '=' not in entry:
            p.error('Each candidate must be Label=path')
        label,filename = entry.split('=',1)
        path = Path(filename)
        audio,rate = reader.read_candidate(path,len(reference),sr)
        if rate != sr:
            p.error('Candidate sample rate must match original')
        started = time.perf_counter()
        details = objective.details(audio)
        audit = check_partial_bounds(details,max_level_error_db=a.max_level_db,
            max_frequency_error_cents=a.max_frequency_cents,max_frequency_error_hz=a.max_frequency_hz,
            duration_seconds=len(reference)/sr)
        result['candidates'][label] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            evaluation_ms=1000*(time.perf_counter()-started),**audit)
    sources = (Path(__file__),CODEC/'partial_bounds.py',CODEC/'harmonic_tracks.py')
    result['source_sha256_normalized_lf'] = {path.relative_to(ROOT).as_posix():
        hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest() for path in sources}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({label:{key:report[key] for key in ('passed','selected_reference_peaks',
        'missing_reference_peaks','matched_level_violations','violating_reference_peaks',
        'violating_reference_power_fraction','max_matched_level_error_db','evaluation_ms')}
        for label,report in result['candidates'].items()}))


if __name__ == '__main__':
    main()
