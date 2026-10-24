"""Faithful original LPX3 v1 excitation with a parameter-only Node LPC2 bridge.

The original reference's closed-loop 2/3/4-bit encoder/decoder is reused without
modifying it. New6/8-bit profiles use the separately named LPX4 v1 container,
with the same quantizer mathematics. No input normalization or automatic
brightness correction is applied. Coefficients come only from embedded LPC2.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT/'ATmega328/Sound/reference/lpx3'
_spec = importlib.util.spec_from_file_location('micromusic_original_hybrid_codec',REFERENCE/'hybrid_codec.py')
legacy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = legacy
_spec.loader.exec_module(legacy)
HEADER = legacy.HEADER


def digest(data):
    return hashlib.sha256(data).hexdigest()


def default_node():
    available = shutil.which('node')
    if available:
        return available
    for root in (ROOT,ROOT.parents[1]):
        candidate = root/'build/toolchains/node-22.22.3/node.exe'
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError('Node.js is required for the original LPC2 reference adapter')


class Lpc2Bridge:
    """Run the exact HTML codec through the separate native Node adapter."""
    def __init__(self,cache_root,*,node=None,adapter=None):
        self.cache_root = Path(cache_root).resolve()
        self.cache_root.mkdir(parents=True,exist_ok=True)
        self.node = str(node or default_node())
        self.adapter = Path(adapter or ROOT/'tools/lpc2-reference-cli.mjs').resolve()
        self.cache = {}

    def _run(self,args):
        done = subprocess.run([self.node,str(self.adapter),*map(str,args)],capture_output=True,text=True,
                              encoding='utf-8',timeout=180)
        if done.returncode:
            raise RuntimeError('Native LPC2 adapter failed: '+done.stderr[-2000:])

    @staticmethod
    def _read(folder):
        report = json.loads((folder/'meta.json').read_text(encoding='utf-8'))
        meta = report.get('meta',report)
        samples,sr,pre = int(meta['samples']),int(meta['sr']),float(meta['pre'])
        raw = (folder/'coefficients.f64le').read_bytes()
        if len(raw) != samples*10*8:
            raise ValueError('Native LPC2 coefficient descriptor length mismatch')
        coefficients = np.frombuffer(raw,dtype='<f8').reshape(samples,10).copy()
        if not np.all(np.isfinite(coefficients)) or not np.isfinite(pre):
            raise ValueError('Nonfinite coefficients from native LPC2 descriptor')
        return (pre,sr,coefficients),report

    def encode(self,reference,sample_rate,output,config=None):
        output = Path(output).resolve()
        output.mkdir(parents=True,exist_ok=True)
        request = dict(sampleRate=int(sample_rate),samples=np.asarray(reference,dtype=float).tolist(),
                       config={} if config is None else config)
        path = output/'input.json'
        path.write_text(json.dumps(request,separators=(',',':')),encoding='utf-8')
        self._run(['--input',path,'--output',output])
        base = (output/'base.lp2').read_bytes()
        coefficients,report = self._read(output)
        self.cache[digest(base)] = coefficients
        return base,report

    def coefficients(self,base):
        """Derive predictor data from a base container alone, without PCM."""
        key = digest(base)
        if key not in self.cache:
            folder = self.cache_root/key
            folder.mkdir(parents=True,exist_ok=True)
            path = folder/'embedded.lp2'
            path.write_bytes(base)
            self._run(['--base',path,'--output',folder])
            self.cache[key] = self._read(folder)[0]
        return self.cache[key]

    def __call__(self,base):
        return self.coefficients(base)


def inspect_container(data):
    """Strict canonical length/header checks around the unchanged v1 format."""
    if len(data) < HEADER.size:
        raise ValueError('Short LPX3 header')
    magic,version,bits,sr,samples,base_bytes,block_samples,brightness,blocks = HEADER.unpack_from(data)
    valid_profile = (magic == b'LPX3' and bits in (2,3,4)) or (magic == b'LPX4' and bits in (6,8))
    if (not valid_profile or version != 1 or not 4000 <= sr <= 96000
            or samples < 1 or samples > sr*3600 or not 20 <= block_samples <= 2048
            or brightness > 700 or base_bytes < 36 or blocks != (samples+block_samples-1)//block_samples):
        raise ValueError('Invalid LPX3/LPX4 v1 descriptor')
    excitation_bytes = (samples*bits+7)//8
    expected = HEADER.size+base_bytes+blocks+excitation_bytes
    if len(data) != expected:
        raise ValueError('LPX3 must contain exactly its base, scales and packed excitation')
    base = data[HEADER.size:HEADER.size+base_bytes]
    if base[:4] != b'LPC2' or struct.unpack_from('<H',base,6)[0] != sr or struct.unpack_from('<I',base,16)[0] != samples:
        raise ValueError('Embedded LPC2 sample rate/count disagrees with LPX3')
    remainder = (samples*bits)%8
    if remainder and data[-1] >> remainder:
        raise ValueError('Nonzero LPX3 excitation padding bits')
    return dict(format=magic.decode('ascii'),version=version,bits_per_sample=bits,sample_rate=sr,samples=samples,
                header_bytes=HEADER.size,base_bytes=base_bytes,scale_bytes=blocks,
                excitation_bytes=excitation_bytes,total_bytes=expected,block_samples=block_samples,
                brightness=brightness/1000,base_sha256=digest(base),container_sha256=digest(data))


def decode_excitation(data,coefficient_provider):
    """Decode using only the complete container and a base-byte coefficient API."""
    info = inspect_container(data)
    base = data[HEADER.size:HEADER.size+info['base_bytes']]
    cache = coefficient_provider(base)
    if cache[1] != info['sample_rate'] or len(cache[2]) != info['samples']:
        raise ValueError('Base-only coefficient provider disagrees with container')
    if info['format'] == 'LPX3':
        audio,_ = legacy.decode_lpx3(data,cache=cache)
    else:
        begin = HEADER.size+info['base_bytes']
        scales = data[begin:begin+info['scale_bytes']]
        codes = legacy.unpack_codes(data[begin+info['scale_bytes']:],info['bits_per_sample'],info['samples'])
        pre,sr,coefficients = cache
        hist = np.zeros(10,dtype=np.float64)
        emphasized = np.empty(info['samples'],dtype=np.float64)
        for block,start in enumerate(range(0,len(codes),info['block_samples'])):
            stop=min(start+info['block_samples'],len(codes))
            emphasized[start:stop] = legacy.decode_qs(codes[start:stop],legacy.byte_to_scale(scales[block]),
                                                     hist,coefficients[start:stop],info['bits_per_sample'])
        audio=np.empty(len(codes),dtype=np.float64)
        previous=0.
        for index in range(len(audio)):
            value=emphasized[index]+pre*previous
            audio[index]=np.clip(value,-1.,1.)
            previous=np.clip(value,-2.,2.)
        if info['brightness']:
            audio=legacy.apply_brightness(audio,info['brightness'])
        audio=np.clip(audio,-1.,1.).astype(np.float32)
    return audio,info


def encode_excitation(reference,sample_rate,base,bits,coefficient_provider,*,block_samples=None):
    """Use the original closed-loop loss and byte scales, brightness disabled."""
    reference = np.asarray(reference,dtype=np.float64)
    if reference.ndim != 1 or not len(reference) or not np.all(np.isfinite(reference)):
        raise ValueError('Expected complete finite mono reference PCM')
    if bits not in (2,3,4,6,8):
        raise ValueError('LPX3 supports2/3/4; the separately versioned LPX4 extension supports6/8')
    cache = coefficient_provider(base)
    if sample_rate != cache[1] or len(reference) != len(cache[2]):
        raise ValueError('Reference rate/count must equal the embedded LPC2 descriptor')
    block_samples = max(20,int(round(sample_rate*.01))) if block_samples is None else int(block_samples)
    if bits in (2,3,4):
        data,audio,training = legacy.encode_lpx3(reference,sample_rate,base,bits,block_size=block_samples,
                                                cache=cache,auto_brightness=False)
    else:
        # Same original closed-loop quantizer and scale grid, explicitly
        # separated from LPX3 v1 by magic LPX4/version1 for the new6/8-bit range.
        pre,_,coefficients=cache
        target=reference.copy();target[1:]-=pre*reference[:-1]
        history=np.zeros(10,np.float64);codes=np.zeros(len(reference),np.uint8)
        scales=bytearray();total=0.
        for start in range(0,len(reference),block_samples):
            stop=min(start+block_samples,len(reference))
            block,co=target[start:stop],coefficients[start:stop]
            energy=np.empty(len(block),dtype=np.float64)
            for j in range(len(block)):
                lag=start+j
                energy[j]=block[j]+sum(co[j,k]*target[lag-k-1] for k in range(10) if lag-k-1>=0)
            rms=max(.00005,float(np.sqrt(np.mean(energy**2))))
            nominal=rms/max(1,(1<<(bits-1))-.5)
            best=None
            for ratio in (.45,.6,.75,.9,1.,1.12,1.3,1.55,1.85,2.25,2.9):
                code=legacy.scale_to_byte(nominal*ratio)
                q,loss=legacy.encode_block_pre(block,co,history.copy(),legacy.byte_to_scale(code),bits)
                if best is None or loss<best[0]:best=loss,code,q
            loss,code,q=best
            scales.append(code);codes[start:stop]=q
            _,actual=legacy.encode_block_pre(block,co,history,legacy.byte_to_scale(code),bits)
            total+=actual
        data=HEADER.pack(b'LPX4',1,bits,sample_rate,len(reference),len(base),block_samples,0,len(scales))+base+bytes(scales)+legacy.pack_codes(codes,bits)
        audio,_=decode_excitation(data,coefficient_provider)
        training=dict(bits=bits,bytes=len(data),duration=len(reference)/sample_rate,
                      bitrate_kbps=len(data)*8*sample_rate/len(reference)/1000,mse_pre=total/len(reference),
                      blocks=len(scales),base_bytes=len(base),brightness=0.,extension='LPX4 v1; original quantizer mathematics, new6/8-bit profiles')
    info = inspect_container(data)
    info.update(training=training,brightness_policy='Disabled; no spectral tilt or global output normalization',
                decoder_implemented_for_avr=False,hardware_tested=False)
    return data,audio,info


def verify_javascript(container_path,output_path,*,node=None):
    """Run the independently retained pure JavaScript LPX3 decoder in Node."""
    javascript = r"""
