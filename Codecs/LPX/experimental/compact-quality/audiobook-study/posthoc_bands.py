"""Read-only global band/relative-octave diagnostics after phase completion.

No encoder is called. Detailed bindings and any local pitch events stay private.
This helper is deliberately outside the frozen study runner/test input list.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import runner as r
import study as s

ORIGINAL_SHA='894e1a2315929496df53494d02b0258b6f6fe8e68029e72524360f616bca5294'


def generated_source():
    original=HERE.parent/'ensemble_diagnostics.cpp'
    if s.sha(original)!=ORIGINAL_SHA:
        raise ValueError('The retained diagnostic arithmetic changed')
    text=original.read_text(encoding='utf-8')
    body=text[text.index('namespace {'):text.index('\nint main(')]
    marker='        std::cout<<",\\\"total_error_raw\\\":";value(b.totalError[path]);\n'
    extra='''        std::cout<<",\\\"total_temporal_baseline\\\":";value(a.totalTemporalError[path]);
        std::cout<<",\\\"total_temporal_raw\\\":";value(b.totalTemporalError[path]);
        std::cout<<",\\\"balanced_error_baseline\\\":";value(a.balancedError[path]);
        std::cout<<",\\\"balanced_error_raw\\\":";value(b.balancedError[path]);
        std::cout<<",\\\"balanced_temporal_baseline\\\":";value(a.balancedTemporalError[path]);
        std::cout<<",\\\"balanced_temporal_raw\\\":";value(b.balancedTemporalError[path]);
'''
    if body.count(marker)!=1:
        raise ValueError('Expected one aggregate print insertion')
    body=body.replace(marker,marker+extra,1)
    main='''
int main(int argc,char**argv){try{
 if(argc!=3)throw std::runtime_error("SOURCE_PCM SAVED_PREFIX");
 const auto reference=readPcm(argv[1]);
 if(reference.size()!=160000)throw std::runtime_error("Expected one continuous twenty-second target");
 const std::string prefix=argv[2];
 const auto baseline=loadOutput(prefix+"-baseline",reference);
 const auto selected=loadOutput(prefix+"-selected",reference);
 if(packV9(baseline)==packV9(selected))throw std::runtime_error("Only selected-changed outputs are diagnosed");
 const auto a=render(baseline),b=render(selected);
 std::cout.precision(17);std::cout<<"{\\\"fullband\\\":[";
 emitBands(reference,a,b,QualityTarget::Pwm);
 std::cout<<"],\\\"octaves\\\":[";
 emitOctaves(reference,a,b,QualityTarget::Pwm);
 std::cout<<"],\\\"native_saved_model_exact\\\":true,\\\"fullband_rule_crosscheck\\\":true,\\\"pitch_rule_crosscheck\\\":true}\\n";
 return 0;
}catch(const std::exception&){std::cerr<<"Read-only Long band diagnostic failed\\n";return 1;}}
'''
    return '#define LPX_AUDIOBOOK_BENCHMARK_NO_MAIN\n#include "benchmark.cpp"\n'+body+main


def build(base,output):
    output=s.private(output);output.mkdir(parents=True,exist_ok=True)
    source=output/'bands-generated.cpp';data=generated_source().encode('utf-8')
    if source.exists() and source.read_bytes()!=data:
        raise ValueError('Existing generated diagnostic source differs')
    if not source.exists():source.write_bytes(data)
    binary=output/'bands';receipt_path=output/'build-private.json'
    sources={**base['sources'],(HERE.parent/'ensemble_diagnostics.cpp').relative_to(s.ROOT).as_posix():ORIGINAL_SHA,
             Path(__file__).resolve().relative_to(s.ROOT).as_posix():s.sha(__file__),
             source.relative_to(s.ROOT).as_posix():s.sha(source)}
    command=base['command'].copy();old=s.builder.linux(HERE/'benchmark.cpp')
    if command.count(old)!=1:raise ValueError('Unexpected frozen source composition')
    command[command.index(old)]=s.builder.linux(source)
    command.insert(command.index('-o'),'-I'+s.builder.linux(HERE))
    command[command.index('-o')+1]=s.builder.linux(binary)
    if receipt_path.exists():
        previous=s.read(receipt_path)
        if previous['sources']==sources and previous['command']==command and binary.exists() and s.sha(binary)==previous['binary_sha256']:
            return binary,previous
        raise ValueError('Existing diagnostic build differs')
    child=subprocess.run(s.builder.launch(base['distro'])+command,capture_output=True)
    (output/'compiler-private.log').write_bytes(child.stdout+child.stderr)
    if child.returncode:raise ValueError('Diagnostic compilation failed; details stay private')
    if sources!={name:s.sha(s.ROOT/name) for name in sources}:
        raise ValueError('Diagnostic source changed during compilation')
    receipt=dict(schema='lpx-audiobook-posthoc-band-build-v1',sources=sources,command=command,
        compiler=base['compiler'],options=base['options'],distro=base['distro'],binary_sha256=s.sha(binary),
        arithmetic='Retained FullBand/PitchGuard diagnostic body; one print-only aggregate insertion; no encoder call')
    s.write(receipt_path,receipt,immutable=True)
    return binary,receipt


def rename(value):
    if isinstance(value,dict):return {k.replace('raw','selected'):rename(v) for k,v in value.items()}
    if isinstance(value,list):return [rename(v) for v in value]
    return value


def safe_row(value,case):
    result=dict(ordinal=case['ordinal'],split=case['split'],source_group=case['source_group'],
        native_saved_model_exact=value['native_saved_model_exact'],
        fullband_rule_crosscheck=value['fullband_rule_crosscheck'],pitch_rule_crosscheck=value['pitch_rule_crosscheck'])
    result['fullband']=[]
    for path in value['fullband']:
        copied={k:v for k,v in path.items() if k!='bands'}
        copied['aggregate_floor_failure']=any(path[n]>path[o]+1e-12 for n,o in (
            ('total_error_selected','total_error_baseline'),('balanced_error_selected','balanced_error_baseline'),
            ('balanced_temporal_selected','balanced_temporal_baseline')))
        copied['bands']=[{k:v for k,v in band.items() if k!='source_power'} for band in path['bands']]
        result['fullband'].append(copied)
    result['octaves']=[{k:v for k,v in path.items() if k!='additions'} for path in value['octaves']]
    if [p['path'] for p in result['fullband']]!=['pcm','pwm'] or [p['path'] for p in result['octaves']]!=['pcm','pwm']:
        raise ValueError('Expected both existing active paths')
    return result


def summary(rows):
    result={}
    for name in ('pcm','pwm'):
        values=[next(p for p in row['fullband'] if p['path']==name) for row in rows]
        bands=[b for path in values for b in path['bands'] if b['supported']]
        drops=[b for b in bands if b['retention_floor_rejected']]
        errors=[b for b in bands if b['error_floor_rejected']]
        octaves=[next(p for p in row['octaves'] if p['path']==name) for row in rows]
        result[name]=dict(selected_changed_cases=len(rows),supported_global_band_case_entries=len(bands),
            magnitude_error_regression_bands=len(errors),lower_retention_bands=len(drops),
            magnitude_error_regression_cases=sum(any(b['error_floor_rejected'] for b in p['bands']) for p in values),
            lower_retention_cases=sum(any(b['retention_floor_rejected'] for b in p['bands']) for p in values),
            aggregate_floor_failure_cases=sum(p['aggregate_floor_failure'] for p in values),
            added_relative_octave_windows=sum(p['added_octave_windows'] for p in octaves),
            worst_retention_delta_percentage_points=min((b['retention_delta_percentage_points'] for b in drops),default=0))
        for metric in ('total_error','balanced_error','balanced_temporal'):
            for label in ('baseline','selected'):
                result[name]['mean_'+metric+'_'+label]=sum(p[metric+'_'+label] for p in values)/len(values) if values else None
    return result


def main(args):
    output,freeze,base=r.load(args.study)
    cases=[c for c in freeze['cases'] if (c['ordinal']==freeze['first_development_ordinal'] if args.phase=='pilot' else c['split']==args.phase)]
    completed=[]
    for case in cases:
        value=r.completed(output,freeze,case)
        if value is None:raise ValueError('The requested phase is not completely successful')
        report=s.read(r.case_folder(output,case['ordinal'])/'encode-private.json')
        if report['selected_changed']:completed.append((case,value,report))
    records=[];private=[];software=None
    if completed:
        binary,software=build(base,args.build)
        for case,completion,report in completed:
            folder=r.case_folder(output,case['ordinal']);prefix=folder/'run'
            before={name:s.sha(folder/name) for name in completion['artifacts']}
            command=s.builder.launch(base['distro'])+[s.builder.linux(binary),s.builder.linux(case['target']),s.builder.linux(prefix)]
            child=subprocess.run(command,capture_output=True)
            if child.returncode:raise ValueError('Read-only band replay failed')
            detailed=rename(json.loads(child.stdout.decode('utf-8')))
            s.write(folder/'posthoc-bands-private.json',detailed,immutable=True)
            if before!={name:s.sha(folder/name) for name in completion['artifacts']}:
                raise ValueError('Diagnostic replay changed a frozen artifact')
            row=safe_row(detailed,case)
            retention_pass=all(not p['total_error_regressed'] and not any(b['error_floor_rejected'] or b['retention_floor_rejected'] for b in p['bands']) for p in row['fullband'])
            if retention_pass!=report['research_retention_guard_selected']:
                raise ValueError('Strict diagnostic no longer matches the frozen case')
            records.append(row)
            private.append(dict(ordinal=case['ordinal'],target=case['target'],target_sha256=case['target_sha256'],
                completion_sha256=s.sha(folder/'complete-private.json'),artifacts=completion['artifacts']))
    r.load(output)
    public_software={k:v for k,v in software.items() if k not in ('command','distro')} if software else None
    result=dict(schema='lpx-audiobook-posthoc-selected-bands-v1',phase=args.phase,posthoc=True,
        completed_phase_cases=len(cases),selected_changed_cases=len(records),cases=records,summary=summary(records),
        software=public_software,helper_source_sha256=s.sha(__file__),private_bindings_verified=True,
        scope='Changed selected outputs only, after immutable phase completion. Global 1 kHz bands and aggregate normalized/temporal errors; capped retention is a separate energy proxy. Relative octave labels are heuristic, not verified F0. No every-bin/time-local/audible/AVR guarantee, no new guard, encoding, source fitting or selection change.')
    text=json.dumps(result)
    for case,completion,report in completed:
        if case['target'] in text or case['target_sha256'] in text:raise ValueError('Private source binding exposed')
        for name,digest in completion['artifacts'].items():
            if name in text or digest in text:raise ValueError('Private artifact binding exposed')
    s.write(output/('posthoc-bands-'+args.phase+'-binding-private.json'),dict(
        schema='lpx-audiobook-posthoc-band-bindings-private-v1',freeze_sha256=s.sha(output/'freeze-private.json'),cases=private),immutable=True)
    destination=args.public.resolve();destination.relative_to(HERE.resolve());s.write(destination,result,immutable=True)
    print(json.dumps(dict(status='PASS',phase=args.phase,completed_phase_cases=len(cases),selected_changed_cases=len(records),no_encoding_or_search=True)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--phase',choices=('pilot','development','heldout'),required=True)
    parser.add_argument('--build',type=Path,required=True);parser.add_argument('--public',type=Path,required=True)
    main(parser.parse_args())
