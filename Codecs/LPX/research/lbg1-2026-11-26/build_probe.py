"""Build the shared research probe with the exact production host sources."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ACTIVE = REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
OUTPUT = REPO/'build/lbg1-common'

def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    config = (REPO/'web-player/scripts/lib/lpx-build.mjs').read_text()
    names = re.findall(r"'([^']+\.cpp)'", config.split('export const hostSources=host([')[1].split(']);')[0])
    sources = [ACTIVE/'src/Lpx4HybridCore.cpp', ACTIVE/'host/LpxEncoder.cpp',
               *(ACTIVE/'host'/n for n in names), HERE/'probe.cpp']
    defines = ['LPX4_ENABLE_ASM=0','LPX4_FLOAT_SYNTHESIS=0','LPX4_ENABLE_SPEECH=1',
               'LPX4_ENABLE_SPEECH_COMPACT=1','LPX4_COMPACT_ONLY=1','LPX4_COMPACT_VERSION=9',
               'LPX4_SAMPLE_RATE=0','LPX4_EXTENDED_SAMPLE_RATES=1','LPX4_ENABLE_WIDE_V9=1']
    command = ['g++','-O3','-std=c++11','-ffp-contract=off','-DNDEBUG',
               *('-D'+d for d in defines), '-include',str(ACTIVE/'host/LpxHostWorkspace.h'),
               '-I'+str(ACTIVE/'src'),'-I'+str(ACTIVE/'host'),
               *(str(p) for p in sources),'-o',str(OUTPUT/'probe')]
    subprocess.run(command, check=True)
    manifest = dict(compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
                    command=[str(Path(a).relative_to(REPO)) if a.startswith(str(REPO)+'/') else a for a in command],
                    sources={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (OUTPUT/'build.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Built build/lbg1-common/probe',flush=True)

if __name__ == '__main__':
    main()
