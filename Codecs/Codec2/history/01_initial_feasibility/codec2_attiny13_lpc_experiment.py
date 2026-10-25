"""Research prototype: standard Codec2 3200 bitstream -> alternate LPC source-filter synthesizer.
NOT a bit-exact or quality-validated Codec2 decoder; host-side floating-point only.
Depends on installed system libcodec2, numpy, scipy. Derivative Codec2 parameter decoder
calls system libcodec2; original Codec2 is LGPL-2.1.
"""
import os,ctypes,ctypes.util,math,wave
import numpy as np
from scipy.signal import lfilter

LIB = ctypes.CDLL(ctypes.util.find_library('codec2'))
LIB.codec2_create.argtypes=[ctypes.c_int];LIB.codec2_create.restype=ctypes.c_void_p
LIB.codec2_encode.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ubyte),ctypes.POINTER(ctypes.c_short)]
LIB.codec2_decode.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_short),ctypes.POINTER(ctypes.c_ubyte)]
LIB.codec2_destroy.argtypes=[ctypes.c_void_p]
LIB.lspd_bits.argtypes=[ctypes.c_int];LIB.lspd_bits.restype=ctypes.c_int
LIB.decode_lspds_scalar.argtypes=[ctypes.POINTER(ctypes.c_float),ctypes.POINTER(ctypes.c_int),ctypes.c_int]
LIB.lsp_to_lpc.argtypes=[ctypes.POINTER(ctypes.c_float),ctypes.POINTER(ctypes.c_float),ctypes.c_int]
LIB.decode_energy.argtypes=[ctypes.c_int,ctypes.c_int];LIB.decode_energy.restype=ctypes.c_float


def bits_unpacked(frame):
    off=0
    def take(n):
        nonlocal off
        val=0
        for j in range(n):
            val=(val<<1) | ((frame[off>>3]>>(7-(off&7)))&1)
            off+=1
        return val
    v0,v1=take(1),take(1)
    pitch=take(7); energy=take(5)
    lspd=[take(LIB.lspd_bits(j)) for j in range(10)]
    assert off==64
    lsp=(ctypes.c_float*10)()
    LIB.decode_lspds_scalar(lsp,(ctypes.c_int*10)(*lspd),10)
    return [v0,v1], 2*math.pi/160+(2*math.pi/20-2*math.pi/160)*pitch/128, LIB.decode_energy(energy,5),np.array(lsp,dtype=float)


def stable_lpc(lsp):
    # The reference harmonics-based Codec2 doesn't require strictly stable LPC IIR poles.
    # A standalone time-domain IIR vocoder does; explicitly enforce monotonic LSP spacing.
    theta=np.clip(np.asarray(lsp,dtype=float),.08,math.pi-.08)
    theta=np.sort(theta)
    for i in range(1,10):theta[i]=max(theta[i],theta[i-1]+.04)
    if theta[-1]>math.pi-.06:
        theta*= (math.pi-.06)/theta[-1]
    ctheta=(ctypes.c_float*10)(*theta)
    ak=(ctypes.c_float*11)()
    LIB.lsp_to_lpc(ctheta,ak,10)
    a=np.array(ak,dtype=float)
    poles=np.roots(a)
    if np.max(np.abs(poles))>.995:
        gamma=min(.98,.985/np.max(np.abs(poles)))
        a*= gamma**np.arange(11)
    return a


def synthesize(frames):
    # 80 output samples from each 10ms subframe, 2 subframes per 8-byte bitstream.
    # This version uses a stationary pulse/noise excitation and explicit block gain.
    # Goal: evaluate the *qualitative* effect of replacing harmonic IFFT with 10-pole LPC.
    sr=8000;prev_lsp=np.linspace(.25,2.75,10);prev_w0=2*math.pi/100;prev_E=0.1
    prev_v=0;zi=np.zeros(10);phase=0.0
    rng=np.random.default_rng(1337)
    out=[];stability=[]
    for frame in frames:
        vs,w0,E,lsp=bits_unpacked(frame)
        for sub in range(2):
            frac=(sub+1)/2
            th=(1-frac)*prev_lsp+frac*lsp
            a=stable_lpc(th)
            # smooth over 10ms to reduce transient LP filtering
            cur_w0=(1-frac)*prev_w0+frac*w0
            cur_E=np.exp((1-frac)*math.log(max(prev_E,.01))+frac*math.log(max(E,.01)))
            n=80; e=np.zeros(n,dtype=float)
            for i in range(n):
                phase+=cur_w0/(2*math.pi)
                if phase>=1.0:
                    phase-=1.0
                    if vs[sub]:
                        e[i]+=math.sqrt((2*math.pi)/cur_w0) # impulse excitation
            if not vs[sub]:
                e=rng.standard_normal(n)
            else:
                e+=rng.standard_normal(n)*0.08
            y,zi=lfilter([1.0],a,e,zi=zi)
            # approximate Codec2 energy: offline experimental gain normalization.
            # Not part of timed AVR path; an embedded implementation needs LUT/scaling.
            rms=float(np.sqrt(np.mean(y*y)+1e-10))
            target=float(35*math.sqrt(cur_E))
            factor=np.clip(target/(rms+1e-9),0.001,1000)
            out.append(np.clip(y*factor,-32768,32767).astype(np.int16))
            stability.append(max(abs(np.roots(a))))
        prev_lsp,prev_w0,prev_E,prev_v=lsp,w0,E,vs[-1]
    return np.concatenate(out),max(stability)


def run():
    input_file='/mnt/data/Speex_AVR_NB8_FastLPC_2026-10-23/audio/speech_ru_optimized.wav'
    out_dir='/mnt/data/Codec2_ATTiny13_Research'; os.makedirs(out_dir,exist_ok=True)
    with wave.open(input_file,'rb') as w:
        assert (w.getframerate(),w.getnchannels(),w.getsampwidth())==(8000,1,2)
        pcm=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
    obj=LIB.codec2_create(0)
    bits=[];reference=[]
    for i in range(0,len(pcm)-159,160):
        frame=(ctypes.c_short*160)(*[int(x) for x in pcm[i:i+160]])
        packed=(ctypes.c_ubyte*8)()
        LIB.codec2_encode(obj,packed,frame)
        decoded=(ctypes.c_short*160)()
        LIB.codec2_decode(obj,decoded,packed)
        bits.append(bytes(packed));reference.extend(decoded)
    LIB.codec2_destroy(obj)
    alt,maxpole=synthesize(bits)
    def writewav(filename,signal):
        with wave.open(os.path.join(out_dir,filename),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
            w.writeframes(np.asarray(signal,dtype='<i2').tobytes())
    writewav('reference_codec2_3200.wav',reference)
    writewav('experimental_lpc_synthesis.wav',alt)
    with open(os.path.join(out_dir,'codec2_3200_8byte_frames.bin'),'wb') as f: f.write(b''.join(bits))
    print('frames',len(bits),'bits',len(bits)*64, 'max pole',maxpole,'ref_rms',np.std(reference),'alternative_rms',np.std(alt))
    print('outputs',out_dir)
if __name__=='__main__':run()
