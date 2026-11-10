#!/usr/bin/env python3
"""Reproduce frozen-source innovation/controller image and loaded-IRQ screens.

The supplied source snapshot is copied into disposable codec trees so source
preparation cannot accidentally read mutable production fragments. Only ASM
firmware executes; the complete C controls compile/link and compare only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--avr-gcc',required=True)
 p.add_argument('--node')
 p.add_argument('--data',type=Path,help='Five profile folders containing streams/ and oracle/')
 p.add_argument('--before-src',type=Path,required=True,help='Frozen baseline src/ at 1da660ea')
 p.add_argument('--candidate-src',type=Path,required=True,help='Frozen innovation.S and short_pitch.h candidate')
 p.add_argument('--out',type=Path,required=True,help='New ignored build directory')
 a=p.parse_args()
 if bool(a.node)!=bool(a.data):p.error('--node and --data must be provided together')
 if a.out.exists():p.error('Output directory must be new')
 a.out.mkdir(parents=True)
 rows=[]
 def run(command,log):
  with log.open('w',encoding='utf-8') as handle:subprocess.run(list(map(str,command)),stdout=handle,stderr=subprocess.STDOUT,check=True)
 for epoch in ['before','after']:
  codec=a.out/epoch/'Codecs/Speex/AVR'
  shutil.copytree(ROOT.parents[1]/'common',codec.parents[1]/'common')
  for folder in ['tools','tests','vendor','handoff','reference']:
   shutil.copytree(ROOT/folder,codec/folder,ignore=shutil.ignore_patterns('__pycache__','node_modules','*.mid','*.midi','*.smf'))
  shutil.copytree(a.before_src,codec/'src')
  if epoch=='after':
   for name in ['innovation.S','short_pitch.h']:shutil.copyfile(a.candidate_src/name,codec/'src'/name)
  for label,width,load in [('wb395',10,25600),('wb575',15,9600),('wb775',20,9600),('wb98',25,25600),('wb128',32,25600)]:
   for kind in ['bare','irq']:
    out=codec/'build'/(kind+'-'+label);out.mkdir(parents=True)
    if kind=='bare':command=[sys.executable,codec/'tools/build_wb.py','--avr-gcc',a.avr_gcc,'--backend','asm','--packet-bytes',width,'--enable-nb4','--low-rates',7,'--out',out]
    else:command=[sys.executable,codec/'tools/build_wb_stream_test.py','--avr-gcc',a.avr_gcc,'--packet-bytes',width,'--enable-nb4','--low-rates',7,'--frame-load-cycles',load,'--out',out]
    run(command,out/'build.log')
    binary=out/'wb.bin';rows.append(dict(epoch=epoch,kind=kind,profile=label,flashBytes=binary.stat().st_size,binarySha256=hashlib.sha256(binary.read_bytes()).hexdigest()))
    if a.node:
     observer=codec/'tests'/('verify_wb.mjs' if kind=='bare' else 'verify_wb_stream.mjs')
     run([a.node,observer,'--firmware',out,'--streams',a.data/label/'streams','--oracle',a.data/label/'oracle',*(['--packet-timing'] if kind=='bare' else [])],out/'run.log')
    print('PASS' if a.node else 'BUILT',epoch,kind,label,flush=True)
  out=codec/'build/c-control';out.mkdir(parents=True)
  run([sys.executable,codec/'tools/build_wb.py','--avr-gcc',a.avr_gcc,'--backend','c','--packet-bytes',25,'--enable-nb4','--low-rates',7,'--out',out],out/'build.log')
 before=(a.out/'before/Codecs/Speex/AVR/build/c-control/wb.bin').read_bytes();after=(a.out/'after/Codecs/Speex/AVR/build/c-control/wb.bin').read_bytes();assert before==after
 (a.out/'images.json').write_text(json.dumps(dict(images=rows,cControls=dict(compileLinkedOnly=True,byteIdentical=True,bytes=len(before),sha256=hashlib.sha256(before).hexdigest())),indent=2)+'\n',encoding='utf-8')
 print('PASS explicit C controls: compile/link only and byte-identical')

if __name__=='__main__':main()
