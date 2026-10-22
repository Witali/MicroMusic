from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parent
DEST=Path('/mnt/data')
source_files=[
 'README.md','requirements.txt','run_all.py','model_keyframes.py','perceptual.py',
 'make_firmware_source.py','baseline_tinylpc.S','tinylpc.S','package_stream.py',
 'train_keyframes.py','build_firmware.py','verify.js','avr_emulator.js',
 'verify_models.py','make_demo.py','test_browser.py','package_release.py']
code_name=DEST/'MicroMusic_KeyframeLPC8_code_only.zip'
priv_name=DEST/'MicroMusic_KeyframeLPC8_private_project.zip'
with ZipFile(code_name,'w',ZIP_DEFLATED,compresslevel=9) as z:
 for rel in source_files:z.write(ROOT/rel,arcname='MicroMusic_KeyframeLPC8/'+rel)
with ZipFile(priv_name,'w',ZIP_DEFLATED,compresslevel=8) as z:
 for rel in source_files:z.write(ROOT/rel,arcname='MicroMusic_KeyframeLPC8/'+rel)
 for rel in ['MicroMusic_KeyframeLPC_ATtiny13.html']:
  z.write(ROOT/rel,arcname='MicroMusic_KeyframeLPC8/'+rel)
 for p in sorted((ROOT/'datasets').rglob('*')):
  if p.is_file():z.write(p,arcname='MicroMusic_KeyframeLPC8/'+str(p.relative_to(ROOT)))
 for clip in ('xtuj-ntt','ne-otv'):
  for rel in ('report.json','history.json','trained_parameters.npz','voice_tinylpc.bin',
              'tinylpc.hex','tinylpc.bin','tinylpc.S','build_firmware.py','package_stream.py','avr_emulator.js','verify.js','model_keyframes.wav','emu_pwm_u8.raw'):
   p=ROOT/clip/rel
   z.write(p,arcname='MicroMusic_KeyframeLPC8/'+clip+'/'+rel)
 for p in sorted((ROOT/'release').iterdir()):
  if p.is_file():z.write(p,arcname='MicroMusic_KeyframeLPC8/release/'+p.name)
for p in [code_name,priv_name]:print(p,p.stat().st_size,'bytes')
