"""Verify complete AVR PWM for selectable C/ASM and compact/reference paths.

Builds isolated images without modifying production sources. Overrides are a
fixed list of output-equivalent controls, injected only into AVR compilation.
Exact output is required; a C compatibility run may report timing underruns.
"""
import argparse,hashlib,json,subprocess
from pathlib import Path
from profile_avr import run as profile

CONFIGS={
    'c-default':(False,()),
    'c-unscaled':(False,('LPX4_EXCITATION_Q4=0',)),
    'asm-default':(True,()),
    'asm-linear':(True,('LPX4_LPC_RING=0',)),
    'asm-reference':(True,tuple(name+'=0' for name in (
        'LPX4_LPC_RING','LPX4_EXCITATION_Q4','LPX4_BATCHED_REMAINING','LPX4_ROM_POINTER',
        'LPX4_ROTATE_LPC_ANCHORS','LPX4_FAST_EXCITATION','LPX4_FAST_PITCH',
        'LPX4_FAST_UNARY','LPX4_FAST_HUFFMAN3','LPX4_FUNCTION_TUNING'))),
}

def run(source,output,avr_bin,runner,lib=None,wsl=None,v3_features=24):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);reports={}
    original_run=subprocess.run
    for name,(enable,defines) in CONFIGS.items():
        flags=['-D'+x for x in defines]
        def selected_compile(command,*args,**kwargs):
            if isinstance(command,(list,tuple)) and Path(command[0]).name in ('avr-g++','avr-g++.exe'):
                command=[command[0],*flags,*command[1:]]
            return original_run(command,*args,**kwargs)
        # profile_avr and its native verifier share subprocess; only the AVR
        # compiler executable matches the condition above. Native PCM remains
        # the unchanged reference, independent of the selected decoder layout.
        try:
            subprocess.run=selected_compile
            report=profile(source,output/name,avr_bin,runner,lib,wsl,enable,
                queue=512,prefill=384,irq_load=0,dot_unroll=9,v3_features=v3_features)
        finally:subprocess.run=original_run
        report['compiler_options']=flags+report['compiler_options']
        report['decoder_defines']=list(defines)
        report['configuration_verifier_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (output/name/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        assert report['done'] and report['pwm_native_exact'] and not report['decoder_error']
        assert report['played']==report['input_samples']
        reports[name]={key:value for key,value in report.items() if key!='occupancy_trace'}
        print(name,{k:report[k] for k in ('mean_decode_wall_cycles','underruns','flash_bytes','static_sram_bytes')},flush=True)
    assert len({r['pwm_sha256'] for r in reports.values()})==1
    result={'images':reports,'scope':'Complete identical useful PWM across selected C/ASM/control paths. Timing support applies only where underruns are zero; no physical board measured.'}
    (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--avr-bin',type=Path,required=True);p.add_argument('--sim-runner',type=Path,required=True)
    p.add_argument('--sim-lib-dir',type=Path);p.add_argument('--wsl');p.add_argument('--v3-features',type=int,default=24)
    a=p.parse_args();run(a.input,a.output,a.avr_bin,a.sim_runner,a.sim_lib_dir,a.wsl,a.v3_features)
