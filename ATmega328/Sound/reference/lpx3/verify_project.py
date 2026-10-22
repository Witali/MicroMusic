#!/usr/bin/env python3
"""Cross-validate Python/JavaScript LPX3 decoders for every bundled voice and profile."""
from pathlib import Path
import numpy as np, json, hashlib
from playwright.sync_api import sync_playwright
from hybrid_codec import ROOT,decode_lpx3

JS=(ROOT/'lpx3_decoder.js').read_text(encoding='utf8')
FILES=[ROOT/'samples'/clip/f'voice_v3_{n}bit.lpx3'
       for clip in ['vinni','xtuj-ntt','ne-otv'] for n in [2,3,4]]

def main():
    # Build the Python reference outputs BEFORE opening another Sync Playwright
    # context; nested Sync API contexts are not allowed.
    reference=[]
    for f in FILES:
        data=f.read_bytes()
        pcm,meta=decode_lpx3(data)
        reference.append((f,data,pcm,meta))
    results=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        pg=browser.new_page();pg.set_content('<script>'+JS+'</script>',wait_until='load')
        for f,data,python_pcm,info in reference:
            js_pcm=pg.evaluate('s=>Array.from(decodeLPX3(Uint8Array.from(s)).pcm)',list(data))
            err=float(np.max(np.abs(python_pcm-np.array(js_pcm))))
            assert len(python_pcm)==len(js_pcm) and err<=3e-6,(f,err)
            assert np.isfinite(python_pcm).all()
            print(f.parent.name,f.name,'bytes',len(data),'samples',len(python_pcm),'max error',err,flush=True)
            results.append({'clip':f.parent.name,'bits':info['bits'],'samples':len(python_pcm),'max_err':err,
                            'sha256':hashlib.sha256(data).hexdigest()})
        browser.close()
    (ROOT/'verification.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    print('PASS: 9/9 streams',flush=True)

if __name__=='__main__':main()
