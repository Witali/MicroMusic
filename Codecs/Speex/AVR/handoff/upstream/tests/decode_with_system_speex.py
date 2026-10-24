#!/usr/bin/env python3
"""Decode restricted 20-byte Speex NB8 frames with installed original libspeex.

This is the *system* binary reference (may be floating-point), not the
user's R4 and not the still-unbuilt AVR port. It checks stream legitimacy.
"""
import argparse
import os
import ctypes as C
import ctypes.util
import struct
import wave
import math
from pathlib import Path

class SpeexBits(C.Structure):
    _fields_ = [
        ('chars', C.c_void_p), ('nbBits', C.c_int), ('charPtr', C.c_int),
        ('bitPtr', C.c_int), ('owner', C.c_int), ('overflow', C.c_int),
        ('buf_size', C.c_int), ('reserved1', C.c_int), ('reserved2', C.c_void_p)]

lib = C.CDLL(ctypes_lib := (os.environ.get('SPEEX_LIBRARY') or ctypes.util.find_library('speex') or 'libspeex.so.1'))
lib.speex_lib_get_mode.argtypes = [C.c_int]
lib.speex_lib_get_mode.restype = C.c_void_p
lib.speex_decoder_init.argtypes = [C.c_void_p]
lib.speex_decoder_init.restype = C.c_void_p
lib.speex_decoder_destroy.argtypes = [C.c_void_p]
lib.speex_decoder_ctl.argtypes = [C.c_void_p, C.c_int, C.c_void_p]
lib.speex_decoder_ctl.restype = C.c_int
lib.speex_decode_int.argtypes = [C.c_void_p, C.POINTER(SpeexBits), C.POINTER(C.c_int16)]
lib.speex_decode_int.restype = C.c_int
lib.speex_bits_init.argtypes = [C.POINTER(SpeexBits)]
lib.speex_bits_destroy.argtypes = [C.POINTER(SpeexBits)]
lib.speex_bits_read_from.argtypes = [C.POINTER(SpeexBits), C.c_void_p, C.c_int]

def decode(data):
    assert len(data) % 20 == 0
    mode = lib.speex_lib_get_mode(0)  # narrowband
    assert mode
    st = lib.speex_decoder_init(mode)
    if not st: raise RuntimeError('speex_decoder_init failed')
    z = C.c_int32(0)
    for ctl in (0, 44): # SPEEX_SET_ENH, SPEEX_SET_HIGHPASS
        if lib.speex_decoder_ctl(st, ctl, C.byref(z)):
            raise RuntimeError('Speex control failed')
    bits = SpeexBits()
    lib.speex_bits_init(C.byref(bits))
    out = (C.c_int16 * 160)()
    pcm = []
    for i in range(len(data)//20):
        raw = C.create_string_buffer(data[20*i:20*(i+1)])
        lib.speex_bits_read_from(C.byref(bits), raw, 20)
        ret = lib.speex_decode_int(st, C.byref(bits), out)
        if ret < 0: raise RuntimeError(f'Decode failed at frame {i}: {ret}')
        pcm.extend(out)
    lib.speex_bits_destroy(C.byref(bits))
    lib.speex_decoder_destroy(st)
    return pcm

def metrics(a, b):
    if len(a)!=len(b):raise ValueError(f'PCM lengths differ {len(a)} {len(b)}')
    n=len(a)
    if not n:return None
    energy = sum(int(x)*int(x) for x in a)
    err = sum((int(x)-int(y))**2 for x,y in zip(a,b))
    dot = sum(int(x)*int(y) for x,y in zip(a,b))
    e2 = sum(int(y)*int(y) for y in b)
    return {'samples':n,'identical':sum(x==y for x,y in zip(a,b)),
            'SNR_dB': float('inf') if not err else 10*math.log10(energy/err) if energy else -float('inf'),
            'corr': dot/(math.sqrt(energy*e2)) if energy and e2 else None}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('input', type=Path)
    p.add_argument('--wav', type=Path)
    p.add_argument('--compare-wav', type=Path)
    args=p.parse_args()
    pcm=decode(args.input.read_bytes())
    print('system libspeex:',ctypes_lib, 'decoded',len(pcm)//160,'frames')
    if args.wav:
        with wave.open(str(args.wav),'wb') as w:
            w.setparams((1,2,8000,0,'NONE','not compressed'))
            w.writeframes(struct.pack('<%dh'%len(pcm),*pcm))
    if args.compare_wav:
        with wave.open(str(args.compare_wav),'rb') as w:
            assert w.getnchannels()==1 and w.getsampwidth()==2 and w.getframerate()==8000
            b=struct.unpack('<%dh'%w.getnframes(),w.readframes(w.getnframes()))
        print('system libspeex vs custom R4:', metrics(pcm,b))

if __name__=='__main__':main()
