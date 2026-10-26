#!/usr/bin/env python3
"""Qualify integer main/weighted spectra in the full ATmega64A decoder."""
import argparse,datetime,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from verify_decoder import metrics
from study_fixed_precision import admissible
from audit_decoder_memory import device_memory
import verify_decoder as original
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/sums32'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cc',default='clang');p.add_argument('--avr-gcc',default='avr-gcc');p.add_argument('--node',default='node')
    p.add_argument('--frames',type=int);p.add_argument('--host-only',action='store_true');p.add_argument('--record',action='store_true')
    a=p.parse_args()
    if a.frames is not None and a.frames<=0:p.error('--frames must be positive')
    if a.record and (a.frames is not None or a.host_only):p.error('--record requires complete AVR streams')
    study=json.loads((ROOT/'reports/adaptive-precision.json').read_text());baseline=json.loads((ROOT/'reports/spectral-decoder.json').read_text())
    for name,wanted in study['sources'].items():assert front.digest(ROOT/name)==wanted,name
    assert study['baseline_report_sha256']==front.digest(ROOT/'reports/spectral-decoder.json')
    canonical=json.loads((ROOT/'reports/canonical-decoder.json').read_text())
    for name,wanted in canonical['sources'].items():assert front.digest(ROOT/name)==wanted,name
    from generate_narrow_spectrum import generate_weight,generate_fast
    assert generate_weight()==(ROOT/'src/fixed_weight_sums32.c').read_bytes()
    assert generate_fast()==(ROOT/'src/fast_analysis_sums32.c').read_bytes()
    config=study['selection'];assert config is not None
    chosen=next(r for r in study['results'] if all(r[k]==v for k,v in config.items()));assert chosen['passes']
    from generate_lpc_math import generate as math_tables
    from generate_canonical_decoder import generate as decoder_source
    assert math_tables()==(ROOT/'src/lpc_math_tables.inc').read_bytes()
    assert decoder_source()==(ROOT/'src/canonical_decoder.c').read_bytes()
    compat=json.loads((ROOT/'reports/lpc-math-compat.json').read_text())
    for name,wanted in compat['sources'].items():assert front.digest(ROOT/name)==wanted,name
    BUILD.mkdir(parents=True,exist_ok=True);source=front.VENDOR/'src';legacy=ROOT/'AVR/Codec2_Tiny13_Quality_R2/tests'
    flags=['-DCODEC2_FIXED_BITS=16','-DCODEC2_FIXED_TWIDDLE_Q=10','-DCODEC2_FIXED_WIDE_LAST=0','-DCODEC2_ROOT_Q=11','-DCODEC2_ROOT_TABLE_BITS=6','-DCODEC2_WEIGHT_BITS=24','-DCODEC2_WEIGHT_TWIDDLE_Q=22','-DCODEC2_WEIGHT_DIRECT_PAIR=1','-DCODEC2_WEIGHT_SPLIT24=0','-DCODEC2_WEIGHT_AVR_INT24=0','-DCODEC2_WEIGHT_ROUND_LEGACY=0','-DCODEC2_LPC_NATIVE_COMPAT=1','-DCODEC2_FAITHFUL_BITS='+str(config['faithful_bits']),'-DCODEC2_ANALYSIS_BITS='+str(config['component_bits']),'-DCODEC2_ANALYSIS_TWIDDLE_Q='+str(config['twiddle_q']),'-DCODEC2_ANALYSIS_DIRECT_PAIR=1','-DCODEC2_ANALYSIS_GUARD_BITS='+str(config['guard_bits'])]
    includes=['-I'+str(ROOT/'include'),'-I'+str(ROOT/'src'),'-I'+str(source)]
    common=[a.cc,'-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_LPC_MATH_CHECKS=1','-DCODEC2_ANALYSIS_CHECKS=1','-DCODEC2_FIXED_CHECKS=1','-DCODEC2_WEIGHT_CHECKS=1',*flags,*includes]
    sources=[ROOT/'src/canonical_decoder.c',ROOT/'src/adaptive_analysis.c',ROOT/'src/fast_analysis_sums32.c',ROOT/'src/fixed_weight_sums32.c',ROOT/'src/fixed_inverse.c',ROOT/'src/fixed_fifth.c',ROOT/'src/compact_fft.c',ROOT/'src/parameters.c',ROOT/'src/canonical_lpc.c',ROOT/'src/lpc_math.c']
    suffix='.exe' if os.name=='nt' else '';libm=[] if os.name=='nt' else ['-lm'];program=BUILD/('decode'+suffix);api=BUILD/('api'+suffix)
    front.run([*common,*sources,ROOT/'tests/hybrid_decode.c','-o',program,*libm]);front.run([*common,*sources,ROOT/'tests/hybrid_api.c','-o',api,*libm])
    api_test=front.run([api,legacy/'speech.c2zx',legacy/'codec2_3200_8byte_frames.bin'],capture_output=True,text=True).stdout.strip();print(api_test,flush=True)
    lifetime=BUILD/('compact-helpers'+suffix)
    front.run([*common,ROOT/'tests/compact_analysis_helpers.c','-o',lifetime,*libm])
    lifetime_test=front.run([lifetime],capture_output=True,text=True).stdout.strip();print(lifetime_test,flush=True)
    math_program=BUILD/('lpc-math'+suffix)
    front.run([*common,ROOT/'src/lpc_math.c',ROOT/'tests/lpc_math.c','-o',math_program,*libm])
    math_test=json.loads(front.run([math_program],capture_output=True,text=True).stdout);assert math_test['reachable_cosine_differences']==0
    arithmetic=BUILD/('sum32'+suffix)
    front.run([*common,ROOT/'tests/weight_sum32.c','-o',arithmetic,*libm])
    arithmetic_test=front.run([arithmetic],capture_output=True,text=True).stdout.strip();print(arithmetic_test,flush=True)
    streams=[]
    for name,path in [('speech.c2zx',legacy/'speech.c2zx'),('codec2_3200_8byte_frames.bin',legacy/'codec2_3200_8byte_frames.bin'),('all-11333',front.BUILD/'frames.bin')]:
        previous=next(s for s in baseline['streams'] if s['name']==name);oracle=ROOT.parents[1]/'build/codec2/spectral'/(name+'.upstream.pcm')
        assert front.digest(path)==previous['packet_sha256'] and front.digest(oracle)==previous['oracle_sha256']
        output=BUILD/(name+'.pcm');front.run([program,path,output]);(BUILD/(name+'.upstream.pcm')).write_bytes(oracle.read_bytes())
        record={'name':name,'frames':path.stat().st_size//8,'packet_sha256':front.digest(path),'oracle_sha256':front.digest(oracle),'output_sha256':front.digest(output),**metrics(output.read_bytes(),oracle.read_bytes())}
        assert admissible(record),record
        assert record['output_sha256']==next(s for s in chosen['streams'] if s['name']==name)['output_sha256']
        assert record['output_sha256']==next(s for s in canonical['streams'] if s['name']==name)['output_sha256']
        streams.append(record);print(json.dumps(record),flush=True)
    # Exercise the refinement path with the complete decoder call stack. The
    # archived phrases do not trigger it at the selected guard. Keep this new
    # sequence outside precision selection and compare to original upstream C.
    packets=[bytes([value])*8 for value in (0,255,85,170) for _ in range(4)]
    packets += [bytes(0 if i==slot else 255 for i in range(8)) for slot in range(8)]
    stress=BUILD/'conditioning.bin';stress.write_bytes(b''.join(packets))
    manifest=json.loads((front.VENDOR/'UPSTREAM.json').read_text())
    for item in manifest['files']:assert front.digest(front.VENDOR/item['path'])==item['sha256'],item['path']
    original.BUILD=BUILD/'oracle';selected=original.reference_sources(a.cc)
    oracle_program=BUILD/('upstream'+suffix)
    front.run([a.cc,'-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_MODE_EN_DEFAULT=0','-DCODEC2_MODE_3200_EN=1','-I'+str(source),'-I'+str(ROOT/'include'),'-I'+str(original.BUILD/'include'),*selected,source/'pack.c',source/'codec2_fft.c',source/'lsp.c',source/'postfilter.c',source/'kiss_fft.c',source/'kiss_fftr.c',ROOT/'tests/upstream_decode.c','-o',oracle_program,*libm])
    name='conditioning-stress';oracle=BUILD/(name+'.upstream.pcm');output=BUILD/(name+'.pcm')
    front.run([oracle_program,stress,oracle]);front.run([program,stress,output])
    record={'name':name,'packet_path':stress.name,'frames':len(packets),'packet_sha256':front.digest(stress),'oracle_sha256':front.digest(oracle),'output_sha256':front.digest(output),**metrics(output.read_bytes(),oracle.read_bytes())}
    assert admissible(record),record
    assert record['output_sha256']==next(s for s in canonical['streams'] if s['name']==name)['output_sha256']
    streams.append(record);print(json.dumps(record),flush=True)
    assert [s['name'] for s in streams]==['speech.c2zx','codec2_3200_8byte_frames.bin','all-11333','conditioning-stress']
    report={'precision':config,'precision_study_sha256':front.digest(ROOT/'reports/adaptive-precision.json'),'baseline_report_sha256':front.digest(ROOT/'reports/spectral-decoder.json'),'root_precision':baseline['root_precision'],'api_test':api_test,'lifetime_test':lifetime_test,'sum32_test':arithmetic_test,'exact_baseline_report_sha256':front.digest(ROOT/'reports/canonical-decoder.json'),'lpc_math_native_test':math_test,'lpc_math_compat_report_sha256':front.digest(ROOT/'reports/lpc-math-compat.json'),'streams':streams,'host_compiler':front.run([a.cc,'--version'],capture_output=True,text=True).stdout.splitlines()[0]}
    report['conditioning_stress']={'purpose':'Independent 24-frame extreme/transition holdout, outside precision selection; exercises the wide path with full call stack.','packets_hex':[x.hex() for x in packets],'upstream_commit':manifest['commit'],'upstream_manifest_sha256':front.digest(front.VENDOR/'UPSTREAM.json'),'oracle_binary_sha256':front.digest(oracle_program)}
    if not a.host_only:
        output=BUILD/'atmega64a';output.mkdir(exist_ok=True);memory=device_memory(a.avr_gcc,'atmega64a');prefix=a.avr_gcc[:-3] if a.avr_gcc.endswith('gcc') else a.avr_gcc.replace('gcc.exe','')
        avr_flags=[*flags,'-DCODEC2_LPC_MATH_CHECKS=0','-DCODEC2_ANALYSIS_CHECKS=0','-DCODEC2_FIXED_CHECKS=0','-DCODEC2_WEIGHT_CHECKS=0']
        front.run([a.avr_gcc,'-mmcu=atmega64a','-Os','-std=c99','-fstack-usage','-fno-strict-aliasing','-ffunction-sections','-fdata-sections',*avr_flags,*includes,*sources,ROOT/'tests/avr_hybrid.c','-Wl,--gc-sections,-Map='+str(output/'decoder.map'),'-Wl,--defsym=__DATA_REGION_ORIGIN__='+str(0x800000+memory['RAMSTART']),'-Wl,--defsym=__DATA_REGION_LENGTH__='+str(memory['RAMEND']-memory['RAMSTART']+1),'-Wl,--defsym=__TEXT_REGION_LENGTH__='+str(memory['FLASHEND']+1),'-o',output/'decoder.elf','-lm'],cwd=output)
        front.run([prefix+'objcopy','-O','binary',output/'decoder.elf',output/'decoder.bin'])
        with (output/'symbols.txt').open('wb') as f:front.run([prefix+'nm','-n',output/'decoder.elf'],stdout=f)
        report['avr_build']={'mcu':'atmega64a','compiler':front.run([a.avr_gcc,'--version'],capture_output=True,text=True).stdout.splitlines()[0],'binary_sha256':front.digest(output/'decoder.bin'),'manufacturer_header_memory':memory,'defines':avr_flags,'section_sizes':front.run([prefix+'size','-A',output/'decoder.elf'],capture_output=True,text=True).stdout}
        front.dump(BUILD/'host-verification.json',report);front.run([a.node,ROOT/'tests/verify_sums32_avr.mjs',*(['--frames',str(a.frames)] if a.frames is not None else [])]);report['avr_execution']=json.loads((BUILD/'avr-execution.json').read_text())
    names=['tools/verify_sums32.py','tests/verify_sums32_avr.mjs','tests/compact_analysis_helpers.c','tests/upstream_decode.c','tools/verify_decoder.py','vendor/codec2-1.2.0/UPSTREAM.json']
    names+=['src/canonical_decoder.c','src/canonical_lpc.c','src/lpc_math.c','src/lpc_math.h','src/lpc_math_tables.inc','src/lpc_math_compat.inc','tests/lpc_math.c','tools/generate_lpc_math.py','tools/generate_lpc_compat.py','tools/generate_canonical_decoder.py']
    names+=['src/fixed_weight_sums32.c','src/fast_analysis_sums32.c','src/weight_sum32.h','tools/generate_narrow_spectrum.py','tests/weight_sum32.c']
    report['sources']={**study['sources'],**{n:front.digest(ROOT/n) for n in names}};report['verified_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();report['scope']='Complete decoder with integer main LPC/weighted spectra, IFFT and postfilter power. Main spectrum uses a narrow integer pass and selective faithful integer refinement. Boundaries, phase, normalization and other stages still float. No active IRQ, board or real-time admission.'
    front.dump(BUILD/'verification.json',report)
    if a.record:front.dump(ROOT/'reports/sums32-decoder.json',report)
if __name__=='__main__':main()
