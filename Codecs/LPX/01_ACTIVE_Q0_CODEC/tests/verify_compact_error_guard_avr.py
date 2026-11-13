"""Source-bound full-IRQ comparison for the compact error-guard removal."""
from __future__ import annotations
import argparse,concurrent.futures,hashlib,json,shutil,subprocess,sys
from pathlib import Path

ACTIVE=Path(__file__).resolve().parents[1];REPO=ACTIVE.parents[2]
sys.path[:0]=[str(ACTIVE/'tools'),str(ACTIVE/'tests')]
import verify_attiny88_player as player_verifier
import build_attiny88_player as player_builder
from build_attiny88_player import DFP
from verify_compact_error_guard import guard_variants

REVISION='95346ea9'
RECEIPT='Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/v9-sparse80-measurements.json'
def sha(data):return hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()
def binary_sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def prepare_private_source(output,removed):
    private_repo=Path(output)/'source';private=private_repo/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
    for part in ('src','profiles','examples/ATTINY88_V5_PLAYER'):
        shutil.copytree(ACTIVE/part,private/part,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ACTIVE.parent/'validation/attiny88',private.parent/'validation/attiny88')
    shutil.copytree(REPO/'Codecs/common',private_repo/'Codecs/common')
    (private/'src/Lpx4HybridCore.cpp').write_text(removed,encoding='utf-8',newline='\n')
    return private_repo,private

