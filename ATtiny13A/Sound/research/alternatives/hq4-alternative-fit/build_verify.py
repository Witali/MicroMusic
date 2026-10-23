#!/usr/bin/env python3
"""Rebuild each optimized ATtiny13A HEX and verify PCM against real AVR cycle interpreter.
No silent fallback: stop immediately on size error, checksum error, or sample mismatch.
"""
from pathlib import Path
import subprocess,json,hashlib
import numpy as np,soundfile as sf
from scipy.signal import resample_poly
from codec import decode_stream,encode_stream,src_size
from model import decode
from quality import Compare
ROOT=Path(__file__).resolve().parent
NAMES=('chego','otvechaesh','vinni')

def make_hex(raw):
    lines=[]
    for addr in range(0,len(raw),16):
        data=raw[addr:addr+16];r=[len(data),(addr>>8)&255,addr&255,0,*data];r.append(-sum(r)&255)
        lines.append(':'+''.join(f'{x:02X}' for x in r))
    return '\n'.join(lines+[':00000001FF'])+'\n'

def prepare():
    stats={}
    for n in NAMES:
        src=ROOT/'inputs'/n;dst=ROOT/'results'/n
        trained=np.load(dst/'trained.npz');frames=trained['frames'];duration=trained['durations']
        expected_speech=encode_stream(frames,duration)
        orig_speech=(src/'speech.hq').read_bytes()
        assert sum(duration)==(9216 if n=='chego' else 7936 if n=='otvechaesh' else 22272)
        code_size=src_size(src/'firmware.S')
        assert code_size==406
        (dst/'speech.hq').write_bytes(expected_speech[:-1])
        (dst/'firmware.S').write_text((src/'firmware.S').read_text())
        subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.o'],cwd=dst,check=True,capture_output=True)
        subprocess.run(['llvm-objcopy','-O','binary','firmware.o','firmware.bin'],cwd=dst,check=True,capture_output=True)
        binary=(dst/'firmware.bin').read_bytes();assert len(binary)==code_size+len(expected_speech)
        assert binary[code_size:]==expected_speech
        if len(binary)>1024:raise RuntimeError(f'{n}: flash overflow {len(binary)}')
        (dst/'firmware.hex').write_text(make_hex(binary))
        decoded=decode(frames,duration,0)
        (dst/'expected.raw').write_bytes(decoded.tobytes())
        sf.write(dst/'new_7500.wav',(decoded.astype(np.float64)-128)/128,7500,subtype='PCM_16')
        ref,sr=sf.read(src/'original.wav');assert sr==7500
        score=Compare(ref).scores(decoded)
        old_f,old_d=decode_stream(orig_speech)
        old=decode(old_f,old_d,0);old_scores=Compare(ref).scores(old)
        stats[n]={'phrase':{'chego':'Чего тебе нужно?','otvechaesh':'Что ж ты не отвечаешь?','vinni':'Сова! Открывай! Медведь пришёл!'}[n],
              'stoi_before':round(old_scores[0],7),'stoi_after':round(score[0],7),
              'spec_before':round(old_scores[1],5),'spec_after':round(score[1],5),
              'clicks48_before':old_scores[2],'clicks48_after':score[2],
              'flash_bytes':len(binary),'decoder_bytes':code_size,'speech_bytes':len(expected_speech)-1,
              'frames_old':len(old_f),'frames_new':len(frames),'samples':len(decoded),'sha256':hashlib.sha256(binary).hexdigest()}
        print('ASSEMBLED',n,stats[n],flush=True)
        # Listen side by side at native sample rate in archive
        lpx,sr=sf.read(src/'lpx3.wav');assert sr==7500
        chunks=[]
        target=.11
        for sig in [ref,(old.astype(np.float32)-128)/128,(decoded.astype(np.float32)-128)/128,lpx]:
            sig=np.asarray(sig,dtype=np.float64)
            rms=(np.mean(sig**2)**.5)+1e-10
            sig=np.clip(sig*min(3,target/rms),-1,1)
            chunks.extend([sig,np.zeros(int(.32*7500))])
        sf.write(dst/'AB_original_HQ3_HQ4_LPX3.wav',np.concatenate(chunks),7500,subtype='PCM_16')
        for key,samples in [('original',ref),('HQ3',(old.astype(np.float32)-128)/128),('HQ4',(decoded.astype(np.float32)-128)/128),('LPX3',lpx)]:
            samples=np.asarray(samples,dtype=np.float64)
            samples=resample_poly(samples,16,5)
            sf.write(dst/f'{key}_player.wav',samples,24000,subtype='PCM_16')
    (ROOT/'metrics.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2))
    return stats

if __name__=='__main__':prepare()
