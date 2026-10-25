#!/usr/bin/env python3
"""Restore a measured packet-reader candidate for decoder-only reproduction."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args()
    report=json.loads((ROOT/'reports/subframe-candidates.json').read_text())
    rows={r['name']:r for r in report['candidates']}
    if args.candidate not in rows:parser.error('Unknown candidate; choose: '+', '.join(rows))
    out=args.out.resolve()
    if out.exists():parser.error('Output directory must not exist')
    prefix='Codecs/Speex/AVR/';parts=['src','tools','tests','vendor','handoff','reference','PORTING.md']
    repository=subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=ROOT,text=True).strip()
    data=subprocess.check_output(['git','archive','--format=zip',report['baselineGitCommit'],
        '--',*[prefix+p for p in parts]],cwd=repository)
    files=[]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in archive.infolist():
            if entry.is_dir():continue
            if not entry.filename.startswith(prefix):raise ValueError('Unexpected archive path')
            path=Path(entry.filename[len(prefix):])
            if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe archive path')
            if path.suffix.lower() in ('.mid','.midi','.smf'):raise ValueError('MIDI source is forbidden')
            files.append((path,archive.read(entry)))
    out.mkdir(parents=True)
    for path,data in files:
        target=out/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    for name,key in rows[args.candidate]['sources'].items():
        if Path(name).name!=name or Path(name).is_absolute():raise ValueError('Unsafe source name')
        text=report['sourceText'][key];assert hashlib.sha256(text.encode()).hexdigest()==key
        (out/'src'/name).write_text(text,encoding='utf-8')
    print(out)

if __name__=='__main__':main()
