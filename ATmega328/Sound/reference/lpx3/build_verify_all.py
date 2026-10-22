#!/usr/bin/env python3
import pathlib,subprocess,os,sys
R=pathlib.Path(__file__).resolve().parent
for name,frames in [('chego',36),('otvechaesh',31),('vinni',87)]:
    d=R/'examples'/name
    original=(d/'tinylpc.bin').read_bytes()
    print('\n===',name,'===',flush=True)
    subprocess.run([sys.executable,'build_firmware.py'],cwd=d,check=True)
    actual=(d/'tinylpc.bin').read_bytes()
    assert len(actual)<=1024, f'Flash overflow {name}'
    assert actual==original, f'Rebuild mismatch {name}'
    subprocess.run(['node','verify.js'],cwd=d,check=True,env={**os.environ,'FRAMES':str(frames)})
print('\nThree AVR firmware examples verified.')
