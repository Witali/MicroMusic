#!/usr/bin/env python3
"""Restore a measured LSP lifetime/bounds candidate for decoder reproduction."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SOURCES={'src/nb3_interpolate.h','src/nb_decode.c.inc','src/speex_avr.c'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args()
    report=json.loads((ROOT/'reports/lifetime-candidates.json').read_text())
    rows={r['name']:r for r in report['candidates']}
    if args.candidate not in rows:parser.error('Unknown candidate; choose: '+', '.join(rows))
    out=args.out.resolve()
    if out.exists():parser.error('Output directory must not exist')
    sources=rows[args.candidate]['sources']
    if set(sources)!=SOURCES:raise ValueError('Unexpected candidate source files')
    files=[]
    for name,key in sources.items():
        text=report['sourceText'][key]
        assert hashlib.sha256(text.encode()).hexdigest()==key
        files.append((Path(name),text.encode()))
    prefix='Codecs/Speex/AVR/'
    parts=['src','tools','tests','vendor','handoff','reference','PORTING.md']
    repository=subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=ROOT,text=True).strip()
    data=subprocess.check_output(['git','archive','--format=zip',report['baselineGitCommit'],
        '--',*[prefix+p for p in parts]],cwd=repository)
    archive_files=[]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in archive.infolist():
            if entry.is_dir():continue
            if not entry.filename.startswith(prefix):raise ValueError('Unexpected archive path')
            name=entry.filename[len(prefix):]
            path=PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:
                raise ValueError('Unsafe archive path')
            if path.suffix.lower() in ('.mid','.midi','.smf'):raise ValueError('MIDI source is forbidden')
            archive_files.append((Path(path),archive.read(entry)))
    out.mkdir(parents=True)
    for path,data in archive_files+files:
        target=out/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    print(out)

if __name__=='__main__':main()
