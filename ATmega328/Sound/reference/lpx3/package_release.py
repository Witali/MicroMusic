#!/usr/bin/env python3
"""Package clean source-only archive and a PRIVATE full listening project."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from shutil import copyfile
import json,os
R=Path(__file__).resolve().parent
out=R.parent
include_code=['README.md','requirements.txt','hybrid_codec.py','train_encode.py','lpx3_decoder.js','lpc2_v2_reference.html',
              'generate_js_decoder.py','make_player.py','make_ab.py','benchmark.py','verify_project.py','package_release.py']
copyfile(R/'index.html', out/'MicroMusic_LPC2_Voice_v3.html')
files_private=[R/f for f in include_code]+[R/'index.html',R/'benchmark.json',R/'verification.json']
for clip in ('vinni','xtuj-ntt','ne-otv'):
    data=R/'samples'/clip
    files_private+=sorted(x for x in data.iterdir() if x.is_file())
private_path=out/'MicroMusic_LPC2_Voice_v3_private.zip'
code_path=out/'MicroMusic_LPC2_Voice_v3_code_only.zip'
with ZipFile(private_path,'w',ZIP_DEFLATED,compresslevel=7) as z:
    for f in files_private:
        z.write(f,'MicroMusic_LPC2_Voice_v3/'+str(f.relative_to(R)))
with ZipFile(code_path,'w',ZIP_DEFLATED,compresslevel=7) as z:
    for f in include_code:
        z.write(R/f,'MicroMusic_LPC2_Voice_v3/'+f)
for f in [private_path,code_path,out/'MicroMusic_LPC2_Voice_v3.html']:
    assert f.exists() and f.stat().st_size>1000
    print(f,f.stat().st_size)
