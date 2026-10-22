#!/usr/bin/env python3
"""One command rebuild: input voices -> encoder training -> AVR HEX -> verification -> browser."""
import shutil,sys,subprocess,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CLIPS={'xtuj-ntt':(36,1000),'ne-otv':(31,1500)}
def call(*argv,cwd=ROOT,env=None):
    print('+',' '.join(map(str,argv)),flush=True)
    subprocess.run(argv,cwd=cwd,env=env,check=True)
def main():
    call(sys.executable,'make_adaptive_source.py')
    for clip,(frames,budget) in CLIPS.items():
        call(sys.executable,'train_adaptive.py','--clip',clip,'--budget',str(budget))
        p=ROOT/'adaptive_results'/clip;p.mkdir(exist_ok=True,parents=True)
        for filename in ('tinylpc.S','build_firmware.py','avr_emulator.js','verify.js'):
            shutil.copy2(ROOT/filename,p/filename)
        call(sys.executable,'build_firmware.py',cwd=p)
        call('node','verify.js',cwd=p,env={**os.environ,'FRAMES':str(frames)})
    call(sys.executable,'verify_adaptive_models.py')
    call(sys.executable,'make_adaptive_demo.py')
    call(sys.executable,'test_adaptive_browser.py')
    print('PASS: both voices, real AVR HEX, all PCM samples, browser audio and verification')
if __name__=='__main__':main()
