"""Restore pinned baseline, screening or admitted angle kernels for replay."""
import argparse
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import re
import subprocess
import zipfile
ROOT=Path(__file__).resolve().parents[1]
ALLOWED={'src/compact_lsp.c.inc','src/lsp_pair.S','src/lsp_angle.S','src/nb3_lsp_angle.h','tools/build.py'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',choices=['baseline','layout','cosine','production'],default='production')
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    report=json.loads((ROOT/'reports/angle-admission.json').read_text(encoding='utf-8'))
    sources=report['candidates'][args.candidate]
    if not set(sources)<=ALLOWED:raise ValueError('Unexpected source replacement')
    if set(report['observers'])!={'tests/verify_avr.mjs','tests/verify_wb.mjs'}:raise ValueError('Unexpected replay observer')
    if not re.fullmatch('[0-9a-f]{40}',report['baselineGitCommit']):raise ValueError('Expected a pinned Git commit')
    out=args.out.resolve()
    if out.exists():p.error('Output directory must not exist')
    replacements=[]
    for name,key in {**sources,**report['observers']}.items():
        data=report['sourceText'][key].encode();assert hashlib.sha256(data).hexdigest()==key
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:raise ValueError('Unsafe source path')
        replacements.append((Path(path),data))
    repo=subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=ROOT,text=True).strip()
    prefix='Codecs/Speex/AVR/';parts=['src','tools','tests','vendor','handoff','reference','PORTING.md']
    data=subprocess.check_output(['git','archive','--format=zip',report['baselineGitCommit'],'--',*[prefix+n for n in parts]],cwd=repo)
    files=[]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in archive.infolist():
            if entry.is_dir():continue
            if not entry.filename.startswith(prefix):raise ValueError('Unexpected archive path')
            name=entry.filename[len(prefix):];path=PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:raise ValueError('Unsafe archive path')
            if path.suffix.lower() in ('.mid','.midi','.smf'):raise ValueError('MIDI source is forbidden')
            files.append((Path(path),archive.read(entry)))
    out.mkdir(parents=True)
    for name,data in files+replacements:
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    print(out)
if __name__=='__main__':main()