def run(baseline,output,native_receipt,*,wsl=None,workers=4):
    baseline=Path(baseline).resolve();output=Path(output).resolve();native_receipt=Path(native_receipt).resolve()
    if not output.is_relative_to((REPO/'build').resolve()):raise ValueError('Use ignored repository build storage')
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('Use a fresh output directory')
    if not 1<=workers<=4:raise ValueError('Select one to four independent workers')
    frozen=subprocess.check_output(['git','show',REVISION+':'+RECEIPT],cwd=REPO)
    before=json.loads(frozen)
    if sha((baseline/'summary.json').read_bytes())!=sha(frozen):raise ValueError('Baseline receipt differs from its historical Git revision')
    core=ACTIVE/'src/Lpx4HybridCore.cpp';text=core.read_text(encoding='utf-8')
    restored,removed,present=guard_variants(text)
    archived=subprocess.check_output(['git','show',REVISION+':'+core.relative_to(REPO).as_posix()],cwd=REPO).decode().replace('\r\n','\n')
    if not present or text!=archived:raise ValueError('Use the reviewed production source with its guard retained; the candidate is created privately')
    native=read(native_receipt)
    if not (native['full_matrix'] and native['explicit_c_backend'] and native['all_api_traces_exact']
            and native['noncompact_preprocessed_exact']
            and native['variant_sha256']['without_check_sha256']==sha(removed.encode())
            and native['variant_sha256']['with_check_sha256']==sha(restored.encode())):
        raise ValueError('Full native API proof does not bind the private guard-only candidate')
    for name,digest in native['source_sha256'].items():
        if name.startswith('Codecs/LPX/01_ACTIVE_Q0_CODEC/src/') and name!=core.relative_to(REPO).as_posix():
            if sha((REPO/name).read_bytes())!=digest:raise ValueError('Native proof uses different arithmetic/header sources')
    paths=[Path(__file__),ACTIVE/'tests/verify_compact_error_guard.py',ACTIVE/'tools/build_attiny88_player.py',
        ACTIVE/'tools/verify_attiny88_player.py',ACTIVE/'examples/ATTINY88_V5_PLAYER/player.cpp',
        ACTIVE/'profiles/Lpx4Sram512.h',*sorted((ACTIVE/'src').glob('Lpx4*')),
        DFP/'avr/iotn88.h',ACTIVE.parent/'validation/attiny88/sim_player.c']
    production_source_sha256={p.relative_to(REPO).as_posix():sha(p.read_bytes()) for p in paths}
    private_repo,private=prepare_private_source(output,removed)
    private_paths=[p for p in private_repo.rglob('*') if p.is_file()]
    candidate_source_sha256={p.relative_to(private_repo).as_posix():sha(p.read_bytes()) for p in private_paths}
    candidate_source_sha256[(DFP/'avr/iotn88.h').relative_to(REPO).as_posix()]=sha((DFP/'avr/iotn88.h').read_bytes())
    def unchanged():
        for name,digest in candidate_source_sha256.items():
            p=private_repo/name if (private_repo/name).exists() else REPO/name
            if sha(p.read_bytes())!=digest:raise RuntimeError('Private measured source changed during admission')
    cases=before['cases'];results=[]
    def one(row):
        name=row['case'];source=baseline/name/'stream.lpx';golden=baseline/name/'current/expected.pwm'
        if binary_sha(source.read_bytes())!=row['data_sha256'] or binary_sha(golden.read_bytes())!=row['pwm_sha256']:
            raise ValueError('Frozen input or PWM oracle changed')
        unchanged();after=player_verifier.verify(source,output/name,wsl=wsl);unchanged()
        actual=(output/name/'actual.pwm').read_bytes()
        if not after['accepted'] or actual!=golden.read_bytes():raise AssertionError('Full IRQ playback differs from the frozen oracle')
        old=row['after'];total=after['decode_active_cpu_mean']+after['irq_max']
        speed_ok=total<=row['total_active_cycles_per_sample']
        size_ok=after['program_excluding_audio_bytes']<=old['program_excluding_audio_bytes']
        fields=('samples','flash_bytes','program_excluding_audio_bytes','embedded_audio_bytes','static_ram_bytes',
            'stack_bytes','stack_margin','underruns','min_queue','decode_active_cpu_mean','decode_cpu_cycles',
            'decode_irq_cycles','irq_max','output_gap_min','output_gap_max')
        return dict(case=name,profile=row['profile'],input_sha256=row['data_sha256'],pwm_sha256=row['pwm_sha256'],
            pwm_exact=True,no_speed_regression=speed_ok,no_program_growth=size_ok,
            before={k:old[k] for k in fields if k in old},after={k:after[k] for k in fields},
            before_total_active_cycles_per_sample=row['total_active_cycles_per_sample'],total_active_cycles_per_sample=total)
    old_builder_root,old_verifier_root=player_builder.ROOT,player_verifier.ROOT
    player_builder.ROOT=private;player_verifier.ROOT=private
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(one,row) for row in cases]
            for future in concurrent.futures.as_completed(futures):
                try:result=future.result()
                except Exception as error:
                    (output/'failure-private.json').write_text(json.dumps(dict(error_type=type(error).__name__,detail=str(error)),indent=2)+'\n',encoding='utf-8')
                    raise
                results.append(result)
                print(json.dumps(dict(completed=len(results),program_bytes=result['after']['program_excluding_audio_bytes'],
                    cycles_with_irq=result['total_active_cycles_per_sample'],stack_margin=result['after']['stack_margin'])),flush=True)
    finally:
        player_builder.ROOT=old_builder_root;player_verifier.ROOT=old_verifier_root
    unchanged();results.sort(key=lambda r:r['case'])
    summary=dict(schema='lpx-compact-error-guard-avr-v1',historical_baseline_revision=REVISION,
        historical_baseline_receipt_sha256=sha(frozen),native_api_receipt_sha256=sha(native_receipt.read_bytes()),
        native_api_source_sha256=native['source_sha256'],source_hash_encoding='UTF-8, LF',
        production_source_sha256=production_source_sha256,candidate_source_sha256=candidate_source_sha256,
        production_guard_present=present,production_cpp_sha256=production_source_sha256[core.relative_to(REPO).as_posix()],candidate_cpp_sha256=sha(removed.encode()),
        clock_hz=16000000,sample_hz=8000,queue=32,prefill=24,physical_board_measured=False,
        complete=True,accepted=all(r['no_speed_regression'] and r['no_program_growth'] for r in results),
        cases=results,all_pwm_exact=True,total_underruns=sum(r['after']['underruns'] for r in results),
        maximum_program_bytes=max(r['after']['program_excluding_audio_bytes'] for r in results),
        maximum_active_cycles_with_irq=max(r['total_active_cycles_per_sample'] for r in results),
        maximum_stack_bytes=max(r['after']['stack_bytes'] for r in results),minimum_stack_margin=min(r['after']['stack_margin'] for r in results),
        scope='Guard-only source change; complete selected historical22-case IRQ playback. No Rice0 or physical-board claim.')
    (output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--native-receipt',type=Path,required=True)
    parser.add_argument('--wsl');parser.add_argument('--workers',type=int,default=4)
    a=parser.parse_args();r=run(a.baseline,a.output,a.native_receipt,wsl=a.wsl,workers=a.workers)
    print(json.dumps({k:r[k] for k in ('complete','accepted','all_pwm_exact','total_underruns','maximum_program_bytes','maximum_active_cycles_with_irq','maximum_stack_bytes','minimum_stack_margin')}))
    raise SystemExit(0 if r['accepted'] else 1)

if __name__=='__main__':main()
