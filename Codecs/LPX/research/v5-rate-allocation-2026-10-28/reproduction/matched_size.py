import hashlib,json
from pathlib import Path
import numpy as np
import soundfile as sf
import speech_compact as compact
from speech_rate_allocation import bit_accounting,fit_capacity
from batch_decoder import BatchSession
from refine_speech_compact import quality
from standard_metrics import pwm_duties

import argparse
from measure_speech_firmware import checked_output
from output_paths import protect_outputs
_parser=argparse.ArgumentParser(description=__doc__)
_parser.add_argument('manifest',type=Path)
_parser.add_argument('pilot',type=Path)
_args=_parser.parse_args()
ROOT=Path.cwd();OUT=checked_output(_args.pilot);manifest=json.loads(_args.manifest.read_text())
records=json.loads((OUT/'results-private.json').read_text())['records']
lookup={(r['private_case_id'],r['profile']):r for r in manifest['records']}
rows=[];used=set()
protect_outputs([_args.manifest,Path(__file__),OUT/'results-private.json']+[Path(r['stream_path']) for r in records], [OUT/'matched-size.json'])
with BatchSession('batch',speech=True,speech_compact=True) as common,BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as v5:
    for row in records:
        stream=Path(row['stream_path']).read_bytes();pcm=compact.decode_model(stream);n=len(pcm)
        for decoder in (common,v5):
            np.testing.assert_array_equal(decoder.decode_one_s16(stream,n),pcm)
            np.testing.assert_array_equal(decoder.decode_one(stream,n),pwm_duties(pcm))
        if row['policy']!='marginal' or not row['removed']:continue
        identity=(row['id'],len(stream))
        if identity in used:continue
        used.add(identity);original=lookup[(row['private_case_id'],row['profile'])]
        assert original['split']=='tuning' and len(original['segments'])==1
        reference,rate=sf.read(original['reference']['path'],dtype='int16');assert rate==8000 and len(reference)==n
        blob=Path(original['segments'][0]['path']).read_bytes();values=compact.unpack(blob);extras=np.asarray(values[7],np.int64)
        cost=bit_accounting(values[2],values[1],extras)
        control,capacity,size,removed=fit_capacity(cost['spectrum_bits'],len(values[2]),values[1],extras,len(stream),0,n)
        baseline=compact.pack(*values[:7],extras=control)[0];assert len(baseline)==len(stream)==size
        baseline_pcm=compact.decode_model(baseline)
        for decoder in (common,v5):
            np.testing.assert_array_equal(decoder.decode_one_s16(baseline,n),baseline_pcm)
            np.testing.assert_array_equal(decoder.decode_one(baseline,n),pwm_duties(baseline_pcm))
        old=quality(reference,baseline_pcm);new=quality(reference,pcm)
        rows.append({'id':row['id'],'profile':row['profile'],'cohort':row['cohort'],'samples':n,'file_bytes':size,
            'removed_extras':row['removed'],'amplitude':old,'marginal':new,'original_cap_percent':row['percent'],
            'original_cap_fitted':row['fits'],'marginal_evaluations':row['evaluations'],'marginal_seconds':row['seconds'],
            'pcm_sse_change_percent':100*(new['pcm16']['error_energy']-old['pcm16']['error_energy'])/old['pcm16']['error_energy'] if old['pcm16']['error_energy'] else 0,
            'native_common_v5_model_pcm_pwm_exact':True})
summary={'schema':'lpx-v5-marginal-equal-achieved-size-v1','rows':rows,'complete_pilot_outputs_pcm_pwm_verified':len(records),'unique_comparisons':len(rows),
    'better_equal_worse':[sum((r['marginal']['pcm16']['error_energy']<r['amplitude']['pcm16']['error_energy']) if k==0 else (r['marginal']['pcm16']['error_energy']==r['amplitude']['pcm16']['error_energy']) if k==1 else (r['marginal']['pcm16']['error_energy']>r['amplitude']['pcm16']['error_energy']) for r in rows) for k in range(3)],
    'scope':'Secondary comparison at the marginal search actual achieved size, including candidates that missed the original95/90cap. Not original-cap admission; fixed spectra/parameters/base pulses and unchanged complete length/gain.'}
(OUT/'matched-size.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'comparisons':len(rows),'better_equal_worse':summary['better_equal_worse'],'pcm_sse_changes':[r['pcm_sse_change_percent'] for r in rows],'all36_pcm_pwm_exact':True}))
