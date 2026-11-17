"""Encode real PCM/WAV at a selected LPX v9 rate, or decode using its header.

The existing P4/P6 search and 320-sample packet geometry are unchanged. Higher
sampling rates shorten packets and increase the real bitrate; they are not
quality-calibrated presets. AVR real-time admission requires a separate IRQ
verification for the selected stream and target.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from numbers import Integral
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

import numpy as np

from batch_decoder import BatchSession
from output_paths import protect_outputs
from pcm16_wav import write_pcm16_wav
import speech_compact
import speech_v4
from speech_v9 import repack
from standard_metrics import pwm_duties
from wav_lpc import load_wav


SAMPLE_RATES=(8000,12000,16000)
ROOT=Path(__file__).resolve().parents[1]

REFERENCE=r'''
#include <cstdio>
#include <iostream>
#include <iterator>
#include <vector>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
#include "Lpx4HybridCore.h"
int main(int argc,char** argv){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 if(argc!=2)return 1;
 std::vector<unsigned char> data((std::istreambuf_iterator<char>(std::cin)),{});
 if(data.size()>65535)return 2;
 Lpx4HybridCore d;if(!d.begin(data.data(),data.size()))return 3;
 if(argv[1][0]=='s'){
  short s;while(d.nextS16(s)){unsigned short u=s;putchar(u&255);putchar(u>>8);}
 }else{unsigned char p;while(d.next(p))putchar(p);}
 return d.error()||!d.finished()?4:0;
}
'''


class ProcessReference:
    """Selectable C compiler/subprocess backend, including Windows plus WSL."""
    def __init__(self,compact_version=5,*,wsl=None,cxx=None):
        self.version=compact_version;self.wsl=wsl
        self.compiler=shlex.split(cxx or os.environ.get('CXX','g++'))
        if not self.compiler:raise ValueError('Expected a C++ compiler command')

    def _path(self,path):
        p=Path(path).resolve()
        if self.wsl and os.name=='nt':return '/mnt/'+p.drive[0].lower()+'/'+ '/'.join(p.parts[1:])
        return str(p)

    def _command(self,*args,**kwargs):
        prefix=['wsl','-d',self.wsl,'--'] if self.wsl else []
        return subprocess.run([*prefix,*args],capture_output=True,**kwargs)

    def __enter__(self):
        self.temp=tempfile.TemporaryDirectory(prefix='lpx-v9-reference-')
        folder=Path(self.temp.name);source=folder/'reference.cpp'
        source.write_text(REFERENCE,encoding='ascii')
        self.executable=folder/('reference.exe' if os.name=='nt' and not self.wsl else 'reference')
        flags=['-DLPX4_ENABLE_ASM=0','-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
            f'-DLPX4_COMPACT_VERSION={self.version}']
        if self.version==9:flags+=['-DLPX4_COMPACT_ONLY=1']
        try:
            result=self._command(*self.compiler,'-O2','-std=c++11',*flags,'-I'+self._path(ROOT/'src'),
                self._path(source),self._path(ROOT/'src/Lpx4HybridCore.cpp'),'-o',self._path(self.executable))
            if result.returncode:raise RuntimeError('C reference compilation failed: '+result.stderr.decode(errors='replace'))
            return self
        except BaseException:
            self.temp.cleanup();raise

    def __exit__(self,*exc):self.temp.cleanup()

    def _decode(self,blob,expected_samples,mode):
        result=self._command(self._path(self.executable),mode,input=bytes(blob))
        dtype='<i2' if mode=='s16' else 'u1'
        if result.returncode or len(result.stdout)!=expected_samples*(2 if mode=='s16' else 1):return None
        return np.frombuffer(result.stdout,dtype=dtype).copy()

    def decode_one_s16(self,blob,expected_samples):return self._decode(blob,expected_samples,'s16')
    def decode_one(self,blob,expected_samples):return self._decode(blob,expected_samples,'pwm')


def reference_session(version,*,wsl=None,cxx=None):
    if wsl or cxx or os.environ.get('CXX'):
        return ProcessReference(version,wsl=wsl,cxx=cxx)
    return BatchSession('batch',speech=True,speech_compact=True,
        compact_only=version==9,compact_version=version)


def validate_rate(rate):
    if isinstance(rate,bool) or not isinstance(rate,Integral) or rate not in SAMPLE_RATES:
        raise ValueError('Expected an 8000, 12000 or 16000 Hz sampling rate')
    return int(rate)


def metadata(blob):
    """Validate one complete v9 stream and report its stored nominal rate."""
    data=bytes(blob)
    if data[:2]!=b'L9':raise ValueError('Expected one complete LPX v9 stream')
    canonical,_=repack(data,9)
    if canonical!=data:raise ValueError('Noncanonical LPX v9 stream')
    rate=validate_rate(int.from_bytes(data[3:5],'little'))
    n=int.from_bytes(data[5:7],'little')
    return dict(sample_rate=rate,samples=n,duration_seconds=n/rate,
        file_bytes=len(data),payload_bytes=len(data)-13,
        file_bitrate_bps=len(data)*8*rate/n,payload_bitrate_bps=(len(data)-13)*8*rate/n,
        packet_samples=320,packet_ms=320000/rate,
        stream_sha256=hashlib.sha256(data).hexdigest())


def decode_pcm(blob,decoder):
    """Return PCM16 from the portable C reference, with the header rate."""
    info=metadata(blob)
    pcm=decoder.decode_one_s16(bytes(blob),info['samples'])
    if pcm is None:raise ValueError('The C reference rejected the LPX stream')
    duty=decoder.decode_one(bytes(blob),info['samples'])
    if duty is None or not np.array_equal(duty,pwm_duties(pcm)):
        raise AssertionError('C reference PCM/PWM outputs disagree')
    return pcm,info


def encode_pcm(reference,profile,legacy_decoder,v9_decoder,*,sample_rate=8000,
               pre=13926,bandwidth=.97,allow_zero_scale=False):
    """Analyze PCM already sampled at sample_rate; do not retag old audio.

    Legacy8k metadata is used only for an internal, unchanged per-sample search
    and model check. The final v9 stream is independently decoded after storing
    the real input rate. No legacy higher-rate file is exposed.
    """
    rate=validate_rate(sample_rate)
    legacy,expected,analysis=speech_v4.encode(reference,profile,legacy_decoder,
        pre=pre,bandwidth=bandwidth,allow_zero_scale=allow_zero_scale)
    compact,_=speech_compact.repack(legacy)
    data=bytearray(repack(compact,9)[0])
    data[3:5]=rate.to_bytes(2,'little')
    blob=bytes(data)
    pcm,info=decode_pcm(blob,v9_decoder)
    if not np.array_equal(pcm,expected):
        raise AssertionError('Final rate-bearing v9 PCM differs from the search model')
    info.update(schema='lpx-v9-audio-v1',profile=profile,native_model_exact=True,
        higher_rate_quality_calibrated=False,avr_realtime_verified=False,
        pitch_lag_samples=[18,145],pitch_frequency_hz=[rate/145,rate/18],
        analysis=analysis['analysis'],preQ14=pre,bandwidth=bandwidth,
        allow_zero_scale=bool(allow_zero_scale),encoder_seconds=analysis['seconds'])
    return blob,pcm,info


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    modes=ap.add_subparsers(dest='mode',required=True)
    enc=modes.add_parser('encode',help='Resample WAV before analysis and encode P4/P6 to v9')
    enc.add_argument('input',type=Path);enc.add_argument('output',type=Path)
    enc.add_argument('--sample-rate',type=int,choices=SAMPLE_RATES,default=8000)
    enc.add_argument('--profile',type=int,choices=(4,6),required=True)
    enc.add_argument('--allow-zero-scale',action='store_true')
    dec=modes.add_parser('decode',help='Write PCM16 WAV at the stored nominal sampling rate')
    dec.add_argument('input',type=Path);dec.add_argument('output',type=Path)
    for mode in (enc,dec):
        mode.add_argument('--wsl',help='Compile and run the C reference in this WSL distribution')
        mode.add_argument('--cxx',help='C++ compiler command (default CXX or g++)')
    args=ap.parse_args(argv)
    if args.mode=='encode':
        paths=[args.output/name for name in ('audio.lpx','decoded.wav','target.wav','report.json')]
        protect_outputs([args.input],paths)
        reference,input_info=load_wav(args.input,sample_rate=args.sample_rate)
        with reference_session(5,wsl=args.wsl,cxx=args.cxx) as legacy,reference_session(9,wsl=args.wsl,cxx=args.cxx) as v9:
            blob,pcm,info=encode_pcm(reference,args.profile,legacy,v9,
                sample_rate=args.sample_rate,allow_zero_scale=args.allow_zero_scale)
        info['input']=input_info
        info['input']['output_rate']=args.sample_rate
        info['input']['source_sha256']=hashlib.sha256(args.input.read_bytes()).hexdigest()
        args.output.mkdir(parents=True,exist_ok=True)
        paths[0].write_bytes(blob)
        write_pcm16_wav(paths[1],pcm,info['sample_rate'])
        write_pcm16_wav(paths[2],reference,info['sample_rate'])
        paths[3].write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8')
    else:
        protect_outputs([args.input],[args.output])
        with reference_session(9,wsl=args.wsl,cxx=args.cxx) as decoder:pcm,info=decode_pcm(args.input.read_bytes(),decoder)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        write_pcm16_wav(args.output,pcm,info['sample_rate'])
    print(json.dumps(info,indent=2))
    return info


if __name__=='__main__':main()
