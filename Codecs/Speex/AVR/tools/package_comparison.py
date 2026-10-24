#!/usr/bin/env python3
"""Package the generated listening gallery, excerpts and source attribution.

Keeps the corpus's external full-length recordings out of both Git and ZIP.
Run analyze_real_speech.py --rates before packaging native-rate examples.
"""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/real-speech'

def main():
    corpus=json.loads((OUT/'corpus.json').read_text(encoding='utf-8'))
    files=[OUT/name for name in ('index.html','ATTRIBUTION.md','corpus.json','comparison.json')]
    if (OUT/'rates-verification.json').exists(): files.append(OUT/'rates-verification.json')
    for clip in corpus['clips']:
        folder=OUT/'clips'/clip['id']
        files += [folder/name for name in ('original.wav','input.wav','decoded-s16.wav','decoded-pwm.wav')]
        if clip['condition']=='natural':
            files += [folder/str(rate)/'aligned.wav' for rate in (16000,32000)
                      if (folder/str(rate)/'aligned.wav').exists()]
    output=OUT/'speex-listening.zip'
    with ZipFile(output,'w',ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files: archive.write(path,path.relative_to(OUT).as_posix())
        for source in corpus['sources']:
            archive.write(OUT/'originals'/(source['id']+'.html'),'credits/'+source['id']+'.html')
    with ZipFile(output) as archive:
        assert archive.testzip() is None
    print(output,output.stat().st_size,'bytes')

if __name__=='__main__':main()
