"""Fresh paired current-LPX baselines for the LG1 full-decoder experiment."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import subprocess

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
BUILD=REPO/'build/lbg1-common'

def head():
    # A Windows-created Git worktree retains a Windows gitdir path. Use the
    # matching Git executable when this runner is launched through WSL.
    marker=(REPO/'.git').read_text().strip()
    if str(REPO).startswith('/mnt/') and ':/' in marker:
        drive=str(REPO)[5]
        windows=drive.upper()+':'+str(REPO)[6:]
        return subprocess.check_output(['/mnt/c/Program Files/Git/cmd/git.exe','-C',windows,'rev-parse','HEAD'],text=True).strip()
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def encode(case):
    clip,level=case
    source=BUILD/(clip+'.source.pcm')
    prefix=BUILD/'baselines'/f'{clip}-p{level}'
    result=subprocess.run([str(BUILD/'probe'),'encode',str(source),str(prefix),str(level),'4'],capture_output=True,check=True)
    metrics=json.loads(result.stdout)
    row=dict(clip=clip,level=level,calls=4,metrics=metrics,
             reference=str(source.relative_to(REPO)),reference_sha256=sha(source),
             **{ext:str(prefix.with_suffix('.'+ext).relative_to(REPO)) for ext in ('lpx','model','pcm')},
             sha256={ext:sha(prefix.with_suffix('.'+ext)) for ext in ('lpx','model','pcm')})
    prefix.with_suffix('.json').write_text(json.dumps(row,indent=2)+'\n')
    print(f'{clip} P{level}: {prefix.with_suffix(".lpx").stat().st_size} bytes, STOI {metrics["pcm_stoi"]:.6f}',flush=True)
    return row

def main():
    (BUILD/'baselines').mkdir(parents=True,exist_ok=True)
    cases=[(clip,level) for clip in ('chego','otvechaesh','vinni','bread') for level in (4,6)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows=list(pool.map(encode,cases))
    report=dict(schema='lbg1-current-lpx-baselines-v1',
                baseline_revision='24fd9416',
                current_head=head(),
                method='Current encodeAccuracy4/6, calls4, same complete public PCM16/8000 inputs, no fitted gain/delay. Model/native exact.',
                probe_sha256=sha(BUILD/'probe'),sources=json.loads((BUILD/'sources.json').read_text()),rows=rows)
    (BUILD/'baselines.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Saved build/lbg1-common/baselines.json',flush=True)

if __name__=='__main__':
    main()
