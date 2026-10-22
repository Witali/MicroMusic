#!/usr/bin/env python3
"""Make a clean source-only archive and a separate personal test bundle."""
from pathlib import Path
import json,zipfile,shutil,csv
R=Path(__file__).resolve().parent
ROOT=R.parent.parent
meta={}
for n in ('chego','otvechaesh','vinni','chego_balanced'):
 info=json.loads((R/'final'/n/'result.json').read_text())
 meta[n]=info
(R/'release_report.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
with (R/'release_report.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=['name','stoi','flash','speech_bytes','native_seconds','sha256'])
 writer.writeheader()
 for n,v in meta.items():writer.writerow({'name':n,'stoi':v['verified_stoi_after'],'flash':v['flash'],'speech_bytes':v['new_stream_bytes'],'native_seconds':v['elapsed_seconds'],'sha256':v['sha256']})
sourcefiles=['README.md','requirements.txt','fast_core.c','fast_train.py','build_native.sh','decoder_template.S','convert_audio.py','make_demo.py','make_player.py','benchmark.py','quality_reference.py','test_regression.py','verify_avr.js','verify_release.py','avr_emulator.js','package.py']
# Include only self-generated synthetic materials in the source-only archive.
common_demo=['examples/demo/original.wav','examples/demo/speech.hq','examples/demo/firmware.S']
privatefiles=[]
for n in ('chego','otvechaesh','vinni'):
 for name in ('firmware.S','speech.hq','original.wav'):
  privatefiles.append(f'examples/{n}/{name}')
for n in ('chego','otvechaesh','vinni','chego_balanced'):
 for p in (R/'final'/n).iterdir():
  if p.is_file() and not p.name.endswith('.o'):
   privatefiles.append(p.relative_to(R).as_posix())
sourcepath=ROOT/'MicroMusic_FastEncoder_C_Source.zip'
privatepath=ROOT/'MicroMusic_FastEncoder_C_Private.zip'

def create(path,names):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name in sorted(set(names)):
            p=R/name
            assert p.exists(),p
            z.write(p,arcname='MicroMusic_FastEncoder_C/'+name)
    with zipfile.ZipFile(path) as z:
        corrupt=z.testzip()
        assert corrupt is None,corrupt
        print(path.name,len(z.namelist()),'files',round(path.stat().st_size/1024,1),'KiB')

create(sourcepath,sourcefiles+common_demo)
create(privatepath,sourcefiles+common_demo+privatefiles+['libmicrolpc.so','MicroMusic_C_Encoder_Player.html','release_report.json','release_report.csv'])
shutil.copyfile(R/'MicroMusic_C_Encoder_Player.html',ROOT/'MicroMusic_C_Encoder_Player.html')
shutil.copyfile(R/'fast_core.c',ROOT/'MicroMusic_FastEncoder_C.c')
shutil.copyfile(R/'release_report.csv',ROOT/'MicroMusic_FastEncoder_Report.csv')
