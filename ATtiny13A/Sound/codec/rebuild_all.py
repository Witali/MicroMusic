#!/usr/bin/env python3
"""Rebuild every firmware from the included sources and packed parameters.
Requires Python NumPy, Clang for AVR, llvm-objcopy and Node.js. No network.
"""
import os, sys, subprocess, pathlib, argparse
P=pathlib.Path(__file__).resolve().parent

def run(*cmd,cwd=None,env=None):
 print('+',' '.join(map(str,cmd)),flush=True)
 subprocess.run(list(map(str,cmd)),cwd=cwd,env=env,check=True)

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--clip',choices=['xtuj-ntt','ne-otv','vinni','all'],default='all')
 args=ap.parse_args()
 for name in (['xtuj-ntt','ne-otv','vinni'] if args.clip=='all' else [args.clip]):
  fw=P/name/'firmware'
  env=dict(os.environ,FRAMES=str({'xtuj-ntt':36,'ne-otv':31,'vinni':87}[name]))
  run(sys.executable,'package_stream.py',cwd=fw)
  run(sys.executable,'build_firmware.py',cwd=fw)
  run('node','verify.js',cwd=fw,env=env)
  assert (fw/'tinylpc.bin').stat().st_size<=1024
 print('All firmware builds and AVR timing tests passed.')
if __name__=='__main__':main()
