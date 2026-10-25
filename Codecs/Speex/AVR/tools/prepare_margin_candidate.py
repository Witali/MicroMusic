#!/usr/bin/env python3
"""Restore a measured NB3 margin/LPC candidate for decoder-only replay."""
import argparse
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import subprocess
import zipfile
ROOT=Path(__file__).resolve().parents[1]
REQUIRED={'src/nb3_interpolate.h','src/compact_lsp.c.inc','src/nb_decode.c.inc'}
ALLOWED=REQUIRED|{'src/lsp_advance.S','tools/build.py'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',required=True);p.add_argument('--out',required=True,type=Path)
    args=p.parse_args();report=json.loads((ROOT/'reports/margin-candidates.json').read_text())
    rows={r['name']:r for r in report['candidates']}
    if args.candidate=='production':sources=report['productionSources'];observer=report['productionObserver']
    elif args.candidate in rows:sources=rows[args.candidate]['sources'];observer=report['prototypeObserver']
    else:p.error('Unknown candidate; choose production or '+', '.join(rows))
    if not REQUIRED<=set(sources)<=ALLOWED:raise ValueError('Unexpected source files')
    out=args.out.resolve()
    if out.exists():p.error('Output directory must not exist')
    replacements=[]
    for name,key in list(sources.items())+[('tests/verify_avr.mjs',observer)]:
        data=report['sourceText'][key].encode();assert hashlib.sha256(data).hexdigest()==key
        replacements.append((Path(name),data))
    prefix='Codecs/Speex/AVR/';parts=['src','tools','tests','vendor','handoff','reference','PORTING.md']
    repo=subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=ROOT,text=True).strip()
    data=subprocess.check_output(['git','archive','--format=zip',report['baselineGitCommit'],'--',*[prefix+n for n in parts]],cwd=repo)
    files=[]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in archive.infolist():
            if entry.is_dir():continue
            if not entry.filename.startswith(prefix):raise ValueError('Unexpected archive path')
            name=entry.filename[len(prefix):];path=PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:raise ValueError('Unsafe path')
            if path.suffix.lower() in ('.mid','.midi','.smf'):raise ValueError('MIDI source is forbidden')
            files.append((Path(path),archive.read(entry)))
    out.mkdir(parents=True)
    for path,data in files+replacements:
        target=out/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    print(out)
if __name__=='__main__':main()