const fs=require('node:fs'),vm=require('node:vm');
const [decoder,input,output]=process.argv.slice(1);
const bytes=fs.readFileSync(input);
const context=vm.createContext({Uint8Array,Float32Array,Float64Array,DataView,ArrayBuffer,
 input:new Uint8Array(bytes.buffer,bytes.byteOffset,bytes.byteLength)});
let source=fs.readFileSync(decoder,'utf8');
if(bytes.subarray(0,4).toString()==='LPX4'){
 if(!source.includes("!=='LPX3'")||!source.includes('![2,3,4].includes(bits)'))throw Error('Original decoder guard markers changed');
 // Only format/bit-range guards change. The independently retained original
 // JavaScript unpacking, all-pole filter and deemphasis mathematics are exact.
 source=source.replace("!=='LPX3'","!=='LPX4'").replace('![2,3,4].includes(bits)','![6,8].includes(bits)');
}
vm.runInContext(source,context,{filename:decoder});
const decoded=vm.runInContext('decodeLPX3(input)',context);
fs.writeFileSync(output,Buffer.from(decoded.pcm.buffer,decoded.pcm.byteOffset,decoded.pcm.byteLength));
"""
    done = subprocess.run([str(node or default_node()),'-e',javascript,str(REFERENCE/'lpx3_decoder.js'),
                           str(Path(container_path).resolve()),str(Path(output_path).resolve())],
                          capture_output=True,text=True,encoding='utf-8',timeout=180)
    if done.returncode:
        raise RuntimeError('Independent JavaScript LPX3 decoder failed: '+done.stderr[-2000:])
    return np.frombuffer(Path(output_path).read_bytes(),dtype='<f4').copy()
