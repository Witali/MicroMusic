"""Persistent unchanged C receivers for Windows Python through WSL pipes.

Only decoding/oracle access. No encoder search, dependency installation,
firmware change, fallback receiver or subprocess per individual candidate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import threading

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[4]
ACTIVE=REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
OUTPUT=REPO/'build/compact-quality/sparse2'
HELLO=struct.Struct('<5I')
REQUEST=struct.Struct('<6I')
RESPONSE=struct.Struct('<IIi10I')


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def linux_path(path):
    path=Path(path).resolve()
    if os.name=='nt':return '/mnt/'+path.drive[0].lower()+'/'+('/'.join(path.parts[1:]))
    return str(path)


def launcher(distro):return ['wsl','-d',distro,'--'] if os.name=='nt' else []


def build_servers(output=OUTPUT,*,distro='Ubuntu'):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    inputs=[ACTIVE/'src/Lpx4HybridCore.cpp',HERE/'decoder_server.cpp',
            *sorted((ACTIVE/'src').glob('Lpx4*.h')),
            *(ACTIVE/'src'/name for name in ['cos_table.inc','cos_half_table.inc','scale_table.inc'])]
    before={p.relative_to(REPO).as_posix():digest(p) for p in inputs}
    prefix=launcher(distro);compiler=subprocess.check_output(prefix+['g++','--version'],text=True).splitlines()[0]
    receipt=dict(schema='lpx-sparse2-native-ipc-v1',protocol=1,compiler=compiler,inputs=before,variants={})
    for kind,compact in [('common',0),('v5-only',1)]:
        binary=output/('decoder-'+kind)
        defines=['LPX4_ENABLE_ASM=0','LPX4_FLOAT_SYNTHESIS=0','LPX4_ENABLE_SPEECH=1',
                 'LPX4_ENABLE_SPEECH_COMPACT=1','LPX4_COMPACT_VERSION=5','LPX4_COMPACT_ONLY='+str(compact)]
        command=['g++','-O2','-std=c++11','-ffp-contract=off',*('-D'+d for d in defines),
                 '-I'+linux_path(ACTIVE/'src'),linux_path(inputs[0]),linux_path(inputs[1]),'-o',linux_path(binary)]
        done=subprocess.run(prefix+command,capture_output=True,text=True)
        if done.returncode:raise RuntimeError(done.stdout+done.stderr)
        receipt['variants'][kind]=dict(binary=str(binary),sha256=digest(binary),bytes=binary.stat().st_size,
                                        compact_only=compact,command=command)
    if before!={p.relative_to(REPO).as_posix():digest(p) for p in inputs}:
        raise RuntimeError('Native receiver inputs changed during build')
    (output/'build.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    return receipt


class NativeReceiver:
    """BatchDecoder-compatible fixed PCM16/PWM methods; invalid streams return None.

    Metadata is exposed by decode_result/last_metadata, not inferred from success.
    Transport corruption is an exception. One owner serializes requests with a
    lock; distinct common/v5-only contexts retain independent processes.
    """
    numeric_mode='fixed'
    float_synthesis=False
    compact_version=5

    def __init__(self,kind='common',output=OUTPUT,*,distro='Ubuntu'):
        if kind not in ('common','v5-only'):raise ValueError('Select common or v5-only')
        self.kind=kind;self.output=Path(output).resolve();self._lock=threading.Lock()
        receipt=json.loads((self.output/'build.json').read_text(encoding='utf-8'))
        if receipt.get('schema')!='lpx-sparse2-native-ipc-v1' or receipt.get('protocol')!=1:
            raise ValueError('Unknown native build manifest')
        for relative,expected in receipt['inputs'].items():
            if digest(REPO/relative)!=expected:raise ValueError('Native source fingerprint changed; rebuild explicitly')
        variant=receipt['variants'][kind];binary=Path(variant['binary'])
        if digest(binary)!=variant['sha256']:raise ValueError('Native executable fingerprint changed')
        self.process=subprocess.Popen(launcher(distro)+[linux_path(binary)],stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
        self.request_id=self.calls=self.streams=0;self.last_metadata=None
        try:hello=HELLO.unpack(self._read(HELLO.size))
        except Exception:
            self.close();raise
        if hello!=(0x5348504c,1,variant['compact_only'],5,0):
            self.close();raise RuntimeError('Native receiver handshake mismatch')
        self.metadata=dict(protocol=hello[1],compact_only=hello[2],compact_version=hello[3],numeric_mode=hello[4],
                           binary_sha256=variant['sha256'],compiler=receipt['compiler'])

    def _read(self,count):
        result=bytearray()
        while len(result)<count:
            data=self.process.stdout.read(count-len(result))
            if not data:raise RuntimeError('Native receiver closed or truncated its response')
            result.extend(data)
        return bytes(result)

    def decode_result(self,blob,expected_samples,*,s16=False):
        if type(expected_samples) is not int or not 0<=expected_samples<=1000000:
            raise ValueError('Invalid expected sample count')
        if not isinstance(blob,(bytes,bytearray,memoryview)):raise TypeError('Expected binary stream')
        blob=bytes(blob)
        if len(blob)>65535:raise ValueError('Stream exceeds bounded native ROM API')
        import numpy as np
        with self._lock:
            if self.process.stdin.closed or self.process.poll() is not None:raise RuntimeError('Native receiver is closed')
            self.request_id+=1
            request=REQUEST.pack(0x3144504c,self.request_id,int(s16),len(blob),expected_samples,0)+blob
            # Raw pipe writes may be short on either platform.
            pending=memoryview(request)
            while pending:
                written=self.process.stdin.write(pending)
                if not written:raise RuntimeError('Native receiver input pipe closed')
                pending=pending[written:]
            header=RESPONSE.unpack(self._read(RESPONSE.size))
            magic,identifier,status,got,declared,rate,produced,error,finished,count,compact,version,numeric=header
            if magic!=0x3152504c or identifier!=self.request_id or (compact,version,numeric)!=(int(self.kind=='v5-only'),5,0):
                raise RuntimeError('Native receiver response identity mismatch')
            if count>expected_samples*(2 if s16 else 1):raise RuntimeError('Oversized native response')
            data=self._read(count)
            meta=dict(status=status,decoded_samples=got,declared_samples=declared,sample_rate=rate,
                      produced_samples=produced,error=error,finished=bool(finished),payload_bytes=count,
                      compact_only=compact,compact_version=version,numeric_mode=numeric)
            self.last_metadata=meta;self.calls+=1;self.streams+=1
            if status:
                if count:raise RuntimeError('Failed native decode included an unexpected payload')
                return None,meta
            if got!=expected_samples or declared!=expected_samples or produced!=expected_samples or error or not finished:
                raise RuntimeError('Native success metadata does not describe complete EOF')
            if count!=expected_samples*(2 if s16 else 1):raise RuntimeError('Native output length mismatch')
            return np.frombuffer(data,dtype='<i2' if s16 else np.uint8).copy(),meta

    def decode_one_s16(self,blob,expected_samples):return self.decode_result(blob,expected_samples,s16=True)[0]
    def decode_one(self,blob,expected_samples):return self.decode_result(blob,expected_samples)[0]
    def decode_many_s16(self,blobs,expected_samples):return [self.decode_one_s16(blob,expected_samples) for blob in blobs]
    def decode_many(self,blobs,expected_samples):return [self.decode_one(blob,expected_samples) for blob in blobs]

    def close(self):
        if not hasattr(self,'process'):return
        with self._lock:
            if not self.process.stdin.closed:self.process.stdin.close()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate();self.process.wait(timeout=5)
            self.process.stdout.close();self.process.stderr.close()

    def __enter__(self):return self
    def __exit__(self,*exc):self.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--distro',default='Ubuntu');args=parser.parse_args()
    print(json.dumps(build_servers(args.output,distro=args.distro),indent=2))
