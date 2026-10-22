#!/usr/bin/env python3
"""Fully automated LPC2 Improved v11 reference encoding using the original
browser codec without porting its complex LSF mathematics.
Requires chromium + Python Playwright. Output: .lp2 stream and PCM WAV.
"""
from pathlib import Path
import argparse, numpy as np, soundfile as sf, shutil
from scipy.signal import resample_poly
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--source',type=Path,default=ROOT/'references/original_reference.wav')
 ap.add_argument('--out',type=Path,default=ROOT/'results')
 ap.add_argument('--codec-html',type=Path,default=ROOT/'lpc2_improved_encoder.html')
 args=ap.parse_args()
 if not args.codec_html.exists():raise SystemExit('Missing local LPC2 Improved codec HTML from v11')
 args.out.mkdir(parents=True,exist_ok=True)
 y,sr=sf.read(args.source)
 if y.ndim>1:y=y.mean(axis=1)
 if sr!=8000:
  import math
  g=math.gcd(sr,8000)
  y=resample_poly(y,8000//g,sr//g)
 wave=np.clip(y,-1,1).astype('float32')
 with sync_playwright() as p:
  chromium=shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')
  kwargs={'executable_path':chromium} if chromium else {}
  browser=p.chromium.launch(headless=True,args=['--no-sandbox'],**kwargs)
  page=browser.new_page()
  page.set_content(args.codec_html.read_text(encoding='utf-8'),wait_until='load')
  page.set_default_timeout(90000)
  res=page.evaluate('''async (data) => {
    const x=new Float32Array(data);
    const config={frameMs:20,windowMs:32,pre:.85,voicing:.38,pitchSmooth:.65,repeat:.05};
    const enc=await encodeLPC2(x,8000,config);
    const bin=packLPC2(enc.meta,enc.frames,enc.analysis);
    const decoded=await synthLPC2(enc.meta,enc.frames,.35);
    return {bytes:Array.from(new Uint8Array(bin.buffer)),samples:Array.from(decoded),frames:enc.frames.length,stats:bin.stats};
  }''',wave.tolist())
  browser.close()
 (args.out/'teacher.lp2').write_bytes(bytes(res['bytes']))
 sf.write(args.out/'teacher_8000.wav',np.asarray(res['samples'],dtype=float),8000,subtype='PCM_16')
 print('Encoded',res['frames'],'LPC2 frames,',len(res['bytes']),'bytes,',len(res['samples']),'samples')
 return res
if __name__=='__main__':main()
