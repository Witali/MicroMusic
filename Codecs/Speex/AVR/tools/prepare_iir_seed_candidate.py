"""Restore pinned IIR screening/admission variants in a new decoder-only tree."""
import argparse
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import re
import subprocess
import zipfile
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',choices=['baseline','first','move','negate','production'],default='production')
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    report=json.loads((ROOT/'reports/seed-admission.json').read_text(encoding='utf-8'))
    if not re.fullmatch('[0-9a-f]{40}',report['baselineGitCommit']):raise ValueError('Expected pinned Git revision')
    replacements=report['candidates'][args.candidate]
    if not set(replacements)<={'src/iir_kernel.inc'}:raise ValueError('Unexpected replacement')
    out=args.out.resolve()
    if out.exists():p.error('Output must not exist')
    prefix='Codecs/Speex/AVR/';parts=['src','tools','tests','vendor','handoff','reference','PORTING.md']
    repo=subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=ROOT,text=True).strip()
    data=subprocess.check_output(['git','archive','--format=zip',report['baselineGitCommit'],'--',*[prefix+s for s in parts]],cwd=repo)
    files=[]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in archive.infolist():
            if entry.is_dir():continue
            if not entry.filename.startswith(prefix):raise ValueError('Unexpected archive prefix')
            name=entry.filename[len(prefix):];path=PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:raise ValueError('Unsafe archive path')
            if path.suffix.lower() in ['.mid','.midi','.smf']:raise ValueError('MIDI is forbidden')
            files.append((Path(path),archive.read(entry)))
    for name,sha in replacements.items():
        payload=report['sourceText'][sha].encode();assert hashlib.sha256(payload).hexdigest()==sha
        files.append((Path(name),payload))
    out.mkdir(parents=True)
    for name,payload in files:
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
    print(out)
if __name__=='__main__':main()
