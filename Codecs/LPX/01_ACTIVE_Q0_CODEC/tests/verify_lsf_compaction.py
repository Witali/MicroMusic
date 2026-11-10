"""Fresh matched 0320c101/current LSF-compaction IRQ measurements.

Stdlib Python; AVR-GCC, g++, simavr1.6 and libelf. Run on Windows with
--wsl Ubuntu, or on Linux without --wsl. Use a fresh ignored build directory.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,subprocess,sys

ACTIVE=Path(__file__).resolve().parents[1]
REPO=ACTIVE.parents[2]
REL=Path('Codecs/LPX/01_ACTIVE_Q0_CODEC')
BASELINE='0320c1014618188a3121fdfef0be55b30690d977'
PARTS=('src','profiles','examples/ATTINY88_V5_PLAYER')
FIELDS=('samples','flash_bytes','program_excluding_audio_bytes','embedded_audio_bytes',
        'static_ram_bytes','stack_bytes','stack_margin','underruns','min_queue',
        'decode_cpu_cycles','decode_active_cpu_mean','irq_max','output_gap_min','output_gap_max')

def sha(data):return hashlib.sha256(data).hexdigest()
def textsha(data):return sha(data.replace(b'\r\n',b'\n'))
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module);return module
def git(*arguments):
    result=subprocess.run(['git',*arguments],cwd=REPO,capture_output=True)
    if result.returncode:
        # Native Git cannot resolve a Windows-created worktree's .git path in WSL.
        result=subprocess.run(['git.exe',*arguments],cwd=REPO,capture_output=True)
    if result.returncode:raise RuntimeError('Local baseline Git read failed')
    return result.stdout

def run(output,target,*,wsl=None,case=None):
    output=Path(output).resolve()
    if not output.is_relative_to((REPO/'build').resolve()) or output==REPO/'build':
        raise ValueError('Use an ignored build subdirectory')
    if output.exists() and any(output.iterdir()):raise ValueError('Use a fresh directory')
    output.mkdir(parents=True,exist_ok=True)
    prefix=['wsl','-d',wsl,'--'] if wsl else []
    def path(value):
        value=Path(value).resolve()
        return '/mnt/'+value.drive[0].lower()+'/'+ '/'.join(value.parts[1:]) if wsl and value.drive else str(value)
    def command(*arguments,input=None):
        result=subprocess.run([*prefix,*map(str,arguments)],input=input,capture_output=True)
        if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
        return result.stdout
    sys.path[:0]=[str(ACTIVE/'tests'),str(ACTIVE/'tools')]
    import verify_atmega328p_v9 as mega
    from verify_attiny88_universal import streams
    from speech_v9 import repack
    from test_speech_v9 import sparse_fixture,all_pairs

    paths=[]
    for part in PARTS:
        paths.extend(p for p in (ACTIVE/part).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    paths.extend(p for p in (REPO/'Codecs/common').rglob('*.h'))
    observer=ACTIVE.parent/'validation/attiny88/sim_player.c';paths.append(observer)
    for name in ('build_attiny88_player.py','verify_attiny88_player.py'):
        paths.append(ACTIVE/'tools'/name)
    binding={p.relative_to(REPO).as_posix():textsha(p.read_bytes()) for p in paths}
    source_binding={}
    for variant in ('before','after'):
        root=output/variant/'source'
        for source in paths:
            relative=source.relative_to(REPO);destination=root/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            data=git('show',BASELINE+':'+relative.as_posix()) if variant=='before' else source.read_bytes()
            destination.write_bytes(data)
        port=root/REL
        tools=output/variant/'tools';tools.mkdir(parents=True)
        if target=='mega':
            player=port/'examples/ATTINY88_V5_PLAYER/player.cpp'
            player.write_text(mega.adapt_player(player.read_text()),encoding='utf-8',newline='\n')
            adapted=root/observer.relative_to(REPO)
            adapted.write_text(mega.adapt_observer(adapted.read_text()),encoding='utf-8',newline='\n')
        for name,transform in (('build',mega.adapt_builder),('verify',mega.adapt_verifier)):
            source=port/'tools'/('build_attiny88_player.py' if name=='build' else 'verify_attiny88_player.py')
            filename=f'{name}_mega_player.py' if target=='mega' else f'{name}_attiny88_player.py'
            text=source.read_text();text=transform(text) if target=='mega' else text
            (tools/filename).write_text(text,encoding='utf-8',newline='\n')
        source_binding[variant]={p.relative_to(root).as_posix():textsha(p.read_bytes())
                                 for p in root.rglob('*') if p.is_file()}

    device=output/'device'
    if target=='mega':
        probe=subprocess.run([*prefix,'avr-g++','-mmcu=atmega328p','-E','-H','-x','c++','-'],
                             input=b'#include <avr/io.h>\n',capture_output=True,check=True)
        header=next(line.split()[-1] for line in probe.stderr.decode().splitlines()
                    if line.strip().endswith('/avr/iom328p.h'))
        (device/'avr').mkdir(parents=True)
        (device/'avr/iom328p.h').write_bytes(command('cat',header))

    inputs=output/'inputs';inputs.mkdir()
    jobs=[]
    if target=='tiny':
        jobs=[(name,repack(source.read_bytes())[0]) for name,source in streams(inputs)]
        jobs.append(('bread-low15',repack((REPO/'web-player/audio/lpx-bread/low15.lpx').read_bytes())[0]))
        jobs.append(('chego-2k',repack((ACTIVE/'tests/fixtures/chego-2k-v8.lpx').read_bytes())[0]))
        for style,lag,pre,bright in [('changing',145,0,0),('clusters',18,16384,11469),
                ('changing',145,8192,11469),('changing',18,16383,11468),('clusters',145,1,1)]:
            jobs.append((f's80-{style}-lag{lag}-pre{pre}-bright{bright}',
                         repack(sparse_fixture(12800,style,pre,bright,lag)[0])[0]))
        jobs.append(('all-pairs',repack(bytes(all_pairs()))[0]))
        assert len(jobs)==22
    else:
        public=[ACTIVE/'tests/fixtures/chego-2k-v8.lpx',
                REPO/'web-player/audio/lpx-speech/chego/compact.lpx',
                REPO/'web-player/audio/lpx-speech/chego/quality.lpx']
        blobs=[repack(source.read_bytes())[0] for source in public]
        blobs.append(repack(sparse_fixture(12800,'changing',16383,11468,18)[0])[0])
        jobs=list(zip(mega.CASES,blobs))
    if case:
        jobs=[job for job in jobs if job[0]==case]
        if not jobs:raise ValueError('Unknown public case')
    rows=[]
    for variant in ('before','after'):
        root=output/variant/'source';port=root/REL;tools=output/variant/'tools'
        suffix='mega_player' if target=='mega' else 'attiny88_player'
        builder=load('build_'+suffix,tools/('build_'+suffix+'.py'))
        builder.ROOT=port;builder.REPO=REPO
        builder.DFP=device if target=='mega' else REPO/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include'
        verifier=load('verify_'+suffix,tools/('verify_'+suffix+'.py'))
        original_build=verifier.build
        def matched_build(*arguments,**keywords):
            if not keywords.get('assembly',False):keywords['extra_flags']=('-finline-small-functions',)
            return original_build(*arguments,**keywords)
        verifier.build=matched_build
        for backend in (('asm','c') if target=='mega' else ('asm',)):
            for name,blob in jobs:
                source=inputs/(name+'.lpx');source.write_bytes(blob)
                folder=output/variant/backend/name
                result=verifier.verify(source,folder,wsl=wsl,assembly=backend=='asm',
                                       asm_isr=target=='tiny',queue=32)
                expected=(folder/'expected.pwm').read_bytes();actual=(folder/'actual.pwm').read_bytes()
                assert result['accepted'] and actual==expected,(variant,target,backend,name)
                cost=json.loads((folder/'build.json').read_text())
                options=[option.replace(path(output),'<output>').replace(path(REPO),'<repo>')
                         for option in cost['compiler_options']]
                row=dict(variant=variant,case=name,target=target,backend=backend,
                    **{field:result[field] for field in FIELDS},
                    total_cycles=result['decode_active_cpu_mean']+result['irq_max'],
                    full_pwm_exact=True,pwm_sha256=sha(actual),input_sha256=sha(blob),
                    compiler_options=options)
                if variant=='after':
                    old=next(r for r in rows if r['variant']=='before' and r['backend']==backend and r['case']==name)
                    row.update(old_pwm_exact=row['pwm_sha256']==old['pwm_sha256'],
                        no_program_growth=row['program_excluding_audio_bytes']<=old['program_excluding_audio_bytes'],
                        no_speed_loss=row['total_cycles']<=old['total_cycles'],
                        no_stack_growth=row['stack_bytes']<=old['stack_bytes'])
                    assert all(row[key] for key in ('old_pwm_exact','no_program_growth','no_speed_loss','no_stack_growth')),row
                rows.append(row)
                (output/'progress.json').write_text(json.dumps(rows,indent=2)+'\n')
                print(json.dumps({key:row[key] for key in ('variant','target','backend','case','program_excluding_audio_bytes','total_cycles')}),flush=True)
    for relative,digest in binding.items():
        assert textsha((REPO/relative).read_bytes())==digest,'Current source changed'
    for variant,recorded in source_binding.items():
        for relative,digest in recorded.items():
            assert textsha((output/variant/'source'/relative).read_bytes())==digest,'Frozen source changed'
    report=dict(schema='lpx-lsf-compaction-admission-v1',baseline_revision=BASELINE,
        current_source_sha256=binding,snapshot_source_sha256=source_binding,
        driver_sha256=textsha(Path(__file__).read_bytes()),target=target,
        physical_board_measured=False,clock_hz=16000000,sample_hz=8000,
        queue=32,prefill=24,lpc_segments=2,memory_profile='SRAM512',
        cycle_accounting='active decoder CPU mean plus complete IRQ; foreground queue work excluded',
        complete=True,cases=rows)
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--target',choices=('tiny','mega'),required=True)
    parser.add_argument('--wsl');parser.add_argument('--case')
    arguments=parser.parse_args()
    run(arguments.output,arguments.target,wsl=arguments.wsl,case=arguments.case)
