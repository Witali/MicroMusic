"""Check independent cycle-counting AVR emulator output against integer-exact model."""
import json
from pathlib import Path
import numpy as np
from model_adaptive import render
from perceptual import Evaluator,load_wav
ROOT=Path(__file__).resolve().parent
for clip in ('xtuj-ntt','ne-otv'):
    p=ROOT/'adaptive_results'/clip
    z=np.load(p/'trained_parameters.npz')
    actual=np.fromfile(p/'emu_pwm_u8.raw',dtype=np.uint8).astype(np.int16)-128
    expected=render(z['K'],z['P'],z['E'],z['mask'],z['fast'],len(actual),4,8)
    mismatch=int(np.count_nonzero(actual!=expected))
    report=json.loads((p/'report.json').read_text())
    ev=Evaluator(load_wav(ROOT/'datasets'/clip/'original.wav'), load_wav(ROOT/'datasets'/clip/'lpx3_voice.wav'))
    metrics=ev.metrics(actual)
    flash=len((p/'tinylpc.bin').read_bytes())
    report['verified_AVR']={'samples':len(actual),'mismatches':mismatch,'metrics':metrics,'flash_bytes':flash}
    (p/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(clip,'FLASH',flash,'mismatch',mismatch,'STOI',round(metrics['stoi'],6))
    assert mismatch==0 and flash<=1024
