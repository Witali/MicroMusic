#!/usr/bin/env python3
"""Qualify integer main/weighted spectra in the full ATmega64A decoder."""
import argparse,datetime,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from verify_decoder import metrics
from study_fixed_precision import admissible
from audit_decoder_memory import device_memory
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/analysis'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cc',default='clang');p.add_argument('--avr-gcc',default='avr-gcc');p.add_argument('--node',default='node')
    p.add_argument('--frames',type=int);p.add_argument('--bits',type=int);p.add_argument('--host-only',action='store_true');p.add_argument('--record',action='store_true')
    a=p.parse_args()
    if a.frames is not None and a.frames<=0:p.error('--frames must be positive')
    if a.record and (a.frames is not None or a.host_only):p.error('--record requires complete AVR streams')
    study=json.loads((ROOT/'reports/faithful-precision.json').read_text());baseline=json.loads((ROOT/'reports/spectral-decoder.json').read_text())
    for name,wanted in study['sources'].items():assert front.digest(ROOT/name)==wanted,name
    assert study['baseline_report_sha256']==front.digest(ROOT/'reports/spectral-decoder.json')
    bits=a.bits if a.bits is not None else study['selection']['component_bits']
    if a.record and bits!=study['selection']['component_bits']:p.error('--record uses the selected minimum width')
    chosen=next(r for r in study['results'] if r['component_bits']==bits);assert chosen['passes'],chosen
    BUILD.mkdir(parents=True,exist_ok=True);source=front.VENDOR/'src';legacy=ROOT/'AVR/Codec2_Tiny13_Quality_R2/tests'
    flags=['-DCODEC2_FIXED_BITS=16','-DCODEC2_FIXED_TWIDDLE_Q=10','-DCODEC2_FIXED_WIDE_LAST=0','-DCODEC2_ROOT_Q=11','-DCODEC2_ROOT_TABLE_BITS=6','-DCODEC2_WEIGHT_BITS=24','-DCODEC2_WEIGHT_TWIDDLE_Q=22','-DCODEC2_WEIGHT_DIRECT_PAIR=1','-DCODEC2_WEIGHT_SPLIT24=0','-DCODEC2_WEIGHT_AVR_INT24=0','-DCODEC2_WEIGHT_ROUND_LEGACY=0','-DCODEC2_FAITHFUL_BITS='+str(bits)]
    includes=['-I'+str(ROOT/'include'),'-I'+str(ROOT/'src'),'-I'+str(source)]
    common=[a.cc,'-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_ANALYSIS_CHECKS=1','-DCODEC2_FIXED_CHECKS=1','-DCODEC2_WEIGHT_CHECKS=1',*flags,*includes]
    sources=[ROOT/'src/analysis_decoder.c',ROOT/'src/faithful_analysis.c',ROOT/'src/fixed_weight.c',ROOT/'src/fixed_inverse.c',ROOT/'src/fixed_fifth.c',ROOT/'src/compact_fft.c',ROOT/'src/parameters.c',source/'lsp.c']
    suffix='.exe' if os.name=='nt' else '';libm=[] if os.name=='nt' else ['-lm'];program=BUILD/('decode'+suffix);api=BUILD/('api'+suffix)
    front.run([*common,*sources,ROOT/'tests/hybrid_decode.c','-o',program,*libm]);front.run([*common,*sources,ROOT/'tests/hybrid_api.c','-o',api,*libm])
    api_test=front.run([api,legacy/'speech.c2zx',legacy/'codec2_3200_8byte_frames.bin'],capture_output=True,text=True).stdout.strip();print(api_test,flush=True)
    streams=[]
    for name,path in [('speech.c2zx',legacy/'speech.c2zx'),('codec2_3200_8byte_frames.bin',legacy/'codec2_3200_8byte_frames.bin'),('all-11333',front.BUILD/'frames.bin')]:
        previous=next(s for s in baseline['streams'] if s['name']==name);oracle=ROOT.parents[1]/'build/codec2/spectral'/(name+'.upstream.pcm')
        assert front.digest(path)==previous['packet_sha256'] and front.digest(oracle)==previous['oracle_sha256']
        output=BUILD/(name+'.pcm');front.run([program,path,output]);(BUILD/(name+'.upstream.pcm')).write_bytes(oracle.read_bytes())
        record={'name':name,'frames':path.stat().st_size//8,'packet_sha256':front.digest(path),'oracle_sha256':front.digest(oracle),'output_sha256':front.digest(output),**metrics(output.read_bytes(),oracle.read_bytes())}
        assert admissible(record),record
        assert record['output_sha256']==next(s for s in chosen['streams'] if s['name']==name)['output_sha256']
        streams.append(record);print(json.dumps(record),flush=True)
    report={'precision':{'component_bits':bits,'significand_bits':24},'precision_study_sha256':front.digest(ROOT/'reports/faithful-precision.json'),'baseline_report_sha256':front.digest(ROOT/'reports/spectral-decoder.json'),'root_precision':baseline['root_precision'],'api_test':api_test,'streams':streams,'host_compiler':front.run([a.cc,'--version'],capture_output=True,text=True).stdout.splitlines()[0]}
    if not a.host_only:
        output=BUILD/'atmega64a';output.mkdir(exist_ok=True);memory=device_memory(a.avr_gcc,'atmega64a');prefix=a.avr_gcc[:-3] if a.avr_gcc.endswith('gcc') else a.avr_gcc.replace('gcc.exe','')
        avr_flags=[*flags,'-DCODEC2_ANALYSIS_CHECKS=0','-DCODEC2_FIXED_CHECKS=0','-DCODEC2_WEIGHT_CHECKS=0']
        front.run([a.avr_gcc,'-mmcu=atmega64a','-Os','-std=c99','-fstack-usage','-fno-strict-aliasing','-ffunction-sections','-fdata-sections',*avr_flags,*includes,*sources,ROOT/'tests/avr_hybrid.c','-Wl,--gc-sections,-Map='+str(output/'decoder.map'),'-Wl,--defsym=__DATA_REGION_ORIGIN__='+str(0x800000+memory['RAMSTART']),'-Wl,--defsym=__DATA_REGION_LENGTH__='+str(memory['RAMEND']-memory['RAMSTART']+1),'-Wl,--defsym=__TEXT_REGION_LENGTH__='+str(memory['FLASHEND']+1),'-o',output/'decoder.elf','-lm'],cwd=output)
        front.run([prefix+'objcopy','-O','binary',output/'decoder.elf',output/'decoder.bin'])
        with (output/'symbols.txt').open('wb') as f:front.run([prefix+'nm','-n',output/'decoder.elf'],stdout=f)
        report['avr_build']={'mcu':'atmega64a','compiler':front.run([a.avr_gcc,'--version'],capture_output=True,text=True).stdout.splitlines()[0],'binary_sha256':front.digest(output/'decoder.bin'),'manufacturer_header_memory':memory,'defines':avr_flags,'section_sizes':front.run([prefix+'size','-A',output/'decoder.elf'],capture_output=True,text=True).stdout}
        front.dump(BUILD/'host-verification.json',report);front.run([a.node,ROOT/'tests/verify_analysis_avr.mjs',*(['--frames',str(a.frames)] if a.frames is not None else [])]);report['avr_execution']=json.loads((BUILD/'avr-execution.json').read_text())
    names=['tools/verify_analysis.py','tests/verify_analysis_avr.mjs']
    report['sources']={**study['sources'],**{n:front.digest(ROOT/n) for n in names}};report['verified_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();report['scope']='Complete decoder with integer main LPC/weighted spectra, IFFT and postfilter power. Main spectrum uses common block scale and original 24-significand rounding. Boundaries, phase, normalization and other stages still float. No active IRQ, board or real-time admission.'
    front.dump(BUILD/'verification.json',report)
    if a.record:front.dump(ROOT/'reports/analysis-decoder.json',report)
if __name__=='__main__':main()
