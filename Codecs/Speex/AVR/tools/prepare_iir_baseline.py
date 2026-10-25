#!/usr/bin/env python3
"""Restore tracked IIR mailbox sources from an explicit Git baseline ref."""
import argparse
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PREFIX='Codecs/Speex/AVR/'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();target=args.out.resolve()
    if target.exists():raise ValueError('Choose a new baseline directory: '+str(target))
    revision=subprocess.check_output(['git','rev-parse','--verify','--end-of-options',args.ref+'^{commit}'],
                                     cwd=ROOT,text=True).strip()
    paths=subprocess.check_output(['git','ls-tree','-r','--name-only',revision,'--',PREFIX+'src'],
                                  cwd=ROOT.parents[2],text=True).splitlines()
    paths += [PREFIX+'tools/'+n for n in ['build.py','apply_profile.py','build_iir_test.py']]
    paths += [PREFIX+'tests/'+n for n in ['avr_iir.c','verify_iir.mjs','verify_iir_cursor.mjs']]
    for name in sorted(set(paths)):
        assert name.startswith(PREFIX)
        relative=Path(name[len(PREFIX):])
        assert relative.suffix.lower() not in ['.mid','.midi','.smf']
        data=subprocess.check_output(['git','show',revision+':'+name],cwd=ROOT)
        output=target/relative;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(data)
    (target/'baseline-commit.txt').write_text(revision+'\n')
    print(str(target))


if __name__=='__main__':main()
