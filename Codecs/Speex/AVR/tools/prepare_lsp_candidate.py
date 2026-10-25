#!/usr/bin/env python3
"""Replay a retained quarter-LSP candidate in a new isolated source directory."""
import argparse
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args()
    report=json.loads((ROOT/'reports/lsp-quarter-candidates.json').read_text())
    rows={r['name']:r for r in report['candidates']}
    if args.candidate not in rows:parser.error('Unknown candidate; use one of: '+', '.join(rows))
    out=args.out.resolve()
    if out.exists():parser.error('Output directory must not exist')
    prefix='Codecs/Speex/AVR/'
    parts=['src','tools','tests','vendor','handoff','reference','PORTING.md']
    repository=subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=ROOT,text=True).strip()
    archive=subprocess.check_output(['git','archive','--format=zip',report['baselineGitCommit'],
        '--',*[prefix+p for p in parts]],cwd=repository)
    files=[]
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        for entry in z.infolist():
            if entry.is_dir():continue
            if not entry.filename.startswith(prefix):raise ValueError('Unexpected archive path')
            path=Path(entry.filename[len(prefix):])
            if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe archive path')
            if path.suffix.lower() in ('.mid','.midi','.smf'):raise ValueError('MIDI source is forbidden')
            files.append((path,z.read(entry)))
    out.mkdir(parents=True)
    for path,data in files:
        target=out/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    row=rows[args.candidate]
    (out/'src/nb3_interpolate.h').write_text(row['header'],encoding='utf-8')
    (out/'src/nb_decode.c.inc').write_text(report['controllers'][row['controller']],encoding='utf-8')
    print(out)

if __name__=='__main__':main()
