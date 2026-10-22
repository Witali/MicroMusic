#!/usr/bin/env python3
"""Package both source-only and PRIVATE audio-containing MicroMusic experiments.
Do not publish the private ZIP: it includes third-party source voice.
"""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import argparse
ROOT=Path(__file__).resolve().parent
SOURCE=['README.md','requirements.txt','run_all.py','prepare_source.py','generate_seed.py',
        'generate_lpc2_teacher.py','perceptual.py','model_lite.py','optimize.py',
        'package_project.py','lpc2_improved_encoder.html',
        'firmware/tinylpc.S','firmware/build_firmware.py','firmware/package_stream.py',
        'firmware/avr_emulator.js','firmware/verify.js']
PRIVATE=['references/base_parameters.npz','references/original_reference.wav',
         'references/lpc2_improved_reference.s16le',
         'references/lite_baseline_u8.raw','references/v5_baseline_u8.raw']
GEN=['optimized.hex','optimized.bin','optimized_parameters.npz','voice.bin','index.html',
     'original.wav','lpc2.wav','baseline.wav','optimized_avr.wav','AB_comparison.wav',
     'report.json','teacher_8000.wav','teacher.lp2']

def package(out,report_dir=None):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
 report_dir=Path(report_dir).resolve() if report_dir is not None else ROOT/'results/release'
 try: report_rel=str(report_dir.relative_to(ROOT))
 except ValueError: raise ValueError('Report directory must be inside the project for self-contained archive')
 paths=[]
 for filename,files in [('MicroMusic_AutoLPC2_code_only.zip',SOURCE),
                        ('MicroMusic_AutoLPC2_private_full.zip',SOURCE+PRIVATE+[report_rel+'/'+n for n in GEN])]:
  dest=out/filename
  with ZipFile(dest,'w',ZIP_DEFLATED,compresslevel=8) as z:
   for name in files:
    source=ROOT/name
    if not source.is_file():raise FileNotFoundError(source)
    z.write(source,arcname='MicroMusic_AutoLPC2/'+name)
  paths.append(dest)
  print(dest,'size',dest.stat().st_size,'bytes')
 return paths

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=ROOT/'results/release');parser.add_argument('--report-dir',type=Path,default=None);a=parser.parse_args()
 package(a.out,a.report_dir)
