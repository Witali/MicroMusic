#!/usr/bin/env python3
"""Restore measured constant polynomial stage candidates for decoder-only replay."""
import argparse
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import subprocess
import zipfile
ROOT=Path(__file__).resolve().parents[1]
ALLOWED={'src/lsp_stage.S', 'src/q14_macros.S', 'src/compact_lsp.c.inc', 'src/nb3_lsp_stage.h', 'tools/build.py', 'src/q14.S'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',required=True);p.add_argument('--out',required=True,type=Path)
    args=p.parse_args();report=json.loads((ROOT/'reports/poly-candidates.json').read_text())
    rows={r['name']:r for r in report['candidates']}
    if args.candidate=='production':sources=report['productionSources']
    elif args.candidate in rows:sources=rows[args.candidate]['sources']
    else:p.error('Unknown candidate; choose production or '+', '.join(rows))
    if not {'src/compact_lsp.c.inc'}<=set(sources)<=ALLOWED:raise ValueError('Unexpected source files')
    out=args.out.resolve()
    if out.exists():p.error('Output directory must not exist')
    replacements=[]
    for name,key in list(sources.items())+[('tests/verify_avr.mjs',report['observer'])]:
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
