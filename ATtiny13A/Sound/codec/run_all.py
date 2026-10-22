#!/usr/bin/env python3
"""One command: optimize both voices, build true AVR firmware, verify and make test page.
Requires: numpy numba scipy soundfile pystoi, Node.js, Clang AVR, llvm-objcopy.
"""
import os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

clips={'xtuj-ntt':(36,4,900),'ne-otv':(31,4,1600)}
def run(args,cwd=ROOT,env=None):
  print('+',' '.join(map(str,args)),flush=True)
  subprocess.run(args,cwd=cwd,env=env,check=True)

def main():
  run([sys.executable,'make_firmware_source.py'])
  for clip,(frames,skips,train_budget) in clips.items():
    run([sys.executable,'train_keyframes.py','--clip',clip,'--skips',str(skips),'--budget',str(train_budget)])
    d=ROOT/clip;d.mkdir(parents=True,exist_ok=True)
    for name in ('tinylpc.S','build_firmware.py','avr_emulator.js','verify.js','package_stream.py'):
      shutil.copy2(ROOT/name,d/name)
    run([sys.executable,'build_firmware.py'],cwd=d)
    env={**os.environ,'FRAMES':str(frames)}
    run(['node','verify.js'],cwd=d,env=env)
  run([sys.executable,'verify_models.py'])
  run([sys.executable,'make_demo.py'])
  run([sys.executable,'test_browser.py'])
  print('SUCCESS: keyframes encoded, actual AVR HEX verified, browser tested')

if __name__=='__main__':main()
